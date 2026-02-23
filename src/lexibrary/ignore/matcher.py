"""Combined ignore pattern matching."""

from __future__ import annotations

from pathlib import Path

import pathspec


class IgnoreMatcher:
    """
    Unified ignore pattern matcher combining config, .gitignore, and .lexignore patterns.

    Checks config patterns first (cheap), then .gitignore specs in hierarchical
    order (most specific directory first), then .lexignore patterns.
    """

    def __init__(
        self,
        root: Path,
        config_spec: pathspec.PathSpec,
        gitignore_specs: list[tuple[Path, pathspec.PathSpec]],
        lexignore_patterns: list[str] | None = None,
    ) -> None:
        """
        Initialize matcher.

        Args:
            root: Project root directory for relative path conversion.
            config_spec: PathSpec from config.ignore.additional_patterns.
            gitignore_specs: List of (directory, PathSpec) tuples from .gitignore files,
                           sorted by depth (root first).
            lexignore_patterns: Patterns from .lexignore file (gitignore format).
        """
        self.root = root.resolve()
        self.config_spec = config_spec
        self.gitignore_specs = gitignore_specs
        self.lexignore_spec = pathspec.PathSpec.from_lines("gitignore", lexignore_patterns or [])

    def _relative_path(self, path: Path, is_dir: bool = False) -> str:
        """
        Convert path to relative string for pattern matching.

        Args:
            path: Absolute or relative path.
            is_dir: If True, append trailing slash for directory matching.

        Returns:
            Path relative to root as string.
        """
        try:
            abs_path = path.resolve()
            rel_path = abs_path.relative_to(self.root)
            path_str = str(rel_path)
            # Append trailing slash for directories (pathspec requirement)
            if is_dir and not path_str.endswith("/"):
                path_str += "/"
            return path_str
        except ValueError:
            # Path is outside root
            path_str = str(path)
            if is_dir and not path_str.endswith("/"):
                path_str += "/"
            return path_str

    def is_ignored(self, path: Path) -> bool:
        """
        Check if path should be ignored.

        Checks config patterns first (cheap), then .gitignore specs in
        hierarchical order (most specific directory first).

        Args:
            path: Path to check (absolute or relative).

        Returns:
            True if path matches any ignore pattern.
        """
        rel_path = self._relative_path(path)

        # Check config patterns first (cheap)
        if self.config_spec.match_file(rel_path):
            return True

        # Check .gitignore specs in reverse order (most specific first)
        # This ensures subdirectory .gitignore files take precedence
        for directory, spec in reversed(self.gitignore_specs):
            # Only check gitignore if path is under its directory
            try:
                abs_path = path.resolve()
                abs_path.relative_to(directory)

                # Path is under this directory, check its patterns
                if spec.match_file(rel_path):
                    return True
            except ValueError:
                # Path not under this directory, skip
                continue

        # Check .lexignore patterns
        return bool(self.lexignore_spec.match_file(rel_path))

    def should_descend(self, directory: Path) -> bool:
        """
        Check if directory should be descended during traversal.

        Enables crawlers to skip entire directory trees without traversing
        their contents.

        Args:
            directory: Directory path to check.

        Returns:
            True if directory should be traversed, False to skip.
        """
        rel_path = self._relative_path(directory, is_dir=True)

        # Check config patterns first (cheap)
        if self.config_spec.match_file(rel_path):
            return False

        # Check .gitignore specs
        for directory_path, spec in reversed(self.gitignore_specs):
            try:
                abs_path = directory.resolve()
                abs_path.relative_to(directory_path)

                if spec.match_file(rel_path):
                    return False
            except ValueError:
                continue

        # Check .lexignore patterns
        return not self.lexignore_spec.match_file(rel_path)
