"""Stack issue management CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, hint, info, markdown_table, warn
from lexibrary.cli._shared import require_project_root

stack_app = typer.Typer(help="Stack issue management commands.", rich_markup_mode=None)


# ---------------------------------------------------------------------------
# Stack helpers (private, used only by stack commands)
# ---------------------------------------------------------------------------


def _stack_dir(project_root: Path) -> Path:
    """Return the .lexibrary/stack/ directory, creating it if needed."""
    d = project_root / ".lexibrary" / "stack"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_stack_id(stack_dir: Path) -> int:
    """Scan existing ST-NNN-*.md files and return the next available number."""
    import re as _re  # noqa: PLC0415

    max_num = 0
    for f in stack_dir.glob("ST-*-*.md"):
        m = _re.match(r"ST-(\d+)-", f.name)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def _slugify(title: str) -> str:
    """Convert a title to a URL-friendly slug."""
    import re as _re  # noqa: PLC0415

    slug = title.lower()
    slug = _re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    # Collapse consecutive hyphens
    slug = _re.sub(r"-+", "-", slug)
    return slug[:50]


def _find_post_path(project_root: Path, post_id: str) -> Path | None:
    """Find the file path for a post ID (e.g. 'ST-001')."""
    stack_dir = project_root / ".lexibrary" / "stack"
    if not stack_dir.is_dir():
        return None
    for f in stack_dir.glob(f"{post_id}-*.md"):
        return f
    return None


def _require_post(project_root: Path, post_id: str) -> Path:
    """Resolve a post ID to its file path, or exit with a helpful error.

    Raises ``typer.Exit(1)`` if the post is not found, with a hint
    suggesting ``lexi search --type stack`` to discover valid post IDs.
    """
    post_path = _find_post_path(project_root, post_id)
    if post_path is None:
        error(f"Post not found: {post_id}")
        hint("Run `lexi search --type stack` to see available posts.")
        raise typer.Exit(1)
    return post_path


# ---------------------------------------------------------------------------
# Stack commands
# ---------------------------------------------------------------------------


@stack_app.command("post")
def stack_post(
    *,
    title: Annotated[
        str,
        typer.Option("--title", help="Title for the new issue post."),
    ],
    tag: Annotated[
        list[str],
        typer.Option("--tag", help="Tag for the post (repeatable, at least one required)."),
    ],
    bead: Annotated[
        str | None,
        typer.Option("--bead", help="Bead ID to associate with the post."),
    ] = None,
    file: Annotated[
        list[str] | None,
        typer.Option("--file", help="Source file reference (repeatable)."),
    ] = None,
    concept: Annotated[
        list[str] | None,
        typer.Option("--concept", help="Concept reference (repeatable)."),
    ] = None,
    problem: Annotated[
        str | None,
        typer.Option("--problem", help="Problem description for the issue."),
    ] = None,
    context: Annotated[
        str | None,
        typer.Option("--context", help="Context for the issue."),
    ] = None,
    evidence: Annotated[
        list[str] | None,
        typer.Option("--evidence", help="Evidence item (repeatable)."),
    ] = None,
    attempts: Annotated[
        list[str] | None,
        typer.Option("--attempts", help="Attempt description (repeatable)."),
    ] = None,
    finding: Annotated[
        str | None,
        typer.Option("--finding", help="Inline finding body text."),
    ] = None,
    resolve: Annotated[
        bool,
        typer.Option("--resolve", help="Auto-accept inline finding and set status to resolved."),
    ] = False,
    resolution_type: Annotated[
        str | None,
        typer.Option(
            "--resolution-type",
            help="Resolution type (e.g. fix, workaround). Requires --resolve.",
        ),
    ] = None,
    fix: Annotated[
        str | None,
        typer.Option(
            "--fix",
            help="Shortcut: add a finding, resolve, and set resolution-type to 'fix'.",
        ),
    ] = None,
    workaround: Annotated[
        str | None,
        typer.Option(
            "--workaround",
            help="Shortcut: add a finding, resolve, and set resolution-type to 'workaround'.",
        ),
    ] = None,
) -> None:
    """Create a Stack issue post and return its auto-assigned ID (e.g. ST-001)."""
    from lexibrary.stack.template import render_post_template  # noqa: PLC0415

    project_root = require_project_root()
    sd = _stack_dir(project_root)

    if not tag:
        error("At least one --tag is required.")
        raise typer.Exit(1)

    # Mutual exclusivity: --fix and --workaround conflict with each other
    if fix is not None and workaround is not None:
        error("--fix and --workaround are mutually exclusive.")
        raise typer.Exit(1)

    # Mutual exclusivity: shortcuts conflict with --finding, --resolve, --resolution-type
    shortcut_name = (
        "--fix" if fix is not None
        else "--workaround" if workaround is not None
        else None
    )
    if shortcut_name is not None:
        if finding is not None:
            error(f"{shortcut_name} conflicts with --finding.")
            raise typer.Exit(1)
        if resolve:
            error(f"{shortcut_name} conflicts with --resolve.")
            raise typer.Exit(1)
        if resolution_type is not None:
            error(f"{shortcut_name} conflicts with --resolution-type.")
            raise typer.Exit(1)

    # Expand shortcuts into canonical flags
    if fix is not None:
        finding = fix
        resolve = True
        resolution_type = "fix"
    elif workaround is not None:
        finding = workaround
        resolve = True
        resolution_type = "workaround"

    # CLI validation: --resolve requires --finding, --resolution-type requires --resolve
    if resolve and finding is None:
        error("--resolve requires --finding.")
        raise typer.Exit(1)
    if resolution_type is not None and not resolve:
        error("--resolution-type requires --resolve.")
        raise typer.Exit(1)

    next_num = _next_stack_id(sd)
    post_id = f"ST-{next_num:03d}"
    slug = _slugify(title)
    filename = f"{post_id}-{slug}.md"
    post_path = sd / filename

    content = render_post_template(
        post_id=post_id,
        title=title,
        tags=tag,
        author="user",
        bead=bead,
        refs_files=file,
        refs_concepts=concept,
        problem=problem,
        context=context,
        evidence=evidence,
        attempts=attempts,
    )
    post_path.write_text(content, encoding="utf-8")

    # Two-step one-shot flow: if --finding is provided, append finding via mutation
    if finding is not None:
        from lexibrary.stack.mutations import accept_finding, add_finding  # noqa: PLC0415

        add_finding(post_path, author="user", body=finding)
        if resolve:
            accept_finding(post_path, finding_num=1, resolution_type=resolution_type)

    rel = post_path.relative_to(project_root)
    info(f"Created {rel}")

    # Blank-section warnings for expected-but-empty fields
    blank_sections: list[str] = []
    if not problem:
        blank_sections.append("problem")
    if not context:
        blank_sections.append("context")
    if not evidence:
        blank_sections.append("evidence")
    if not attempts:
        blank_sections.append("attempts")
    if blank_sections:
        info(
            f"Note: The following sections are blank: "
            f"{', '.join(blank_sections)}"
        )


@stack_app.command("finding")
def stack_finding(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", help="Finding body text."),
    ],
) -> None:
    """Append a finding to a Stack post and return the finding number."""
    from lexibrary.stack.mutations import add_finding  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    updated = add_finding(post_path, author="user", body=body)
    last_finding = updated.findings[-1]
    info(f"Added finding F{last_finding.number} to {post_id}")


@stack_app.command("vote")
def stack_vote(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
    direction: Annotated[
        str,
        typer.Argument(help="Vote direction: 'up' or 'down'."),
    ],
    *,
    finding: Annotated[
        int | None,
        typer.Option("--finding", help="Finding number to vote on (omit to vote on post)."),
    ] = None,
    comment: Annotated[
        str | None,
        typer.Option("--comment", help="Comment (required for downvotes)."),
    ] = None,
) -> None:
    """Record a vote on a Stack post or finding and return the updated vote count."""
    from lexibrary.stack.mutations import record_vote  # noqa: PLC0415

    project_root = require_project_root()

    if direction not in ("up", "down"):
        error("Direction must be 'up' or 'down'.")
        raise typer.Exit(1)

    if direction == "down" and comment is None:
        error("Downvotes require --comment.")
        raise typer.Exit(1)

    post_path = _require_post(project_root, post_id)

    target = f"F{finding}" if finding is not None else "post"

    try:
        updated = record_vote(
            post_path,
            target=target,
            direction=direction,
            author="user",
            comment=comment,
        )
    except ValueError as e:
        error(str(e))
        raise typer.Exit(1) from None

    if finding is not None:
        for a in updated.findings:
            if a.number == finding:
                info(f"Recorded {direction}vote on F{finding} (votes: {a.votes})")
                return
    else:
        info(
            f"Recorded {direction}vote on {post_id} "
            f"(votes: {updated.frontmatter.votes})"
        )


@stack_app.command("accept")
def stack_accept(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
    *,
    finding_num: Annotated[
        int,
        typer.Option("--finding", help="Finding number to accept."),
    ],
    resolution_type: Annotated[
        str | None,
        typer.Option("--resolution-type", help="Resolution type (e.g. fix, workaround)."),
    ] = None,
) -> None:
    """Accept a finding and set the post status to resolved."""
    from lexibrary.stack.mutations import accept_finding  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    try:
        accept_finding(post_path, finding_num, resolution_type=resolution_type)
    except ValueError as e:
        error(str(e))
        raise typer.Exit(1) from None

    info(f"Accepted F{finding_num} on {post_id} -- status set to resolved")


@stack_app.command("view")
def stack_view(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Return the full content of a Stack post including findings, votes, and comments."""
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    post = parse_stack_post(post_path)
    if post is None:
        error(f"Failed to parse post: {post_id}")
        raise typer.Exit(1)

    fm = post.frontmatter

    # Header
    info(f"# {fm.id}: {fm.title}")
    info("")
    info(f"Status: {fm.status} | Votes: {fm.votes} | Tags: {', '.join(fm.tags)}")
    info(f"Created: {fm.created.isoformat()} | Author: {fm.author}")
    if fm.bead:
        info(f"Bead: {fm.bead}")
    if fm.refs.files:
        info(f"Files: {', '.join(fm.refs.files)}")
    if fm.refs.concepts:
        info(f"Concepts: {', '.join(fm.refs.concepts)}")
    if fm.duplicate_of:
        info(f"Duplicate of: {fm.duplicate_of}")
    if fm.resolution_type:
        info(f"Resolution: {fm.resolution_type}")

    # Problem
    info("\n## Problem\n")
    info(post.problem)

    # Context
    if post.context:
        info("\n### Context\n")
        info(post.context)

    # Evidence
    if post.evidence:
        info("\n### Evidence\n")
        for item in post.evidence:
            info(f"  - {item}")

    # Attempts
    if post.attempts:
        info("\n### Attempts\n")
        for item in post.attempts:
            info(f"  - {item}")

    # Findings
    if post.findings:
        info(f"\n## Findings ({len(post.findings)})\n")
        for a in post.findings:
            accepted_badge = " (accepted)" if a.accepted else ""
            info(
                f"### F{a.number}{accepted_badge}  "
                f"Votes: {a.votes} | {a.date.isoformat()} | {a.author}"
            )
            info(a.body)
            if a.comments:
                info("  Comments:")
                for c in a.comments:
                    info(f"    {c}")
            info("")
    else:
        info("\nNo findings yet.")


