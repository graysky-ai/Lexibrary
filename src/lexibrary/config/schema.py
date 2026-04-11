"""Configuration schema with Pydantic 2 models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lexibrary.curator.config import CuratorConfig


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

    Phase 1 ships a single ``enabled`` toggle. Phase 5 will extend this model
    with extraction knobs (see the comment block below).
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    # Phase 5 will add the following real fields (listed here as a
    # forward-compatibility marker, not as live config):
    #   include_enums: bool = True          — extract enum members as symbols
    #   include_call_paths: bool = False    — record transitive call paths
    #   call_path_depth: int = 2            — max hops when include_call_paths is on
    #   include_data_flows: bool = False    — record data-flow edges


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


class LexibraryConfig(BaseModel):
    """Top-level Lexibrary configuration."""

    model_config = ConfigDict(extra="ignore")

    scope_root: str = "."
    project_name: str = ""
    agent_environment: list[str] = Field(default_factory=list)
    concepts: ConceptConfig = Field(default_factory=ConceptConfig)
    conventions: ConventionConfig = Field(default_factory=ConventionConfig)
    convention_declarations: list[ConventionDeclaration] = Field(default_factory=list)
    playbooks: PlaybookConfig = Field(default_factory=PlaybookConfig)
    topology: TopologyConfig = Field(default_factory=TopologyConfig)
    iwh: IWHConfig = Field(default_factory=IWHConfig)
    deprecation: DeprecationConfig = Field(default_factory=DeprecationConfig)
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
