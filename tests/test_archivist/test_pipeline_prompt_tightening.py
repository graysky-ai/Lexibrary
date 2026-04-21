"""Tests for the Group 17 prompt-tightening of ``complexity_warning``.

Verifies that when the LLM obeys the tightened §2.4(a) prompt
(``baml_src/archivist_design_file.baml``), the pipeline behaves correctly
end-to-end:

- If the LLM returns ``None`` because the module has no load-bearing
  invariant (the post-prompt-tightening behaviour on modules that previously
  attracted generic-hedge warnings), the Group 16 post-filter SHALL NOT
  synthesise a new warning. ``None`` stays ``None``.
- If the LLM returns a citation-rich warning on a complex module (naming a
  specific symbol, version string, file path, or CLI flag), the Group 16
  post-filter SHALL NOT drop it. The warning survives through to the parsed
  design file.

These cases complement the Group 15 suppression tests in
``test_pipeline_complexity_suppression.py`` (which covers aggregator /
constants-only modules where the pipeline zeroes the warning regardless of
LLM output) and the Group 16 unit-level filter tests: this module drives the
full pipeline with realistic LLM outputs under the new prompt.

Contract reference: ``archivist-baml`` spec —
"complexity_warning requires specific citation" + "complexity_warning
load-bearing emitted".
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import update_file
from lexibrary.archivist.service import ArchivistService, DesignFileResult
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(tmp_path: Path, rel: str, content: str) -> Path:
    """Create a source file at ``tmp_path / rel`` with ``content``."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_config() -> LexibraryConfig:
    """Default single-root config rooted at ``.`` with a generous token budget."""
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=".")],
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _mock_archivist(complexity_warning: str | None) -> ArchivistService:
    """Mock ArchivistService whose LLM output carries ``complexity_warning``."""
    output = DesignFileOutput(
        summary="Test module.",
        interface_contract="def foo(): ...",
        dependencies=[],
        tests=None,
        complexity_warning=complexity_warning,
        wikilinks=[],
        tags=[],
    )
    result = DesignFileResult(
        source_path="mock",
        design_file_output=output,
        error=False,
        error_message=None,
    )
    service = MagicMock(spec=ArchivistService)
    service.generate_design_file = AsyncMock(return_value=result)
    return service


# ---------------------------------------------------------------------------
# Prompt-tightening behaviour tests
# ---------------------------------------------------------------------------


class TestPromptTightening:
    """Verify that the Group 16 post-filter respects the LLM's decisions
    under the Group 17 tightened prompt."""

    @pytest.mark.asyncio()
    async def test_llm_returns_none_for_generic_hedge_module(self, tmp_path: Path) -> None:
        """LLM (obeying the new prompt) returns ``None`` on a module that
        previously attracted a generic-hedge warning. The filter SHALL NOT
        synthesise or resurrect a warning — ``None`` stays ``None``."""
        # Module shape: a thin Pydantic model file. It is NOT an aggregator
        # (fails the Group 15 suppression gate) and NOT constants-only (has a
        # class def), so the Group 15 path does not fire. The post-tightening
        # LLM sees nothing load-bearing and returns ``None`` per §2.4(a).
        source_rel = "src/pkg/thin_model.py"
        content = (
            "from pydantic import BaseModel\n"
            "\n"
            "class ThinModel(BaseModel):\n"
            "    name: str\n"
            "    count: int = 0\n"
        )
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        # LLM obeys the new prompt: no specific invariant → return None.
        archivist = _mock_archivist(None)

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        # Group 16 filter never synthesises — ``None`` stays ``None``.
        assert parsed.complexity_warning is None

    @pytest.mark.asyncio()
    async def test_llm_returns_citation_rich_warning_on_complex_module(
        self, tmp_path: Path
    ) -> None:
        """LLM (obeying the new prompt) returns a citation-rich warning on a
        complex module. The Group 16 post-filter SHALL NOT drop it — the
        warning survives through to the parsed design file."""
        source_rel = "src/pkg/complex.py"
        # A module with real behaviour — has functions and a class. The
        # skeleton will contain ``run_transaction`` so the filter's
        # ``_has_code_identifier`` path would also hold, but we deliberately
        # choose warning text that exercises MULTIPLE signal-marker paths:
        # dotted identifier (``sqlite3.connect``), SQL keyword (``WAL``),
        # file path (``.lexibrary/index.db``), CLI flag (``--force``), and
        # version string (``Python 3.11+``). Any one of these would keep the
        # warning; together they assert the filter is permissive in the
        # presence of the new prompt's citation requirement.
        content = (
            "from __future__ import annotations\n"
            "\n"
            "import sqlite3\n"
            "\n"
            "def run_transaction(db_path: str) -> None:\n"
            "    conn = sqlite3.connect(db_path)\n"
            "    conn.execute('PRAGMA journal_mode = WAL')\n"
            "    conn.commit()\n"
            "\n"
            "class TxnManager:\n"
            "    def __init__(self, db_path: str) -> None:\n"
            "        self.db_path = db_path\n"
        )
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        citation_rich_warning = (
            "run_transaction() opens sqlite3.connect(...) directly and sets "
            "PRAGMA journal_mode = WAL; callers MUST not concurrently open the "
            "same .lexibrary/index.db in read-write mode from another process. "
            "Python 3.11+ is required because of the sqlite3.Connection.execute "
            "return-type change. Running with --force from the CLI reinitialises "
            "the WAL file."
        )
        archivist = _mock_archivist(citation_rich_warning)

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        # The citation-rich warning survives the Group 16 post-filter.
        assert parsed.complexity_warning is not None
        # Assert every signal-marker substring we deliberately placed is
        # still present — i.e. the filter preserved the FULL warning, not
        # just a subset of clauses.
        for marker in (
            "run_transaction",
            "sqlite3.connect",
            "WAL",
            ".lexibrary/index.db",
            "Python 3.11+",
            "--force",
        ):
            assert marker in parsed.complexity_warning, (
                f"Signal marker {marker!r} was dropped by the post-filter"
            )

    @pytest.mark.asyncio()
    async def test_llm_returns_short_citation_rich_warning_is_preserved(
        self, tmp_path: Path
    ) -> None:
        """A SHORT citation-rich warning (below the 500-char length gate) is
        still preserved because a signal marker fires. This is the key
        interaction between the tightened prompt (which may emit short,
        specific warnings) and the Group 16 length threshold: the filter
        uses OR semantics — long-enough OR any signal marker → keep."""
        source_rel = "src/pkg/short_complex.py"
        content = (
            "def worker(times: int) -> int:\n"
            "    total = 0\n"
            "    for i in range(times):\n"
            "        total += i\n"
            "    return total\n"
        )
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        # Well under 500 chars, but cites a named symbol AND a CLI flag.
        short_warning = "worker() is unaffected by the --unlimited flag."
        assert len(short_warning) < 500
        archivist = _mock_archivist(short_warning)

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        # Short but citation-rich → keeps through the filter.
        assert parsed.complexity_warning is not None
        assert "worker()" in parsed.complexity_warning
        assert "--unlimited" in parsed.complexity_warning
