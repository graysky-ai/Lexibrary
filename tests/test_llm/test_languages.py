"""Tests for language detection from file extensions."""

from __future__ import annotations

import pytest

from lexibrary.utils.languages import detect_language


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("main.py", "Python"),
        ("index.js", "JavaScript"),
        ("App.tsx", "TypeScript JSX"),
        ("styles.css", "CSS"),
        ("config.yaml", "YAML"),
        ("schema.sql", "SQL"),
        ("lib.rs", "Rust"),
        ("main.go", "Go"),
        ("server.java", "Java"),
        ("utils.rb", "Ruby"),
    ],
)
def test_known_extensions(filename: str, expected: str) -> None:
    assert detect_language(filename) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Dockerfile", "Dockerfile"),
        ("Makefile", "Makefile"),
        ("CMakeLists.txt", "CMake"),
        ("Gemfile", "Ruby"),
    ],
)
def test_special_filenames(filename: str, expected: str) -> None:
    assert detect_language(filename) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (".gitignore", "Config"),
        (".env", "Config"),
        (".dockerignore", "Config"),
        (".editorconfig", "Config"),
    ],
)
def test_config_dotfiles(filename: str, expected: str) -> None:
    assert detect_language(filename) == expected


def test_unknown_extension() -> None:
    assert detect_language("data.xyz") == "Text"


def test_no_extension() -> None:
    assert detect_language("LICENSE") == "Text"
