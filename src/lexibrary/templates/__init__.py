"""Template loading utilities for Lexibrary.

Provides ``read_template()`` to load static template files bundled inside the
``lexibrary.templates`` package.  Templates are loaded via
``importlib.resources.files()`` so they work correctly whether Lexibrary is
installed from a wheel or run from a source checkout.
"""

from __future__ import annotations

from importlib.resources import files


def read_template(resource_path: str) -> str:
    """Load a template file from the ``lexibrary.templates`` package.

    Parameters
    ----------
    resource_path:
        Slash-separated path relative to ``src/lexibrary/templates/``,
        e.g. ``"rules/core_rules.md"`` or ``"hooks/post-commit.sh"``.

    Returns
    -------
    str
        The raw file content, including any trailing newline.

    Raises
    ------
    FileNotFoundError
        If the requested template does not exist.
    """
    parts = resource_path.split("/")
    traversable = files("lexibrary.templates")
    for part in parts:
        traversable = traversable.joinpath(part)

    try:
        return traversable.read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, IsADirectoryError):
        msg = f"Template not found: {resource_path}"
        raise FileNotFoundError(msg) from None
