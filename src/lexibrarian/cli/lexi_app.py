"""Agent-facing CLI for Lexibrarian — lookups, search, concepts, and Stack Q&A."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrarian.cli._shared import console, require_project_root

lexi_app = typer.Typer(
    name="lexi",
    help=(
        "Agent-facing CLI for Lexibrarian. "
        "Provides lookups, search, concepts, and Stack Q&A for LLM context navigation."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Sub-groups
# ---------------------------------------------------------------------------
stack_app = typer.Typer(help="Stack Q&A management commands.")
lexi_app.add_typer(stack_app, name="stack")

concept_app = typer.Typer(help="Concept management commands.")
lexi_app.add_typer(concept_app, name="concept")


# ---------------------------------------------------------------------------
# Stack helpers (private, used only by stack commands — D2)
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


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


@lexi_app.command()
def lookup(
    file: Annotated[
        Path,
        typer.Argument(help="Source file to look up."),
    ],
) -> None:
    """Return the design file for a source file."""
    import hashlib  # noqa: PLC0415

    from lexibrarian.artifacts.design_file_parser import parse_design_file_metadata  # noqa: PLC0415
    from lexibrarian.config.loader import load_config  # noqa: PLC0415
    from lexibrarian.utils.paths import mirror_path  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    target = Path(file).resolve()

    # Check scope: file must be under scope_root
    scope_abs = (project_root / config.scope_root).resolve()
    try:
        target.relative_to(scope_abs)
    except ValueError:
        console.print(
            f"[yellow]{file}[/yellow] is outside the configured scope_root "
            f"([dim]{config.scope_root}[/dim])."
        )
        raise typer.Exit(1) from None

    # Compute mirror path
    design_path = mirror_path(project_root, target)

    if not design_path.exists():
        console.print(
            f"[yellow]No design file found for[/yellow] {file}\n"
            f"Run [cyan]lexictl update {file}[/cyan] to generate one."
        )
        raise typer.Exit(1)

    # Check staleness
    metadata = parse_design_file_metadata(design_path)
    if metadata is not None:
        try:
            current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if current_hash != metadata.source_hash:
                console.print(
                    "[yellow]Warning:[/yellow] Source file has changed since "
                    "the design file was last generated. "
                    "Run [cyan]lexictl update " + str(file) + "[/cyan] to refresh.\n"
                )
        except OSError:
            pass

    # Display design file content
    content = design_path.read_text(encoding="utf-8")
    console.print(content)

    # Walk parent .aindex files for inherited conventions
    from lexibrarian.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrarian.utils.paths import aindex_path  # noqa: PLC0415

    conventions_by_dir: list[tuple[str, list[str]]] = []
    current_dir = target.parent
    while True:
        try:
            current_dir.relative_to(scope_abs)
        except ValueError:
            break
        idx_path = aindex_path(project_root, current_dir)
        if idx_path.exists():
            aindex = parse_aindex(idx_path)
            if aindex is not None and aindex.local_conventions:
                rel_dir = str(current_dir.relative_to(project_root))
                if rel_dir == ".":
                    rel_dir = ""
                display_dir = f"{rel_dir}/" if rel_dir else "./"
                conventions_by_dir.append((display_dir, list(aindex.local_conventions)))
        if current_dir == scope_abs:
            break
        current_dir = current_dir.parent

    if conventions_by_dir:
        console.print("\n## Applicable Conventions\n")
        for dir_path, convs in conventions_by_dir:
            console.print(f"**From `{dir_path}`:**\n")
            for conv in convs:
                console.print(f"- {conv}")
            console.print()

    # Reverse links from the link graph index (graceful degradation)
    from lexibrarian.linkgraph import open_index  # noqa: PLC0415

    link_graph = open_index(project_root)
    if link_graph is not None:
        rel_path = str(target.relative_to(project_root))

        # Dependents: inbound ast_import links
        import_links = link_graph.reverse_deps(rel_path, link_type="ast_import")
        if import_links:
            console.print("\n## Dependents (imports this file)\n")
            for link in import_links:
                console.print(f"- {link.source_path}")
            console.print()

        # Also Referenced By: all other inbound link types
        link_type_labels: dict[str, str] = {
            "wikilink": "concept wikilink",
            "stack_file_ref": "stack post",
            "stack_concept_ref": "stack concept ref",
            "design_stack_ref": "design stack ref",
            "design_source": "design file",
            "concept_file_ref": "concept file ref",
            "convention_concept_ref": "convention concept ref",
        }
        all_links = link_graph.reverse_deps(rel_path)
        other_links = [lnk for lnk in all_links if lnk.link_type != "ast_import"]
        if other_links:
            console.print("\n## Also Referenced By\n")
            for link in other_links:
                label = link_type_labels.get(link.link_type, link.link_type)
                # Use link_context as the display name when available,
                # otherwise fall back to the source_path
                display_name = link.link_context or link.source_path
                console.print(f"- [[{display_name}]] ({label})")
            console.print()

        link_graph.close()


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


@lexi_app.command()
def index(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory to index."),
    ] = Path("."),
    *,
    recursive: Annotated[
        bool,
        typer.Option("-r", "--recursive", help="Recursively index all directories."),
    ] = False,
) -> None:
    """Generate .aindex file(s) for a directory."""
    from rich.progress import Progress, SpinnerColumn, TextColumn  # noqa: PLC0415

    from lexibrarian.config.loader import load_config  # noqa: PLC0415
    from lexibrarian.indexer.orchestrator import index_directory, index_recursive  # noqa: PLC0415

    project_root = require_project_root()

    # Resolve directory relative to cwd
    target = Path(directory).resolve()

    # Validate directory exists
    if not target.exists():
        console.print(f"[red]Directory not found:[/red] {directory}")
        raise typer.Exit(1)

    if not target.is_dir():
        console.print(f"[red]Not a directory:[/red] {directory}")
        raise typer.Exit(1)

    # Validate directory is within project root
    try:
        target.relative_to(project_root)
    except ValueError:
        console.print(
            f"[red]Directory is outside the project root:[/red] {directory}\n"
            f"Project root: {project_root}"
        )
        raise typer.Exit(1) from None

    config = load_config(project_root)

    if recursive:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing...", total=None)

            def _progress_callback(current: int, total: int, name: str) -> None:
                progress.update(task, description=f"Indexing [{current}/{total}] {name}")

            stats = index_recursive(
                target, project_root, config, progress_callback=_progress_callback
            )

        console.print(
            f"\n[green]Indexing complete.[/green] "
            f"{stats.directories_indexed} directories indexed, "
            f"{stats.files_found} files found"
            + (f", [red]{stats.errors} errors[/red]" if stats.errors else "")
            + "."
        )
    else:
        output_path = index_directory(target, project_root, config)
        console.print(f"[green]Wrote[/green] {output_path}")


# ---------------------------------------------------------------------------
# concepts
# ---------------------------------------------------------------------------


@lexi_app.command()
def concepts(
    topic: Annotated[
        str | None,
        typer.Argument(help="Optional topic to search for."),
    ] = None,
) -> None:
    """List or search concept files."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrarian.wiki.index import ConceptIndex  # noqa: PLC0415

    project_root = require_project_root()
    concepts_dir = project_root / ".lexibrary" / "concepts"
    idx = ConceptIndex.load(concepts_dir)

    if len(idx) == 0:
        console.print(
            "[yellow]No concepts found.[/yellow] "
            "Run [cyan]lexi concept new <name>[/cyan] to create one."
        )
        return

    if topic:
        results = idx.search(topic)
        if not results:
            console.print(f"[yellow]No concepts matching[/yellow] '{topic}'")
            return
        title = f"Concepts matching '{topic}'"
    else:
        results = [c for name in idx.names() if (c := idx.find(name)) is not None]
        title = "All concepts"

    table = Table(title=title)
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Tags")
    table.add_column("Summary", max_width=50)

    for concept in results:
        fm = concept.frontmatter
        status_style = {
            "active": "green",
            "draft": "yellow",
            "deprecated": "red",
        }.get(fm.status, "dim")
        table.add_row(
            fm.title,
            f"[{status_style}]{fm.status}[/{status_style}]",
            ", ".join(fm.tags) if fm.tags else "",
            concept.summary[:50] if concept.summary else "",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# concept new
# ---------------------------------------------------------------------------


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
    """Create a new concept file from template."""
    from lexibrarian.wiki.template import (  # noqa: PLC0415
        concept_file_path,
        render_concept_template,
    )

    project_root = require_project_root()
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    target = concept_file_path(name, concepts_dir)

    if target.exists():
        console.print(f"[red]Concept file already exists:[/red] {target.relative_to(project_root)}")
        raise typer.Exit(1)

    content = render_concept_template(name, tags=tag)
    target.write_text(content, encoding="utf-8")

    console.print(f"[green]Created[/green] {target.relative_to(project_root)}")


# ---------------------------------------------------------------------------
# concept link
# ---------------------------------------------------------------------------


@concept_app.command("link")
def concept_link(
    concept_name: Annotated[
        str,
        typer.Argument(help="Concept name to link."),
    ],
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file whose design file should receive the wikilink."),
    ],
) -> None:
    """Add a wikilink to a source file's design file."""
    from lexibrarian.artifacts.design_file_parser import parse_design_file  # noqa: PLC0415
    from lexibrarian.artifacts.design_file_serializer import serialize_design_file  # noqa: PLC0415
    from lexibrarian.utils.paths import mirror_path  # noqa: PLC0415
    from lexibrarian.wiki.index import ConceptIndex  # noqa: PLC0415

    project_root = require_project_root()

    # Verify concept exists
    concepts_dir = project_root / ".lexibrary" / "concepts"
    idx = ConceptIndex.load(concepts_dir)
    if concept_name not in idx:
        console.print(
            f"[red]Concept not found:[/red] '{concept_name}'\n"
            "Available concepts: " + ", ".join(idx.names())
            if idx.names()
            else f"[red]Concept not found:[/red] '{concept_name}'\n"
            "No concepts exist yet. Run [cyan]lexi concept new <name>[/cyan] first."
        )
        raise typer.Exit(1)

    # Find design file
    target = Path(source_file).resolve()
    if not target.exists():
        console.print(f"[red]Source file not found:[/red] {source_file}")
        raise typer.Exit(1)

    design_path = mirror_path(project_root, target)
    if not design_path.exists():
        console.print(
            f"[yellow]No design file found for[/yellow] {source_file}\n"
            f"Run [cyan]lexictl update {source_file}[/cyan] to generate one first."
        )
        raise typer.Exit(1)

    # Parse, add wikilink, re-serialize
    design = parse_design_file(design_path)
    if design is None:
        console.print(f"[red]Failed to parse design file:[/red] {design_path}")
        raise typer.Exit(1)

    # Check if already linked
    if concept_name in design.wikilinks:
        console.print(
            f"[yellow]Already linked:[/yellow] '{concept_name}' "
            f"in {design_path.relative_to(project_root)}"
        )
        return

    design.wikilinks.append(concept_name)
    serialized = serialize_design_file(design)
    design_path.write_text(serialized, encoding="utf-8")

    console.print(
        f"[green]Linked[/green] [[{concept_name}]] to {design_path.relative_to(project_root)}"
    )


