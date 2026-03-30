"""Configuration file discovery and loading."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from lexibrary.config.schema import LexibraryConfig

logger = logging.getLogger(__name__)

# Fields that existed on the old DaemonConfig but were removed in the
# DaemonConfig -> SweepConfig rename.
_DAEMON_REMOVED_FIELDS = frozenset(
    {
        "debounce_seconds",
        "git_suppression_seconds",
        "watchdog_enabled",
    }
)

# XDG base directory default
_XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
GLOBAL_CONFIG_PATH = _XDG_CONFIG_HOME / "lexibrary" / "config.yaml"


def find_config_file(start_dir: Path | None = None) -> Path | None:
    """Search for .lexibrary/config.yaml starting from start_dir and walking upward.

    Args:
        start_dir: Directory to start search from. Defaults to current working directory.

    Returns:
        Path to config.yaml if found, None otherwise.
    """
    start_dir = Path.cwd() if start_dir is None else Path(start_dir).resolve()

    current = start_dir
    while True:
        config_path = current / ".lexibrary" / "config.yaml"
        if config_path.exists():
            return config_path

        # Stop at filesystem root
        if current.parent == current:
            break

        current = current.parent

    return None


def _migrate_daemon_to_sweep(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy ``daemon:`` config section to ``sweep:``.

    If ``data`` contains a ``daemon`` key but no ``sweep`` key, the daemon
    section is renamed to ``sweep`` and any fields that were removed during the
    rename (debounce_seconds, git_suppression_seconds, watchdog_enabled) are
    dropped.  A deprecation warning is logged to help users update their config
    files.

    If both ``daemon`` and ``sweep`` exist, ``sweep`` takes precedence and the
    ``daemon`` key is silently dropped.
    """
    if "daemon" not in data:
        return data

    if "sweep" not in data:
        daemon_section = dict(data["daemon"]) if isinstance(data["daemon"], dict) else {}
        # Drop fields that no longer exist on SweepConfig
        for field in _DAEMON_REMOVED_FIELDS:
            daemon_section.pop(field, None)
        data["sweep"] = daemon_section
        logger.warning(
            "Config key 'daemon:' is deprecated and will be removed in a future "
            "release. Rename it to 'sweep:' in your config file."
        )

    del data["daemon"]
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_config(
    project_root: Path | None = None,
    global_config_path: Path | None = None,
) -> LexibraryConfig:
    """Load and validate configuration with two-tier YAML merge.

    Merge strategy: load global config → load project config → shallow merge
    with project values taking precedence → validate with Pydantic.

    Args:
        project_root: Project root directory containing ``.lexibrary/config.yaml``.
            If None, no project config is loaded.
        global_config_path: Override for the global config path (useful for testing).
            Defaults to ``~/.config/lexibrary/config.yaml``.

    Returns:
        Validated LexibraryConfig instance.

    Raises:
        ValueError: If merged config contains invalid values. The message
            includes which config file(s) were loaded and which fields failed.
    """
    global_path = global_config_path if global_config_path is not None else GLOBAL_CONFIG_PATH
    project_path = project_root / ".lexibrary" / "config.yaml" if project_root else None

    # Load global config
    global_data: dict[str, Any] = {}
    if global_path.exists():
        global_data = _load_yaml(global_path)

    # Load project config
    project_data: dict[str, Any] = {}
    if project_path is not None and project_path.exists():
        project_data = _load_yaml(project_path)

    # Shallow merge: project top-level keys override global
    merged = {**global_data, **project_data}

    # Migrate legacy daemon: -> sweep:
    merged = _migrate_daemon_to_sweep(merged)

    # Validate and return
    try:
        return LexibraryConfig.model_validate(merged)
    except ValidationError as exc:
        # Build a list of source files so the user knows where to look.
        sources: list[str] = []
        if global_path.exists():
            sources.append(f"global ({global_path})")
        if project_path is not None and project_path.exists():
            sources.append(f"project ({project_path})")
        source_label = ", ".join(sources) if sources else "merged config"

        # Summarise each Pydantic error with field path and message.
        details = "; ".join(
            f"{' -> '.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )

        raise ValueError(f"Invalid configuration in {source_label}: {details}") from exc
