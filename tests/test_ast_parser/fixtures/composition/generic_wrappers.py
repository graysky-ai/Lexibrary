"""Fixture: composition through generic wrapper types."""

from __future__ import annotations


class Handler:
    pass


class Middleware:
    pass


class Plugin:
    pass


class Router:
    pass


class Pipeline:
    handlers: list[Handler]
    middleware: Middleware | None
    plugins: dict[str, Plugin]
    router: Router | None
    names: list[str]
    items: dict[str, int]
    single_letter: list[T]  # type: ignore  # noqa: F821
