"""Tests for the default project config template (now loaded from templates/)."""

from __future__ import annotations

from lexibrary.templates import read_template

# Load the template once for all tests in this module.
_DEFAULT_CONFIG = read_template("config/default_config.yaml")


def test_template_is_nonempty_yaml() -> None:
    assert "llm:" in _DEFAULT_CONFIG
    assert "daemon:" in _DEFAULT_CONFIG


def test_template_contains_all_sections() -> None:
    for section in ("llm:", "token_budgets:", "mapping:", "ignore:", "daemon:"):
        assert section in _DEFAULT_CONFIG


def test_template_contains_project_name() -> None:
    """Template includes project_name with default."""
    assert 'project_name: ""' in _DEFAULT_CONFIG


def test_template_contains_agent_environment() -> None:
    """Template includes agent_environment with default."""
    assert "agent_environment: []" in _DEFAULT_CONFIG


def test_template_contains_iwh_section() -> None:
    """Template includes iwh section with enabled: true."""
    assert "iwh:" in _DEFAULT_CONFIG
    assert "enabled: true" in _DEFAULT_CONFIG


def test_template_contains_new_daemon_fields() -> None:
    """Template includes updated daemon fields from update-triggers change."""
    assert "sweep_interval_seconds: 3600" in _DEFAULT_CONFIG
    assert "sweep_skip_if_unchanged: true" in _DEFAULT_CONFIG
    assert "git_suppression_seconds: 5" in _DEFAULT_CONFIG
    assert "watchdog_enabled: false" in _DEFAULT_CONFIG
    assert "log_level: info" in _DEFAULT_CONFIG


def test_template_no_old_enabled_field() -> None:
    """Template SHALL NOT include the old standalone daemon enabled field."""
    # Extract the daemon section and check there is no bare "enabled:" line
    # (watchdog_enabled is fine, but a standalone "enabled:" is not)
    daemon_section = _DEFAULT_CONFIG.split("daemon:")[1].split("\n# ")[0]
    daemon_lines = [line.strip() for line in daemon_section.splitlines()]
    assert not any(line.startswith("enabled:") for line in daemon_lines), (
        "daemon section should not contain a standalone 'enabled:' field"
    )
