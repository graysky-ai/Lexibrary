"""Config-based pattern matching."""

from __future__ import annotations

import pathspec

from lexibrary.config.schema import IgnoreConfig


def load_config_patterns(config: IgnoreConfig) -> pathspec.PathSpec:
    """
    Create a PathSpec from config-defined ignore patterns.

    Args:
        config: IgnoreConfig with additional_patterns list.

    Returns:
        PathSpec for matching paths against config patterns.
    """
    return pathspec.PathSpec.from_lines("gitignore", config.additional_patterns)
