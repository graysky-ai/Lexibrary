"""Gitignore integration for IWH files."""

from __future__ import annotations

from pathlib import Path

# The canonical gitignore pattern for IWH files
IWH_GITIGNORE_PATTERN = "**/.iwh"

# Alternative patterns that are considered equivalent coverage
_ALTERNATIVE_PATTERNS = frozenset(
    {
        "**/.iwh",
        ".iwh",
        ".lexibrary/**/.iwh",
    }
)


def ensure_iwh_gitignored(project_root: Path) -> bool:
    """Ensure that ``.iwh`` files are listed in ``.gitignore``.

    Appends the ``**/.iwh`` pattern to the project's ``.gitignore`` if no
    equivalent pattern is already present.  Creates the ``.gitignore``
    file if it does not exist.

    Args:
        project_root: Root directory of the project (where ``.gitignore``
            lives).

    Returns:
        ``True`` if the file was modified (or created), ``False`` if the
        pattern was already present.
    """
    gitignore_path = project_root / ".gitignore"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        existing_patterns = {line.strip() for line in content.splitlines() if line.strip()}

        # Check if any equivalent pattern is already present
        if existing_patterns & _ALTERNATIVE_PATTERNS:
            return False

        # Append the pattern, ensuring a newline before it if needed
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{IWH_GITIGNORE_PATTERN}\n"
        gitignore_path.write_text(content, encoding="utf-8")
        return True

    # Create new .gitignore with the pattern
    gitignore_path.write_text(f"{IWH_GITIGNORE_PATTERN}\n", encoding="utf-8")
    return True
