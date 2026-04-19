"""Tests for :func:`fix_lookup_token_budget_exceeded` (curator-4 Group 12).

Covers the five scenarios from ``openspec/changes/curator-4/tasks.md``:

(a) under budget at fix time → ``fixed=False``, ``llm_calls=0``;
(b) kill-switch disabled (default) → ``fixed=False``, ``llm_calls=0``;
(c) condense successful → ``fixed=True``, ``llm_calls=1``, body shorter;
(d) condense did not reduce below budget → ``fixed=False``, ``llm_calls=1``;
(e) BAML raises → ``fixed=False``, ``llm_calls=0``, error message propagated.

Also covers:

* ``FIXERS`` registry entry for ``lookup_token_budget_exceeded`` points
  at the new fixer (Group 12 task 12.3);
* Missing design path → ``fixed=False``, ``llm_calls=0`` (defensive).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import (
    LexibraryConfig,
    ScopeRoot,
    TokenBudgetConfig,
    ValidatorConfig,
)
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.fixes import (
    FIXERS,
    FixResult,
    fix_lookup_token_budget_exceeded,
)
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    *,
    lookup_total_tokens: int = 100,
    fix_condense: bool = True,
    scope_root: str = ".",
) -> LexibraryConfig:
    """Return a :class:`LexibraryConfig` tuned for fixer tests.

    ``fix_condense`` defaults to ``True`` because the helper is intended
    to exercise the condense path; kill-switch-specific tests override
    it to ``False`` to hit the guard.
    """
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=scope_root)],
        token_budgets=TokenBudgetConfig(lookup_total_tokens=lookup_total_tokens),
        validator=ValidatorConfig(fix_lookup_token_budget_condense=fix_condense),
    )


def _write_source(project_root: Path, source_rel: str) -> Path:
    """Write a minimal source file and return its absolute path."""
    abs_path = project_root / source_rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("def noop() -> None:\n    return None\n", encoding="utf-8")
    return abs_path


def _write_design_file(
    project_root: Path,
    source_rel: str,
    *,
    body_size: int = 1,
    updated_by: str = "agent",
) -> Path:
    """Write a valid design file; ``body_size`` scales a preserved section."""
    design_path = project_root / LEXIBRARY_DIR / DESIGNS_DIR / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    bulky = "Long padding paragraph to inflate token count. " * body_size
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Budget fixer fixture.",
            id="DS-BUDGET-FIXER",
            updated_by=updated_by,  # type: ignore[arg-type]
        ),
        summary="Sentinel summary (not serialised).",
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        preserved_sections={"Summary": bulky},
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="stub-source-hash",
            interface_hash="stub-interface-hash",
            design_hash="stub-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _build_condensed_body(
    source_rel: str,
    *,
    marker: str | None = None,
    updated_by: str = "curator",
) -> str:
    """Return a BAML-shaped condensed body (parseable design file).

    When ``marker`` is provided, a one-line preserved section named
    ``"Summary"`` is written with the marker as its body — this gives
    tests a stable on-disk string to assert against.  ``DesignFile.summary``
    itself is a sentinel field that is NOT serialised.
    """
    preserved: dict[str, str] = {}
    if marker is not None:
        preserved["Summary"] = marker

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Budget fixer fixture.",
            id="DS-BUDGET-FIXER",
            updated_by=updated_by,  # type: ignore[arg-type]
        ),
        summary="Sentinel (not serialised).",
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        preserved_sections=preserved,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="baml-source-hash",
            interface_hash="baml-interface-hash",
            design_hash="baml-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    return serialize_design_file(df)


def _make_issue(
    artifact: str,
    *,
    message: str = "Design file uses 400 tokens, exceeding lookup budget of 100",
) -> ValidationIssue:
    return ValidationIssue(
        severity="info",
        check="lookup_token_budget_exceeded",
        message=message,
        artifact=artifact,
    )


# ---------------------------------------------------------------------------
# Registry entry (task 12.3)
# ---------------------------------------------------------------------------


class TestFixerRegistryEntry:
    """``FIXERS`` wires ``lookup_token_budget_exceeded`` → the new helper."""

    def test_fixers_registry_has_entry(self) -> None:
        assert "lookup_token_budget_exceeded" in FIXERS
        assert FIXERS["lookup_token_budget_exceeded"] is fix_lookup_token_budget_exceeded


# ---------------------------------------------------------------------------
# (a) Under budget at fix time
# ---------------------------------------------------------------------------


class TestUnderBudgetAtFixTime:
    """File already fits budget when the fixer runs — no-op with zero LLM calls."""

    def test_fits_budget_returns_fixed_false_zero_llm_calls(self, tmp_path: Path) -> None:
        source_rel = "src/small.py"
        _write_source(tmp_path, source_rel)
        design_path = _write_design_file(tmp_path, source_rel, body_size=1)

        # Generous budget so the file fits comfortably.
        config = _make_config(lookup_total_tokens=10_000, fix_condense=True)
        rel_artifact = str(design_path.relative_to(tmp_path / LEXIBRARY_DIR))
        issue = _make_issue(rel_artifact)

        result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        assert isinstance(result, FixResult)
        assert result.fixed is False
        assert result.llm_calls == 0
        assert result.message == "file fits budget now"


# ---------------------------------------------------------------------------
# (b) Kill-switch disabled
# ---------------------------------------------------------------------------


class TestKillSwitchDisabled:
    """``validator.fix_lookup_token_budget_condense=False`` → no BAML call."""

    def test_kill_switch_off_short_circuits(self, tmp_path: Path) -> None:
        source_rel = "src/big.py"
        _write_source(tmp_path, source_rel)
        design_path = _write_design_file(tmp_path, source_rel, body_size=500)

        config = _make_config(lookup_total_tokens=50, fix_condense=False)
        rel_artifact = str(design_path.relative_to(tmp_path / LEXIBRARY_DIR))
        issue = _make_issue(rel_artifact)

        # Mock condense_file to assert it is NOT invoked.
        with patch("lexibrary.curator.budget.condense_file", new=AsyncMock()) as mock_condense:
            result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        mock_condense.assert_not_called()
        assert result.fixed is False
        assert result.llm_calls == 0
        assert "auto-condense disabled by config" in result.message
        assert "lookup_total_tokens" in result.message

    def test_kill_switch_off_is_default(self, tmp_path: Path) -> None:
        """``ValidatorConfig()`` defaults the flag to ``False``; verify behaviour."""
        source_rel = "src/big.py"
        _write_source(tmp_path, source_rel)
        design_path = _write_design_file(tmp_path, source_rel, body_size=500)

        config = LexibraryConfig(
            scope_roots=[ScopeRoot(path=".")],
            token_budgets=TokenBudgetConfig(lookup_total_tokens=50),
            # Omit validator=; default ValidatorConfig() has fix_* = False.
        )
        rel_artifact = str(design_path.relative_to(tmp_path / LEXIBRARY_DIR))
        issue = _make_issue(rel_artifact)

        result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        assert result.fixed is False
        assert result.llm_calls == 0
        assert "auto-condense disabled by config" in result.message


# ---------------------------------------------------------------------------
# (c) Condense successful
# ---------------------------------------------------------------------------


class TestCondenseSuccess:
    """BAML returns a tight body → ``fixed=True``, ``llm_calls=1``."""

    def test_successful_condense(self, tmp_path: Path) -> None:
        source_rel = "src/big.py"
        _write_source(tmp_path, source_rel)
        design_path = _write_design_file(tmp_path, source_rel, body_size=500)

        # Budget must exceed the minimum-body token count (~135) but sit
        # well below the inflated original (body_size=500 → ~6k+ tokens).
        config = _make_config(lookup_total_tokens=200, fix_condense=True)
        rel_artifact = str(design_path.relative_to(tmp_path / LEXIBRARY_DIR))
        issue = _make_issue(rel_artifact)

        original_len = design_path.stat().st_size

        # Condensed body has no preserved_sections — it's the minimum
        # valid design file body (~135 approximate tokens).
        short_body = _build_condensed_body(source_rel)
        mock_baml = MagicMock()
        mock_baml.condensed_content = short_body
        mock_baml.trimmed_sections = ["Removed verbose Summary"]

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = mock_baml

        with patch("lexibrary.curator.budget.b", mock_client):
            result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        assert result.fixed is True
        assert result.llm_calls == 1
        assert "condensed from" in result.message
        assert "tokens" in result.message

        # Body on disk is actually shorter than the oversized original.
        new_len = design_path.stat().st_size
        assert new_len < original_len


# ---------------------------------------------------------------------------
# (d) Condense did not reduce below budget
# ---------------------------------------------------------------------------


class TestCondenseDidNotReduce:
    """BAML output still exceeds budget — charge the LLM call, fix=False."""

    def test_still_over_budget_after_condense(self, tmp_path: Path) -> None:
        source_rel = "src/big.py"
        _write_source(tmp_path, source_rel)
        design_path = _write_design_file(tmp_path, source_rel, body_size=500)

        # Budget deliberately set BELOW the "condensed" body's own
        # floor (~135 tokens for the minimum parseable design file) so
        # even the shrunk output still trips the post-write recount.
        config = _make_config(lookup_total_tokens=5, fix_condense=True)
        rel_artifact = str(design_path.relative_to(tmp_path / LEXIBRARY_DIR))
        issue = _make_issue(rel_artifact)

        # The condensed body we return is still well above 5 tokens.
        # Use a marker string so we can verify the condensed body is
        # written to disk (via a preserved Summary section, which IS
        # serialised — `DesignFile.summary` itself is a sentinel).
        short_body = _build_condensed_body(source_rel, marker="MARKER-ONDISK")
        mock_baml = MagicMock()
        mock_baml.condensed_content = short_body
        mock_baml.trimmed_sections = []

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = mock_baml

        with patch("lexibrary.curator.budget.b", mock_client):
            result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        assert result.fixed is False
        assert result.llm_calls == 1
        assert result.message == "condensation did not reduce below budget"

        # Despite fixed=False, the condensed body IS left on disk (the
        # write still improved the situation per the fixer contract).
        on_disk = design_path.read_text(encoding="utf-8")
        assert "MARKER-ONDISK" in on_disk


# ---------------------------------------------------------------------------
# (e) BAML raises
# ---------------------------------------------------------------------------


class TestBamlRaises:
    """An exception from BAML surfaces as ``fixed=False``, ``llm_calls=0``."""

    def test_baml_exception_reports_error_zero_llm_calls(self, tmp_path: Path) -> None:
        source_rel = "src/big.py"
        _write_source(tmp_path, source_rel)
        design_path = _write_design_file(tmp_path, source_rel, body_size=500)

        config = _make_config(lookup_total_tokens=100, fix_condense=True)
        rel_artifact = str(design_path.relative_to(tmp_path / LEXIBRARY_DIR))
        issue = _make_issue(rel_artifact)

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.side_effect = RuntimeError("boom from BAML")

        with patch("lexibrary.curator.budget.b", mock_client):
            result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        assert result.fixed is False
        # Conservative charge — parity with ``fix_validation_issue`` "fixer
        # raised" branch (we cannot tell how much of the call completed).
        assert result.llm_calls == 0
        assert "error" in result.message.lower()


# ---------------------------------------------------------------------------
# Defensive: missing design file
# ---------------------------------------------------------------------------


class TestMissingDesignFile:
    """An ``issue.artifact`` with no file on disk → ``fixed=False``."""

    def test_missing_design_reports_zero_llm_calls(self, tmp_path: Path) -> None:
        config = _make_config(lookup_total_tokens=100, fix_condense=True)
        issue = _make_issue("designs/src/nonexistent.py.md")

        result = fix_lookup_token_budget_exceeded(issue, tmp_path, config)

        assert result.fixed is False
        assert result.llm_calls == 0
        assert "design file not found" in result.message
