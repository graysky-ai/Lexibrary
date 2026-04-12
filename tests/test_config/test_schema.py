"""Tests for v2 configuration schema."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from lexibrary.config.schema import (
    ConceptConfig,
    ConventionConfig,
    ConventionDeclaration,
    CrawlConfig,
    DeprecationConfig,
    IgnoreConfig,
    IWHConfig,
    LexibraryConfig,
    LLMConfig,
    MappingConfig,
    StackConfig,
    SweepConfig,
    SymbolGraphConfig,
    TokenBudgetConfig,
    TopologyConfig,
)


def test_llm_config_defaults() -> None:
    config = LLMConfig()
    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-6"
    assert config.api_key_env == "ANTHROPIC_API_KEY"
    assert config.api_key_source == "env"
    assert config.max_retries == 3
    assert config.timeout == 60


def test_llm_config_api_key_source_default_is_env() -> None:
    """LLMConfig.api_key_source defaults to 'env'."""
    config = LLMConfig()
    assert config.api_key_source == "env"


def test_llm_config_api_key_source_from_yaml() -> None:
    """api_key_source can be set via model_validate (simulating YAML load)."""
    config = LLMConfig.model_validate({"api_key_source": "dotenv"})
    assert config.api_key_source == "dotenv"


def test_llm_config_api_key_source_manual_from_yaml() -> None:
    """api_key_source accepts 'manual' via model_validate."""
    config = LLMConfig.model_validate({"api_key_source": "manual"})
    assert config.api_key_source == "manual"


def test_llm_config_api_key_source_via_top_level_config() -> None:
    """api_key_source is accessible via LexibraryConfig.llm."""
    config = LexibraryConfig.model_validate({"llm": {"api_key_source": "dotenv"}})
    assert config.llm.api_key_source == "dotenv"
    # Other defaults preserved
    assert config.llm.provider == "anthropic"
    assert config.llm.max_retries == 3


def test_token_budget_defaults() -> None:
    config = TokenBudgetConfig()
    assert config.design_file_tokens == 400
    assert config.design_file_abridged_tokens == 100
    assert config.aindex_tokens == 200
    assert config.concept_file_tokens == 400
    assert config.convention_file_tokens == 500
    assert config.lookup_total_tokens == 1200
    assert config.summarize_max_tokens == 200
    assert config.archivist_max_tokens == 5000
    assert not hasattr(config, "start_here_tokens")


def test_token_budget_no_handoff_tokens() -> None:
    """TokenBudgetConfig SHALL NOT have a handoff_tokens attribute (removed)."""
    config = TokenBudgetConfig()
    assert not hasattr(config, "handoff_tokens")


def test_stale_handoff_tokens_silently_ignored() -> None:
    """Loading config with stale handoff_tokens key does not raise an error."""
    config = TokenBudgetConfig.model_validate({"handoff_tokens": 100})
    assert not hasattr(config, "handoff_tokens")
    # Other defaults still work
    assert config.design_file_tokens == 400


def test_stale_start_here_tokens_silently_ignored() -> None:
    """Loading config with stale start_here_tokens key does not raise an error."""
    config = TokenBudgetConfig.model_validate({"start_here_tokens": 800})
    assert not hasattr(config, "start_here_tokens")
    # Other defaults still work
    assert config.design_file_tokens == 400


def test_ignore_config_no_handoff_pattern() -> None:
    """Default additional_patterns SHALL NOT include .lexibrary/HANDOFF.md."""
    config = IgnoreConfig()
    assert ".lexibrary/HANDOFF.md" not in config.additional_patterns


def test_mapping_config_defaults() -> None:
    config = MappingConfig()
    assert config.strategies == []


def test_ignore_config_defaults() -> None:
    config = IgnoreConfig()
    assert config.use_gitignore is True
    # Single ".lexibrary/" pattern replaces the old three child patterns
    assert ".lexibrary/" in config.additional_patterns
    assert "node_modules/" in config.additional_patterns
    assert "__pycache__/" in config.additional_patterns


def test_ignore_config_env_patterns_in_defaults() -> None:
    """IgnoreConfig.additional_patterns includes .env patterns by default."""
    config = IgnoreConfig()
    assert ".env" in config.additional_patterns
    assert ".env.*" in config.additional_patterns
    assert "*.env" in config.additional_patterns


def test_sweep_config_defaults() -> None:
    config = SweepConfig()
    assert config.sweep_interval_seconds == 3600
    assert config.sweep_skip_if_unchanged is True
    assert config.log_level == "info"


def test_sweep_config_removed_daemon_fields() -> None:
    """SweepConfig SHALL NOT have the removed daemon fields."""
    config = SweepConfig()
    assert not hasattr(config, "debounce_seconds")
    assert not hasattr(config, "git_suppression_seconds")
    assert not hasattr(config, "watchdog_enabled")


def test_sweep_config_old_daemon_fields_silently_ignored() -> None:
    """Loading config with old daemon fields does not raise an error."""
    config = SweepConfig.model_validate(
        {
            "debounce_seconds": 5.0,
            "git_suppression_seconds": 10,
            "watchdog_enabled": True,
        }
    )
    assert not hasattr(config, "debounce_seconds")
    assert not hasattr(config, "git_suppression_seconds")
    assert not hasattr(config, "watchdog_enabled")
    # Kept defaults still work
    assert config.sweep_interval_seconds == 3600


def test_lexibrary_config_validates_all_subconfigs() -> None:
    config = LexibraryConfig()
    assert isinstance(config.llm, LLMConfig)
    assert isinstance(config.token_budgets, TokenBudgetConfig)
    assert isinstance(config.mapping, MappingConfig)
    assert isinstance(config.ignore, IgnoreConfig)
    assert isinstance(config.sweep, SweepConfig)


def test_lexibrary_config_partial_override() -> None:
    config = LexibraryConfig.model_validate({"llm": {"provider": "openai"}})
    assert config.llm.provider == "openai"
    assert config.llm.max_retries == 3
    assert config.sweep.sweep_interval_seconds == 3600


def test_invalid_type_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        LLMConfig(max_retries="not_a_number")  # type: ignore[arg-type]


def test_extra_fields_ignored() -> None:
    config = LLMConfig.model_validate({"provider": "x", "unknown": "y"})
    assert config.provider == "x"
    assert not hasattr(config, "unknown")


def test_crawl_config_defaults() -> None:
    config = CrawlConfig()
    for ext in (".png", ".jpg", ".pyc", ".zip", ".exe", ".pdf", ".mp4"):
        assert ext in config.binary_extensions


def test_crawl_config_custom_extensions() -> None:
    config = LexibraryConfig.model_validate({"crawl": {"binary_extensions": [".bin"]}})
    assert config.crawl.binary_extensions == [".bin"]


def test_crawl_config_extra_fields_ignored() -> None:
    config = CrawlConfig.model_validate({"unknown_field": "value"})
    assert not hasattr(config, "unknown_field")


def test_lexibrary_config_has_crawl() -> None:
    config = LexibraryConfig()
    assert isinstance(config.crawl, CrawlConfig)


def test_scope_root_default() -> None:
    config = LexibraryConfig()
    assert config.scope_root == "."


def test_scope_root_custom() -> None:
    config = LexibraryConfig.model_validate({"scope_root": "src/"})
    assert config.scope_root == "src/"


def test_max_file_size_kb_default() -> None:
    config = CrawlConfig()
    assert config.max_file_size_kb == 512


def test_max_file_size_kb_custom() -> None:
    config = LexibraryConfig.model_validate({"crawl": {"max_file_size_kb": 256}})
    assert config.crawl.max_file_size_kb == 256


# --- IWHConfig tests ---


def test_iwh_config_defaults() -> None:
    """IWHConfig() defaults to enabled=True."""
    config = IWHConfig()
    assert config.enabled is True


def test_iwh_config_ttl_hours_default() -> None:
    """IWHConfig.ttl_hours defaults to 72."""
    config = IWHConfig()
    assert config.ttl_hours == 72


def test_iwh_config_ttl_hours_custom() -> None:
    """IWHConfig.ttl_hours can be overridden via model_validate."""
    config = IWHConfig.model_validate({"ttl_hours": 24})
    assert config.ttl_hours == 24


def test_iwh_config_ttl_hours_zero() -> None:
    """IWHConfig.ttl_hours accepts zero (disable TTL expiry)."""
    config = IWHConfig.model_validate({"ttl_hours": 0})
    assert config.ttl_hours == 0


def test_iwh_config_ttl_hours_from_top_level_config() -> None:
    """iwh.ttl_hours can be set via LexibraryConfig model_validate."""
    config = LexibraryConfig.model_validate({"iwh": {"ttl_hours": 48}})
    assert config.iwh.ttl_hours == 48
    # Other defaults preserved
    assert config.iwh.enabled is True


def test_iwh_config_extra_ignored() -> None:
    """IWHConfig tolerates unknown extra fields without raising."""
    config = IWHConfig.model_validate({"enabled": True, "unknown_field": "value"})
    assert config.enabled is True
    assert not hasattr(config, "unknown_field")


# --- New LexibraryConfig field tests ---


def test_project_name_default() -> None:
    """project_name defaults to empty string."""
    config = LexibraryConfig()
    assert config.project_name == ""


def test_agent_environment_default() -> None:
    """agent_environment defaults to empty list."""
    config = LexibraryConfig()
    assert config.agent_environment == []


def test_iwh_enabled_from_yaml() -> None:
    """iwh.enabled can be set to False via model_validate (simulating YAML load)."""
    config = LexibraryConfig.model_validate({"iwh": {"enabled": False}})
    assert config.iwh.enabled is False


def test_agent_environment_from_yaml() -> None:
    """agent_environment can be populated via model_validate (simulating YAML load)."""
    config = LexibraryConfig.model_validate({"agent_environment": ["claude", "cursor"]})
    assert config.agent_environment == ["claude", "cursor"]


def test_lexibrary_config_has_iwh() -> None:
    """LexibraryConfig includes IWHConfig sub-model."""
    config = LexibraryConfig()
    assert isinstance(config.iwh, IWHConfig)


def test_iwh_config_importable_from_package() -> None:
    """IWHConfig is re-exported from lexibrary.config."""
    from lexibrary.config import IWHConfig as PackageIWHConfig

    assert PackageIWHConfig is IWHConfig


# --- ConventionConfig tests ---


def test_convention_config_defaults() -> None:
    """ConventionConfig() defaults to lookup_display_limit=5."""
    config = ConventionConfig()
    assert config.lookup_display_limit == 5


def test_convention_config_custom_display_limit() -> None:
    """ConventionConfig accepts a custom lookup_display_limit from YAML."""
    config = ConventionConfig.model_validate({"lookup_display_limit": 10})
    assert config.lookup_display_limit == 10


def test_convention_config_extra_fields_ignored() -> None:
    """ConventionConfig tolerates unknown extra fields without raising."""
    config = ConventionConfig.model_validate({"lookup_display_limit": 5, "unknown_field": "value"})
    assert config.lookup_display_limit == 5
    assert not hasattr(config, "unknown_field")


def test_convention_config_deprecation_confirm_default() -> None:
    """ConventionConfig() defaults to deprecation_confirm='human'."""
    config = ConventionConfig()
    assert config.deprecation_confirm == "human"


def test_convention_config_deprecation_confirm_maintainer() -> None:
    """ConventionConfig accepts deprecation_confirm='maintainer' from YAML."""
    config = ConventionConfig.model_validate({"deprecation_confirm": "maintainer"})
    assert config.deprecation_confirm == "maintainer"


def test_convention_config_deprecation_confirm_invalid() -> None:
    """ConventionConfig rejects invalid deprecation_confirm values."""
    with pytest.raises(ValidationError):
        ConventionConfig.model_validate({"deprecation_confirm": "auto"})


def test_convention_config_accessible_from_lexibrary_config() -> None:
    """LexibraryConfig includes ConventionConfig sub-model with default values."""
    config = LexibraryConfig()
    assert isinstance(config.conventions, ConventionConfig)
    assert config.conventions.lookup_display_limit == 5
    assert config.conventions.deprecation_confirm == "human"


def test_convention_config_from_yaml() -> None:
    """conventions.lookup_display_limit can be set via top-level config."""
    config = LexibraryConfig.model_validate({"conventions": {"lookup_display_limit": 10}})
    assert config.conventions.lookup_display_limit == 10


def test_convention_config_deprecation_confirm_from_yaml() -> None:
    """conventions.deprecation_confirm can be set via top-level config."""
    config = LexibraryConfig.model_validate({"conventions": {"deprecation_confirm": "maintainer"}})
    assert config.conventions.deprecation_confirm == "maintainer"


# --- ConventionDeclaration tests ---


def test_convention_declaration_full() -> None:
    """ConventionDeclaration with all fields populated."""
    decl = ConventionDeclaration(body="Use UTC everywhere", scope="project", tags=["time"])
    assert decl.body == "Use UTC everywhere"
    assert decl.scope == "project"
    assert decl.tags == ["time"]


def test_convention_declaration_minimal() -> None:
    """ConventionDeclaration with only body defaults scope and tags."""
    decl = ConventionDeclaration(body="No bare prints")
    assert decl.body == "No bare prints"
    assert decl.scope == "project"
    assert decl.tags == []


def test_convention_declaration_extra_fields_ignored() -> None:
    """ConventionDeclaration tolerates unknown extra fields."""
    decl = ConventionDeclaration.model_validate({"body": "Rule text", "unknown": "value"})
    assert decl.body == "Rule text"
    assert not hasattr(decl, "unknown")


def test_convention_declarations_in_lexibrary_config() -> None:
    """convention_declarations can be populated from YAML on LexibraryConfig."""
    config = LexibraryConfig.model_validate(
        {
            "convention_declarations": [
                {"body": "Use UTC everywhere", "scope": "project", "tags": ["time"]},
                {"body": "No bare prints"},
            ]
        }
    )
    assert len(config.convention_declarations) == 2
    assert config.convention_declarations[0].body == "Use UTC everywhere"
    assert config.convention_declarations[0].scope == "project"
    assert config.convention_declarations[0].tags == ["time"]
    assert config.convention_declarations[1].body == "No bare prints"
    assert config.convention_declarations[1].scope == "project"
    assert config.convention_declarations[1].tags == []


def test_convention_declarations_default_empty() -> None:
    """convention_declarations defaults to empty list on LexibraryConfig."""
    config = LexibraryConfig()
    assert config.convention_declarations == []


# --- TokenBudgetConfig convention_file_tokens tests ---


def test_convention_file_tokens_default() -> None:
    """TokenBudgetConfig.convention_file_tokens defaults to 500."""
    config = TokenBudgetConfig()
    assert config.convention_file_tokens == 500


def test_convention_file_tokens_custom() -> None:
    """convention_file_tokens can be overridden from YAML."""
    config = LexibraryConfig.model_validate({"token_budgets": {"convention_file_tokens": 800}})
    assert config.token_budgets.convention_file_tokens == 800


def test_lookup_total_tokens_default() -> None:
    """TokenBudgetConfig.lookup_total_tokens defaults to 1200."""
    config = TokenBudgetConfig()
    assert config.lookup_total_tokens == 1200


def test_lookup_total_tokens_custom() -> None:
    """lookup_total_tokens can be overridden from YAML."""
    config = LexibraryConfig.model_validate({"token_budgets": {"lookup_total_tokens": 2000}})
    assert config.token_budgets.lookup_total_tokens == 2000


def test_token_budget_no_orientation_tokens() -> None:
    """TokenBudgetConfig SHALL NOT have an orientation_tokens attribute (removed)."""
    config = TokenBudgetConfig()
    assert not hasattr(config, "orientation_tokens")


def test_stale_orientation_tokens_silently_ignored() -> None:
    """Loading config with stale orientation_tokens key does not raise an error."""
    config = TokenBudgetConfig.model_validate({"orientation_tokens": 300})
    assert not hasattr(config, "orientation_tokens")
    # Other defaults still work
    assert config.design_file_tokens == 400


# --- TokenBudgetConfig summarize_max_tokens tests ---


def test_summarize_max_tokens_default() -> None:
    """TokenBudgetConfig.summarize_max_tokens defaults to 200."""
    config = TokenBudgetConfig()
    assert config.summarize_max_tokens == 200


def test_summarize_max_tokens_custom() -> None:
    """summarize_max_tokens can be overridden from YAML."""
    config = LexibraryConfig.model_validate({"token_budgets": {"summarize_max_tokens": 500}})
    assert config.token_budgets.summarize_max_tokens == 500


def test_summarize_max_tokens_absent_uses_default() -> None:
    """Absent summarize_max_tokens uses Pydantic default when other fields are set."""
    config = TokenBudgetConfig.model_validate({"design_file_tokens": 600})
    assert config.summarize_max_tokens == 200
    assert config.design_file_tokens == 600


# --- TokenBudgetConfig archivist_max_tokens tests ---


def test_archivist_max_tokens_default() -> None:
    """TokenBudgetConfig.archivist_max_tokens defaults to 5000."""
    config = TokenBudgetConfig()
    assert config.archivist_max_tokens == 5000


def test_archivist_max_tokens_custom() -> None:
    """archivist_max_tokens can be overridden from YAML."""
    config = LexibraryConfig.model_validate({"token_budgets": {"archivist_max_tokens": 8000}})
    assert config.token_budgets.archivist_max_tokens == 8000


def test_archivist_max_tokens_absent_uses_default() -> None:
    """Absent archivist_max_tokens uses Pydantic default when other fields are set."""
    config = TokenBudgetConfig.model_validate({"design_file_tokens": 600})
    assert config.archivist_max_tokens == 5000
    assert config.design_file_tokens == 600


# --- Config package re-export tests ---


def test_convention_config_importable_from_package() -> None:
    """ConventionConfig is re-exported from lexibrary.config."""
    from lexibrary.config import ConventionConfig as PackageConventionConfig

    assert PackageConventionConfig is ConventionConfig


def test_convention_declaration_importable_from_package() -> None:
    """ConventionDeclaration is re-exported from lexibrary.config."""
    from lexibrary.config import ConventionDeclaration as PackageConventionDeclaration

    assert PackageConventionDeclaration is ConventionDeclaration


# --- DeprecationConfig tests ---


def test_deprecation_config_defaults() -> None:
    """DeprecationConfig() defaults to ttl_commits=50 and comment_warning_threshold=10."""
    config = DeprecationConfig()
    assert config.ttl_commits == 50
    assert config.comment_warning_threshold == 10


def test_deprecation_config_custom_ttl() -> None:
    """DeprecationConfig accepts a custom ttl_commits value."""
    config = DeprecationConfig(ttl_commits=100)
    assert config.ttl_commits == 100


def test_deprecation_config_custom_annotation_threshold() -> None:
    """DeprecationConfig accepts a custom comment_warning_threshold value."""
    config = DeprecationConfig(comment_warning_threshold=20)
    assert config.comment_warning_threshold == 20


def test_deprecation_config_extra_fields_ignored() -> None:
    """DeprecationConfig tolerates unknown extra fields without raising."""
    config = DeprecationConfig.model_validate({"ttl_commits": 50, "unknown_field": "value"})
    assert config.ttl_commits == 50
    assert not hasattr(config, "unknown_field")


def test_lexibrary_config_has_deprecation() -> None:
    """LexibraryConfig includes DeprecationConfig sub-model with default values."""
    config = LexibraryConfig()
    assert isinstance(config.deprecation, DeprecationConfig)
    assert config.deprecation.ttl_commits == 50
    assert config.deprecation.comment_warning_threshold == 10


def test_deprecation_config_from_yaml() -> None:
    """deprecation.ttl_commits can be set via top-level config (simulating YAML load)."""
    config = LexibraryConfig.model_validate({"deprecation": {"ttl_commits": 100}})
    assert config.deprecation.ttl_commits == 100
    # Default annotation threshold preserved
    assert config.deprecation.comment_warning_threshold == 10


def test_deprecation_config_full_override_from_yaml() -> None:
    """Both deprecation fields can be overridden via top-level config."""
    config = LexibraryConfig.model_validate(
        {"deprecation": {"ttl_commits": 200, "comment_warning_threshold": 5}}
    )
    assert config.deprecation.ttl_commits == 200
    assert config.deprecation.comment_warning_threshold == 5


def test_deprecation_config_importable_from_package() -> None:
    """DeprecationConfig is re-exported from lexibrary.config."""
    from lexibrary.config import DeprecationConfig as PackageDeprecationConfig

    assert PackageDeprecationConfig is DeprecationConfig


# --- ConceptConfig tests ---


def test_concept_config_defaults() -> None:
    """ConceptConfig() defaults to deprecation_confirm='human'."""
    config = ConceptConfig()
    assert config.deprecation_confirm == "human"


def test_concept_config_custom_deprecation_confirm() -> None:
    """ConceptConfig accepts deprecation_confirm='maintainer' from YAML."""
    config = ConceptConfig.model_validate({"deprecation_confirm": "maintainer"})
    assert config.deprecation_confirm == "maintainer"


def test_concept_config_invalid_deprecation_confirm() -> None:
    """ConceptConfig rejects invalid deprecation_confirm values."""
    with pytest.raises(ValidationError):
        ConceptConfig.model_validate({"deprecation_confirm": "invalid"})


def test_concept_config_extra_fields_ignored() -> None:
    """ConceptConfig tolerates unknown extra fields without raising."""
    config = ConceptConfig.model_validate(
        {"deprecation_confirm": "human", "unknown_field": "value"}
    )
    assert config.deprecation_confirm == "human"
    assert not hasattr(config, "unknown_field")


def test_lexibrary_config_has_concepts() -> None:
    """LexibraryConfig includes ConceptConfig sub-model with default values."""
    config = LexibraryConfig()
    assert isinstance(config.concepts, ConceptConfig)
    assert config.concepts.deprecation_confirm == "human"


def test_concept_config_from_yaml() -> None:
    """concepts.deprecation_confirm can be set via top-level config (simulating YAML load)."""
    config = LexibraryConfig.model_validate({"concepts": {"deprecation_confirm": "maintainer"}})
    assert config.concepts.deprecation_confirm == "maintainer"


def test_concept_config_from_yaml_preserves_other_defaults() -> None:
    """Setting concepts config preserves other LexibraryConfig defaults."""
    config = LexibraryConfig.model_validate({"concepts": {"deprecation_confirm": "maintainer"}})
    assert config.concepts.deprecation_confirm == "maintainer"
    # Other defaults preserved
    assert config.llm.provider == "anthropic"
    assert config.deprecation.ttl_commits == 50


def test_concept_config_importable_from_package() -> None:
    """ConceptConfig is re-exported from lexibrary.config."""
    from lexibrary.config import ConceptConfig as PackageConceptConfig

    assert PackageConceptConfig is ConceptConfig


# --- StackConfig tests ---


def test_stack_config_defaults() -> None:
    """StackConfig() defaults match spec: human confirm, 200/100 TTLs, 3 display limit."""
    config = StackConfig()
    assert config.staleness_confirm == "human"
    assert config.staleness_ttl_commits == 200
    assert config.staleness_ttl_short_commits == 100
    assert config.lookup_display_limit == 3


def test_stack_config_custom_staleness_ttl() -> None:
    """StackConfig accepts a custom staleness_ttl_commits value."""
    config = StackConfig(staleness_ttl_commits=300)
    assert config.staleness_ttl_commits == 300


def test_stack_config_custom_short_ttl() -> None:
    """StackConfig accepts a custom staleness_ttl_short_commits value."""
    config = StackConfig(staleness_ttl_short_commits=50)
    assert config.staleness_ttl_short_commits == 50


def test_stack_config_maintainer_confirm() -> None:
    """StackConfig accepts staleness_confirm='maintainer' from YAML."""
    config = StackConfig.model_validate({"staleness_confirm": "maintainer"})
    assert config.staleness_confirm == "maintainer"


def test_stack_config_invalid_staleness_confirm() -> None:
    """StackConfig rejects invalid staleness_confirm values."""
    with pytest.raises(ValidationError):
        StackConfig.model_validate({"staleness_confirm": "auto"})


def test_stack_config_extra_fields_ignored() -> None:
    """StackConfig tolerates unknown extra fields without raising."""
    config = StackConfig.model_validate({"staleness_ttl_commits": 200, "unknown_field": "value"})
    assert config.staleness_ttl_commits == 200
    assert not hasattr(config, "unknown_field")


def test_stack_config_custom_lookup_display_limit() -> None:
    """StackConfig accepts a custom lookup_display_limit value."""
    config = StackConfig(lookup_display_limit=5)
    assert config.lookup_display_limit == 5


def test_lexibrary_config_has_stack() -> None:
    """LexibraryConfig includes StackConfig sub-model with default values."""
    config = LexibraryConfig()
    assert isinstance(config.stack, StackConfig)
    assert config.stack.staleness_ttl_commits == 200
    assert config.stack.staleness_ttl_short_commits == 100
    assert config.stack.staleness_confirm == "human"
    assert config.stack.lookup_display_limit == 3


def test_stack_config_from_yaml() -> None:
    """stack.staleness_ttl_commits can be set via top-level config (simulating YAML load)."""
    config = LexibraryConfig.model_validate({"stack": {"staleness_ttl_commits": 300}})
    assert config.stack.staleness_ttl_commits == 300
    # Other defaults preserved
    assert config.stack.staleness_ttl_short_commits == 100
    assert config.stack.staleness_confirm == "human"


def test_stack_config_full_override_from_yaml() -> None:
    """All stack config fields can be overridden via top-level config."""
    config = LexibraryConfig.model_validate(
        {
            "stack": {
                "staleness_confirm": "maintainer",
                "staleness_ttl_commits": 300,
                "staleness_ttl_short_commits": 50,
                "lookup_display_limit": 5,
            }
        }
    )
    assert config.stack.staleness_confirm == "maintainer"
    assert config.stack.staleness_ttl_commits == 300
    assert config.stack.staleness_ttl_short_commits == 50
    assert config.stack.lookup_display_limit == 5


def test_stack_config_from_yaml_preserves_other_defaults() -> None:
    """Setting stack config preserves other LexibraryConfig defaults."""
    config = LexibraryConfig.model_validate({"stack": {"staleness_ttl_commits": 300}})
    assert config.stack.staleness_ttl_commits == 300
    # Other defaults preserved
    assert config.llm.provider == "anthropic"
    assert config.deprecation.ttl_commits == 50


def test_stack_config_importable_from_package() -> None:
    """StackConfig is re-exported from lexibrary.config."""
    from lexibrary.config import StackConfig as PackageStackConfig

    assert PackageStackConfig is StackConfig


# --- TopologyConfig tests ---


def test_topology_config_defaults() -> None:
    """TopologyConfig() defaults to detail_dirs=[]."""
    config = TopologyConfig()
    assert config.detail_dirs == []


def test_topology_config_custom_detail_dirs() -> None:
    """TopologyConfig accepts custom detail_dirs from YAML."""
    config = TopologyConfig.model_validate({"detail_dirs": ["baml_src/", "docs/"]})
    assert config.detail_dirs == ["baml_src/", "docs/"]


def test_topology_config_extra_fields_ignored() -> None:
    """TopologyConfig tolerates unknown extra fields without raising."""
    config = TopologyConfig.model_validate({"detail_dirs": [], "unknown_field": "value"})
    assert config.detail_dirs == []
    assert not hasattr(config, "unknown_field")


def test_lexibrary_config_has_topology() -> None:
    """LexibraryConfig includes TopologyConfig sub-model with default values."""
    config = LexibraryConfig()
    assert isinstance(config.topology, TopologyConfig)
    assert config.topology.detail_dirs == []


def test_topology_config_from_yaml() -> None:
    """topology.detail_dirs can be set via top-level config (simulating YAML load)."""
    config = LexibraryConfig.model_validate({"topology": {"detail_dirs": ["baml_src/", "docs/"]}})
    assert config.topology.detail_dirs == ["baml_src/", "docs/"]
    # Other defaults preserved
    assert config.llm.provider == "anthropic"


def test_topology_config_from_yaml_preserves_other_defaults() -> None:
    """Setting topology config preserves other LexibraryConfig defaults."""
    config = LexibraryConfig.model_validate({"topology": {"detail_dirs": ["src/"]}})
    assert config.topology.detail_dirs == ["src/"]
    assert config.deprecation.ttl_commits == 50
    assert config.sweep.sweep_interval_seconds == 3600


def test_topology_config_importable_from_package() -> None:
    """TopologyConfig is re-exported from lexibrary.config."""
    from lexibrary.config import TopologyConfig as PackageTopologyConfig

    assert PackageTopologyConfig is TopologyConfig


# --- SymbolGraphConfig tests ---


def test_symbols_config_defaults() -> None:
    """LexibraryConfig().symbols defaults to SymbolGraphConfig(enabled=True)."""
    config = LexibraryConfig()
    assert isinstance(config.symbols, SymbolGraphConfig)
    assert config.symbols.enabled is True


def test_symbols_config_disabled_from_yaml() -> None:
    """symbols.enabled can be set to False via YAML-loaded dict."""
    yaml_snippet = "symbols:\n  enabled: false\n"
    data = yaml.safe_load(yaml_snippet)
    config = LexibraryConfig.model_validate(data)
    assert config.symbols.enabled is False


def test_symbols_config_extra_fields_ignored() -> None:
    """SymbolGraphConfig tolerates unknown extra fields without raising."""
    config = SymbolGraphConfig.model_validate({"enabled": True, "unknown_field": "value"})
    assert config.enabled is True
    assert not hasattr(config, "unknown_field")


def test_symbols_config_importable_from_package() -> None:
    """SymbolGraphConfig is re-exported from lexibrary.config."""
    from lexibrary.config import SymbolGraphConfig as PackageSymbolGraphConfig

    assert PackageSymbolGraphConfig is SymbolGraphConfig


def test_symbols_config_default_enrichment_flags() -> None:
    """SymbolGraphConfig() exposes the Phase 5 enrichment defaults."""
    config = SymbolGraphConfig()
    assert config.enabled is True
    assert config.include_enums is True
    assert config.include_call_paths is False
    assert config.call_path_depth == 2
    assert config.max_enum_items == 20
    assert config.max_call_path_items == 10


def test_symbols_config_override_enrichment() -> None:
    """All five enrichment flags can be overridden via a YAML-loaded dict."""
    yaml_snippet = (
        "symbols:\n"
        "  include_enums: false\n"
        "  include_call_paths: true\n"
        "  call_path_depth: 3\n"
        "  max_enum_items: 50\n"
        "  max_call_path_items: 25\n"
    )
    data = yaml.safe_load(yaml_snippet)
    config = LexibraryConfig.model_validate(data)
    assert config.symbols.include_enums is False
    assert config.symbols.include_call_paths is True
    assert config.symbols.call_path_depth == 3
    assert config.symbols.max_enum_items == 50
    assert config.symbols.max_call_path_items == 25
    # The enabled flag default is preserved when not overridden.
    assert config.symbols.enabled is True


def test_symbols_config_accepts_phase1_yaml_without_new_keys() -> None:
    """Pre-Phase-5 YAML containing only enabled: true loads with enrichment defaults."""
    yaml_snippet = "symbols:\n  enabled: true\n"
    data = yaml.safe_load(yaml_snippet)
    config = LexibraryConfig.model_validate(data)
    assert config.symbols.enabled is True
    # All enrichment defaults apply because the YAML omits them.
    assert config.symbols.include_enums is True
    assert config.symbols.include_call_paths is False
    assert config.symbols.call_path_depth == 2
    assert config.symbols.max_enum_items == 20
    assert config.symbols.max_call_path_items == 10


# --- SymbolGraphConfig include_data_flows tests (Phase 7) ---


def test_symbols_config_default_include_data_flows_false() -> None:
    """SymbolGraphConfig().include_data_flows defaults to False (opt-in)."""
    config = SymbolGraphConfig()
    assert config.include_data_flows is False


def test_symbols_config_override_include_data_flows_true() -> None:
    """include_data_flows can be set to True via a YAML-loaded dict."""
    yaml_snippet = "symbols:\n  include_data_flows: true\n"
    data = yaml.safe_load(yaml_snippet)
    config = LexibraryConfig.model_validate(data)
    assert config.symbols.include_data_flows is True
    # Other defaults preserved when not overridden.
    assert config.symbols.enabled is True
    assert config.symbols.include_enums is True
    assert config.symbols.include_call_paths is False
    assert config.symbols.max_call_path_items == 10


def test_symbols_config_accepts_phase5_yaml_without_data_flows_key() -> None:
    """Pre-Phase-7 YAML with Phase 5 keys but no include_data_flows loads cleanly."""
    yaml_snippet = (
        "symbols:\n"
        "  enabled: true\n"
        "  include_enums: true\n"
        "  include_call_paths: false\n"
        "  call_path_depth: 2\n"
        "  max_enum_items: 20\n"
        "  max_call_path_items: 10\n"
    )
    data = yaml.safe_load(yaml_snippet)
    config = LexibraryConfig.model_validate(data)
    # include_data_flows falls back to its Pydantic default of False.
    assert config.symbols.include_data_flows is False
    # All explicitly-set Phase 5 fields are respected.
    assert config.symbols.enabled is True
    assert config.symbols.include_enums is True
    assert config.symbols.include_call_paths is False
    assert config.symbols.call_path_depth == 2
    assert config.symbols.max_enum_items == 20
    assert config.symbols.max_call_path_items == 10
