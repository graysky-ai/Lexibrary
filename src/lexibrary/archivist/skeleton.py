"""Shared skeleton design file generation.

Extracts the core skeleton generation logic from ``bootstrap.py`` into a
reusable helper that both ``bootstrap_quick`` and the size-gate / truncation
fallback paths can call.

Also exposes the aggregator detector (:func:`classify_aggregator`) used by
the archivist pipeline to route re-export-only modules through a compacted
``## Re-exports`` rendering path instead of the default
``## Interface Contract`` path, and :func:`is_constants_only` used by the
pipeline to suppress the LLM's ``complexity_warning`` output for modules
that have nothing but top-level value assignments.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from lexibrary.archivist.dependency_extractor import extract_dependencies
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.ids import next_design_id
from lexibrary.ast_parser import compute_hashes, parse_interface, render_skeleton
from lexibrary.ast_parser.registry import get_parser
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR

UpdatedByLiteral = Literal[
    "archivist", "agent", "bootstrap-quick", "skeleton-fallback", "maintainer"
]

logger = logging.getLogger(__name__)

_GENERATOR_ID = "lexibrary-v2"

# Re-export-gate threshold: ratio of re-exported top-level named symbols to
# total top-level named symbols. See SHARED_BLOCK_D in the design-cleanup
# tasks.md for the full detector contract.
_REEXPORT_RATIO_THRESHOLD = 0.8

# Body-size-gate threshold: maximum number of non-comment, non-blank lines
# in any top-level function or class body for the module to qualify as an
# aggregator.
_MAX_BODY_LINES = 3


def _extract_module_docstring(source_path: Path) -> str | None:
    """Extract the module-level docstring from a Python file.

    Returns the docstring text or None if no module docstring is found.
    """
    if source_path.suffix not in (".py", ".pyi"):
        return None

    try:
        source = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    return ast.get_docstring(tree)


def heuristic_description(source_path: Path) -> str:
    """Generate a heuristic description from filename and docstrings.

    Checks for a module-level docstring first. Falls back to a
    description derived from the filename.
    """
    docstring = _extract_module_docstring(source_path)
    if docstring:
        # Use first line of docstring as description
        first_line = docstring.strip().split("\n")[0].strip()
        if first_line:
            return first_line

    # Fallback: generate from filename
    stem = source_path.stem
    if stem == "__init__":
        return f"Package initializer for {source_path.parent.name}"
    if stem == "__main__":
        return f"Entry point for {source_path.parent.name}"

    # Convert snake_case to readable
    readable = stem.replace("_", " ").strip()
    return f"Design file for {readable}"


def generate_skeleton_design(
    source_path: Path,
    project_root: Path,
    *,
    updated_by: UpdatedByLiteral = "skeleton-fallback",
    summary_suffix: str = "",
) -> DesignFile:
    """Generate a skeleton design file for a single source file without LLM.

    Uses tree-sitter for interface extraction, AST for dependency extraction,
    and heuristics for the description. Returns a ``DesignFile`` model that the
    caller can serialize and write.

    Args:
        source_path: Absolute path to the source file.
        project_root: Absolute path to the project root.
        updated_by: Value for ``DesignFileFrontmatter.updated_by``.
        summary_suffix: Optional text appended to the summary (e.g. token
            count guidance for size-gated files).

    Returns:
        A fully-populated ``DesignFile`` model ready for serialization.
    """
    # Compute hashes
    content_hash, interface_hash = compute_hashes(source_path)

    rel_path = str(source_path.relative_to(project_root))

    # Generate design ID
    designs_dir = project_root / LEXIBRARY_DIR / DESIGNS_DIR
    design_id = next_design_id(designs_dir)

    # Extract interface skeleton
    skeleton = parse_interface(source_path)
    skeleton_text = ""
    if skeleton is not None:
        skeleton_text = render_skeleton(skeleton)

    # Extract dependencies
    deps = extract_dependencies(source_path, project_root)

    # Heuristic description
    description = heuristic_description(source_path)

    # Build summary (description + optional suffix)
    summary = description + summary_suffix

    # Build DesignFile model
    return DesignFile(
        source_path=rel_path,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=design_id,
            updated_by=updated_by,
        ),
        summary=summary,
        interface_contract=skeleton_text,
        dependencies=deps,
        dependents=[],
        metadata=StalenessMetadata(
            source=rel_path,
            source_hash=content_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator=_GENERATOR_ID,
        ),
    )


# ---------------------------------------------------------------------------
# Aggregator detector (§2.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregatorClassification:
    """Result of running :func:`classify_aggregator` on a source file.

    Attributes:
        is_aggregator: True iff all three gates pass (re-export ratio,
            body-size, conditional-logic). See SHARED_BLOCK_D in the
            design-cleanup tasks.md for the gate definitions.
        reexports_by_source: Mapping from source module (the ``X`` in
            ``from X import A, B``) to the list of names re-exported from
            that module. Empty when ``is_aggregator=False``.
        body_size_ratio: Informational ratio of top-level
            function/class bodies that passed the body-size gate. 1.0 when
            there are no top-level function/class definitions. Useful for
            logging but not acted on by downstream code.
    """

    is_aggregator: bool
    reexports_by_source: dict[str, list[str]] = field(default_factory=dict)
    body_size_ratio: float = 1.0


def classify_aggregator(source_path: Path) -> AggregatorClassification:
    """Classify a Python source file as an aggregator module or not.

    A module is an aggregator iff ALL three gates pass:

    1. **Re-export gate:** ≥80% of top-level named symbols are re-exported
       from another module (members of ``__all__`` whose sole binding is
       ``from <src> import <name>`` / ``<name> = <mod>.<name>``).
    2. **Body-size gate:** Every top-level function and class has a body
       of ≤3 non-comment, non-blank lines.
    3. **Conditional-logic gate:** At most one top-level ``if`` statement,
       and when present its condition subtree must reference
       ``sys.version_info``.

    Non-Python files, unparseable files, and files with no top-level named
    symbols all return ``is_aggregator=False``.

    Args:
        source_path: Absolute path to the source file to classify.

    Returns:
        :class:`AggregatorClassification` describing the verdict.
    """
    if source_path.suffix not in (".py", ".pyi"):
        return AggregatorClassification(is_aggregator=False)

    parser = get_parser(source_path.suffix)
    if parser is None:
        return AggregatorClassification(is_aggregator=False)

    try:
        source_bytes = source_path.read_bytes()
    except OSError:
        logger.warning("Cannot read file for aggregator classification: %s", source_path)
        return AggregatorClassification(is_aggregator=False)

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if root is None:
        return AggregatorClassification(is_aggregator=False)

    # Gate 3: conditional-logic gate — checked first because it's cheap and
    # lets us bail early without walking imports on platform-gated modules.
    if not _conditional_logic_gate_passes(root):
        return AggregatorClassification(is_aggregator=False)

    # Gate 2: body-size gate.
    body_size_passes, body_size_ratio = _body_size_gate(root)
    if not body_size_passes:
        return AggregatorClassification(is_aggregator=False, body_size_ratio=body_size_ratio)

    # Gate 1: re-export gate.
    reexports_by_source, reexport_ratio = _collect_reexports(root)
    if reexport_ratio < _REEXPORT_RATIO_THRESHOLD:
        return AggregatorClassification(is_aggregator=False, body_size_ratio=body_size_ratio)

    return AggregatorClassification(
        is_aggregator=True,
        reexports_by_source=reexports_by_source,
        body_size_ratio=body_size_ratio,
    )


# ---------------------------------------------------------------------------
# Constants-only detector (§2.4c — Complexity Warning prompt suppression)
# ---------------------------------------------------------------------------


def is_constants_only(source_path: Path) -> bool:
    """Return True when *source_path* is a constants-only Python module.

    A constants-only module has:

    - NO top-level ``def`` (``function_definition``)
    - NO top-level ``class`` (``class_definition``)
    - NO top-level decorated definitions
    - Only module-level assignments (``X = 1`` / ``FOO: list[int] = [1, 2]``),
      imports, and docstrings.

    Empty Python files also return True — there is no content for a
    ``complexity_warning`` to describe.

    Non-Python extensions, unreadable files, and unparseable files all
    return False (the pipeline keeps the LLM's ``complexity_warning`` path
    active when the skeleton gate cannot conclude).

    Used by the archivist pipeline to suppress ``complexity_warning`` for
    modules where no top-level behaviour exists to warn about. See
    ``aggregator-design-rendering`` spec for the full requirement.
    """
    if source_path.suffix not in (".py", ".pyi"):
        return False

    parser = get_parser(source_path.suffix)
    if parser is None:
        return False

    try:
        source_bytes = source_path.read_bytes()
    except OSError:
        logger.warning("Cannot read file for constants-only check: %s", source_path)
        return False

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if root is None:
        return False

    # Empty / whitespace-only files: no top-level children → constants-only.
    # (There is no behaviour for a complexity_warning to describe.)
    for child in _ts_children(root):
        child_type = _ts_type(child)
        if child_type in ("function_definition", "class_definition", "decorated_definition"):
            return False

    return True


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------


def _conditional_logic_gate_passes(root: object) -> bool:
    """Return True when the module has at most one top-level ``if``, and
    that ``if`` references ``sys.version_info`` in its condition subtree.
    """
    top_level_ifs = [child for child in _ts_children(root) if _ts_type(child) == "if_statement"]
    if len(top_level_ifs) == 0:
        return True
    if len(top_level_ifs) > 1:
        return False

    condition_node = _ts_child_by_field(top_level_ifs[0], "condition")
    if condition_node is None:
        # Fallback: inspect the full if_statement text.
        return "sys.version_info" in _ts_text(top_level_ifs[0])
    return "sys.version_info" in _ts_text(condition_node)


def _body_size_gate(root: object) -> tuple[bool, float]:
    """Return ``(passes, ratio)`` for the body-size gate.

    ``passes`` is True when every top-level function/class body has ≤3
    non-comment, non-blank lines. ``ratio`` is ``bodies_passed / bodies_total``
    (1.0 when there are no top-level bodies).
    """
    bodies_total = 0
    bodies_passed = 0

    for child in _ts_children(root):
        child_type = _ts_type(child)
        target = child
        if child_type == "decorated_definition":
            inner = _ts_child_by_field(child, "definition")
            if inner is None:
                continue
            target = inner
            child_type = _ts_type(target)

        if child_type not in ("function_definition", "class_definition"):
            continue

        body_node = _ts_child_by_field(target, "body")
        if body_node is None:
            continue

        bodies_total += 1
        if _count_body_lines(body_node) <= _MAX_BODY_LINES:
            bodies_passed += 1

    if bodies_total == 0:
        return True, 1.0
    ratio = bodies_passed / bodies_total
    return bodies_passed == bodies_total, ratio


def _count_body_lines(body_node: object) -> int:
    """Count non-comment, non-blank lines inside a function/class ``block``.

    Tree-sitter's ``block`` node contains each statement as a direct child;
    comments appear as ``comment`` siblings. A statement spanning N source
    lines counts as N lines for the purposes of this gate — we use row
    spans rather than statement counts so that a one-statement function
    with a long multi-line call still fails the ≤3 gate.

    Docstring-only bodies (a single ``expression_statement`` wrapping a
    string literal) count as zero lines so that ``def foo(): ...`` style
    pass-through shims don't trip the gate.
    """
    statements = [child for child in _ts_children(body_node) if _ts_type(child) != "comment"]

    # Treat a pure-docstring body (single expression_statement that is a
    # string) as zero lines — it's a pass-through shim, not real logic.
    if len(statements) == 1 and _is_docstring_statement(statements[0]):
        return 0

    lines = 0
    for stmt in statements:
        start_row, end_row = _ts_row_span(stmt)
        lines += (end_row - start_row) + 1
    return lines


def _is_docstring_statement(node: object) -> bool:
    """Return True when ``node`` is a docstring-only expression_statement."""
    if _ts_type(node) != "expression_statement":
        return False
    children = _ts_children(node)
    if len(children) != 1:
        return False
    child_type = _ts_type(children[0])
    return child_type in ("string", "concatenated_string")


def _collect_reexports(root: object) -> tuple[dict[str, list[str]], float]:
    """Collect re-exports from the module's top level.

    Returns ``(reexports_by_source, ratio)`` where:

    - ``reexports_by_source`` maps each source module to the list of names
      re-exported from it (``from <src> import A, B`` → ``{src: [A, B]}``).
      ``X = module.X`` top-level trivial re-binds contribute to the
      synthetic ``"<unknown>"`` key when the source module isn't
      traceable from the statement alone.
    - ``ratio`` is ``reexported_count / total_named_top_level_symbols``.
      Zero when there are no top-level named symbols (so the gate fails
      gracefully on empty modules).
    """
    reexports_by_source: dict[str, list[str]] = {}
    reexported_names: set[str] = set()
    other_named_symbols: set[str] = set()

    for child in _ts_children(root):
        child_type = _ts_type(child)

        if child_type == "import_from_statement":
            source_mod, names = _parse_from_import(child)
            if source_mod is None or not names:
                continue
            # Skip `from __future__ import ...` — it's a compiler directive,
            # not a re-export.
            if source_mod == "__future__":
                continue
            reexports_by_source.setdefault(source_mod, []).extend(names)
            reexported_names.update(names)

        elif child_type == "import_statement":
            # ``import X`` or ``import X as Y`` — the binding of X is
            # top-level and trivially re-exported only if X is also listed
            # in ``__all__``. We don't eagerly count these as re-exports:
            # adding them here would inflate the ratio on files that use
            # ``import sys`` without re-exporting it.
            continue

        elif child_type in ("function_definition", "class_definition"):
            name = _definition_name(child)
            if name is not None and not name.startswith("_"):
                other_named_symbols.add(name)

        elif child_type == "decorated_definition":
            inner = _ts_child_by_field(child, "definition")
            if inner is None:
                continue
            name = _definition_name(inner)
            if name is not None and not name.startswith("_"):
                other_named_symbols.add(name)

        elif child_type == "expression_statement":
            assign = _find_assignment(child)
            if assign is None:
                continue
            lhs = _simple_assignment_lhs(assign)
            if lhs is None:
                continue
            if lhs == "__all__":
                # ``__all__`` is purely informational for this detector —
                # top-level `from X import Y` bindings already count as
                # re-exports regardless of whether they're listed here.
                # Skip without double-counting it as a standalone symbol.
                continue
            # Non-__all__ top-level assignment — treat as a standalone named
            # symbol unless its RHS is a trivial ``module.X`` re-bind matching
            # the LHS name, which counts as a re-export (``X = module.X``).
            if _is_trivial_rebind(assign, lhs):
                # No traceable source module from just this expression.
                reexports_by_source.setdefault("<unknown>", []).append(lhs)
                reexported_names.add(lhs)
                continue
            if not lhs.startswith("_"):
                other_named_symbols.add(lhs)

    total_named = len(reexported_names) + len(other_named_symbols)
    if total_named == 0:
        return {}, 0.0

    # Sort the name lists deterministically so downstream renderers emit
    # stable output without having to re-sort.
    reexports_by_source = {
        src: sorted(set(names)) for src, names in reexports_by_source.items() if names
    }
    ratio = len(reexported_names) / total_named
    return reexports_by_source, ratio


# ---------------------------------------------------------------------------
# AST-level helpers
# ---------------------------------------------------------------------------


def _parse_from_import(node: object) -> tuple[str | None, list[str]]:
    """Parse a ``from <src> import A, B`` node into ``(source, names)``.

    Returns ``(None, [])`` when the statement is a wildcard import or
    otherwise unparseable. Relative-import source modules are returned
    with their leading dots preserved (e.g. ``".sibling"``).
    """
    names: list[str] = []
    source: str | None = None

    for child in _ts_children(node):
        child_type = _ts_type(child)
        if child_type == "dotted_name" and source is None:
            source = _ts_text(child)
        elif child_type == "relative_import":
            dots = ""
            mod = ""
            for rel_child in _ts_children(child):
                rel_type = _ts_type(rel_child)
                if rel_type == "import_prefix":
                    dots = _ts_text(rel_child)
                elif rel_type == ".":
                    dots += "."
                elif rel_type == "dotted_name":
                    mod = _ts_text(rel_child)
            source = f"{dots}{mod}" if mod else dots
        elif child_type == "dotted_name" and source is not None:
            # The *imported* dotted_name after the first one.
            names.append(_ts_text(child))
        elif child_type == "aliased_import":
            # ``import X as Y`` — record the alias, since that's what's
            # re-exposed at the module's top level.
            alias_node = _ts_child_by_field(child, "alias")
            if alias_node is not None:
                names.append(_ts_text(alias_node))
            else:
                # Fallback: first dotted_name child.
                for sub in _ts_children(child):
                    if _ts_type(sub) == "dotted_name":
                        names.append(_ts_text(sub))
                        break
        elif child_type == "wildcard_import":
            return None, []
        elif child_type == "identifier" and source is not None:
            # Some grammars surface bare identifiers for imports without
            # aliasing (treesitter-python typically uses dotted_name, but
            # guard against future grammar changes).
            names.append(_ts_text(child))

    return source, names


def _find_assignment(expr_stmt_node: object) -> object | None:
    """Return the ``assignment`` child of an expression_statement, if any."""
    for child in _ts_children(expr_stmt_node):
        if _ts_type(child) == "assignment":
            return child
    return None


def _simple_assignment_lhs(assign_node: object) -> str | None:
    """Return the LHS identifier name of ``NAME = <expr>``, else None.

    Tuple unpacking (``a, b = ...``), attribute targets (``self.x = ...``),
    and subscripted targets (``d["k"] = ...``) all return None.
    """
    lhs = _ts_child_by_field(assign_node, "left")
    if lhs is None:
        return None
    if _ts_type(lhs) != "identifier":
        return None
    return _ts_text(lhs)


def _is_trivial_rebind(assign_node: object, lhs_name: str) -> bool:
    """Return True when an assignment is ``<lhs_name> = <anything>.<lhs_name>``.

    This captures the ``X = other_module.X`` re-export idiom where a
    symbol is re-exposed at the module's top level under the same name
    after being traversed to via attribute access.
    """
    rhs = _ts_child_by_field(assign_node, "right")
    if rhs is None:
        return False
    if _ts_type(rhs) != "attribute":
        return False
    attr_name_node = _ts_child_by_field(rhs, "attribute")
    if attr_name_node is None:
        return False
    return _ts_text(attr_name_node) == lhs_name


def _definition_name(definition_node: object) -> str | None:
    """Return the declared name of a function_definition / class_definition."""
    name_node = _ts_child_by_field(definition_node, "name")
    if name_node is None:
        return None
    return _ts_text(name_node)


# ---------------------------------------------------------------------------
# Tree-sitter node access helpers (mirror those in dependency_extractor.py
# — kept inline to preserve the grammar-optional getattr pattern).
# ---------------------------------------------------------------------------


def _ts_children(node: object) -> list[object]:
    """Return all direct children of a tree-sitter node."""
    return list(getattr(node, "children", []))


def _ts_type(node: object) -> str:
    """Return the tree-sitter node type string, or ``""`` when unavailable."""
    return str(getattr(node, "type", ""))


def _ts_text(node: object) -> str:
    """Return the UTF-8 source text of a tree-sitter node."""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text)


def _ts_child_by_field(node: object, field_name: str) -> object | None:
    """Return the named field child of a tree-sitter node, or None."""
    accessor = getattr(node, "child_by_field_name", None)
    if accessor is None:
        return None
    result: object | None = accessor(field_name)
    return result


def _ts_row_span(node: object) -> tuple[int, int]:
    """Return (start_row, end_row) as 0-indexed tree-sitter rows."""
    start = getattr(node, "start_point", (0, 0))
    end = getattr(node, "end_point", start)
    start_row = start[0] if isinstance(start, (tuple, list)) else 0
    end_row = end[0] if isinstance(end, (tuple, list)) else start_row
    return int(start_row), int(end_row)
