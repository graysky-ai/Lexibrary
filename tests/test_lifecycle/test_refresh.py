"""Tests for refresh helpers in ``lexibrary.lifecycle.refresh``.

Covers per-helper behaviour plus the cross-cutting SHARED_BLOCK_A contract
(no ``lexibrary._output`` imports).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from lexibrary.conventions.parser import parse_convention_file
from lexibrary.lifecycle.refresh import (
    refresh_convention_stale,
    refresh_orphan_concept,
    refresh_playbook_staleness,
    refresh_stale_concept,
)
from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.wiki.parser import parse_concept_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_concept_id_counter = 0


def _next_concept_id() -> str:
    global _concept_id_counter
    _concept_id_counter += 1
    return f"CN-{_concept_id_counter:03d}"


def _write_concept(
    concepts_dir: Path,
    *,
    slug: str = "test-concept",
    title: str = "Test Concept",
    last_verified: date | None = None,
    body: str = "Concept body.\n",
) -> Path:
    """Write a minimally-valid concept file and return its path."""
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{slug}.md"

    lines = [
        "---",
        f"title: {title}",
        f"id: {_next_concept_id()}",
        "aliases: []",
        "tags: []",
        "status: active",
    ]
    if last_verified is not None:
        lines.append(f"last_verified: {last_verified.isoformat()}")
    lines.extend(["---", "", body])

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# refresh_orphan_concept
# ---------------------------------------------------------------------------


def test_refresh_orphan_concept_sets_last_verified_when_none(tmp_path: Path) -> None:
    """Concept with ``last_verified=None`` gets today's date stamped."""
    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    path = _write_concept(concepts_dir, last_verified=None)

    # Sanity: parsed initial state has last_verified = None
    before = parse_concept_file(path)
    assert before is not None
    assert before.frontmatter.last_verified is None

    refresh_orphan_concept(path)

    after = parse_concept_file(path)
    assert after is not None
    assert after.frontmatter.last_verified == date.today()


def test_refresh_orphan_concept_overwrites_prior_last_verified(tmp_path: Path) -> None:
    """Concept with a prior ``last_verified`` is overwritten with today's date."""
    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    prior = date.today() - timedelta(days=365)
    path = _write_concept(concepts_dir, last_verified=prior)

    before = parse_concept_file(path)
    assert before is not None
    assert before.frontmatter.last_verified == prior

    refresh_orphan_concept(path)

    after = parse_concept_file(path)
    assert after is not None
    assert after.frontmatter.last_verified == date.today()


def test_refresh_orphan_concept_unparseable_returns_none(tmp_path: Path) -> None:
    """Unparseable concept files return ``None`` without raising.

    The file is left untouched (helper has no recovery path for malformed
    input — parity with other lifecycle helpers).
    """
    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / "broken.md"
    original_content = "no frontmatter here at all\n"
    path.write_text(original_content, encoding="utf-8")

    result = refresh_orphan_concept(path)

    assert result is None
    assert path.read_text(encoding="utf-8") == original_content


def test_refresh_orphan_concept_missing_file_returns_none(tmp_path: Path) -> None:
    """Missing concept files return ``None`` without raising."""
    path = tmp_path / ".lexibrary" / "concepts" / "does-not-exist.md"
    assert not path.exists()

    result = refresh_orphan_concept(path)

    assert result is None
    assert not path.exists()


def test_refresh_orphan_concept_atomic_write_no_temp_files(tmp_path: Path) -> None:
    """Successful refresh leaves no ``.tmp`` artefacts in the concepts dir.

    ``atomic_write`` creates a sibling temp file then renames via
    ``os.replace`` — on success, only the target file remains.
    """
    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    path = _write_concept(concepts_dir, last_verified=None)

    refresh_orphan_concept(path)

    temp_files = [p for p in concepts_dir.iterdir() if p.suffix == ".tmp"]
    assert temp_files == []
    assert path.exists()