# ---------------------------------------------------------------------------
# Stack commands
# ---------------------------------------------------------------------------


@stack_app.command("post")
def stack_post(
    *,
    title: Annotated[
        str,
        typer.Option("--title", help="Title for the new stack post."),
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
) -> None:
    """Create a new Stack post with auto-assigned ID."""
    from lexibrarian.stack.template import render_post_template  # noqa: PLC0415

    project_root = require_project_root()
    sd = _stack_dir(project_root)

    if not tag:
        console.print("[red]At least one --tag is required.[/red]")
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
    )
    post_path.write_text(content, encoding="utf-8")

    rel = post_path.relative_to(project_root)
    console.print(f"[green]Created[/green] {rel}")
    console.print(
        "[dim]Fill in the ## Problem and ### Evidence sections, "
        "then share the post ID with your team.[/dim]"
    )


@stack_app.command("search")
def stack_search(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query string."),
    ] = None,
    *,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Filter by tag."),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Filter by file scope path."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status (open/resolved/outdated/duplicate)."),
    ] = None,
    concept: Annotated[
        str | None,
        typer.Option("--concept", help="Filter by concept name."),
    ] = None,
) -> None:
    """Search Stack posts by query and/or filters."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrarian.stack.index import StackIndex  # noqa: PLC0415

    project_root = require_project_root()
    idx = StackIndex.build(project_root)

    # Start with all or query results
    results = idx.search(query) if query else list(idx)

    # Apply filters
    if tag:
        tag_set = {p.frontmatter.id for p in idx.by_tag(tag)}
        results = [p for p in results if p.frontmatter.id in tag_set]
    if scope:
        scope_set = {p.frontmatter.id for p in idx.by_scope(scope)}
        results = [p for p in results if p.frontmatter.id in scope_set]
    if status:
        results = [p for p in results if p.frontmatter.status == status]
    if concept:
        concept_set = {p.frontmatter.id for p in idx.by_concept(concept)}
        results = [p for p in results if p.frontmatter.id in concept_set]

    if not results:
        console.print("[yellow]No posts found.[/yellow]")
        return

    table = Table(title="Stack Posts")
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Votes", justify="right")
    table.add_column("Title")
    table.add_column("Tags")

    for post in results:
        fm = post.frontmatter
        status_style = {
            "open": "green",
            "resolved": "blue",
            "outdated": "yellow",
            "duplicate": "red",
        }.get(fm.status, "dim")
        table.add_row(
            fm.id,
            f"[{status_style}]{fm.status}[/{status_style}]",
            str(fm.votes),
            fm.title,
            ", ".join(fm.tags),
        )

    console.print(table)


@stack_app.command("answer")
def stack_answer(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", help="Answer body text."),
    ],
    author: Annotated[
        str,
        typer.Option("--author", help="Author of the answer."),
    ] = "user",
) -> None:
    """Append a new answer to a Stack post."""
    from lexibrarian.stack.mutations import add_answer  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    updated = add_answer(post_path, author=author, body=body)
    last_answer = updated.answers[-1]
    console.print(f"[green]Added answer A{last_answer.number}[/green] to {post_id}")


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
    answer: Annotated[
        int | None,
        typer.Option("--answer", help="Answer number to vote on (omit to vote on post)."),
    ] = None,
    comment: Annotated[
        str | None,
        typer.Option("--comment", help="Comment (required for downvotes)."),
    ] = None,
    author: Annotated[
        str,
        typer.Option("--author", help="Author of the vote."),
    ] = "user",
) -> None:
    """Record an upvote or downvote on a post or answer."""
    from lexibrarian.stack.mutations import record_vote  # noqa: PLC0415

    project_root = require_project_root()

    if direction not in ("up", "down"):
        console.print("[red]Direction must be 'up' or 'down'.[/red]")
        raise typer.Exit(1)

    if direction == "down" and comment is None:
        console.print("[red]Downvotes require --comment.[/red]")
        raise typer.Exit(1)

    post_path = _find_post_path(project_root, post_id)
    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    target = f"A{answer}" if answer is not None else "post"

    try:
        updated = record_vote(
            post_path,
            target=target,
            direction=direction,
            author=author,
            comment=comment,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    if answer is not None:
        for a in updated.answers:
            if a.number == answer:
                console.print(
                    f"[green]Recorded {direction}vote[/green] on A{answer} (votes: {a.votes})"
                )
                return
    else:
        console.print(
            f"[green]Recorded {direction}vote[/green] on {post_id} "
            f"(votes: {updated.frontmatter.votes})"
        )


@stack_app.command("accept")
def stack_accept(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
    *,
    answer_num: Annotated[
        int,
        typer.Option("--answer", help="Answer number to accept."),
    ],
) -> None:
    """Mark an answer as accepted and set the post to resolved."""
    from lexibrarian.stack.mutations import accept_answer  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    try:
        accept_answer(post_path, answer_num)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(f"[green]Accepted A{answer_num}[/green] on {post_id} — status set to resolved")


@stack_app.command("view")
def stack_view(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Display the full content of a Stack post."""
    from rich.markdown import Markdown  # noqa: PLC0415
    from rich.panel import Panel  # noqa: PLC0415

    from lexibrarian.stack.parser import parse_stack_post  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    post = parse_stack_post(post_path)
    if post is None:
        console.print(f"[red]Failed to parse post:[/red] {post_id}")
        raise typer.Exit(1)

    fm = post.frontmatter

    # Header
    status_style = {
        "open": "green",
        "resolved": "blue",
        "outdated": "yellow",
        "duplicate": "red",
    }.get(fm.status, "dim")

    header = (
        f"[bold]{fm.title}[/bold]\n"
        f"[{status_style}]{fm.status}[/{status_style}] | "
        f"Votes: {fm.votes} | Tags: {', '.join(fm.tags)} | "
        f"Created: {fm.created.isoformat()} | Author: {fm.author}"
    )
    if fm.bead:
        header += f" | Bead: {fm.bead}"
    if fm.refs.files:
        header += f"\nFiles: {', '.join(fm.refs.files)}"
    if fm.refs.concepts:
        header += f"\nConcepts: {', '.join(fm.refs.concepts)}"
    if fm.duplicate_of:
        header += f"\nDuplicate of: {fm.duplicate_of}"

    console.print(Panel(header, title=fm.id, border_style="cyan"))

    # Problem
    console.print("\n[bold]## Problem[/bold]\n")
    console.print(Markdown(post.problem))

    # Evidence
    if post.evidence:
        console.print("\n[bold]### Evidence[/bold]\n")
        for item in post.evidence:
            console.print(f"  - {item}")

    # Answers
    if post.answers:
        console.print(f"\n[bold]## Answers ({len(post.answers)})[/bold]\n")
        for a in post.answers:
            accepted_badge = " [green](accepted)[/green]" if a.accepted else ""
            console.print(
                f"[bold]### A{a.number}[/bold]{accepted_badge}  "
                f"Votes: {a.votes} | {a.date.isoformat()} | {a.author}"
            )
            console.print(Markdown(a.body))
            if a.comments:
                console.print("  [dim]Comments:[/dim]")
                for c in a.comments:
                    console.print(f"    {c}")
            console.print()
    else:
        console.print("\n[dim]No answers yet.[/dim]")


