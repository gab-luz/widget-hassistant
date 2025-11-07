#!/usr/bin/env python3
"""Build and publish platform-specific releases for the Home Assistant widget.

This script automates the following steps:

* Determine an appropriate release version based on ``pyproject.toml`` and the
  existing GitHub releases.
* Build standalone binaries for Linux and Windows using PyInstaller.
* Create a GitHub release and upload the generated artifacts.

The script is intentionally opinionated to match the project's current layout
and dependencies.  It assumes that ``main.py`` is the entrypoint for the
application and that PyInstaller can produce functional executables without a
custom spec file.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import requests

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    import tomli as tomllib  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST_DIR = REPO_ROOT / "dist"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
ENTRYPOINT = REPO_ROOT / "main.py"
LINUX_ARTIFACT_NAME = "hassistant-widget-linux.tar.gz"
WINDOWS_ARTIFACT_NAME = "hassistant-widget-windows.zip"
DOCKER_WINDOWS_IMAGE = "ghcr.io/cdrx/pyinstaller-windows:python3"


class ReleaseError(RuntimeError):
    """Custom exception raised for release related failures."""


@dataclass
class ReleaseTarget:
    """Description of a release artifact that should be uploaded."""

    name: str
    path: Path
    content_type: str


@dataclass
class ReleaseConfig:
    repo: str
    token: str
    version: str
    skip_linux: bool
    skip_windows: bool
    dist_dir: Path = DEFAULT_DIST_DIR


def debug(message: str) -> None:
    """Print a debug message to stderr so logs are easy to follow."""

    print(f"[release] {message}", file=sys.stderr)


def run(command: List[str], *, cwd: Optional[Path] = None, env: Optional[dict] = None) -> None:
    """Run a subprocess command with error handling and logging."""

    display_cwd = str(cwd or REPO_ROOT)
    debug(f"Running command in {display_cwd}: {' '.join(command)}")
    try:
        subprocess.run(command, cwd=cwd or REPO_ROOT, env=env, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - direct error propagation
        raise ReleaseError(f"Command {' '.join(command)} failed with exit code {exc.returncode}") from exc


def load_project_version() -> str:
    """Return the version defined in ``pyproject.toml``."""

    if not PYPROJECT_PATH.exists():
        raise ReleaseError("pyproject.toml not found; cannot determine project version")

    with PYPROJECT_PATH.open("rb") as handle:
        data = tomllib.load(handle)

    try:
        version = data["project"]["version"]
    except KeyError as exc:  # pragma: no cover - configuration error path
        raise ReleaseError("'project.version' missing from pyproject.toml") from exc

    return str(version)


def ensure_pyinstaller() -> None:
    """Ensure that PyInstaller is available in the current environment."""

    if shutil.which("pyinstaller"):
        debug("PyInstaller is already installed")
        return

    debug("Installing PyInstaller via pip")
    run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_linux_binary(dist_dir: Path) -> Path:
    """Build the Linux executable using PyInstaller."""

    ensure_pyinstaller()
    build_dir = dist_dir / "linux"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--name",
            "hassistant-widget",
            "--distpath",
            str(build_dir),
            str(ENTRYPOINT),
        ]
    )

    binary_path = build_dir / "hassistant-widget" / "hassistant-widget"
    if not binary_path.exists():  # pragma: no cover - unexpected builder change
        raise ReleaseError("Expected Linux binary not found after PyInstaller build")

    archive_path = dist_dir / LINUX_ARTIFACT_NAME
    debug(f"Packaging Linux binary into {archive_path}")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(binary_path, arcname="hassistant-widget")

    return archive_path


def build_windows_binary(dist_dir: Path) -> Path:
    """Build the Windows executable using a Dockerized PyInstaller environment."""

    if shutil.which("pyinstaller") and os.name == "nt":  # pragma: no cover - Windows specific path
        debug("Building Windows binary using local PyInstaller")
        build_dir = dist_dir / "windows"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True)
        run(
            [
                "pyinstaller",
                "--clean",
                "--noconfirm",
                "--name",
                "hassistant-widget",
                "--distpath",
                str(build_dir),
                str(ENTRYPOINT),
            ]
        )
        exe_path = build_dir / "hassistant-widget" / "hassistant-widget.exe"
    else:
        debug("Building Windows binary via Docker cross-compilation")
        if not shutil.which("docker"):
            raise ReleaseError("Docker is required for Windows builds on non-Windows platforms")

        build_dir = dist_dir / "windows"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True)

        env = os.environ.copy()
        env.setdefault("PYINSTALLER_STRIP", "false")
        docker_command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{REPO_ROOT}:/src",
            "-v",
            f"{build_dir}:/dist",
            DOCKER_WINDOWS_IMAGE,
            "pyinstaller",
            "--clean",
            "--noconfirm",
            "--name",
            "hassistant-widget",
            "--distpath",
            "/dist",
            "main.py",
        ]
        run(docker_command, env=env)
        exe_path = build_dir / "hassistant-widget.exe"
        if not exe_path.exists():
            # PyInstaller inside the container names the directory differently.
            candidate = build_dir / "hassistant-widget" / "hassistant-widget.exe"
            if candidate.exists():
                exe_path = candidate
            else:  # pragma: no cover - unexpected builder change
                raise ReleaseError("Windows executable not found after Docker build")

    archive_path = dist_dir / WINDOWS_ARTIFACT_NAME
    debug(f"Packaging Windows binary into {archive_path}")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(exe_path, arcname="hassistant-widget.exe")

    return archive_path


def parse_repo_slug(repo: Optional[str]) -> str:
    """Return the GitHub ``owner/repo`` slug, inferring it from git config when possible."""

    if repo:
        return repo

    try:
        completed = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - git misconfiguration
        raise ReleaseError("Unable to determine repository slug; please pass --repo") from exc

    url = completed.stdout.strip()
    if url.endswith(".git"):
        url = url[:-4]

    if url.startswith("git@"):
        _, path = url.split(":", 1)
    elif url.startswith("https://"):
        path = url.split("github.com/", 1)[1]
    else:  # pragma: no cover - unsupported remote configuration
        raise ReleaseError(f"Unsupported remote URL: {url}")

    return path


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "widget-hassistant-release-script",
    }


def list_existing_versions(repo: str, token: str) -> List[str]:
    releases_url = f"https://api.github.com/repos/{repo}/releases"
    headers = github_headers(token)
    versions: List[str] = []
    debug(f"Fetching existing releases from {releases_url}")
    response = requests.get(releases_url, headers=headers, timeout=30)
    response.raise_for_status()
    for release in response.json():
        tag = release.get("tag_name", "")
        if tag.startswith("v"):
            tag = tag[1:]
        versions.append(tag)
    return versions


def suggest_version(base_version: str, existing_versions: Iterable[str]) -> str:
    """Return a release version that does not conflict with existing tags."""

    def parse(version: str) -> List[int]:
        parts = version.split(".")
        return [int(part) for part in parts]

    if base_version not in existing_versions:
        return base_version

    major, minor, patch = parse(base_version)
    candidate = patch
    existing = {v for v in existing_versions if v.startswith(f"{major}.{minor}.")}
    while True:
        candidate += 1
        new_version = f"{major}.{minor}.{candidate}"
        if new_version not in existing:
            return new_version


def create_github_release(repo: str, token: str, version: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases"
    payload = {
        "tag_name": f"v{version}",
        "name": f"v{version}",
        "body": "Automated release created by scripts/create_release.py",
        "draft": False,
        "prerelease": False,
    }
    debug(f"Creating GitHub release v{version}")
    response = requests.post(url, headers=github_headers(token), json=payload, timeout=30)
    if response.status_code == 422 and "already_exists" in response.text:
        raise ReleaseError(f"Release v{version} already exists on GitHub")
    response.raise_for_status()
    return response.json()


def upload_asset(upload_url: str, token: str, target: ReleaseTarget) -> None:
    url = upload_url.split("{", 1)[0] + f"?name={target.name}"
    debug(f"Uploading asset {target.name}")
    with target.path.open("rb") as handle:
        response = requests.post(
            url,
            headers={
                **github_headers(token),
                "Content-Type": target.content_type,
            },
            data=handle,
            timeout=60,
        )
    response.raise_for_status()


def build_artifacts(config: ReleaseConfig) -> List[ReleaseTarget]:
    config.dist_dir.mkdir(parents=True, exist_ok=True)
    artifacts: List[ReleaseTarget] = []

    if not config.skip_linux:
        linux_path = build_linux_binary(config.dist_dir)
        artifacts.append(
            ReleaseTarget(
                name=LINUX_ARTIFACT_NAME,
                path=linux_path,
                content_type="application/gzip",
            )
        )

    if not config.skip_windows:
        windows_path = build_windows_binary(config.dist_dir)
        artifacts.append(
            ReleaseTarget(
                name=WINDOWS_ARTIFACT_NAME,
                path=windows_path,
                content_type="application/zip",
            )
        )

    return artifacts


def parse_args(argv: Optional[List[str]] = None) -> ReleaseConfig:
    parser = argparse.ArgumentParser(description="Build and publish GitHub releases")
    parser.add_argument("--repo", help="GitHub repository in owner/repo format")
    parser.add_argument(
        "--token",
        help="GitHub API token; defaults to the GITHUB_TOKEN environment variable",
    )
    parser.add_argument(
        "--version",
        help="Override the version number (defaults to project version with suggestions)",
    )
    parser.add_argument(
        "--skip-linux",
        action="store_true",
        help="Skip building the Linux artifact",
    )
    parser.add_argument(
        "--skip-windows",
        action="store_true",
        help="Skip building the Windows artifact",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=DEFAULT_DIST_DIR,
        help="Output directory for build artifacts",
    )

    args = parser.parse_args(argv)

    repo = parse_repo_slug(args.repo)
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ReleaseError("A GitHub token must be provided via --token or GITHUB_TOKEN")

    base_version = args.version or load_project_version()
    existing_versions = list_existing_versions(repo, token)
    version = suggest_version(base_version, existing_versions)
    if version != base_version:
        debug(f"Suggested version {version} (base {base_version} already exists)")
    else:
        debug(f"Using project version {version}")

    return ReleaseConfig(
        repo=repo,
        token=token,
        version=version,
        skip_linux=args.skip_linux,
        skip_windows=args.skip_windows,
        dist_dir=args.dist_dir,
    )


def main(argv: Optional[List[str]] = None) -> int:
    try:
        config = parse_args(argv)
        artifacts = build_artifacts(config)
        release = create_github_release(config.repo, config.token, config.version)
        upload_url = release["upload_url"]
        for artifact in artifacts:
            upload_asset(upload_url, config.token, artifact)
        debug("Release creation completed successfully")
        return 0
    except ReleaseError as exc:
        debug(str(exc))
        return 1
    except requests.HTTPError as exc:  # pragma: no cover - network issues
        debug(f"GitHub API request failed: {exc}")
        if exc.response is not None:
            try:
                debug(json.dumps(exc.response.json(), indent=2))
            except Exception:  # pragma: no cover - fallback when response isn't JSON
                debug(exc.response.text)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
