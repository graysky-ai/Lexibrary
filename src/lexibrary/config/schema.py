"""Configuration schema with Pydantic 2 models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lexibrary.curator.config import CuratorConfig

# Error text emitted when a legacy ``scope_root:`` key is present in a loaded
# config. Matches the multi-root change's Block D snippet exactly so callers can
# substring-assert on it.
_LEGACY_SCOPE_ROOT_ERROR = (
    "Unknown config key 'scope_root'. Multi-root support replaced this with\n"
    "'scope_roots' (list of mappings). Migrate your config to:\n"
    "  scope_roots:\n"
    "    - path: <your-old-scope-root>"
)


class CrawlConfig(BaseModel):
    """Crawl behaviour configuration."""

    model_config = ConfigDict(extra="ignore")

    max_file_size_kb: int = 512
    binary_extensions: list[str] = Field(
        default_factory=lambda: [
            # Images
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".svg",
            ".webp",
            # Audio/video
            ".mp3",
            ".mp4",
            ".wav",
            ".ogg",
            ".webm",
            # Fonts
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            # Archives
            ".zip",
            ".tar",
            ".gz",
            ".bz2",
            ".7z",
            ".rar",
            # Documents
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            # Executables / compiled
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".pyc",
            ".pyo",
            ".class",
            ".o",
            ".obj",
            # Database
            ".sqlite",
            ".db",
        ]
    )


class TokenizerConfig(BaseModel):
    """Tokenizer configuration."""

    model_config = ConfigDict(extra="ignore")

    backend: str = "tiktoken"
    model: str = "cl100k_base"
    max_tokens_per_chunk: int = 4000


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    model_config = ConfigDict(extra="ignore")

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    api_key_source: str = "env"
    max_retries: int = 3
    timeout: int = 60


class TokenBudgetConfig(BaseModel):
    """Per-artifact token budget configuration."""

    model_config = ConfigDict(extra="ignore")

    design_file_tokens: int = 400
    design_file_abridged_tokens: int = 100
    aindex_tokens: int = 200
    concept_file_tokens: int = 400
    convention_file_tokens: int = 500
    lookup_total_tokens: int = 1200
    playbook_tokens: int = 500
    summarize_max_tokens: int = 200
    archivist_max_tokens: int = 5000


class MappingConfig(BaseModel):
    """Mapping strategy configuration (stub for Phase 1)."""

    model_config = ConfigDict(extra="ignore")

    strategies: list[dict[str, Any]] = Field(default_factory=list)


class IgnoreConfig(BaseModel):
    """Ignore pattern configuration."""

    model_config = ConfigDict(extra="ignore")

    use_gitignore: bool = True
    additional_patterns: list[str] = Field(
        default_factory=lambda: [
            # Lexibrary internals
            ".lexibrary/",
            # Dev/build directories
            "node_modules/",
            "__pycache__/",
            ".git/",
            ".venv/",
            "venv/",
            # Lock files
            "*.lock",
            # Environment files
            ".env",
            ".env.*",
            "*.env",
            # Private keys & certificates
            "*.pem",
            "*.key",
            "*.p12",
            "*.pfx",
            "*.jks",
            "*.keystore",
            "id_rsa",
            "id_dsa",
            "id_ed25519",
            "id_ecdsa",
            # Cloud provider credentials
            ".aws/",
            ".azure/",
            # Package manager credentials
            ".npmrc",
            ".pypirc",
            # Docker registry auth
            ".dockercfg",
            ".docker/config.json",
            # Terraform state & vars
            "*.tfvars",
            "*.tfstate",
            "*.tfstate.backup",
            # Vault / secrets
            ".vault-password*",
            # Auth & credential files
            "credentials.json",
            ".git-credentials",
            ".htpasswd",
            ".netrc",
            # Database files
            "*.sqlite",
            "*.sqlite3",
        ]
    )


class SweepConfig(BaseModel):
    """Sweep configuration for periodic re-indexing."""

    model_config = ConfigDict(extra="ignore")

    sweep_interval_seconds: int = 3600
    sweep_skip_if_unchanged: bool = True
    log_level: str = "info"


class ASTConfig(BaseModel):
    """AST-based interface extraction configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    languages: list[str] = Field(default_factory=lambda: ["python", "typescript", "javascript"])


