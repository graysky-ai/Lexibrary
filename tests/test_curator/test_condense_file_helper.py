"""Tests for the standalone ``curator.budget.condense_file`` helper.

Introduced in ``curator-4`` Phase 4 alongside the ``fix_lookup_token_budget_exceeded``
validator fixer.  The helper extracts the per-file BAML call + write
step from the curator budget sub-agent so both agent-session and
non-session callers can reach the same code path.  Mirrors the
``reconcile_deps_only`` extraction pattern introduced by
``curator-freshness``.

Coverage:

* Over-budget file gets condensed; ``before_tokens > after_tokens`` and
  ``updated_by`` flips to ``"archivist"`` (spec scenario: Helper
  condenses single file).
* ``source_hash`` / ``interface_hash`` / ``design_hash`` all recomputed
  from current on-disk state after the rewrite.
* The write is atomic — no stray ``*.tmp`` siblings remain after a
  successful call, and the body on disk round-trips through
  ``parse_design_file``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_metadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.ast_parser import compute_hashes
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.budget import CondenseResult, condense_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_baml_mock(condensed_content: str, trimmed_sections: list[str]) -> MagicMock:
    """Return a MagicMock shaped like BAML's ``CondensedFileOutput``."""
    mock = MagicMock()
    mock.condensed_content = condensed_content
    mock.trimmed_sections = trimmed_sections
    return mock


def _write_source(project_root: Path, source_rel: str, body: str) -> Path:
    """Write a Python source file under ``project_root`` and return its Path."""
    abs_path = project_root / source_rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(body, encoding="utf-8")
    return abs_path


def _write_design_file(
    project_root: Path,
    source_rel: str,
    *,
    body_size: int = 1,
    source_hash: str = "stale-source-hash",
    interface_hash: str = "stale-interface-hash",
    updated_by: str = "agent",
) -> Path:
    """Write a minimal valid design file mirror for ``source_rel``.

    ``body_size`` inflates a preserved section so the fixture can
    simulate an "over-budget" state — the test does not exercise the
    scanner, so the actual token count only matters for
    ``before_tokens``.  The ``summary`` dataclass field is NOT
    serialised by ``serialize_design_file``; the inflation has to live
    in a preserved (non-standard) section to show up on disk.
    """
    design_path = project_root / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    bulky_body = "Long padding paragraph for budget inflation. " * body_size
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Condense fixture.",
            id="DS-CONDENSE-TEST",
            updated_by=updated_by,  # type: ignore[arg-type]
        ),
        summary="Sentinel summary (not serialised).",
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        preserved_sections={"Summary": bulky_body},
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=interface_hash,
            design_hash="stale-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _build_condensed_body(source_rel: str, *, summary: str = "Condensed.") -> str:
    """Return a serialised design-file body shaped like BAML's successful output."""
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Condense fixture.",
            id="DS-CONDENSE-TEST",
            updated_by="curator",  # helper flips to archivist on write
        ),
        summary=summary,
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            # BAML-produced hashes deliberately differ from the caller's;
            # the helper MUST overwrite them with fresh values from the
            # current source on disk.
            source_hash="baml-source-hash",
            interface_hash="baml-interface-hash",
            design_hash="baml-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    return serialize_design_file(df)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCondenseFileOverBudget:
    """Spec scenario: Helper condenses single file (before_tokens > after_tokens)."""

    def test_writes_condensed_body_and_flips_authorship(self, tmp_path: Path) -> None:
        source_rel = "src/mod.py"
        _write_source(tmp_path, source_rel, "def noop() -> None:\n    return None\n")
        design_path = _write_design_file(tmp_path, source_rel, body_size=500)

        short_body = _build_condensed_body(source_rel, summary="Tight summary.")
        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_mock(
            condensed_content=short_body,
            trimmed_sections=["Removed verbose examples"],
        )

        config = LexibraryConfig()
        result = asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

        assert isinstance(result, CondenseResult)
        # Over-budget → condensed body is smaller than the original.
        assert result.before_tokens > result.after_tokens
        assert result.trimmed_sections == ["Removed verbose examples"]

        # Post-write: authorship flipped to archivist (curator-freshness
        # precedent for non-agent-session helper writes).
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "archivist"


class TestCondenseFileHashRefresh:
    """Hashes (source_hash, interface_hash, design_hash) all get recomputed."""

    def test_refreshes_source_and_interface_hashes_from_source(self, tmp_path: Path) -> None:
        source_rel = "src/mod.py"
        source_abs = _write_source(
            tmp_path,
            source_rel,
            "def noop() -> None:\n    return None\n",
        )
        design_path = _write_design_file(
            tmp_path,
            source_rel,
            source_hash="stale-source-hash",
            interface_hash="stale-interface-hash",
        )

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_mock(
            condensed_content=_build_condensed_body(source_rel),
            trimmed_sections=[],
        )

        config = LexibraryConfig()
        asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

        # Hashes on disk match `compute_hashes` against the source file.
        expected_source, expected_interface = compute_hashes(source_abs)
        metadata = parse_design_file_metadata(design_path)
        assert metadata is not None
        assert metadata.source_hash == expected_source
        assert metadata.interface_hash == expected_interface
        # Neither should equal the stale/BAML-provided values.
        assert metadata.source_hash != "stale-source-hash"
        assert metadata.source_hash != "baml-source-hash"

    def test_recomputes_design_hash_from_rendered_body(self, tmp_path: Path) -> None:
        source_rel = "src/mod.py"
        _write_source(tmp_path, source_rel, "def noop() -> None:\n    return None\n")
        design_path = _write_design_file(tmp_path, source_rel)

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_mock(
            condensed_content=_build_condensed_body(source_rel),
            trimmed_sections=[],
        )

        config = LexibraryConfig()
        asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

        metadata = parse_design_file_metadata(design_path)
        assert metadata is not None
        assert metadata.design_hash is not None
        # design_hash is a fresh SHA-256 of the rendered body — it must
        # NOT be the stale sentinel written by the fixture, and it must
        # NOT be the BAML-provided sentinel either (the serializer
        # recomputes it from the actual on-disk body).
        assert metadata.design_hash != "stale-design-hash"
        assert metadata.design_hash != "baml-design-hash"
        # SHA-256 hex digest length.
        assert len(metadata.design_hash) == 64


class TestCondenseFileAtomicWrite:
    """Atomic write leaves no stray temp files and preserves readability."""

    def test_atomic_write_no_leftover_temp_and_body_parses(self, tmp_path: Path) -> None:
        source_rel = "src/mod.py"
        _write_source(tmp_path, source_rel, "def noop() -> None:\n    return None\n")
        design_path = _write_design_file(tmp_path, source_rel)

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_mock(
            condensed_content=_build_condensed_body(source_rel),
            trimmed_sections=["trimmed example"],
        )

        config = LexibraryConfig()
        asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

        # No *.tmp siblings remain in the designs directory.
        leftovers = [
            p.name
            for p in design_path.parent.iterdir()
            if p.name.endswith(".tmp") or ".condense.tmp" in p.name
        ]
        assert leftovers == []

        # The written body is itself parseable — atomic replace produced
        # a complete valid file, not a truncated one.
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "archivist"
