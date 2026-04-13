"""Pure detection functions for project auto-discovery.

All functions take ``project_root: Path`` and return typed results.
No stdout I/O, no Rich output -- fully testable with ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class DetectedProject(NamedTuple):
    """Result of project name detection."""

    name: str
    source: str  # "pyproject.toml" | "package.json" | "directory"


class DetectedLLMProvider(NamedTuple):
    """Result of LLM provider detection."""

    provider: str
    api_key_env: str
    model: str


# ---------------------------------------------------------------------------
# Provider registry (priority order)
# ---------------------------------------------------------------------------

_LLM_PROVIDERS: list[tuple[str, str, str]] = [
    ("anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-4-6"),
    ("openai", "OPENAI_API_KEY", "gpt-4o"),
    ("google", "GEMINI_API_KEY", "gemini-2.0-flash"),
    ("ollama", "OLLAMA_HOST", "llama3"),
]

# ---------------------------------------------------------------------------
# Agent environment mapping
# ---------------------------------------------------------------------------

_AGENT_MARKERS: list[tuple[str, list[str]]] = [
    # (environment_name, [marker_paths...])
    ("claude", [".claude/", "CLAUDE.md"]),
    ("cursor", [".cursor/"]),
    ("codex", ["AGENTS.md"]),
]

_AGENT_RULES_FILES: dict[str, list[str]] = {
    "claude": ["CLAUDE.md", ".claude/CLAUDE.md"],
    "cursor": [".cursor/rules"],
    "codex": ["AGENTS.md"],
}

# Directories that each environment's rule generator will create.
# Used by the wizard to warn the user when base directories are missing.
_AGENT_REQUIRED_DIRS: dict[str, list[str]] = {
    "claude": [".claude/", ".claude/skills/"],
    "cursor": [".cursor/", ".cursor/rules/", ".cursor/skills/"],
    "codex": [],  # codex only writes AGENTS.md at root
}

# ---------------------------------------------------------------------------
# Ignore pattern suggestions per project type
# ---------------------------------------------------------------------------

_IGNORE_PATTERNS: dict[str, list[str]] = {
    "python": ["**/migrations/", "**/__generated__/"],
    "node": ["dist/", "build/", "coverage/", ".next/"],
    "typescript": ["dist/", "build/", "coverage/", ".next/"],
    "rust": ["target/"],
    "go": ["vendor/"],
}

# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------


def detect_project_name(project_root: Path) -> DetectedProject:
    """Detect the project name with precedence: pyproject.toml -> package.json -> directory name.

    Uses ``tomllib`` (stdlib) for TOML and ``json`` (stdlib) for JSON.
    """
    # Try pyproject.toml first
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            name = data.get("project", {}).get("name")
            if name:
                return DetectedProject(name=name, source="pyproject.toml")
        except Exception:  # noqa: BLE001 — malformed TOML falls through
            pass

    # Try package.json
    package_json = project_root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            name = data.get("name")
            if name:
                return DetectedProject(name=name, source="package.json")
        except Exception:  # noqa: BLE001 — malformed JSON falls through
            pass

    # Fallback to directory name
    return DetectedProject(name=project_root.name, source="directory")


def detect_scope_roots(project_root: Path) -> list[str]:
    """Check for common source directories and return those that exist.

    Candidates are checked in declared order; ``baml_src/`` is included
    alongside the historical ``src/``, ``lib/``, ``app/`` set so multi-root
    projects (e.g. Python source plus BAML schemas) light up by default in
    the wizard's checkbox UI.
    """
    candidates = ["src/", "lib/", "app/", "baml_src/"]
    return [d for d in candidates if (project_root / d.rstrip("/")).is_dir()]


def detect_agent_environments(project_root: Path) -> list[str]:
    """Detect agent environments from filesystem markers.

    Returns a deduplicated list of environment names (e.g. ``["claude", "cursor"]``).
    """
    found: list[str] = []
    for env_name, markers in _AGENT_MARKERS:
        for marker in markers:
            path = project_root / marker
            exists = path.is_dir() if marker.endswith("/") else path.is_file()
            if exists and env_name not in found:
                found.append(env_name)
                break  # no need to check remaining markers for this env
    return found


def get_all_agent_environments() -> list[str]:
    """Return all supported agent environment names from the registry.

    Unlike :func:`detect_agent_environments`, this does not inspect the
    filesystem — it returns every known environment name.  Used by the
    wizard to populate the full checkbox list.
    """
    return [env_name for env_name, _markers in _AGENT_MARKERS]


def check_existing_agent_rules(
    project_root: Path,
    environment: str,
) -> str | None:
    """Search for a ``<!-- lexibrary:`` marker in the rules file for *environment*.

    Returns the file path (as string) if found, ``None`` otherwise.
    """
    candidates = _AGENT_RULES_FILES.get(environment, [])
    for rel in candidates:
        path = project_root / rel
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                if "<!-- lexibrary:" in content:
                    return str(path)
            except Exception:  # noqa: BLE001
                pass
    return None


def check_missing_agent_dirs(
    project_root: Path,
    environments: list[str],
) -> dict[str, list[str]]:
    """Check which agent environments have missing base directories.

    Returns a mapping of environment name to list of missing directory paths
    (relative to *project_root*).  Environments with no missing directories
    are omitted from the result.
    """
    missing: dict[str, list[str]] = {}
    for env in environments:
        dirs = _AGENT_REQUIRED_DIRS.get(env, [])
        env_missing = [d for d in dirs if not (project_root / d.rstrip("/")).is_dir()]
        if env_missing:
            missing[env] = env_missing
    return missing


def detect_llm_providers() -> list[DetectedLLMProvider]:
    """Check environment variables for known LLM providers in priority order.

    Returns all providers whose env var is set.
    """
    return [
        DetectedLLMProvider(provider=provider, api_key_env=env_var, model=model)
        for provider, env_var, model in _LLM_PROVIDERS
        if os.environ.get(env_var)
    ]


def get_all_llm_providers() -> list[DetectedLLMProvider]:
    """Return all known LLM providers from the registry in priority order.

    Unlike :func:`detect_llm_providers`, this returns every provider
    regardless of whether its environment variable is set.  Used by the
    wizard to populate the full selection list.
    """
    return [
        DetectedLLMProvider(provider=provider, api_key_env=env_var, model=model)
        for provider, env_var, model in _LLM_PROVIDERS
    ]


def detect_project_type(project_root: Path) -> str | None:
    """Detect the project type from marker files.

    Returns one of ``"python"``, ``"typescript"``, ``"node"``, ``"rust"``,
    ``"go"``, or ``None``.
    """
    if (project_root / "pyproject.toml").is_file() or (project_root / "setup.py").is_file():
        return "python"
    if (project_root / "package.json").is_file():
        if (project_root / "tsconfig.json").is_file():
            return "typescript"
        return "node"
    if (project_root / "Cargo.toml").is_file():
        return "rust"
    if (project_root / "go.mod").is_file():
        return "go"
    return None


def suggest_ignore_patterns(project_type: str | None) -> list[str]:
    """Return suggested ``.lexignore`` patterns for a given project type."""
    if project_type is None:
        return []
    return list(_IGNORE_PATTERNS.get(project_type, []))
