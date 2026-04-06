"""Convention lifecycle management CLI commands."""

from __future__ import annotations

from typing import Annotated, Literal

import typer

from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import require_project_root

convention_app = typer.Typer(
    help="Convention lifecycle management commands.", rich_markup_mode=None
)


# ---------------------------------------------------------------------------
# convention new
# ---------------------------------------------------------------------------


@convention_app.command("new")
def convention_new(
    *,
    scope_value: Annotated[
        str,
        typer.Option(
            "--scope",
            help=(
                "Convention scope: 'project' for repo-wide, or one or more "
                "comma-separated directory paths (e.g. 'src/auth' or "
                "'src/lexibrary/cli/, src/lexibrary/services/'). "
                "Each path must be an existing directory relative to the project root."
            ),
        ),
    ],
    body: Annotated[
        str,
        typer.Option("--body", help="Convention body text (first paragraph is the rule)."),
    ],
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag to add (repeatable)."),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Convention title (derived from body if omitted)."),
    ] = None,
    source: Annotated[
        str,
        typer.Option("--source", help="Convention source: 'user' or 'agent'."),
    ] = "user",
    alias: Annotated[
        list[str] | None,
        typer.Option("--alias", help="Short alias for the convention (repeatable)."),
    ] = None,
) -> None:
    """Create a convention file and return its path. Status defaults to draft."""
    from lexibrary.artifacts.convention import (  # noqa: PLC0415
        ConventionFile,
        ConventionFileFrontmatter,
        convention_file_path,
        convention_slug,
    )
    from lexibrary.artifacts.ids import next_artifact_id  # noqa: PLC0415
    from lexibrary.artifacts.title_check import find_title_matches  # noqa: PLC0415
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    # Derive title from body if not provided
    resolved_title = title if title else body[:60].strip()

    # Title collision detection
    title_result = find_title_matches(resolved_title, "convention", project_root)
    if title_result.has_same_type:
        match = title_result.same_type[0]
        rel = match.file_path.relative_to(project_root)
        error(f"A convention with this title already exists: {rel}")
        hint("Edit the existing convention instead of creating a duplicate.")
        raise typer.Exit(1)
    if title_result.has_cross_type:
        for match in title_result.cross_type:
            rel = match.file_path.relative_to(project_root)
            warn(f"Related {match.kind} with same title exists: {rel}")

    # Check for duplicate slug (match ID-prefixed filenames)
    slug = convention_slug(resolved_title)
    existing_matches = list(conventions_dir.glob(f"CV-*-{slug}.md"))
    if existing_matches:
        existing = existing_matches[0]
        error(
            f"Convention already exists: {existing.relative_to(project_root)}\n"
            f"Edit the existing file instead of creating a duplicate."
        )
        raise typer.Exit(1)

    # Validate scope paths exist
    if scope_value != "project":
        from lexibrary.artifacts.convention import split_scope  # noqa: PLC0415

        scope_paths = split_scope(scope_value)
        if not scope_paths:
            error("Scope must be 'project' or at least one directory path.")
            raise typer.Exit(1)
        missing = [p for p in scope_paths if not (project_root / p).is_dir()]
        if missing:
            error(
                f"Scope director{'ies do' if len(missing) > 1 else 'y does'} not exist: "
                + ", ".join(missing)
            )
            hint("Each scope path must be an existing directory relative to the project root.")
            raise typer.Exit(1)

    # Set defaults based on source
    conv_status: Literal["draft", "active", "deprecated"]
    if source == "agent":
        conv_status = "draft"
        conv_priority = -1
    else:
        conv_status = "active"
        conv_priority = 0

    convention_id = next_artifact_id("CV", conventions_dir, "CV-*-*.md")
    frontmatter = ConventionFileFrontmatter(
        title=resolved_title,
        id=convention_id,
        scope=scope_value,
        tags=tag or [],
        status=conv_status,
        source=source,  # type: ignore[arg-type]
        priority=conv_priority,
        aliases=alias or [],
    )
    convention = ConventionFile(frontmatter=frontmatter, body=body)
    content = serialize_convention_file(convention)
    target = convention_file_path(convention_id, resolved_title, conventions_dir)
    target.write_text(content, encoding="utf-8")

    info(f"Created {target.relative_to(project_root)}")


# ---------------------------------------------------------------------------
# convention approve
# ---------------------------------------------------------------------------


