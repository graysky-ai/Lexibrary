"""Budget Trimmer sub-agent for the curator.

Scans knowledge-layer files (design files, START_HERE.md, HANDOFF.md) for
token budget overruns and provides an LLM-based condensation function.

Two condensation entry points are exposed:

1. :func:`condense_file` (standalone) — reads a design file, invokes
   ``CuratorCondenseFile`` BAML, re-serialises with
   ``updated_by="archivist"`` and refreshed hashes, and atomically writes
   the condensed body.  Designed for non-agent-session callers (validator
   fixer + curator sub-agent under ``full`` autonomy).  Mirrors the
   ``reconcile_deps_only`` extraction pattern introduced by
   ``curator-freshness``.
2. :func:`_call_baml_condense` (internal) — thin BAML wrapper returning
   the raw condensed body.  Reused under ``propose``/``auto_low``
   autonomy where the sub-agent reports a proposal without writing.

Risk classification:
- ``condense_file`` is **High** risk (lossy transformation).
- ``shorten_description`` is **Low** risk.
- ``propose_condensation`` is **Medium** risk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.ast_parser import compute_hashes
from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.config import BudgetConfig, CuratorConfig
from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.tokenizer import TokenCounter, create_tokenizer
from lexibrary.tokenizer.approximate import ApproximateCounter
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
    """Outcome of a :func:`condense_file` call.

    Token counts flank the BAML rewrite: ``before_tokens`` is the
    approximate token count of the on-disk file at entry, and
    ``after_tokens`` is the approximate count of the body written back
    to disk.  ``trimmed_sections`` is the per-section manifest the BAML
    prompt produced while condensing.
    """

    before_tokens: int
    after_tokens: int
    trimmed_sections: list[str] = field(default_factory=list)


@dataclass
class _BamlCondenseOutput:
    """Internal result of an isolated BAML :func:`CuratorCondenseFile` call.

    Used by both :func:`condense_file` (write path) and the curator
    sub-agent's ``propose``/``auto_low`` branches (no-write path).
    """

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


async def _call_baml_condense(
    issue: BudgetIssue,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> _BamlCondenseOutput:
    """Invoke ``CuratorCondenseFile`` BAML for *issue* and return the raw output.

    Internal helper shared between :func:`condense_file` (write path) and
    the curator sub-agent's propose/auto_low branches (no-write path).

    Parameters
    ----------
    issue:
        The ``BudgetIssue`` describing the over-budget file.
    baml_client:
        Optional BAML async client for the LLM call.  When ``None``, the
        default ``b`` singleton is used.  Pass a mock in tests.

    Returns
    -------
    _BamlCondenseOutput
        ``success=True`` with condensed content + trimmed sections on a
        successful call, ``success=False`` with empty fields on read or
        BAML failure.  The helper intentionally does not raise — it
        converts failures into a typed result so callers can branch.
    """
    client = baml_client if baml_client is not None else b

    try:
        file_content = issue.path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read %s: %s", issue.path, exc)
        return _BamlCondenseOutput(
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

        return _BamlCondenseOutput(
            condensed_content=output.condensed_content,
            trimmed_sections=list(output.trimmed_sections),
            success=True,
        )
    except Exception as exc:
        logger.error("BAML CuratorCondenseFile failed for %s: %s", issue.path, exc)
        return _BamlCondenseOutput(
            condensed_content="",
            trimmed_sections=[],
            success=False,
        )


async def condense_file(
    design_path: Path,
    project_root: Path,
    config: LexibraryConfig,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> CondenseResult:
    """Condense an over-budget design file and persist the result atomically.

    Standalone helper — no curator agent session required.  Mirrors the
    ``reconcile_deps_only`` extraction pattern introduced by
    ``curator-freshness``.  The existing curator budget sub-agent
    delegates its single-file condensation step here under ``full``
    autonomy; :func:`lexibrary.validator.fixes.fix_lookup_token_budget_exceeded`
    calls this helper directly.

    The helper:

    1. Reads *design_path* and measures its current token count using the
       :class:`~lexibrary.tokenizer.approximate.ApproximateCounter`.
    2. Invokes the ``CuratorCondenseFile`` BAML function with the default
       priority hints (Interface, Dependencies, Insights preserved in
       full).
    3. Parses the condensed body, flips ``frontmatter.updated_by`` to
       ``"archivist"`` (precedent: ``curator-freshness`` non-agent-session
       writes set ``archivist`` rather than ``curator``), and refreshes
       ``metadata.source_hash`` / ``metadata.interface_hash`` from the
       current on-disk source file.
    4. Re-serialises (:func:`serialize_design_file` recomputes
       ``metadata.design_hash`` from the rendered body) and atomically
       writes the result to *design_path*.
    5. Recomputes the token count after the write and returns both
       counts plus the BAML-reported trimmed-section manifest.

    Parameters
    ----------
    design_path:
        Absolute path to the design file under ``.lexibrary/designs/``.
    project_root:
        Absolute project root.  Used to resolve the source file from
        the design file's ``source_path`` for hash recomputation.
    config:
        Full :class:`~lexibrary.config.schema.LexibraryConfig`.  The
        helper reads ``config.curator.budget.token_limits.design_file``
        as the BAML ``budget_target``.
    baml_client:
        Optional BAML async client.  When ``None``, the default ``b``
        singleton is used.  Pass a mock in tests.

    Returns
    -------
    CondenseResult
        ``before_tokens``/``after_tokens`` around the rewrite plus the
        trimmed-section manifest from BAML.

    Raises
    ------
    OSError
        If the design file cannot be read or the atomic write fails.
    RuntimeError
        If the BAML call raises or the condensed body cannot be parsed
        as a valid design file.  The helper propagates failure so the
        caller (curator sub-agent or validator fixer) can convert it to
        a typed result with a structured error message.
    """
    # 1. Read current content + measure token count at entry.
    counter = ApproximateCounter()
    original_content = design_path.read_text(encoding="utf-8")
    before_tokens = counter.count(original_content)

    # 2. Call BAML.  The design-file budget target drives how aggressively
    #    the BAML prompt trims.
    budget_target = config.curator.budget.token_limits.design_file
    issue = BudgetIssue(
        path=design_path,
        current_tokens=before_tokens,
        budget_target=budget_target,
        file_type="design_file",
    )
    output = await _call_baml_condense(issue, baml_client=baml_client)
    if not output.success:
        raise RuntimeError(f"BAML CuratorCondenseFile failed for {design_path}")

    # 3. Parse the condensed body.  The BAML prompt is expected to return
    #    a fully-formed design file (YAML frontmatter + H1 + sections +
    #    HTML comment footer).  Write the raw output to a sibling temp
    #    file so we can use :func:`parse_design_file` — which takes a
    #    Path — then mutate and re-serialise before the final atomic
    #    write.  The temp file is unlinked regardless of success.
    import tempfile  # noqa: PLC0415 — keep top-of-file imports narrow

    tmp_fd, tmp_name = tempfile.mkstemp(
        suffix=".condense.tmp",
        dir=design_path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with open(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(output.condensed_content)

        parsed = parse_design_file(tmp_path)
        if parsed is None:
            raise RuntimeError(
                f"condense_file: BAML output for {design_path} is not a valid design file"
            )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    # 4. Flip authorship + refresh hashes from the current on-disk source.
    parsed.frontmatter.updated_by = "archivist"
    source_abs = project_root / parsed.source_path
    try:
        fresh_source_hash, fresh_interface_hash = compute_hashes(source_abs)
    except Exception:
        # Source may have been deleted since the design was generated.
        # Fall back to the design's existing hashes so the rewrite still
        # captures the condensed body; callers get a valid file either
        # way.  Logged for operator visibility.
        logger.warning(
            "condense_file: compute_hashes failed for %s; preserving existing "
            "source_hash/interface_hash",
            source_abs,
        )
    else:
        parsed.metadata.source_hash = fresh_source_hash
        parsed.metadata.interface_hash = fresh_interface_hash

    # 5. Re-serialise (this recomputes metadata.design_hash from the
    #    rendered body) and atomic-write to the final path.
    serialised = serialize_design_file(parsed)
    atomic_write(design_path, serialised)

    after_tokens = counter.count(serialised)
    return CondenseResult(
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        trimmed_sections=list(output.trimmed_sections),
    )


# ---------------------------------------------------------------------------
# Dispatcher entry point (Phase 1.5)
# ---------------------------------------------------------------------------


async def dispatch_budget_condense(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Dispatch a budget issue to the Budget Trimmer sub-agent.

    Under ``full`` autonomy the per-file condensation is delegated to
    the standalone :func:`condense_file` helper, which runs BAML and
    atomically writes the condensed body.  Under ``auto_low`` or
    ``propose`` this dispatcher calls :func:`_call_baml_condense`
    directly (no write) and reports the proposal.  The sub-agent keeps
    its autonomy gating, event emission, and ``llm_calls`` counter
    plumbing; only the BAML-call + write step moved into
    :func:`condense_file` (Phase 4 of ``curator-4``).
    """
    budget_item = item.budget_item
    if budget_item is None:
        return SubAgentResult(
            success=False,
            action_key="condense_file",
            path=item.source_item.path,
            message="No budget item available for condensation",
        )

    autonomy = ctx.config.curator.autonomy

    # Under full autonomy, delegate everything (BAML + write) to the
    # standalone helper.  The helper refreshes hashes and stamps
    # ``updated_by="archivist"`` per the curator-freshness precedent.
    if autonomy == "full":
        try:
            result = await condense_file(
                budget_item.path,
                ctx.project_root,
                ctx.config,
            )
        except Exception as exc:
            ctx.summary.add("dispatch", exc, path=str(budget_item.path))
            return SubAgentResult(
                success=False,
                action_key="condense_file",
                path=budget_item.path,
                message=f"Budget condensation error: {exc}",
                llm_calls=1,
            )

        return SubAgentResult(
            success=True,
            action_key="condense_file",
            path=budget_item.path,
            message=(
                f"Condensed from {result.before_tokens} to "
                f"~{result.after_tokens} tokens; "
                f"trimmed: {', '.join(result.trimmed_sections)}"
            ),
            llm_calls=1,
        )

    # Under auto_low / propose, call BAML but do NOT write.  The
    # proposal is surfaced via the SubAgentResult message.
    issue = BudgetIssue(
        path=budget_item.path,
        current_tokens=budget_item.current_tokens,
        budget_target=budget_item.budget_target,
        file_type=budget_item.file_type,  # type: ignore[arg-type]
    )

    try:
        output = await _call_baml_condense(issue)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(budget_item.path))
        return SubAgentResult(
            success=False,
            action_key="condense_file",
            path=budget_item.path,
            message=f"Budget condensation error: {exc}",
        )

    if not output.success:
        return SubAgentResult(
            success=False,
            action_key="condense_file",
            path=budget_item.path,
            message="Budget condensation failed (BAML returned failure)",
            llm_calls=1,
        )

    return SubAgentResult(
        success=True,
        action_key="propose_condensation",
        path=budget_item.path,
        message=(
            f"Proposed condensation from {budget_item.current_tokens} to "
            f"~{budget_item.budget_target} tokens; "
            f"would trim: {', '.join(output.trimmed_sections)}"
        ),
        llm_calls=1,
    )
