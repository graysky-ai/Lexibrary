"""Tests for the new curator-4 config scalars.

Covers the three new config entries added by Group 1:

- ``ConceptConfig.orphan_verify_ttl_days`` (``int``, default 90, ``ge=0``)
- ``ValidatorConfig.fix_lookup_token_budget_condense`` (``bool``, default False)
- ``ValidatorConfig.fix_orphaned_iwh_signals_delete`` (``bool``, default True)

Round-trips exercise defaults, custom YAML overrides, and partial-section
merges to confirm the two-tier loader preserves unspecified defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.config.loader import load_config
from lexibrary.config.schema import (
    ConceptConfig,
    LexibraryConfig,
    ValidatorConfig,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_concept_orphan_verify_ttl_days_default() -> None:
    """``ConceptConfig.orphan_verify_ttl_days`` defaults to 90."""
    cfg = ConceptConfig()
    assert cfg.orphan_verify_ttl_days == 90


def test_validator_config_defaults() -> None:
    """``ValidatorConfig`` kill-switch defaults match the spec."""
    cfg = ValidatorConfig()
    assert cfg.fix_lookup_token_budget_condense is False
    assert cfg.fix_orphaned_iwh_signals_delete is True


def test_lexibrary_config_exposes_validator_subsection() -> None:
    """``LexibraryConfig`` wires ``validator`` as a sub-model with defaults."""
    cfg = LexibraryConfig()
    assert isinstance(cfg.validator, ValidatorConfig)
    assert cfg.validator.fix_lookup_token_budget_condense is False
    assert cfg.validator.fix_orphaned_iwh_signals_delete is True


def test_lexibrary_config_concepts_ttl_default() -> None:
    """``LexibraryConfig.concepts.orphan_verify_ttl_days`` defaults to 90."""
    cfg = LexibraryConfig()
    assert cfg.concepts.orphan_verify_ttl_days == 90


# ---------------------------------------------------------------------------
# ge=0 enforcement
# ---------------------------------------------------------------------------


def test_orphan_verify_ttl_days_zero_accepted() -> None:
    """TTL=0 is accepted and disables TTL honouring downstream."""
    cfg = ConceptConfig(orphan_verify_ttl_days=0)
    assert cfg.orphan_verify_ttl_days == 0


def test_orphan_verify_ttl_days_negative_rejected() -> None:
    """Negative ``orphan_verify_ttl_days`` is rejected."""
    with pytest.raises(ValidationError):
        ConceptConfig(orphan_verify_ttl_days=-1)


# ---------------------------------------------------------------------------
# YAML round-trip via load_config
# ---------------------------------------------------------------------------


def test_load_config_custom_orphan_verify_ttl_days(tmp_path: Path) -> None:
    """Project YAML override is honoured for ``concepts.orphan_verify_ttl_days``."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "concepts:\n  orphan_verify_ttl_days: 30\n"
    )

    cfg = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert cfg.concepts.orphan_verify_ttl_days == 30


def test_load_config_custom_validator_kill_switches(tmp_path: Path) -> None:
    """Project YAML override is honoured for both validator kill-switches."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "validator:\n"
        "  fix_lookup_token_budget_condense: true\n"
        "  fix_orphaned_iwh_signals_delete: false\n"
    )

    cfg = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert cfg.validator.fix_lookup_token_budget_condense is True
    assert cfg.validator.fix_orphaned_iwh_signals_delete is False


def test_load_config_partial_validator_section_merges_defaults(tmp_path: Path) -> None:
    """Declaring only one ``validator`` key leaves the other at its default."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "validator:\n  fix_lookup_token_budget_condense: true\n"
    )

    cfg = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert cfg.validator.fix_lookup_token_budget_condense is True
    # The other key retains its default.
    assert cfg.validator.fix_orphaned_iwh_signals_delete is True


def test_load_config_partial_concepts_section_merges_defaults(tmp_path: Path) -> None:
    """Declaring ``concepts.orphan_verify_ttl_days`` only preserves other ``concepts`` defaults."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "concepts:\n  orphan_verify_ttl_days: 45\n"
    )

    cfg = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert cfg.concepts.orphan_verify_ttl_days == 45
    # Other ``concepts`` defaults unchanged.
    assert cfg.concepts.lookup_display_limit == 10
    assert cfg.concepts.deprecation_confirm == "human"


def test_load_config_orphan_verify_ttl_days_zero_via_yaml(tmp_path: Path) -> None:
    """``orphan_verify_ttl_days: 0`` is accepted end-to-end via YAML."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("concepts:\n  orphan_verify_ttl_days: 0\n")

    cfg = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert cfg.concepts.orphan_verify_ttl_days == 0


def test_load_config_defaults_when_no_yaml(tmp_path: Path) -> None:
    """Default load (no YAML files) produces the documented defaults end-to-end."""
    cfg = load_config(
        project_root=tmp_path,
        global_config_path=tmp_path / "nonexistent_global.yaml",
    )
    assert cfg.concepts.orphan_verify_ttl_days == 90
    assert cfg.validator.fix_lookup_token_budget_condense is False
    assert cfg.validator.fix_orphaned_iwh_signals_delete is True
