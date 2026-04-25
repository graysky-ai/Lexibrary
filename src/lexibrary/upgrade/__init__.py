"""Lexibrary project upgrade pipeline.

The upgrade pipeline brings an existing ``.lexibrary/`` project up to current
standards: it migrates legacy config keys, stamps the running Lexibrary
version, backfills gitignore patterns, refreshes agent rule files, and
installs git hooks. It is invoked by ``lexictl upgrade``.

Public API:
    run_upgrade: Run every registered upgrade step against a project.
    UpgradeStep: Dataclass describing a single registered step.
    StepResult: Per-step outcome surfaced in the CLI report.
    UPGRADE_STEPS: Ordered list of registered steps.

Future agents adding new features that require an existing project to be
migrated should add a step here. See :mod:`lexibrary.upgrade.steps` for the
extension contract.
"""

from __future__ import annotations

from lexibrary.upgrade.runner import run_upgrade
from lexibrary.upgrade.steps import UPGRADE_STEPS, StepResult, UpgradeStep

__all__ = ["UPGRADE_STEPS", "StepResult", "UpgradeStep", "run_upgrade"]
