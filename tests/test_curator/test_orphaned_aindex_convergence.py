"""Convergence test for orphaned .aindex detection (SHARED_BLOCK_C).

Asserts parity between the curator-side
``ConsistencyChecker.detect_orphaned_aindex`` and the validator-side
``find_orphaned_aindex`` (check ``orphaned_aindex``).  This test must pass
before the curator-side detector is retired in task 6.2 of the
``curator-freshness`` change.

Both detectors are compared on the set of affected ``.aindex`` paths
expressed relative to ``.lexibrary/`` (the validator already reports
``artifact`` in that form; the curator's ``target_path`` is normalised
the same way here).
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.curator.consistency import ConsistencyChecker
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.checks import find_orphaned_aindex


def _write_aindex(lexibrary_dir: Path, directory_path: str) -> Path:
    """Create an ``.aindex`` at ``.lexibrary/designs/<directory_path>/.aindex``."""
    aindex = lexibrary_dir / DESIGNS_DIR / directory_path / ".aindex"
    aindex.parent.mkdir(parents=True, exist_ok=True)
    aindex.write_text("# test\n", encoding="utf-8")
    return aindex


def _curator_findings(project_root: Path, lexibrary_dir: Path) -> set[str]:
    checker = ConsistencyChecker(project_root, lexibrary_dir)
    return {
        str(instr.target_path.relative_to(lexibrary_dir))
        for instr in checker.detect_orphaned_aindex()
    }


def _validator_findings(project_root: Path, lexibrary_dir: Path) -> set[str]:
    return {
        issue.artifact
        for issue in find_orphaned_aindex(project_root, lexibrary_dir)
    }


class TestOrphanedAindexConvergence:
    """Parity tests: curator detector vs. validator check on identical fixtures."""

    def test_single_orphan(self, tmp_path: Path) -> None:
        """A single orphaned .aindex is reported identically by both detectors."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        _write_aindex(lexibrary_dir, "src/old_module")

        curator = _curator_findings(project_root, lexibrary_dir)
        validator = _validator_findings(project_root, lexibrary_dir)

        assert curator == validator
        assert curator == {f"{DESIGNS_DIR}/src/old_module/.aindex"}

    def test_mixed_orphan_and_valid(self, tmp_path: Path) -> None:
        """Only the orphaned .aindex surfaces; both detectors agree on which."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        valid_dir = project_root / "src" / "valid"
        valid_dir.mkdir(parents=True)
        _write_aindex(lexibrary_dir, "src/valid")
        _write_aindex(lexibrary_dir, "src/removed")

        curator = _curator_findings(project_root, lexibrary_dir)
        validator = _validator_findings(project_root, lexibrary_dir)

        assert curator == validator
        assert curator == {f"{DESIGNS_DIR}/src/removed/.aindex"}

    def test_multiple_orphans_including_nested(self, tmp_path: Path) -> None:
        """Multiple orphans at various depths are reported by both detectors."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _write_aindex(lexibrary_dir, "src/deleted_a")
        _write_aindex(lexibrary_dir, "src/deleted_b")
        _write_aindex(lexibrary_dir, "src/packages/core/deleted_c")

        curator = _curator_findings(project_root, lexibrary_dir)
        validator = _validator_findings(project_root, lexibrary_dir)

        assert curator == validator
        assert curator == {
            f"{DESIGNS_DIR}/src/deleted_a/.aindex",
            f"{DESIGNS_DIR}/src/deleted_b/.aindex",
            f"{DESIGNS_DIR}/src/packages/core/deleted_c/.aindex",
        }

    def test_no_orphans(self, tmp_path: Path) -> None:
        """When every .aindex has a matching source directory, both yield no findings."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src_dir = project_root / "src" / "auth"
        src_dir.mkdir(parents=True)
        _write_aindex(lexibrary_dir, "src/auth")

        curator = _curator_findings(project_root, lexibrary_dir)
        validator = _validator_findings(project_root, lexibrary_dir)

        assert curator == validator == set()

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """Both detectors gracefully return no findings when designs/ is absent."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        curator = _curator_findings(project_root, lexibrary_dir)
        validator = _validator_findings(project_root, lexibrary_dir)

        assert curator == validator == set()