class SymbolGraphConfig(BaseModel):
    """Symbol-level code graph configuration (``.lexibrary/symbols.db``).

    Controls whether the symbol graph is built and how the archivist enriches
    design-file prompts with enum/constant and call-path context drawn from
    that graph.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    """Controls whether ``.lexibrary/symbols.db`` is created and refreshed by
    ``lexictl update``."""

    include_enums: bool = True
    """When True, feed extracted enums and constants into the design-file
    prompt so the archivist can write prose that names them explicitly."""

    include_call_paths: bool = False
    """Opt-in: feed call-path summaries (caller ← this ← callees) into the
    design-file prompt. Increases prompt size by roughly
    ``call_path_depth × 50`` tokens per file."""

    call_path_depth: int = 2
    """How many hops to include in each direction when ``include_call_paths``
    is on."""

    max_enum_items: int = 20
    """Maximum number of enums/constants to include in a single prompt. Files
    with more entries are truncated with a trailing ``... N more`` marker."""

    max_call_path_items: int = 10
    """Maximum number of call-path entries to include in a single prompt.
    Files with more functions/methods are truncated."""

    include_data_flows: bool = False
    """Opt-in (Phase 7): when True and the file contains functions whose
    parameters drive branching (deterministic AST signal), the archivist
    includes data-flow notes in the design-file prompt.  Files without
    branching parameters never trigger the LLM call regardless of this flag."""


class ConventionConfig(BaseModel):
    """Convention system configuration."""

    model_config = ConfigDict(extra="ignore")

    lookup_display_limit: int = 5
    deprecation_confirm: Literal["human", "maintainer"] = "human"
    curator_deprecation_confirm: bool = False


class ConventionDeclaration(BaseModel):
    """A user-declared convention seeded from config.

    These declarations are materialized into `.lexibrary/conventions/` files
    by the build pipeline with `source: config` and `status: active`.
    """

    model_config = ConfigDict(extra="ignore")

    body: str
    scope: str = "project"
    tags: list[str] = Field(default_factory=list)


class ConceptConfig(BaseModel):
    """Concept system configuration."""

    model_config = ConfigDict(extra="ignore")

    deprecation_confirm: Literal["human", "maintainer"] = "human"
    curator_deprecation_confirm: bool = False
    lookup_display_limit: int = 10
    orphan_verify_ttl_days: int = Field(
        default=90,
        ge=0,
        description=(
            "Number of days after a concept's last_verified date during which "
            "check_orphan_concepts will skip emitting an orphan-concept issue. "
            "Set to 0 to disable TTL honouring and always emit."
        ),
    )


class IWHConfig(BaseModel):
    """I Was Here (IWH) configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    ttl_hours: int = 72


class DeprecationConfig(BaseModel):
    """Deprecation lifecycle configuration."""

    model_config = ConfigDict(extra="ignore")

    ttl_commits: int = 50
    comment_warning_threshold: int = 10


class ValidatorConfig(BaseModel):
    """Validator fixer kill-switch configuration.

    Gates opt-in behaviours for the validator fixers introduced by the
    curator-4 escalation work. Each flag controls whether the matching
    ``fix_*`` fixer in :mod:`lexibrary.validator.fixes` actually mutates
    the repository; when a flag is ``False``, the fixer returns a
    ``FixResult`` with ``fixed=False`` and an explanatory message instead.
    """

    model_config = ConfigDict(extra="ignore")

    fix_lookup_token_budget_condense: bool = Field(
        default=False,
        description=(
            "When True, ``fix_lookup_token_budget_exceeded`` invokes "
            "``curator.budget.condense_file`` on over-budget design bodies. "
            "Defaults to False because condensation mutates content and "
            "consumes LLM budget."
        ),
    )
    fix_orphaned_iwh_signals_delete: bool = Field(
        default=True,
        description=(
            "When True, ``fix_orphaned_iwh_signals`` deletes expired IWH "
            "signal files past their TTL. IWH signals are intentionally "
            "ephemeral, so this defaults to True."
        ),
    )


class TopologyConfig(BaseModel):
    """Topology generation configuration."""

    model_config = ConfigDict(extra="ignore")

    detail_dirs: list[str] = Field(default_factory=list)


class PlaybookConfig(BaseModel):
    """Playbook system configuration."""

    model_config = ConfigDict(extra="ignore")

    lookup_display_limit: int = 5
    staleness_commits: int = 100
    staleness_days: int = 180


class StackConfig(BaseModel):
    """Stack post staleness lifecycle configuration."""

    model_config = ConfigDict(extra="ignore")

    staleness_confirm: Literal["human", "maintainer"] = "human"
    staleness_ttl_commits: int = 200
    staleness_ttl_short_commits: int = 100
    lookup_display_limit: int = 3


class ScopeRoot(BaseModel):
    """A single declared scope root.

    Wraps a path string so the on-disk schema can grow per-root options (``name``,
    ``origin``, future overrides) without another migration. ``origin`` is
    reserved for a later multi-repo / multi-drive phase; today it is always
    ``"local"``.
    """

    model_config = ConfigDict(extra="ignore")

    path: str
    name: str | None = None
    origin: Literal["local"] = "local"


@dataclass(frozen=True)
class ResolvedRoots:
    """Return shape for :meth:`LexibraryConfig.resolved_scope_roots`.

    ``resolved`` is the list of absolute :class:`Path` objects that exist on disk
    and passed the nesting/duplicate/traversal guards. ``missing`` holds the
    original :class:`ScopeRoot` entries whose declared path does not exist on
    disk (they are excluded from ``resolved`` but preserved here so a CLI layer
    can warn about them).
    """

    resolved: list[Path]
    missing: list[ScopeRoot]


