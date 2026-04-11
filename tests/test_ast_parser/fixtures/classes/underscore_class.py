"""Underscore class fixture (known limitation: no class edge emitted).

``_Config`` does not match the PascalCase regex because the leading
underscore fails ``^[A-Z]``, so ``_Config()`` is silently ignored by the
parser. This is documented as a known limitation in the plan and exists
here to pin the behavior.
"""


class _Config:
    pass


def main() -> None:
    _Config()
