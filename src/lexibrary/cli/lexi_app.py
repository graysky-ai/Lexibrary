"""Agent-facing CLI for Lexibrary — lookups, search, concepts, and Stack issue tracking."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from lexibrary.cli._format import OutputFormat, set_format
from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import (
    _run_status,
    _run_validate,
    load_dotenv_if_configured,
    require_project_root,
)
from lexibrary.cli.concepts import concept_app
from lexibrary.cli.conventions import convention_app
from lexibrary.cli.design import design_app
from lexibrary.cli.iwh import iwh_app
from lexibrary.cli.playbooks import playbook_app
from lexibrary.cli.stack import stack_app
from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root

if TYPE_CHECKING:
    from lexibrary.artifacts.playbook import PlaybookFile


def _lexi_callback(
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Output format: markdown (default), json, or plain.",
            case_sensitive=False,
        ),
    ] = OutputFormat.markdown,
) -> None:
    """Top-level callback: set global output format and load dotenv."""
    set_format(fmt)
    load_dotenv_if_configured()


lexi_app = typer.Typer(
    name="lexi",
    help=(
        "Agent-facing CLI for Lexibrary. "
        "Provides lookups, search, concepts, and Stack issue tracking for LLM context navigation."
    ),
    no_args_is_help=True,
    rich_markup_mode=None,
    callback=_lexi_callback,
)

# ---------------------------------------------------------------------------
# Sub-groups (imported from per-group modules)
# ---------------------------------------------------------------------------
lexi_app.add_typer(stack_app, name="stack")
lexi_app.add_typer(concept_app, name="concept")
lexi_app.add_typer(convention_app, name="convention")
lexi_app.add_typer(iwh_app, name="iwh")
lexi_app.add_typer(design_app, name="design")
lexi_app.add_typer(playbook_app, name="playbook")


# ---------------------------------------------------------------------------
# lookup helpers
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

    info("\n## Applicable Conventions\n")

    # Group by scope, preserving order (already sorted root-to-leaf)
    groups: OrderedDict[str, list[ConventionFile]] = OrderedDict()
    for conv in typed_conventions:
        scope = conv.frontmatter.scope
        groups.setdefault(scope, []).append(conv)

    for scope, group in groups.items():
        scope_label = scope if scope != "project" else "project"
        info(f"### {scope_label}\n")
        for conv in group:
            draft_marker = " [draft]" if conv.frontmatter.status == "draft" else ""
            rule_text = conv.rule or conv.frontmatter.title
            info(f"- {rule_text}{draft_marker}")
        info("")

    if total_count > display_limit:
        omitted = total_count - display_limit
        info(f"... and {omitted} more -- run `lexi conventions {rel_target}` to see all\n")


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


def _render_triggered_playbooks(
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
            f"\n*{extra} more playbook(s) matched"
            " -- run `lexi playbook search` for full list.*"
        )

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
        info(f"# {aindex.directory_path}\n")
        info(f"{aindex.billboard}\n")

        if aindex.entries:
            info("## Child Map\n")
            info("| Name | Type | Description |")
            info("| --- | --- | --- |")
            for entry in aindex.entries:
                suffix = "/" if entry.entry_type == "dir" else ""
                info(f"| `{entry.name}{suffix}` | {entry.entry_type} | {entry.description} |")
            info("")
    else:
        info(f"# {rel_target}\n")
        info("No .aindex file found for this directory.\n")

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
        info(iwh_text)


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


@lexi_app.command()
def lookup(
    file: Annotated[
        Path,
        typer.Argument(
            metavar="PATH",
            help="Relative or absolute path to a source file or directory.",
        ),
    ],
    *,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help=("Show full output (default is brief: description + conventions + issue count)."),
        ),
    ] = False,
) -> None:
    """Look up context for a source file or directory before editing.

    For a file: shows its design summary, applicable conventions, and open issues.
    For a directory: shows its .aindex overview and child map.
    Use --full to include the complete design file, reverse links, and known issues.
    """
    import hashlib  # noqa: PLC0415

    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file_frontmatter,
        parse_design_file_metadata,
    )
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(file).resolve()

    # Find project root starting from the target (walks upward)
    start_dir = target if target.is_dir() else target.parent
    try:
        project_root = find_project_root(start=start_dir)
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None

    config = load_config(project_root)

    # Check scope: target must be under scope_root
    scope_abs = (project_root / config.scope_root).resolve()
    try:
        target.relative_to(scope_abs)
    except ValueError:
        error(f"{file} is outside the configured scope_root ({config.scope_root}).")
        raise typer.Exit(1) from None

    # Directory lookup mode
    if target.is_dir():
        _lookup_directory(target, project_root, config)
        return

    # --- File lookup mode ---

    # Compute mirror path
    design_path = mirror_path(project_root, target)

    if not design_path.exists():
        warn(f"No design file found for {file}")
        info(f"Run `lexictl update {file}` to generate one.")
        raise typer.Exit(1)

    # Check staleness
    metadata = parse_design_file_metadata(design_path)
    if metadata is not None:
        try:
            current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if current_hash != metadata.source_hash:
                warn(
                    "Source file has changed since the design file was last generated. "
                    "Run `lexictl update " + str(file) + "` to refresh.\n"
                )
        except OSError:
            pass

    # --- Brief mode (default): description + conventions + issue count ---
    if not full:
        rel_target = str(target.relative_to(project_root))
        fm = parse_design_file_frontmatter(design_path)
        if fm is not None:
            info(f"# {rel_target}\n")
            info(f"{fm.description}\n")
        else:
            info(f"# {rel_target}\n")
        from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415

        conventions_dir = project_root / ".lexibrary" / "conventions"
        convention_index = ConventionIndex(conventions_dir)
        convention_index.load()
        if len(convention_index) > 0:
            brief_limit = min(config.conventions.lookup_display_limit, 5)
            convs, total = convention_index.find_by_scope_limited(
                rel_target,
                scope_root=config.scope_root,
                limit=brief_limit,
            )
            if convs:
                _render_conventions(convs, total, brief_limit, rel_target)
        # Triggered playbooks (always shown, after conventions)
        from lexibrary.playbooks.index import PlaybookIndex  # noqa: PLC0415

        playbooks_dir = project_root / ".lexibrary" / "playbooks"
        playbook_index = PlaybookIndex(playbooks_dir)
        playbook_index.load()
        triggered = playbook_index.by_trigger_file(rel_target)
        if triggered:
            brief_pb_limit = min(config.playbooks.lookup_display_limit, 5)
            playbook_section = _render_triggered_playbooks(triggered, brief_pb_limit)
            if playbook_section:
                info(playbook_section)

        from lexibrary.linkgraph import open_index  # noqa: PLC0415

        link_graph = open_index(project_root)
        if link_graph is not None:
            from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

            stack_links = link_graph.reverse_deps(rel_target, link_type="stack_file_ref")
            open_count = 0
            for slink in stack_links:
                post_path = project_root / slink.source_path
                post = parse_stack_post(post_path)
                if post is not None and post.frontmatter.status == "open":
                    open_count += 1
            link_graph.close()
            info(f"Open issues: {open_count}")
        info("")
        info("Run `lexi lookup <path> --full` for complete details.")
        return

    # --- Full mode (--full flag) ---
    # Display design file content (always shown, highest priority)
    design_content = design_path.read_text(encoding="utf-8")
    info(design_content)

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

    # Triggered playbooks (always shown, after conventions, before supplementary)
    from lexibrary.playbooks.index import PlaybookIndex  # noqa: PLC0415

    playbook_token_estimate = 0
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbook_index = PlaybookIndex(playbooks_dir)
    playbook_index.load()

    rel_target_for_trigger = str(target.relative_to(project_root))
    triggered_playbooks = playbook_index.by_trigger_file(rel_target_for_trigger)
    if triggered_playbooks:
        pb_display_limit = config.playbooks.lookup_display_limit
        playbook_section = _render_triggered_playbooks(triggered_playbooks, pb_display_limit)
        if playbook_section:
            info(playbook_section)
            playbook_token_estimate = _estimate_tokens(playbook_section)

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
    # Design, conventions, and playbooks are always shown; remaining budget goes to
    # issues > IWH > links in priority order
    total_budget = config.token_budgets.lookup_total_tokens
    design_tokens = _estimate_tokens(design_content)
    used_tokens = design_tokens + conventions_token_estimate + playbook_token_estimate

    supplementary: list[tuple[str, str, int]] = [
        ("issues", issues_text, 2),
        ("iwh", iwh_text, 3),
        ("links", links_text, 4),
    ]
    remaining_budget = max(0, total_budget - used_tokens)
    truncated_sections = _truncate_lookup_sections(supplementary, remaining_budget)

    # Track what was omitted for the truncation footer (task 8.2)
    included_names = {name for name, _ in truncated_sections}
    omitted_parts: list[str] = []
    for name, sect_content, _priority in supplementary:
        if not sect_content:
            continue
        if name not in included_names:
            if name == "issues":
                omitted_parts.append("Stack posts")
            elif name == "iwh":
                omitted_parts.append("IWH signals")
            elif name == "links":
                omitted_parts.append("links")

    for _name, section_content in truncated_sections:
        if section_content:
            info(section_content)

    if omitted_parts:
        info(f"\n*Truncated: {', '.join(omitted_parts)} omitted (token budget: {total_budget})*")


# ---------------------------------------------------------------------------
# concepts (top-level list/search command)
# ---------------------------------------------------------------------------


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
        error(f"Directory not found: {directory}")
        raise typer.Exit(1)

    if not target.is_dir():
        error(f"Not a directory: {directory}")
        raise typer.Exit(1)

    # Find project root starting from the target directory (walks upward)
    try:
        project_root = find_project_root(start=target)
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None

    # Find the .aindex file
    aindex_file = aindex_path(project_root, target)

    if not aindex_file.exists():
        warn(f"No .aindex file found for {directory}")
        info(f"Run `lexictl index {directory}` to generate one first.")
        raise typer.Exit(1)

    # Parse, update billboard, re-serialize
    aindex = parse_aindex(aindex_file)
    if aindex is None:
        error(f"Failed to parse .aindex file: {aindex_file}")
        hint("The .aindex file may be malformed. Try regenerating it with `lexictl index`.")
        raise typer.Exit(1)

    aindex.billboard = description
    serialized = serialize_aindex(aindex)
    aindex_file.write_text(serialized, encoding="utf-8")

    info(f"Updated billboard for {directory}")


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
            help="Output results as JSON instead of tables.",
        ),
    ] = False,
) -> None:
    """Return consistency check results. Reports errors by default; use --severity for more."""
    from lexibrary.cli._format import OutputFormat, get_format  # noqa: PLC0415

    fmt = get_format()
    if fmt == OutputFormat.json:
        json_output = True

    project_root = require_project_root()

    if fmt == OutputFormat.plain:
        from lexibrary.validator import validate_library  # noqa: PLC0415

        lexibrary_dir = project_root / ".lexibrary"
        try:
            report = validate_library(
                project_root,
                lexibrary_dir,
                severity_filter=severity,
                check_filter=check,
            )
        except ValueError as exc:
            error(str(exc))
            raise typer.Exit(1) from None
        if not report.issues:
            info("No validation issues found.")
        else:
            for issue in report.issues:
                suggestion = issue.suggestion or ""
                info(
                    f"{issue.severity}\t{issue.check}\t{issue.artifact}\t{issue.message}\t{suggestion}"
                )
        raise typer.Exit(report.exit_code())

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
    """Return library health summary including staleness counts and coverage stats."""
    project_root = require_project_root()
    exit_code = _run_status(project_root, path=path, quiet=quiet, cli_prefix="lexi")
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


_VALID_ARTIFACT_TYPES = {"concept", "convention", "design", "stack"}
_STACK_ONLY_FLAGS = ("--concept", "--resolution-type", "--include-stale")


@lexi_app.command()
def search(
    query: Annotated[
        str | None,
        typer.Argument(help="Free-text search query."),
    ] = None,
    *,
    artifact_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Restrict to artifact type: concept, convention, design, or stack.",
        ),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Filter by tag (repeatable, AND logic)."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by artifact status value."),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Filter by file scope path."),
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="Include deprecated/hidden artifacts."),
    ] = False,
    concept: Annotated[
        str | None,
        typer.Option("--concept", help="Stack-only: filter by referenced concept."),
    ] = None,
    resolution_type: Annotated[
        str | None,
        typer.Option(
            "--resolution-type",
            help="Stack-only: filter by resolution type.",
        ),
    ] = None,
    include_stale: Annotated[
        bool,
        typer.Option("--include-stale", help="Stack-only: include stale posts."),
    ] = False,
) -> None:
    """Search across concepts, conventions, design files, and Stack posts."""
    from lexibrary.linkgraph import open_index  # noqa: PLC0415
    from lexibrary.search import unified_search  # noqa: PLC0415

    # --- Validate --type value ---
    if artifact_type is not None and artifact_type not in _VALID_ARTIFACT_TYPES:
        valid = ", ".join(sorted(_VALID_ARTIFACT_TYPES))
        error(f"Invalid --type: '{artifact_type}'. Must be one of: {valid}")
        raise typer.Exit(1)

    # --- Stack-specific flag validation ---
    # These flags only make sense with --type stack; auto-infer if unset,
    # error if --type conflicts.
    stack_flag_used = concept is not None or resolution_type is not None or include_stale
    if stack_flag_used:
        if artifact_type is None:
            artifact_type = "stack"
        elif artifact_type != "stack":
            used = [
                f
                for f, v in [
                    ("--concept", concept),
                    ("--resolution-type", resolution_type),
                    ("--include-stale", include_stale if include_stale else None),
                ]
                if v
            ]
            error(
                f"{', '.join(used)} can only be used with --type stack, "
                f"but --type is '{artifact_type}'."
            )
            raise typer.Exit(1)

    project_root = require_project_root()

    link_graph = open_index(project_root)
    try:
        results = unified_search(
            project_root,
            query=query,
            tags=tag,
            scope=scope,
            link_graph=link_graph,
            artifact_type=artifact_type,
            status=status,
            include_deprecated=show_all,
            concept=concept,
            resolution_type=resolution_type,
            include_stale=include_stale,
        )
    finally:
        if link_graph is not None:
            link_graph.close()

    if not results.has_results():
        warn("No results found.")
        return

    results.render()


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
                parts.append(f"\n*Truncated: {omitted} file descriptions omitted*")

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
    """Collect library statistics: concept, convention, playbook counts, and open stack posts.

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

    # Count playbooks
    playbooks_dir = lexibrary_root / "playbooks"
    playbook_count = 0
    if playbooks_dir.is_dir():
        playbook_count = len(list(playbooks_dir.glob("*.md")))

    # Count open stack posts
    stack_dir = lexibrary_root / "stack"
    open_stack_count = 0
    if stack_dir.is_dir():
        from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

        for md_path in stack_dir.glob("ST-*-*.md"):
            post = parse_stack_post(md_path)
            if post is not None and post.frontmatter.status == "open":
                open_stack_count += 1

    if concept_count or convention_count or playbook_count or open_stack_count:
        lines: list[str] = ["## Library Stats\n"]
        lines.append(f"Concepts: {concept_count}")
        lines.append(f"Conventions: {convention_count}")
        lines.append(f"Playbooks: {playbook_count}")
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
    """Return project orientation: topology, file descriptions, library stats, and IWH signals."""
    try:
        project_root = find_project_root()
    except LexibraryNotFoundError:
        info("No .lexibrary/ directory found. Nothing to orient.")
        return

    output = _build_orient_content(project_root)
    if output:
        # Plain text to stdout — no Rich formatting
        print(output)  # noqa: T201
    else:
        info("Library exists but contains no orientation data yet.")


