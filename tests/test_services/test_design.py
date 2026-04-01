"""Unit tests for lexibrary.services.design — DesignUpdateDecision and check_design_update()."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import yaml

from lexibrary.services.design import DesignUpdateDecision, check_design_update

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary directory and config."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


def _write_source(project: Path, rel_path: str, content: str) -> Path:
    """Create a source file and return its absolute path."""
    source = project / rel_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _create_design_file(
    project: Path,
    source_rel: str,
    source_content: str,
    *,
    updated_by: str = "archivist",
    include_footer: bool = True,
    source_hash_override: str | None = None,
) -> Path:
    """Create a design file in .lexibrary mirror tree with frontmatter and optional footer."""
    content_hash = source_hash_override or hashlib.sha256(
        source_content.encode()
    ).hexdigest()
    design_path = project / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    fm_data = {
        "description": f"Design file for {source_rel}",
        "id": "DS-001",
        "updated_by": updated_by,
        "status": "active",
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    parts = [f"---\n{fm_str}\n---\n", f"\n# {source_rel}\n", "\nTest design file content.\n"]

    if include_footer:
        parts.append(
            f"\n<!-- lexibrary:meta\n"
            f"source: {source_rel}\n"
            f"source_hash: {content_hash}\n"
            f"design_hash: placeholder\n"
            f"generated: {now}\n"
            f"generator: lexibrary-v2\n"
            f"-->\n"
        )

    design_path.write_text("".join(parts), encoding="utf-8")
    return design_path


def _create_iwh_blocked(project: Path, source_dir_rel: str, body: str = "Work in progress") -> Path:
    """Create a blocked IWH signal in the designs mirror for a source directory.

    The IWH parser treats everything after the closing ``---`` as the body,
    so we place the body text there (not inside the YAML frontmatter).
    """
    iwh_dir = project / ".lexibrary" / "designs" / source_dir_rel
    iwh_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = iwh_dir / ".iwh"

    iwh_data = {
        "author": "test-agent",
        "created": datetime.now().isoformat(),
        "scope": "blocked",
    }
    fm_str = yaml.dump(iwh_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    iwh_path.write_text(f"---\n{fm_str}\n---\n{body}\n", encoding="utf-8")
    return iwh_path


def _create_iwh_warning(project: Path, source_dir_rel: str) -> Path:
    """Create a warning (not blocked) IWH signal in the designs mirror."""
    iwh_dir = project / ".lexibrary" / "designs" / source_dir_rel
    iwh_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = iwh_dir / ".iwh"

    iwh_data = {
        "author": "test-agent",
        "created": datetime.now().isoformat(),
        "scope": "warning",
    }
    fm_str = yaml.dump(iwh_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    iwh_path.write_text(f"---\n{fm_str}\n---\nSome warning\n", encoding="utf-8")
    return iwh_path


def _load_config(project: Path) -> object:
    """Load a LexibraryConfig for the test project."""
    from lexibrary.config.loader import load_config  # noqa: PLC0415

    return load_config(project)


# ---------------------------------------------------------------------------
# DesignUpdateDecision dataclass tests
# ---------------------------------------------------------------------------


class TestDesignUpdateDecision:
    """Tests for the DesignUpdateDecision frozen dataclass."""

    def test_generate_decision(self) -> None:
        """Generate decision has action='generate' and skip_code=None."""
        d = DesignUpdateDecision(action="generate", reason="No design file exists")
        assert d.action == "generate"
        assert d.reason == "No design file exists"
        assert d.skip_code is None

    def test_skip_decision(self) -> None:
        """Skip decision has action='skip' with skip_code set."""
        d = DesignUpdateDecision(
            action="skip",
            reason="Design file was last updated by agent",
            skip_code="protected",
        )
        assert d.action == "skip"
        assert d.reason == "Design file was last updated by agent"
        assert d.skip_code == "protected"

    def test_frozen(self) -> None:
        """DesignUpdateDecision is frozen (immutable)."""
        import pytest  # noqa: PLC0415

        d = DesignUpdateDecision(action="generate", reason="test")
        with pytest.raises(AttributeError):
            d.action = "skip"  # type: ignore[misc]

    def test_no_cli_dependencies(self) -> None:
        """design.py is importable without pulling in CLI modules."""
        import importlib  # noqa: PLC0415

        mod = importlib.import_module("lexibrary.services.design")
        source = Path(mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
        assert "import typer" not in source
        assert "from lexibrary.cli._output" not in source


# ---------------------------------------------------------------------------
# check_design_update() — scenario tests matching spec
# ---------------------------------------------------------------------------


class TestCheckDesignUpdate:
    """Tests for the check_design_update() pre-flight decision function.

    Each test maps to a scenario in the design-update-service spec.
    """

    # Scenario: No design file exists
    def test_no_design_file(self, tmp_path: Path) -> None:
        """Returns generate when no design file exists."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        source = _write_source(project, "src/main.py", "def hello(): pass\n")

        decision = check_design_update(source, project, config)

        assert decision.action == "generate"
        assert decision.skip_code is None
        assert "No design file" in decision.reason

    # Scenario: IWH blocked signal present
    def test_iwh_blocked(self, tmp_path: Path) -> None:
        """Returns skip with iwh_blocked when blocked signal exists."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        source = _write_source(project, "src/auth/login.py", "# auth\n")
        _create_iwh_blocked(project, "src/auth", body="Concurrent work in progress")

        decision = check_design_update(source, project, config)

        assert decision.action == "skip"
        assert decision.skip_code == "iwh_blocked"
        assert "src/auth" in decision.reason
        assert "Concurrent work" in decision.reason

    # Scenario: IWH blocked overrides force
    def test_iwh_blocked_overrides_force(self, tmp_path: Path) -> None:
        """IWH blocked signal cannot be bypassed with force=True."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        source = _write_source(project, "src/auth/login.py", "# auth\n")
        _create_iwh_blocked(project, "src/auth")

        decision = check_design_update(source, project, config, force=True)

        assert decision.action == "skip"
        assert decision.skip_code == "iwh_blocked"

    # Scenario: Agent-updated file protected
    def test_agent_updated_protected(self, tmp_path: Path) -> None:
        """Returns skip with protected for updated_by=agent without force."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "class Auth: pass\n"
        source = _write_source(project, "src/auth.py", content)
        _create_design_file(project, "src/auth.py", content, updated_by="agent")

        decision = check_design_update(source, project, config)

        assert decision.action == "skip"
        assert decision.skip_code == "protected"
        assert "--force" in decision.reason or "-f" in decision.reason

    # Scenario: Maintainer-updated file protected
    def test_maintainer_updated_protected(self, tmp_path: Path) -> None:
        """Returns skip with protected for updated_by=maintainer without force."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "class Auth: pass\n"
        source = _write_source(project, "src/auth.py", content)
        _create_design_file(project, "src/auth.py", content, updated_by="maintainer")

        decision = check_design_update(source, project, config)

        assert decision.action == "skip"
        assert decision.skip_code == "protected"
        assert "--force" in decision.reason or "-f" in decision.reason

    # Scenario: Unknown updated_by treated as protected
    def test_unknown_updated_by_protected(self, tmp_path: Path) -> None:
        """Returns skip with protected for unrecognized updated_by value."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "x = 1\n"
        source = _write_source(project, "src/util.py", content)
        _create_design_file(project, "src/util.py", content, updated_by="custom-tool")

        decision = check_design_update(source, project, config)

        assert decision.action == "skip"
        assert decision.skip_code == "protected"
        assert "custom-tool" in decision.reason

    # Scenario: Skeleton-fallback always regenerated
    def test_skeleton_fallback_regenerated(self, tmp_path: Path) -> None:
        """Returns generate for updated_by=skeleton-fallback."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "def calc(): ...\n"
        source = _write_source(project, "src/calc.py", content)
        _create_design_file(project, "src/calc.py", content, updated_by="skeleton-fallback")

        decision = check_design_update(source, project, config)

        assert decision.action == "generate"
        assert "skeleton-fallback" in decision.reason

    # Scenario: Bootstrap-quick always regenerated
    def test_bootstrap_quick_regenerated(self, tmp_path: Path) -> None:
        """Returns generate for updated_by=bootstrap-quick."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "import os\n"
        source = _write_source(project, "src/env.py", content)
        _create_design_file(project, "src/env.py", content, updated_by="bootstrap-quick")

        decision = check_design_update(source, project, config)

        assert decision.action == "generate"
        assert "bootstrap-quick" in decision.reason

    # Scenario: Archivist file up to date
    def test_archivist_up_to_date(self, tmp_path: Path) -> None:
        """Returns skip with up_to_date when source hash matches."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "def stable(): ...\n"
        source = _write_source(project, "src/stable.py", content)
        _create_design_file(project, "src/stable.py", content, updated_by="archivist")

        decision = check_design_update(source, project, config)

        assert decision.action == "skip"
        assert decision.skip_code == "up_to_date"

    # Scenario: Archivist file stale
    def test_archivist_stale(self, tmp_path: Path) -> None:
        """Returns generate when source hash no longer matches."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        original = "def old(): ...\n"
        source = _write_source(project, "src/changed.py", "def new(): ...\n")
        _create_design_file(project, "src/changed.py", original, updated_by="archivist")

        decision = check_design_update(source, project, config)

        assert decision.action == "generate"
        assert "changed" in decision.reason.lower()

    # Scenario: Archivist file missing metadata footer
    def test_archivist_missing_footer(self, tmp_path: Path) -> None:
        """Returns generate when archivist file has no metadata footer."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "def check(): ...\n"
        source = _write_source(project, "src/check.py", content)
        _create_design_file(
            project, "src/check.py", content,
            updated_by="archivist",
            include_footer=False,
        )

        decision = check_design_update(source, project, config)

        assert decision.action == "generate"
        assert "no metadata footer" in decision.reason.lower()

    # Scenario: Force overrides protection
    def test_force_overrides_protection(self, tmp_path: Path) -> None:
        """force=True overrides agent protection."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "class Secured: pass\n"
        source = _write_source(project, "src/secured.py", content)
        _create_design_file(project, "src/secured.py", content, updated_by="agent")

        decision = check_design_update(source, project, config, force=True)

        assert decision.action == "generate"

    # Scenario: Force overrides up-to-date
    def test_force_overrides_up_to_date(self, tmp_path: Path) -> None:
        """force=True regenerates even when hashes match."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        content = "def fresh(): ...\n"
        source = _write_source(project, "src/fresh.py", content)
        _create_design_file(project, "src/fresh.py", content, updated_by="archivist")

        decision = check_design_update(source, project, config, force=True)

        assert decision.action == "generate"

    # Additional: IWH warning (non-blocked) does not block
    def test_iwh_warning_does_not_block(self, tmp_path: Path) -> None:
        """Non-blocked IWH signals (warning, incomplete) do not prevent updates."""
        project = _setup_project(tmp_path)
        config = _load_config(project)
        source = _write_source(project, "src/warned/mod.py", "# warned\n")
        _create_iwh_warning(project, "src/warned")

        decision = check_design_update(source, project, config)

        # Should proceed to check design file (which doesn't exist) -> generate
        assert decision.action == "generate"
        assert decision.skip_code is None
