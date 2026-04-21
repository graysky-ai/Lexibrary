"""Tests for archivist complexity_warning suppression (§2.4c, Group 15).

Verifies that the archivist pipeline forces ``DesignFile.complexity_warning``
to ``None`` when the source module is:

- an aggregator (per :func:`classify_aggregator`'s three gates), OR
- constants-only (per :func:`is_constants_only`).

For every other module shape, the pipeline SHALL pass the LLM's
``complexity_warning`` value through unchanged so the Group 16 post-filter
can apply its own heuristics.

Contract reference: ``aggregator-design-rendering`` spec —
"Complexity Warning suppression for aggregators and constants-only modules".
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
# Suppression path — aggregator + constants-only both force None
# ---------------------------------------------------------------------------


class TestComplexityWarningSuppression:
    """Skeleton gate forces ``complexity_warning`` to ``None`` for modules with
    no top-level behaviour to warn about (aggregators and constants-only)."""

    @pytest.mark.asyncio()
    async def test_aggregator_suppresses_complexity_warning(self, tmp_path: Path) -> None:
        """Aggregator module → LLM's ``complexity_warning`` is discarded."""
        source_rel = "src/pkg/__init__.py"
        # Pure aggregator: re-exports only, passes all three gates.
        content = 'from .a import X\nfrom .b import Y, Z\n__all__ = ["X", "Y", "Z"]\n'
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        # LLM tried to emit a warning, but the skeleton gate should drop it.
        archivist = _mock_archivist("Be careful — aggregator modules affect import ordering.")

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.complexity_warning is None

    @pytest.mark.asyncio()
    async def test_constants_only_suppresses_complexity_warning(self, tmp_path: Path) -> None:
        """Constants-only module → LLM's ``complexity_warning`` is discarded."""
        source_rel = "src/pkg/constants.py"
        # Only top-level value assignments — no def, no class.
        content = (
            "MAX_RETRIES = 5\nDEFAULT_NAME: str = 'lexibrary'\nTHRESHOLDS: list[int] = [1, 2, 3]\n"
        )
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        archivist = _mock_archivist(
            "Watch out for the THRESHOLDS constant when tuning retry logic."
        )

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.complexity_warning is None

    @pytest.mark.asyncio()
    async def test_normal_module_preserves_complexity_warning(self, tmp_path: Path) -> None:
        """Regular module (has def/class and isn't an aggregator) → pipeline
        passes the LLM's ``complexity_warning`` through unchanged."""
        source_rel = "src/pkg/worker.py"
        content = (
            "import time\n"
            "\n"
            "def run(times: int) -> int:\n"
            "    total = 0\n"
            "    for i in range(times):\n"
            "        total += i\n"
            "        time.sleep(0.001)\n"
            "    return total\n"
            "\n"
            "class Worker:\n"
            "    def __init__(self, name: str) -> None:\n"
            "        self.name = name\n"
        )
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        archivist = _mock_archivist(
            "run() sleeps between iterations — avoid calling from an async event loop."
        )

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        # Pipeline preserves the LLM's value — Group 16 post-filter is a
        # separate gate and is not exercised here. We assert the LLM's
        # string appears in the parsed value rather than demanding exact
        # equality: the round-trip parser currently folds the metadata
        # footer into the trailing section when it's the last one emitted
        # (pre-existing behaviour; out of Group 15 scope). The essential
        # contract is that the suppression gate did NOT fire and the
        # warning survives into the on-disk design file.
        assert parsed.complexity_warning is not None
        assert (
            "run() sleeps between iterations — avoid calling from an async event loop."
            in parsed.complexity_warning
        )

    @pytest.mark.asyncio()
    async def test_normal_module_none_stays_none(self, tmp_path: Path) -> None:
        """Regular module with LLM returning ``None`` stays ``None`` — the
        suppression gate does not synthesise a warning."""
        source_rel = "src/pkg/worker.py"
        content = "def run() -> int:\n    return 1\n\nclass Worker:\n    pass\n"
        source = _make_source_file(tmp_path, source_rel, content)
        config = _make_config()
        archivist = _mock_archivist(None)

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.complexity_warning is None