@stack_app.command("mark-outdated")
def stack_mark_outdated(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Set a Stack post's status to outdated."""
    from lexibrary.stack.mutations import mark_outdated  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    mark_outdated(post_path)
    info(f"Marked {post_id} as outdated")


@stack_app.command("duplicate")
def stack_duplicate(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID to mark as duplicate (e.g. ST-003)."),
    ],
    *,
    of: Annotated[
        str,
        typer.Option("--of", help="Original post ID this is a duplicate of."),
    ],
) -> None:
    """Set a Stack post's status to duplicate and link it to the original post via --of."""
    from lexibrary.stack.mutations import mark_duplicate  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    mark_duplicate(post_path, duplicate_of=of)
    info(f"Marked {post_id} as duplicate of {of}")


@stack_app.command("comment")
def stack_comment(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", "-b", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a Stack post and return confirmation."""
    from lexibrary.lifecycle.stack_comments import (  # noqa: PLC0415
        append_stack_comment,
        stack_comment_count,
    )

    project_root = require_project_root()
    _require_post(project_root, post_id)

    append_stack_comment(project_root, post_id, body)
    count = stack_comment_count(project_root, post_id)
    info(
        f"Comment added for post {post_id} "
        f"({count} comment{'s' if count != 1 else ''} total)"
    )


@stack_app.command("stale")
def stack_stale(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Set a resolved Stack post's status to stale for re-evaluation."""
    from lexibrary.stack.mutations import mark_stale  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    try:
        updated = mark_stale(post_path)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    stale_at = updated.frontmatter.stale_at
    stale_at_str = stale_at.isoformat() if stale_at else "unknown"
    info(f"Marked {post_id} as stale (stale_at: {stale_at_str})")


@stack_app.command("unstale")
def stack_unstale(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Reverse staleness on a Stack post, setting status back to resolved."""
    from lexibrary.stack.mutations import mark_unstale  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _require_post(project_root, post_id)

    try:
        mark_unstale(post_path)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    info(f"Marked {post_id} as resolved (un-staled)")
