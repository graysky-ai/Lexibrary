"""Playbook lifecycle management CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer

from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import require_project_root

playbook_app = typer.Typer(help="Playbook lifecycle management commands.", rich_markup_mode=None)


# ---------------------------------------------------------------------------
# playbook new
# ---------------------------------------------------------------------------


@playbook_app.command("new")
def playbook_new(
    title: Annotated[
        str,
        typer.Argument(
            help=(
                "Playbook title — use a semantic name that will help future agents "
                "know when to use this playbook (e.g. 'Version Bump')"
            ),
        ),
    ],
    *,
    trigger_file: Annotated[
        list[str] | None,
        typer.Option(
            "--trigger-file",
            help="Glob pattern for file-context discovery (repeatable).",
        ),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag to add (repeatable)."),
    ] = None,
    estimated_minutes: Annotated[
        int | None,
        typer.Option(
            "--estimated-minutes",
            help="Estimated time in minutes to complete the playbook.",
        ),
    ] = None,
) -> None:
    """Create a scaffolded playbook file. Status defaults to draft."""
    from lexibrary.artifacts.ids import next_artifact_id  # noqa: PLC0415
    from lexibrary.artifacts.playbook import playbook_file_path, playbook_slug  # noqa: PLC0415
    from lexibrary.artifacts.title_check import find_title_matches  # noqa: PLC0415
    from lexibrary.playbooks.template import render_playbook_template  # noqa: PLC0415

    project_root = require_project_root()
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)

    # Title collision detection
    title_result = find_title_matches(title, "playbook", project_root)
    if title_result.has_same_type:
        match = title_result.same_type[0]
        rel = match.file_path.relative_to(project_root)
        error(f"A playbook with this title already exists: {rel}")
        hint("Edit the existing playbook instead of creating a duplicate.")
        raise typer.Exit(1)
    if title_result.has_cross_type:
        for match in title_result.cross_type:
            rel = match.file_path.relative_to(project_root)
            warn(f"Related {match.kind} with same title exists: {rel}")

    # Check for duplicate slug (match ID-prefixed filenames)
    slug = playbook_slug(title)
    existing_matches = list(playbooks_dir.glob(f"PB-*-{slug}.md"))
    if existing_matches:
        existing = existing_matches[0]
        error(
            f"Playbook already exists: {existing.relative_to(project_root)}\n"
            f"Edit the existing file instead of creating a duplicate."
        )
        raise typer.Exit(1)

    playbook_id = next_artifact_id("PB", playbooks_dir, "PB-*-*.md")
    content = render_playbook_template(
        title=title,
        trigger_files=trigger_file or [],
        tags=tag or [],
        estimated_minutes=estimated_minutes,
        playbook_id=playbook_id,
    )
    target = playbook_file_path(playbook_id, title, playbooks_dir)
    target.write_text(content, encoding="utf-8")

    info(f"Created {target.relative_to(project_root)}")


# ---------------------------------------------------------------------------
# playbook approve
# ---------------------------------------------------------------------------


@playbook_app.command("approve")
def playbook_approve(
    slug: Annotated[
        str,
        typer.Argument(help="Playbook file slug (filename stem, e.g. 'version-bump')."),
    ],
) -> None:
    """Promote a draft playbook to active status."""
    from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415
    from lexibrary.playbooks.serializer import serialize_playbook_file  # noqa: PLC0415

    project_root = require_project_root()
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    pb_path = playbooks_dir / f"{slug}.md"

    if not pb_path.exists():
        available = (
            sorted(p.stem for p in playbooks_dir.glob("*.md")) if playbooks_dir.is_dir() else []
        )
        if available:
            error(f"Playbook not found: '{slug}'\nAvailable playbooks: " + ", ".join(available))
        else:
            error(
                f"Playbook not found: '{slug}'\n"
                "No playbooks exist yet. Run `lexi playbook new` first."
            )
        hint("Run `lexi search --type playbook` to browse all playbooks.")
        raise typer.Exit(1)

    pb = parse_playbook_file(pb_path)
    if pb is None:
        error(f"Failed to parse playbook file: {pb_path.relative_to(project_root)}")
        raise typer.Exit(1)

    if pb.frontmatter.status != "draft":
        error(
            f"Cannot approve a non-draft playbook. "
            f"'{pb.frontmatter.title}' has status '{pb.frontmatter.status}'."
        )
        raise typer.Exit(1)

    # Update status and re-serialize
    pb.frontmatter.status = "active"
    content = serialize_playbook_file(pb)
    pb_path.write_text(content, encoding="utf-8")

    info(f"Approved '{pb.frontmatter.title}' -- status set to active")


# ---------------------------------------------------------------------------
# playbook verify
# ---------------------------------------------------------------------------


@playbook_app.command("verify")
def playbook_verify(
    slug: Annotated[
        str,
        typer.Argument(help="Playbook file slug (filename stem, e.g. 'version-bump')."),
    ],
) -> None:
    """Update a playbook's last_verified date to today."""
    from datetime import date  # noqa: PLC0415

    from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415
    from lexibrary.playbooks.serializer import serialize_playbook_file  # noqa: PLC0415

    project_root = require_project_root()
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    pb_path = playbooks_dir / f"{slug}.md"

    if not pb_path.exists():
        available = (
            sorted(p.stem for p in playbooks_dir.glob("*.md")) if playbooks_dir.is_dir() else []
        )
        if available:
            error(f"Playbook not found: '{slug}'\nAvailable playbooks: " + ", ".join(available))
        else:
            error(
                f"Playbook not found: '{slug}'\n"
                "No playbooks exist yet. Run `lexi playbook new` first."
            )
        hint("Run `lexi search --type playbook` to browse all playbooks.")
        raise typer.Exit(1)

    pb = parse_playbook_file(pb_path)
    if pb is None:
        error(f"Failed to parse playbook file: {pb_path.relative_to(project_root)}")
        raise typer.Exit(1)

    today = date.today()
    pb.frontmatter.last_verified = today
    content = serialize_playbook_file(pb)
    pb_path.write_text(content, encoding="utf-8")

    info(f"Verified '{pb.frontmatter.title}' -- last_verified set to {today.isoformat()}")


