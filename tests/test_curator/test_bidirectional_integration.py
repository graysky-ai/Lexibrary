"""End-to-end integration test for the bidirectional_deps curator path.

Phase 1b of the ``curator-freshness`` OpenSpec change wired the narrow
``fix_bidirectional_deps`` action key through three layers:

* ``CHECK_TO_ACTION_KEY`` (coordinator) maps
  ``"bidirectional_deps"`` to ``"fix_bidirectional_deps"``.
* ``FIXERS`` (validator) registers
  :func:`lexibrary.validator.fixes.fix_bidirectional_deps` under the
  same check name.
* ``RISK_TAXONOMY`` (curator) rates the action as ``low`` so it
  dispatches under ``full`` autonomy.

This test runs the full :meth:`Coordinator.run` pipeline against a
fixture that produces a ``bidirectional_deps`` validation issue and
asserts:

1. The resulting :class:`CuratorReport` contains a dispatched entry
   with ``action_key="fix_bidirectional_deps"`` and ``outcome="fixed"``.
2. No dispatched entry carries ``outcome="no_fixer"`` (which would
   indicate the fixer was not routed through the bridge).

The fixture is deliberately minimal — proper DS-NNN ids, valid
frontmatter, computed source hashes, and dependencies that reference
real design files — so that *only* the bidirectional check fires and
the ``no_fixer_registered`` assertion is tight.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.linkgraph.schema import ensure_schema

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "bidirectional_integration"
    project.mkdir()
    lex = project / ".lexibrary"
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")
    return project


def _write_source(project: Path, rel: str, body: str) -> Path:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_design(
    project: Path,
    source_rel: str,
    *,
    source_body: str,
    ds_id: str,
    dependencies: list[str] | None = None,
    dependents: list[str] | None = None,
    dependents_complete: bool = True,
) -> Path:
    """Write a design file whose ``source_hash`` matches the given source body.

    Keeps ``updated_by="archivist"`` so ``check_stale_agent_design`` does
    not fire (that check only triggers on agent/maintainer authored
    files).  The ``ds_id`` MUST be a ``DS-NNN`` string (3+ digits) to
    pass ``check_design_frontmatter``.
    """
    design_path = project / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=ds_id,
            updated_by="archivist",
            status="active",
        ),
        summary=f"Summary of {source_rel}",
        interface_contract="def foo(): ...",
        dependencies=dependencies or [],
        dependents=dependents or [],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=_sha256(source_body),
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="test",
            dependents_complete=dependents_complete,
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _write_index_db(
    lexibrary_dir: Path,
    artifacts: list[tuple[int, str, str]],
    links: list[tuple[int, int, str]],
) -> None:
    """Create a minimal ``index.db`` so ``check_bidirectional_deps`` can read it.

    Local inline copy of ``tests/_index_fixtures._create_index_with_links``
    to keep the integration test self-contained for the curator suite.
    """
    db_path = lexibrary_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    for art_id, art_path, kind in artifacts:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) VALUES (?, ?, ?, ?, ?)",
            (art_id, art_path, kind, f"Artifact {art_id}", None),
        )
    for src_id, tgt_id, link_type in links:
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (?, ?, ?)",
            (src_id, tgt_id, link_type),
        )
    conn.commit()
    conn.close()


def _run(project: Path, *, autonomy: str = "full") -> object:
    """Run the coordinator under ``full`` autonomy so the fixer dispatches."""
    config = LexibraryConfig.model_validate({"curator": {"autonomy": autonomy}})
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestBidirectionalDepsCoordinatorRoundtrip:
    """The full coordinator pipeline fixes a ``bidirectional_deps`` issue."""

    def test_coordinator_dispatches_fix_bidirectional_deps(self, tmp_path: Path) -> None:
        project = _setup_integration_project(tmp_path)

        # Seed a minimal Python import graph so ``extract_dependencies``
        # inside ``reconcile_deps_only`` resolves imports to project-relative
        # paths.  ``src/api/auth.py`` imports ``src/utils/crypto.py``; no
        # other reverse edges exist.
        pkg_init = ""  # empty __init__.py
        crypto_body = "def encrypt(): pass\n"
        auth_body = "from src.utils.crypto import encrypt\n"
        login_body = "from src.api.auth import encrypt\n"
        _write_source(project, "src/__init__.py", pkg_init)
        _write_source(project, "src/api/__init__.py", pkg_init)
        _write_source(project, "src/utils/__init__.py", pkg_init)
        _write_source(project, "src/ui/__init__.py", pkg_init)
        _write_source(project, "src/utils/crypto.py", crypto_body)
        _write_source(project, "src/api/auth.py", auth_body)
        _write_source(project, "src/ui/login.py", login_body)

        # Design for src/api/auth.py -- the victim of the bidirectional
        # drift.  Dependencies is EMPTY (direction 1b drift: graph has
        # an ast_import edge to src/utils/crypto.py that the design
        # does not list).  Dependents is EMPTY (direction 2b drift:
        # graph shows src/ui/login.py imports this file).  Setting
        # ``dependents_complete=True`` unlocks the reverse direction in
        # check_bidirectional_deps.
        _write_design(
            project,
            "src/api/auth.py",
            source_body=auth_body,
            ds_id="DS-001",
            dependencies=[],
            dependents=[],
            dependents_complete=True,
        )
        # Companion design files MUST exist so the forward dep that
        # reconcile_deps_only writes back
        # (``src/utils/crypto.py``) and the dependent edge it writes
        # back (``src/ui/login.py``) both resolve in the subsequent
        # ``design_deps_existence`` check.
        _write_design(
            project,
            "src/utils/crypto.py",
            source_body=crypto_body,
            ds_id="DS-002",
            dependencies=[],
            dependents=[],
            # dependents_complete=False so the reverse-direction diff
            # on this design is skipped (no bidirectional_deps issue
            # emitted against crypto.py).
            dependents_complete=False,
        )
        _write_design(
            project,
            "src/ui/login.py",
            source_body=login_body,
            ds_id="DS-003",
            dependencies=[],
            dependents=[],
            dependents_complete=False,
        )

        # Build index.db with the ast_import edges.  Forward edges from
        # ``auth -> crypto`` and ``login -> auth`` produce:
        #   * dependencies drift on auth.py (auth lists none; graph
        #     shows auth imports crypto).
        #   * dependents  drift on auth.py (auth lists none; graph
        #     shows login imports auth).
        _write_index_db(
            project / ".lexibrary",
            artifacts=[
                (1, "src/api/auth.py", "source"),
                (2, "src/utils/crypto.py", "source"),
                (3, "src/ui/login.py", "source"),
            ],
            links=[
                # auth imports crypto  (forward edge, direction 1b on auth)
                (1, 2, "ast_import"),
                # login imports auth   (reverse edge, direction 2b on auth)
                (3, 1, "ast_import"),
            ],
        )

        report = _run(project)

        # The pipeline returns a CuratorReport with dispatched_details.
        assert hasattr(report, "dispatched_details")
        dispatched: list[dict[str, object]] = list(getattr(report, "dispatched_details", []))

        # No dispatched entry should be an un-routed validation issue
        # (``outcome="no_fixer"``).  A ``no_fixer`` here would mean the
        # validation bridge failed to locate a fixer for one of the
        # checks that fired -- the fixture is tuned so only
        # ``bidirectional_deps`` (and possibly other fixable checks)
        # produce issues.
        no_fixer_entries = [entry for entry in dispatched if entry.get("outcome") == "no_fixer"]
        assert not no_fixer_entries, (
            "Found dispatched entries with outcome='no_fixer'; "
            "fixer registration gaps. Entries: "
            f"{no_fixer_entries}"
        )

        # At least one dispatched entry must be the bidirectional fixer
        # with ``outcome="fixed"``.
        bidirectional_fixed = [
            entry
            for entry in dispatched
            if entry.get("action_key") == "fix_bidirectional_deps"
            and entry.get("outcome") == "fixed"
        ]
        assert bidirectional_fixed, (
            "Expected at least one dispatched entry with "
            "action_key='fix_bidirectional_deps' and outcome='fixed'; "
            f"dispatched_details={dispatched}"
        )
