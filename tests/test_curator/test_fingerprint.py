"""Tests for curator fingerprint module — problem fingerprinting and duplicate detection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from lexibrary.curator.fingerprint import (
    _extract_post_id,
    compute_fingerprint,
    create_or_append_post,
    find_duplicate_post,
)
from lexibrary.linkgraph.query import ArtifactResult

# ---------------------------------------------------------------------------
# compute_fingerprint tests
# ---------------------------------------------------------------------------


class TestComputeFingerprint:
    """Tests for deterministic SHA-256 fingerprinting."""

    def test_deterministic_same_inputs_same_hash(self) -> None:
        """Same inputs must always produce the same hash."""
        fp1 = compute_fingerprint("stale_design", "src/foo.py", "design file outdated")
        fp2 = compute_fingerprint("stale_design", "src/foo.py", "design file outdated")
        assert fp1 == fp2

    def test_different_problem_type_different_hash(self) -> None:
        """Different problem types must produce different hashes."""
        fp1 = compute_fingerprint("stale_design", "src/foo.py", "some error")
        fp2 = compute_fingerprint("orphan_concept", "src/foo.py", "some error")
        assert fp1 != fp2

    def test_different_artifact_path_different_hash(self) -> None:
        """Different artifact paths must produce different hashes."""
        fp1 = compute_fingerprint("stale_design", "src/foo.py", "some error")
        fp2 = compute_fingerprint("stale_design", "src/bar.py", "some error")
        assert fp1 != fp2

    def test_different_error_signature_different_hash(self) -> None:
        """Different error signatures must produce different hashes."""
        fp1 = compute_fingerprint("stale_design", "src/foo.py", "error A")
        fp2 = compute_fingerprint("stale_design", "src/foo.py", "error B")
        assert fp1 != fp2

    def test_whitespace_normalization(self) -> None:
        """Whitespace in error signature should be collapsed before hashing."""
        fp1 = compute_fingerprint("stale_design", "src/foo.py", "design  file   outdated")
        fp2 = compute_fingerprint("stale_design", "src/foo.py", "design file outdated")
        assert fp1 == fp2

    def test_case_normalization(self) -> None:
        """Error signature should be lowercased before hashing."""
        fp1 = compute_fingerprint("stale_design", "src/foo.py", "Design File Outdated")
        fp2 = compute_fingerprint("stale_design", "src/foo.py", "design file outdated")
        assert fp1 == fp2

    def test_returns_hex_sha256(self) -> None:
        """The fingerprint must be a valid 64-character hex string."""
        fp = compute_fingerprint("test", "path", "sig")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_leading_trailing_whitespace_normalized(self) -> None:
        """Leading/trailing whitespace in error_signature is stripped."""
        fp1 = compute_fingerprint("t", "p", "  hello world  ")
        fp2 = compute_fingerprint("t", "p", "hello world")
        assert fp1 == fp2

    def test_tabs_and_newlines_normalized(self) -> None:
        """Tabs and newlines in error_signature are collapsed to spaces."""
        fp1 = compute_fingerprint("t", "p", "hello\tworld\nfoo")
        fp2 = compute_fingerprint("t", "p", "hello world foo")
        assert fp1 == fp2


# ---------------------------------------------------------------------------
# find_duplicate_post tests
# ---------------------------------------------------------------------------


class TestFindDuplicatePost:
    """Tests for duplicate detection via full-text search."""

    def test_returns_none_when_link_graph_is_none(self) -> None:
        """Graceful degradation: None link graph returns None."""
        result = find_duplicate_post("abc123", "stale_design", "src/foo.py", None)
        assert result is None

    def test_returns_matching_open_post(self) -> None:
        """An open stack post with matching fingerprint returns its code."""
        fp = compute_fingerprint("stale_design", "src/foo.py", "outdated")

        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = [
            ArtifactResult(
                id=1,
                path=".lexibrary/stack/ST-001-some-slug.md",
                kind="stack_post",
                title=f"stale_design: src/foo.py [fp:{fp}]",
                status="open",
                artifact_code="ST-001",
            ),
        ]

        result = find_duplicate_post(fp, "stale_design", "src/foo.py", mock_graph)
        assert result == "ST-001"

    def test_resolved_post_not_matched(self) -> None:
        """A resolved post with matching fingerprint should NOT be returned."""
        fp = compute_fingerprint("stale_design", "src/foo.py", "outdated")

        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = [
            ArtifactResult(
                id=1,
                path=".lexibrary/stack/ST-001-some-slug.md",
                kind="stack_post",
                title=f"stale_design: src/foo.py [fp:{fp}]",
                status="resolved",
                artifact_code="ST-001",
            ),
        ]

        result = find_duplicate_post(fp, "stale_design", "src/foo.py", mock_graph)
        assert result is None

    def test_duplicate_status_post_not_matched(self) -> None:
        """A post with 'duplicate' status should NOT be returned."""
        fp = compute_fingerprint("stale_design", "src/foo.py", "outdated")

        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = [
            ArtifactResult(
                id=1,
                path=".lexibrary/stack/ST-001-slug.md",
                kind="stack_post",
                title=f"stale_design: src/foo.py [fp:{fp}]",
                status="duplicate",
                artifact_code="ST-001",
            ),
        ]

        result = find_duplicate_post(fp, "stale_design", "src/foo.py", mock_graph)
        assert result is None

    def test_no_match_returns_none(self) -> None:
        """No matching posts returns None."""
        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = []

        result = find_duplicate_post("abc123", "stale_design", "src/foo.py", mock_graph)
        assert result is None

    def test_non_stack_post_kind_ignored(self) -> None:
        """Results that are not stack_post kind are ignored."""
        fp = compute_fingerprint("stale_design", "src/foo.py", "outdated")

        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = [
            ArtifactResult(
                id=1,
                path=".lexibrary/concepts/some-concept.md",
                kind="concept",
                title=f"stale_design: src/foo.py [fp:{fp}]",
                status="active",
                artifact_code="CN-001",
            ),
        ]

        result = find_duplicate_post(fp, "stale_design", "src/foo.py", mock_graph)
        assert result is None

    def test_mismatched_fingerprint_not_returned(self) -> None:
        """An open post with a different fingerprint should not match."""
        fp = compute_fingerprint("stale_design", "src/foo.py", "outdated")
        other_fp = compute_fingerprint("stale_design", "src/foo.py", "different error")

        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = [
            ArtifactResult(
                id=1,
                path=".lexibrary/stack/ST-001-slug.md",
                kind="stack_post",
                title=f"stale_design: src/foo.py [fp:{other_fp}]",
                status="open",
                artifact_code="ST-001",
            ),
        ]

        result = find_duplicate_post(fp, "stale_design", "src/foo.py", mock_graph)
        assert result is None

    def test_constructs_correct_search_query(self) -> None:
        """The search query should combine problem_type and artifact_path."""
        mock_graph = MagicMock()
        mock_graph.full_text_search.return_value = []

        find_duplicate_post("abc", "stale_design", "src/foo.py", mock_graph)

        mock_graph.full_text_search.assert_called_once_with("stale_design src/foo.py")


# ---------------------------------------------------------------------------
# create_or_append_post tests
# ---------------------------------------------------------------------------


class TestCreateOrAppendPost:
    """Tests for the create-or-append dispatch logic."""

    def test_no_duplicate_creates_new_post(self, tmp_path: Path) -> None:
        """When no duplicate exists, a new Stack post is created."""
        stack_dir = tmp_path / ".lexibrary" / "stack"
        stack_dir.mkdir(parents=True)

        with (
            patch(
                "lexibrary.curator.fingerprint.find_duplicate_post",
                return_value=None,
            ),
            patch(
                "lexibrary.curator.fingerprint.create_stack_post",
                return_value=stack_dir / "ST-001-stale-design-src-foo-py.md",
            ) as mock_create,
        ):
            result = create_or_append_post(
                "stale_design",
                "src/foo.py",
                "design outdated",
                "The design file is stale",
                None,
                project_root=tmp_path,
            )

        assert result == "ST-001"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs[1]["tags"] == ["stale_design", "curator"]
        assert call_kwargs[1]["author"] == "curator"
        assert call_kwargs[1]["problem"] == "The design file is stale"
        assert call_kwargs[1]["refs_files"] == ["src/foo.py"]
        # Fingerprint should be embedded in the title
        assert "[fp:" in call_kwargs[1]["title"]

    def test_duplicate_found_appends_finding(self, tmp_path: Path) -> None:
        """When a duplicate is found, a Finding is appended."""
        stack_dir = tmp_path / ".lexibrary" / "stack"
        stack_dir.mkdir(parents=True)
        post_path = stack_dir / "ST-005-existing-post.md"
        post_path.touch()

        mock_post = MagicMock()

        with (
            patch(
                "lexibrary.curator.fingerprint.find_duplicate_post",
                return_value="ST-005",
            ),
            patch(
                "lexibrary.curator.fingerprint.find_post_path",
                return_value=post_path,
            ),
            patch(
                "lexibrary.curator.fingerprint.add_finding",
                return_value=mock_post,
            ) as mock_add_finding,
        ):
            result = create_or_append_post(
                "stale_design",
                "src/foo.py",
                "design outdated",
                "The design file is stale",
                MagicMock(),
                project_root=tmp_path,
            )

        assert result == "ST-005"
        mock_add_finding.assert_called_once_with(
            post_path, author="curator", body="The design file is stale"
        )

    def test_search_failure_creates_post_anyway(self, tmp_path: Path) -> None:
        """When full_text_search raises, a new post is still created."""
        stack_dir = tmp_path / ".lexibrary" / "stack"
        stack_dir.mkdir(parents=True)

        mock_graph = MagicMock()

        with (
            patch(
                "lexibrary.curator.fingerprint.find_duplicate_post",
                side_effect=RuntimeError("FTS5 error"),
            ),
            patch(
                "lexibrary.curator.fingerprint.create_stack_post",
                return_value=stack_dir / "ST-001-new-post.md",
            ) as mock_create,
        ):
            result = create_or_append_post(
                "stale_design",
                "src/foo.py",
                "design outdated",
                "The design file is stale",
                mock_graph,
                project_root=tmp_path,
            )

        assert result == "ST-001"
        mock_create.assert_called_once()

    def test_duplicate_found_but_file_missing_creates_new(self, tmp_path: Path) -> None:
        """If duplicate ID is in index but file is missing on disk, create new."""
        stack_dir = tmp_path / ".lexibrary" / "stack"
        stack_dir.mkdir(parents=True)

        with (
            patch(
                "lexibrary.curator.fingerprint.find_duplicate_post",
                return_value="ST-099",
            ),
            patch(
                "lexibrary.curator.fingerprint.find_post_path",
                return_value=None,
            ),
            patch(
                "lexibrary.curator.fingerprint.create_stack_post",
                return_value=stack_dir / "ST-002-new-post.md",
            ) as mock_create,
        ):
            result = create_or_append_post(
                "orphan_concept",
                "concepts/old.md",
                "no references",
                "Concept has zero inbound links",
                MagicMock(),
                project_root=tmp_path,
            )

        assert result == "ST-002"
        mock_create.assert_called_once()

    def test_custom_author(self, tmp_path: Path) -> None:
        """The author parameter is forwarded to create_stack_post."""
        stack_dir = tmp_path / ".lexibrary" / "stack"
        stack_dir.mkdir(parents=True)

        with (
            patch(
                "lexibrary.curator.fingerprint.find_duplicate_post",
                return_value=None,
            ),
            patch(
                "lexibrary.curator.fingerprint.create_stack_post",
                return_value=stack_dir / "ST-001-post.md",
            ) as mock_create,
        ):
            create_or_append_post(
                "test_type",
                "path.py",
                "sig",
                "rationale",
                None,
                project_root=tmp_path,
                author="custom-agent",
            )

        assert mock_create.call_args[1]["author"] == "custom-agent"


# ---------------------------------------------------------------------------
# _extract_post_id tests
# ---------------------------------------------------------------------------


class TestExtractPostId:
    """Tests for the internal post ID extraction helper."""

    def test_standard_filename(self) -> None:
        assert _extract_post_id(Path("ST-001-some-slug.md")) == "ST-001"

    def test_long_slug(self) -> None:
        assert _extract_post_id(Path("ST-042-a-very-long-slug-name.md")) == "ST-042"

    def test_no_slug(self) -> None:
        assert _extract_post_id(Path("ST-007.md")) == "ST-007"
