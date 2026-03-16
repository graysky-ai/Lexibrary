"""Shared CLI helpers used by both lexi and lexictl apps."""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from lexibrary.cli._output import error, info, warn
from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root


def require_project_root() -> Path:
    """Resolve the project root or exit with a friendly error."""
    try:
        return find_project_root()
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None


def stub(name: str) -> None:
    """Print a standard stub message for unimplemented commands."""
    require_project_root()
    warn(f"Not yet implemented. ({name})")


# ---------------------------------------------------------------------------
# Shared command implementations
# ---------------------------------------------------------------------------


def _run_validate(
    project_root: Path,
    *,
    severity: str | None = None,
    check: str | None = None,
    json_output: bool = False,
    ci_mode: bool = False,
    fix: bool = False,
) -> int:
    """Run validation checks and render output.

    Accepts parsed CLI args, calls ``validate_library()``, renders the
    results via plain text or JSON, and returns the process exit code.

    Args:
        project_root: Resolved project root directory.
        severity: Minimum severity to report (``"error"``, ``"warning"``,
            or ``"info"``).  ``None`` means all severities.
        check: Run only the named check.  ``None`` means all checks.
        json_output: When ``True``, output results as JSON instead of
            plain tables.
        ci_mode: When ``True``, output a compact single-line summary
            suitable for CI pipelines.
        fix: When ``True``, attempt to auto-fix fixable issues after
            validation.

    Returns:
        Exit code: 0 = clean, 1 = errors, 2 = warnings only.

    Raises:
        typer.Exit: With code 1 when ``check`` names an unknown check or
            ``severity`` is not a valid severity level.
    """
    from lexibrary.validator import AVAILABLE_CHECKS, validate_library  # noqa: PLC0415

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
        # Show available checks if an unknown check was requested
        if check is not None and check not in AVAILABLE_CHECKS:
            info("Available checks: " + ", ".join(sorted(AVAILABLE_CHECKS)))
        raise typer.Exit(1) from None

    # CI mode: compact single-line output
    if ci_mode:
        counts = report.counts_by_severity()
        print(  # noqa: T201
            f"lexibrary-validate: errors={counts['error']}"
            f" warnings={counts['warning']}"
            f" info={counts['info']}"
        )
        return report.exit_code()

    # Fix mode: run fixers after validation
    if fix:
        from lexibrary.config.loader import load_config  # noqa: PLC0415
        from lexibrary.validator.fixes import FIXERS  # noqa: PLC0415

        config = load_config(project_root)
        fixed_count = 0
        total_issues = len(report.issues)

        for issue in report.issues:
            fixer = FIXERS.get(issue.check)
            if fixer is not None:
                result = fixer(issue, project_root, config)
                if result.fixed:
                    info(f"  [FIXED] {issue.check}: {result.message}")
                    fixed_count += 1
                else:
                    info(f"  [SKIP] {issue.check}: {result.message}")
            else:
                info(f"  [SKIP] {issue.check}: no auto-fix available")

        manual_count = total_issues - fixed_count
        info("")
        info(
            f"Fixed {fixed_count} of {total_issues} issues."
            f" {manual_count} require manual attention."
        )
        return report.exit_code()

    if json_output:
        info(_json.dumps(report.to_dict(), indent=2))
    else:
        report.render()

    return report.exit_code()


