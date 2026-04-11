"""Aliased instantiation fixture (known limitation: no class edge emitted).

Binding ``MyClass`` to ``cls`` and then calling ``cls()`` no longer
matches the PascalCase heuristic (``cls`` is lowercase), so no class edge
is emitted. This is documented as a known limitation in the plan.
"""


class MyClass:
    pass


def main() -> None:
    cls = MyClass
    cls()