def test_refresh_orphan_concept_preserves_body_content(tmp_path: Path) -> None:
    """Refresh touches only the ``last_verified`` frontmatter field.

    Other frontmatter values and the concept body survive the round-trip
    unchanged (modulo serialization normalization).
    """
    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    body = (
        "This is the concept body.\n\n"
        "It has multiple paragraphs, wikilinks like [[Other Concept]], and\n"
        "file references like `src/lexibrary/foo.py`.\n"
    )
    path = _write_concept(
        concepts_dir,
        title="Preserved Concept",
        body=body,
        last_verified=None,
    )

    refresh_orphan_concept(path)

    after = parse_concept_file(path)
    assert after is not None
    assert after.frontmatter.title == "Preserved Concept"
    assert after.body.strip() == body.strip()


# ---------------------------------------------------------------------------
# refresh_stale_concept
# ---------------------------------------------------------------------------


def _write_concept_with_links(
    project_root: Path,
    *,
    slug: str = "stale-concept",
    title: str = "Stale Concept",
    file_refs: tuple[str, ...] = (),
    extra_body: str = "",
) -> Path:
    """Write a concept whose body contains backtick-delimited file references.

    The concept parser extracts ``linked_files`` by running a regex over
    backticked paths containing ``/`` with a known extension, so we must
    embed real backticked paths into the body to exercise
    ``refresh_stale_concept``.
    """
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{slug}.md"

    ref_lines = [f"- `{ref}` describes a module." for ref in file_refs]
    body_parts = [
        f"# {title}",
        "",
        "Links to source files:",
        "",
        *ref_lines,
    ]
    if extra_body:
        body_parts.extend(["", extra_body])

    lines = [
        "---",
        f"title: {title}",
        f"id: {_next_concept_id()}",
        "aliases: []",
        "tags: []",
        "status: active",
        "---",
        "",
        *body_parts,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_refresh_stale_concept_prunes_missing_entries(tmp_path: Path) -> None:
    """3 refs with 1 missing → prunes 1, returns 1, remaining refs intact."""
    project_root = tmp_path
    # Create two real source files; leave ``missing.py`` absent.
    (project_root / "src").mkdir()
    (project_root / "src" / "exists_a.py").write_text("# a\n", encoding="utf-8")
    (project_root / "src" / "exists_b.py").write_text("# b\n", encoding="utf-8")

    concept_path = _write_concept_with_links(
        project_root,
        file_refs=(
            "src/exists_a.py",
            "src/missing.py",
            "src/exists_b.py",
        ),
    )

    pruned = refresh_stale_concept(concept_path, project_root)

    assert pruned == 1
    after = parse_concept_file(concept_path)
    assert after is not None
    assert "src/exists_a.py" in after.linked_files
    assert "src/exists_b.py" in after.linked_files
    assert "src/missing.py" not in after.linked_files


def test_refresh_stale_concept_all_resolve_noop(tmp_path: Path) -> None:
    """All refs resolve → returns 0, file unchanged byte-for-byte."""
    project_root = tmp_path
    (project_root / "src").mkdir()
    (project_root / "src" / "a.py").write_text("# a\n", encoding="utf-8")
    (project_root / "src" / "b.py").write_text("# b\n", encoding="utf-8")

    concept_path = _write_concept_with_links(
        project_root,
        file_refs=("src/a.py", "src/b.py"),
    )
    before_bytes = concept_path.read_bytes()

    pruned = refresh_stale_concept(concept_path, project_root)

    assert pruned == 0
    assert concept_path.read_bytes() == before_bytes


def test_refresh_stale_concept_empty_linked_files_noop(tmp_path: Path) -> None:
    """Concept with no ``linked_files`` entries → returns 0, file unchanged."""
    project_root = tmp_path
    concept_path = _write_concept_with_links(project_root, file_refs=())
    before_bytes = concept_path.read_bytes()

    pruned = refresh_stale_concept(concept_path, project_root)

    assert pruned == 0
    assert concept_path.read_bytes() == before_bytes


def test_refresh_stale_concept_unparseable_returns_zero(tmp_path: Path) -> None:
    """Unparseable concept returns 0 without modifying the file."""
    project_root = tmp_path
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    concept_path = concepts_dir / "broken.md"
    original_content = "no frontmatter at all\n"
    concept_path.write_text(original_content, encoding="utf-8")

    pruned = refresh_stale_concept(concept_path, project_root)

    assert pruned == 0
    assert concept_path.read_text(encoding="utf-8") == original_content


def test_refresh_stale_concept_missing_file_returns_zero(tmp_path: Path) -> None:
    """Concept path that does not exist returns 0 without raising."""
    project_root = tmp_path
    concept_path = project_root / ".lexibrary" / "concepts" / "does-not-exist.md"
    assert not concept_path.exists()

    pruned = refresh_stale_concept(concept_path, project_root)

    assert pruned == 0
    assert not concept_path.exists()


def test_refresh_stale_concept_atomic_write_no_temp_files(tmp_path: Path) -> None:
    """Successful refresh leaves no ``.tmp`` artefacts beside the target."""
    project_root = tmp_path
    (project_root / "src").mkdir()
    (project_root / "src" / "a.py").write_text("# a\n", encoding="utf-8")

    concept_path = _write_concept_with_links(
        project_root,
        file_refs=("src/a.py", "src/vanished.py"),
    )
    concepts_dir = concept_path.parent

    refresh_stale_concept(concept_path, project_root)

    temp_files = [p for p in concepts_dir.iterdir() if p.suffix == ".tmp"]
    assert temp_files == []
    assert concept_path.exists()


def test_refresh_stale_concept_preserves_content_outside_linked_files(
    tmp_path: Path,
) -> None:
    """Body content outside pruned backticked refs survives the round-trip.

    Frontmatter fields, headings, wikilinks, and prose surrounding the
    pruned references must all remain intact. The only content expected
    to change is the exact backticked path of each missing entry.
    """
    project_root = tmp_path
    (project_root / "src").mkdir()
    (project_root / "src" / "kept.py").write_text("# kept\n", encoding="utf-8")

    extra = "## Related\n\n- [[Other Concept]]\n- See also the broader topic.\n"
    concept_path = _write_concept_with_links(
        project_root,
        slug="preserve-concept",
        title="Preserve Concept",
        file_refs=("src/kept.py", "src/gone.py"),
        extra_body=extra,
    )

    refresh_stale_concept(concept_path, project_root)

    after = parse_concept_file(concept_path)
    assert after is not None
    # Frontmatter preserved
    assert after.frontmatter.title == "Preserve Concept"
    assert after.frontmatter.status == "active"
    # Related section preserved
    assert "## Related" in after.body
    assert "[[Other Concept]]" in after.body
    assert "See also the broader topic." in after.body
    # Only the gone.py backticked ref is removed; kept.py remains
    assert "`src/kept.py`" in after.body
    assert "`src/gone.py`" not in after.body


def test_refresh_stale_concept_returns_count_of_pruned_entries(tmp_path: Path) -> None:
    """Returned count equals the number of removed entries, not remaining."""
    project_root = tmp_path
    # No files created → every ref is missing.
    concept_path = _write_concept_with_links(
        project_root,
        file_refs=("src/a.py", "src/b.py", "src/c.py"),
    )

    pruned = refresh_stale_concept(concept_path, project_root)

    assert pruned == 3
    after = parse_concept_file(concept_path)
    assert after is not None
    assert after.linked_files == []


# ---------------------------------------------------------------------------
# refresh_convention_stale
# ---------------------------------------------------------------------------


_convention_id_counter = 0


def _next_convention_id() -> str:
    global _convention_id_counter
    _convention_id_counter += 1
    return f"CV-{_convention_id_counter:03d}"


def _write_convention(
    project_root: Path,
    *,
    slug: str = "test-convention",
    title: str = "Test Convention",
    scope: str = "project",
    body: str = "Always prefer X over Y.\n",
) -> Path:
    """Write a minimally-valid convention file and return its path."""
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{slug}.md"

    lines = [
        "---",
        f"title: '{title}'",
        f"id: {_next_convention_id()}",
        f"scope: {scope}",
        "tags: []",
        "status: active",
        "source: user",
        "priority: 0",
        "---",
        "",
        body,
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_refresh_convention_stale_valid_new_scope_overwrites(tmp_path: Path) -> None:
    """All paths in ``new_scope`` resolve → scope is overwritten, file written."""
    project_root = tmp_path
    (project_root / "src" / "a").mkdir(parents=True)
    (project_root / "src" / "b").mkdir(parents=True)

    convention_path = _write_convention(
        project_root,
        scope="src/a/",
    )

    refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="src/a/, src/b/",
    )

    after = parse_convention_file(convention_path)
    assert after is not None
    assert after.frontmatter.scope == "src/a/, src/b/"


def test_refresh_convention_stale_missing_new_scope_path_raises(tmp_path: Path) -> None:
    """A missing path in ``new_scope`` → ``FileNotFoundError``, file unchanged."""
    project_root = tmp_path
    (project_root / "src" / "exists").mkdir(parents=True)

    convention_path = _write_convention(
        project_root,
        scope="src/exists/",
    )
    before_bytes = convention_path.read_bytes()

    import pytest

    with pytest.raises(FileNotFoundError, match="scope path does not exist"):
        refresh_convention_stale(
            convention_path,
            project_root,
            new_scope="src/exists/, src/ghost/",
        )

    # File must not be touched when validation fails.
    assert convention_path.read_bytes() == before_bytes


def test_refresh_convention_stale_partial_stale_subset_allowed(tmp_path: Path) -> None:
    """Existing scope partially stale; ``new_scope`` is a subset of valid paths."""
    project_root = tmp_path
    (project_root / "src" / "alive").mkdir(parents=True)
    # ``src/gone`` intentionally absent: existing scope includes a stale entry.

    convention_path = _write_convention(
        project_root,
        scope="src/alive/, src/gone/",
    )

    # Refresh narrows the scope to only the still-valid path.
    refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="src/alive/",
    )

    after = parse_convention_file(convention_path)
    assert after is not None
    assert after.frontmatter.scope == "src/alive/"


