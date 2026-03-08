"""Agent-facing CLI for Lexibrary — lookups, search, concepts, and Stack issue tracking."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast

import typer

from lexibrary.cli._shared import (
    _run_status,
    _run_validate,
    console,
    load_dotenv_if_configured,
    require_project_root,
)
from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root

if TYPE_CHECKING:
    from lexibrary.artifacts.convention import ConventionFile
    from lexibrary.conventions.index import ConventionIndex

lexi_app = typer.Typer(
    name="lexi",
    help=(
        "Agent-facing CLI for Lexibrary. "
        "Provides lookups, search, concepts, and Stack issue tracking for LLM context navigation."
    ),
    no_args_is_help=True,
    callback=load_dotenv_if_configured,
)

# ---------------------------------------------------------------------------
# Sub-groups
# ---------------------------------------------------------------------------
stack_app = typer.Typer(help="Stack issue management commands.")
lexi_app.add_typer(stack_app, name="stack")

concept_app = typer.Typer(help="Concept management commands.")
lexi_app.add_typer(concept_app, name="concept")

convention_app = typer.Typer(help="Convention lifecycle management commands.")
lexi_app.add_typer(convention_app, name="convention")

iwh_app = typer.Typer(help="IWH (I Was Here) signal management commands.")
lexi_app.add_typer(iwh_app, name="iwh")

design_app = typer.Typer(help="Design file management commands.")
lexi_app.add_typer(design_app, name="design")


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


def _render_conventions(
    conventions: Sequence[object],
    total_count: int,
    display_limit: int,
    rel_target: str,
) -> None:
    """Render an Applicable Conventions section grouped by scope.

    Conventions are grouped by their scope field, ordered from most general
    (project) to most specific. Draft conventions are marked with ``[draft]``.
    When truncated, a notice is appended.
    """
    from collections import OrderedDict  # noqa: PLC0415

    from lexibrary.artifacts.convention import ConventionFile  # noqa: PLC0415

    typed_conventions: list[ConventionFile] = [
        c for c in conventions if isinstance(c, ConventionFile)
    ]
    if not typed_conventions:
        return

    console.print("\n## Applicable Conventions\n")

    # Group by scope, preserving order (already sorted root-to-leaf)
    groups: OrderedDict[str, list[ConventionFile]] = OrderedDict()
    for conv in typed_conventions:
        scope = conv.frontmatter.scope
        groups.setdefault(scope, []).append(conv)

    for scope, group in groups.items():
        scope_label = scope if scope != "project" else "project"
        console.print(f"### {scope_label}\n")
        for conv in group:
            draft_marker = " [dim]\\[draft][/dim]" if conv.frontmatter.status == "draft" else ""
            rule_text = conv.rule or conv.frontmatter.title
            console.print(f"- {rule_text}{draft_marker}")
        console.print()

    if total_count > display_limit:
        omitted = total_count - display_limit
        console.print(
            f"[dim]... and {omitted} more -- run `lexi conventions {rel_target}` to see all[/dim]\n"
        )


def _render_known_issues(
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


def _render_iwh_peek(
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


def _estimate_tokens(text: str) -> int:
    """Estimate token count using a character-based heuristic.

    Approximates ~4 characters per token, avoiding the overhead of
    importing a tokenizer for CLI output.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def _truncate_lookup_sections(
    sections: list[tuple[str, str, int]],
    total_budget: int,
) -> list[tuple[str, str]]:
    """Truncate lookup sections to fit within a token budget.

    Sections are provided as ``(name, content, priority)`` tuples where
    lower priority values mean higher importance.  Sections are included
    in priority order until the budget is exhausted.

    Priority order: design (0) > conventions (1) > issues (2) > IWH (3) > links (4)

    Returns a list of ``(name, content)`` tuples for sections that fit.
    """
    # Sort by priority (lower = more important)
    sorted_sections = sorted(sections, key=lambda s: s[2])

    result: list[tuple[str, str]] = []
    used_tokens = 0

    for name, content, _priority in sorted_sections:
        if not content:
            continue
        section_tokens = _estimate_tokens(content)
        if used_tokens + section_tokens <= total_budget:
            result.append((name, content))
            used_tokens += section_tokens
        else:
            # Try to include a truncated version if there's budget left
            remaining = total_budget - used_tokens
            if remaining > 50:
                max_chars = remaining * 4
                truncated = content[:max_chars] + "\n... truncated due to token budget\n"
                result.append((name, truncated))
                used_tokens = total_budget
            break

    return result


def _lookup_directory(
    target: Path,
    project_root: Path,
    config: object,
) -> None:
    """Handle lookup for a directory argument.

    Displays the aindex content, applicable conventions, and IWH signals
    for the given directory.
    """
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    if not isinstance(config, LexibraryConfig):
        return

    rel_target = str(target.relative_to(project_root))

    # Try to find and display the aindex file
    aindex_path = project_root / LEXIBRARY_DIR / "designs" / rel_target / ".aindex"
    aindex = parse_aindex(aindex_path)

    if aindex is not None:
        console.print(f"# {aindex.directory_path}\n")
        console.print(f"{aindex.billboard}\n")

        if aindex.entries:
            console.print("## Child Map\n")
            console.print("| Name | Type | Description |")
            console.print("| --- | --- | --- |")
            for entry in aindex.entries:
                suffix = "/" if entry.entry_type == "dir" else ""
                console.print(
                    f"| `{entry.name}{suffix}` | {entry.entry_type} | {entry.description} |"
                )
            console.print()
    else:
        console.print(f"# {rel_target}\n")
        console.print("[dim]No .aindex file found for this directory.[/dim]\n")

    # Convention delivery
    conventions_dir = project_root / ".lexibrary" / "conventions"
    convention_index = ConventionIndex(conventions_dir)
    convention_index.load()

    if len(convention_index) > 0:
        display_limit = config.conventions.lookup_display_limit
        conventions, total_count = convention_index.find_by_scope_limited(
            rel_target,
            scope_root=config.scope_root,
            limit=display_limit,
        )
        if conventions:
            _render_conventions(conventions, total_count, display_limit, rel_target)

    # IWH signal peek
    iwh_text = _render_iwh_peek(project_root, target)
    if iwh_text:
        console.print(iwh_text)


