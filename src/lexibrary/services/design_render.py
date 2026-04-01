"""Design update rendering -- terminal formatting for design update outcomes.

Render functions accept :class:`~lexibrary.services.design.DesignUpdateDecision`
instances and pipeline results, returning formatted strings for terminal
output.  The CLI handler calls these renderers and passes the result to
``info()`` / ``warn()`` for display.

The service module (``design.py``) never imports this module, keeping
rendering concerns fully separate.
"""

from __future__ import annotations

from lexibrary.services.design import DesignUpdateDecision


def render_skip(decision: DesignUpdateDecision, *, updated_by: str | None = None) -> str:
    """Render a skip decision as a human-readable message.

    Parameters
    ----------
    decision:
        A decision with ``action == "skip"``.
    updated_by:
        The ``updated_by`` value from frontmatter, if available.
        Included in ``protected`` messages for clarity.

    Returns
    -------
    str
        Formatted message ready for ``warn()`` or ``info()``.
    """
    if decision.skip_code == "iwh_blocked":
        return f"Skipped: {decision.reason}"

    if decision.skip_code == "protected":
        if updated_by:
            return (
                f"Skipped: design file protected (updated_by: {updated_by}). "
                "Use --force / -f to override."
            )
        return f"Skipped: {decision.reason}"

    if decision.skip_code == "up_to_date":
        return "Skipped: design file is up to date."

    # Fallback for unknown skip codes
    return f"Skipped: {decision.reason}"


def render_success(source_path: str, change_level: str) -> str:
    """Render a successful pipeline result.

    Parameters
    ----------
    source_path:
        Relative path to the source file.
    change_level:
        The change level from the pipeline (e.g. ``"NEW_FILE"``,
        ``"INTERFACE_CHANGE"``, ``"BODY_CHANGE"``).

    Returns
    -------
    str
        Formatted success message ready for ``info()``.
    """
    return f"Updated design file for {source_path} (change: {change_level})"


def render_failure(source_path: str, reason: str) -> str:
    """Render a failed pipeline result.

    Parameters
    ----------
    source_path:
        Relative path to the source file.
    reason:
        Explanation of the failure from the pipeline.

    Returns
    -------
    str
        Formatted error message ready for ``error()``.
    """
    return f"Failed to update design file for {source_path}: {reason}"


def render_skeleton_warning(source_path: str, reason: str) -> str:
    """Render a warning when the pipeline fell back to skeleton generation.

    Parameters
    ----------
    source_path:
        Relative path to the source file.
    reason:
        Why the LLM was not used (e.g. file too large, token limit).

    Returns
    -------
    str
        Formatted warning message ready for ``warn()``.  Suggests
        ``--unlimited`` to bypass the token limit.
    """
    return (
        f"Design file for {source_path} was generated as a skeleton "
        f"(LLM not used: {reason}). Use --unlimited to bypass token limits."
    )
