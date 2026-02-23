"""START_HERE.md generation from project topology and .aindex summaries."""

from __future__ import annotations

import logging
from pathlib import Path

from lexibrary.archivist.service import ArchivistService, StartHereRequest
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.config.schema import LexibraryConfig
from lexibrary.ignore import create_ignore_matcher
from lexibrary.utils.paths import LEXIBRARY_DIR

logger = logging.getLogger(__name__)

# Directories that are always excluded from the directory tree.
_ALWAYS_EXCLUDED = {LEXIBRARY_DIR, ".git"}


def _build_directory_tree(
    project_root: Path,
    config: LexibraryConfig,
) -> str:
    """Build a human-readable directory tree string, excluding ignored directories.

    Walks the project directory recursively, skipping ``.lexibrary/``, ``.git/``,
    and any directory the ignore matcher says to skip.  Returns an indented ASCII
    tree suitable for inclusion in an LLM prompt.
    """
    matcher = create_ignore_matcher(config, project_root)
    lines: list[str] = []

    def _walk(directory: Path, prefix: str) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return

        visible: list[Path] = []
        for child in children:
            rel_name = child.name
            # Always exclude .lexibrary and .git at any depth
            if rel_name in _ALWAYS_EXCLUDED:
                continue
            if child.is_dir():
                if not matcher.should_descend(child):
                    continue
            else:
                if matcher.is_ignored(child):
                    continue
            visible.append(child)

        for i, child in enumerate(visible):
            is_last = i == len(visible) - 1
            connector = "└── " if is_last else "├── "
            suffix = "/" if child.is_dir() else ""
            lines.append(f"{prefix}{connector}{child.name}{suffix}")
            if child.is_dir():
                extension = "    " if is_last else "│   "
                _walk(child, prefix + extension)

    lines.append(f"{project_root.name}/")
    _walk(project_root, "")
    return "\n".join(lines)


def _collect_aindex_summaries(project_root: Path) -> str:
    """Collect billboard summaries from all .aindex files in the mirror tree.

    Walks ``.lexibrary/`` looking for ``.aindex`` files, parses each one, and
    returns a newline-separated list of ``<directory>: <billboard>`` entries.
    """
    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return ""

    summaries: list[str] = []
    for aindex_path in sorted(lexibrary_root.rglob(".aindex")):
        parsed = parse_aindex(aindex_path)
        if parsed is None:
            continue
        summaries.append(f"{parsed.directory_path}: {parsed.billboard}")

    return "\n".join(summaries)


def _assemble_start_here(
    topology: str,
    ontology: str,
    navigation_by_intent: str,
    convention_index: str,
    navigation_protocol: str,
) -> str:
    """Assemble final START_HERE.md markdown from StartHereOutput sections."""
    sections = [
        "# START HERE",
        "",
        "## Project Topology",
        "",
        topology,
        "",
        "## Ontology",
        "",
        ontology,
        "",
        "## Navigation by Intent",
        "",
        navigation_by_intent,
        "",
        "## Convention Index",
        "",
        convention_index,
        "",
        "## Navigation Protocol",
        "",
        navigation_protocol,
        "",
    ]
    return "\n".join(sections)


def _count_tokens_approx(text: str) -> int:
    """Approximate token count using whitespace splitting.

    This is a rough heuristic (words ~= tokens). Good enough for budget
    warnings without requiring a tokenizer dependency.
    """
    return len(text.split())


async def generate_start_here(
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
) -> Path:
    """Generate or update ``.lexibrary/START_HERE.md`` from project topology.

    Pipeline:
    1. Build directory tree string (exclude ``.lexibrary/``, ignored dirs)
    2. Collect billboard summaries from all ``.aindex`` files in the mirror tree
    3. Read existing ``START_HERE.md`` if it exists (for continuity)
    4. Call ``archivist.generate_start_here()``
    5. Assemble final markdown from ``StartHereOutput`` sections
    6. Validate against token budget (``start_here_tokens``)
    7. Write to ``.lexibrary/START_HERE.md``

    Args:
        project_root: Absolute path to the project root.
        config: Validated project configuration.
        archivist: ArchivistService instance for LLM calls.

    Returns:
        Path to the written ``START_HERE.md`` file.

    Raises:
        RuntimeError: If the LLM call fails.
    """
    # 1. Build directory tree
    directory_tree = _build_directory_tree(project_root, config)
    logger.debug("Directory tree built (%d lines)", directory_tree.count("\n") + 1)

    # 2. Collect .aindex summaries
    aindex_summaries = _collect_aindex_summaries(project_root)
    logger.debug(
        "Collected %d .aindex summaries",
        len(aindex_summaries.splitlines()) if aindex_summaries else 0,
    )

    # 3. Read existing START_HERE.md if present
    start_here_path = project_root / LEXIBRARY_DIR / "START_HERE.md"
    existing_start_here: str | None = None
    if start_here_path.exists():
        try:
            existing_start_here = start_here_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Could not read existing START_HERE.md; generating fresh")

    # 4. Call LLM via archivist service
    project_name = project_root.name
    request = StartHereRequest(
        project_name=project_name,
        directory_tree=directory_tree,
        aindex_summaries=aindex_summaries or "(no .aindex files found)",
        existing_start_here=existing_start_here,
    )
    result = await archivist.generate_start_here(request)

    if result.error or result.start_here_output is None:
        msg = f"Failed to generate START_HERE.md: {result.error_message}"
        raise RuntimeError(msg)

    output = result.start_here_output

    # 5. Assemble final markdown
    content = _assemble_start_here(
        topology=output.topology,
        ontology=output.ontology,
        navigation_by_intent=output.navigation_by_intent,
        convention_index=output.convention_index,
        navigation_protocol=output.navigation_protocol,
    )

    # 6. Validate token budget
    token_count = _count_tokens_approx(content)
    budget = config.token_budgets.start_here_tokens
    if token_count > budget:
        logger.warning(
            "START_HERE.md exceeds token budget: ~%d tokens (budget: %d)",
            token_count,
            budget,
        )

    # 7. Write to .lexibrary/START_HERE.md
    start_here_path.parent.mkdir(parents=True, exist_ok=True)
    start_here_path.write_text(content, encoding="utf-8")
    logger.info("Wrote START_HERE.md (%d chars, ~%d tokens)", len(content), token_count)

    return start_here_path
