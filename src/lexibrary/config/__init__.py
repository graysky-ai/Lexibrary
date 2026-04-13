"""Configuration system for Lexibrary."""

from __future__ import annotations

from lexibrary.config.loader import find_config_file, load_config
from lexibrary.config.schema import (
    ConceptConfig,
    ConventionConfig,
    ConventionDeclaration,
    DeprecationConfig,
    IgnoreConfig,
    IWHConfig,
    LexibraryConfig,
    LLMConfig,
    MappingConfig,
    ResolvedRoots,
    ScopeRoot,
    StackConfig,
    SweepConfig,
    SymbolGraphConfig,
    TokenBudgetConfig,
    TokenizerConfig,
    TopologyConfig,
)
from lexibrary.config.scope import find_owning_root

__all__ = [
    "find_config_file",
    "find_owning_root",
    "load_config",
    "ConceptConfig",
    "ConventionConfig",
    "ConventionDeclaration",
    "DeprecationConfig",
    "IgnoreConfig",
    "IWHConfig",
    "LexibraryConfig",
    "LLMConfig",
    "MappingConfig",
    "ResolvedRoots",
    "ScopeRoot",
    "StackConfig",
    "SweepConfig",
    "SymbolGraphConfig",
    "TokenBudgetConfig",
    "TokenizerConfig",
    "TopologyConfig",
]
