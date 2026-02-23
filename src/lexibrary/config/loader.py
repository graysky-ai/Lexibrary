"""Configuration file discovery and loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from lexibrary.config.schema import LexibraryConfig

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
        pydantic.ValidationError: If merged config contains invalid values.
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

    # Validate and return
    return LexibraryConfig.model_validate(merged)
