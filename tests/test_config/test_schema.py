"""Tests for v2 configuration schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lexibrary.config.schema import (
    ConventionConfig,
    ConventionDeclaration,
    CrawlConfig,
    DaemonConfig,
    IgnoreConfig,
    IWHConfig,
    LexibraryConfig,
    LLMConfig,
    MappingConfig,
    TokenBudgetConfig,
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


def test_daemon_config_defaults() -> None:
    config = DaemonConfig()
    assert config.debounce_seconds == 2.0
    assert config.sweep_interval_seconds == 3600
    assert config.sweep_skip_if_unchanged is True
    assert config.git_suppression_seconds == 5
    assert config.watchdog_enabled is False
    assert config.log_level == "info"


def test_daemon_config_enabled_field_removed() -> None:
    """DaemonConfig SHALL NOT have an enabled field."""
    config = DaemonConfig()
    assert not hasattr(config, "enabled")


def test_daemon_config_old_enabled_silently_ignored() -> None:
    """Loading config with old enabled: true field does not raise an error."""
    config = DaemonConfig.model_validate({"enabled": True})
    assert not hasattr(config, "enabled")
    # New defaults still work
    assert config.watchdog_enabled is False
    assert config.sweep_interval_seconds == 3600


def test_lexibrary_config_validates_all_subconfigs() -> None:
    config = LexibraryConfig()
    assert isinstance(config.llm, LLMConfig)
    assert isinstance(config.token_budgets, TokenBudgetConfig)
    assert isinstance(config.mapping, MappingConfig)
    assert isinstance(config.ignore, IgnoreConfig)
    assert isinstance(config.daemon, DaemonConfig)


def test_lexibrary_config_partial_override() -> None:
    config = LexibraryConfig.model_validate({"llm": {"provider": "openai"}})
    assert config.llm.provider == "openai"
    assert config.llm.max_retries == 3
    assert config.daemon.watchdog_enabled is False


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
    config = ConventionConfig.model_validate(
        {"lookup_display_limit": 5, "unknown_field": "value"}
    )
    assert config.lookup_display_limit == 5
    assert not hasattr(config, "unknown_field")


def test_convention_config_accessible_from_lexibrary_config() -> None:
    """LexibraryConfig includes ConventionConfig sub-model with default values."""
    config = LexibraryConfig()
    assert isinstance(config.conventions, ConventionConfig)
    assert config.conventions.lookup_display_limit == 5


def test_convention_config_from_yaml() -> None:
    """conventions.lookup_display_limit can be set via top-level config."""
    config = LexibraryConfig.model_validate(
        {"conventions": {"lookup_display_limit": 10}}
    )
    assert config.conventions.lookup_display_limit == 10


# --- ConventionDeclaration tests ---


def test_convention_declaration_full() -> None:
    """ConventionDeclaration with all fields populated."""
    decl = ConventionDeclaration(
        body="Use UTC everywhere", scope="project", tags=["time"]
    )
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
    decl = ConventionDeclaration.model_validate(
        {"body": "Rule text", "unknown": "value"}
    )
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
    config = LexibraryConfig.model_validate(
        {"token_budgets": {"convention_file_tokens": 800}}
    )
    assert config.token_budgets.convention_file_tokens == 800


# --- Config package re-export tests ---


def test_convention_config_importable_from_package() -> None:
    """ConventionConfig is re-exported from lexibrary.config."""
    from lexibrary.config import ConventionConfig as PackageConventionConfig

    assert PackageConventionConfig is ConventionConfig


def test_convention_declaration_importable_from_package() -> None:
    """ConventionDeclaration is re-exported from lexibrary.config."""
    from lexibrary.config import ConventionDeclaration as PackageConventionDeclaration

    assert PackageConventionDeclaration is ConventionDeclaration
