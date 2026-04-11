"""Module-level constant fixture for the Python parser constant extractor.

Covers the four supported shapes:

- ALL_CAPS without annotation (``MAX_RETRIES = 3``)
- Type-annotated non-ALL_CAPS (``DEFAULT_TIMEOUT: float = 30.0``)
- Tuple-of-literals RHS (``SUPPORTED_EXTS = (".py", ".ts")``)
- Underscore-prefixed private constant (``_PRIVATE = "secret"``)

Also includes a nested constant and a computed RHS that must NOT be
extracted.
"""

from __future__ import annotations


def _compute() -> int:
    NESTED_VALUE = 42  # noqa: N806  # Nested ALL_CAPS is the point of the fixture.
    return NESTED_VALUE


MAX_RETRIES = 3
DEFAULT_TIMEOUT: float = 30.0
SUPPORTED_EXTS = (".py", ".ts")
_PRIVATE = "secret"
COMPUTED = _compute()  # Non-literal RHS — must not be extracted.
