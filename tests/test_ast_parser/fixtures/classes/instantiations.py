"""Instantiation fixture.

``Builder()`` matches the PascalCase heuristic and should emit a
``ClassEdgeSite``; ``process_data()`` is lowercase and should not.
"""


def build_thing() -> None:
    Builder()
    process_data()
