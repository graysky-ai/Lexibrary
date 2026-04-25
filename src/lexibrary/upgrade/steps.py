"""Registered upgrade steps.

Each step is a self-contained, idempotent migration. The CLI command
``lexictl upgrade`` runs them in order against an existing project and
prints a per-step report.

Adding a new step
-----------------
When a new Lexibrary feature requires existing projects to be migrated
(e.g. a new config field, a new generated artifact that needs gitignoring,
a new ``.lexibrary/`` subdirectory), wire it in here:

1. Write a function ``apply_<thing>(project_root, config) -> StepResult``
   in this module. The function MUST be idempotent — running it twice in
   a row should produce ``changed=False`` on the second call.
2. Append a new :class:`UpgradeStep` entry to :data:`UPGRADE_STEPS`. Order
   matters — config migrations run first so later steps can read the
   migrated config.
3. Add a unit test in ``tests/test_upgrade/`` covering both the
   "needs upgrade" and the "already current" paths.

Step functions take ``(project_root, config)`` so they can read declared
config without re-loading it. They return a :class:`StepResult`; the CLI
formats ``[updated]`` / ``[ok]`` based on the ``changed`` flag.

If a step needs to mutate ``config.yaml``, prefer routing through
:func:`lexibrary.upgrade.config_writer.rewrite_config_yaml` so all writes
share one round-trip strategy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig


@dataclass
class StepResult:
    """Outcome of a single upgrade step.

    Attributes:
        name: Step identifier (matches the registered :class:`UpgradeStep`).
        changed: ``True`` if the step modified project state. ``False`` if
            the project was already current.
        summary: One-line status, shown next to the step name.
        details: Optional list of per-item details (one per line in the
            CLI report). Use for things like "added 3 patterns: ...".
        warnings: Non-fatal issues encountered while applying the step.
    """

    name: str
    changed: bool
    summary: str
    details: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpgradeStep:
    """A registered upgrade step.

    Attributes:
        name: Stable identifier (snake-case). Used in the CLI report and
            for opting steps in/out of tests.
        description: One-line human-readable explanation. Surfaced by
            ``lexictl upgrade --list``.
        apply: Callable invoked with ``(project_root, config)`` that
            performs the upgrade and returns a :class:`StepResult`.
    """

    name: str
    description: str
    apply: Callable[[Path, LexibraryConfig], StepResult]


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def apply_config_migrations(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Persist in-memory config-key migrations back to ``.lexibrary/config.yaml``.

    The loader transparently rewrites legacy keys in memory
    (``daemon:`` → ``sweep:``, ``scope_root:`` → ``scope_roots:``); this
    step writes the same change to disk so the deprecation warning stops
    firing on every command.

    Idempotent: when no legacy keys are present, returns ``changed=False``.
    """
    from lexibrary.upgrade.config_writer import (
        legacy_keys_present,
        rewrite_config_yaml,
    )

    config_path = project_root / ".lexibrary" / "config.yaml"
    legacy = legacy_keys_present(config_path)
    if not legacy:
        return StepResult(
            name="config-migrations",
            changed=False,
            summary="no legacy keys in config.yaml",
        )

    rewrite_config_yaml(config_path)
    return StepResult(
        name="config-migrations",
        changed=True,
        summary=f"rewrote legacy key(s): {', '.join(sorted(legacy))}",
        details=[f"backup written to {config_path.name}.bak"],
    )


