"""Concept management CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import require_project_root

concept_app = typer.Typer(help="Concept management commands.", rich_markup_mode=None)


@concept_app.command("new")
def concept_new(
    name: Annotated[
        str,
        typer.Argument(help="Name for the new concept."),
    ],
    *,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag to add to the concept (repeatable)."),
    ] = None,
) -> None:
    """Create a concept file from template and return the file path."""
    from lexibrary.wiki.template import (  # noqa: PLC0415
        concept_file_path,
        render_concept_template,
    )

    project_root = require_project_root()
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    target = concept_file_path(name, concepts_dir)

    if target.exists():
        error(f"Concept file already exists: {target.relative_to(project_root)}")
        raise typer.Exit(1)

    content = render_concept_template(name, tags=tag)
    target.write_text(content, encoding="utf-8")

    slug = target.stem
    info(f"Created {target.relative_to(project_root)} (slug: {slug})")

    # Blank-section warnings for expected-but-empty fields
    blank_sections: list[str] = []
    if not tag:
        blank_sections.append("tags")
    if blank_sections:
        info(f"Note: The following sections are blank: {', '.join(blank_sections)}")


@concept_app.command("link")
def concept_link(
    slug: Annotated[
        str,
        typer.Argument(help="Concept slug (filename stem, e.g. 'ScopeRoot')."),
    ],
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file whose design file should receive the wikilink."),
    ],
) -> None:
    """Add a [[wikilink]] to a design file and return confirmation."""
    from lexibrary.artifacts.design_file_parser import parse_design_file  # noqa: PLC0415
    from lexibrary.artifacts.design_file_serializer import serialize_design_file  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

    project_root = require_project_root()

    # Verify concept exists by slug (filename stem)
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concept_path = concepts_dir / f"{slug}.md"
    if not concept_path.exists():
        # List available slugs for helpful error
        available = (
            sorted(p.stem for p in concepts_dir.glob("*.md")) if concepts_dir.is_dir() else []
        )
        if available:
            error(f"Concept not found: '{slug}'\nAvailable concepts: " + ", ".join(available))
        else:
            error(
                f"Concept not found: '{slug}'\n"
                "No concepts exist yet. Run `lexi concept new <name>` first."
            )
        raise typer.Exit(1)

    # Parse to get the concept title for the wikilink
    concept = parse_concept_file(concept_path)
    concept_name = concept.frontmatter.title if concept else slug

    # Find design file
    target = Path(source_file).resolve()
    if not target.exists():
        error(f"Source file not found: {source_file}")
        hint("Check the file path and ensure the file exists on disk.")
        raise typer.Exit(1)

    design_path = mirror_path(project_root, target)
    if not design_path.exists():
        warn(f"No design file found for {source_file}")
        info(f"Run `lexictl update {source_file}` to generate one first.")
        raise typer.Exit(1)

    # Parse, add wikilink, re-serialize
    design = parse_design_file(design_path)
    if design is None:
        error(f"Failed to parse design file: {design_path}")
        raise typer.Exit(1)

    # Check if already linked
    if concept_name in design.wikilinks:
        warn(f"Already linked: '{concept_name}' in {design_path.relative_to(project_root)}")
        return

    design.wikilinks.append(concept_name)
    serialized = serialize_design_file(design)
    design_path.write_text(serialized, encoding="utf-8")

    info(f"Linked [[{concept_name}]] to {design_path.relative_to(project_root)}")


@concept_app.command("comment")
def concept_comment(
    slug: Annotated[
        str,
        typer.Argument(help="Concept slug (filename stem, e.g. 'scope-root')."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", "-b", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a concept and return confirmation."""
    from lexibrary.lifecycle.concept_comments import append_concept_comment  # noqa: PLC0415

    project_root = require_project_root()

    # Validate concept file exists
    concept_path = project_root / ".lexibrary" / "concepts" / f"{slug}.md"
    if not concept_path.exists():
        error(f"Concept file not found: {concept_path.relative_to(project_root)}")
        raise typer.Exit(1)

    # Append the comment
    append_concept_comment(project_root, slug, body)

    comment_file = concept_path.with_suffix(".comments.yaml")
    info(f"Comment added for concept {slug} ({comment_file.relative_to(project_root)})")


@concept_app.command("deprecate")
def concept_deprecate(
    slug: Annotated[
        str,
        typer.Argument(help="Concept slug (filename stem, e.g. 'scope-root')."),
    ],
    *,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="Title of the concept that replaces this one."),
    ] = None,
) -> None:
    """Set a concept's status to deprecated and return confirmation."""
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415
    from lexibrary.wiki.serializer import serialize_concept_file  # noqa: PLC0415

    project_root = require_project_root()

    # Validate concept file exists
    concept_path = project_root / ".lexibrary" / "concepts" / f"{slug}.md"
    if not concept_path.exists():
        error(f"Concept file not found: {concept_path.relative_to(project_root)}")
        raise typer.Exit(1)

    # Parse the concept file
    concept = parse_concept_file(concept_path)
    if concept is None:
        error(f"Failed to parse concept file: {concept_path.relative_to(project_root)}")
        raise typer.Exit(1)

    # Already deprecated -- exit 0 with informational message
    if concept.frontmatter.status == "deprecated":
        msg = f"Already deprecated: {concept.frontmatter.title}"
        if concept.frontmatter.superseded_by:
            msg += f" (superseded by {concept.frontmatter.superseded_by})"
        warn(msg)
        return

    # Update status, deprecated_at timestamp, and optional superseded_by
    from datetime import UTC  # noqa: PLC0415
    from datetime import datetime as _datetime

    concept.frontmatter.status = "deprecated"
    concept.frontmatter.deprecated_at = _datetime.now(UTC).replace(microsecond=0)
    if superseded_by is not None:
        concept.frontmatter.superseded_by = superseded_by

    # Re-serialize and write
    serialized = serialize_concept_file(concept)
    concept_path.write_text(serialized, encoding="utf-8")

    # Print confirmation
    msg = f"Deprecated concept {concept.frontmatter.title}"
    if superseded_by:
        msg += f" (superseded by {superseded_by})"
    info(msg)
