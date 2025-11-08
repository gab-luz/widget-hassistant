#!/usr/bin/env bash
set -euo pipefail

# Build Linux and Windows binaries for the Home Assistant tray widget.
#
# The Linux build is produced locally with PyInstaller. Windows artifacts
# are produced by syncing the repository to a remote Windows host via SSH
# and running the accompanying PowerShell build script.
#
# Required environment variables / arguments:
#   --windows-host HOST or WINDOWS_SSH_HOST: SSH hostname for the Windows builder
# Optional parameters (flags override environment variables when provided):
#   --windows-user USER        (default: current user / WINDOWS_SSH_USER)
#   --windows-port PORT        (default: 22 / WINDOWS_SSH_PORT)
#   --windows-root PATH        (default: ~/hassistant-widget / WINDOWS_REMOTE_ROOT)
#   --windows-python COMMAND   (default: "py -3" / WINDOWS_PYTHON_COMMAND)
#   --windows-inno PATH        (default: "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"
#                               or WINDOWS_INNO_COMPILER)
#
# Usage:
#   scripts/build_artifacts.sh --windows-host 192.168.1.50
#
# The script produces the following artifacts in dist/:
#   dist/hassistant-widget-linux.tar.gz
#   dist/windows/hassistant-widget-portable.exe
#   dist/windows/hassistant-widget-setup.exe

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
LINUX_DIST="$DIST_DIR/linux"
WINDOWS_DIST="$DIST_DIR/windows"
LINUX_VENV="$PROJECT_ROOT/.venv-build-linux"

WINDOWS_HOST="${WINDOWS_SSH_HOST:-}"
WINDOWS_USER="${WINDOWS_SSH_USER:-$(whoami)}"
WINDOWS_PORT="${WINDOWS_SSH_PORT:-22}"
WINDOWS_ROOT="${WINDOWS_REMOTE_ROOT:-~/hassistant-widget}"
WINDOWS_PYTHON="${WINDOWS_PYTHON_COMMAND:-py -3}"
WINDOWS_INNO="${WINDOWS_INNO_COMPILER:-C:/Program Files (x86)/Inno Setup 6/ISCC.exe}"

usage() {
    cat <<'USAGE'
Usage: scripts/build_artifacts.sh --windows-host HOST [options]

Options:
  --windows-user USER        SSH user for Windows host
  --windows-port PORT        SSH port for Windows host (default 22)
  --windows-root PATH        Deployment path on Windows host (default ~/hassistant-widget)
  --windows-python CMD       Python command on Windows host (default "py -3")
  --windows-inno PATH        Path to Inno Setup compiler on Windows host
  -h, --help                 Show this help message
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --windows-host)
            WINDOWS_HOST="$2"
            shift 2
            ;;
        --windows-user)
            WINDOWS_USER="$2"
            shift 2
            ;;
        --windows-port)
            WINDOWS_PORT="$2"
            shift 2
            ;;
        --windows-root)
            WINDOWS_ROOT="$2"
            shift 2
            ;;
        --windows-python)
            WINDOWS_PYTHON="$2"
            shift 2
            ;;
        --windows-inno)
            WINDOWS_INNO="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$WINDOWS_HOST" ]]; then
    echo "Error: --windows-host or WINDOWS_SSH_HOST must be provided" >&2
    exit 1
fi

SSH_BASE=(ssh -p "$WINDOWS_PORT" "${WINDOWS_USER}@${WINDOWS_HOST}")
SCP_BASE=(scp -P "$WINDOWS_PORT")

cleanup() {
    if [[ -d "$LINUX_VENV" ]]; then
        rm -rf "$LINUX_VENV"
    fi
}
trap cleanup EXIT

run_linux_build() {
    echo "[build] Preparing Linux virtual environment"
    python3 -m venv "$LINUX_VENV"
    "$LINUX_VENV/bin/pip" install --upgrade pip >/dev/null
    "$LINUX_VENV/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" pyinstaller >/dev/null

    rm -rf "$LINUX_DIST"
    mkdir -p "$LINUX_DIST"

    echo "[build] Building Linux binary via PyInstaller"
    "$LINUX_VENV/bin/pyinstaller" \
        --clean \
        --noconfirm \
        --name hassistant-widget \
        --distpath "$LINUX_DIST" \
        "$PROJECT_ROOT/main.py" >/dev/null

    local binary_path="$LINUX_DIST/hassistant-widget/hassistant-widget"
    if [[ ! -f "$binary_path" ]]; then
        echo "Linux binary not found at $binary_path" >&2
        exit 1
    fi

    mkdir -p "$DIST_DIR"
    local archive="$DIST_DIR/hassistant-widget-linux.tar.gz"
    echo "[build] Packaging Linux binary to $archive"
    tar -czf "$archive" -C "$(dirname "$binary_path")" "$(basename "$binary_path")"
}

sync_source_to_windows() {
    echo "[build] Creating source archive for Windows build"
    local tmp_archive
    tmp_archive="$(mktemp -t hassistant-src-XXXXXX.tar.gz)"
    tar --exclude='.git' --exclude='dist' --exclude='__pycache__' -czf "$tmp_archive" -C "$PROJECT_ROOT" .

    local remote_stage="$WINDOWS_ROOT/.build"
    echo "[build] Uploading source archive to Windows host"
    "${SSH_BASE[@]}" powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path '$remote_stage' | Out-Null"
    "${SCP_BASE[@]}" "$tmp_archive" "${WINDOWS_USER}@${WINDOWS_HOST}:$remote_stage/source.tar.gz"

    echo "[build] Expanding source archive on Windows host"
    "${SSH_BASE[@]}" powershell -NoProfile -Command "if (Test-Path '$WINDOWS_ROOT') { Remove-Item -Recurse -Force '$WINDOWS_ROOT' }; New-Item -ItemType Directory -Force -Path '$WINDOWS_ROOT' | Out-Null; tar -xf '$remote_stage/source.tar.gz' -C '$WINDOWS_ROOT'"
    "${SSH_BASE[@]}" powershell -NoProfile -Command "Remove-Item -Force '$remote_stage/source.tar.gz'"
    rm -f "$tmp_archive"
}

run_windows_build() {
    echo "[build] Triggering Windows build via SSH"
    local command
    command="& { $project = Resolve-Path '$WINDOWS_ROOT'; Set-Location $project; .\scripts\windows_build.ps1 -PythonCommand '$WINDOWS_PYTHON' -DistRelative 'dist\\windows' -InnoSetupCompiler '$WINDOWS_INNO' }"
    "${SSH_BASE[@]}" powershell -NoProfile -ExecutionPolicy Bypass -Command "$command"
}

fetch_windows_artifacts() {
    mkdir -p "$WINDOWS_DIST"
    echo "[build] Downloading Windows portable executable"
    "${SCP_BASE[@]}" "${WINDOWS_USER}@${WINDOWS_HOST}:$WINDOWS_ROOT/dist/windows/portable/hassistant-widget.exe" "$WINDOWS_DIST/hassistant-widget-portable.exe"

    echo "[build] Downloading Windows installer executable"
    "${SCP_BASE[@]}" "${WINDOWS_USER}@${WINDOWS_HOST}:$WINDOWS_ROOT/dist/windows/hassistant-widget-setup.exe" "$WINDOWS_DIST/hassistant-widget-setup.exe"
}

run_linux_build
sync_source_to_windows
run_windows_build
fetch_windows_artifacts

echo "[build] Artifacts created in $DIST_DIR"
