"""Create the .lexibrary/ directory skeleton for a new project."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from lexibrary.config.schema import LexibraryConfig
from lexibrary.iwh.gitignore import ensure_iwh_gitignored
from lexibrary.templates import read_template

if TYPE_CHECKING:
    from lexibrary.init.wizard import WizardAnswers

LEXIBRARY_DIR = ".lexibrary"

# Patterns for generated artifacts that should be gitignored.
# The link graph index.db needs an explicit entry (it's inside .lexibrary/
# but called out for clarity).
_GENERATED_GITIGNORE_PATTERNS = [".lexibrary/index.db"]

LEXIGNORE_HEADER = read_template("scaffolder/lexignore_header.txt")

# Default patterns always included in .lexignore to prevent sensitive files
# (particularly API keys in dotenv files) from being indexed as source content.
_DEFAULT_LEXIGNORE_PATTERNS = [
    ".env",
    ".env.*",
    "*.env",
]

_CONFIG_YAML_HEADER = read_template("scaffolder/config_yaml_header.txt")


def _generate_lexignore(patterns: list[str]) -> str:
    """Build ``.lexignore`` content from wizard-collected patterns.

    The output always starts with :data:`LEXIGNORE_HEADER`, followed by
    :data:`_DEFAULT_LEXIGNORE_PATTERNS` (e.g. ``.env`` patterns to prevent
    API keys from being indexed).  If *patterns* is non-empty, each
    user-provided pattern is appended after the defaults.

    Args:
        patterns: Additional gitignore-style glob patterns to include.

    Returns:
        Complete ``.lexignore`` file content.
    """
    all_patterns = list(_DEFAULT_LEXIGNORE_PATTERNS)
    for p in patterns:
        if p not in all_patterns:
            all_patterns.append(p)

    return LEXIGNORE_HEADER + "\n".join(all_patterns) + "\n"


def _generate_config_yaml(answers: WizardAnswers) -> str:
    """Build config YAML from wizard answers with Pydantic validation.

    Constructs a config dict from *answers*, validates it through
    :class:`~lexibrary.config.schema.LexibraryConfig`, then serialises to
    YAML.  A ``ValidationError`` is raised before any output if the data
    is invalid.

    Args:
        answers: Completed wizard answers dataclass.

    Returns:
        YAML string including a header comment, ready to write to disk.
    """
    config_dict: dict[str, Any] = {
        "scope_root": answers.scope_root,
        "project_name": answers.project_name,
        "agent_environment": answers.agent_environments,
        "iwh": {"enabled": answers.iwh_enabled},
        "llm": {
            "provider": answers.llm_provider,
            "model": answers.llm_model,
            "api_key_env": answers.llm_api_key_env,
            "api_key_source": answers.llm_api_key_source,
        },
    }

    if answers.token_budgets_customized and answers.token_budgets:
        config_dict["token_budgets"] = answers.token_budgets

    # Validate through Pydantic — raises ValidationError on bad data
    LexibraryConfig.model_validate(config_dict)

    return _CONFIG_YAML_HEADER + yaml.dump(
        config_dict,
        sort_keys=False,
        default_flow_style=False,
    )


def _ensure_generated_files_gitignored(project_root: Path) -> bool:
    """Ensure generated artifacts are listed in ``.gitignore``.

    Appends ``.lexibrary/index.db`` to the project's ``.gitignore`` if
    it is not already present.  Creates the ``.gitignore`` file if it
    does not exist.

    Args:
        project_root: Root directory of the project.

    Returns:
        ``True`` if the file was modified (or created), ``False`` if all
        patterns were already present.
    """
    gitignore_path = project_root / ".gitignore"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        existing_patterns = {line.strip() for line in content.splitlines() if line.strip()}
    else:
        content = ""
        existing_patterns = set()

    missing = [p for p in _GENERATED_GITIGNORE_PATTERNS if p not in existing_patterns]
    if not missing:
        return False

    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n".join(missing) + "\n"
    gitignore_path.write_text(content, encoding="utf-8")
    return True


def create_lexibrary_skeleton(project_root: Path) -> list[Path]:
    """Create the ``.lexibrary/`` directory skeleton at *project_root*.

    Idempotent — existing files are never overwritten.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of paths that were created (empty if skeleton already exists).
    """
    base = project_root / LEXIBRARY_DIR
    created: list[Path] = []

    # Directories
    for subdir in [
        base,
        base / "concepts",
        base / "conventions",
        base / "designs",
        base / "stack",
    ]:
        if not subdir.exists():
            subdir.mkdir(parents=True)
            created.append(subdir)

    # .gitkeep files for empty directories
    for gitkeep in [
        base / "concepts" / ".gitkeep",
        base / "conventions" / ".gitkeep",
        base / "designs" / ".gitkeep",
        base / "stack" / ".gitkeep",
    ]:
        if not gitkeep.exists():
            gitkeep.touch()
            created.append(gitkeep)

    # Template files — never overwrite existing
    files: dict[Path, str] = {
        base / "config.yaml": read_template("config/default_config.yaml"),
        project_root / ".lexignore": _generate_lexignore([]),
    }
    for path, content in files.items():
        if not path.exists():
            path.write_text(content)
            created.append(path)

    # Ensure .iwh files are gitignored
    ensure_iwh_gitignored(project_root)

    # Ensure generated artifacts are gitignored
    _ensure_generated_files_gitignored(project_root)

    return created


def create_lexibrary_from_wizard(
    project_root: Path,
    answers: WizardAnswers,
) -> list[Path]:
    """Create the ``.lexibrary/`` skeleton using wizard answers.

    Unlike :func:`create_lexibrary_skeleton`, this function generates the
    config file dynamically from *answers* rather than using a static
    template.

    Args:
        project_root: Absolute path to the project root directory.
        answers: Completed :class:`WizardAnswers` from the init wizard.

    Returns:
        List of all created file and directory paths.
    """
    base = project_root / LEXIBRARY_DIR
    created: list[Path] = []

    # Directories
    for subdir in [
        base,
        base / "concepts",
        base / "conventions",
        base / "designs",
        base / "stack",
    ]:
        if not subdir.exists():
            subdir.mkdir(parents=True)
            created.append(subdir)

    # .gitkeep files for empty directories
    for gitkeep in [
        base / "concepts" / ".gitkeep",
        base / "conventions" / ".gitkeep",
        base / "designs" / ".gitkeep",
        base / "stack" / ".gitkeep",
    ]:
        if not gitkeep.exists():
            gitkeep.touch()
            created.append(gitkeep)

    # Config from wizard answers (validated through Pydantic)
    config_path = base / "config.yaml"
    if not config_path.exists():
        config_path.write_text(_generate_config_yaml(answers))
        created.append(config_path)

    # .lexignore with wizard-provided patterns
    lexignore_path = project_root / ".lexignore"
    if not lexignore_path.exists():
        lexignore_path.write_text(_generate_lexignore(answers.ignore_patterns))
        created.append(lexignore_path)

    # Ensure .iwh files are gitignored
    ensure_iwh_gitignored(project_root)

    # Ensure generated artifacts are gitignored
    _ensure_generated_files_gitignored(project_root)

    return created
