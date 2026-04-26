"""Upgrade runner: iterate :data:`UPGRADE_STEPS` and collect results."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.upgrade.steps import UPGRADE_STEPS, StepResult


def run_upgrade(
    project_root: Path,
    config: LexibraryConfig,
    *,
    flags: Iterable[str] = (),
) -> list[StepResult]:
    """Run every registered upgrade step that is opted in.

    Each step receives the same ``config`` instance the caller loaded.
    Steps that mutate ``config.yaml`` are responsible for ensuring later
    steps still see correct state — in practice this works because the
    config-migrations step runs first and the rest of the steps rely on
    fields the migration step never touches.

    Steps with ``requires_flag`` set are skipped unless that flag is
    present in ``flags``. Steps without ``requires_flag`` always run.

    Args:
        project_root: Absolute path to the project root.
        config: Loaded :class:`LexibraryConfig` (with legacy keys already
            migrated in memory by the loader).
        flags: Set of opt-in flags. Steps whose ``requires_flag`` is in
            this set will run; others without ``requires_flag`` always
            run. Defaults to the empty set.

    Returns:
        One :class:`StepResult` per executed step, in registry order.
    """
    flag_set = set(flags)
    return [
        step.apply(project_root, config)
        for step in UPGRADE_STEPS
        if step.requires_flag is None or step.requires_flag in flag_set
    ]