def test_refresh_convention_stale_all_existing_missing_same_scope_raises(
    tmp_path: Path,
) -> None:
    """Existing scope fully stale AND ``new_scope`` unchanged → ``ValueError``.

    The helper guards against silent no-ops on unrecoverable artifacts:
    when every path in the existing scope is missing and the operator
    supplies the same scope value, the helper refuses via ``ValueError``
    rather than the downstream ``FileNotFoundError`` that the shared
    stale paths would also trigger.
    """
    project_root = tmp_path
    # Neither path exists — existing scope is fully stale.
    convention_path = _write_convention(
        project_root,
        scope="src/gone_a/, src/gone_b/",
    )
    before_bytes = convention_path.read_bytes()

    import pytest

    with pytest.raises(ValueError, match="new_scope required"):
        refresh_convention_stale(
            convention_path,
            project_root,
            new_scope="src/gone_a/, src/gone_b/",
        )

    # File must not be touched when the guard fires.
    assert convention_path.read_bytes() == before_bytes


def test_refresh_convention_stale_new_scope_project_allowed(tmp_path: Path) -> None:
    """``new_scope = "project"`` bypasses path validation (symbolic scope)."""
    project_root = tmp_path
    # Existing scope partially stale; new_scope is the symbolic "project".
    (project_root / "src" / "alive").mkdir(parents=True)

    convention_path = _write_convention(
        project_root,
        scope="src/alive/, src/gone/",
    )

    refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="project",
    )

    after = parse_convention_file(convention_path)
    assert after is not None
    assert after.frontmatter.scope == "project"


