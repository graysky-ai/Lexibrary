"""Tests for CuratorConfig model and LexibraryConfig integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.config.loader import load_config
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.config import CuratorConfig

# --- CuratorConfig model tests ---


class TestCuratorConfigDefaults:
    """Default values match spec."""

    def test_default_autonomy(self) -> None:
        config = CuratorConfig()
        assert config.autonomy == "auto_low"

    def test_default_max_llm_calls(self) -> None:
        config = CuratorConfig()
        assert config.max_llm_calls_per_run == 50

    def test_default_risk_overrides_empty(self) -> None:
        config = CuratorConfig()
        assert config.risk_overrides == {}


class TestCuratorConfigAutonomy:
    """Autonomy level validation."""

    @pytest.mark.parametrize("level", ["auto_low", "full", "propose"])
    def test_valid_autonomy_accepted(self, level: str) -> None:
        config = CuratorConfig(autonomy=level)
        assert config.autonomy == level

    def test_invalid_autonomy_rejected(self) -> None:
        with pytest.raises(ValidationError, match="autonomy"):
            CuratorConfig(autonomy="yolo")  # type: ignore[arg-type]


class TestCuratorConfigMaxLLMCalls:
    """max_llm_calls_per_run validation."""

    def test_positive_value_accepted(self) -> None:
        config = CuratorConfig(max_llm_calls_per_run=1)
        assert config.max_llm_calls_per_run == 1

    def test_large_value_accepted(self) -> None:
        config = CuratorConfig(max_llm_calls_per_run=1000)
        assert config.max_llm_calls_per_run == 1000

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_llm_calls_per_run"):
            CuratorConfig(max_llm_calls_per_run=0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_llm_calls_per_run"):
            CuratorConfig(max_llm_calls_per_run=-5)


class TestCuratorConfigRiskOverrides:
    """Risk override validation."""

    def test_valid_override_accepted(self) -> None:
        config = CuratorConfig(risk_overrides={"deprecate_convention": "high"})
        assert config.risk_overrides == {"deprecate_convention": "high"}

    def test_multiple_overrides_accepted(self) -> None:
        overrides = {
            "regen_stale_design": "low",
            "remove_orphan_concept": "medium",
            "reconcile_agent_edit": "high",
        }
        config = CuratorConfig(risk_overrides=overrides)
        assert config.risk_overrides == overrides

    def test_invalid_risk_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CuratorConfig(risk_overrides={"some_action": "extreme"})  # type: ignore[dict-item]


class TestCuratorConfigExtraIgnored:
    """Unknown keys are silently ignored (backwards compat)."""

    def test_extra_fields_ignored(self) -> None:
        config = CuratorConfig.model_validate(
            {"autonomy": "full", "unknown_future_field": True}
        )
        assert config.autonomy == "full"
        assert not hasattr(config, "unknown_future_field")


# --- LexibraryConfig integration tests ---


class TestLexibraryConfigIntegration:
    """CuratorConfig integrated into LexibraryConfig."""

    def test_default_curator_present(self) -> None:
        config = LexibraryConfig()
        assert isinstance(config.curator, CuratorConfig)
        assert config.curator.autonomy == "auto_low"
        assert config.curator.max_llm_calls_per_run == 50
        assert config.curator.risk_overrides == {}

    def test_curator_from_dict(self) -> None:
        config = LexibraryConfig.model_validate(
            {"curator": {"autonomy": "full", "max_llm_calls_per_run": 100}}
        )
        assert config.curator.autonomy == "full"
        assert config.curator.max_llm_calls_per_run == 100

    def test_missing_curator_section_uses_defaults(self) -> None:
        config = LexibraryConfig.model_validate({"llm": {"provider": "anthropic"}})
        assert config.curator.autonomy == "auto_low"
        assert config.curator.max_llm_calls_per_run == 50

    def test_partial_curator_section_merges_with_defaults(self) -> None:
        config = LexibraryConfig.model_validate(
            {"curator": {"autonomy": "full"}}
        )
        assert config.curator.autonomy == "full"
        assert config.curator.max_llm_calls_per_run == 50  # default preserved
        assert config.curator.risk_overrides == {}  # default preserved

    def test_config_round_trip(self) -> None:
        original = LexibraryConfig.model_validate(
            {
                "curator": {
                    "autonomy": "propose",
                    "max_llm_calls_per_run": 25,
                    "risk_overrides": {"regen_stale_design": "high"},
                }
            }
        )
        dumped = original.model_dump()
        restored = LexibraryConfig.model_validate(dumped)

        assert restored.curator.autonomy == original.curator.autonomy
        assert restored.curator.max_llm_calls_per_run == original.curator.max_llm_calls_per_run
        assert restored.curator.risk_overrides == original.curator.risk_overrides


# --- Config loader integration tests ---


class TestConfigLoaderCurator:
    """Config loader parses curator: section from YAML."""

    def test_missing_curator_in_yaml_uses_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "llm:\n  provider: anthropic\n"
        )

        config = load_config(
            project_root=tmp_path,
            global_config_path=tmp_path / "nonexistent_global.yaml",
        )
        assert config.curator.autonomy == "auto_low"
        assert config.curator.max_llm_calls_per_run == 50
        assert config.curator.risk_overrides == {}

    def test_full_curator_section_parsed(self, tmp_path: Path) -> None:
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "curator:\n"
            "  autonomy: full\n"
            "  max_llm_calls_per_run: 100\n"
            "  risk_overrides:\n"
            "    deprecate_convention: high\n"
        )

        config = load_config(
            project_root=tmp_path,
            global_config_path=tmp_path / "nonexistent_global.yaml",
        )
        assert config.curator.autonomy == "full"
        assert config.curator.max_llm_calls_per_run == 100
        assert config.curator.risk_overrides == {"deprecate_convention": "high"}

    def test_partial_curator_section_merges(self, tmp_path: Path) -> None:
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "curator:\n  autonomy: propose\n"
        )

        config = load_config(
            project_root=tmp_path,
            global_config_path=tmp_path / "nonexistent_global.yaml",
        )
        assert config.curator.autonomy == "propose"
        assert config.curator.max_llm_calls_per_run == 50  # default
        assert config.curator.risk_overrides == {}  # default