@lexi_app.command()
def lookup(
    file: Annotated[
        Path,
        typer.Argument(help="Source file or directory to look up."),
    ],
) -> None:
    """Return the design file for a source file, or directory overview for a directory."""
    import hashlib  # noqa: PLC0415

    from lexibrary.artifacts.design_file_parser import parse_design_file_metadata  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(file).resolve()

    # Find project root starting from the target (walks upward)
    start_dir = target if target.is_dir() else target.parent
    try:
        project_root = find_project_root(start=start_dir)
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red]"
            " Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None

    config = load_config(project_root)

    # Check scope: target must be under scope_root
    scope_abs = (project_root / config.scope_root).resolve()
    try:
        target.relative_to(scope_abs)
    except ValueError:
        console.print(
            f"[yellow]{file}[/yellow] is outside the configured scope_root "
            f"([dim]{config.scope_root}[/dim])."
        )
        raise typer.Exit(1) from None

    # Directory lookup mode
    if target.is_dir():
        _lookup_directory(target, project_root, config)
        return

    # --- File lookup mode ---

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

    # Display design file content (always shown, highest priority)
    design_content = design_path.read_text(encoding="utf-8")
    console.print(design_content)

    # Convention delivery via ConventionIndex (always shown, second priority)
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415

    conventions_token_estimate = 0
    conventions_dir = project_root / ".lexibrary" / "conventions"
    convention_index = ConventionIndex(conventions_dir)
    convention_index.load()

    if len(convention_index) > 0:
        rel_target = str(target.relative_to(project_root))
        display_limit = config.conventions.lookup_display_limit
        conventions, total_count = convention_index.find_by_scope_limited(
            rel_target,
            scope_root=config.scope_root,
            limit=display_limit,
        )

        if conventions:
            _render_conventions(conventions, total_count, display_limit, rel_target)
            # Estimate token cost of rendered conventions for budget tracking
            conventions_token_estimate = len(conventions) * 10  # rough estimate

    # Gather supplementary sections for token-budget-aware rendering
    # Priority: issues (2) > IWH (3) > links (4)
    from lexibrary.linkgraph import open_index  # noqa: PLC0415

    link_graph = open_index(project_root)
    issues_text = ""
    links_text_parts: list[str] = []
    if link_graph is not None:
        rel_path = str(target.relative_to(project_root))

        # Known Issues from Stack posts (task 6.1)
        stack_display_limit = config.stack.lookup_display_limit
        issues_text = _render_known_issues(link_graph, rel_path, project_root, stack_display_limit)

        # Dependents: inbound ast_import links
        import_links = link_graph.reverse_deps(rel_path, link_type="ast_import")
        if import_links:
            links_text_parts.append("\n## Dependents (imports this file)\n")
            for link in import_links:
                links_text_parts.append(f"- {link.source_path}")
            links_text_parts.append("")

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
            links_text_parts.append("\n## Also Referenced By\n")
            for link in other_links:
                label = link_type_labels.get(link.link_type, link.link_type)
                display_name = link.link_context or link.source_path
                links_text_parts.append(f"- [[{display_name}]] ({label})")
            links_text_parts.append("")

        link_graph.close()

    links_text = "\n".join(links_text_parts)

    # IWH signal peek (task 6.3)
    iwh_text = _render_iwh_peek(project_root, target)

    # Apply token budget truncation to supplementary sections
    # Design and conventions are always shown; remaining budget goes to
    # issues > IWH > links in priority order
    total_budget = config.token_budgets.lookup_total_tokens
    design_tokens = _estimate_tokens(design_content)
    used_tokens = design_tokens + conventions_token_estimate

    supplementary: list[tuple[str, str, int]] = [
        ("issues", issues_text, 2),
        ("iwh", iwh_text, 3),
        ("links", links_text, 4),
    ]
    remaining_budget = max(0, total_budget - used_tokens)
    truncated = _truncate_lookup_sections(supplementary, remaining_budget)

    for _name, section_content in truncated:
        if section_content:
            console.print(section_content)


# ---------------------------------------------------------------------------
# concepts
# ---------------------------------------------------------------------------


@lexi_app.command()
def concepts(
    topic: Annotated[
        str | None,
        typer.Argument(help="Optional topic to search for."),
    ] = None,
    *,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Filter by tag (repeatable, AND logic)."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by status: active, draft, or deprecated.",
        ),
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="Include deprecated concepts in results."),
    ] = False,
) -> None:
    """List or search concept files."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415

    # Validate --status value if provided
    valid_statuses = {"active", "draft", "deprecated"}
    if status is not None and status not in valid_statuses:
        console.print(
            f"[red]Invalid status:[/red] '{status}'. "
            f"Must be one of: {', '.join(sorted(valid_statuses))}"
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    concepts_dir = project_root / ".lexibrary" / "concepts"
    idx = ConceptIndex.load(concepts_dir)

    if len(idx) == 0:
        console.print(
            "[yellow]No concepts found.[/yellow] "
            "Run [cyan]lexi concept new <name>[/cyan] to create one."
        )
        return

    # Start with topic search or full list
    if topic:
        results = idx.search(topic)
        if not results:
            console.print(f"[yellow]No concepts matching[/yellow] '{topic}'")
            return
        title = f"Concepts matching '{topic}'"
    else:
        results = [c for name in idx.names() if (c := idx.find(name)) is not None]
        title = "All concepts"

    # Apply --tag filter(s) with AND logic: each tag narrows the result set
    if tag:
        for t in tag:
            tag_set = {c.frontmatter.title for c in idx.by_tag(t)}
            results = [c for c in results if c.frontmatter.title in tag_set]

    # Apply --status filter
    if status:
        results = [c for c in results if c.frontmatter.status == status]

    # Exclude deprecated by default unless --all or --status deprecated
    if not show_all and status != "deprecated":
        results = [c for c in results if c.frontmatter.status != "deprecated"]

    if not results:
        console.print("[yellow]No concepts found matching the given filters.[/yellow]")
        return

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
    console.print(f"\nFound {len(results)} concept(s)")


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
    from lexibrary.wiki.template import (  # noqa: PLC0415
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
    from lexibrary.artifacts.design_file_parser import parse_design_file  # noqa: PLC0415
    from lexibrary.artifacts.design_file_serializer import serialize_design_file  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415
    from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415

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
# concept comment
# ---------------------------------------------------------------------------


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
    """Append a comment to a concept's comment file."""
    from lexibrary.lifecycle.concept_comments import append_concept_comment  # noqa: PLC0415

    project_root = require_project_root()

    # Validate concept file exists
    concept_path = project_root / ".lexibrary" / "concepts" / f"{slug}.md"
    if not concept_path.exists():
        console.print(
            f"[red]Error:[/red] Concept file not found: "
            f"[cyan]{concept_path.relative_to(project_root)}[/cyan]"
        )
        raise typer.Exit(1)

    # Append the comment
    append_concept_comment(project_root, slug, body)

    comment_file = concept_path.with_suffix(".comments.yaml")
    console.print(
        f"[green]Comment added[/green] for concept [cyan]{slug}[/cyan] "
        f"({comment_file.relative_to(project_root)})"
    )


# ---------------------------------------------------------------------------
# concept deprecate
# ---------------------------------------------------------------------------


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
    """Deprecate a concept, optionally specifying a replacement."""
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415
    from lexibrary.wiki.serializer import serialize_concept_file  # noqa: PLC0415

    project_root = require_project_root()

    # Validate concept file exists
    concept_path = project_root / ".lexibrary" / "concepts" / f"{slug}.md"
    if not concept_path.exists():
        console.print(
            f"[red]Error:[/red] Concept file not found: "
            f"[cyan]{concept_path.relative_to(project_root)}[/cyan]"
        )
        raise typer.Exit(1)

    # Parse the concept file
    concept = parse_concept_file(concept_path)
    if concept is None:
        console.print(
            f"[red]Error:[/red] Failed to parse concept file: "
            f"[cyan]{concept_path.relative_to(project_root)}[/cyan]"
        )
        raise typer.Exit(1)

    # Already deprecated — exit 0 with informational message
    if concept.frontmatter.status == "deprecated":
        msg = f"[yellow]Already deprecated:[/yellow] [cyan]{concept.frontmatter.title}[/cyan]"
        if concept.frontmatter.superseded_by:
            msg += f" (superseded by [cyan]{concept.frontmatter.superseded_by}[/cyan])"
        console.print(msg)
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
    msg = f"[green]Deprecated[/green] concept [cyan]{concept.frontmatter.title}[/cyan]"
    if superseded_by:
        msg += f" (superseded by [cyan]{superseded_by}[/cyan])"
    console.print(msg)


# ---------------------------------------------------------------------------
# conventions (top-level list command)
# ---------------------------------------------------------------------------