def test_refresh_convention_stale_unparseable_returns_none(tmp_path: Path) -> None:
    """Unparseable convention returns ``None`` without raising or writing."""
    project_root = tmp_path
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    convention_path = conventions_dir / "broken.md"
    original_content = "no frontmatter at all\n"
    convention_path.write_text(original_content, encoding="utf-8")

    result = refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="project",
    )

    assert result is None
    assert convention_path.read_text(encoding="utf-8") == original_content


def test_refresh_convention_stale_missing_file_returns_none(tmp_path: Path) -> None:
    """Missing convention file returns ``None`` without raising."""
    project_root = tmp_path
    convention_path = project_root / ".lexibrary" / "conventions" / "does-not-exist.md"
    assert not convention_path.exists()

    result = refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="project",
    )

    assert result is None
    assert not convention_path.exists()


def test_refresh_convention_stale_atomic_write_no_temp_files(tmp_path: Path) -> None:
    """Successful refresh leaves no ``.tmp`` artefacts beside the target."""
    project_root = tmp_path
    (project_root / "src" / "alive").mkdir(parents=True)

    convention_path = _write_convention(
        project_root,
        scope="project",
    )
    conventions_dir = convention_path.parent

    refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="src/alive/",
    )

    temp_files = [p for p in conventions_dir.iterdir() if p.suffix == ".tmp"]
    assert temp_files == []
    assert convention_path.exists()


