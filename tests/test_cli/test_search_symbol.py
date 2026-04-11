"""Tests for ``lexi search --type symbol``.

Covers the symbol-graph search branch added in symbol-graph-2 group 13:

1. ``test_search_symbol_basic`` — happy path, a known qualified name in
   the seeded corpus turns up at least one result.
2. ``test_search_symbol_no_match`` — exit 0 with ``No results`` when the
   query matches nothing in the symbol graph.
3. ``test_search_symbol_rejects_tag_flag`` — exit 1 when ``--tag`` is
   combined with ``--type symbol``, plus the other stack-only flags.
4. ``test_search_symbol_json_format`` — ``--format json`` emits records
   with ``type="symbol"`` and the symbol-specific fields.

Uses the shared :func:`tests.test_symbolgraph.conftest.seed_phase2_fixture`
helper so the tests share the same two-file corpus as
``tests/test_services/test_symbols.py`` and ``tests/test_cli/test_trace.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lexibrary.cli.lexi_app import lexi_app
from tests.test_symbolgraph.conftest import (
    make_linkgraph,
    make_project,
    seed_phase2_fixture,
)

runner = CliRunner()


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