@stack_app.command("list")
def stack_list(
    *,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status."),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Filter by tag."),
    ] = None,
) -> None:
    """List Stack posts with optional filters."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrarian.stack.index import StackIndex  # noqa: PLC0415

    project_root = require_project_root()
    idx = StackIndex.build(project_root)

    results = list(idx)

    if status:
        results = [p for p in results if p.frontmatter.status == status]
    if tag:
        tag_set = {p.frontmatter.id for p in idx.by_tag(tag)}
        results = [p for p in results if p.frontmatter.id in tag_set]

    if not results:
        console.print("[yellow]No posts found.[/yellow]")
        return

    table = Table(title="Stack Posts")
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Votes", justify="right")
    table.add_column("Title")
    table.add_column("Tags")

    for post in results:
        fm = post.frontmatter
        status_style = {
            "open": "green",
            "resolved": "blue",
            "outdated": "yellow",
            "duplicate": "red",
        }.get(fm.status, "dim")
        table.add_row(
            fm.id,
            f"[{status_style}]{fm.status}[/{status_style}]",
            str(fm.votes),
            fm.title,
            ", ".join(fm.tags),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------


@lexi_app.command()
def describe(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory whose .aindex billboard to update."),
    ],
    description: Annotated[
        str,
        typer.Argument(help="New billboard description for the directory."),
    ],
) -> None:
    """Update the billboard description in a directory's .aindex file."""
    from lexibrarian.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrarian.artifacts.aindex_serializer import serialize_aindex  # noqa: PLC0415
    from lexibrarian.utils.paths import aindex_path  # noqa: PLC0415

    project_root = require_project_root()

    target = Path(directory).resolve()

    # Validate directory exists
    if not target.exists():
        console.print(f"[red]Directory not found:[/red] {directory}")
        raise typer.Exit(1)

    if not target.is_dir():
        console.print(f"[red]Not a directory:[/red] {directory}")
        raise typer.Exit(1)

    # Validate directory is within project root
    try:
        target.relative_to(project_root)
    except ValueError:
        console.print(
            f"[red]Directory is outside the project root:[/red] {directory}\n"
            f"Project root: {project_root}"
        )
        raise typer.Exit(1) from None

    # Find the .aindex file
    aindex_file = aindex_path(project_root, target)

    if not aindex_file.exists():
        console.print(
            f"[yellow]No .aindex file found for[/yellow] {directory}\n"
            f"Run [cyan]lexi index {directory}[/cyan] to generate one first."
        )
        raise typer.Exit(1)

    # Parse, update billboard, re-serialize
    aindex = parse_aindex(aindex_file)
    if aindex is None:
        console.print(f"[red]Failed to parse .aindex file:[/red] {aindex_file}")
        raise typer.Exit(1)

    aindex.billboard = description
    serialized = serialize_aindex(aindex)
    aindex_file.write_text(serialized, encoding="utf-8")

    console.print(f"[green]Updated[/green] billboard for [cyan]{directory}[/cyan]")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@lexi_app.command()
def search(
    query: Annotated[
        str | None,
        typer.Argument(help="Free-text search query."),
    ] = None,
    *,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Filter by tag across all artifact types."),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Filter by file scope path."),
    ] = None,
) -> None:
    """Search across concepts, design files, and Stack posts."""
    from lexibrarian.linkgraph import open_index  # noqa: PLC0415
    from lexibrarian.search import unified_search  # noqa: PLC0415

    if query is None and tag is None and scope is None:
        console.print("[yellow]Provide a query, --tag, or --scope to search.[/yellow]")
        raise typer.Exit(1)

    project_root = require_project_root()

    link_graph = open_index(project_root)
    try:
        results = unified_search(
            project_root, query=query, tag=tag, scope=scope, link_graph=link_graph
        )
    finally:
        if link_graph is not None:
            link_graph.close()

    if not results.has_results():
        console.print("[yellow]No results found.[/yellow]")
        return

    results.render(console)
