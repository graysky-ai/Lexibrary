"""Tests for two-tier config loading (v2: YAML, global + project merge)."""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.loader import load_config
from lexibrary.config.schema import LexibraryConfig


def test_load_config_defaults_only(tmp_path: Path) -> None:
    """load_config returns defaults when neither global nor project config exists."""
    config = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert isinstance(config, LexibraryConfig)
    assert config.llm.provider == "anthropic"
    assert config.daemon.debounce_seconds == 2.0


def test_load_config_global_only(tmp_path: Path) -> None:
    """load_config loads values from global config when no project config."""
    global_cfg = tmp_path / "global.yaml"
    global_cfg.write_text("llm:\n  provider: openai\n  model: gpt-4o\n")

    config = load_config(project_root=None, global_config_path=global_cfg)
    assert config.llm.provider == "openai"
    assert config.llm.model == "gpt-4o"
    # Other fields use defaults
    assert config.llm.max_retries == 3


def test_load_config_project_only(tmp_path: Path) -> None:
    """load_config loads values from project config when no global config."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("daemon:\n  debounce_seconds: 5.0\n")

    config = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert config.daemon.debounce_seconds == 5.0
    # Other fields use defaults
    assert config.llm.provider == "anthropic"


def test_load_config_project_overrides_global(tmp_path: Path) -> None:
    """Project config top-level keys override global config."""
    global_cfg = tmp_path / "global.yaml"
    global_cfg.write_text(
        "llm:\n  provider: openai\n  model: gpt-4o\ndaemon:\n  debounce_seconds: 5.0\n"
    )

    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "llm:\n  provider: anthropic\n  model: claude-opus-4-6\n"
    )

    config = load_config(project_root=tmp_path, global_config_path=global_cfg)
    # Project wins for llm (entire key replaced)
    assert config.llm.provider == "anthropic"
    assert config.llm.model == "claude-opus-4-6"
    # Global value kept for daemon (not overridden)
    assert config.daemon.debounce_seconds == 5.0


def test_load_config_partial_project(tmp_path: Path) -> None:
    """Partial project config only overrides declared keys."""
    global_cfg = tmp_path / "global.yaml"
    global_cfg.write_text("llm:\n  provider: openai\n")

    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "token_budgets:\n  start_here_tokens: 1200\n"
    )

    config = load_config(project_root=tmp_path, global_config_path=global_cfg)
    assert config.llm.provider == "openai"  # from global
    assert config.token_budgets.start_here_tokens == 1200  # from project


def test_load_config_extra_fields_ignored(tmp_path: Path) -> None:
    """Extra fields in YAML are silently ignored (extra='ignore')."""
    global_cfg = tmp_path / "global.yaml"
    global_cfg.write_text(
        "llm:\n  provider: anthropic\n  unknown_field: whatever\n"
        "completely_new_section:\n  foo: bar\n"
    )

    config = load_config(project_root=None, global_config_path=global_cfg)
    assert config.llm.provider == "anthropic"
    assert not hasattr(config.llm, "unknown_field")
