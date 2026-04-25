"""Per-step tests for the upgrade pipeline.

Each step is exercised in two paths: the "needs upgrade" path (asserts
``changed=True`` and verifies the on-disk effect) and the "already
current" path (asserts ``changed=False`` so the step is verified as
idempotent).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lexibrary.config.schema import LexibraryConfig
from lexibrary.upgrade.steps import (
    UPGRADE_STEPS,
    apply_agent_rules,
    apply_config_migrations,
    apply_gitignore_patterns,
    apply_iwh_gitignore,
    apply_skeleton_directories,
    apply_version_stamp,
)

# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_registry_step_names_are_unique() -> None:
    """No duplicate step names — the CLI report uses them as keys."""
    names = [s.name for s in UPGRADE_STEPS]
    assert len(names) == len(set(names))


def test_registry_step_descriptions_are_non_empty() -> None:
    """Every registered step has a human-readable description."""
    for step in UPGRADE_STEPS:
        assert step.description.strip()


# ---------------------------------------------------------------------------
# config-migrations
# ---------------------------------------------------------------------------


def test_config_migrations_rewrites_legacy_scope_root(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".lexibrary"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope_root: .\nproject_name: legacy\n")

    config = LexibraryConfig()  # in-memory placeholder; step reads file directly
    result = apply_config_migrations(tmp_path, config)
    assert result.changed
    assert "scope_root" in result.summary

    after = yaml.safe_load((cfg_dir / "config.yaml").read_text(encoding="utf-8"))
    assert "scope_root" not in after
    assert after["scope_roots"] == [{"path": "."}]


def test_config_migrations_idempotent_when_clean(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".lexibrary"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope_roots:\n  - path: .\n")

    config = LexibraryConfig()
    result = apply_config_migrations(tmp_path, config)
    assert not result.changed


# ---------------------------------------------------------------------------
# version-stamp
# ---------------------------------------------------------------------------


def test_version_stamp_writes_current_version(tmp_path: Path) -> None:
    from lexibrary import __version__ as current_version

    cfg_dir = tmp_path / ".lexibrary"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope_roots:\n  - path: .\n")
    config = LexibraryConfig()  # lexibrary_version defaults to ""

    result = apply_version_stamp(tmp_path, config)
    assert result.changed
    assert current_version in result.summary

    after = yaml.safe_load((cfg_dir / "config.yaml").read_text(encoding="utf-8"))
    assert after["lexibrary_version"] == current_version


def test_version_stamp_skips_when_current(tmp_path: Path) -> None:
    from lexibrary import __version__ as current_version

    cfg_dir = tmp_path / ".lexibrary"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        f"scope_roots:\n  - path: .\nlexibrary_version: '{current_version}'\n"
    )
    config = LexibraryConfig.model_validate({"lexibrary_version": current_version})

    result = apply_version_stamp(tmp_path, config)
    assert not result.changed
    assert current_version in result.summary


# ---------------------------------------------------------------------------
# skeleton-directories
# ---------------------------------------------------------------------------


def test_skeleton_directories_creates_missing(tmp_path: Path) -> None:
    (tmp_path / ".lexibrary").mkdir()
    # Only some subdirs exist.
    (tmp_path / ".lexibrary" / "designs").mkdir()

    config = LexibraryConfig()
    result = apply_skeleton_directories(tmp_path, config)
    assert result.changed
    for sub in ["concepts", "conventions", "designs", "stack"]:
        assert (tmp_path / ".lexibrary" / sub).is_dir()


def test_skeleton_directories_idempotent_when_complete(tmp_path: Path) -> None:
    base = tmp_path / ".lexibrary"
    base.mkdir()
    for sub in ["concepts", "conventions", "designs", "stack"]:
        (base / sub).mkdir()

    config = LexibraryConfig()
    result = apply_skeleton_directories(tmp_path, config)
    assert not result.changed


# ---------------------------------------------------------------------------
# gitignore-patterns
# ---------------------------------------------------------------------------


def test_gitignore_patterns_adds_missing_patterns(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".lexibrary/index.db\n", encoding="utf-8")

    config = LexibraryConfig()
    result = apply_gitignore_patterns(tmp_path, config)
    assert result.changed
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "symbols.db" in text
    assert ".lexibrary/tmp/" in text


def test_gitignore_patterns_idempotent_when_complete(tmp_path: Path) -> None:
    from lexibrary.init.scaffolder import _GENERATED_GITIGNORE_PATTERNS

    (tmp_path / ".gitignore").write_text(
        "\n".join(_GENERATED_GITIGNORE_PATTERNS) + "\n", encoding="utf-8"
    )

    config = LexibraryConfig()
    result = apply_gitignore_patterns(tmp_path, config)
    assert not result.changed


# ---------------------------------------------------------------------------
# iwh-gitignore
# ---------------------------------------------------------------------------


def test_iwh_gitignore_adds_pattern(tmp_path: Path) -> None:
    config = LexibraryConfig()
    result = apply_iwh_gitignore(tmp_path, config)
    # First run: either creates the file or appends to an empty one.
    assert (tmp_path / ".gitignore").exists()
    assert "**/.iwh" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert result.changed or "**/.iwh" in result.summary


def test_iwh_gitignore_idempotent(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("**/.iwh\n", encoding="utf-8")
    config = LexibraryConfig()
    result = apply_iwh_gitignore(tmp_path, config)
    assert not result.changed


# ---------------------------------------------------------------------------
# agent-rules
# ---------------------------------------------------------------------------


def test_agent_rules_skips_when_no_environments(tmp_path: Path) -> None:
    config = LexibraryConfig.model_validate({"agent_environment": []})
    result = apply_agent_rules(tmp_path, config)
    assert not result.changed
    assert result.warnings  # surfaces "no agent_environment configured"


def test_agent_rules_regenerates_for_configured_env(tmp_path: Path) -> None:
    (tmp_path / ".lexibrary").mkdir()
    config = LexibraryConfig.model_validate({"agent_environment": ["claude"]})
    result = apply_agent_rules(tmp_path, config)
    assert result.changed
    assert (tmp_path / "CLAUDE.md").exists()


def test_agent_rules_warns_on_unsupported_env(tmp_path: Path) -> None:
    (tmp_path / ".lexibrary").mkdir()
    config = LexibraryConfig.model_validate({"agent_environment": ["claude", "bogus"]})
    result = apply_agent_rules(tmp_path, config)
    assert result.changed  # still ran for claude
    assert any("bogus" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# git-hooks
# ---------------------------------------------------------------------------


def test_git_hooks_skipped_without_git_dir(tmp_path: Path) -> None:
    from lexibrary.upgrade.steps import apply_git_hooks

    config = LexibraryConfig()
    result = apply_git_hooks(tmp_path, config)
    assert not result.changed
    assert "no .git" in result.summary


def test_git_hooks_installs_when_git_dir_present(tmp_path: Path) -> None:
    from lexibrary.upgrade.steps import apply_git_hooks

    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    config = LexibraryConfig()
    result = apply_git_hooks(tmp_path, config)
    assert result.changed
    assert (tmp_path / ".git" / "hooks" / "pre-commit").exists()
    assert (tmp_path / ".git" / "hooks" / "post-commit").exists()


def test_git_hooks_idempotent(tmp_path: Path) -> None:
    from lexibrary.upgrade.steps import apply_git_hooks

    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    config = LexibraryConfig()
    apply_git_hooks(tmp_path, config)  # first run
    second = apply_git_hooks(tmp_path, config)  # second run
    assert not second.changed


# ---------------------------------------------------------------------------
# End-to-end: run all steps on a graysky-v2-style legacy project
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_project(tmp_path: Path) -> Path:
    """Fixture: a project that mirrors graysky-v2's pre-upgrade state.

    - legacy ``scope_root: .`` in config.yaml
    - older agent_environment, dotenv-style llm config
    - .gitignore with only the early lexibrary patterns
    - all .lexibrary/ subdirectories present
    - no .git/ directory (so git-hooks step is a skip, not a failure)
    """
    base = tmp_path / ".lexibrary"
    base.mkdir()
    for sub in ["concepts", "conventions", "designs", "stack"]:
        (base / sub).mkdir()
    (base / "config.yaml").write_text(
        "scope_root: .\n"
        "project_name: graysky-v2\n"
        "agent_environment:\n- claude\n"
        "iwh:\n  enabled: true\n"
        "llm:\n"
        "  provider: openai\n"
        "  model: gpt-4o\n"
        "  api_key_env: OPENAI_API_KEY\n"
        "  api_key_source: dotenv\n"
    )
    (tmp_path / ".gitignore").write_text(".lexibrary/index.db\n", encoding="utf-8")
    return tmp_path


def test_run_upgrade_on_legacy_project(legacy_project: Path) -> None:
    """End-to-end: every step runs cleanly and the project lands on current schema."""
    from lexibrary import __version__ as current_version
    from lexibrary.config.loader import load_config
    from lexibrary.upgrade import run_upgrade

    config = load_config(legacy_project)
    results = run_upgrade(legacy_project, config)

    by_name = {r.name: r for r in results}
    # The two surface gaps we care about.
    assert by_name["config-migrations"].changed
    assert by_name["version-stamp"].changed
    assert by_name["gitignore-patterns"].changed
    assert by_name["agent-rules"].changed
    # No .git dir in the fixture → git-hooks is a clean skip, not a failure.
    assert not by_name["git-hooks"].changed
    assert "no .git" in by_name["git-hooks"].summary

    # Verify on-disk state.
    cfg = yaml.safe_load(
        (legacy_project / ".lexibrary" / "config.yaml").read_text(encoding="utf-8")
    )
    assert "scope_root" not in cfg
    assert cfg["scope_roots"] == [{"path": "."}]
    assert cfg["lexibrary_version"] == current_version
    assert "symbols.db" in (legacy_project / ".gitignore").read_text(encoding="utf-8")
    assert (legacy_project / "CLAUDE.md").exists()


def test_run_upgrade_idempotent(legacy_project: Path) -> None:
    """A second run after a first should report all-clean."""
    from lexibrary.config.loader import load_config
    from lexibrary.upgrade import run_upgrade

    # First pass: bring it current.
    run_upgrade(legacy_project, load_config(legacy_project))

    # Second pass: re-load (legacy keys now persisted, version stamp now present)
    # and confirm every step reports unchanged.
    second = run_upgrade(legacy_project, load_config(legacy_project))
    by_name = {r.name: r for r in second}
    assert not by_name["config-migrations"].changed
    assert not by_name["version-stamp"].changed
    assert not by_name["skeleton-directories"].changed
    assert not by_name["gitignore-patterns"].changed
    assert not by_name["iwh-gitignore"].changed