@lexi_app.command()
def conventions(
    query: Annotated[
        str | None,
        typer.Argument(
            help=(
                "Free-text search query, or a file/directory path for scope-based retrieval. "
                "Omit to list all conventions."
            ),
        ),
    ] = None,
    *,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Filter by tag (repeatable, AND logic)."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by status: active, draft, or deprecated.",
        ),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Filter by scope value."),
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="Include deprecated conventions in results."),
    ] = False,
) -> None:
    """List, search, or filter convention files."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415

    # Validate --status value if provided
    valid_statuses = {"active", "draft", "deprecated"}
    if status is not None and status not in valid_statuses:
        console.print(
            f"[red]Invalid status:[/red] '{status}'. "
            f"Must be one of: {', '.join(sorted(valid_statuses))}"
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"

    if not conventions_dir.is_dir():
        console.print(
            "[yellow]No conventions found.[/yellow] "
            'Run [cyan]lexi convention new --scope project --body "..."[/cyan] to create one.'
        )
        return

    idx = ConventionIndex(conventions_dir)
    idx.load()

    if len(idx) == 0:
        console.print(
            "[yellow]No conventions found.[/yellow] "
            'Run [cyan]lexi convention new --scope project --body "..."[/cyan] to create one.'
        )
        return

    # Determine whether the positional argument is a path (scope retrieval)
    # or a free-text search query
    if query is not None and ("/" in query or "." in query):
        # Looks like a file/directory path — use scope-based retrieval
        from lexibrary.config.loader import load_config  # noqa: PLC0415

        config = load_config(project_root)
        results = idx.find_by_scope(query, scope_root=config.scope_root)
        title = f"Conventions for '{query}'"
    elif query is not None:
        # Free-text search
        results = idx.search(query)
        title = f"Conventions matching '{query}'"
    else:
        results = list(idx.conventions)
        title = "All conventions"

    # Apply --tag filter(s) with AND logic
    if tag:
        for t in tag:
            tag_lower = t.strip().lower()
            results = [
                c
                for c in results
                if any(ct.strip().lower() == tag_lower for ct in c.frontmatter.tags)
            ]

    # Apply --status filter
    if status:
        results = [c for c in results if c.frontmatter.status == status]

    # Apply --scope filter
    if scope:
        results = [c for c in results if c.frontmatter.scope == scope]

    # Exclude deprecated by default unless --all or --status deprecated
    if not show_all and status != "deprecated":
        results = [c for c in results if c.frontmatter.status != "deprecated"]

    if not results:
        console.print("[yellow]No conventions matching the given filters.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Title", style="cyan")
    table.add_column("Scope")
    table.add_column("Status")
    table.add_column("Tags")
    table.add_column("Rule", max_width=60)

    for conv in results:
        fm = conv.frontmatter
        status_style = {
            "active": "green",
            "draft": "yellow",
            "deprecated": "red",
        }.get(fm.status, "dim")
        rule_text = conv.rule[:60] if conv.rule else ""
        table.add_row(
            fm.title,
            fm.scope,
            f"[{status_style}]{fm.status}[/{status_style}]",
            ", ".join(fm.tags) if fm.tags else "",
            rule_text,
        )

    console.print(table)
    console.print(f"\nFound {len(results)} convention(s)")


# ---------------------------------------------------------------------------
# convention new
# ---------------------------------------------------------------------------


@convention_app.command("new")
def convention_new(
    *,
    scope_value: Annotated[
        str,
        typer.Option("--scope", help="Convention scope: 'project' or a directory path."),
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
    """Create a new convention file."""
    from lexibrary.artifacts.convention import (  # noqa: PLC0415
        ConventionFile,
        ConventionFileFrontmatter,
        convention_file_path,
        convention_slug,
    )
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    # Derive title from body if not provided
    resolved_title = title if title else body[:60].strip()

    # Check for duplicate slug
    slug = convention_slug(resolved_title)
    existing = conventions_dir / f"{slug}.md"
    if existing.exists():
        console.print(
            f"[red]Convention already exists:[/red] {existing.relative_to(project_root)}\n"
            f"Edit the existing file instead of creating a duplicate."
        )
        raise typer.Exit(1)

    # Set defaults based on source
    conv_status: Literal["draft", "active", "deprecated"]
    if source == "agent":
        conv_status = "draft"
        conv_priority = -1
    else:
        conv_status = "active"
        conv_priority = 0

    frontmatter = ConventionFileFrontmatter(
        title=resolved_title,
        scope=scope_value,
        tags=tag or [],
        status=conv_status,
        source=source,  # type: ignore[arg-type]
        priority=conv_priority,
        aliases=alias or [],
    )
    convention = ConventionFile(frontmatter=frontmatter, body=body)
    content = serialize_convention_file(convention)
    target = convention_file_path(resolved_title, conventions_dir)
    target.write_text(content, encoding="utf-8")

    console.print(f"[green]Created[/green] {target.relative_to(project_root)}")


# ---------------------------------------------------------------------------
# convention approve
# ---------------------------------------------------------------------------


@convention_app.command("approve")
def convention_approve(
    name: Annotated[
        str,
        typer.Argument(help="Convention title or file slug to approve."),
    ],
) -> None:
    """Promote a draft convention to active status."""
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"

    idx = ConventionIndex(conventions_dir)
    idx.load()

    conv = _find_convention_by_name_or_slug(idx, name)
    if conv is None:
        console.print(
            f"[red]Convention not found:[/red] '{name}'\n"
            + (
                "Available conventions: " + ", ".join(idx.names())
                if idx.names()
                else "No conventions exist yet. Run [cyan]lexi convention new[/cyan] first."
            )
        )
        raise typer.Exit(1)

    if conv.frontmatter.status == "active":
        console.print(f"[yellow]Already active:[/yellow] '{conv.frontmatter.title}'")
        return

    if conv.frontmatter.status == "deprecated":
        console.print(
            f"[red]Cannot approve a deprecated convention.[/red] "
            f"'{conv.frontmatter.title}' has status 'deprecated'."
        )
        raise typer.Exit(1)

    # Update status and re-serialize
    conv.frontmatter.status = "active"
    content = serialize_convention_file(conv)
    if conv.file_path is not None:
        conv.file_path.write_text(content, encoding="utf-8")

    console.print(f"[green]Approved[/green] '{conv.frontmatter.title}' — status set to active")


# ---------------------------------------------------------------------------
# convention deprecate
# ---------------------------------------------------------------------------


@convention_app.command("deprecate")
def convention_deprecate(
    name: Annotated[
        str,
        typer.Argument(help="Convention title or file slug to deprecate."),
    ],
) -> None:
    """Set a convention's status to deprecated."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"

    idx = ConventionIndex(conventions_dir)
    idx.load()

    conv = _find_convention_by_name_or_slug(idx, name)
    if conv is None:
        console.print(
            f"[red]Convention not found:[/red] '{name}'\n"
            + (
                "Available conventions: " + ", ".join(idx.names())
                if idx.names()
                else "No conventions exist yet. Run [cyan]lexi convention new[/cyan] first."
            )
        )
        raise typer.Exit(1)

    # Already deprecated — do nothing
    if conv.frontmatter.status == "deprecated":
        console.print(f"[yellow]Already deprecated:[/yellow] '{conv.frontmatter.title}'")
        return

    # Update status, set deprecated_at timestamp, and re-serialize
    timestamp = datetime.now(tz=UTC).isoformat()
    conv.frontmatter.status = "deprecated"
    conv.frontmatter.deprecated_at = timestamp
    content = serialize_convention_file(conv)
    if conv.file_path is not None:
        conv.file_path.write_text(content, encoding="utf-8")

    console.print(
        f"[green]Deprecated[/green] '{conv.frontmatter.title}' — "
        f"status set to deprecated at {timestamp}"
    )


# ---------------------------------------------------------------------------
# convention comment
# ---------------------------------------------------------------------------


