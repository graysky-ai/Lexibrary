"""Budget Trimmer sub-agent for the curator.

Scans knowledge-layer files (design files, START_HERE.md, HANDOFF.md) for
token budget overruns and provides an LLM-based condensation function.
The write contract is NOT handled here -- the coordinator manages all
file writes after condensation.

Risk classification:
- ``condense_file`` is **High** risk (lossy transformation).
- ``shorten_description`` is **Low** risk.
- ``propose_condensation`` is **Medium** risk.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.curator.config import BudgetConfig, CuratorConfig
from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.tokenizer import TokenCounter, create_tokenizer
from lexibrary.utils.atomic import atomic_write
from lexibrary.utils.paths import LEXIBRARY_DIR

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)

# Section priority hints for the Budget Trimmer BAML function.
# High-priority sections are preserved first during condensation.
_DEFAULT_PRIORITY_HINTS: list[str] = [
    "Interface",
    "Dependencies",
    "Insights",
]

# File type to glob pattern mapping for scanning.
_FILE_TYPE_PATTERNS: dict[str, list[str]] = {
    "design_file": ["designs/**/*.md"],
    "start_here": ["START_HERE.md"],
    "handoff": ["HANDOFF.md"],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BudgetIssue:
    """A knowledge-layer file that exceeds its token budget."""

    path: Path
    current_tokens: int
    budget_target: int
    file_type: Literal["design_file", "start_here", "handoff"]


@dataclass
class CondenseResult:
    """Result of a condensation operation via the Budget Trimmer BAML function."""

    condensed_content: str
    trimmed_sections: list[str]
    success: bool


# ---------------------------------------------------------------------------
# Budget scanning
# ---------------------------------------------------------------------------


def _get_budget_for_type(
    file_type: Literal["design_file", "start_here", "handoff"],
    budget_config: BudgetConfig,
) -> int:
    """Return the token budget for a given file type."""
    value: int = getattr(budget_config.token_limits, file_type)
    return value


def scan_token_budgets(
    project_root: Path,
    config: CuratorConfig,
    *,
    tokenizer: TokenCounter | None = None,
) -> list[BudgetIssue]:
    """Scan knowledge-layer files and return those exceeding their token budget.

    Scans design files, START_HERE.md, and HANDOFF.md under the project's
    ``.lexibrary/`` directory.  Compares each file's token count against the
    corresponding limit in ``config.budget.token_limits``.

    Parameters
    ----------
    project_root:
        Root of the project containing the ``.lexibrary/`` directory.
    config:
        Curator configuration (provides ``budget.token_limits``).
    tokenizer:
        Optional pre-built token counter.  When ``None``, an approximate
        counter is created as a fallback.

    Returns
    -------
    list[BudgetIssue]
        One entry per file that exceeds its configured token budget.
    """
    if tokenizer is None:
        from lexibrary.config.schema import TokenizerConfig  # noqa: PLC0415

        tokenizer = create_tokenizer(TokenizerConfig(backend="approximate"))

    lexibrary_dir = project_root / LEXIBRARY_DIR
    if not lexibrary_dir.is_dir():
        return []

    budget_config = config.budget
    issues: list[BudgetIssue] = []

    # Scan design files
    designs_dir = lexibrary_dir / "designs"
    if designs_dir.is_dir():
        budget_target = _get_budget_for_type("design_file", budget_config)
        for design_path in sorted(designs_dir.rglob("*.md")):
            # Skip hidden files (e.g., .comments.yaml siblings)
            if design_path.name.startswith("."):
                continue
            try:
                tokens = tokenizer.count_file(design_path)
            except Exception:
                logger.debug("Failed to count tokens for %s", design_path, exc_info=True)
                continue
            if tokens > budget_target:
                issues.append(
                    BudgetIssue(
                        path=design_path,
                        current_tokens=tokens,
                        budget_target=budget_target,
                        file_type="design_file",
                    )
                )

    # Scan START_HERE.md
    start_here = lexibrary_dir / "START_HERE.md"
    if start_here.is_file():
        budget_target = _get_budget_for_type("start_here", budget_config)
        try:
            tokens = tokenizer.count_file(start_here)
        except Exception:
            logger.debug("Failed to count tokens for %s", start_here, exc_info=True)
        else:
            if tokens > budget_target:
                issues.append(
                    BudgetIssue(
                        path=start_here,
                        current_tokens=tokens,
                        budget_target=budget_target,
                        file_type="start_here",
                    )
                )

    # Scan HANDOFF.md
    handoff = lexibrary_dir / "HANDOFF.md"
    if handoff.is_file():
        budget_target = _get_budget_for_type("handoff", budget_config)
        try:
            tokens = tokenizer.count_file(handoff)
        except Exception:
            logger.debug("Failed to count tokens for %s", handoff, exc_info=True)
        else:
            if tokens > budget_target:
                issues.append(
                    BudgetIssue(
                        path=handoff,
                        current_tokens=tokens,
                        budget_target=budget_target,
                        file_type="handoff",
                    )
                )

    return issues


# ---------------------------------------------------------------------------
# Condensation
# ---------------------------------------------------------------------------


async def condense_file(
    issue: BudgetIssue,
    config: CuratorConfig,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> CondenseResult:
    """Condense an over-budget file via the CuratorCondenseFile BAML function.

    Reads the file content, calls the BAML function, and returns the result.
    Does **NOT** write the file -- the coordinator handles writes.

    Parameters
    ----------
    issue:
        The ``BudgetIssue`` describing the over-budget file.
    config:
        Curator configuration (unused currently, reserved for future options).
    baml_client:
        Optional BAML async client for the LLM call.  When ``None``, the
        default ``b`` singleton is used.  Pass a mock in tests.

    Returns
    -------
    CondenseResult
        The condensed content and a manifest of what was trimmed.
    """
    client = baml_client if baml_client is not None else b

    try:
        file_content = issue.path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read %s: %s", issue.path, exc)
        return CondenseResult(
            condensed_content="",
            trimmed_sections=[],
            success=False,
        )

    try:
        output = await client.CuratorCondenseFile(
            file_content=file_content,
            budget_target=issue.budget_target,
            section_priority_hints=_DEFAULT_PRIORITY_HINTS,
        )

        return CondenseResult(
            condensed_content=output.condensed_content,
            trimmed_sections=list(output.trimmed_sections),
            success=True,
        )
    except Exception as exc:
        logger.error("BAML CuratorCondenseFile failed for %s: %s", issue.path, exc)
        return CondenseResult(
            condensed_content="",
            trimmed_sections=[],
            success=False,
        )


# ---------------------------------------------------------------------------
# Dispatcher entry point (Phase 1.5)
# ---------------------------------------------------------------------------


def _write_condensed_file(file_path: Path, condensed_content: str) -> None:
    """Write condensed content to a design file with updated metadata.

    Uses ``atomic_write()``.  For design files the frontmatter's
    ``updated_by`` field should already have been reset to
    ``"curator"`` by the BAML function output; this helper just writes
    the new content atomically.
    """
    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file_frontmatter,
    )

    fm = None
    with contextlib.suppress(Exception):
        fm = parse_design_file_frontmatter(file_path)

    if fm is not None:
        atomic_write(file_path, condensed_content)
    else:
        atomic_write(file_path, condensed_content)


async def dispatch_budget_condense(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Dispatch a budget issue to the Budget Trimmer sub-agent.

    Under ``full`` autonomy the condensed content is written to disk
    via ``atomic_write()`` with the BAML-produced content.  Under
    ``auto_low`` or ``propose`` the condensation is proposed only
    (returned in the result message).

    Extracted from :class:`Coordinator._dispatch_budget_condense`
    (Phase 1.5 dispatcher refactor).
    """
    budget_item = item.budget_item
    if budget_item is None:
        return SubAgentResult(
            success=False,
            action_key="condense_file",
            path=item.source_item.path,
            message="No budget item available for condensation",
        )

    issue = BudgetIssue(
        path=budget_item.path,
        current_tokens=budget_item.current_tokens,
        budget_target=budget_item.budget_target,
        file_type=budget_item.file_type,  # type: ignore[arg-type]
    )

    try:
        condense_result = await condense_file(issue, ctx.config.curator)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(budget_item.path))
        return SubAgentResult(
            success=False,
            action_key="condense_file",
            path=budget_item.path,
            message=f"Budget condensation error: {exc}",
        )

    if not condense_result.success:
        return SubAgentResult(
            success=False,
            action_key="condense_file",
            path=budget_item.path,
            message="Budget condensation failed (BAML returned failure)",
            llm_calls=1,
        )

    # Under full autonomy, write the condensed file
    autonomy = ctx.config.curator.autonomy
    if autonomy == "full":
        try:
            _write_condensed_file(budget_item.path, condense_result.condensed_content)
        except Exception as exc:
            ctx.summary.add("dispatch", exc, path=str(budget_item.path))
            return SubAgentResult(
                success=False,
                action_key="condense_file",
                path=budget_item.path,
                message=f"Failed to write condensed file: {exc}",
                llm_calls=1,
            )

        return SubAgentResult(
            success=True,
            action_key="condense_file",
            path=budget_item.path,
            message=(
                f"Condensed from {budget_item.current_tokens} to "
                f"~{budget_item.budget_target} tokens; "
                f"trimmed: {', '.join(condense_result.trimmed_sections)}"
            ),
            llm_calls=1,
        )

    # Under auto_low or propose, just report the proposal
    return SubAgentResult(
        success=True,
        action_key="propose_condensation",
        path=budget_item.path,
        message=(
            f"Proposed condensation from {budget_item.current_tokens} to "
            f"~{budget_item.budget_target} tokens; "
            f"would trim: {', '.join(condense_result.trimmed_sections)}"
        ),
        llm_calls=1,
    )
