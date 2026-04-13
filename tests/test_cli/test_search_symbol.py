"""Tests for ``lexi search --type symbol`` and the symbol-search mixed mode.

Covers the symbol-graph search branch added in symbol-graph-2 group 13:

1. ``test_search_symbol_basic`` — happy path, a known qualified name in
   the seeded corpus turns up at least one result.
2. ``test_search_symbol_no_match`` — exit 0 with ``No results`` when the
   query matches nothing in the symbol graph.
3. ``test_search_symbol_rejects_tag_flag`` — exit 1 when ``--tag`` is
   combined with ``--type symbol``, plus the other stack-only flags.
4. ``test_search_symbol_json_format`` — ``--format json`` emits records
   with ``type="symbol"`` and the symbol-specific fields.

Also covers the ``symbol-search`` change (Group 7 — CLI mixed-mode and
``--symbol-limit`` flag):

5. ``test_search_default_mode_shows_symbols`` — in mixed mode (no
   ``--type``), symbols appear alongside artefact hits for both
   markdown and JSON output modes.
6. ``test_search_symbol_limit_flag`` — ``--symbol-limit N`` caps the
   number of symbols included in mixed-mode output.
7. ``test_search_symbol_limit_ignored_with_type_symbol`` —
   ``--symbol-limit`` has no effect when ``--type symbol`` is set;
   ``--limit`` governs the result cap instead.
8. ``test_search_tag_filter_omits_symbols_in_mixed_mode`` — adding
   ``--tag`` to a mixed-mode query suppresses symbols entirely
   (neither the Markdown ``### Symbols`` section nor JSON
   ``{"type": "symbol"}`` entries appear).

Uses the shared :func:`tests.test_symbolgraph.conftest.seed_phase2_fixture`
helper so the tests share the same two-file corpus as
``tests/test_services/test_symbols.py`` and ``tests/test_cli/test_trace.py``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from lexibrary.cli.lexi_app import lexi_app
from tests.test_symbolgraph.conftest import (
    make_linkgraph,
    make_project,
    seed_phase2_fixture,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers for mixed-mode tests (Group 7)
# ---------------------------------------------------------------------------


def _seed_extra_symbols(
    project_root: Path,
    names: list[str],
    *,
    file_rel_path: str = "src/extra.py",
) -> list[int]:
    """Append extra symbols to the already-seeded ``symbols.db``.

    The phase-2 fixture already creates a single source file and four
    symbols (``foo``, ``bar``, ``baz``, ``meth``). For the mixed-mode
    limit tests we need several symbols matching the same query ("render"),
    so this helper inserts additional rows into the existing ``files``
    and ``symbols`` tables using the same schema seeded by the fixture.

    Returns the list of new symbol ids in seeding order.
    """
    # Write a placeholder source file so ``files.last_hash`` has a target
    # (staleness checks tolerate the mismatch in these tests because none
    # of the assertions touch the stale-warning path).
    src_abs = project_root / file_rel_path
    src_abs.parent.mkdir(parents=True, exist_ok=True)
    src_abs.write_text("# extra fixture\n", encoding="utf-8")

    db_path = project_root / ".lexibrary" / "symbols.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            (file_rel_path, "python", "0" * 64),
        )
        file_id = int(cur.lastrowid or 0)

        symbol_ids: list[int] = []
        for idx, name in enumerate(names, start=1):
            line = idx * 10
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    file_id,
                    name,
                    f"extra.{name}",
                    "function",
                    line,
                    line + 2,
                    "public",
                ),
            )
            symbol_ids.append(int(cur.lastrowid or 0))

        conn.commit()
    finally:
        conn.close()

    return symbol_ids


def _create_concept_file(
    project: Path,
    title: str,
    *,
    concept_id: str = "CN-001",
    tags: list[str] | None = None,
    summary: str = "",
) -> Path:
    """Create a minimal concept file in ``.lexibrary/concepts/``.

    The concept index indexes the frontmatter ``title`` and body; the
    mixed-mode tests use this to prove that an artefact hit appears
    alongside the symbol hits returned by the symbol graph.
    """
    concepts_dir = project / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    slug = title.replace(" ", "")
    path = concepts_dir / f"{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": concept_id,
        "aliases": [],
        "tags": tags or [],
        "status": "active",
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    body = summary if summary else f"Summary of {title}."
    path.write_text(f"---\n{fm_str}\n---\n{body}\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# (1) Happy path — a known symbol is found
# ---------------------------------------------------------------------------


def test_search_symbol_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A known symbol name exits 0 and appears in the rendered output."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(lexi_app, ["search", "bar", "--type", "symbol"])

    assert result.exit_code == 0, result.output
    # The seeded corpus has ``a.bar`` as a function — expect the qualified
    # name in the Symbols table.
    assert "a.bar" in result.output
    # The default markdown renderer prepends a ``### Symbols`` header when
    # ``symbol_results`` is non-empty.
    assert "Symbols" in result.output


# ---------------------------------------------------------------------------
# (2) No match — empty results, exit 0
# ---------------------------------------------------------------------------


def test_search_symbol_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown symbol name exits 0 and emits a no-results message."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        ["search", "zzzz_not_a_symbol", "--type", "symbol"],
    )

    assert result.exit_code == 0, result.output
    # The CLI search handler emits ``No results found`` when
    # ``results.has_results()`` is False. Exact wording matches the
    # existing ``--type concept`` empty-result path.
    assert "No results" in result.output


# ---------------------------------------------------------------------------
# (3) --tag is rejected with --type symbol — exit 1
# ---------------------------------------------------------------------------


def test_search_symbol_rejects_tag_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--tag`` combined with ``--type symbol`` exits 1 with a clear error."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        ["search", "bar", "--type", "symbol", "--tag", "security"],
    )

    assert result.exit_code == 1, result.output
    assert "--tag" in result.output
    assert "--type symbol" in result.output


def test_search_symbol_rejects_concept_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--concept`` combined with ``--type symbol`` exits 1."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        ["search", "bar", "--type", "symbol", "--concept", "auth"],
    )

    assert result.exit_code == 1, result.output
    assert "--concept" in result.output
    assert "--type symbol" in result.output


def test_search_symbol_rejects_resolution_type_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--resolution-type`` combined with ``--type symbol`` exits 1."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        [
            "search",
            "bar",
            "--type",
            "symbol",
            "--resolution-type",
            "answered",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "--resolution-type" in result.output
    assert "--type symbol" in result.output


def test_search_symbol_rejects_include_stale_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--include-stale`` combined with ``--type symbol`` exits 1."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        ["search", "bar", "--type", "symbol", "--include-stale"],
    )

    assert result.exit_code == 1, result.output
    assert "--include-stale" in result.output
    assert "--type symbol" in result.output


# ---------------------------------------------------------------------------
# (4) JSON output format — records include symbol-specific fields
# ---------------------------------------------------------------------------


def test_search_symbol_json_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--format json`` emits a JSON array whose symbol entries carry
    ``type='symbol'`` and the expected fields (``name``, ``qualified_name``,
    ``file``, ``line``)."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        ["--format", "json", "search", "bar", "--type", "symbol"],
    )

    assert result.exit_code == 0, result.output

    # The JSON renderer emits either a bare array of records or, when
    # suggestions are non-empty, an object with a ``results`` array. The
    # symbol search path never produces suggestions, so expect a list.
    payload = json.loads(result.output)
    assert isinstance(payload, list)

    symbol_records = [record for record in payload if record.get("type") == "symbol"]
    assert len(symbol_records) >= 1

    first = symbol_records[0]
    assert first["type"] == "symbol"
    assert "name" in first
    assert "qualified_name" in first
    assert "file" in first
    assert "line" in first
    # The seeded fixture has ``a.bar`` at ``src/a.py``.
    qualified_names = {record["qualified_name"] for record in symbol_records}
    assert "a.bar" in qualified_names


# ---------------------------------------------------------------------------
# (5) Mixed mode — default search surfaces symbols alongside artefact hits
# ---------------------------------------------------------------------------


def test_search_default_mode_shows_symbols(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``--type``, ``lexi search`` surfaces both artefact hits and
    symbol hits in the default (markdown) renderer and in JSON output.

    The seeded corpus ships a ``render_results`` symbol alongside a
    concept titled ``RenderPipeline``; a free-text query for ``render``
    MUST return both in mixed mode.
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    _seed_extra_symbols(project, ["render_results"])
    _create_concept_file(
        project,
        title="RenderPipeline",
        concept_id="CN-100",
        summary="Concept for rendering search results.",
    )
    monkeypatch.chdir(project)

    # --- Markdown output -----------------------------------------------------
    md_result = runner.invoke(lexi_app, ["search", "render"])
    assert md_result.exit_code == 0, md_result.output
    # Symbols section appears with the seeded symbol.
    assert "### Symbols" in md_result.output
    assert "extra.render_results" in md_result.output
    # The concept artefact also appears via the Concepts table.
    assert "## Concepts" in md_result.output
    assert "RenderPipeline" in md_result.output

    # --- JSON output ---------------------------------------------------------
    json_result = runner.invoke(lexi_app, ["--format", "json", "search", "render"])
    assert json_result.exit_code == 0, json_result.output

    payload = json.loads(json_result.output)
    # ``_render_json`` returns a bare list when suggestions are empty
    # and an object with ``results`` / ``suggestions`` otherwise.
    records = payload["results"] if isinstance(payload, dict) else payload

    symbol_records = [r for r in records if r.get("type") == "symbol"]
    concept_records = [r for r in records if r.get("type") == "concept"]

    assert len(symbol_records) >= 1, records
    assert any(r["qualified_name"] == "extra.render_results" for r in symbol_records)
    assert len(concept_records) >= 1, records
    assert any(r.get("name") == "RenderPipeline" for r in concept_records)


# ---------------------------------------------------------------------------
# (6) --symbol-limit caps mixed-mode symbol output
# ---------------------------------------------------------------------------


def test_search_symbol_limit_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--symbol-limit 1`` caps the symbol section to a single row even
    when the symbol graph has five matching symbols.

    The cap is enforced at the service layer via
    ``SymbolQueryService.search_symbols(limit=...)``, so the CLI output
    MUST contain at most one row matching the seeded names.
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    seeded_names = [
        "render_results",
        "render_plain",
        "render_json",
        "render_markdown",
        "render_summary",
    ]
    _seed_extra_symbols(project, seeded_names)
    monkeypatch.chdir(project)

    result = runner.invoke(lexi_app, ["search", "render", "--symbol-limit", "1"])
    assert result.exit_code == 0, result.output
    # At most one of the seeded names should appear in the output.
    matches = [name for name in seeded_names if f"extra.{name}" in result.output]
    assert len(matches) == 1, (
        f"expected exactly one symbol in output (--symbol-limit 1), found {len(matches)}: {matches}"
    )


# ---------------------------------------------------------------------------
# (7) --symbol-limit ignored with --type symbol (which honours --limit)
# ---------------------------------------------------------------------------


def test_search_symbol_limit_ignored_with_type_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ``--type symbol --symbol-limit 3 --limit 20``, ``--limit`` drives
    the result cap (not ``--symbol-limit``): all five seeded symbols appear.

    The ``--type symbol`` early-route in ``unified_search`` routes through
    ``_symbol_search`` which reads ``limit`` (not ``symbol_limit``); this
    test guards that the CLI threads ``--limit`` through and that
    ``--symbol-limit`` is ignored in the symbol-only branch.
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    seeded_names = [
        "render_results",
        "render_plain",
        "render_json",
        "render_markdown",
        "render_summary",
    ]
    _seed_extra_symbols(project, seeded_names)
    monkeypatch.chdir(project)

    result = runner.invoke(
        lexi_app,
        [
            "search",
            "render",
            "--type",
            "symbol",
            "--symbol-limit",
            "3",
            "--limit",
            "20",
        ],
    )
    assert result.exit_code == 0, result.output

    # All five seeded symbols should appear — ``--limit 20`` governs the
    # cap in the ``--type symbol`` branch, and 5 ≤ 20.
    matches = [name for name in seeded_names if f"extra.{name}" in result.output]
    assert len(matches) == 5, (
        f"expected all 5 symbols in --type symbol output (--limit 20 governs), "
        f"found {len(matches)}: {matches}"
    )


# ---------------------------------------------------------------------------
# (8) Tag filter suppresses symbols in mixed mode
# ---------------------------------------------------------------------------


def test_search_tag_filter_omits_symbols_in_mixed_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mixed-mode search with ``--tag`` MUST NOT include symbols, even if
    the symbol graph has a matching symbol.

    ``_augment_with_symbols`` is a no-op whenever ``resolved_tags`` is
    non-empty, so both the Markdown ``### Symbols`` header and the JSON
    ``{"type": "symbol", ...}`` records MUST be absent.

    The test does not require an artefact to surface under ``--tag`` —
    the contract under test is solely that symbols are suppressed. When
    no artefact matches the tag, the CLI emits ``No results found`` for
    both formats; that output still satisfies the "no symbols" invariant
    and is handled explicitly below.
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    _seed_extra_symbols(project, ["render_results"])
    monkeypatch.chdir(project)

    # --- Markdown output -----------------------------------------------------
    md_result = runner.invoke(lexi_app, ["search", "render", "--tag", "bar"])
    assert md_result.exit_code == 0, md_result.output
    assert "### Symbols" not in md_result.output
    # The seeded symbol name must not appear in the Markdown output.
    assert "extra.render_results" not in md_result.output

    # --- JSON output ---------------------------------------------------------
    json_result = runner.invoke(
        lexi_app,
        ["--format", "json", "search", "render", "--tag", "bar"],
    )
    assert json_result.exit_code == 0, json_result.output

    output = json_result.output
    # Under no-artefact-match, the CLI short-circuits with a "No results"
    # warning before rendering. In either case the invariant holds:
    # there must be no ``{"type": "symbol", ...}`` record in the output.
    if output.strip().startswith(("[", "{")):
        payload = json.loads(output)
        records = payload["results"] if isinstance(payload, dict) else payload
        symbol_records = [r for r in records if r.get("type") == "symbol"]
        assert symbol_records == [], (
            f"expected no symbol records under --tag in mixed mode, got: {symbol_records}"
        )
    else:
        # Not JSON — the CLI emitted a "No results" warning. Check the raw
        # text for the absence of any symbol marker (name or ``type: symbol``).
        assert '"type": "symbol"' not in output
        assert "extra.render_results" not in output