@convention_app.command("comment")
def convention_comment(
    name: Annotated[
        str,
        typer.Argument(help="Convention title or file slug to comment on."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a convention's sibling .comments.yaml file."""
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.lifecycle.convention_comments import (  # noqa: PLC0415
        append_convention_comment,
        convention_comment_path,
    )

    project_root = require_project_root()
    conventions_dir = project_root / ".lexibrary" / "conventions"

    idx = ConventionIndex(conventions_dir)
    idx.load()

    conv = _find_convention_by_name_or_slug(idx, name)
    if conv is None:
        console.print(
            f"[red]Convention not found:[/red] '{name}'\n"
            + (
                "Available conventions: " + ", ".join(idx.names())
                if idx.names()
                else "No conventions exist yet. Run [cyan]lexi convention new[/cyan] first."
            )
        )
        raise typer.Exit(1)

    if conv.file_path is None:
        console.print("[red]Convention file path is unknown.[/red]")
        raise typer.Exit(1)

    append_convention_comment(conv.file_path, body)
    comment_file = convention_comment_path(conv.file_path)
    console.print(
        f"[green]Comment added[/green] to '{conv.frontmatter.title}' — "
        f"{comment_file.relative_to(project_root)}"
    )


# ---------------------------------------------------------------------------
# Convention helpers (private)
# ---------------------------------------------------------------------------


def _find_convention_by_name_or_slug(idx: ConventionIndex, name: str) -> ConventionFile | None:
    """Find a convention by title (case-insensitive) or file slug.

    Returns the ConventionFile or None if not found.
    """
    from lexibrary.artifacts.convention import convention_slug  # noqa: PLC0415

    needle_lower = name.strip().lower()
    needle_slug = convention_slug(name)

    for conv in idx.conventions:
        # Match by title (case-insensitive)
        if conv.frontmatter.title.lower() == needle_lower:
            return conv
        # Match by slug
        if conv.file_path is not None and conv.file_path.stem == needle_slug:
            return conv

    return None


# ---------------------------------------------------------------------------
# Design commands
# ---------------------------------------------------------------------------


@design_app.command("update")
def design_update(
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file to scaffold or display a design file for."),
    ],
) -> None:
    """Display existing or scaffold a new design file for a source file."""
    from lexibrary.archivist.scaffold import generate_design_scaffold  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(source_file).resolve()

    # Find project root starting from the file's directory (walks upward)
    try:
        project_root = find_project_root(start=target.parent)
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red]"
            " Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None

    config = load_config(project_root)

    # Check scope: file must be under scope_root
    scope_abs = (project_root / config.scope_root).resolve()
    try:
        target.relative_to(scope_abs)
    except ValueError:
        console.print(
            f"[red]Error:[/red] {source_file} is outside the configured scope_root "
            f"([dim]{config.scope_root}[/dim])."
        )
        raise typer.Exit(1) from None

    # Compute mirror path
    design_path = mirror_path(project_root, target)

    if design_path.exists():
        # Display existing design file
        rel_design = design_path.relative_to(project_root)
        content = design_path.read_text(encoding="utf-8")
        console.print(f"[cyan]{rel_design}[/cyan]\n")
        console.print(content)
        console.print(
            "\n[dim]Reminder: set `updated_by: agent` in frontmatter after making changes.[/dim]"
        )
    else:
        # Scaffold new design file
        scaffold = generate_design_scaffold(target, project_root)
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(scaffold, encoding="utf-8")
        rel_design = design_path.relative_to(project_root)
        console.print(f"[green]Created design scaffold:[/green] {rel_design}\n")
        console.print(scaffold)


@design_app.command("comment")
def design_comment(
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file to add a design comment for."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", "-b", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a source file's design comment file."""
    from lexibrary.lifecycle.design_comments import append_design_comment  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(source_file).resolve()

    # Find project root starting from the file's directory (walks upward)
    try:
        project_root = find_project_root(start=target.parent)
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red]"
            " Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None

    # Check that the design file exists for this source file
    design_path = mirror_path(project_root, target)
    if not design_path.exists():
        rel_source = target.relative_to(project_root)
        console.print(
            f"[red]Error:[/red] No design file exists for [cyan]{rel_source}[/cyan].\n"
            "Run [cyan]lexi design update "
            f"{rel_source}[/cyan] to create one first."
        )
        raise typer.Exit(1) from None

    # Append the comment
    append_design_comment(project_root, target, body)

    rel_source = target.relative_to(project_root)
    console.print(f"[green]Comment added[/green] for [cyan]{rel_source}[/cyan].")


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
) -> None:
    """Create a new Stack issue post with auto-assigned ID."""
    from lexibrary.stack.template import render_post_template  # noqa: PLC0415

    project_root = require_project_root()
    sd = _stack_dir(project_root)

    if not tag:
        console.print("[red]At least one --tag is required.[/red]")
        raise typer.Exit(1)

    # CLI validation: --resolve requires --finding, --resolution-type requires --resolve
    if resolve and finding is None:
        console.print("[red]--resolve requires --finding.[/red]")
        raise typer.Exit(1)
    if resolution_type is not None and not resolve:
        console.print("[red]--resolution-type requires --resolve.[/red]")
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
    console.print(f"[green]Created[/green] {rel}")
    console.print(
        "[dim]Fill in the ## Problem, ### Context, ### Evidence, and ### Attempts sections, "
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
        typer.Option("--status", help="Filter by status (open/resolved/outdated/duplicate/stale)."),
    ] = None,
    concept: Annotated[
        str | None,
        typer.Option("--concept", help="Filter by concept name."),
    ] = None,
    resolution_type: Annotated[
        str | None,
        typer.Option("--resolution-type", help="Filter by resolution type (e.g. fix, workaround)."),
    ] = None,
    include_stale: Annotated[
        bool,
        typer.Option(
            "--include-stale",
            help="Include stale posts in results (excluded by default).",
        ),
    ] = False,
) -> None:
    """Search Stack issue posts by query and/or filters."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrary.stack.index import StackIndex  # noqa: PLC0415

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
    if resolution_type:
        rt_set = {p.frontmatter.id for p in idx.by_resolution_type(resolution_type)}
        results = [p for p in results if p.frontmatter.id in rt_set]

    # Filter out stale posts by default (unless --include-stale or explicit --status stale)
    if not include_stale and status != "stale":
        results = [p for p in results if p.frontmatter.status != "stale"]

    if not results:
        console.print("[yellow]No matching posts found.[/yellow]")
        console.print()
        console.print(
            "Tip: If you encounter an issue here, document it with:\n"
            '  lexi stack post --title "..." --problem "..." --attempts "..."\n'
            "Even unsolved issues help future agents avoid repeating your work."
        )
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
            "stale": "dim",
        }.get(fm.status, "dim")
        table.add_row(
            fm.id,
            f"[{status_style}]{fm.status}[/{status_style}]",
            str(fm.votes),
            fm.title,
            ", ".join(fm.tags),
        )

    console.print(table)


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
    author: Annotated[
        str,
        typer.Option("--author", help="Author of the finding."),
    ] = "user",
) -> None:
    """Append a new finding to a Stack issue post."""
    from lexibrary.stack.mutations import add_finding  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    updated = add_finding(post_path, author=author, body=body)
    last_finding = updated.findings[-1]
    console.print(f"[green]Added finding F{last_finding.number}[/green] to {post_id}")


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
    author: Annotated[
        str,
        typer.Option("--author", help="Author of the vote."),
    ] = "user",
) -> None:
    """Record an upvote or downvote on an issue post or finding."""
    from lexibrary.stack.mutations import record_vote  # noqa: PLC0415

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

    target = f"F{finding}" if finding is not None else "post"

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

    if finding is not None:
        for a in updated.findings:
            if a.number == finding:
                console.print(
                    f"[green]Recorded {direction}vote[/green] on F{finding} (votes: {a.votes})"
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
    finding_num: Annotated[
        int,
        typer.Option("--finding", help="Finding number to accept."),
    ],
    resolution_type: Annotated[
        str | None,
        typer.Option("--resolution-type", help="Resolution type (e.g. fix, workaround)."),
    ] = None,
) -> None:
    """Mark a finding as accepted and set the post to resolved."""
    from lexibrary.stack.mutations import accept_finding  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    try:
        accept_finding(post_path, finding_num, resolution_type=resolution_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(f"[green]Accepted F{finding_num}[/green] on {post_id} — status set to resolved")


@stack_app.command("view")
def stack_view(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Display the full content of a Stack issue post."""
    from rich.markdown import Markdown  # noqa: PLC0415
    from rich.panel import Panel  # noqa: PLC0415

    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

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
    if fm.resolution_type:
        header += f"\nResolution: {fm.resolution_type}"

    console.print(Panel(header, title=fm.id, border_style="cyan"))

    # Problem
    console.print("\n[bold]## Problem[/bold]\n")
    console.print(Markdown(post.problem))

    # Context
    if post.context:
        console.print("\n[bold]### Context[/bold]\n")
        console.print(Markdown(post.context))

    # Evidence
    if post.evidence:
        console.print("\n[bold]### Evidence[/bold]\n")
        for item in post.evidence:
            console.print(f"  - {item}")

    # Attempts
    if post.attempts:
        console.print("\n[bold]### Attempts[/bold]\n")
        for item in post.attempts:
            console.print(f"  - {item}")

    # Findings
    if post.findings:
        console.print(f"\n[bold]## Findings ({len(post.findings)})[/bold]\n")
        for a in post.findings:
            accepted_badge = " [green](accepted)[/green]" if a.accepted else ""
            console.print(
                f"[bold]### F{a.number}[/bold]{accepted_badge}  "
                f"Votes: {a.votes} | {a.date.isoformat()} | {a.author}"
            )
            console.print(Markdown(a.body))
            if a.comments:
                console.print("  [dim]Comments:[/dim]")
                for c in a.comments:
                    console.print(f"    {c}")
            console.print()
    else:
        console.print("\n[dim]No findings yet.[/dim]")


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
    include_stale: Annotated[
        bool,
        typer.Option(
            "--include-stale",
            help="Include stale posts in listing (excluded by default).",
        ),
    ] = False,
) -> None:
    """List Stack issue posts with optional filters."""
    from rich.table import Table  # noqa: PLC0415

    from lexibrary.stack.index import StackIndex  # noqa: PLC0415

    project_root = require_project_root()
    idx = StackIndex.build(project_root)

    results = list(idx)

    if status:
        results = [p for p in results if p.frontmatter.status == status]
    if tag:
        tag_set = {p.frontmatter.id for p in idx.by_tag(tag)}
        results = [p for p in results if p.frontmatter.id in tag_set]

    # Filter out stale posts by default (unless --include-stale or explicit --status stale)
    if not include_stale and status != "stale":
        results = [p for p in results if p.frontmatter.status != "stale"]

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
            "stale": "dim",
        }.get(fm.status, "dim")
        table.add_row(
            fm.id,
            f"[{status_style}]{fm.status}[/{status_style}]",
            str(fm.votes),
            fm.title,
            ", ".join(fm.tags),
        )

    console.print(table)


