"""Lookup render — terminal formatting for lookup results.

Render functions accept data from :mod:`lexibrary.services.lookup` result
dataclasses and return formatted strings.  They do **not** call
:func:`~lexibrary.cli._output.info` or any other output function directly.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexibrary.artifacts.design_file import CallPathNote, DataFlowNote, EnumNote
    from lexibrary.artifacts.playbook import PlaybookFile


def render_conventions(
    conventions: Sequence[object],
    total_count: int,
    display_limit: int,
    rel_target: str,
) -> str:
    """Render an Applicable Conventions section grouped by scope.

    Conventions are grouped by their scope field, ordered from most general
    (project) to most specific. Draft conventions are marked with ``[draft]``.
    When truncated, a notice is appended.

    Returns a formatted string (empty string if no conventions).
    """
    from lexibrary.artifacts.convention import ConventionFile  # noqa: PLC0415

    typed_conventions: list[ConventionFile] = [
        c for c in conventions if isinstance(c, ConventionFile)
    ]
    if not typed_conventions:
        return ""

    lines: list[str] = ["\n## Applicable Conventions\n"]

    # Group by scope, preserving order (already sorted root-to-leaf)
    groups: OrderedDict[str, list[ConventionFile]] = OrderedDict()
    for conv in typed_conventions:
        scope = conv.frontmatter.scope
        groups.setdefault(scope, []).append(conv)

    for scope, group in groups.items():
        scope_label = scope if scope != "project" else "project"
        lines.append(f"### {scope_label}\n")
        for conv in group:
            draft_marker = " [draft]" if conv.frontmatter.status == "draft" else ""
            rule_text = conv.rule or conv.frontmatter.title
            lines.append(f"- {rule_text}{draft_marker}")
        lines.append("")

    if total_count > display_limit:
        omitted = total_count - display_limit
        lines.append(f"... and {omitted} more -- run `lexi conventions {rel_target}` to see all\n")

    return "\n".join(lines)


def render_known_issues(
    link_graph: object,
    rel_path: str,
    project_root: Path,
    display_limit: int,
) -> str:
    """Render a Known Issues section from stack_file_ref links.

    Queries the link graph for ``stack_file_ref`` links pointing to *rel_path*,
    parses each matching Stack post, and renders a summary with status, title,
    attempts count, and votes.

    Posts with ``stale`` status are excluded.  Open posts are shown first,
    then resolved posts, up to *display_limit*.

    Returns the rendered text (empty string if no issues found).
    """
    from lexibrary.linkgraph.query import LinkGraph  # noqa: PLC0415
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

    if not isinstance(link_graph, LinkGraph):
        return ""

    stack_links = link_graph.reverse_deps(rel_path, link_type="stack_file_ref")
    if not stack_links:
        return ""

    # Parse each referenced stack post
    posts = []
    for link in stack_links:
        post_path = project_root / link.source_path
        post = parse_stack_post(post_path)
        if post is None:
            continue
        # Exclude stale posts
        if post.frontmatter.status == "stale":
            continue
        posts.append(post)

    if not posts:
        return ""

    # Sort: open first, then resolved; within each group sort by votes descending
    status_order = {"open": 0, "resolved": 1, "outdated": 2, "duplicate": 3}
    posts.sort(key=lambda p: (status_order.get(p.frontmatter.status, 9), -p.frontmatter.votes))

    # Apply display limit
    shown = posts[:display_limit]
    omitted = len(posts) - len(shown)

    lines: list[str] = ["\n## Known Issues\n"]
    for post in shown:
        status_label = post.frontmatter.status
        attempts_count = len(post.attempts)
        attempts_str = f", {attempts_count} attempts" if attempts_count > 0 else ""
        votes_str = f", {post.frontmatter.votes} votes" if post.frontmatter.votes > 0 else ""
        lines.append(f"- [{status_label}] {post.frontmatter.title}{attempts_str}{votes_str}")
    if omitted > 0:
        lines.append(f"\n... and {omitted} more issues")
    lines.append("")

    return "\n".join(lines)


def render_iwh_peek(
    project_root: Path,
    target: Path,
) -> str:
    """Render an IWH signal peek section without consuming the signal.

    Checks for an IWH file in the mirror directory corresponding to *target*
    (which may be a file or directory).  Returns rendered text or empty string.
    """
    from lexibrary.iwh.reader import read_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    # For a file, the IWH lives in the parent's mirror directory
    # For a directory, it lives in the directory's own mirror
    if target.is_file():
        rel = target.parent.relative_to(project_root)
    else:
        rel = target.relative_to(project_root)

    # Check the designs mirror tree for IWH signals
    iwh_dir = project_root / LEXIBRARY_DIR / "designs" / rel
    iwh = None
    if iwh_dir.is_dir():
        iwh = read_iwh(iwh_dir)

    if iwh is None:
        # Also check legacy mirror path (without designs/)
        iwh_dir = project_root / LEXIBRARY_DIR / rel
        if iwh_dir.is_dir():
            iwh = read_iwh(iwh_dir)

    if iwh is None:
        return ""

    lines: list[str] = ["\n## IWH Signal\n"]
    lines.append(f"- Scope: {iwh.scope}")
    lines.append(f"- Author: {iwh.author}")
    lines.append(f"- Created: {iwh.created.isoformat()}")
    if iwh.body:
        # Truncate body preview to first 200 chars
        body_preview = iwh.body[:200]
        if len(iwh.body) > 200:
            body_preview += "..."
        lines.append(f"- Body: {body_preview}")
    lines.append("")
    lines.append("Run `lexi iwh read <directory>` to consume this signal.")
    lines.append("")

    return "\n".join(lines)


def render_triggered_playbooks(
    playbooks: Sequence[PlaybookFile],
    display_limit: int,
) -> str:
    """Render a 'Triggered Playbooks' section for matching playbooks.

    *playbooks* should already be ordered by trigger specificity (as returned
    by :meth:`PlaybookIndex.by_trigger_file`).  At most *display_limit*
    entries are shown; a note is appended when more exist.

    Returns an empty string if *playbooks* is empty.
    """
    if not playbooks:
        return ""

    shown = playbooks[:display_limit]
    lines: list[str] = ["\n## Triggered Playbooks\n"]
    for pb in shown:
        overview_preview = pb.overview.replace("\n", " ").strip()
        if len(overview_preview) > 120:
            overview_preview = overview_preview[:117] + "..."
        est = (
            f" (~{pb.frontmatter.estimated_minutes} min)"
            if pb.frontmatter.estimated_minutes
            else ""
        )
        lines.append(f"- **{pb.frontmatter.title}**{est}")
        if overview_preview:
            lines.append(f"  {overview_preview}")

    if len(playbooks) > display_limit:
        extra = len(playbooks) - display_limit
        lines.append(
            f"\n*{extra} more playbook(s) matched -- run `lexi playbook search` for full list.*"
        )

    lines.append("")
    return "\n".join(lines)


def render_siblings(
    siblings: Sequence[object],
    current_file: str,
    full: bool = False,
) -> str:
    """Render a sibling files section.

    *siblings* should be a list of :class:`SiblingSummary` instances from the
    parent directory's ``.aindex``.  The entry matching *current_file* is
    annotated with ``(this file)``.

    **Brief mode** (``full=False``): returns a single inline line.
    **Full mode** (``full=True``): returns a ``## Sibling Files`` section with
    descriptions.

    Returns an empty string when *siblings* is empty.
    """
    from lexibrary.services.lookup import SiblingSummary  # noqa: PLC0415

    typed: list[SiblingSummary] = [s for s in siblings if isinstance(s, SiblingSummary)]
    if not typed:
        return ""

    current_name = Path(current_file).name

    if not full:
        parts: list[str] = []
        for s in typed:
            label = f"{s.name} (this file)" if s.name == current_name else s.name
            parts.append(label)
        return f"Siblings: {', '.join(parts)}\n"

    lines: list[str] = ["\n## Sibling Files\n"]
    for s in typed:
        marker = " (this file)" if s.name == current_name else ""
        lines.append(f"- {s.name}{marker} -- {s.description}")
    lines.append("")
    return "\n".join(lines)


def render_related_concepts(
    concepts: Sequence[object],
    full: bool = False,
    linkgraph_available: bool = True,
) -> str:
    """Render a related concepts section.

    *concepts* should be a list of :class:`ConceptSummary` instances.

    **Brief mode** (``full=False``): returns a single inline line with
    ``[[name]] (status)`` notation; status parenthetical is omitted when
    ``status is None``.

    **Full mode** (``full=True``): returns a ``## Related Concepts`` section.
    When *linkgraph_available* is ``False`` the heading includes a note that
    only names are available.

    Returns an empty string when *concepts* is empty.
    """
    from lexibrary.services.lookup import ConceptSummary  # noqa: PLC0415

    typed: list[ConceptSummary] = [c for c in concepts if isinstance(c, ConceptSummary)]
    if not typed:
        return ""

    if not full:
        parts: list[str] = []
        for c in typed:
            if c.status is not None:
                parts.append(f"[[{c.name}]] ({c.status})")
            else:
                parts.append(f"[[{c.name}]]")
        return f"Related concepts: {', '.join(parts)}\n"

    if linkgraph_available:
        heading = "## Related Concepts"
    else:
        heading = "## Related Concepts (link graph unavailable -- names only)"

    lines: list[str] = [f"\n{heading}\n"]
    for c in typed:
        status_part = f" ({c.status})" if c.status is not None else ""
        if c.summary is not None:
            lines.append(f"- **{c.name}**{status_part} -- {c.summary}")
        else:
            lines.append(f"- **{c.name}**{status_part}")
    lines.append("")
    return "\n".join(lines)


def render_key_symbols(
    key_symbols: Sequence[object],
    key_symbols_total: int,
) -> str:
    """Render a ``### Key symbols`` markdown table for a file lookup.

    *key_symbols* should be a list of :class:`KeySymbolSummary` instances,
    already ordered by source line (as produced by
    :func:`lexibrary.services.lookup.build_file_lookup`). The renderer
    groups methods under their parent class by showing the qualified-name
    tail (``Class.method``) for ``symbol_type == "method"`` and the bare
    ``name`` otherwise. When *key_symbols_total* exceeds
    ``len(key_symbols)``, a trailing ``… and N more`` line is appended so
    users know the list was truncated by the display cap.

    Returns an empty string when *key_symbols* is empty; the CLI uses
    that signal to omit the whole section.
    """
    from lexibrary.cli._output import markdown_table  # noqa: PLC0415
    from lexibrary.services.lookup import KeySymbolSummary  # noqa: PLC0415

    typed: list[KeySymbolSummary] = [s for s in key_symbols if isinstance(s, KeySymbolSummary)]
    if not typed:
        return ""

    rows: list[list[str]] = []
    for summary in typed:
        if summary.symbol_type == "method" and summary.qualified_name is not None:
            # Trim the module prefix and keep the ``Class.method`` tail so
            # readers can see which class owns the method without having
            # to scan upward.
            parts = summary.qualified_name.split(".")
            display_name = ".".join(parts[-2:]) if len(parts) >= 2 else summary.name
        else:
            display_name = summary.name
        rows.append(
            [
                display_name,
                summary.symbol_type,
                str(summary.line_start),
                f"{summary.caller_count} → {summary.callee_count}",
            ]
        )

    table = markdown_table(
        ["Symbol", "Type", "Line", "Callers → Callees"],
        rows,
    )

    lines: list[str] = ["\n### Key symbols\n", table]
    remainder = key_symbols_total - len(typed)
    if remainder > 0:
        lines.append(f"\n… and {remainder} more")
    lines.append("")
    return "\n".join(lines)


def render_class_hierarchy(classes: Sequence[object]) -> str:
    """Render a ``### Class hierarchy`` section for a file lookup.

    *classes* should be a list of :class:`ClassHierarchyEntry` instances
    (order preserved — typically source order). The renderer emits a
    markdown table with columns ``Class | Bases | Subclasses | Methods |
    Line``. ``Bases`` joins the resolved base-class names with ``, ``
    then appends each unresolved base name with a trailing ``*`` marker;
    rows with neither resolved nor unresolved bases render ``—``.

    Returns an empty string when *classes* is empty so the CLI can omit
    the whole section.
    """
    from lexibrary.cli._output import markdown_table  # noqa: PLC0415
    from lexibrary.services.lookup import ClassHierarchyEntry  # noqa: PLC0415

    typed: list[ClassHierarchyEntry] = [c for c in classes if isinstance(c, ClassHierarchyEntry)]
    if not typed:
        return ""

    rows: list[list[str]] = []
    for entry in typed:
        base_parts: list[str] = list(entry.bases)
        base_parts.extend(f"{name}*" for name in entry.unresolved_bases)
        bases_display = ", ".join(base_parts) if base_parts else "—"
        rows.append(
            [
                entry.class_name,
                bases_display,
                str(entry.subclass_count),
                str(entry.method_count),
                str(entry.line_start),
            ]
        )

    table = markdown_table(
        ["Class", "Bases", "Subclasses", "Methods", "Line"],
        rows,
    )
    lines: list[str] = ["\n### Class hierarchy\n", table, ""]
    return "\n".join(lines)


def render_enum_notes(enum_notes: Sequence[EnumNote]) -> str:
    """Render an ``### Enums & constants`` section for a file lookup.

    *enum_notes* should be a list of
    :class:`~lexibrary.artifacts.design_file.EnumNote` instances surfaced from
    the parsed design file.  Each note becomes a markdown bullet of the form
    ``- **{name}** — {role}`` with an indented ``Values:`` continuation line
    when the note carries enum members.

    Non-:class:`EnumNote` items in the sequence are filtered out so the
    renderer mirrors the defensive behaviour of :func:`render_key_symbols`
    and :func:`render_class_hierarchy`.

    Returns an empty string when *enum_notes* is empty so the CLI can omit
    the whole section.
    """
    from lexibrary.artifacts.design_file import EnumNote as _EnumNote  # noqa: PLC0415

    typed: list[EnumNote] = [n for n in enum_notes if isinstance(n, _EnumNote)]
    if not typed:
        return ""

    lines: list[str] = ["\n### Enums & constants\n"]
    for note in typed:
        lines.append(f"- **{note.name}** — {note.role}")
        if note.values:
            lines.append(f"  Values: {', '.join(note.values)}")
    lines.append("")
    return "\n".join(lines)


def render_call_path_notes(call_path_notes: Sequence[CallPathNote]) -> str:
    """Render an ``### Call paths`` section for a file lookup.

    *call_path_notes* should be a list of
    :class:`~lexibrary.artifacts.design_file.CallPathNote` instances surfaced
    from the parsed design file.  Each note becomes a markdown bullet of the
    form ``- **{entry}** — {narrative}`` with an indented ``Key hops:``
    continuation line when the note carries hop names.

    Non-:class:`CallPathNote` items in the sequence are filtered out so the
    renderer mirrors the defensive behaviour of :func:`render_key_symbols`
    and :func:`render_class_hierarchy`.

    Returns an empty string when *call_path_notes* is empty so the CLI can
    omit the whole section.
    """
    from lexibrary.artifacts.design_file import (  # noqa: PLC0415
        CallPathNote as _CallPathNote,
    )

    typed: list[CallPathNote] = [n for n in call_path_notes if isinstance(n, _CallPathNote)]
    if not typed:
        return ""

    lines: list[str] = ["\n### Call paths\n"]
    for note in typed:
        lines.append(f"- **{note.entry}** — {note.narrative}")
        if note.key_hops:
            lines.append(f"  Key hops: {', '.join(note.key_hops)}")
    lines.append("")
    return "\n".join(lines)


def render_data_flow_notes(data_flow_notes: Sequence[DataFlowNote]) -> str:
    """Render a ``### Data flows`` section for a file lookup.

    *data_flow_notes* should be a list of
    :class:`~lexibrary.artifacts.design_file.DataFlowNote` instances surfaced
    from the parsed design file.  Each note becomes a markdown bullet of the
    form ``- **{parameter}** in **{location}** — {effect}``.

    Non-:class:`DataFlowNote` items in the sequence are filtered out so the
    renderer mirrors the defensive behaviour of :func:`render_call_path_notes`.

    Returns an empty string when *data_flow_notes* is empty so the CLI can
    omit the whole section.
    """
    from lexibrary.artifacts.design_file import (  # noqa: PLC0415
        DataFlowNote as _DataFlowNote,
    )

    typed: list[DataFlowNote] = [n for n in data_flow_notes if isinstance(n, _DataFlowNote)]
    if not typed:
        return ""

    lines: list[str] = ["\n### Data flows\n"]
    for note in typed:
        lines.append(f"- **{note.parameter}** in **{note.location}** — {note.effect}")
    lines.append("")
    return "\n".join(lines)


def render_directory_link_summary(
    import_count: int,
    imported_file_count: int,
) -> str:
    """Render a one-line inbound import summary for a directory.

    Returns an empty string when *import_count* is zero.
    """
    if import_count == 0:
        return ""
    return f"Inbound imports: {import_count} (across {imported_file_count} files)\n"