def test_refresh_convention_stale_fully_stale_new_scope_differs_allowed(
    tmp_path: Path,
) -> None:
    """Fully-stale existing scope + different valid ``new_scope`` → proceeds."""
    project_root = tmp_path
    (project_root / "src" / "replacement").mkdir(parents=True)

    convention_path = _write_convention(
        project_root,
        scope="src/gone_a/, src/gone_b/",
    )

    refresh_convention_stale(
        convention_path,
        project_root,
        new_scope="src/replacement/",
    )

    after = parse_convention_file(convention_path)
    assert after is not None
    assert after.frontmatter.scope == "src/replacement/"


# ---------------------------------------------------------------------------
# refresh_playbook_staleness
# ---------------------------------------------------------------------------


_playbook_id_counter = 0


def _next_playbook_id() -> str:
    global _playbook_id_counter
    _playbook_id_counter += 1
    return f"PB-{_playbook_id_counter:03d}"


def _write_playbook(
    playbooks_dir: Path,
    *,
    slug: str = "test-playbook",
    title: str = "Test Playbook",
    last_verified: date | None = None,
    body: str = "## Overview\n\nPlaybook overview.\n",
) -> Path:
    """Write a minimally-valid playbook file and return its path."""
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / f"{slug}.md"

    lines = [
        "---",
        f"title: {title}",
        f"id: {_next_playbook_id()}",
        "trigger_files: []",
        "tags: []",
        "status: active",
        "source: user",
    ]
    if last_verified is not None:
        lines.append(f"last_verified: {last_verified.isoformat()}")
    lines.extend(["---", "", body])

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_refresh_playbook_staleness_sets_last_verified_when_none(tmp_path: Path) -> None:
    """Playbook with ``last_verified=None`` gets today's date stamped."""
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    path = _write_playbook(playbooks_dir, last_verified=None)

    before = parse_playbook_file(path)
    assert before is not None
    assert before.frontmatter.last_verified is None

    refresh_playbook_staleness(path)

    after = parse_playbook_file(path)
    assert after is not None
    assert after.frontmatter.last_verified == date.today()