@stack_app.command("mark-outdated")
def stack_mark_outdated(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Mark a Stack issue post as outdated."""
    from lexibrary.stack.mutations import mark_outdated  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    mark_outdated(post_path)
    console.print(f"[green]Marked {post_id} as outdated[/green]")


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
    """Mark a Stack issue post as a duplicate of another post."""
    from lexibrary.stack.mutations import mark_duplicate  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    mark_duplicate(post_path, duplicate_of=of)
    console.print(f"[green]Marked {post_id} as duplicate of {of}[/green]")


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
    """Append a comment to a Stack post's comment file."""
    from lexibrary.lifecycle.stack_comments import (  # noqa: PLC0415
        append_stack_comment,
        stack_comment_count,
    )

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    append_stack_comment(project_root, post_id, body)
    count = stack_comment_count(project_root, post_id)
    console.print(
        f"[green]Comment added[/green] for post [cyan]{post_id}[/cyan] "
        f"({count} comment{'s' if count != 1 else ''} total)"
    )


@stack_app.command("stale")
def stack_stale(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Mark a resolved Stack post as stale."""
    from lexibrary.stack.mutations import mark_stale  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    try:
        updated = mark_stale(post_path)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    console.print(
        f"[green]Marked {post_id} as stale[/green] (stale_at: {updated.frontmatter.stale_at})"
    )


@stack_app.command("unstale")
def stack_unstale(
    post_id: Annotated[
        str,
        typer.Argument(help="Post ID (e.g. ST-001)."),
    ],
) -> None:
    """Reverse staleness on a stale Stack post (set back to resolved)."""
    from lexibrary.stack.mutations import mark_unstale  # noqa: PLC0415

    project_root = require_project_root()
    post_path = _find_post_path(project_root, post_id)

    if post_path is None:
        console.print(f"[red]Post not found:[/red] {post_id}")
        raise typer.Exit(1)

    try:
        mark_unstale(post_path)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    console.print(f"[green]Marked {post_id} as resolved (un-staled)[/green]")


# ---------------------------------------------------------------------------
# IWH commands
# ---------------------------------------------------------------------------


@iwh_app.command("write")
def iwh_write(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Source directory for the signal. Defaults to project root."),
    ] = None,
    *,
    scope: Annotated[
        str,
        typer.Option("--scope", "-s", help="Signal scope: incomplete, blocked, or warning."),
    ] = "incomplete",
    body: Annotated[
        str,
        typer.Option("--body", "-b", help="Signal body text describing the situation."),
    ],
    author: Annotated[
        str,
        typer.Option("--author", help="Agent identifier."),
    ] = "agent",
) -> None:
    """Write an IWH signal for a directory."""
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh import IWHScope, write_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import iwh_path  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.iwh.enabled:
        console.print("[yellow]IWH is disabled in project configuration.[/yellow]")
        raise typer.Exit(0)

    valid_scopes = ("warning", "incomplete", "blocked")
    if scope not in valid_scopes:
        console.print(
            f"[red]Invalid scope:[/red] '{scope}'. Must be one of: {', '.join(valid_scopes)}"
        )
        raise typer.Exit(1)

    source_dir = Path(directory).resolve() if directory is not None else project_root
    target_dir = iwh_path(project_root, source_dir).parent

    result_path = write_iwh(target_dir, author=author, scope=cast(IWHScope, scope), body=body)
    rel = result_path.relative_to(project_root)
    console.print(f"[green]Created[/green] IWH signal at {rel} (scope: {scope})")


@iwh_app.command("read")
def iwh_read(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Source directory to read signal from. Defaults to project root."),
    ] = None,
    *,
    peek: Annotated[
        bool,
        typer.Option("--peek", help="Read without consuming (do not delete the signal)."),
    ] = False,
) -> None:
    """Read (and consume) an IWH signal for a directory."""
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh import consume_iwh, read_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import iwh_path  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.iwh.enabled:
        console.print("[yellow]IWH is disabled in project configuration.[/yellow]")
        raise typer.Exit(0)

    source_dir = Path(directory).resolve() if directory is not None else project_root
    target_dir = iwh_path(project_root, source_dir).parent

    iwh = read_iwh(target_dir) if peek else consume_iwh(target_dir)

    if iwh is None:
        console.print("[dim]No IWH signal found.[/dim]")
        return

    scope_styles = {"warning": "yellow", "incomplete": "cyan", "blocked": "red"}
    style = scope_styles.get(iwh.scope, "dim")
    console.print(
        f"[{style}][{iwh.scope.upper()}][/{style}] by {iwh.author} at {iwh.created.isoformat()}"
    )
    if iwh.body:
        console.print()
        console.print(iwh.body)

    if not peek:
        console.print("\n[dim]Signal consumed (deleted).[/dim]")


@iwh_app.command("list")
def iwh_list() -> None:
    """List all IWH signals in the project."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from rich.table import Table  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.iwh.enabled:
        console.print("[yellow]IWH is disabled in project configuration.[/yellow]")
        raise typer.Exit(0)

    results = find_all_iwh(project_root)

    if not results:
        console.print("[dim]No IWH signals found.[/dim]")
        return

    table = Table(title="IWH Signals")
    table.add_column("Directory", style="cyan")
    table.add_column("Scope")
    table.add_column("Author")
    table.add_column("Age")
    table.add_column("Body", max_width=50)

    now = datetime.now(tz=UTC)
    for source_dir, iwh in results:
        scope_styles = {"warning": "yellow", "incomplete": "cyan", "blocked": "red"}
        style = scope_styles.get(iwh.scope, "dim")

        created = iwh.created
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        total_seconds = int((now - created).total_seconds())
        if total_seconds < 3600:
            age = f"{total_seconds // 60}m"
        elif total_seconds < 86400:
            age = f"{total_seconds // 3600}h"
        else:
            age = f"{total_seconds // 86400}d"

        display_dir = f"{source_dir}/" if str(source_dir) != "." else "./"
        body_preview = iwh.body.replace("\n", " ")
        if len(body_preview) > 50:
            body_preview = body_preview[:47] + "..."

        table.add_row(
            display_dir,
            f"[{style}]{iwh.scope}[/{style}]",
            iwh.author,
            age,
            body_preview,
        )

    console.print(table)
    console.print(f"\nFound {len(results)} signal(s)")


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
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrary.artifacts.aindex_serializer import serialize_aindex  # noqa: PLC0415
    from lexibrary.utils.paths import aindex_path  # noqa: PLC0415

    target = Path(directory).resolve()

    # Validate directory exists
    if not target.exists():
        console.print(f"[red]Directory not found:[/red] {directory}")
        raise typer.Exit(1)

    if not target.is_dir():
        console.print(f"[red]Not a directory:[/red] {directory}")
        raise typer.Exit(1)

    # Find project root starting from the target directory (walks upward)
    try:
        project_root = find_project_root(start=target)
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red]"
            " Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None

    # Find the .aindex file
    aindex_file = aindex_path(project_root, target)

    if not aindex_file.exists():
        console.print(
            f"[yellow]No .aindex file found for[/yellow] {directory}\n"
            f"Run [cyan]lexictl index {directory}[/cyan] to generate one first."
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
# validate
# ---------------------------------------------------------------------------


@lexi_app.command()
def validate(
    *,
    severity: Annotated[
        str | None,
        typer.Option(
            "--severity",
            help="Minimum severity to report: error, warning, or info.",
        ),
    ] = None,
    check: Annotated[
        str | None,
        typer.Option(
            "--check",
            help="Run only the named check (see available checks below).",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output results as JSON instead of Rich tables.",
        ),
    ] = False,
) -> None:
    """Run consistency checks on the library."""
    project_root = require_project_root()
    exit_code = _run_validate(project_root, severity=severity, check=check, json_output=json_output)
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@lexi_app.command()
def status(
    path: Annotated[
        Path | None,
        typer.Argument(help="Project directory to check."),
    ] = None,
    *,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Single-line output for hooks/CI."),
    ] = False,
) -> None:
    """Show library health and staleness summary."""
    project_root = require_project_root()
    exit_code = _run_status(project_root, path=path, quiet=quiet, cli_prefix="lexi")
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@lexi_app.command("help")
def agent_help() -> None:
    """Display structured guidance for coding agents working with Lexibrary."""
    from rich.panel import Panel  # noqa: PLC0415
    from rich.text import Text  # noqa: PLC0415

    # -- Command Groups --------------------------------------------------------
    commands_text = Text()
    commands_text.append("Session Start\n", style="bold underline")
    commands_text.append("  lexi orient", style="cyan")
    commands_text.append("              Show project topology, stats, and IWH signals\n")
    commands_text.append("  lexi help", style="cyan")
    commands_text.append("                Show this guidance\n")
    commands_text.append("\n")
    commands_text.append("Lookup & Navigation\n", style="bold underline")
    commands_text.append("  lexi lookup <file>", style="cyan")
    commands_text.append("      Show design file, conventions, and reverse links\n")
    commands_text.append("  lexi search [query]", style="cyan")
    commands_text.append("     Search across concepts, design files, and Stack posts\n")
    commands_text.append("  lexi impact <file>", style="cyan")
    commands_text.append("      Show reverse dependents (--depth, --quiet)\n")
    commands_text.append("\n")
    commands_text.append("Knowledge Management\n", style="bold underline")
    commands_text.append("  lexi concepts [topic]", style="cyan")
    commands_text.append("    List or search concepts (--tag, --status, --all)\n")
    commands_text.append("  lexi concept new <name>", style="cyan")
    commands_text.append("  Create a new concept file (--tag)\n")
    commands_text.append("  lexi concept link <name> <file>", style="cyan")
    commands_text.append("  Add a wikilink to a design file\n")
    commands_text.append("  lexi concept comment <name>", style="cyan")
    commands_text.append("  Add a comment to a concept (--body)\n")
    commands_text.append("  lexi concept deprecate <name>", style="cyan")
    commands_text.append("  Deprecate a concept (--comment, --author)\n")
    commands_text.append("  lexi conventions [query]", style="cyan")
    commands_text.append("  List/search conventions (--tag, --status, --scope, --all)\n")
    commands_text.append("  lexi convention new", style="cyan")
    commands_text.append("      Create a convention (--scope, --body, --tag, --title, --alias)\n")
    commands_text.append("  lexi convention approve <name>", style="cyan")
    commands_text.append("  Promote draft to active\n")
    commands_text.append("  lexi convention deprecate <name>", style="cyan")
    commands_text.append("  Set status to deprecated\n")
    commands_text.append("  lexi convention comment <name>", style="cyan")
    commands_text.append("  Add a comment to a convention (--body)\n")
    commands_text.append("\n")
    commands_text.append("Stack Issues\n", style="bold underline")
    commands_text.append("  lexi stack post", style="cyan")
    commands_text.append("            Post a new issue (--title, --tag, --problem, --finding)\n")
    commands_text.append("  lexi stack search [query]", style="cyan")
    commands_text.append("   Search issues (--tag, --scope, --status, --resolution-type)\n")
    commands_text.append("  lexi stack view <id>", style="cyan")
    commands_text.append("        Read a full issue with findings\n")
    commands_text.append("  lexi stack finding <id>", style="cyan")
    commands_text.append("      Add a finding (--body, --author)\n")
    commands_text.append("  lexi stack vote <id> up|down", style="cyan")
    commands_text.append("  Vote on an issue or finding (--finding, --comment)\n")
    commands_text.append("  lexi stack accept <id>", style="cyan")
    commands_text.append("      Accept a finding (--finding, --resolution-type)\n")
    commands_text.append("  lexi stack list", style="cyan")
    commands_text.append("            List issues (--status, --tag)\n")
    commands_text.append("  ")
    commands_text.append("Lifecycle:\n", style="dim")
    commands_text.append("  lexi stack comment <id>", style="cyan")
    commands_text.append("     Add a comment (--body)\n")
    commands_text.append("  lexi stack mark-outdated <id>", style="cyan")
    commands_text.append(" Mark issue as outdated\n")
    commands_text.append("  lexi stack duplicate <id>", style="cyan")
    commands_text.append("    Mark as duplicate (--of <orig>)\n")
    commands_text.append("  lexi stack stale <id>", style="cyan")
    commands_text.append("        Mark resolved issue as stale\n")
    commands_text.append("  lexi stack unstale <id>", style="cyan")
    commands_text.append("      Reverse staleness (back to resolved)\n")
    commands_text.append("\n")
    commands_text.append("IWH Signals\n", style="bold underline")
    commands_text.append("  lexi iwh write [dir]", style="cyan")
    commands_text.append("      Create signal (--scope, --body, --author)\n")
    commands_text.append("  lexi iwh read [dir]", style="cyan")
    commands_text.append("       Read & consume signal (--peek to preserve)\n")
    commands_text.append("  lexi iwh list", style="cyan")
    commands_text.append("             List all IWH signals in the project\n")
    commands_text.append("\n")
    commands_text.append("Design Files\n", style="bold underline")
    commands_text.append("  lexi design update <file>", style="cyan")
    commands_text.append("   Display or scaffold a design file for a source file\n")
    commands_text.append("  lexi design comment <file>", style="cyan")
    commands_text.append("  Add a comment to a design file (--body)\n")
    commands_text.append("\n")
    commands_text.append("Inspection & Annotation\n", style="bold underline")
    commands_text.append("  lexi status [path]", style="cyan")
    commands_text.append("        Show library health and staleness summary (-q for quiet)\n")
    commands_text.append("  lexi validate", style="cyan")
    commands_text.append("             Run consistency checks (--severity, --check, --json)\n")
    commands_text.append("  lexi describe <dir> <desc>", style="cyan")
    commands_text.append("  Update billboard description in .aindex\n")

    console.print(Panel(commands_text, title="Available Commands", border_style="cyan"))

    # -- Common Workflows ------------------------------------------------------
    workflows_text = Text()
    workflows_text.append("1. Start a new session\n", style="bold")
    workflows_text.append("   lexi orient\n", style="cyan")
    workflows_text.append("   lexi iwh list\n", style="cyan")
    workflows_text.append(
        "   Get project context and check for signals from previous sessions.\n\n"
    )
    workflows_text.append("2. Understand a source file\n", style="bold")
    workflows_text.append("   lexi lookup src/mypackage/module.py\n", style="cyan")
    workflows_text.append("   Read the design file to understand purpose, interface, and\n")
    workflows_text.append("   dependencies. Check the inherited conventions and reverse links\n")
    workflows_text.append("   to see what depends on this file.\n\n")
    workflows_text.append("3. Explore a topic across the codebase\n", style="bold")
    workflows_text.append("   lexi concepts auth --tag security\n", style="cyan")
    workflows_text.append("   lexi search auth --tag security\n", style="cyan")
    workflows_text.append("   Start with concept search to find relevant knowledge articles,\n")
    workflows_text.append("   then use cross-artifact search to find related design files and\n")
    workflows_text.append("   Stack posts.\n\n")
    workflows_text.append("4. Document an issue and capture knowledge\n", style="bold")
    workflows_text.append(
        '   lexi stack post --title "Config fails on startup" --tag config'
        ' --problem "..." --finding "Set extra=forbid" --resolve\n',
        style="cyan",
    )
    workflows_text.append("   Or use the multi-step flow:\n")
    workflows_text.append(
        '   lexi stack post --title "Why does X use Y?" --tag arch\n',
        style="cyan",
    )
    workflows_text.append('   lexi stack finding ST-001 --body "Because ..."\n', style="cyan")
    workflows_text.append(
        "   lexi stack accept ST-001 --finding 1 --resolution-type fix\n",
        style="cyan",
    )
    workflows_text.append("   Create a Stack issue, add a finding, and accept to build\n")
    workflows_text.append("   project knowledge.\n\n")
    workflows_text.append("5. Create and manage conventions\n", style="bold")
    workflows_text.append(
        '   lexi convention new --scope project --body "Use rich console"\n',
        style="cyan",
    )
    workflows_text.append("   lexi conventions\n", style="cyan")
    workflows_text.append('   lexi convention approve "use-rich-console"\n', style="cyan")
    workflows_text.append("   Create conventions to codify project rules, list them, and\n")
    workflows_text.append("   approve drafts when they are ready for enforcement.\n\n")
    workflows_text.append("6. Check library health\n", style="bold")
    workflows_text.append("   lexi status\n", style="cyan")
    workflows_text.append("   lexi validate --severity warning\n", style="cyan")
    workflows_text.append("   Use status to see staleness and coverage at a glance, then run\n")
    workflows_text.append("   validate to find specific issues that need attention.\n")

    console.print(Panel(workflows_text, title="Common Workflows", border_style="green"))

    # -- Navigation Tips -------------------------------------------------------
    tips_text = Text()
    tips_text.append("Wikilinks: ", style="bold")
    tips_text.append("Concept names in [[double brackets]] link design files to concept\n")
    tips_text.append("  articles. Use ")
    tips_text.append("lexi concept link", style="cyan")
    tips_text.append(" to add them.\n\n")
    tips_text.append("Reverse Dependencies: ", style="bold")
    tips_text.append("lexi impact <file>", style="cyan")
    tips_text.append(" shows who imports a file. Use with\n")
    tips_text.append("  ")
    tips_text.append("lexi lookup", style="cyan")
    tips_text.append(" (which shows the full link graph) to trace impact before\n")
    tips_text.append("  making changes.\n\n")
    tips_text.append("Cross-Artifact Search: ", style="bold")
    tips_text.append("lexi search", style="cyan")
    tips_text.append(" queries concepts, design files, and Stack\n")
    tips_text.append(
        "  posts in one command. Combine with --tag and --scope to narrow results.\n\n"
    )
    tips_text.append("Filtering Concepts: ", style="bold")
    tips_text.append("Deprecated concepts are hidden by default. Use ")
    tips_text.append("--all", style="cyan")
    tips_text.append(" to include\n")
    tips_text.append("  them, or ")
    tips_text.append("--status deprecated", style="cyan")
    tips_text.append(" to show only deprecated concepts.\n\n")
    tips_text.append("No project needed: ", style="bold")
    tips_text.append("lexi help", style="cyan")
    tips_text.append(" works anywhere -- no .lexibrary/ directory required.\n")

    console.print(Panel(tips_text, title="Navigation Tips", border_style="yellow"))


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
    from lexibrary.linkgraph import open_index  # noqa: PLC0415
    from lexibrary.search import unified_search  # noqa: PLC0415

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


# ---------------------------------------------------------------------------
# orient (project orientation for agent sessions)
# ---------------------------------------------------------------------------

# Approximate token budget for orient output.
# 1 token ~= 4 characters for English text.
_ORIENT_TOKEN_BUDGET = 2000
_CHARS_PER_TOKEN = 4
_ORIENT_CHAR_BUDGET = _ORIENT_TOKEN_BUDGET * _CHARS_PER_TOKEN


def _collect_file_descriptions(project_root: Path) -> list[tuple[str, str]]:
    """Extract (relative_path, description) pairs for file-level aindex entries.

    Reuses ``_collect_aindex_data()`` from the topology module for .aindex
    discovery, then additionally parses each .aindex file for entries with
    ``entry_type == "file"`` and returns their descriptions.

    Returns a sorted list of ``(dir_path/file_name, description)`` tuples.
    """
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return []

    descriptions: list[tuple[str, str]] = []
    for aindex_path in sorted(lexibrary_root.rglob(".aindex")):
        parsed = parse_aindex(aindex_path)
        if parsed is None:
            continue
        for entry in parsed.entries:
            if entry.entry_type == "file" and entry.description:
                dir_path = parsed.directory_path
                file_rel = f"{dir_path}/{entry.name}" if dir_path != "." else entry.name
                descriptions.append((file_rel, entry.description))

    return sorted(descriptions, key=lambda t: t[0])


def _build_orient_content(project_root: Path) -> str:
    """Build plain-text orientation context for agent sessions.

    Includes TOPOLOGY.md content, file-level descriptions from .aindex
    files (trimmed to approximately ``_ORIENT_TOKEN_BUDGET`` tokens),
    library stats (concept count, convention count, open stack posts),
    and IWH signal summaries (peek only, no consumption).

    Returns an empty string if no .lexibrary/ directory exists.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return ""

    parts: list[str] = []

    # 1. TOPOLOGY.md content
    topology_path = lexibrary_root / "TOPOLOGY.md"
    topology_text = ""
    if topology_path.is_file():
        topology_text = topology_path.read_text(encoding="utf-8").strip()
        if topology_text:
            parts.append(topology_text)

    # 2. File descriptions from .aindex entries
    file_descs = _collect_file_descriptions(project_root)
    if file_descs:
        desc_lines = [f"{path}: {desc}" for path, desc in file_descs]
        parts.append("## File Descriptions\n")
        # Check budget before adding all descriptions
        header_chars = sum(len(p) for p in parts) + len("## File Descriptions\n")
        remaining_budget = _ORIENT_CHAR_BUDGET - header_chars

        if remaining_budget <= 0:
            # Topology alone fills the budget; skip descriptions
            pass
        else:
            # Sort deepest paths first for trimming (more path segments = deeper)
            # We want to *trim* deepest first, so we add shallowest first
            # and stop when budget exhausted.
            sorted_by_depth = sorted(desc_lines, key=lambda line: line.count("/"))

            included: list[str] = []
            chars_used = 0
            for line in sorted_by_depth:
                line_chars = len(line) + 1  # +1 for newline
                if chars_used + line_chars > remaining_budget:
                    break
                included.append(line)
                chars_used += line_chars

            omitted = len(desc_lines) - len(included)
            # Re-sort included lines alphabetically for clean output
            included.sort()

            if included:
                # Replace the placeholder "## File Descriptions\n" with header + lines
                parts[-1] = "## File Descriptions\n\n" + "\n".join(included)

            if omitted > 0:
                parts.append(f"\n({omitted} file descriptions omitted for brevity)")

    # 3. Library stats (concept count, convention count, open stack posts)
    stats = _collect_library_stats(project_root)
    if stats:
        parts.append(stats)

    # 4. IWH signals peek (no consumption)
    iwh_section = _collect_iwh_peek(project_root)
    if iwh_section:
        parts.append(iwh_section)

    return "\n\n".join(parts).strip() if parts else ""


def _collect_library_stats(project_root: Path) -> str:
    """Collect library statistics: concept count, convention count, open stack posts.

    Returns a formatted section string, or empty string if no stats available.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_root = project_root / LEXIBRARY_DIR

    # Count concepts
    concepts_dir = lexibrary_root / "concepts"
    concept_count = 0
    if concepts_dir.is_dir():
        concept_count = len(list(concepts_dir.glob("*.md")))

    # Count conventions
    conventions_dir = lexibrary_root / "conventions"
    convention_count = 0
    if conventions_dir.is_dir():
        convention_count = len(list(conventions_dir.glob("*.md")))

    # Count open stack posts
    stack_dir = lexibrary_root / "stack"
    open_stack_count = 0
    if stack_dir.is_dir():
        from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

        for md_path in stack_dir.glob("ST-*-*.md"):
            post = parse_stack_post(md_path)
            if post is not None and post.frontmatter.status == "open":
                open_stack_count += 1

    if concept_count or convention_count or open_stack_count:
        lines: list[str] = ["## Library Stats\n"]
        lines.append(f"Concepts: {concept_count}")
        lines.append(f"Conventions: {convention_count}")
        lines.append(f"Open stack posts: {open_stack_count}")
        return "\n".join(lines)

    return ""


def _collect_iwh_peek(project_root: Path) -> str:
    """Peek at IWH signals without consuming them.

    Returns a formatted section string, or empty string if no signals found.
    """
    from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415

    results = find_all_iwh(project_root)
    if not results:
        return ""

    lines: list[str] = ["## IWH Signals\n"]
    for source_dir, iwh in results:
        display_dir = f"{source_dir}/" if str(source_dir) != "." else "./"
        body_preview = iwh.body.replace("\n", " ").strip()
        if len(body_preview) > 80:
            body_preview = body_preview[:77] + "..."
        lines.append(f"- [{iwh.scope}] {display_dir} -- {body_preview}")

    # Consumption guidance footer
    lines.append("")
    lines.append(
        "Run `lexi iwh read <directory>` for each signal above to get full details "
        "and consume the signal."
    )

    return "\n".join(lines)


@lexi_app.command("orient")
def orient() -> None:
    """Show project orientation: topology, file map, library stats, and IWH signals."""
    try:
        project_root = find_project_root()
    except LexibraryNotFoundError:
        # Silently exit with 0 — no .lexibrary is a graceful no-op
        return

    output = _build_orient_content(project_root)
    if output:
        # Plain text to stdout — no Rich formatting
        print(output)  # noqa: T201


@lexi_app.command("context-dump", hidden=True)
def context_dump() -> None:
    """Emit orientation context (hidden, deprecated alias for orient)."""
    orient()


@lexi_app.command()
def impact(
    file: Annotated[
        Path,
        typer.Argument(help="Source file to analyse for reverse dependents."),
    ],
    *,
    depth: Annotated[
        int,
        typer.Option("--depth", help="Maximum traversal depth (1-3, default 1)."),
    ] = 1,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Output paths only, one per line."),
    ] = False,
) -> None:
    """Show reverse dependents of a source file (who imports it).

    Traverses the link graph's ``ast_import`` edges in reverse to find
    files that depend on the given file.  Use ``--depth N`` to follow
    the dependency chain further (clamped to 3).

    With ``--quiet``, prints one path per line with no decoration --
    suitable for piping to other tools.
    """
    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file_frontmatter,
    )
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.linkgraph import open_index  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(file).resolve()

    # Find project root starting from the file's directory
    try:
        project_root = find_project_root(start=target.parent)
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red]"
            " Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None

    config = load_config(project_root)

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

    rel_path = str(target.relative_to(project_root))

    # Clamp depth to 1-3
    effective_depth = max(1, min(depth, 3))

    # Open the link graph
    link_graph = open_index(project_root)
    if link_graph is None:
        if quiet:
            return
        console.print(
            "[yellow]No link graph index found.[/yellow] "
            "Run [cyan]lexictl index[/cyan] to build one."
        )
        raise typer.Exit(1) from None

    try:
        nodes = link_graph.traverse(
            rel_path,
            max_depth=effective_depth,
            link_types=["ast_import"],
            direction="inbound",
        )
    finally:
        link_graph.close()

    if not nodes:
        if quiet:
            return
        console.print(f"No dependents found for [cyan]{rel_path}[/cyan].")
        return

    # Quiet mode: paths only
    if quiet:
        seen: set[str] = set()
        for node in nodes:
            if node.path not in seen:
                seen.add(node.path)
                console.print(node.path)
        return

    # Tree output with design file descriptions and open stack post warnings
    # Re-open link graph for stack post checks
    link_graph_for_stack = open_index(project_root)

    console.print(f"\n## Dependents of [cyan]{rel_path}[/cyan]\n")

    for node in nodes:
        indent = "  " * (node.depth - 1)
        prefix = "|-" if node.depth == 1 else "|--"

        # Try to get the design file description
        design_desc = ""
        design_path = mirror_path(project_root, project_root / node.path)
        fm = parse_design_file_frontmatter(design_path)
        if fm is not None and fm.description:
            design_desc = f"  -- {fm.description}"

        console.print(f"{indent}{prefix} {node.path}{design_desc}")

        # Check for open stack posts referencing this dependent
        if link_graph_for_stack is not None:
            stack_links = link_graph_for_stack.reverse_deps(node.path, link_type="stack_file_ref")
            for slink in stack_links:
                stack_artifact = link_graph_for_stack.get_artifact(slink.source_path)
                if stack_artifact is not None and stack_artifact.status == "open":
                    console.print(
                        f"{indent}   [yellow]warning:[/yellow] open stack post "
                        f"[dim]{stack_artifact.path}[/dim] "
                        f"({stack_artifact.title or 'untitled'})"
                    )

    if link_graph_for_stack is not None:
        link_graph_for_stack.close()

    console.print()


@lexi_app.command("context-dump", hidden=True)
def context_dump() -> None:
    """Emit orientation context for hook injection (hidden command)."""
    try:
        project_root = find_project_root()
    except LexibraryNotFoundError:
        # Silently exit with 0 — no .lexibrary is a graceful no-op
        return

    output = _build_context_dump(project_root)
    if output:
        # Plain text to stdout — no Rich formatting
        print(output)  # noqa: T201
