"""Tests for CuratorConfig model and LexibraryConfig integration."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.config.loader import load_config
from lexibrary.config.schema import ConceptConfig, ConventionConfig, LexibraryConfig
from lexibrary.curator.config import (
    DEPRECATION_ACTION_KEYS,
    CuratorConfig,
    CuratorDeprecationConfig,
)

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


# --- Phase 2: CuratorDeprecationConfig tests ---


class TestCuratorDeprecationConfigDefaults:
    """Default values for the nested deprecation config."""

    def test_default_ttl_commits(self) -> None:
        config = CuratorDeprecationConfig()
        assert config.ttl_commits == 50

    def test_custom_ttl_commits(self) -> None:
        config = CuratorDeprecationConfig(ttl_commits=100)
        assert config.ttl_commits == 100

    def test_minimum_ttl_commits(self) -> None:
        config = CuratorDeprecationConfig(ttl_commits=1)
        assert config.ttl_commits == 1

    def test_zero_ttl_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ttl_commits"):
            CuratorDeprecationConfig(ttl_commits=0)

    def test_negative_ttl_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ttl_commits"):
            CuratorDeprecationConfig(ttl_commits=-1)


class TestCuratorConfigDeprecationIntegration:
    """CuratorConfig.deprecation nested model."""

    def test_default_deprecation_present(self) -> None:
        config = CuratorConfig()
        assert isinstance(config.deprecation, CuratorDeprecationConfig)
        assert config.deprecation.ttl_commits == 50

    def test_custom_deprecation_from_dict(self) -> None:
        config = CuratorConfig.model_validate(
            {"deprecation": {"ttl_commits": 200}}
        )
        assert config.deprecation.ttl_commits == 200

    def test_missing_deprecation_uses_defaults(self) -> None:
        config = CuratorConfig.model_validate({"autonomy": "full"})
        assert config.deprecation.ttl_commits == 50


# --- Phase 2: deprecation_confirm on ConceptConfig / ConventionConfig ---


class TestCuratorDeprecationConfirm:
    """curator_deprecation_confirm field on Concept and Convention configs."""

    def test_concept_default_false(self) -> None:
        config = ConceptConfig()
        assert config.curator_deprecation_confirm is False

    def test_concept_set_true(self) -> None:
        config = ConceptConfig.model_validate({"curator_deprecation_confirm": True})
        assert config.curator_deprecation_confirm is True

    def test_convention_default_false(self) -> None:
        config = ConventionConfig()
        assert config.curator_deprecation_confirm is False

    def test_convention_set_true(self) -> None:
        config = ConventionConfig.model_validate({"curator_deprecation_confirm": True})
        assert config.curator_deprecation_confirm is True

    def test_full_config_concept_deprecation_confirm(self) -> None:
        config = LexibraryConfig.model_validate(
            {"concepts": {"curator_deprecation_confirm": True}}
        )
        assert config.concepts.curator_deprecation_confirm is True

    def test_full_config_convention_deprecation_confirm(self) -> None:
        config = LexibraryConfig.model_validate(
            {"conventions": {"curator_deprecation_confirm": True}}
        )
        assert config.conventions.curator_deprecation_confirm is True


# --- Phase 2: risk_overrides validation warnings ---


class TestRiskOverridesValidation:
    """Unknown risk_overrides keys produce warnings (not errors)."""

    def test_known_deprecation_key_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = CuratorConfig(risk_overrides={"deprecate_concept": "low"})
            assert config.risk_overrides == {"deprecate_concept": "low"}
            unknown_warnings = [
                x for x in w if "Unknown risk_overrides key" in str(x.message)
            ]
            assert len(unknown_warnings) == 0

    def test_unknown_key_produces_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            CuratorConfig(risk_overrides={"totally_unknown_action": "high"})
            unknown_warnings = [
                x for x in w if "Unknown risk_overrides key" in str(x.message)
            ]
            assert len(unknown_warnings) == 1
            assert "totally_unknown_action" in str(unknown_warnings[0].message)

    def test_unknown_key_still_accepted(self) -> None:
        """Unknown keys produce a warning but are NOT rejected."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            config = CuratorConfig(risk_overrides={"future_action": "medium"})
            assert config.risk_overrides == {"future_action": "medium"}

    def test_all_deprecation_action_keys_accepted(self) -> None:
        """Every key in DEPRECATION_ACTION_KEYS is accepted without warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            overrides = {key: "low" for key in DEPRECATION_ACTION_KEYS}
            config = CuratorConfig(risk_overrides=overrides)
            assert len(config.risk_overrides) == len(DEPRECATION_ACTION_KEYS)
            unknown_warnings = [
                x for x in w if "Unknown risk_overrides key" in str(x.message)
            ]
            assert len(unknown_warnings) == 0

    def test_deprecation_action_keys_count(self) -> None:
        """Verify we have all 13 deprecation action keys."""
        assert len(DEPRECATION_ACTION_KEYS) == 13


# --- Phase 2: YAML round-trip with new fields ---


class TestPhase2YAMLRoundTrip:
    """Config YAML round-trip with Phase 2 deprecation fields."""

    def test_risk_overrides_round_trip(self) -> None:
        """Parse, serialize, parse again — risk_overrides value preserved."""
        original = LexibraryConfig.model_validate(
            {
                "curator": {
                    "risk_overrides": {"deprecate_concept": "low"},
                }
            }
        )
        dumped = original.model_dump()
        restored = LexibraryConfig.model_validate(dumped)
        assert restored.curator.risk_overrides == {"deprecate_concept": "low"}

    def test_deprecation_ttl_round_trip(self) -> None:
        original = LexibraryConfig.model_validate(
            {"curator": {"deprecation": {"ttl_commits": 100}}}
        )
        dumped = original.model_dump()
        restored = LexibraryConfig.model_validate(dumped)
        assert restored.curator.deprecation.ttl_commits == 100

    def test_curator_deprecation_confirm_round_trip(self) -> None:
        original = LexibraryConfig.model_validate(
            {
                "concepts": {"curator_deprecation_confirm": True},
                "conventions": {"curator_deprecation_confirm": True},
            }
        )
        dumped = original.model_dump()
        restored = LexibraryConfig.model_validate(dumped)
        assert restored.concepts.curator_deprecation_confirm is True
        assert restored.conventions.curator_deprecation_confirm is True

    def test_full_phase2_config_round_trip(self, tmp_path: Path) -> None:
        """Full YAML load round-trip with all Phase 2 config fields."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "curator:\n"
            "  autonomy: full\n"
            "  risk_overrides:\n"
            "    deprecate_concept: low\n"
            "  deprecation:\n"
            "    ttl_commits: 75\n"
            "concepts:\n"
            "  curator_deprecation_confirm: true\n"
            "conventions:\n"
            "  curator_deprecation_confirm: true\n"
        )
        config = load_config(
            project_root=tmp_path,
            global_config_path=tmp_path / "nonexistent_global.yaml",
        )
        assert config.curator.risk_overrides == {"deprecate_concept": "low"}
        assert config.curator.deprecation.ttl_commits == 75
        assert config.concepts.curator_deprecation_confirm is True
        assert config.conventions.curator_deprecation_confirm is True
