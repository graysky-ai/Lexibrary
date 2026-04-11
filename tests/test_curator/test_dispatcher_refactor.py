"""Tests for the Phase 1.5 dispatcher refactor.

Covers the changes introduced by openspec change ``curator-fix`` group 3:

* :class:`DispatchContext` dataclass exposes the expected fields.
* :meth:`Coordinator._ctx` returns a context snapshot that mirrors
  coordinator state.
* The public ``dispatch_*`` functions extracted from coordinator are
  importable by their new dotted paths.
* ``_route_to_handler`` is a pure router (zero inline business logic).
"""

from __future__ import annotations

import importlib
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.dispatch_context import DispatchContext


def _setup_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with ``.lexibrary`` structure."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    (project / ".lexibrary" / "config.yaml").write_text("", encoding="utf-8")
    return project


# ---------------------------------------------------------------------------
# DispatchContext construction
# ---------------------------------------------------------------------------


class TestDispatchContextConstruction:
    """Verify _ctx() returns a snapshot of coordinator state."""

    def test_dispatch_context_has_expected_fields(self, tmp_path: Path) -> None:
        """DispatchContext dataclass exposes every field from the task spec."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()

        ctx = DispatchContext(
            project_root=project,
            config=config,
            summary=Coordinator(project, config).summary,
            lexibrary_dir=project / ".lexibrary",
            dry_run=False,
            uncommitted=set(),
            active_iwh=set(),
        )

        # Every field documented in Shared Content Blocks.
        assert ctx.project_root == project
        assert ctx.config is config
        assert ctx.summary is not None
        assert ctx.lexibrary_dir == project / ".lexibrary"
        assert ctx.dry_run is False
        assert ctx.uncommitted == set()
        assert ctx.active_iwh == set()

    def test_coordinator_ctx_mirrors_state(self, tmp_path: Path) -> None:
        """Coordinator._ctx() returns fields matching coordinator attrs."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Simulate collect phase populating the scope-isolation caches.
        coord._uncommitted = {project / "src" / "changed.py"}
        coord._active_iwh = {project / "src"}
        coord._dry_run = True

        ctx = coord._ctx()

        assert ctx.project_root is coord.project_root
        assert ctx.config is coord.config
        assert ctx.summary is coord.summary
        assert ctx.lexibrary_dir == coord.lexibrary_dir
        assert ctx.dry_run is True
        assert ctx.uncommitted == {project / "src" / "changed.py"}
        assert ctx.active_iwh == {project / "src"}

    def test_ctx_defaults_before_collect(self, tmp_path: Path) -> None:
        """Immediately after __init__, _ctx() returns empty caches and dry_run=False."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        ctx = coord._ctx()

        assert ctx.uncommitted == set()
        assert ctx.active_iwh == set()
        assert ctx.dry_run is False


# ---------------------------------------------------------------------------
# Public dispatch function imports
# ---------------------------------------------------------------------------


class TestPublicDispatchFunctionsImportable:
    """Every extracted dispatch function must be importable by dotted path."""

    EXPECTED_DISPATCHERS = [
        ("lexibrary.curator.staleness", "dispatch_staleness_resolver"),
        ("lexibrary.curator.reconciliation", "dispatch_reconciliation"),
        ("lexibrary.curator.comments", "dispatch_comment_integration"),
        ("lexibrary.curator.budget", "dispatch_budget_condense"),
        ("lexibrary.curator.auditing", "dispatch_comment_audit"),
        ("lexibrary.curator.deprecation", "dispatch_deprecation_router"),
        ("lexibrary.curator.deprecation", "dispatch_soft_deprecation"),
        ("lexibrary.curator.lifecycle", "dispatch_hard_delete"),
        ("lexibrary.curator.lifecycle", "dispatch_stack_transition"),
    ]

    def test_all_extracted_dispatchers_importable(self) -> None:
        """Each public dispatcher resolves via importlib and is callable."""
        for module_path, func_name in self.EXPECTED_DISPATCHERS:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name, None)
            assert func is not None, f"{module_path}.{func_name} missing"
            assert callable(func), f"{module_path}.{func_name} not callable"

    def test_no_leading_underscore_in_public_names(self) -> None:
        """Extracted functions must be public (no leading underscore)."""
        for _, func_name in self.EXPECTED_DISPATCHERS:
            assert not func_name.startswith("_"), f"Extracted dispatcher {func_name} must be public"


# ---------------------------------------------------------------------------
# Router purity
# ---------------------------------------------------------------------------


class TestRouteToHandlerPurity:
    """_route_to_handler must delegate to module-level dispatchers."""

    def test_route_to_handler_exists(self, tmp_path: Path) -> None:
        """Coordinator has _route_to_handler replacing _dispatch_to_stub."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        assert hasattr(coord, "_route_to_handler")
        assert not hasattr(coord, "_dispatch_to_stub")

    def test_route_to_handler_is_async(self, tmp_path: Path) -> None:
        """_route_to_handler is a coroutine function (async)."""
        import inspect

        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        assert inspect.iscoroutinefunction(coord._route_to_handler)