class LexibraryConfig(BaseModel):
    """Top-level Lexibrary configuration."""

    model_config = ConfigDict(extra="ignore")

    scope_roots: list[ScopeRoot] = Field(default_factory=lambda: [ScopeRoot(path=".")])
    project_name: str = ""
    agent_environment: list[str] = Field(default_factory=list)
    concepts: ConceptConfig = Field(default_factory=ConceptConfig)
    conventions: ConventionConfig = Field(default_factory=ConventionConfig)
    convention_declarations: list[ConventionDeclaration] = Field(default_factory=list)
    playbooks: PlaybookConfig = Field(default_factory=PlaybookConfig)
    topology: TopologyConfig = Field(default_factory=TopologyConfig)
    iwh: IWHConfig = Field(default_factory=IWHConfig)
    deprecation: DeprecationConfig = Field(default_factory=DeprecationConfig)
    validator: ValidatorConfig = Field(default_factory=ValidatorConfig)
    stack: StackConfig = Field(default_factory=StackConfig)
    symbols: SymbolGraphConfig = Field(default_factory=SymbolGraphConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    token_budgets: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    sweep: SweepConfig = Field(default_factory=SweepConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    ast: ASTConfig = Field(default_factory=ASTConfig)
    curator: CuratorConfig = Field(default_factory=CuratorConfig)

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_scope_root(cls, data: Any) -> Any:
        """Raise an actionable error when a legacy ``scope_root:`` key is present.

        The top-level model otherwise silently drops unknown keys via
        ``extra="ignore"``; this key is a known-renamed field from the
        single-root era and deserves a loud pointer to the new shape instead
        of a silent no-op.
        """

        if isinstance(data, dict) and "scope_root" in data:
            raise ValueError(_LEGACY_SCOPE_ROOT_ERROR)
        return data

    def resolved_scope_roots(self, project_root: Path) -> ResolvedRoots:
        """Resolve, validate, and existence-filter the declared scope roots.

        Steps, in order:

        1. Resolve each declared path relative to ``project_root`` and call
           ``.resolve()``.
        2. **Path-traversal guard** — each resolved root must be relative to
           ``project_root``. Violations raise a :class:`ValueError` naming the
           offending entry.
        3. **Nested-roots guard** — for each pair of declared roots, reject if
           either resolves to an ancestor of the other (or they are equal).
           Both original path strings appear in the error.
        4. **Duplicate-entry guard** — reject duplicate declared path strings
           (after whitespace normalisation).
        5. **Existence filter** — non-existent roots are dropped from the
           ``resolved`` list and preserved in ``missing``.

        The Pydantic model stays decoupled from ``_output.py`` — callers emit
        ``warn()`` for missing entries themselves.
        """

        project_root_abs = project_root.resolve()

        # Duplicate-entry guard. Run on the declared path strings so the
        # error message names what the user actually typed.
        seen: set[str] = set()
        for sr in self.scope_roots:
            key = sr.path.strip()
            if key in seen:
                raise ValueError(
                    f"Duplicate scope_roots entry: {sr.path!r}. "
                    f"Each declared path must appear exactly once."
                )
            seen.add(key)

        # Resolve + path-traversal guard.
        resolved_pairs: list[tuple[ScopeRoot, Path]] = []
        for sr in self.scope_roots:
            candidate = (project_root_abs / sr.path).resolve()
            if not candidate.is_relative_to(project_root_abs):
                raise ValueError(
                    f"scope_roots entry {sr.path!r} resolves to {candidate} "
                    f"which is outside the project root {project_root_abs}. "
                    f"Path traversal is not allowed."
                )
            resolved_pairs.append((sr, candidate))

        # Nested-roots guard. Compare every pair of resolved roots and reject
        # when one is relative to (or equal to) another.
        for i, (sr_a, path_a) in enumerate(resolved_pairs):
            for sr_b, path_b in resolved_pairs[i + 1 :]:
                if (
                    path_a == path_b
                    or path_a.is_relative_to(path_b)
                    or path_b.is_relative_to(path_a)
                ):
                    raise ValueError(
                        f"scope_roots entries {sr_a.path!r} and {sr_b.path!r} "
                        f"are nested or identical. Each declared root must be "
                        f"an independent subtree."
                    )

        # Existence filter — non-existent roots move to ``missing``.
        resolved: list[Path] = []
        missing: list[ScopeRoot] = []
        for sr, path in resolved_pairs:
            if path.exists():
                resolved.append(path)
            else:
                missing.append(sr)

        return ResolvedRoots(resolved=resolved, missing=missing)

    def owning_root(self, path: Path, project_root: Path) -> ScopeRoot | None:
        """Return the declared :class:`ScopeRoot` that owns ``path``, or ``None``.

        Thin wrapper around :func:`lexibrary.config.scope.find_owning_root` so
        call sites that have a :class:`LexibraryConfig` in hand do not have to
        import the helper themselves.
        """

        # Local import avoids a circular dependency at module import time —
        # ``scope.py`` imports :class:`ScopeRoot` from this module.
        from lexibrary.config.scope import find_owning_root

        return find_owning_root(path, self.scope_roots, project_root)
