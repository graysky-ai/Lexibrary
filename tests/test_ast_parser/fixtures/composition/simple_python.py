"""Fixture: simple class-body composition annotations."""

from __future__ import annotations


class Database:
    pass


class Cache:
    pass


class Service:
    db: Database
    cache: Cache
    name: str
    count: int
