"""Fixture: composition via __init__ self.attr: Type annotations."""

from __future__ import annotations


class Engine:
    pass


class Renderer:
    pass


class Application:
    def __init__(self, name: str) -> None:
        self.engine: Engine = Engine()
        self.renderer: Renderer = Renderer()
        self.name: str = name
        self.count: int = 0
