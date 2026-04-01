"""View service -- resolve an artifact ID and load its parsed content.

Provides the business logic for the ``lexi view`` command.  Accepts an
artifact ID in ``XX-NNN`` format, resolves it to a file on disk via
:func:`~lexibrary.artifacts.ids.find_artifact_path`, and dispatches to
the appropriate parser.  Returns a :class:`ViewResult` dataclass on
success, or raises a :class:`ViewError` subclass on failure.

No terminal output or CLI dependencies -- all formatting is handled
by the paired ``view_render.py`` module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.artifacts.convention import ConventionFile
from lexibrary.artifacts.design_file import DesignFile
from lexibrary.artifacts.ids import (
    ARTIFACT_PREFIXES,
    find_artifact_path,
    kind_for_prefix,
    parse_artifact_id,
)
from lexibrary.artifacts.playbook import PlaybookFile
from lexibrary.exceptions import LexibraryError
from lexibrary.stack.models import StackPost

# ---------------------------------------------------------------------------
# Type alias for parsed artifact content
# ---------------------------------------------------------------------------

ArtifactContent = ConceptFile | ConventionFile | PlaybookFile | DesignFile | StackPost

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ViewResult:
    """Data returned by :func:`resolve_and_load` on success."""

    kind: str
    """Artifact kind name (e.g. ``"concept"``, ``"stack"``)."""

    artifact_id: str
    """The resolved artifact ID in ``XX-NNN`` format."""

    file_path: Path
    """Absolute path to the artifact file on disk."""

    content: ArtifactContent
    """Fully parsed artifact model."""


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ViewError(LexibraryError):
    """Base exception for view-service errors.

    Carries the original *artifact_id* (if available) and a human-readable
    *hint* for agent consumers.
    """

    def __init__(self, message: str, *, artifact_id: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.artifact_id = artifact_id
        self.hint = hint


class InvalidArtifactIdError(ViewError):
    """The supplied string is not in ``XX-NNN`` artifact ID format."""


class UnknownPrefixError(ViewError):
    """The 2-letter prefix is syntactically valid but not a known artifact type."""


class ArtifactNotFoundError(ViewError):
    """The artifact ID is valid, but no matching file exists on disk."""


class ArtifactParseError(ViewError):
    """The file was found but the parser returned ``None``."""


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------

# Maps artifact kind -> (module_path, function_name) for lazy imports.
_PARSER_DISPATCH: dict[str, tuple[str, str]] = {
    "concept": ("lexibrary.wiki.parser", "parse_concept_file"),
    "convention": ("lexibrary.conventions.parser", "parse_convention_file"),
    "playbook": ("lexibrary.playbooks.parser", "parse_playbook_file"),
    "design": ("lexibrary.artifacts.design_file_parser", "parse_design_file"),
    "stack": ("lexibrary.stack.parser", "parse_stack_post"),
}


def resolve_and_load(project_root: Path, artifact_id: str) -> ViewResult:
    """Resolve *artifact_id* to its file and return the parsed content.

    Parameters
    ----------
    project_root:
        The project root directory (containing ``.lexibrary/``).
    artifact_id:
        An artifact ID in ``XX-NNN`` format (e.g. ``"CN-001"``).

    Returns
    -------
    ViewResult
        The resolved artifact with parsed content.

    Raises
    ------
    InvalidArtifactIdError
        If *artifact_id* does not match the ``XX-NNN`` format.
    UnknownPrefixError
        If the 2-letter prefix is not a recognised artifact type.
    ArtifactNotFoundError
        If no file matches the artifact ID on disk.
    ArtifactParseError
        If the file exists but the parser returns ``None``.
    """
    # 1. Validate ID format
    parsed = parse_artifact_id(artifact_id)
    if parsed is None:
        valid_prefixes = ", ".join(sorted(ARTIFACT_PREFIXES.values()))
        raise InvalidArtifactIdError(
            f"Invalid artifact ID format: {artifact_id!r}",
            artifact_id=artifact_id,
            hint=f"Expected format: XX-NNN (e.g. CN-001). Valid prefixes: {valid_prefixes}",
        )

    prefix, _number = parsed

    # 2. Validate prefix
    kind = kind_for_prefix(prefix)
    if kind is None:
        valid_prefixes = ", ".join(sorted(ARTIFACT_PREFIXES.values()))
        raise UnknownPrefixError(
            f"Unknown artifact prefix: {prefix!r}",
            artifact_id=artifact_id,
            hint=f"Valid prefixes: {valid_prefixes}",
        )

    # 3. Find the artifact file
    file_path = find_artifact_path(project_root, artifact_id)
    if file_path is None:
        raise ArtifactNotFoundError(
            f"Artifact not found: {artifact_id}",
            artifact_id=artifact_id,
            hint=f"No {kind} file found for {artifact_id}. Check that the artifact exists.",
        )

    # 4. Parse via lazy dispatch
    content = _load_artifact(kind, file_path)
    if content is None:
        raise ArtifactParseError(
            f"Failed to parse artifact: {artifact_id}",
            artifact_id=artifact_id,
            hint=f"File found at {file_path} but the parser returned None.",
        )

    return ViewResult(
        kind=kind,
        artifact_id=artifact_id,
        file_path=file_path,
        content=content,
    )


def _load_artifact(kind: str, file_path: Path) -> ArtifactContent | None:
    """Dispatch to the correct parser for *kind* and return the parsed model.

    Uses lazy imports to avoid loading all parsers at module level.
    """
    import importlib  # noqa: PLC0415

    dispatch = _PARSER_DISPATCH.get(kind)
    if dispatch is None:
        return None

    module_path, func_name = dispatch
    module = importlib.import_module(module_path)
    parser_fn = getattr(module, func_name)
    return parser_fn(file_path)  # type: ignore[no-any-return]
