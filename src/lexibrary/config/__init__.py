"""Configuration system for Lexibrary."""

from __future__ import annotations

from lexibrary.config.defaults import DEFAULT_PROJECT_CONFIG_TEMPLATE
from lexibrary.config.loader import find_config_file, load_config
from lexibrary.config.schema import (
    ConventionConfig,
    ConventionDeclaration,
    DaemonConfig,
    IgnoreConfig,
    IWHConfig,
    LexibraryConfig,
    LLMConfig,
    MappingConfig,
    TokenBudgetConfig,
    TokenizerConfig,
)

__all__ = [
    "DEFAULT_PROJECT_CONFIG_TEMPLATE",
    "find_config_file",
    "load_config",
    "ConventionConfig",
    "ConventionDeclaration",
    "DaemonConfig",
    "IgnoreConfig",
    "IWHConfig",
    "LexibraryConfig",
    "LLMConfig",
    "MappingConfig",
    "TokenBudgetConfig",
    "TokenizerConfig",
]
