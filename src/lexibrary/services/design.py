"""Design update service -- pre-flight decision logic for ``lexi design update``.

Evaluates whether a design file should be (re)generated for a given source
file, returning a frozen :class:`DesignUpdateDecision` that the CLI handler
can act on without embedding business logic.

Evaluation order:
1. IWH blocked signal (overrides ``--force``)
2. Design file existence
3. Frontmatter ``updated_by`` protection
4. ``--force`` override
5. Staleness via metadata footer hash
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesignUpdateDecision:
    """Outcome of the pre-flight check for a single source file.

    Attributes:
        action: ``"generate"`` to invoke the archivist pipeline, ``"skip"``
            to leave the design file unchanged.
        reason: Human-readable explanation suitable for terminal output.
        skip_code: Machine-readable code for skip decisions (``None``
            when ``action == "generate"``).
    """

    action: Literal["generate", "skip"]
    reason: str
    skip_code: str | None = None


# ---------------------------------------------------------------------------
# Values of ``updated_by`` that are always regenerated (no protection).
# ---------------------------------------------------------------------------

_AUTO_GENERATED_UPDATERS = frozenset({"skeleton-fallback", "bootstrap-quick"})

# Values of ``updated_by`` that receive protection (skip unless --force).
_PROTECTED_UPDATERS = frozenset({"agent", "maintainer"})

# Values of ``updated_by`` that the archivist owns and may freely regenerate
# subject to the staleness check (hash comparison).  Curator uses the shared
# write contract (curator/write_contract.py), which recomputes
# source_hash/interface_hash and re-serializes to refresh design_hash, so
# curator-stamped files are just as hash-fresh as archivist-stamped files and
# are safe to route through the same staleness path.
_ARCHIVIST_OWNED_UPDATERS = frozenset({"archivist", "curator"})


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------


def check_design_update(
    source_path: Path,
    project_root: Path,
    config: object,
    *,
    force: bool = False,
) -> DesignUpdateDecision:
    """Decide whether to (re)generate the design file for *source_path*.

    Parameters
    ----------
    source_path:
        Absolute path to the source file.
    project_root:
        Absolute path to the project root (contains ``.lexibrary/``).
    config:
        A :class:`~lexibrary.config.schema.LexibraryConfig` instance.
        Accepted as ``object`` to keep this module free of config imports
        at module level.
    force:
        When ``True``, override ``updated_by`` protection and
        up-to-date status.  Does **not** override IWH blocked signals.

    Returns
    -------
    DesignUpdateDecision
        Frozen dataclass indicating whether to generate or skip, with
        a human-readable reason and optional skip code.
    """
    import re  # noqa: PLC0415

    import yaml as _yaml  # noqa: PLC0415

    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file_frontmatter,
        parse_design_file_metadata,
    )
    from lexibrary.iwh.reader import read_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR, mirror_path  # noqa: PLC0415

    # ------------------------------------------------------------------
    # 1. Check for IWH blocked signal (overrides --force)
    # ------------------------------------------------------------------
    rel_source = source_path.relative_to(project_root)
    source_dir = source_path.parent
    iwh_dir = project_root / LEXIBRARY_DIR / "designs" / source_dir.relative_to(project_root)
    iwh = None
    if iwh_dir.is_dir():
        iwh = read_iwh(iwh_dir)

    if iwh is not None and iwh.scope == "blocked":
        rel_dir = source_dir.relative_to(project_root)
        body_preview = iwh.body[:200] if iwh.body else ""
        return DesignUpdateDecision(
            action="skip",
            reason=(
                f"IWH blocked signal in {rel_dir}/: {body_preview}. "
                "Resolve the IWH signal before updating."
            ),
            skip_code="iwh_blocked",
        )

    # ------------------------------------------------------------------
    # 2. Check if design file exists
    # ------------------------------------------------------------------
    design_path = mirror_path(project_root, source_path)
    if not design_path.exists():
        return DesignUpdateDecision(
            action="generate",
            reason=f"No design file exists for {rel_source}",
        )

    # ------------------------------------------------------------------
    # 3. Parse frontmatter
    #
    # The typed parser rejects unrecognized ``updated_by`` values via
    # Pydantic validation.  We fall back to raw YAML parsing so that
    # unknown values are treated as protected rather than silently
    # defaulting to "archivist".
    # ------------------------------------------------------------------
    frontmatter = parse_design_file_frontmatter(design_path)
    updated_by: str = "archivist"
    if frontmatter is not None:
        updated_by = frontmatter.updated_by
    else:
        # Typed parser failed -- try raw YAML to capture unknown updated_by
        _FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)  # noqa: N806
        try:
            raw_text = design_path.read_text(encoding="utf-8")
            fm_match = _FM_RE.match(raw_text)
            if fm_match:
                raw_data = _yaml.safe_load(fm_match.group(1))
                if isinstance(raw_data, dict) and "updated_by" in raw_data:
                    updated_by = str(raw_data["updated_by"])
        except (OSError, _yaml.YAMLError):
            pass

    # ------------------------------------------------------------------
    # 4. Evaluate --force: if set, skip protection and staleness checks
    # ------------------------------------------------------------------
    if force:
        return DesignUpdateDecision(
            action="generate",
            reason=f"Force regeneration requested for {rel_source}",
        )

    # ------------------------------------------------------------------
    # 5. Evaluate updated_by protection
    # ------------------------------------------------------------------
    if updated_by in _AUTO_GENERATED_UPDATERS:
        return DesignUpdateDecision(
            action="generate",
            reason=f"Design file was auto-generated (updated_by: {updated_by})",
        )

    if updated_by in _PROTECTED_UPDATERS:
        return DesignUpdateDecision(
            action="skip",
            reason=(f"Design file was last updated by {updated_by}. Use --force / -f to override."),
            skip_code="protected",
        )

    # Unknown updated_by value -- treat as protected.
    # Archivist and curator are both hash-fresh (curator via write_contract)
    # and fall through to the staleness check below.
    if updated_by not in _ARCHIVIST_OWNED_UPDATERS:
        return DesignUpdateDecision(
            action="skip",
            reason=(
                f"Design file has unrecognized updated_by: {updated_by}. "
                "Use --force / -f to override."
            ),
            skip_code="protected",
        )

    # ------------------------------------------------------------------
    # 6. Staleness via metadata footer hash (archivist-owned files)
    # ------------------------------------------------------------------
    metadata = parse_design_file_metadata(design_path)
    if metadata is None:
        # No metadata footer -- treat as stale
        return DesignUpdateDecision(
            action="generate",
            reason=f"Design file for {rel_source} has no metadata footer (treating as stale)",
        )

    try:
        current_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    except OSError:
        # Cannot read source -- treat as stale
        return DesignUpdateDecision(
            action="generate",
            reason=f"Cannot read source file {rel_source} for hash comparison",
        )

    if current_hash == metadata.source_hash:
        return DesignUpdateDecision(
            action="skip",
            reason=f"Design file for {rel_source} is up to date",
            skip_code="up_to_date",
        )

    return DesignUpdateDecision(
        action="generate",
        reason=f"Source file {rel_source} has changed since last generation",
    )
