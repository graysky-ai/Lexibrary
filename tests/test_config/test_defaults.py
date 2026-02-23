"""Tests for the default project config template."""

from __future__ import annotations

from lexibrary.config.defaults import DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_is_nonempty_yaml() -> None:
    assert "llm:" in DEFAULT_PROJECT_CONFIG_TEMPLATE
    assert "daemon:" in DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_contains_all_sections() -> None:
    for section in ("llm:", "token_budgets:", "mapping:", "ignore:", "daemon:"):
        assert section in DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_contains_project_name() -> None:
    """Template includes project_name with default."""
    assert 'project_name: ""' in DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_contains_agent_environment() -> None:
    """Template includes agent_environment with default."""
    assert "agent_environment: []" in DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_contains_iwh_section() -> None:
    """Template includes iwh section with enabled: true."""
    assert "iwh:" in DEFAULT_PROJECT_CONFIG_TEMPLATE
    assert "enabled: true" in DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_contains_new_daemon_fields() -> None:
    """Template includes updated daemon fields from update-triggers change."""
    assert "sweep_interval_seconds: 3600" in DEFAULT_PROJECT_CONFIG_TEMPLATE
    assert "sweep_skip_if_unchanged: true" in DEFAULT_PROJECT_CONFIG_TEMPLATE
    assert "git_suppression_seconds: 5" in DEFAULT_PROJECT_CONFIG_TEMPLATE
    assert "watchdog_enabled: false" in DEFAULT_PROJECT_CONFIG_TEMPLATE
    assert "log_level: info" in DEFAULT_PROJECT_CONFIG_TEMPLATE


def test_template_no_old_enabled_field() -> None:
    """Template SHALL NOT include the old standalone daemon enabled field."""
    # Extract the daemon section and check there is no bare "enabled:" line
    # (watchdog_enabled is fine, but a standalone "enabled:" is not)
    daemon_section = DEFAULT_PROJECT_CONFIG_TEMPLATE.split("daemon:")[1].split("\n# ")[0]
    daemon_lines = [line.strip() for line in daemon_section.splitlines()]
    assert not any(line.startswith("enabled:") for line in daemon_lines), (
        "daemon section should not contain a standalone 'enabled:' field"
    )
