"""Upgrade runner: iterate :data:`UPGRADE_STEPS` and collect results."""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.upgrade.steps import UPGRADE_STEPS, StepResult


def run_upgrade(project_root: Path, config: LexibraryConfig) -> list[StepResult]:
    """Run every registered upgrade step in order.

    Each step receives the same ``config`` instance the caller loaded.
    Steps that mutate ``config.yaml`` are responsible for ensuring later
    steps still see correct state — in practice this works because the
    config-migrations step runs first and the rest of the steps rely on
    fields the migration step never touches.

    Args:
        project_root: Absolute path to the project root.
        config: Loaded :class:`LexibraryConfig` (with legacy keys already
            migrated in memory by the loader).

    Returns:
        One :class:`StepResult` per registered step, in registry order.
    """
    return [step.apply(project_root, config) for step in UPGRADE_STEPS]
