"""Regression tests for parse-tree sharing across extractors.

Phase 2 group 2 refactors each language parser so ``tree_sitter.Parser.parse``
is invoked exactly once per source file per ``build_symbol_graph`` run. The
actual tree-cache wiring landed in group 8 (``symbolgraph/builder.py`` full
rebuild body), and this module's main regression test is now expected to
pass: the builder parses each source file once into a shared
``tree_cache`` and the Python resolver primes its import cache from those
already-parsed trees instead of re-reading the file.

Note on monkeypatching: ``tree_sitter.Parser.parse`` is a C-extension slot
and read-only, so ``monkeypatch.setattr(parser, "parse", ...)`` would raise
``AttributeError``. Instead the test wraps the registry's cached Parser
instance in a tiny proxy object that delegates ``parse`` through a
call-counting wrapper, and injects that proxy into ``_parser_cache`` so all
downstream callers (the refactored parser entry points, the builder) see
the wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from lexibrary.ast_parser import registry
from lexibrary.ast_parser.registry import clear_caches, get_parser
from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.builder import build_symbol_graph


@dataclass
class _CountingParserProxy:
    """Thin wrapper around a tree-sitter ``Parser`` that counts parse calls.

    ``tree_sitter.Parser.parse`` is a read-only C-extension slot, so we can
    not directly monkeypatch the attribute. The proxy delegates every
    attribute access to the wrapped parser except ``parse``, which is
    intercepted and routed through :meth:`parse`.
    """

    inner: Any
    call_count: int = field(default=0)

    def parse(self, *args: Any, **kwargs: Any) -> Any:
        self.call_count += 1
        return self.inner.parse(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _make_project(tmp_path: Path) -> Path:
    """Create a tiny 3-file Python project under ``tmp_path``.

    Each file contains a top-level function that calls another function in a
    sibling module, so any future call-site extractor walking the trees has
    real content to work with.
    """
    (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True, exist_ok=True)

    (src / "__init__.py").write_text("\n", encoding="utf-8")
    (src / "alpha.py").write_text(
        "def alpha_fn() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    (src / "beta.py").write_text(
        "from pkg.alpha import alpha_fn\n\ndef beta_fn() -> int:\n    return alpha_fn() + 1\n",
        encoding="utf-8",
    )
    (src / "gamma.py").write_text(
        "from pkg.beta import beta_fn\n\ndef gamma_fn() -> int:\n    return beta_fn() + 1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_parse_tree_shared_not_duplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each source file SHALL be parsed exactly once per build run.

    Wraps the cached Python ``tree_sitter.Parser`` in a proxy whose
    ``parse`` method counts invocations, runs ``build_symbol_graph`` against
    a 4-file project (``__init__.py`` + three modules), and asserts that
    the proxy's ``parse`` was called exactly four times — once per source
    file. Any extra parse call indicates the builder and the Python
    resolver are not sharing a single tree per file.
    """
    # Reset the registry's module-level caches so the proxy installed below
    # cannot leak between tests.
    clear_caches()

    project_root = _make_project(tmp_path)

    # Warm the Python parser cache, then wrap the cached instance in a
    # counting proxy so every downstream ``get_parser(".py")`` sees the
    # same wrapper.
    inner = get_parser(".py")
    if inner is None:
        pytest.skip("tree-sitter Python grammar not available")

    proxy = _CountingParserProxy(inner=inner)
    monkeypatch.setitem(registry._parser_cache, "python", proxy)

    build_symbol_graph(project_root, LexibraryConfig())

    # Four files in the fixture: __init__.py, alpha.py, beta.py, gamma.py.
    # The shared tree cache should cap the parse count at exactly one per
    # file; any duplicate parse (e.g. a re-parse inside the Python resolver
    # because the import cache was not primed) would push the count higher.
    assert proxy.call_count == 4, (
        f"Expected Parser.parse to be invoked exactly 4 times (once per "
        f"source file), got {proxy.call_count}."
    )
