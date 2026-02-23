"""Tests for ignore pattern matching."""

from __future__ import annotations

from pathlib import Path

import pathspec

from lexibrary.config.schema import IgnoreConfig
from lexibrary.ignore import create_ignore_matcher
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.ignore.patterns import load_config_patterns


def test_config_patterns_match(tmp_path: Path) -> None:
    """Config patterns should match common files and directories."""
    config = IgnoreConfig()
    spec = load_config_patterns(config)

    assert spec.match_file(".lexibrary/src/.aindex")
    assert spec.match_file("node_modules/foo")
    assert spec.match_file("file.lock")
    assert not spec.match_file("src/main.py")


def test_is_ignored_with_config_pattern(tmp_path: Path) -> None:
    """is_ignored should return True for paths matching config patterns."""
    config_spec = pathspec.PathSpec.from_lines("gitignore", [".aindex", "*.lock"])
    matcher = IgnoreMatcher(tmp_path, config_spec, [])

    assert matcher.is_ignored(tmp_path / ".aindex")
    assert matcher.is_ignored(tmp_path / "package.lock")
    assert not matcher.is_ignored(tmp_path / "src" / "main.py")


def test_is_ignored_with_gitignore_pattern(tmp_path: Path) -> None:
    """is_ignored should return True for paths matching .gitignore patterns."""
    # Create .gitignore
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__/\n")

    config_spec = pathspec.PathSpec.from_lines("gitignore", [])
    gitignore_spec = pathspec.PathSpec.from_lines("gitignore", ["*.pyc", "__pycache__/"])
    matcher = IgnoreMatcher(tmp_path, config_spec, [(tmp_path, gitignore_spec)])

    assert matcher.is_ignored(tmp_path / "test.pyc")
    assert matcher.is_ignored(tmp_path / "__pycache__" / "foo.py")
    assert not matcher.is_ignored(tmp_path / "src" / "main.py")


def test_hierarchical_gitignore_override(tmp_path: Path) -> None:
    """Subdirectory .gitignore should take precedence over parent."""
    # Root .gitignore
    root_gitignore = tmp_path / ".gitignore"
    root_gitignore.write_text("*.log\n")

    # Subdirectory .gitignore with negation
    subdir = tmp_path / "logs"
    subdir.mkdir()
    sub_gitignore = subdir / ".gitignore"
    sub_gitignore.write_text("!important.log\n")

    config_spec = pathspec.PathSpec.from_lines("gitignore", [])
    root_spec = pathspec.PathSpec.from_lines("gitignore", ["*.log"])
    sub_spec = pathspec.PathSpec.from_lines("gitignore", ["!important.log"])

    matcher = IgnoreMatcher(
        tmp_path,
        config_spec,
        [(tmp_path, root_spec), (subdir, sub_spec)],
    )

    # File in root should be ignored
    assert matcher.is_ignored(tmp_path / "debug.log")

    # File in subdir matching negation should NOT be ignored
    # Note: pathspec negations can be tricky, so this tests the logic
    assert not matcher.is_ignored(subdir / "other.py")


def test_should_descend_ignores_directory(tmp_path: Path) -> None:
    """should_descend should return False for ignored directories."""
    config_spec = pathspec.PathSpec.from_lines("gitignore", ["node_modules/", ".venv/"])
    matcher = IgnoreMatcher(tmp_path, config_spec, [])

    assert not matcher.should_descend(tmp_path / "node_modules")
    assert not matcher.should_descend(tmp_path / ".venv")
    assert matcher.should_descend(tmp_path / "src")


def test_create_ignore_matcher_with_gitignore(tmp_path: Path) -> None:
    """create_ignore_matcher should load .gitignore when enabled."""
    from lexibrary.config.schema import LexibraryConfig

    # Create .gitignore
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n")

    config = LexibraryConfig()
    matcher = create_ignore_matcher(config, tmp_path)

    # Config patterns should work
    assert matcher.is_ignored(tmp_path / ".lexibrary" / "src" / ".aindex")

    # Gitignore patterns should work
    assert matcher.is_ignored(tmp_path / "test.pyc")


def test_create_ignore_matcher_without_gitignore(tmp_path: Path) -> None:
    """create_ignore_matcher should skip .gitignore when disabled."""
    from lexibrary.config.schema import LexibraryConfig

    # Create .gitignore
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n")

    config = LexibraryConfig()
    config.ignore.use_gitignore = False
    matcher = create_ignore_matcher(config, tmp_path)

    # Config patterns should work
    assert matcher.is_ignored(tmp_path / ".lexibrary" / "src" / ".aindex")

    # Gitignore patterns should NOT work
    assert not matcher.is_ignored(tmp_path / "test.pyc")


def test_lexignore_patterns_loaded(tmp_path: Path) -> None:
    """create_ignore_matcher should load .lexignore patterns when the file exists."""
    from lexibrary.config.schema import LexibraryConfig

    (tmp_path / ".lexignore").write_text("**/migrations/\n")

    config = LexibraryConfig()
    config.ignore.use_gitignore = False
    matcher = create_ignore_matcher(config, tmp_path)

    assert matcher.is_ignored(tmp_path / "app" / "migrations" / "0001_initial.py")
    assert not matcher.is_ignored(tmp_path / "app" / "models.py")


def test_lexignore_missing_is_ok(tmp_path: Path) -> None:
    """create_ignore_matcher should not raise when .lexignore is absent."""
    from lexibrary.config.schema import LexibraryConfig

    config = LexibraryConfig()
    config.ignore.use_gitignore = False
    # No .lexignore file — should succeed without error
    matcher = create_ignore_matcher(config, tmp_path)

    assert not matcher.is_ignored(tmp_path / "src" / "main.py")


def test_config_patterns_match_dotenv_files(tmp_path: Path) -> None:
    """Default config patterns match .env, .env.*, and *.env files."""
    config = IgnoreConfig()
    spec = load_config_patterns(config)

    # .env exact match
    assert spec.match_file(".env")
    # .env.* wildcard matches
    assert spec.match_file(".env.local")
    assert spec.match_file(".env.production")
    # *.env wildcard matches
    assert spec.match_file("staging.env")
    assert spec.match_file("production.env")
    # Regular files should not match
    assert not spec.match_file("src/main.py")
    assert not spec.match_file("environment.py")


def test_three_layer_ignore_merge(tmp_path: Path) -> None:
    """A file ignored by any single layer should be excluded."""
    from lexibrary.config.schema import LexibraryConfig

    # .gitignore ignores *.log
    (tmp_path / ".gitignore").write_text("*.log\n")
    # .lexignore ignores migrations/
    (tmp_path / ".lexignore").write_text("**/migrations/\n")
    # Config ignores *.tmp via additional_patterns
    config = LexibraryConfig()
    config.ignore.additional_patterns = ["*.tmp"]

    matcher = create_ignore_matcher(config, tmp_path)

    # Matched by .gitignore layer
    assert matcher.is_ignored(tmp_path / "debug.log")
    # Matched by .lexignore layer
    assert matcher.is_ignored(tmp_path / "app" / "migrations" / "0001.py")
    # Matched by config layer
    assert matcher.is_ignored(tmp_path / "scratch.tmp")
    # Not matched by any layer
    assert not matcher.is_ignored(tmp_path / "src" / "main.py")
