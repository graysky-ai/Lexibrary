"""Unit tests for IWH gitignore integration."""

from __future__ import annotations

from pathlib import Path

from lexibrary.iwh.gitignore import ensure_iwh_gitignored


class TestEnsureIWHGitignored:
    """Tests for ensure_iwh_gitignored()."""

    def test_adds_pattern_to_existing_gitignore(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        result = ensure_iwh_gitignored(tmp_path)
        assert result is True
        content = gitignore.read_text(encoding="utf-8")
        assert "**/.iwh" in content
        # Existing patterns preserved
        assert "*.pyc" in content
        assert "__pycache__/" in content

    def test_creates_gitignore_if_missing(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        assert not gitignore.exists()
        result = ensure_iwh_gitignored(tmp_path)
        assert result is True
        assert gitignore.exists()
        content = gitignore.read_text(encoding="utf-8")
        assert "**/.iwh" in content

    def test_idempotent_when_already_present(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n**/.iwh\n", encoding="utf-8")
        original_content = gitignore.read_text(encoding="utf-8")
        result = ensure_iwh_gitignored(tmp_path)
        assert result is False
        assert gitignore.read_text(encoding="utf-8") == original_content

    def test_recognizes_alternative_pattern_dotiwh(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n.iwh\n", encoding="utf-8")
        result = ensure_iwh_gitignored(tmp_path)
        assert result is False

    def test_recognizes_alternative_pattern_lexibrary(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n.lexibrary/**/.iwh\n", encoding="utf-8")
        result = ensure_iwh_gitignored(tmp_path)
        assert result is False

    def test_preserves_existing_content(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        existing = "# Build artifacts\n*.pyc\n__pycache__/\n\n# IDE\n.vscode/\n"
        gitignore.write_text(existing, encoding="utf-8")
        ensure_iwh_gitignored(tmp_path)
        content = gitignore.read_text(encoding="utf-8")
        # All original lines should still be present
        assert "# Build artifacts" in content
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert "# IDE" in content
        assert ".vscode/" in content

    def test_adds_newline_before_pattern_if_missing(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        # File without trailing newline
        gitignore.write_text("*.pyc", encoding="utf-8")
        ensure_iwh_gitignored(tmp_path)
        content = gitignore.read_text(encoding="utf-8")
        # Pattern should be on its own line
        lines = content.splitlines()
        assert "*.pyc" in lines
        assert "**/.iwh" in lines

    def test_pattern_has_trailing_newline(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        ensure_iwh_gitignored(tmp_path)
        content = gitignore.read_text(encoding="utf-8")
        assert content.endswith("\n")

    def test_multiple_calls_idempotent(self, tmp_path: Path) -> None:
        ensure_iwh_gitignored(tmp_path)
        ensure_iwh_gitignored(tmp_path)
        ensure_iwh_gitignored(tmp_path)
        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        # Pattern should appear exactly once
        assert content.count("**/.iwh") == 1

    def test_comment_lines_not_matched(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("# **/.iwh\n", encoding="utf-8")
        result = ensure_iwh_gitignored(tmp_path)
        # A commented-out pattern should not count
        assert result is True
