"""Comment Auditing sub-agent for the curator.

Scans source files for stale TODO/FIXME/HACK markers and audits design
file descriptions and summaries for accuracy drift.

Functions
---------
scan_todo_comments
    Regex-scans a source file for TODO, FIXME, HACK markers with
    surrounding context (plus/minus 20 lines).

audit_comment
    Invokes the ``CuratorAuditComment`` BAML function to assess
    whether a TODO/FIXME/HACK comment is stale, current, or uncertain.

audit_description
    Invokes the ``CuratorAuditDescription`` BAML function to evaluate
    whether a design file's frontmatter description accurately reflects
    the source file.

audit_summary
    Invokes the ``CuratorAuditSummary`` BAML function to evaluate
    whether a design file's Summary section accurately reflects the
    source file's behaviour.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.curator.config import CuratorConfig
from lexibrary.curator.models import SubAgentResult, TriageItem

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# How many lines of context to extract above and below each marker.
_CONTEXT_LINES = 20

# Regex matching Python comment lines containing TODO, FIXME, or HACK markers.
# Handles patterns like:
#   # TODO: description
#   # FIXME(username): description
#   # HACK: description
#   # todo - description
_TODO_RE = re.compile(
    r"^[ \t]*#\s*(?P<marker>TODO|FIXME|HACK)"  # leading whitespace + # + marker
    r"(?:\([^)]*\))?",  # optional (username) parenthetical
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CommentAuditIssue:
    """A TODO/FIXME/HACK marker found in a source file."""

    path: Path
    line_number: int
    comment_text: str
    code_context: str
    marker_type: Literal["TODO", "FIXME", "HACK"]


@dataclass
class CommentAuditResult:
    """Result from the CuratorAuditComment BAML function."""

    staleness: Literal["stale", "current", "uncertain"]
    reasoning: str


@dataclass
class DescriptionAuditResult:
    """Result from the CuratorAuditDescription BAML function."""

    quality_score: float
    correction: str


@dataclass
class SummaryAuditResult:
    """Result from the CuratorAuditSummary BAML function."""

    quality_score: float
    rewrite: str


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def scan_todo_comments(source_path: Path) -> list[CommentAuditIssue]:
    """Regex-scan a source file for TODO, FIXME, HACK markers.

    For each match, extracts the full comment line text and plus/minus
    20 lines of surrounding code context.

    Parameters
    ----------
    source_path:
        Path to the source file to scan.

    Returns
    -------
    list[CommentAuditIssue]
        One issue per marker found.  Empty list if the file cannot be
        read or contains no markers.
    """
    try:
        content = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Cannot read %s for TODO scanning: %s", source_path, exc)
        return []

    lines = content.splitlines()
    issues: list[CommentAuditIssue] = []

    for match in _TODO_RE.finditer(content):
        # Determine line number (1-based) from the match offset.
        line_number = content[: match.start()].count("\n") + 1
        line_index = line_number - 1

        # Extract the full comment line text.
        comment_text = lines[line_index].strip() if line_index < len(lines) else ""

        # Normalise marker to uppercase.
        raw_marker = match.group("marker").upper()
        marker_type: Literal["TODO", "FIXME", "HACK"]
        if raw_marker == "TODO":
            marker_type = "TODO"
        elif raw_marker == "FIXME":
            marker_type = "FIXME"
        else:
            marker_type = "HACK"

        # Extract plus/minus _CONTEXT_LINES of surrounding context.
        start = max(0, line_index - _CONTEXT_LINES)
        end = min(len(lines), line_index + _CONTEXT_LINES + 1)
        code_context = "\n".join(lines[start:end])

        issues.append(
            CommentAuditIssue(
                path=source_path,
                line_number=line_number,
                comment_text=comment_text,
                code_context=code_context,
                marker_type=marker_type,
            )
        )

    return issues


# ---------------------------------------------------------------------------
# BAML audit functions
# ---------------------------------------------------------------------------


async def audit_comment(
    issue: CommentAuditIssue,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> CommentAuditResult:
    """Invoke the ``CuratorAuditComment`` BAML function.

    Assesses whether a TODO/FIXME/HACK comment is stale, current, or
    uncertain by analysing it against its surrounding code context.

    Parameters
    ----------
    issue:
        The comment audit issue containing the comment text and context.
    baml_client:
        Optional pre-configured ``BamlAsyncClient``.  When ``None``,
        uses the default BAML client.

    Returns
    -------
    CommentAuditResult
        Staleness assessment and reasoning.
    """
    client = baml_client if baml_client is not None else b

    logger.info(
        "Auditing comment at %s:%d (%s)",
        issue.path,
        issue.line_number,
        issue.marker_type,
    )

    result = await client.CuratorAuditComment(
        comment_text=issue.comment_text,
        code_context=issue.code_context,
    )

    # Map the BAML enum to our Literal type.
    staleness_map = {
        "STALE": "stale",
        "CURRENT": "current",
        "UNCERTAIN": "uncertain",
    }
    staleness_str = staleness_map.get(result.staleness.value, "uncertain")
    staleness: Literal["stale", "current", "uncertain"]
    if staleness_str == "stale":
        staleness = "stale"
    elif staleness_str == "current":
        staleness = "current"
    else:
        staleness = "uncertain"

    logger.info(
        "Comment at %s:%d assessed as %s",
        issue.path,
        issue.line_number,
        staleness,
    )

    return CommentAuditResult(
        staleness=staleness,
        reasoning=result.reasoning,
    )


async def audit_description(
    description: str,
    source_content: str,
    config: CuratorConfig,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> DescriptionAuditResult:
    """Invoke the ``CuratorAuditDescription`` BAML function.

    Evaluates whether a design file's frontmatter description accurately
    reflects the corresponding source file.

    Parameters
    ----------
    description:
        The design file's frontmatter description string.
    source_content:
        The full source file content.
    config:
        Curator configuration (uses ``config.auditing.quality_threshold``
        for logging).
    baml_client:
        Optional pre-configured ``BamlAsyncClient``.  When ``None``,
        uses the default BAML client.

    Returns
    -------
    DescriptionAuditResult
        Quality score and optional correction.
    """
    client = baml_client if baml_client is not None else b

    logger.info("Auditing description (threshold=%.2f)", config.auditing.quality_threshold)

    result = await client.CuratorAuditDescription(
        description=description,
        source_content=source_content,
    )

    logger.info(
        "Description audit: quality_score=%.2f, has_correction=%s",
        result.quality_score,
        bool(result.correction),
    )

    return DescriptionAuditResult(
        quality_score=result.quality_score,
        correction=result.correction,
    )


async def audit_summary(
    summary: str,
    source_content: str,
    config: CuratorConfig,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> SummaryAuditResult:
    """Invoke the ``CuratorAuditSummary`` BAML function.

    Evaluates whether a design file's Summary section accurately reflects
    the corresponding source file's behaviour.

    Parameters
    ----------
    summary:
        The design file's Summary section text.
    source_content:
        The full source file content.
    config:
        Curator configuration (uses ``config.auditing.quality_threshold``
        for logging).
    baml_client:
        Optional pre-configured ``BamlAsyncClient``.  When ``None``,
        uses the default BAML client.

    Returns
    -------
    SummaryAuditResult
        Quality score and optional rewrite.
    """
    client = baml_client if baml_client is not None else b

    logger.info("Auditing summary (threshold=%.2f)", config.auditing.quality_threshold)

    result = await client.CuratorAuditSummary(
        summary=summary,
        source_content=source_content,
    )

    logger.info(
        "Summary audit: quality_score=%.2f, has_rewrite=%s",
        result.quality_score,
        bool(result.rewrite),
    )

    return SummaryAuditResult(
        quality_score=result.quality_score,
        rewrite=result.rewrite,
    )


# ---------------------------------------------------------------------------
# Coordinator helpers
# ---------------------------------------------------------------------------


def comment_audit_to_sub_agent_result(
    issue: CommentAuditIssue,
    result: CommentAuditResult,
) -> SubAgentResult:
    """Convert a ``CommentAuditResult`` to a ``SubAgentResult`` for the coordinator."""
    return SubAgentResult(
        success=True,
        action_key="flag_stale_comment",
        path=issue.path,
        message=(
            f"{issue.marker_type} at line {issue.line_number}: "
            f"{result.staleness} -- {result.reasoning}"
        ),
        llm_calls=1,
    )


def description_audit_to_sub_agent_result(
    path: Path,
    result: DescriptionAuditResult,
) -> SubAgentResult:
    """Convert a ``DescriptionAuditResult`` to a ``SubAgentResult`` for the coordinator."""
    return SubAgentResult(
        success=True,
        action_key="audit_description",
        path=path,
        message=f"quality_score={result.quality_score:.2f}"
        + (f", correction: {result.correction}" if result.correction else ""),
        llm_calls=1,
    )


def summary_audit_to_sub_agent_result(
    path: Path,
    result: SummaryAuditResult,
) -> SubAgentResult:
    """Convert a ``SummaryAuditResult`` to a ``SubAgentResult`` for the coordinator."""
    return SubAgentResult(
        success=True,
        action_key="audit_summary",
        path=path,
        message=f"quality_score={result.quality_score:.2f}"
        + (", rewrite available" if result.rewrite else ""),
        llm_calls=1,
    )


# ---------------------------------------------------------------------------
# Dispatcher entry point (Phase 1.5)
# ---------------------------------------------------------------------------


async def dispatch_comment_audit(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Dispatch a comment audit issue to the Comment Auditor sub-agent.

    Calls :func:`audit_comment` and returns the result via the
    :func:`comment_audit_to_sub_agent_result` converter.

    Extracted from :class:`Coordinator._dispatch_comment_audit`
    (Phase 1.5 dispatcher refactor).
    """
    audit_item = item.comment_audit_item
    if audit_item is None:
        return SubAgentResult(
            success=False,
            action_key="flag_stale_comment",
            path=item.source_item.path,
            message="No comment audit item available",
        )

    issue = CommentAuditIssue(
        path=audit_item.path,
        line_number=audit_item.line_number,
        comment_text=audit_item.comment_text,
        code_context=audit_item.code_context,
        marker_type=audit_item.marker_type,  # type: ignore[arg-type]
    )

    try:
        audit_result = await audit_comment(issue)
        return comment_audit_to_sub_agent_result(issue, audit_result)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(audit_item.path))
        return SubAgentResult(
            success=False,
            action_key="flag_stale_comment",
            path=audit_item.path,
            message=f"Comment audit error: {exc}",
        )
