"""Configuration schema with Pydantic 2 models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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

    start_here_tokens: int = 800
    design_file_tokens: int = 400
    design_file_abridged_tokens: int = 100
    aindex_tokens: int = 200
    concept_file_tokens: int = 400
    convention_file_tokens: int = 500


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
            ".lexibrary/START_HERE.md",
            ".lexibrary/**/*.md",
            ".lexibrary/**/.aindex",
            "node_modules/",
            "__pycache__/",
            ".git/",
            ".venv/",
            "venv/",
            "*.lock",
            ".env",
            ".env.*",
            "*.env",
        ]
    )


class DaemonConfig(BaseModel):
    """Daemon watch configuration."""

    model_config = ConfigDict(extra="ignore")

    debounce_seconds: float = 2.0
    sweep_interval_seconds: int = 3600
    sweep_skip_if_unchanged: bool = True
    git_suppression_seconds: int = 5
    watchdog_enabled: bool = False
    log_level: str = "info"


class ASTConfig(BaseModel):
    """AST-based interface extraction configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    languages: list[str] = Field(default_factory=lambda: ["python", "typescript", "javascript"])


class ConventionConfig(BaseModel):
    """Convention system configuration."""

    model_config = ConfigDict(extra="ignore")

    lookup_display_limit: int = 5


class ConventionDeclaration(BaseModel):
    """A user-declared convention seeded from config.

    These declarations are materialized into `.lexibrary/conventions/` files
    by the build pipeline with `source: config` and `status: active`.
    """

    model_config = ConfigDict(extra="ignore")

    body: str
    scope: str = "project"
    tags: list[str] = Field(default_factory=list)


class IWHConfig(BaseModel):
    """I Was Here (IWH) configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True


class LexibraryConfig(BaseModel):
    """Top-level Lexibrary configuration."""

    model_config = ConfigDict(extra="ignore")

    scope_root: str = "."
    project_name: str = ""
    agent_environment: list[str] = Field(default_factory=list)
    conventions: ConventionConfig = Field(default_factory=ConventionConfig)
    convention_declarations: list[ConventionDeclaration] = Field(default_factory=list)
    iwh: IWHConfig = Field(default_factory=IWHConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    token_budgets: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    ast: ASTConfig = Field(default_factory=ASTConfig)
