"""Pin the symbols: block in the bundled default_config.yaml template.

This test ensures the shipped YAML template stays aligned with the schema
defined in ``lexibrary.config.schema.SymbolGraphConfig``. Future drift
(renaming the field, dropping the default, etc.) will be caught here rather
than at runtime when a scaffolded project tries to load the template.
"""

from __future__ import annotations

import yaml

from lexibrary.config.schema import LexibraryConfig
from lexibrary.templates import read_template


def test_default_config_has_symbols_block() -> None:
    """The default_config.yaml template exposes a symbols block with enabled=True."""
    raw = read_template("config/default_config.yaml")
    data = yaml.safe_load(raw)
    config = LexibraryConfig.model_validate(data)
    assert config.symbols.enabled is True
