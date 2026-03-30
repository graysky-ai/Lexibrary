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
