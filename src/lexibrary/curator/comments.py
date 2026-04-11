"""Comment Curator sub-agent for the curator.

Integrates sidecar comments from ``.comments.yaml`` files into the
Insights section of design files.  Each comment is classified as:

- **durable** -- design rationale, gotchas, cross-file contracts.
  Integrated into the ``## Insights`` section.
- **ephemeral** -- progress notes, obvious-from-diff observations.
  Marked for pruning (removed from sidecar after TTL).
- **actionable** -- bugs, questions, suggestions.
  Promoted to a Stack post or IWH signal.

The write contract is owned by the shared helper
:func:`lexibrary.curator.write_contract.write_design_file_as_curator`,
which stamps ``updated_by="curator"``, recomputes
``source_hash``/``interface_hash`` from the current source file,
serializes via :func:`serialize_design_file` (which computes
``design_hash`` as a footer field), and writes atomically.  This module
is responsible only for building the in-memory :class:`DesignFile` with
the updated Insights section and preserved metadata.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.curator.write_contract import write_design_file_as_curator
from lexibrary.lifecycle.comments import read_comments
from lexibrary.lifecycle.models import ArtefactComment

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CommentClassification:
    """Classification result for a single sidecar comment."""

    comment: ArtefactComment
    disposition: Literal["durable", "ephemeral", "actionable"]
    insight_text: str = ""
    promotion_title: str = ""
    promotion_problem: str = ""


@dataclass
class CommentIntegrationResult:
    """Result from the comment integration sub-agent."""

    success: bool
    insights_content: str = ""
    classifications: list[CommentClassification] = field(default_factory=list)
    message: str = ""
    llm_calls: int = 0


@dataclass
class CommentWorkItem:
    """A single work item for the Comment Curator."""

    design_path: Path
    source_path: Path
    comments_path: Path
    comments: list[ArtefactComment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stack post deduplication
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s]")
_MULTI_SPACE_RE = re.compile(r"\s+")

# Keyword sets for the BAML stub heuristic classification.
_STUB_ACTIONABLE_KEYWORDS = frozenset({"bug", "error", "fix", "broken", "crash", "fail"})
_STUB_EPHEMERAL_KEYWORDS = frozenset({"updated", "progress", "done", "todo", "wip", "refactor"})


def _normalise_title(title: str) -> str:
    """Normalise a title for fingerprint comparison.

    Lowercased, punctuation-stripped, whitespace-collapsed.
    """
    result = title.lower()
    result = _PUNCT_RE.sub("", result)
    result = _MULTI_SPACE_RE.sub(" ", result).strip()
    return result


def compute_stack_fingerprint(
    source_path: str,
    problem_category: str,
    title: str,
) -> str:
    """Compute SHA-256 fingerprint for Stack post deduplication.

    The fingerprint is computed from ``(source_path, problem_category,
    normalised_title)`` where normalised_title is lowercased,
    punctuation-stripped, and whitespace-collapsed.
    """
    normalised = _normalise_title(title)
    key = f"{source_path}|{problem_category}|{normalised}"
    return hashlib.sha256(key.encode()).hexdigest()


def find_matching_open_post(
    stack_dir: Path,
    fingerprint: str,
) -> Path | None:
    """Search for an open Stack post with a matching fingerprint.

    Scans all ``.md`` files in *stack_dir*, parsing each to check if
    its status is ``"open"`` and its problem text hashes to the same
    fingerprint.  Returns the path to the first match, or ``None``.
    """
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

    if not stack_dir.is_dir():
        return None

    for post_path in sorted(stack_dir.glob("ST-*-*.md")):
        try:
            post = parse_stack_post(post_path)
        except Exception:
            continue
        if post is None:
            continue
        if post.frontmatter.status != "open":
            continue

        # Compute fingerprint from the post's attributes
        # We check refs.files for source_path match and tags for category match
        post_source = ""
        if post.frontmatter.refs.files:
            post_source = post.frontmatter.refs.files[0]
        post_category = post.frontmatter.tags[0] if post.frontmatter.tags else ""
        post_fp = compute_stack_fingerprint(post_source, post_category, post.frontmatter.title)
        if post_fp == fingerprint:
            return post_path

    return None


def promote_to_stack_post(
    stack_dir: Path,
    *,
    source_path: str,
    title: str,
    problem: str,
    category: str = "curator-promoted",
) -> tuple[Path, bool]:
    """Create or append to a Stack post for a promoted comment.

    Returns ``(post_path, is_new)`` -- True if a new post was created,
    False if a Finding was appended to an existing post.
    """
    from lexibrary.stack.mutations import add_finding, create_stack_post  # noqa: PLC0415

    fingerprint = compute_stack_fingerprint(source_path, category, title)
    existing = find_matching_open_post(stack_dir, fingerprint)

    if existing is not None:
        add_finding(existing, author="curator", body=problem)
        return existing, False

    post_path = create_stack_post(
        stack_dir,
        title=title,
        tags=[category],
        author="curator",
        problem=problem,
        refs_files=[source_path],
    )
    return post_path, True


# ---------------------------------------------------------------------------
# Comment integration implementation
# ---------------------------------------------------------------------------


def integrate_comments(
    work_item: CommentWorkItem,
    project_root: Path,
) -> CommentIntegrationResult:
    """Integrate sidecar comments into a design file's Insights section.

    Calls the BAML comment integration stub to classify each comment,
    then updates the design file with the new Insights section content,
    sets ``updated_by: curator``, computes fresh hashes, and writes
    atomically.

    Consumed comments (durable + actionable) are removed from the
    ``.comments.yaml`` sidecar; ephemeral comments remain (pending TTL
    pruning).

    Args:
        work_item: Details of the design file and its comments.
        project_root: Root directory of the project.

    Returns:
        A CommentIntegrationResult indicating success or failure.
    """
    # Read existing design file
    existing_df = parse_design_file(work_item.design_path)
    if existing_df is None:
        return CommentIntegrationResult(
            success=False,
            message=f"Cannot parse design file: {work_item.design_path}",
        )

    # Read source file content (optional, for LLM context)
    source_content: str | None = None
    if work_item.source_path.exists():
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(OSError):
            source_content = work_item.source_path.read_text(encoding="utf-8")

    # Call the BAML stub
    stub_result = _comment_integration_stub(
        design_content=serialize_design_file(existing_df),
        comments=work_item.comments,
        source_content=source_content,
    )

    if not stub_result.success:
        return CommentIntegrationResult(
            success=False,
            message=f"Comment integration stub failed: {stub_result.message}",
            llm_calls=stub_result.llm_calls,
        )

    # Update preserved_sections with the Insights content
    preserved = dict(existing_df.preserved_sections)
    if stub_result.insights_content.strip():
        existing_insights = preserved.get("Insights", "")
        if existing_insights:
            # Append to existing Insights
            preserved["Insights"] = (
                existing_insights.rstrip() + "\n\n" + stub_result.insights_content.strip()
            )
        else:
            preserved["Insights"] = stub_result.insights_content.strip()

    source_rel = str(work_item.source_path.relative_to(project_root))

    # Preserve existing frontmatter identity
    existing_fm = parse_design_file_frontmatter(work_item.design_path)
    design_id = (
        existing_fm.id
        if existing_fm is not None
        else source_rel.replace("/", "-").replace(".", "-")
    )
    description = (
        existing_fm.description if existing_fm is not None else f"Design file for {source_rel}"
    )

    # Build updated DesignFile.  ``updated_by`` and hash metadata are
    # set by :func:`write_design_file_as_curator` below -- the helper
    # stamps curator authorship and recomputes hashes from the on-disk
    # source.  Passing placeholders here keeps the Pydantic model valid
    # until the helper overwrites them.
    df = DesignFile(
        source_path=existing_df.source_path,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=design_id,
            updated_by="curator",  # re-stamped by the shared write helper
            status=existing_fm.status if existing_fm else "active",
        ),
        summary=existing_df.summary,
        interface_contract=existing_df.interface_contract,
        dependencies=existing_df.dependencies,
        dependents=existing_df.dependents,
        tests=existing_df.tests,
        complexity_warning=existing_df.complexity_warning,
        wikilinks=existing_df.wikilinks,
        tags=existing_df.tags,
        stack_refs=existing_df.stack_refs,
        preserved_sections=preserved,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="",  # overwritten by the shared write helper
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="curator-comment-integration",
        ),
    )

    # Delegate the write contract: the helper sets updated_by,
    # recomputes hashes, serializes, and atomically writes.
    try:
        write_design_file_as_curator(df, work_item.design_path, project_root)
    except Exception as exc:
        return CommentIntegrationResult(
            success=False,
            message=f"Failed to write design file: {exc}",
            llm_calls=stub_result.llm_calls,
        )

    # Update the .comments.yaml sidecar -- remove consumed comments
    # (durable + actionable are consumed; ephemeral remain)
    _update_comments_sidecar(work_item.comments_path, stub_result.classifications)

    logger.info(
        "Integrated %d comments into %s (durable=%d, ephemeral=%d, actionable=%d)",
        len(work_item.comments),
        work_item.design_path,
        sum(1 for c in stub_result.classifications if c.disposition == "durable"),
        sum(1 for c in stub_result.classifications if c.disposition == "ephemeral"),
        sum(1 for c in stub_result.classifications if c.disposition == "actionable"),
    )

    return CommentIntegrationResult(
        success=True,
        insights_content=preserved.get("Insights", ""),
        classifications=stub_result.classifications,
        message=f"Integrated comments for {source_rel}",
        llm_calls=stub_result.llm_calls,
    )


def _update_comments_sidecar(
    comments_path: Path,
    classifications: list[CommentClassification],
) -> None:
    """Update the .comments.yaml sidecar after integration.

    Consumed comments (durable and actionable) are removed.
    Ephemeral comments remain for future TTL-based pruning.
    """
    import yaml  # noqa: PLC0415

    from lexibrary.lifecycle.models import ArtefactCommentFile  # noqa: PLC0415

    # Build set of ephemeral comment bodies (to keep)
    ephemeral_bodies = {c.comment.body for c in classifications if c.disposition == "ephemeral"}

    # Read current comments and filter to only ephemeral ones
    existing = read_comments(comments_path)
    remaining = [c for c in existing if c.body in ephemeral_bodies]

    if not remaining:
        # All consumed -- remove the sidecar file
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(OSError):
            comments_path.unlink(missing_ok=True)
        return

    # Write back only the ephemeral comments
    comment_file = ArtefactCommentFile(comments=remaining)
    data = comment_file.model_dump(mode="json")
    try:
        comments_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to update comments sidecar %s: %s", comments_path, exc)


def comment_result_to_sub_agent_result(
    result: CommentIntegrationResult,
    source_path: Path | None = None,
) -> SubAgentResult:
    """Convert a CommentIntegrationResult to a SubAgentResult for the coordinator."""
    return SubAgentResult(
        success=result.success,
        action_key="integrate_sidecar_comments",
        path=source_path,
        message=result.message,
        llm_calls=result.llm_calls,
    )


def dispatch_comment_integration(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Dispatch a comment integration item to the Comment Curator.

    Reads sidecar comments, calls the Comment Curator sub-agent,
    updates the design file Insights section, and handles Stack
    post promotion for actionable comments.

    Extracted from :class:`Coordinator._dispatch_comment_integration`
    (Phase 1.5 dispatcher refactor).
    """
    from lexibrary.stack.helpers import stack_dir  # noqa: PLC0415

    if item.comment_item is None:
        return SubAgentResult(
            success=False,
            action_key="integrate_sidecar_comments",
            path=item.source_item.path,
            message="No comment item available for integration",
        )

    # Read the actual comments from sidecar
    comments = read_comments(item.comment_item.comments_path)
    if not comments:
        return SubAgentResult(
            success=True,
            action_key="integrate_sidecar_comments",
            path=item.source_item.path,
            message="No comments to process",
            llm_calls=0,
        )

    work_item = CommentWorkItem(
        design_path=item.comment_item.design_path,
        source_path=item.comment_item.source_path,
        comments_path=item.comment_item.comments_path,
        comments=comments,
    )

    try:
        result = integrate_comments(work_item, ctx.project_root)
    except Exception as exc:
        ctx.summary.add(
            "dispatch",
            exc,
            path=str(item.comment_item.source_path),
        )
        return SubAgentResult(
            success=False,
            action_key="integrate_sidecar_comments",
            path=item.source_item.path,
            message=f"Comment integration error: {exc}",
        )

    # Handle actionable comment promotion to Stack posts
    if result.success:
        sdir = stack_dir(ctx.project_root)
        source_rel = str(item.comment_item.source_path.relative_to(ctx.project_root))
        for classification in result.classifications:
            if classification.disposition == "actionable":
                try:
                    promote_to_stack_post(
                        sdir,
                        source_path=source_rel,
                        title=classification.promotion_title,
                        problem=classification.promotion_problem,
                    )
                except Exception as exc:
                    ctx.summary.add(
                        "dispatch",
                        exc,
                        path=f"stack-promote:{source_rel}",
                    )

    return comment_result_to_sub_agent_result(result, item.source_item.path)