def apply_version_stamp(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Record the running Lexibrary version in ``config.yaml``.

    Reads the version from :data:`lexibrary.__version__` (the canonical
    in-tree value, reliable for both PyPI and editable installs). Writes
    it to ``lexibrary_version:`` in the project config when the recorded
    value is missing or stale.
    """
    from lexibrary import __version__ as current_version
    from lexibrary.upgrade.config_writer import set_config_value

    if config.lexibrary_version == current_version:
        return StepResult(
            name="version-stamp",
            changed=False,
            summary=f"already at {current_version}",
        )

    config_path = project_root / ".lexibrary" / "config.yaml"
    old = config.lexibrary_version or "(unset)"
    set_config_value(config_path, "lexibrary_version", current_version)
    return StepResult(
        name="version-stamp",
        changed=True,
        summary=f"{old} → {current_version}",
    )


def apply_skeleton_directories(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Create any missing ``.lexibrary/`` subdirectories.

    Idempotent — only the directories that don't yet exist are created.
    Mirrors the directory list used by
    :func:`lexibrary.init.scaffolder.create_lexibrary_skeleton`.
    """
    base = project_root / ".lexibrary"
    expected = ["concepts", "conventions", "designs", "stack"]
    created: list[str] = []
    for sub in expected:
        d = base / sub
        if not d.exists():
            d.mkdir(parents=True)
            (d / ".gitkeep").touch()
            created.append(sub)

    if not created:
        return StepResult(
            name="skeleton-directories",
            changed=False,
            summary="all .lexibrary/ subdirectories present",
        )
    return StepResult(
        name="skeleton-directories",
        changed=True,
        summary=f"created {len(created)} subdirectory/ies",
        details=[f"+ .lexibrary/{name}/" for name in created],
    )


def apply_gitignore_patterns(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Backfill ``.gitignore`` patterns for generated Lexibrary artifacts.

    Pulls the canonical pattern list from
    :data:`lexibrary.init.scaffolder._GENERATED_GITIGNORE_PATTERNS` so a
    single source of truth governs both ``init`` and ``upgrade``.
    """
    from lexibrary.init.scaffolder import (
        _GENERATED_GITIGNORE_PATTERNS,
        _ensure_generated_files_gitignored,
    )

    gitignore_path = project_root / ".gitignore"
    existing: set[str] = set()
    if gitignore_path.exists():
        existing = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    missing_before = [p for p in _GENERATED_GITIGNORE_PATTERNS if p not in existing]

    changed = _ensure_generated_files_gitignored(project_root)
    if not changed:
        return StepResult(
            name="gitignore-patterns",
            changed=False,
            summary=".gitignore already has all generated-artifact patterns",
        )
    return StepResult(
        name="gitignore-patterns",
        changed=True,
        summary=f"added {len(missing_before)} pattern(s) to .gitignore",
        details=[f"+ {p}" for p in missing_before],
    )


def apply_iwh_gitignore(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Ensure ``.iwh`` signal files are gitignored.

    Wraps :func:`lexibrary.iwh.gitignore.ensure_iwh_gitignored`, which
    appends the ``**/.iwh`` pattern when missing and is a no-op otherwise.
    """
    from lexibrary.iwh.gitignore import ensure_iwh_gitignored

    changed = ensure_iwh_gitignored(project_root)
    if not changed:
        return StepResult(
            name="iwh-gitignore",
            changed=False,
            summary="**/.iwh already gitignored",
        )
    return StepResult(
        name="iwh-gitignore",
        changed=True,
        summary="added **/.iwh to .gitignore",
    )


def _hash_rule_tree(project_root: Path) -> dict[Path, bytes]:
    """Hash every existing file under the known agent-rule locations.

    Used by :func:`apply_agent_rules` to detect whether regeneration
    actually changed anything on disk. Hashes ``CLAUDE.md``, ``AGENTS.md``,
    everything under ``.claude/`` and ``.cursor/`` recursively.
    """
    import hashlib

    targets: list[Path] = [
        project_root / "CLAUDE.md",
        project_root / "AGENTS.md",
    ]
    for d in (project_root / ".claude", project_root / ".cursor"):
        if d.is_dir():
            targets.extend(p for p in d.rglob("*") if p.is_file())

    out: dict[Path, bytes] = {}
    for p in targets:
        if p.exists() and p.is_file():
            out[p] = hashlib.sha256(p.read_bytes()).digest()
    return out


def apply_agent_rules(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Regenerate agent rule files for every configured environment.

    Writes CLAUDE.md, .cursor/rules, etc., according to
    ``config.agent_environment``. Skipped (with a warning) when no
    environments are configured.

    Idempotent: hashes the rule-file tree before and after regeneration,
    and reports ``changed=False`` when the output is byte-identical.
    """
    from lexibrary.init.rules import generate_rules, supported_environments

    environments = list(config.agent_environment)
    if not environments:
        return StepResult(
            name="agent-rules",
            changed=False,
            summary="no agent_environment configured; skipped",
            warnings=[
                "Set agent_environment in .lexibrary/config.yaml to "
                "regenerate CLAUDE.md / .cursor/rules on upgrade."
            ],
        )

    supported = supported_environments()
    unsupported = [e for e in environments if e not in supported]
    valid = [e for e in environments if e in supported]
    warnings: list[str] = []
    if unsupported:
        warnings.append(
            f"unsupported environment(s) skipped: {', '.join(sorted(unsupported))}. "
            f"Supported: {', '.join(supported)}"
        )

    if not valid:
        return StepResult(
            name="agent-rules",
            changed=False,
            summary="no valid environments to generate",
            warnings=warnings,
        )

    before = _hash_rule_tree(project_root)
    results = generate_rules(project_root, valid)
    after = _hash_rule_tree(project_root)

    actually_changed = before != after
    total = sum(len(paths) for paths in results.values())
    if not actually_changed:
        return StepResult(
            name="agent-rules",
            changed=False,
            summary=f"all {total} rule file(s) already current",
            warnings=warnings,
        )

    detail_lines = [
        f"{env}: {', '.join(p.relative_to(project_root).as_posix() for p in paths)}"
        for env, paths in results.items()
    ]
    return StepResult(
        name="agent-rules",
        changed=True,
        summary=f"regenerated {total} rule file(s) for {len(valid)} environment(s)",
        details=detail_lines,
        warnings=warnings,
    )


def apply_git_hooks(project_root: Path, config: LexibraryConfig) -> StepResult:
    """Install Lexibrary's pre-commit and post-commit git hooks.

    Idempotent — the underlying installers detect their hook marker and
    short-circuit when already installed. Skipped (not failed) when the
    project has no ``.git`` directory.
    """
    from lexibrary.hooks.post_commit import install_post_commit_hook
    from lexibrary.hooks.pre_commit import install_pre_commit_hook

    post = install_post_commit_hook(project_root)
    if post.no_git_dir:
        return StepResult(
            name="git-hooks",
            changed=False,
            summary="no .git directory; skipped",
        )

    pre = install_pre_commit_hook(project_root)
    installed_now: list[str] = []
    already: list[str] = []
    if post.installed:
        installed_now.append("post-commit")
    elif post.already_installed:
        already.append("post-commit")
    if pre.installed:
        installed_now.append("pre-commit")
    elif pre.already_installed:
        already.append("pre-commit")

    if installed_now:
        details = [f"installed: {', '.join(installed_now)}"]
        if already:
            details.append(f"already present: {', '.join(already)}")
        return StepResult(
            name="git-hooks",
            changed=True,
            summary=f"installed {len(installed_now)} hook(s)",
            details=details,
        )
    return StepResult(
        name="git-hooks",
        changed=False,
        summary=f"all hooks already installed ({', '.join(already)})",
    )


# ---------------------------------------------------------------------------
# Registry — order matters
# ---------------------------------------------------------------------------

UPGRADE_STEPS: list[UpgradeStep] = [
    UpgradeStep(
        name="config-migrations",
        description=(
            "Persist legacy config-key renames (scope_root → scope_roots, "
            "daemon → sweep) to disk so deprecation warnings stop firing."
        ),
        apply=apply_config_migrations,
    ),
    UpgradeStep(
        name="version-stamp",
        description="Record the running Lexibrary version in config.yaml.",
        apply=apply_version_stamp,
    ),
    UpgradeStep(
        name="skeleton-directories",
        description="Create any missing .lexibrary/ subdirectories.",
        apply=apply_skeleton_directories,
    ),
    UpgradeStep(
        name="gitignore-patterns",
        description="Backfill .gitignore patterns for generated artifacts.",
        apply=apply_gitignore_patterns,
    ),
    UpgradeStep(
        name="iwh-gitignore",
        description="Ensure **/.iwh signal files are gitignored.",
        apply=apply_iwh_gitignore,
    ),
    UpgradeStep(
        name="agent-rules",
        description="Regenerate agent rule files (CLAUDE.md, .cursor/rules).",
        apply=apply_agent_rules,
    ),
    UpgradeStep(
        name="git-hooks",
        description="Install pre-commit and post-commit git hooks.",
        apply=apply_git_hooks,
    ),
]
