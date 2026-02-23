"""File extension to programming language detection."""

from __future__ import annotations

from pathlib import Path

EXTENSION_MAP: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python Stub",
    ".js": "JavaScript",
    ".jsx": "JavaScript JSX",
    ".ts": "TypeScript",
    ".tsx": "TypeScript JSX",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin Script",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C Header",
    ".cpp": "C++",
    ".hpp": "C++ Header",
    ".cc": "C++",
    ".cxx": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".scala": "Scala",
    ".r": "R",
    ".m": "Objective-C",
    ".mm": "Objective-C++",
    ".lua": "Lua",
    ".pl": "Perl",
    ".pm": "Perl",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".fish": "Fish",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".xml": "XML",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "Config",
    ".conf": "Config",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".tex": "LaTeX",
    ".txt": "Text",
    ".csv": "CSV",
    ".tsv": "TSV",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".fs": "F#",
    ".fsx": "F#",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".tf": "Terraform",
    ".dockerfile": "Dockerfile",
    ".baml": "BAML",
}

SPECIAL_FILENAMES: dict[str, str] = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "CMakeLists.txt": "CMake",
    "Rakefile": "Ruby",
    "Gemfile": "Ruby",
    "Vagrantfile": "Ruby",
    "Justfile": "Just",
    "Taskfile.yml": "Task",
}


def detect_language(filename: str) -> str:
    """Detect programming language from a filename.

    Checks special filenames first, then file extension.
    Dotfiles (e.g. .gitignore) return "Config".
    Unknown extensions return "Text".
    """
    name = Path(filename).name

    if name in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[name]

    ext = Path(filename).suffix.lower()

    if not ext and name.startswith("."):
        return "Config"

    return EXTENSION_MAP.get(ext, "Text")