@convention_app.command("approve")
def convention_approve(
    slug: Annotated[
        str,
        typer.Argument(help="Convention file slug (filename stem, e.g. 'use-pathspec-gitignore')."),
    ],
) -> None:
    """Promote a draft convention to active status and return confirmation."""
    from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conv_path = conventions_dir / f"{slug}.md"

    if not conv_path.exists():
        available = (
            sorted(p.stem for p in conventions_dir.glob("*.md")) if conventions_dir.is_dir() else []
        )
        if available:
            error(f"Convention not found: '{slug}'\nAvailable conventions: " + ", ".join(available))
        else:
            error(
                f"Convention not found: '{slug}'\n"
                "No conventions exist yet. Run `lexi convention new` first."
            )
        hint("Run `lexi search --type convention` to browse all conventions.")
        raise typer.Exit(1)

    conv = parse_convention_file(conv_path)
    if conv is None:
        error(f"Failed to parse convention file: {conv_path.relative_to(project_root)}")
        raise typer.Exit(1)

    if conv.frontmatter.status == "active":
        warn(f"Already active: '{conv.frontmatter.title}'")
        return

    if conv.frontmatter.status == "deprecated":
        error(
            f"Cannot approve a deprecated convention. "
            f"'{conv.frontmatter.title}' has status 'deprecated'."
        )
        raise typer.Exit(1)

    # Update status and re-serialize
    conv.frontmatter.status = "active"
    content = serialize_convention_file(conv)
    conv_path.write_text(content, encoding="utf-8")

    info(f"Approved '{conv.frontmatter.title}' -- status set to active")


# ---------------------------------------------------------------------------
# convention deprecate
# ---------------------------------------------------------------------------


@convention_app.command("deprecate")
def convention_deprecate(
    slug: Annotated[
        str,
        typer.Argument(help="Convention file slug (filename stem, e.g. 'use-pathspec-gitignore')."),
    ],
) -> None:
    """Set a convention's status to deprecated and return confirmation."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conv_path = conventions_dir / f"{slug}.md"

    if not conv_path.exists():
        available = (
            sorted(p.stem for p in conventions_dir.glob("*.md")) if conventions_dir.is_dir() else []
        )
        if available:
            error(f"Convention not found: '{slug}'\nAvailable conventions: " + ", ".join(available))
        else:
            error(
                f"Convention not found: '{slug}'\n"
                "No conventions exist yet. Run `lexi convention new` first."
            )
        hint("Run `lexi search --type convention` to browse all conventions.")
        raise typer.Exit(1)

    conv = parse_convention_file(conv_path)
    if conv is None:
        error(f"Failed to parse convention file: {conv_path.relative_to(project_root)}")
        raise typer.Exit(1)

    # Already deprecated -- do nothing
    if conv.frontmatter.status == "deprecated":
        warn(f"Already deprecated: '{conv.frontmatter.title}'")
        return

    # Update status, set deprecated_at timestamp, and re-serialize
    timestamp = datetime.now(tz=UTC).replace(microsecond=0)
    conv.frontmatter.status = "deprecated"
    conv.frontmatter.deprecated_at = timestamp
    content = serialize_convention_file(conv)
    conv_path.write_text(content, encoding="utf-8")

    info(
        f"Deprecated '{conv.frontmatter.title}' -- "
        f"status set to deprecated at {timestamp.isoformat()}"
    )


# ---------------------------------------------------------------------------
# convention comment
# ---------------------------------------------------------------------------


@convention_app.command("comment")
def convention_comment(
    slug: Annotated[
        str,
        typer.Argument(help="Convention file slug (filename stem, e.g. 'use-pathspec-gitignore')."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a convention and return confirmation."""
    from lexibrary.lifecycle.convention_comments import (  # noqa: PLC0415
        append_convention_comment,
        convention_comment_path,
    )

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conv_path = conventions_dir / f"{slug}.md"

    if not conv_path.exists():
        available = (
            sorted(p.stem for p in conventions_dir.glob("*.md")) if conventions_dir.is_dir() else []
        )
        if available:
            error(f"Convention not found: '{slug}'\nAvailable conventions: " + ", ".join(available))
        else:
            error(
                f"Convention not found: '{slug}'\n"
                "No conventions exist yet. Run `lexi convention new` first."
            )
        hint("Run `lexi search --type convention` to browse all conventions.")
        raise typer.Exit(1)

    append_convention_comment(conv_path, body)
    comment_file = convention_comment_path(conv_path)
    info(f"Comment added for convention '{slug}' -- {comment_file.relative_to(project_root)}")
