# Phase 3: .aindex Format

**Goal:** Generate, write, and parse `.aindex` Markdown files with a precise, LLM-friendly format.
**Milestone:** Round-trip test passes: `generate → write → parse → verify` data matches.
**Depends on:** Phase 1 (config schema for `OutputConfig`). Independent of Phase 2 and Phase 4.

---

## 3.1 Data Models

### File: `src/lexibrary/indexer/__init__.py`

Shared dataclasses used by the generator and parser:

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class FileEntry:
    """A single file's index entry."""
    name: str           # e.g. "cli.py"
    tokens: int         # token count (0 for binary files)
    description: str    # one-sentence summary

@dataclass
class DirEntry:
    """A subdirectory's index entry."""
    name: str           # e.g. "config/" (always trailing slash)
    description: str    # 1-2 sentence summary (from child .aindex)

@dataclass
class IandexData:
    """Complete contents of a single .aindex file."""
    directory_name: str         # e.g. "lexibrary/"
    summary: str                # 1-3 sentence directory summary
    files: list[FileEntry] = field(default_factory=list)
    subdirectories: list[DirEntry] = field(default_factory=list)
```

---

## 3.2 Generator

### File: `src/lexibrary/indexer/generator.py`

Transforms an `IandexData` object into the Markdown string for a `.aindex` file.

```python
from .models import IandexData, FileEntry, DirEntry

def generate_iandex(data: IandexData) -> str:
    """Generate .aindex Markdown content from structured data."""
    lines: list[str] = []

    # H1: directory name
    lines.append(f"# {data.directory_name}")
    lines.append("")

    # Summary
    lines.append(data.summary)
    lines.append("")

    # Files section
    lines.append("## Files")
    lines.append("")
    if data.files:
        lines.append("| File | Tokens | Description |")
        lines.append("|------|--------|-------------|")
        for f in sorted(data.files, key=lambda x: x.name.lower()):
            lines.append(f"| `{f.name}` | {f.tokens} | {f.description} |")
    else:
        lines.append("(none)")
    lines.append("")

    # Subdirectories section
    lines.append("## Subdirectories")
    lines.append("")
    if data.subdirectories:
        lines.append("| Directory | Description |")
        lines.append("|-----------|-------------|")
        for d in sorted(data.subdirectories, key=lambda x: x.name.lower()):
            name = d.name if d.name.endswith("/") else d.name + "/"
            lines.append(f"| `{name}` | {d.description} |")
    else:
        lines.append("(none)")
    lines.append("")

    return "\n".join(lines)
```

### Format rules enforced
1. H1 = directory name with trailing `/`
2. Blank line after H1, after summary, after each section
3. Files sorted alphabetically (case-insensitive)
4. Subdirectories sorted alphabetically (case-insensitive)
5. Directory names always have trailing `/`
6. File names wrapped in backticks
7. Empty sections show `(none)`
8. File ends with a trailing newline

---

## 3.3 Writer

### File: `src/lexibrary/indexer/writer.py`

Atomic file writes — prevents corruption if the process is interrupted mid-write.

```python
import os
import tempfile
from pathlib import Path

def write_iandex(directory: Path, content: str, filename: str = ".aindex") -> Path:
    """Atomically write .aindex content to a directory.

    Writes to a temp file first, then renames (atomic on same filesystem).
    Returns the path to the written file.
    """
    target = directory / filename
    fd, tmp_path = tempfile.mkstemp(
        dir=directory,
        prefix=".aindex.tmp.",
        suffix=".md",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, target)  # atomic rename
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target
```

Key considerations:
- `os.replace()` is atomic on POSIX (same filesystem)
- Temp file is created in the same directory to ensure same-filesystem rename
- Cleanup on failure prevents orphaned temp files

---

## 3.4 Parser

### File: `src/lexibrary/indexer/parser.py`

Reads existing `.aindex` files to extract cached data. Used during incremental crawls to reuse unchanged file summaries.

```python
import re
from pathlib import Path
from . import IandexData, FileEntry, DirEntry

