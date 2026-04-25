"""Tests for the config writer used by the upgrade pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lexibrary.upgrade.config_writer import (
    legacy_keys_present,
    rewrite_config_yaml,
    set_config_value,
)


def _write_config(tmp_path: Path, body: str) -> Path:
    cfg_dir = tmp_path / ".lexibrary"
    cfg_dir.mkdir(exist_ok=True)
    cfg_path = cfg_dir / "config.yaml"
    cfg_path.write_text(body, encoding="utf-8")
    return cfg_path


def test_legacy_keys_present_detects_scope_root(tmp_path: Path) -> None:
    """``scope_root`` at the top level is reported as a legacy key."""
    cfg = _write_config(tmp_path, "scope_root: .\nproject_name: foo\n")
    assert legacy_keys_present(cfg) == {"scope_root"}


def test_legacy_keys_present_detects_daemon(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "daemon:\n  sweep_interval_seconds: 1800\n")
    assert legacy_keys_present(cfg) == {"daemon"}


def test_legacy_keys_present_detects_both(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "scope_root: .\ndaemon:\n  sweep_interval_seconds: 1\n")
    assert legacy_keys_present(cfg) == {"scope_root", "daemon"}


def test_legacy_keys_present_returns_empty_when_clean(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "scope_roots:\n  - path: .\nproject_name: foo\n")
    assert legacy_keys_present(cfg) == set()


def test_legacy_keys_present_returns_empty_when_missing(tmp_path: Path) -> None:
    assert legacy_keys_present(tmp_path / "nope.yaml") == set()


def test_rewrite_config_yaml_migrates_scope_root(tmp_path: Path) -> None:
    """``scope_root: .`` → ``scope_roots: [{path: .}]`` and a backup is left."""
    cfg = _write_config(tmp_path, "scope_root: .\nproject_name: foo\n")
    written = rewrite_config_yaml(cfg)

    assert written == {"scope_roots": [{"path": "."}], "project_name": "foo"}

    after = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert after["scope_roots"] == [{"path": "."}]
    assert "scope_root" not in after

    backup = cfg.with_suffix(cfg.suffix + ".bak")
    assert backup.exists()
    assert "scope_root: ." in backup.read_text(encoding="utf-8")


def test_rewrite_config_yaml_migrates_daemon(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        "daemon:\n  sweep_interval_seconds: 1800\n  log_level: debug\n",
    )
    written = rewrite_config_yaml(cfg)

    assert written["sweep"] == {"sweep_interval_seconds": 1800, "log_level": "debug"}
    assert "daemon" not in written


def test_rewrite_config_yaml_keeps_canonical_header(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "scope_root: .\n")
    rewrite_config_yaml(cfg)

    text = cfg.read_text(encoding="utf-8")
    assert text.startswith("# Lexibrary project configuration")


def test_rewrite_config_yaml_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        rewrite_config_yaml(tmp_path / "nope.yaml")


def test_set_config_value_updates_existing_key(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        "scope_roots:\n  - path: .\nlexibrary_version: '0.5.0'\n",
    )
    written = set_config_value(cfg, "lexibrary_version", "0.6.3")
    assert written["lexibrary_version"] == "0.6.3"

    after = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert after["lexibrary_version"] == "0.6.3"


def test_set_config_value_inserts_new_key(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "scope_roots:\n  - path: .\nproject_name: foo\n")
    set_config_value(cfg, "lexibrary_version", "0.6.3")

    after = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert after["lexibrary_version"] == "0.6.3"
    assert after["project_name"] == "foo"  # untouched


def test_set_config_value_writes_backup(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "scope_roots:\n  - path: .\n")
    set_config_value(cfg, "lexibrary_version", "0.6.3")

    backup = cfg.with_suffix(cfg.suffix + ".bak")
    assert backup.exists()
    assert "lexibrary_version" not in backup.read_text(encoding="utf-8")