def _run_status(
    project_root: Path,
    *,
    path: Path | None = None,
    quiet: bool = False,
    cli_prefix: str = "lexictl",
) -> int:
    """Collect library health data and render a status dashboard.

    Accepts parsed CLI args plus a CLI prefix string (``"lexi"`` or
    ``"lexictl"``) so that quiet-mode output reflects the calling CLI.

    Args:
        project_root: Resolved project root directory.
        path: Optional project directory to check (currently unused,
            reserved for future per-directory status).
        quiet: When ``True``, output a single line for hooks/CI.
        cli_prefix: Prefix for quiet-mode output (e.g. ``"lexi"`` or
            ``"lexictl"``).

    Returns:
        Exit code: 0 = clean, 1 = errors, 2 = warnings only.
    """
    import hashlib  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file_metadata,
    )
    from lexibrary.linkgraph.health import read_index_health  # noqa: PLC0415
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415
    from lexibrary.validator import validate_library  # noqa: PLC0415
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

    lexibrary_dir = project_root / ".lexibrary"

    # --- Artifact counts ---
    # Design files: count .md files in the mirror tree (exclude concepts/ and stack/)
    design_dir = lexibrary_dir
    design_files: list[Path] = []
    stale_count = 0
    latest_generated: datetime | None = None

    for md_path in sorted(design_dir.rglob("*.md")):
        # Skip non-design-file directories
        rel = md_path.relative_to(lexibrary_dir)
        rel_parts = rel.parts
        if rel_parts[0] in ("concepts", "stack"):
            continue
        # Skip known non-design files
        if md_path.name == "HANDOFF.md":
            continue
        meta = parse_design_file_metadata(md_path)
        if meta is not None:
            design_files.append(md_path)
            # Check staleness via source hash
            source_path = project_root / meta.source
            if source_path.exists():
                current_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
                if current_hash != meta.source_hash:
                    stale_count += 1
            # Track latest generated timestamp
            if latest_generated is None or meta.generated > latest_generated:
                latest_generated = meta.generated

    total_designs = len(design_files)

    # Concepts: count by status
    concepts_dir = lexibrary_dir / "concepts"
    concept_counts: dict[str, int] = {"active": 0, "deprecated": 0, "draft": 0}
    if concepts_dir.is_dir():
        for md_path in sorted(concepts_dir.glob("*.md")):
            concept = parse_concept_file(md_path)
            if concept is not None:
                s = concept.frontmatter.status
                if s in concept_counts:
                    concept_counts[s] += 1

    # Stack posts: count by status
    stack_dir = lexibrary_dir / "stack"
    stack_counts: dict[str, int] = {"open": 0, "resolved": 0}
    if stack_dir.is_dir():
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            post = parse_stack_post(md_path)
            if post is not None:
                st = post.frontmatter.status
                if st in stack_counts:
                    stack_counts[st] += 1
                else:
                    stack_counts[st] = 1

    total_stack = sum(stack_counts.values())

    # --- Lightweight validation (errors + warnings only) ---
    report = validate_library(
        project_root,
        lexibrary_dir,
        severity_filter="warning",
    )
    error_count = report.summary.error_count
    warning_count = report.summary.warning_count

    # --- Quiet mode ---
    if quiet:
        if error_count > 0 and warning_count > 0:
            parts: list[str] = []
            parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
            parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
            info(
                f"{cli_prefix}: " + ", ".join(parts) + f" \u2014 run `{cli_prefix} validate`"
            )
        elif error_count > 0:
            info(
                f"{cli_prefix}: {error_count} error{'s' if error_count != 1 else ''}"
                f" \u2014 run `{cli_prefix} validate`"
            )
        elif warning_count > 0:
            info(
                f"{cli_prefix}: {warning_count} warning{'s' if warning_count != 1 else ''}"
                f" \u2014 run `{cli_prefix} validate`"
            )
        else:
            info(f"{cli_prefix}: library healthy")
        return report.exit_code()

    # --- Full dashboard ---
    info("")
    info("Lexibrary Status")
    info("")

    # Files
    if stale_count > 0:
        info(f"  Files: {total_designs} tracked, {stale_count} stale")
    else:
        info(f"  Files: {total_designs} tracked")

    # Concepts
    concept_parts: list[str] = []
    if concept_counts["active"] > 0:
        concept_parts.append(f"{concept_counts['active']} active")
    if concept_counts["deprecated"] > 0:
        concept_parts.append(f"{concept_counts['deprecated']} deprecated")
    if concept_counts["draft"] > 0:
        concept_parts.append(f"{concept_counts['draft']} draft")
    if concept_parts:
        info("  Concepts: " + ", ".join(concept_parts))
    else:
        info("  Concepts: 0")

    # Stack
    if total_stack > 0:
        info(
            f"  Stack: {total_stack} post{'s' if total_stack != 1 else ''}"
            f" ({stack_counts.get('resolved', 0)} resolved,"
            f" {stack_counts.get('open', 0)} open)"
        )
    else:
        info("  Stack: 0 posts")

    # Link graph health
    index_health = read_index_health(project_root)
    if index_health.artifact_count is not None:
        built_part = f" (built {index_health.built_at})" if index_health.built_at else ""
        info(
            f"  Link graph: {index_health.artifact_count} artifact"
            f"{'s' if index_health.artifact_count != 1 else ''}"
            f", {index_health.link_count} link"
            f"{'s' if index_health.link_count != 1 else ''}"
            f"{built_part}"
        )
    else:
        info("  Link graph: not built (run lexictl update to create)")

    info("")

    # Issues
    info(
        f"  Issues: {error_count} error{'s' if error_count != 1 else ''},"
        f" {warning_count} warning{'s' if warning_count != 1 else ''}"
    )

    # Last updated
    if latest_generated is not None:
        now = datetime.now(tz=UTC)
        gen = latest_generated
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=UTC)
        delta = now - gen
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            time_str = f"{total_seconds} second{'s' if total_seconds != 1 else ''} ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = total_seconds // 86400
            time_str = f"{days} day{'s' if days != 1 else ''} ago"
        info(f"  Updated: {time_str}")
    else:
        info("  Updated: never")

    info("")

    # Suggest validate if issues exist
    if error_count > 0 or warning_count > 0:
        info(f"Run `{cli_prefix} validate` for details.")

    return report.exit_code()


def load_dotenv_if_configured() -> None:
    """Load ``.env`` at CLI startup when ``api_key_source`` is ``"dotenv"``.

    Reads raw YAML from the project config (no Pydantic validation) to
    check ``llm.api_key_source`` before full config initialisation.
    When the value equals ``"dotenv"``, calls
    ``load_dotenv(project_root / ".env", override=False)`` so that env
    vars already set in the shell take precedence.

    All errors are silently swallowed -- the normal project-not-found or
    config-not-found error surfaces later when a command actually runs.
    """
    try:
        import yaml  # noqa: PLC0415
        from dotenv import load_dotenv  # noqa: PLC0415

        project_root = find_project_root()
        config_path = project_root / ".lexibrary" / "config.yaml"
        if not config_path.exists():
            return

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            return

        llm_section = raw.get("llm")
        if not isinstance(llm_section, dict):
            return

        if llm_section.get("api_key_source") == "dotenv":
            load_dotenv(project_root / ".env", override=False)
    except Exception:  # noqa: BLE001
        # Silently skip -- errors will surface later during normal
        # config loading when a command actually runs.
        pass
