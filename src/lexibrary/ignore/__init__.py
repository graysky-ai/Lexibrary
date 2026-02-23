"""Ignore pattern matching system."""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.ignore.gitignore import load_gitignore_specs
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.ignore.patterns import load_config_patterns

__all__ = [
    "create_ignore_matcher",
    "IgnoreMatcher",
    "load_gitignore_specs",
    "load_config_patterns",
]


def create_ignore_matcher(config: LexibraryConfig, root: Path) -> IgnoreMatcher:
    """
    Factory function to create an IgnoreMatcher from configuration.

    Args:
        config: LexibraryConfig with ignore settings.
        root: Project root directory.

    Returns:
        Configured IgnoreMatcher instance.
    """
    # Load config patterns
    config_spec = load_config_patterns(config.ignore)

    # Load .gitignore patterns if enabled
    gitignore_specs = []
    if config.ignore.use_gitignore:
        gitignore_specs = load_gitignore_specs(root)

    # Load .lexignore patterns (optional — missing file is OK)
    lexignore_patterns: list[str] = []
    lexignore_path = root / ".lexignore"
    if lexignore_path.exists():
        lexignore_patterns = lexignore_path.read_text().splitlines()

    return IgnoreMatcher(root, config_spec, gitignore_specs, lexignore_patterns)
