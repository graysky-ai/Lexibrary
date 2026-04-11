"""Living contract for the curator risk taxonomy.

This module hosts the single self-check test that every ``function_ref`` in
``RISK_TAXONOMY`` resolves to a real importable callable.

History
-------

The ``curator-fix`` OpenSpec plan progressively wired up the missing
handlers across groups 5–9.  The ``curator-fix-2`` follow-up plan (group 1)
then removed the 6 orphan/dead stub entries whose ``function_ref`` values
pointed at modules or functions that were never implemented, so the test
now passes cleanly without ``xfail``.
"""

from __future__ import annotations

import importlib

from lexibrary.curator.risk_taxonomy import RISK_TAXONOMY


def test_taxonomy_function_refs_resolve() -> None:
    """Every ``function_ref`` in ``RISK_TAXONOMY`` must resolve to a callable.

    The ``function_ref`` values use dotted paths rooted at ``lexibrary`` but
    with the leading package name omitted (e.g. ``curator.staleness.foo``).
    We split on the last ``.`` to separate the module path from the attribute
    name, import the module via ``lexibrary.<module>``, then ``getattr`` the
    attribute and assert the result is callable.

    Collects every failing action key so the assertion message lists the
    complete to-do list rather than stopping at the first unresolved
    reference.
    """
    failures: list[str] = []

    for action_key, action_risk in RISK_TAXONOMY.items():
        function_ref = action_risk.function_ref
        module_path, _, func_name = function_ref.rpartition(".")
        if not module_path or not func_name:
            failures.append(f"{action_key}: malformed function_ref {function_ref!r}")
            continue

        full_module = f"lexibrary.{module_path}"
        try:
            module = importlib.import_module(full_module)
        except Exception as exc:  # pragma: no cover - failure path
            failures.append(f"{action_key}: cannot import {full_module!r} ({exc!r})")
            continue

        attribute = getattr(module, func_name, None)
        if attribute is None:
            failures.append(f"{action_key}: {full_module!r} has no attribute {func_name!r}")
            continue

        if not callable(attribute):
            failures.append(
                f"{action_key}: {function_ref!r} resolved but is not "
                f"callable (got {type(attribute).__name__})"
            )

    assert not failures, "Unresolved RISK_TAXONOMY function_refs:\n  - " + "\n  - ".join(failures)
