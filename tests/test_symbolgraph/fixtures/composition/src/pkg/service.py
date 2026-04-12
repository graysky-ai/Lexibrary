"""A class with composition edges to Database (class body) and LRUCache (init).

Also has ExternalClient which is an unresolvable external type.
"""

from __future__ import annotations

from pkg.cache import LRUCache
from pkg.database import Database


class Service:
    db: Database
    name: str

    def __init__(self) -> None:
        self.cache: LRUCache = LRUCache()
        self.client: ExternalClient = None  # type: ignore[assignment]  # noqa: F821