def test_refresh_playbook_staleness_overwrites_prior_last_verified(tmp_path: Path) -> None:
    """Playbook with a prior ``last_verified`` is overwritten with today's date."""
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    prior = date.today() - timedelta(days=180)
    path = _write_playbook(playbooks_dir, last_verified=prior)

    before = parse_playbook_file(path)
    assert before is not None
    assert before.frontmatter.last_verified == prior

    refresh_playbook_staleness(path)

    after = parse_playbook_file(path)
    assert after is not None
    assert after.frontmatter.last_verified == date.today()


def test_refresh_playbook_staleness_idempotent_on_same_day(tmp_path: Path) -> None:
    """Same-day re-invocation is a no-op on the stored value.

    The helper unconditionally writes the file (value = ``date.today()``),
    so the byte contents may be refreshed if the original had the same
    value. What matters is that ``last_verified`` remains ``date.today()``
    and no exception is raised on the second call.
    """
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    path = _write_playbook(playbooks_dir, last_verified=date.today())

    refresh_playbook_staleness(path)
    refresh_playbook_staleness(path)

    after = parse_playbook_file(path)
    assert after is not None
    assert after.frontmatter.last_verified == date.today()


def test_refresh_playbook_staleness_unparseable_returns_none(tmp_path: Path) -> None:
    """Unparseable playbook files return ``None`` without raising.

    The file is left untouched (helper has no recovery path for malformed
    input — parity with other lifecycle helpers).
    """
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / "broken.md"
    original_content = "no frontmatter here at all\n"
    path.write_text(original_content, encoding="utf-8")

    result = refresh_playbook_staleness(path)

    assert result is None
    assert path.read_text(encoding="utf-8") == original_content


def test_refresh_playbook_staleness_missing_file_returns_none(tmp_path: Path) -> None:
    """Missing playbook files return ``None`` without raising."""
    path = tmp_path / ".lexibrary" / "playbooks" / "does-not-exist.md"
    assert not path.exists()

    result = refresh_playbook_staleness(path)

    assert result is None
    assert not path.exists()


def test_refresh_playbook_staleness_atomic_write_no_temp_files(tmp_path: Path) -> None:
    """Successful refresh leaves no ``.tmp`` artefacts in the playbooks dir.

    ``atomic_write`` creates a sibling temp file then renames via
    ``os.replace`` — on success, only the target file remains.
    """
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    path = _write_playbook(playbooks_dir, last_verified=None)

    refresh_playbook_staleness(path)

    temp_files = [p for p in playbooks_dir.iterdir() if p.suffix == ".tmp"]
    assert temp_files == []
    assert path.exists()


def test_refresh_playbook_staleness_preserves_body_content(tmp_path: Path) -> None:
    """Refresh touches only the ``last_verified`` frontmatter field.

    Other frontmatter values and the playbook body survive the round-trip
    unchanged (modulo serialization normalization).
    """
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    body = (
        "## Overview\n\n"
        "Bump the version number in pyproject.toml and rebuild.\n\n"
        "## Steps\n\n"
        "1. [ ] Update pyproject.toml\n"
        "2. [ ] Run build command\n"
    )
    path = _write_playbook(
        playbooks_dir,
        title="Version Bump",
        body=body,
        last_verified=None,
    )

    refresh_playbook_staleness(path)

    after = parse_playbook_file(path)
    assert after is not None
    assert after.frontmatter.title == "Version Bump"
    assert "## Overview" in after.body
    assert "Bump the version number" in after.body
    assert "## Steps" in after.body


def test_refresh_orphan_concept_module_has_no_output_import() -> None:
    """SHARED_BLOCK_A: ``lifecycle/refresh.py`` must not import ``_output``."""
    repo_root = Path(__file__).resolve().parents[2]
    refresh_py = repo_root / "src" / "lexibrary" / "lifecycle" / "refresh.py"
    source = refresh_py.read_text(encoding="utf-8")
    assert "from lexibrary._output" not in source
    assert "import lexibrary._output" not in source
