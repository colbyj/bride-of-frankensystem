"""PyPI update notification for the BOFS framework.

Resolves which PyPI distribution is installed (``bride-of-frankensystem``
vs ``bride-of-frankensystem-dev``), queries PyPI for the latest version,
and compares versions.  All network failures are silent — the caller
sees ``None`` when the check cannot be completed.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple


UPDATE_CHECK_INTERVAL = 24 * 60 * 60  # 24 hours, in seconds


@dataclass
class UpdateInfo:
    """Result of an update check.

    Attributes:
        available: ``True`` when a newer version exists on PyPI.
        current:   The installed version string.
        latest:    The latest version string on PyPI.
        dist_name: The resolved PyPI distribution name.
    """

    available: bool
    current: str
    latest: str
    dist_name: str


def _dist_name_version(dist) -> Optional[Tuple[str, str]]:
    """Extract ``(Name, Version)`` from a Distribution's metadata.

    ``Distribution.name`` / ``.version`` are convenience properties added
    in Python 3.10; reading the raw metadata works on 3.9 (the project's
    minimum) and newer.  Returns ``None`` when metadata is missing or
    lacks a name/version.
    """
    try:
        md = dist.metadata
    except Exception:
        return None
    if md is None:
        return None
    name = md.get("Name")
    version = md.get("Version")
    if not name or not version:
        return None
    return (name, version)


def get_install_info() -> Optional[Tuple[str, str]]:
    """Resolve the installed BOFS distribution name and version.

    Iterates ``importlib.metadata.distributions()`` and finds the
    distribution that owns the ``BOFS`` top-level package by consulting
    ``top_level.txt``.  Falls back to matching by distribution name
    (``bride-of-frankensystem`` / ``bride-of-frankensystem-dev``).

    Returns ``(dist_name, version)`` or ``None`` when no owning
    distribution is found.
    """
    try:
        from importlib.metadata import distributions
    except ImportError:
        return None

    for dist in distributions():
        try:
            top_level = dist.read_text("top_level.txt")
        except Exception:
            continue
        if top_level is None:
            continue
        names = [n.strip() for n in top_level.splitlines() if n.strip()]
        if "BOFS" in names:
            info = _dist_name_version(dist)
            if info is not None:
                return info

    # Fallback: match by known distribution name.
    for dist in distributions():
        info = _dist_name_version(dist)
        if info is None:
            continue
        if info[0] in ("bride-of-frankensystem", "bride-of-frankensystem-dev"):
            return info

    return None


def fetch_latest_version(dist_name: str, timeout: int = 3) -> Optional[str]:
    """Query PyPI for the latest version of *dist_name*.

    Uses ``urllib.request`` with *timeout* seconds.  Returns the version
    string on success, or ``None`` on any failure (network, timeout,
    non-200, malformed JSON, DNS failure).
    """
    url = f"https://pypi.org/pypi/{dist_name}/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        return None


def _parse_version(version: str) -> tuple:
    """Parse a version string into a comparable tuple of ints.

    Handles 4-part numeric versions like ``2.0.0.60``.  Non-numeric
    segments are treated as ``0`` so the comparison does not crash.
    """
    parts = []
    for segment in version.split("."):
        try:
            parts.append(int(segment))
        except (ValueError, TypeError):
            parts.append(0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """Return ``True`` if *latest* is strictly newer than *current*.

    Versions are compared as tuples of ints after splitting on ``.``.
    Shorter tuples are zero-padded so ``(2, 0, 0, 0)`` compares
    correctly against ``(2, 0, 0)``.  Non-numeric segments are mapped
    to zero.
    """
    latest_parts = _parse_version(latest)
    current_parts = _parse_version(current)
    max_len = max(len(latest_parts), len(current_parts))
    # Pad to the same length so (2,0,0,0) > (2,0,0) evaluates correctly.
    latest_parts = latest_parts + (0,) * (max_len - len(latest_parts))
    current_parts = current_parts + (0,) * (max_len - len(current_parts))
    return latest_parts > current_parts


def check_for_update() -> Optional[UpdateInfo]:
    """Top-level entry point.  Returns an ``UpdateInfo`` or ``None``.

    Returns ``None`` when the installed distribution cannot be resolved
    or when the network check fails (offline, timeout, PyPI unreachable).
    Returns an ``UpdateInfo`` with ``available=True`` when a newer
    version exists on PyPI.
    """
    install_info = get_install_info()
    if install_info is None:
        return None

    dist_name, current_version = install_info
    latest_version = fetch_latest_version(dist_name)
    if latest_version is None:
        return None

    available = is_newer(latest_version, current_version)
    return UpdateInfo(
        available=available,
        current=current_version,
        latest=latest_version,
        dist_name=dist_name,
    )