@lexi_app.command("context-dump", hidden=True)
def context_dump() -> None:
    """Emit orientation context (hidden, deprecated alias for orient)."""
    orient()


# ---------------------------------------------------------------------------
# impact
# ---------------------------------------------------------------------------


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
    """Return reverse dependents of a source file (files that import it).

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
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None

    config = load_config(project_root)

    # Check scope: file must be under scope_root
    scope_abs = (project_root / config.scope_root).resolve()
    try:
        target.relative_to(scope_abs)
    except ValueError:
        error(f"{file} is outside the configured scope_root ({config.scope_root}).")
        raise typer.Exit(1) from None

    rel_path = str(target.relative_to(project_root))

    # Clamp depth to 1-3
    effective_depth = max(1, min(depth, 3))

    # Open the link graph
    link_graph = open_index(project_root)
    if link_graph is None:
        if quiet:
            return
        warn("No link graph index found. Run `lexictl index` to build one.")
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
        info(f"No dependents found for {rel_path}.")
        return

    # Quiet mode: paths only
    if quiet:
        seen: set[str] = set()
        for node in nodes:
            if node.path not in seen:
                seen.add(node.path)
                info(node.path)
        return

    # Tree output with design file descriptions and open stack post warnings
    # Re-open link graph for stack post checks
    link_graph_for_stack = open_index(project_root)

    info(f"\n## Dependents of {rel_path}\n")

    for node in nodes:
        indent = "  " * (node.depth - 1)
        prefix = "|-" if node.depth == 1 else "|--"

        # Try to get the design file description
        design_desc = ""
        design_path = mirror_path(project_root, project_root / node.path)
        fm = parse_design_file_frontmatter(design_path)
        if fm is not None and fm.description:
            design_desc = f"  -- {fm.description}"

        info(f"{indent}{prefix} {node.path}{design_desc}")

        # Check for open stack posts referencing this dependent
        if link_graph_for_stack is not None:
            stack_links = link_graph_for_stack.reverse_deps(node.path, link_type="stack_file_ref")
            for slink in stack_links:
                stack_artifact = link_graph_for_stack.get_artifact(slink.source_path)
                if stack_artifact is not None and stack_artifact.status == "open":
                    info(
                        f"{indent}   warning: open stack post "
                        f"{stack_artifact.path} "
                        f"({stack_artifact.title or 'untitled'})"
                    )

    if link_graph_for_stack is not None:
        link_graph_for_stack.close()

    info("")
