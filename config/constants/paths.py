"""Filesystem roots for NinjaSRE state.

Resolution order for every root:

1. ``NINJASRE_HOME_DIR``, when set, wins outright. One directory holds
   everything, which is what a container image and an air-gapped install want.
2. Otherwise the platform convention: XDG base directories on Linux and macOS,
   ``%APPDATA%`` and ``%LOCALAPPDATA%`` on Windows.

Nothing here creates a directory. Resolution is a pure function of the
environment so it stays safe to call during import; the owning module creates
what it needs, when it needs it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

NINJASRE_HOME_DIR_ENV: Final = "NINJASRE_HOME_DIR"

XDG_CONFIG_HOME_ENV: Final = "XDG_CONFIG_HOME"
XDG_CACHE_HOME_ENV: Final = "XDG_CACHE_HOME"
XDG_DATA_HOME_ENV: Final = "XDG_DATA_HOME"
XDG_STATE_HOME_ENV: Final = "XDG_STATE_HOME"

WINDOWS_ROAMING_APP_DATA_ENV: Final = "APPDATA"
WINDOWS_LOCAL_APP_DATA_ENV: Final = "LOCALAPPDATA"

#: Directory name used under a shared root such as ``~/.config``.
APPLICATION_DIR_NAME: Final = "ninjasre"

#: Directory name used when falling back to a dotted directory in ``$HOME``.
DOTTED_HOME_DIR_NAME: Final = ".ninjasre"

CONFIG_SUBDIR_NAME: Final = "config"
CACHE_SUBDIR_NAME: Final = "cache"
DATA_SUBDIR_NAME: Final = "data"
STATE_SUBDIR_NAME: Final = "state"

#: The repository root, resolved from this file's location. Useful to tooling
#: and tests; runtime code should prefer the resolved roots below.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

_IS_WINDOWS: Final = sys.platform == "win32"


def _environment_path(name: str) -> Path | None:
    """Return the path in environment variable ``name``, if it holds one."""
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return None
    return Path(raw).expanduser()


def home_dir() -> Path:
    """Return the single root that overrides every other location, if set."""
    explicit = _environment_path(NINJASRE_HOME_DIR_ENV)
    if explicit is not None:
        return explicit
    return Path.home() / DOTTED_HOME_DIR_NAME


def _resolve(
    subdir: str,
    xdg_env: str,
    posix_default: str,
    windows_env: str,
) -> Path:
    """Resolve one root, honouring the explicit home first."""
    explicit = _environment_path(NINJASRE_HOME_DIR_ENV)
    if explicit is not None:
        return explicit / subdir

    if _IS_WINDOWS:
        base = _environment_path(windows_env) or Path.home() / DOTTED_HOME_DIR_NAME
        return base / APPLICATION_DIR_NAME / subdir

    base = _environment_path(xdg_env) or Path.home() / posix_default
    return base / APPLICATION_DIR_NAME


def config_dir() -> Path:
    """Return the directory holding operator-edited configuration."""
    return _resolve(
        CONFIG_SUBDIR_NAME,
        XDG_CONFIG_HOME_ENV,
        ".config",
        WINDOWS_ROAMING_APP_DATA_ENV,
    )


def cache_dir() -> Path:
    """Return the directory holding regenerable data."""
    return _resolve(
        CACHE_SUBDIR_NAME,
        XDG_CACHE_HOME_ENV,
        ".cache",
        WINDOWS_LOCAL_APP_DATA_ENV,
    )


def data_dir() -> Path:
    """Return the directory holding data that must survive a cache wipe."""
    return _resolve(
        DATA_SUBDIR_NAME,
        XDG_DATA_HOME_ENV,
        ".local/share",
        WINDOWS_LOCAL_APP_DATA_ENV,
    )


def state_dir() -> Path:
    """Return the directory holding logs, pids, and other run state."""
    return _resolve(
        STATE_SUBDIR_NAME,
        XDG_STATE_HOME_ENV,
        ".local/state",
        WINDOWS_LOCAL_APP_DATA_ENV,
    )


__all__ = [
    "APPLICATION_DIR_NAME",
    "CACHE_SUBDIR_NAME",
    "CONFIG_SUBDIR_NAME",
    "DATA_SUBDIR_NAME",
    "DOTTED_HOME_DIR_NAME",
    "NINJASRE_HOME_DIR_ENV",
    "REPO_ROOT",
    "STATE_SUBDIR_NAME",
    "WINDOWS_LOCAL_APP_DATA_ENV",
    "WINDOWS_ROAMING_APP_DATA_ENV",
    "XDG_CACHE_HOME_ENV",
    "XDG_CONFIG_HOME_ENV",
    "XDG_DATA_HOME_ENV",
    "XDG_STATE_HOME_ENV",
    "cache_dir",
    "config_dir",
    "data_dir",
    "home_dir",
    "state_dir",
]
