"""Agent-facing CLI for Lexibrary — lookups, search, concepts, and Stack issue tracking."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._format import OutputFormat, set_format
from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import (
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
from lexibrary.services.status import collect_status
from lexibrary.services.status_render import render_dashboard, render_quiet
from lexibrary.utils.root import find_project_root


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
# view
# ---------------------------------------------------------------------------


@lexi_app.command()
def view(
    artifact_id: Annotated[
        str,
        typer.Argument(
            metavar="ARTIFACT_ID",
            help="Artifact ID in XX-NNN format (e.g. CN-001, ST-042, DS-017).",
        ),
    ],
) -> None:
    """View any artifact by its ID.

    Accepts concept (CN), convention (CV), playbook (PB), design (DS),
    and stack (ST) IDs.  Displays the full parsed content of the artifact.

    Use --format json at the top level for JSON output on errors.
    """
    from lexibrary.cli._format import OutputFormat, get_format  # noqa: PLC0415
    from lexibrary.services.view import ViewError, resolve_and_load  # noqa: PLC0415
    from lexibrary.services.view_render import render_view, render_view_error  # noqa: PLC0415

    project_root = require_project_root()

    fmt = get_format()

    try:
        result = resolve_and_load(project_root, artifact_id)
    except ViewError as exc:
        if fmt == OutputFormat.json:
            info(render_view_error(exc, fmt="json"))
        else:
            error(render_view_error(exc))
        raise typer.Exit(1) from None

    output = render_view(result)
    info(output)


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
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.services.lookup import (  # noqa: PLC0415
        build_directory_lookup,
        build_file_lookup,
        estimate_tokens,
        truncate_lookup_sections,
    )
    from lexibrary.services.lookup_render import (  # noqa: PLC0415
        render_call_path_notes,
        render_class_hierarchy,
        render_conventions,
        render_data_flow_notes,
        render_directory_link_summary,
        render_enum_notes,
        render_key_symbols,
        render_related_concepts,
        render_siblings,
        render_triggered_playbooks,
    )
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
        dir_result = build_directory_lookup(target, project_root, config)
        if dir_result is None:
            return

        if dir_result.aindex_content is not None:
            info(dir_result.aindex_content)
        else:
            info(f"# {dir_result.directory_path}\n")
            info("No .aindex file found for this directory.\n")

        if dir_result.conventions:
            conv_text = render_conventions(
                dir_result.conventions,
                dir_result.conventions_total_count,
                dir_result.display_limit,
                dir_result.directory_path,
            )
            if conv_text:
                info(conv_text)

        if dir_result.playbooks:
            playbook_section = render_triggered_playbooks(
                dir_result.playbooks, dir_result.playbook_display_limit
            )
            if playbook_section:
                info(playbook_section)

        link_summary = render_directory_link_summary(
            dir_result.import_count, dir_result.imported_file_count
        )
        if link_summary:
            info(link_summary)

        if dir_result.iwh_text:
            info(dir_result.iwh_text)
        return

    # --- File lookup mode ---

    # Check design file exists
    design_path = mirror_path(project_root, target)
    if not design_path.exists():
        warn(f"No design file found for {file}")
        info(f"Run `lexictl update {file}` to generate one.")
        raise typer.Exit(1)

    # Gather data via service
    file_result = build_file_lookup(target, project_root, config, full=full)
    if file_result is None:
        return

    # Staleness warning
    if file_result.is_stale:
        warn(
            "Source file has changed since the design file was last generated. "
            "Advise user to run `lexictl update " + str(file) + "` to refresh.\n"
        )

    # --- Brief mode (default): description + conventions + issue count ---
    if not full:
        info(f"# {file_result.file_path}\n")
        if file_result.description:
            info(f"{file_result.description}\n")

        if file_result.conventions:
            conv_text = render_conventions(
                file_result.conventions,
                file_result.conventions_total_count,
                file_result.display_limit,
                file_result.file_path,
            )
            if conv_text:
                info(conv_text)

        if file_result.playbooks:
            playbook_section = render_triggered_playbooks(
                file_result.playbooks, file_result.playbook_display_limit
            )
            if playbook_section:
                info(playbook_section)

        siblings_text = render_siblings(file_result.siblings, file_result.file_path, full=False)
        if siblings_text:
            info(siblings_text)

        concepts_text = render_related_concepts(file_result.concepts, full=False)
        if concepts_text:
            info(concepts_text)

        info(f"Open issues: {file_result.open_issue_count}")
        info("")
        info("Run `lexi lookup <path> --full` for complete details.")
        return

    # --- Full mode (--full flag) ---
    if file_result.design_content:
        info(file_result.design_content)

    # Conventions (always shown, second priority)
    conventions_token_estimate = 0
    if file_result.conventions:
        conv_text = render_conventions(
            file_result.conventions,
            file_result.conventions_total_count,
            file_result.display_limit,
            file_result.file_path,
        )
        if conv_text:
            info(conv_text)
            conventions_token_estimate = len(file_result.conventions) * 10

    # Triggered playbooks (always shown, after conventions, before supplementary)
    playbook_token_estimate = 0
    if file_result.playbooks:
        playbook_section = render_triggered_playbooks(
            file_result.playbooks, file_result.playbook_display_limit
        )
        if playbook_section:
            info(playbook_section)
            playbook_token_estimate = estimate_tokens(playbook_section)

    # Sibling files (always shown in full mode)
    siblings_text = render_siblings(file_result.siblings, file_result.file_path, full=True)
    if siblings_text:
        info(siblings_text)

    # Related concepts (always shown in full mode)
    concepts_text = render_related_concepts(
        file_result.concepts,
        full=True,
        linkgraph_available=file_result.concepts_linkgraph_available,
    )
    if concepts_text:
        info(concepts_text)

    # Key symbols (always shown in full mode when non-empty -- emitted
    # after Dependencies / Reverse dependencies per the symbol-graph-2
    # spec so users see caller/callee fan-out for the file at a glance).
    key_symbols_text = render_key_symbols(
        file_result.key_symbols,
        file_result.key_symbols_total,
    )
    if key_symbols_text:
        info(key_symbols_text)

    # Class hierarchy (symbol-graph-3) -- emits after Key symbols so
    # users see inheritance, subclass counts, and unresolved external
    # bases right next to the per-symbol fan-out data for the file.
    class_hierarchy_text = render_class_hierarchy(file_result.classes)
    if class_hierarchy_text:
        info(class_hierarchy_text)

    # Enums & constants (symbol-graph-5) -- emits after Class hierarchy so
    # users see the named values defined by the file alongside the structural
    # symbol-graph sections.  Sourced from the design file's
    # ``## Enums & constants`` enrichment section.
    enum_notes_text = render_enum_notes(file_result.enum_notes)
    if enum_notes_text:
        info(enum_notes_text)

    # Call paths (symbol-graph-5) -- emits after Enums & constants so the
    # narrative call-flow notes sit next to the structural symbol-graph
    # sections.  Sourced from the design file's ``## Call paths`` enrichment
    # section.
    call_path_notes_text = render_call_path_notes(file_result.call_path_notes)
    if call_path_notes_text:
        info(call_path_notes_text)

    # Data flows (symbol-graph-7) -- emits after Call paths.  Sourced from
    # the design file's ``## Data flows`` enrichment section, which is gated
    # on deterministic AST signal (branch parameters).
    data_flow_notes_text = render_data_flow_notes(file_result.data_flow_notes)
    if data_flow_notes_text:
        info(data_flow_notes_text)

    # Apply token budget truncation to supplementary sections
    total_budget = config.token_budgets.lookup_total_tokens
    design_tokens = estimate_tokens(file_result.design_content or "")
    used_tokens = design_tokens + conventions_token_estimate + playbook_token_estimate

    supplementary: list[tuple[str, str, int]] = [
        ("issues", file_result.issues_text, 2),
        ("iwh", file_result.iwh_text, 3),
        ("links", file_result.links_text, 4),
    ]
    remaining_budget = max(0, total_budget - used_tokens)
    truncated_sections = truncate_lookup_sections(supplementary, remaining_budget)

    # Track what was omitted for the truncation footer
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
    from lexibrary.services.describe import DescribeError, update_billboard  # noqa: PLC0415

    target = Path(directory).resolve()

    # Find project root starting from the target directory (walks upward)
    try:
        project_root = find_project_root(start=target)
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None

    try:
        update_billboard(project_root, target, description)
    except DescribeError as exc:
        msg = str(exc)
        if "No .aindex file" in msg:
            warn(f"No .aindex file found for {directory}")
            info(f"Run `lexictl index {directory}` to generate one first.")
        elif "Failed to parse" in msg:
            error(msg)
            hint("The .aindex file may be malformed. Try regenerating it with `lexictl index`.")
        else:
            error(msg)
        raise typer.Exit(1) from None

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
    result = collect_status(project_root)
    if quiet:
        info(render_quiet(result, cli_prefix="lexi"))
    else:
        info(render_dashboard(result, cli_prefix="lexi"))
    raise typer.Exit(result.exit_code)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


_VALID_ARTIFACT_TYPES = {"concept", "convention", "design", "playbook", "stack", "symbol"}
_STACK_ONLY_FLAGS = ("--concept", "--resolution-type", "--include-stale")


@lexi_app.command()
def search(
    query: Annotated[
        str | None,
        typer.Argument(help="Free-text search query (quote multi-word phrases)."),
    ] = None,
    *,
    artifact_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help=(
                "Restrict to artifact type: concept, convention, design, "
                "playbook, stack, or symbol."
            ),
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
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum results returned from full-text search (default: 20).",
        ),
    ] = 20,
) -> None:
    """Search across concepts, conventions, design files, playbooks, Stack posts, and symbols."""
    from lexibrary.linkgraph import open_index  # noqa: PLC0415
    from lexibrary.search import unified_search  # noqa: PLC0415

    # --- Validate --type value ---
    if artifact_type is not None and artifact_type not in _VALID_ARTIFACT_TYPES:
        valid = ", ".join(sorted(_VALID_ARTIFACT_TYPES))
        error(f"Invalid --type: '{artifact_type}'. Must be one of: {valid}")
        raise typer.Exit(1)

    # --- Symbol-specific flag validation ---
    # ``--type symbol`` bypasses the artifact search entirely and hits the
    # symbol graph, so artifact-oriented filters (tags, stack-only flags)
    # are rejected in the CLI handler before ``unified_search`` is called.
    if artifact_type == "symbol":
        used_flags: list[str] = []
        if tag:
            used_flags.append("--tag")
        if concept is not None:
            used_flags.append("--concept")
        if resolution_type is not None:
            used_flags.append("--resolution-type")
        if include_stale:
            used_flags.append("--include-stale")
        if used_flags:
            error(f"{', '.join(used_flags)} cannot be used with --type symbol.")
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
            limit=limit,
            suggest=True,
        )
    finally:
        if link_graph is not None:
            link_graph.close()

    if not results.has_results() and not results.suggestions:
        warn("No results found.")
        return

    results.render()


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
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.services.impact import (  # noqa: PLC0415
        LinkGraphMissingError,
        analyse_impact,
    )
    from lexibrary.services.impact_render import render_quiet, render_tree  # noqa: PLC0415

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

    try:
        result = analyse_impact(target, project_root, config, depth=depth)
    except LinkGraphMissingError:
        if quiet:
            return
        warn("No link graph index found. Run `lexictl index` to build one.")
        raise typer.Exit(1) from None

    if not result.dependents:
        if quiet:
            return
        info(f"No dependents found for {result.target_path}.")
        return

    if quiet:
        info(render_quiet(result))
    else:
        info(render_tree(result))


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------


@lexi_app.command("trace")
def trace(
    symbol: Annotated[
        str,
        typer.Argument(
            help=(
                "Symbol name or fully-qualified name "
                "(e.g. 'update_project' or "
                "'lexibrary.archivist.pipeline.update_project'). "
                "If the argument contains a '.', it is matched against "
                "qualified_name; otherwise against the bare name."
            ),
        ),
    ],
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            help=(
                "Narrow the match to this file path. Combine with an "
                "ambiguous bare name when the same symbol exists in "
                "multiple files."
            ),
        ),
    ] = None,
    help_extended: Annotated[
        bool,
        typer.Option(
            "--help-extended",
            help="Show detailed guidance on interpreting trace output and exit.",
        ),
    ] = False,
) -> None:
    """Trace a symbol's callers, callees, and class relationships.

    Use this before renaming, moving, or deleting a symbol to understand
    its usage, or when debugging a call chain — the output shows every
    caller and callee with file:line locations.

    The output has conditional sections depending on symbol type
    (Callers, Callees, Unresolved callees, Class relationships,
    Subclasses, Members). For the full reference on how to interpret
    each section, run `lexi trace --help-extended`.

    Disambiguation: a bare name matches every symbol with that name
    across files. Pass `--file <path>` to narrow, or use a
    fully-qualified name (e.g.
    'lexibrary.archivist.pipeline.update_project') for an exact match.
    """
    if help_extended:
        from lexibrary.templates import read_template  # noqa: PLC0415
        info(read_template("help/trace.md"))
        raise typer.Exit(0)

    from lexibrary.services.symbols import SymbolQueryService  # noqa: PLC0415
    from lexibrary.services.symbols_render import render_trace  # noqa: PLC0415

    project_root = require_project_root()
    with SymbolQueryService(project_root) as svc:
        response = svc.trace(symbol, file=file)

    if not response.results:
        warn(f"No symbol named {symbol!r} found in the symbol graph.")
        hint("Run `lexi design update <file>` to refresh, or try `lexi search --type symbol`.")
        raise typer.Exit(1)

    for warning in response.stale:
        warn(
            f"Symbol graph may be stale for {warning.file_path} — "
            f"run `lexi design update {warning.file_path}` to refresh."
        )

    render_trace(symbol, response.results)
    hint("Run `lexi trace --help-extended` for output interpretation.")
