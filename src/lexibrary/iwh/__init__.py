"""IWH (I Was Here) module -- ephemeral inter-agent signal files."""

from __future__ import annotations

from lexibrary.iwh.gitignore import ensure_iwh_gitignored
from lexibrary.iwh.model import IWHFile, IWHScope
from lexibrary.iwh.parser import parse_iwh
from lexibrary.iwh.reader import consume_iwh, read_iwh
from lexibrary.iwh.serializer import serialize_iwh
from lexibrary.iwh.writer import write_iwh

__all__ = [
    "IWHFile",
    "IWHScope",
    "consume_iwh",
    "ensure_iwh_gitignored",
    "parse_iwh",
    "read_iwh",
    "serialize_iwh",
    "write_iwh",
]
