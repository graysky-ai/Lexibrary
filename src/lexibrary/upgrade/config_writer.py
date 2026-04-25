"""Targeted writes to ``.lexibrary/config.yaml``.

The upgrade pipeline occasionally needs to mutate the on-disk config
file: persisting legacy-key renames, stamping the Lexibrary version,
etc.  All such writes route through this module so the round-trip
strategy lives in one place.

Strategy:
    Load with :func:`yaml.safe_load`, mutate the dict, write back via
    :func:`yaml.dump` with ``sort_keys=False``.  PyYAML strips comments,
    so the previous file is saved alongside as ``config.yaml.bak`` for
    safety.  A canonical header is re-prepended so the rewritten file
    still explains what it is.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from lexibrary.config.loader import (
    _migrate_daemon_to_sweep,
    _migrate_scope_root_to_scope_roots,
)
from lexibrary.templates import read_template

_CONFIG_YAML_HEADER = read_template("scaffolder/config_yaml_header.txt")

_LEGACY_KEYS = ("scope_root", "daemon")


def legacy_keys_present(config_path: Path) -> set[str]:
    """Return the set of legacy top-level keys present in ``config_path``.

    Reads the file as YAML and reports which of the recognised legacy
    keys (``scope_root``, ``daemon``) appear at the top level.  Returns
    an empty set when the file is missing or contains none of them.
    """
    if not config_path.exists():
        return set()
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return set()
    return {key for key in _LEGACY_KEYS if key in data}


def _write_with_backup(config_path: Path, data: dict[str, Any]) -> None:
    """Back up ``config_path`` to ``<path>.bak`` then rewrite it from ``data``.

    The header comment from
    ``templates/scaffolder/config_yaml_header.txt`` is prepended so the
    rewritten file is self-describing.  The previous backup (if any) is
    overwritten — only the most recent pre-upgrade snapshot is kept.
    """
    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, backup_path)
    body = yaml.dump(data, sort_keys=False, default_flow_style=False)
    config_path.write_text(_CONFIG_YAML_HEADER + body, encoding="utf-8")


def rewrite_config_yaml(config_path: Path) -> dict[str, Any]:
    """Rewrite ``config_path`` with legacy keys migrated to current schema.

    Applies the same migrations the loader applies in memory (legacy
    ``daemon:`` and ``scope_root:`` keys) and writes the result back.
    A timestamped backup is left at ``config.yaml.bak``.

    Returns:
        The migrated dict that was written.  Useful for tests.

    Raises:
        FileNotFoundError: If ``config_path`` does not exist.
    """
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}

    raw = _migrate_daemon_to_sweep(raw)
    raw = _migrate_scope_root_to_scope_roots(raw)

    _write_with_backup(config_path, raw)
    return raw


def set_config_value(config_path: Path, key: str, value: Any) -> dict[str, Any]:
    """Set a single top-level key in ``config_path`` and rewrite the file.

    Used by the version-stamp step to record ``lexibrary_version:`` without
    perturbing the rest of the config.  A backup is written alongside.

    Returns:
        The dict that was written.

    Raises:
        FileNotFoundError: If ``config_path`` does not exist.
    """
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}
    raw[key] = value

    _write_with_backup(config_path, raw)
    return raw