def parse_iandex(path: Path) -> IandexData | None:
    """Parse an existing .aindex file.

    Returns None if file doesn't exist or is malformed.
    Tolerant of minor formatting differences.
    """
    if not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    lines = content.splitlines()
    if not lines:
        return None

    # Parse H1
    h1_match = re.match(r"^#\s+(.+)$", lines[0])
    if not h1_match:
        return None
    directory_name = h1_match.group(1).strip()

    # Parse summary (lines between H1 and first H2)
    summary_lines: list[str] = []
    files: list[FileEntry] = []
    subdirs: list[DirEntry] = []

    section = "summary"  # tracks which section we're in
    for line in lines[1:]:
        stripped = line.strip()

        if stripped == "## Files":
            section = "files"
            continue
        elif stripped == "## Subdirectories":
            section = "subdirs"
            continue
        elif stripped.startswith("##"):
            section = "unknown"
            continue

        if section == "summary":
            if stripped:
                summary_lines.append(stripped)

        elif section == "files":
            file_match = re.match(
                r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|$", stripped
            )
            if file_match:
                files.append(FileEntry(
                    name=file_match.group(1),
                    tokens=int(file_match.group(2)),
                    description=file_match.group(3).strip(),
                ))

        elif section == "subdirs":
            dir_match = re.match(
                r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|$", stripped
            )
            if dir_match:
                subdirs.append(DirEntry(
                    name=dir_match.group(1),
                    description=dir_match.group(2).strip(),
                ))

    return IandexData(
        directory_name=directory_name,
        summary=" ".join(summary_lines),
        files=files,
        subdirectories=subdirs,
    )
```

### Helper for cached lookups

```python
def get_cached_file_entries(iandex_path: Path) -> dict[str, FileEntry]:
    """Parse .aindex and return file entries keyed by filename.

    Used by the crawler to check if a file's summary can be reused.
    """
    data = parse_iandex(iandex_path)
    if data is None:
        return {}
    return {entry.name: entry for entry in data.files}
```

---

## 3.5 Tests

### File: `tests/test_indexer/test_generator.py`

| Test | What it verifies |
|------|-----------------|
| `test_generate_basic` | Generates valid Markdown with files and subdirs |
| `test_generate_no_files` | Files section shows `(none)` |
| `test_generate_no_subdirs` | Subdirectories section shows `(none)` |
| `test_generate_empty` | Both sections show `(none)` |
| `test_files_sorted_alphabetically` | Output file rows are sorted case-insensitively |
| `test_subdirs_have_trailing_slash` | Directory names always end with `/` |
| `test_trailing_newline` | Output ends with `\n` |

### File: `tests/test_indexer/test_parser.py`

| Test | What it verifies |
|------|-----------------|
| `test_parse_basic` | Parses a well-formed `.aindex` and returns correct `IandexData` |
| `test_parse_nonexistent` | Returns `None` for missing file |
| `test_parse_malformed` | Returns `None` for garbage content |
| `test_parse_empty_sections` | Handles `(none)` sections gracefully (empty lists) |
| `test_get_cached_file_entries` | Returns dict keyed by filename |

### File: `tests/test_indexer/test_roundtrip.py`

| Test | What it verifies |
|------|-----------------|
| `test_roundtrip` | `generate → write → parse` produces identical `IandexData` |
| `test_roundtrip_empty` | Works for a directory with no files and no subdirs |
| `test_roundtrip_unicode` | Handles Unicode filenames and descriptions |

### File: `tests/test_indexer/test_writer.py`

| Test | What it verifies |
|------|-----------------|
| `test_write_creates_file` | `.aindex` file exists after write |
| `test_write_content_matches` | File content matches the input string |
| `test_write_overwrites` | Writing twice overwrites cleanly |
| `test_write_atomic` | No partial files left on simulated failure |

---

## Acceptance Criteria

- [ ] `generate_iandex()` produces Markdown matching the format spec exactly
- [ ] Files are sorted alphabetically (case-insensitive)
- [ ] Subdirectory names always have trailing `/`
- [ ] Empty sections render as `(none)`
- [ ] `write_iandex()` writes atomically (no partial files on failure)
- [ ] `parse_iandex()` correctly extracts all fields from generated content
- [ ] Round-trip test: generate → write → parse → compare passes
- [ ] Parser returns `None` for missing/malformed files (no exceptions)
- [ ] All tests pass: `uv run pytest tests/test_indexer -v`
