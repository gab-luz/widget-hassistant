"""Helpers for collecting local system metrics to expose as Home Assistant sensors."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping

import math
import shutil
import subprocess
import time


try:  # pragma: no cover - optional dependency
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil is optional
    psutil = None  # type: ignore


@dataclass(frozen=True)
class MetricOption:
    """Description of a metric that can be exposed to Home Assistant."""

    key: str
    label: str
    description: str


@dataclass
class MetricValue:
    """Value collected for a metric."""

    state: str
    attributes: Dict[str, object]


AGENT_METRIC_OPTIONS: tuple[MetricOption, ...] = (
    MetricOption(
        key="disk_free_gb",
        label="Available disk space (GB)",
        description="Reports the remaining free space on the system volume in gigabytes.",
    ),
    MetricOption(
        key="memory_used_percent",
        label="Memory usage (%)",
        description="Percentage of physical memory currently in use on this machine.",
    ),
    MetricOption(
        key="gpu_usage_percent",
        label="GPU load (%)",
        description="Approximate GPU utilization gathered from available system tools.",
    ),
    MetricOption(
        key="uptime_seconds",
        label="System uptime (seconds)",
        description="Seconds elapsed since the operating system booted.",
    ),
)


_OPTION_MAP: Mapping[str, MetricOption] = {option.key: option for option in AGENT_METRIC_OPTIONS}


def get_metric_option(key: str) -> MetricOption | None:
    """Return the configured metric option for the given key, if it exists."""

    return _OPTION_MAP.get(key)


def collect_metrics(selected: Iterable[str]) -> Dict[str, MetricValue]:
    """Collect the requested metrics and return their values."""

    collected: Dict[str, MetricValue] = {}
    for key in selected:
        if key == "disk_free_gb":
            value = _collect_disk_free()
        elif key == "memory_used_percent":
            value = _collect_memory_percent()
        elif key == "gpu_usage_percent":
            value = _collect_gpu_usage()
        elif key == "uptime_seconds":
            value = _collect_uptime()
        else:
            continue

        if value is not None:
            collected[key] = value
    return collected


def slugify_agent_name(name: str) -> str:
    """Return a slug version of the provided agent name suitable for entity IDs."""

    import re

    name = name.strip().lower()
    if not name:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "_", name)
    slug = slug.strip("_")
    return slug or "agent"


def _collect_disk_free() -> MetricValue | None:
    path = Path.home()
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        try:
            usage = shutil.disk_usage("/")
        except OSError:
            return None

    free_gb = usage.free / (1024 ** 3)
    free_gb = round(free_gb, 2)
    attributes = {
        "unit_of_measurement": "GB",
        "icon": "mdi:harddisk",
    }
    return MetricValue(state=f"{free_gb}", attributes=attributes)


def _collect_memory_percent() -> MetricValue | None:
    percent: float | None = None
    total_bytes: float | None = None
    available_bytes: float | None = None

    if psutil is not None:
        try:
            memory = psutil.virtual_memory()  # type: ignore[call-arg]
        except Exception:
            memory = None
        if memory is not None:
            percent = float(memory.percent)
            total_bytes = float(memory.total)
            available_bytes = float(memory.available)

    if percent is None:
        try:
            page_size = float(_sysconf("SC_PAGE_SIZE"))
            phys_pages = float(_sysconf("SC_PHYS_PAGES"))
            avail_pages = float(_sysconf("SC_AVPHYS_PAGES"))
        except (ValueError, OSError):
            page_size = phys_pages = avail_pages = math.nan

        if not math.isnan(page_size) and not math.isnan(phys_pages) and not math.isnan(avail_pages):
            total_bytes = page_size * phys_pages
            available_bytes = page_size * avail_pages
            if total_bytes > 0:
                percent = ((total_bytes - available_bytes) / total_bytes) * 100.0

    if percent is None:
        return None

    percent = round(percent, 2)
    attributes = {
        "unit_of_measurement": "%",
        "icon": "mdi:memory",
    }
    if total_bytes is not None:
        attributes["total_gb"] = round(total_bytes / (1024 ** 3), 2)
    if available_bytes is not None:
        attributes["available_gb"] = round(available_bytes / (1024 ** 3), 2)

    return MetricValue(state=f"{percent}", attributes=attributes)


def _collect_gpu_usage() -> MetricValue | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # GPU metrics are optional. Report as unavailable so the entity exists.
        attributes = {
            "unit_of_measurement": "%",
            "icon": "mdi:gpu",
        }
        return MetricValue(state="unavailable", attributes=attributes)

    output = result.stdout.strip()
    if not output:
        return MetricValue(state="unavailable", attributes={"icon": "mdi:gpu"})

    try:
        value = float(output.splitlines()[0].strip())
    except (ValueError, IndexError):
        return MetricValue(state="unavailable", attributes={"icon": "mdi:gpu"})

    value = round(value, 2)
    attributes = {
        "unit_of_measurement": "%",
        "icon": "mdi:gpu",
    }
    return MetricValue(state=f"{value}", attributes=attributes)


def _collect_uptime() -> MetricValue | None:
    boot_time: float | None = None
    if psutil is not None and hasattr(psutil, "boot_time"):
        try:
            boot_time = float(psutil.boot_time())  # type: ignore[call-arg]
        except Exception:
            boot_time = None

    if boot_time is None:
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as fp:
                first_value = fp.read().split()[0]
                uptime_seconds = float(first_value)
            return MetricValue(
                state=f"{int(uptime_seconds)}",
                attributes={
                    "unit_of_measurement": "s",
                    "device_class": "duration",
                    "icon": "mdi:timer-outline",
                },
            )
        except (FileNotFoundError, IndexError, ValueError, OSError):
            boot_time = None

    if boot_time is None:
        return None

    uptime_seconds = max(0, int(time.time() - boot_time))
    attributes = {
        "unit_of_measurement": "s",
        "device_class": "duration",
        "icon": "mdi:timer-outline",
    }
    return MetricValue(state=f"{uptime_seconds}", attributes=attributes)


def _sysconf(name: str) -> int:
    import os

    value = os.sysconf(name)  # type: ignore[attr-defined]
    if value == -1:
        raise ValueError(name)
    return int(value)


__all__ = [
    "AGENT_METRIC_OPTIONS",
    "MetricOption",
    "MetricValue",
    "collect_metrics",
    "get_metric_option",
    "slugify_agent_name",
]