# ---------------------------------------------------------------------------
# BAML Comment Integration stub
# ---------------------------------------------------------------------------


def _comment_integration_stub(
    *,
    design_content: str,
    comments: list[ArtefactComment],
    source_content: str | None,
) -> CommentIntegrationResult:
    """BAML stub for the Comment Curator (Sonnet).

    In production this will call the ``CuratorIntegrateComments`` BAML
    function.  The stub applies simple heuristics to classify comments:

    - Comments mentioning "bug", "error", "fix", "broken" -> actionable
    - Comments mentioning "updated", "progress", "done", "todo" -> ephemeral
    - Everything else -> durable

    Input fields (for future BAML function):
      - design_content: serialized design file content
      - comments: list of ArtefactComment objects
      - source_content: optional source file content for context

    Output fields (from future BAML function):
      - insights_content: updated Insights section markdown
      - classifications: per-comment disposition
    """
    classifications: list[CommentClassification] = []
    insights_parts: list[str] = []

    for comment in comments:
        body_lower = comment.body.lower()
        # Strip punctuation from each word for keyword matching
        words = {_PUNCT_RE.sub("", w) for w in body_lower.split()}

        if words & _STUB_ACTIONABLE_KEYWORDS:
            # Actionable: promote to Stack post
            classifications.append(
                CommentClassification(
                    comment=comment,
                    disposition="actionable",
                    promotion_title=f"Promoted: {comment.body[:60]}",
                    promotion_problem=comment.body,
                )
            )
        elif words & _STUB_EPHEMERAL_KEYWORDS:
            # Ephemeral: will be pruned after TTL
            classifications.append(
                CommentClassification(
                    comment=comment,
                    disposition="ephemeral",
                )
            )
        else:
            # Durable: integrate into Insights
            insight_text = f"- {comment.body}"
            insights_parts.append(insight_text)
            classifications.append(
                CommentClassification(
                    comment=comment,
                    disposition="durable",
                    insight_text=insight_text,
                )
            )

    insights_content = "\n".join(insights_parts) if insights_parts else ""

    return CommentIntegrationResult(
        success=True,
        insights_content=insights_content,
        classifications=classifications,
        message=f"Classified {len(comments)} comments (stub)",
        llm_calls=1 if comments else 0,
    )