# ---------------------------------------------------------------------------
# playbook deprecate
# ---------------------------------------------------------------------------


@playbook_app.command("deprecate")
def playbook_deprecate(
    slug: Annotated[
        str,
        typer.Argument(help="Playbook file slug (filename stem, e.g. 'version-bump')."),
    ],
    *,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="Slug of the playbook that supersedes this one."),
    ] = None,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for deprecation."),
    ] = None,
) -> None:
    """Set a playbook's status to deprecated."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415
    from lexibrary.playbooks.serializer import serialize_playbook_file  # noqa: PLC0415

    project_root = require_project_root()
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    pb_path = playbooks_dir / f"{slug}.md"

    if not pb_path.exists():
        available = (
            sorted(p.stem for p in playbooks_dir.glob("*.md")) if playbooks_dir.is_dir() else []
        )
        if available:
            error(f"Playbook not found: '{slug}'\nAvailable playbooks: " + ", ".join(available))
        else:
            error(
                f"Playbook not found: '{slug}'\n"
                "No playbooks exist yet. Run `lexi playbook new` first."
            )
        hint("Run `lexi search --type playbook` to browse all playbooks.")
        raise typer.Exit(1)

    pb = parse_playbook_file(pb_path)
    if pb is None:
        error(f"Failed to parse playbook file: {pb_path.relative_to(project_root)}")
        raise typer.Exit(1)

    if pb.frontmatter.status == "deprecated":
        error(f"Already deprecated: '{pb.frontmatter.title}'")
        raise typer.Exit(1)

    # Update status, set deprecated_at timestamp, and optionally superseded_by
    timestamp = datetime.now(tz=UTC).replace(microsecond=0)
    pb.frontmatter.status = "deprecated"
    pb.frontmatter.deprecated_at = timestamp

    if superseded_by is not None:
        pb.frontmatter.superseded_by = superseded_by

    # If reason provided, append deprecation note to body
    if reason is not None:
        deprecation_note = f"\n\n> **Deprecated:** {reason}\n"
        pb.body = (
            pb.body.rstrip("\n") + deprecation_note if pb.body else deprecation_note.lstrip("\n")
        )

    content = serialize_playbook_file(pb)
    pb_path.write_text(content, encoding="utf-8")

    info(
        f"Deprecated '{pb.frontmatter.title}' -- "
        f"status set to deprecated at {timestamp.isoformat()}"
    )


# ---------------------------------------------------------------------------
# playbook comment
# ---------------------------------------------------------------------------


@playbook_app.command("comment")
def playbook_comment(
    slug: Annotated[
        str,
        typer.Argument(help="Playbook file slug (filename stem, e.g. 'version-bump')."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a playbook's sidecar comment file."""
    from lexibrary.lifecycle.playbook_comments import (  # noqa: PLC0415
        append_playbook_comment,
        playbook_comment_path,
    )

    project_root = require_project_root()
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    pb_path = playbooks_dir / f"{slug}.md"

    if not pb_path.exists():
        available = (
            sorted(p.stem for p in playbooks_dir.glob("*.md")) if playbooks_dir.is_dir() else []
        )
        if available:
            error(f"Playbook not found: '{slug}'\nAvailable playbooks: " + ", ".join(available))
        else:
            error(
                f"Playbook not found: '{slug}'\n"
                "No playbooks exist yet. Run `lexi playbook new` first."
            )
        hint("Run `lexi search --type playbook` to browse all playbooks.")
        raise typer.Exit(1)

    append_playbook_comment(pb_path, body)
    comment_file = playbook_comment_path(pb_path)
    info(f"Comment added for playbook '{slug}' -- {comment_file.relative_to(project_root)}")
