"""Agent environment rule generation.

Public API:
    generate_rules: Generate agent rule files for specified environments.
    supported_environments: Return list of supported environment names.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from lexibrary.init.rules.claude import generate_claude_rules
from lexibrary.init.rules.codex import generate_codex_rules
from lexibrary.init.rules.cursor import generate_cursor_rules

_GENERATORS: dict[str, Callable[[Path], list[Path]]] = {
    "claude": generate_claude_rules,
    "cursor": generate_cursor_rules,
    "codex": generate_codex_rules,
}


def supported_environments() -> list[str]:
    """Return the list of supported agent environment names.

    Returns:
        Sorted list of environment name strings (e.g. ``["claude", "codex", "cursor"]``).
    """
    return sorted(_GENERATORS.keys())


def generate_rules(
    project_root: Path,
    environments: list[str],
) -> dict[str, list[Path]]:
    """Generate agent rule files for the specified environments.

    Iterates over *environments* and calls the corresponding generator
    for each one.  Unknown environment names raise :class:`ValueError`.

    Args:
        project_root: Absolute path to the project root directory.
        environments: List of environment names to generate rules for
            (e.g. ``["claude", "cursor"]``).

    Returns:
        Mapping of environment name to the list of absolute paths
        created or updated by that environment's generator.

    Raises:
        ValueError: If any environment name is not in
            :func:`supported_environments`.
    """
    unsupported = [env for env in environments if env not in _GENERATORS]
    if unsupported:
        supported = ", ".join(sorted(_GENERATORS.keys()))
        bad = ", ".join(sorted(unsupported))
        msg = f"Unsupported environment(s): {bad}. Supported environments: {supported}"
        raise ValueError(msg)

    results: dict[str, list[Path]] = {}
    for env in environments:
        generator = _GENERATORS[env]
        results[env] = generator(project_root)
    return results
