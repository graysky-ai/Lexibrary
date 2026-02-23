# Phase 2: Directory Indexes (`.aindex`)

**Goal:** `lexi index` produces `.aindex` files inside the `.lexibrary/` mirror tree.
**Milestone:** `lexi index -r .` generates a complete set of `.aindex` files for a sample project; round-trip test passes.
**Depends on:** Phase 1 (artifact data models, config system, CLI skeleton, project init).

---

## Decisions Settled

| # | Decision | Resolution |
|---|----------|------------|
| 1 | LLM usage | **Structural-only in Phase 2.** Billboard and descriptions are mechanical (language, file count). LLM enrichment deferred to Phase 4 (Archivist). |
| 2 | `lexi index` scope | Single directory by default. `-r` / `--recursive` flag for bottom-up recursive indexing. |
| 3 | Token column in Child Map | **Dropped.** `AIndexEntry` keeps `name`, `description`, `is_directory` — no `tokens` field. Token counting is Phase 4+ concern. |
| 4 | Config additions | **Add `CrawlConfig` to schema now** with binary extensions, max file size, etc. |
| 5 | Local Conventions | **Empty placeholder** in Phase 2. Future phases will provide agent-population mechanism with preservation on update. |

---

## Open Question: Change Detection Strategy

Phase 2 needs a way to skip regenerating `.aindex` for directories that haven't changed. The existing `ChangeDetector` tracks per-file content hashes. Directory-level change detection is a different problem — a directory is "changed" if its listing changed (files added/removed/renamed) or any child file's content changed.

### Option A: Always regenerate

Every `lexi index` invocation regenerates all targeted `.aindex` files unconditionally.

| Pros | Cons |
|------|------|
| Simplest implementation — no cache to manage | Redundant work on large projects |
| Always correct — no staleness bugs | Slower for incremental workflows |
| Fine for Phase 2 where generation is cheap (no LLM) | Won't scale when LLM enrichment arrives in Phase 4 |

### Option B: Directory listing hash

Hash the sorted list of `(name, is_directory)` tuples for each directory. Compare against a stored hash. Only regenerate if the listing changed.

| Pros | Cons |
|------|------|
| Cheap to compute — no file reads needed | Misses file content changes (descriptions may reference content) |
| Catches add/remove/rename accurately | Needs a new cache file or extending `ChangeDetector` |
| Natural fit for structural-only Phase 2 | Phase 4 will need content-aware detection anyway |

### Option C: Composite hash (listing + child content hashes)

Hash the directory listing combined with content hashes of all child files. Catches both structural and content changes.

| Pros | Cons |
|------|------|
| Complete — detects any change that could affect the `.aindex` | More expensive — must hash all child files |
| Extends naturally to Phase 4 (LLM regeneration decisions) | More complex cache structure |
| Reuses existing `hash_file()` infrastructure | May be over-engineering for structural-only phase |

### Recommendation

**Start with Option A (always regenerate) for Phase 2.** Generation is cheap without LLM calls — just directory listing + metadata. Add Option C when Phase 4 introduces LLM costs that make skipping valuable. The `.aindex` serializer and parser are the hard parts; swapping the change detection strategy later is straightforward.

If you disagree, let me know which option you prefer and I'll adjust the plan.

---

## .aindex Format (v2)

The v2 format evolves from v1. Key changes: output lands in `.lexibrary/` mirror tree (not source tree), token column dropped, Local Conventions section added, staleness metadata footer added.

### Example output

```markdown
# src/auth/

Authentication and authorization modules for the application.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `login.py` | file | Python source (42 lines) |
| `middleware.py` | file | Python source (128 lines) |
| `tokens/` | dir | Contains 3 files |

## Local Conventions

(none)

<!-- lexibrary:meta
source: src/auth
source_hash: d4e5f6a7
generated: 2026-02-19T10:30:00Z
generator: lexibrary v0.2.0
-->
```

### Format rules

1. H1 = directory path relative to project root, with trailing `/`
2. Blank line after H1, after billboard, after each section
3. Child Map is a 3-column table: `Name`, `Type`, `Description`
4. Entries sorted alphabetically (case-insensitive), directories after files
5. File names wrapped in backticks; directory names have trailing `/` and backticks
6. `Type` column: `file` or `dir`
7. Empty sections show `(none)`
8. Local Conventions section always present (empty = `(none)`)
9. Staleness metadata as HTML comment footer
10. File ends with a trailing newline

### Structural descriptions (no LLM)

Since Phase 2 is LLM-free, descriptions are mechanical:

- **Files:** `"{Language} source ({line_count} lines)"` or `"Binary file ({ext})"` for binary files
- **Directories:** `"Contains {N} files"` or `"Contains {N} files, {M} subdirectories"` (counts from child `.aindex` if it exists, otherwise from direct listing)
- **Billboard:** `"Directory containing {language} source files."` — derived from the dominant language of contained files. If mixed: `"Mixed-language directory ({lang1}, {lang2})."` If empty: `"Empty directory."`

These will be replaced by LLM-generated prose in Phase 4.

---

## Implementation Tasks

### 2.1 Add `CrawlConfig` to config schema

**File:** `src/lexibrary/config/schema.py`

Add a `CrawlConfig` model to `LexibraryConfig`:

```python
class CrawlConfig(BaseModel):
    """Crawl/indexing configuration."""
    model_config = ConfigDict(extra="ignore")

    binary_extensions: list[str] = Field(
        default_factory=lambda: [
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
            ".mp3", ".mp4", ".wav", ".ogg", ".webm",
            ".woff", ".woff2", ".ttf", ".eot",
            ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".exe", ".dll", ".so", ".dylib",
            ".pyc", ".pyo", ".class", ".o", ".obj",
            ".sqlite", ".db",
        ]
    )
    max_file_size_kb: int = 512
```

Wire into `LexibraryConfig`:

```python
class LexibraryConfig(BaseModel):
    # ... existing fields ...
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
```

Update `src/lexibrary/config/defaults.py` if the default YAML template needs a `crawl:` section.

**Tests:** `tests/test_config/test_schema.py` — validate defaults, override, extra-field tolerance.

---

### 2.2 Update `AIndexEntry` model — add `entry_type` field

**File:** `src/lexibrary/artifacts/aindex.py`

The current model uses `is_directory: bool`. The new format has an explicit `Type` column. Replace with a string field for clarity and future extensibility:

```python
from typing import Literal

class AIndexEntry(BaseModel):
    """A single entry in a directory's .aindex file."""
    name: str
    entry_type: Literal["file", "dir"]
    description: str
```

Drop `is_directory`. This is a breaking change to the model but Phase 1 only has tests, no persisted data.

**Tests:** Update `tests/test_artifacts/test_models.py` to use `entry_type` instead of `is_directory`.

---

### 2.3 `.aindex` markdown serializer

**File:** `src/lexibrary/artifacts/aindex_serializer.py` (new)

```python
def serialize_aindex(data: AIndexFile) -> str:
    """Serialize an AIndexFile model to the v2 .aindex markdown format."""
```

Converts an `AIndexFile` Pydantic model into the markdown string per the format rules above. Includes the staleness metadata footer as an HTML comment.

**Key behaviours:**
- Entries sorted: files first (alphabetical), then dirs (alphabetical)
- Names wrapped in backticks; dir names get trailing `/`
- Empty `local_conventions` renders as `(none)`
- Metadata footer serialized as `<!-- lexibrary:meta ... -->`

**Tests:** `tests/test_artifacts/test_aindex_serializer.py`

| Test | Verifies |
|------|----------|
| `test_serialize_basic` | Correct markdown for a directory with files and subdirs |
| `test_serialize_empty` | Both sections show `(none)` for empty directory |
| `test_serialize_files_only` | No dirs in table |
| `test_serialize_dirs_only` | No files in table |
| `test_serialize_sorting` | Files before dirs, each group alphabetical case-insensitive |
| `test_serialize_local_conventions` | Conventions rendered as bullet list |
| `test_serialize_metadata_footer` | HTML comment footer present and parseable |
| `test_serialize_trailing_newline` | Output ends with `\n` |

---

### 2.4 `.aindex` markdown parser

**File:** `src/lexibrary/artifacts/aindex_parser.py` (new)

```python
def parse_aindex(path: Path) -> AIndexFile | None:
    """Parse an existing .aindex file into an AIndexFile model.

    Returns None if file doesn't exist or is malformed.
    """

def parse_aindex_metadata(path: Path) -> StalenessMetadata | None:
    """Parse only the metadata footer from an .aindex file.

    Cheaper than full parse when only checking staleness.
    """
```

Regex-based parser matching the v2 format. Tolerant of minor whitespace differences.

**Key behaviours:**
- Extracts H1 as `directory_path`
- Extracts billboard (text between H1 and first H2)
- Parses Child Map table rows into `AIndexEntry` objects
- Parses Local Conventions as list of strings (bullet items)
- Parses metadata HTML comment into `StalenessMetadata`
- Returns `None` for missing/malformed files (no exceptions)

**Tests:** `tests/test_artifacts/test_aindex_parser.py`

| Test | Verifies |
|------|----------|
| `test_parse_basic` | Parses well-formed `.aindex` into correct `AIndexFile` |
| `test_parse_nonexistent` | Returns `None` for missing file |
| `test_parse_malformed` | Returns `None` for garbage content |
| `test_parse_empty_sections` | Handles `(none)` gracefully |
| `test_parse_local_conventions` | Extracts convention bullet items |
| `test_parse_metadata` | Extracts staleness metadata from footer |
| `test_parse_metadata_only` | `parse_aindex_metadata` works standalone |

---

### 2.5 Round-trip test

**File:** `tests/test_artifacts/test_aindex_roundtrip.py`

| Test | Verifies |
|------|----------|
| `test_roundtrip` | `serialize → write → parse` produces identical `AIndexFile` |
| `test_roundtrip_empty` | Works for a directory with no entries |
| `test_roundtrip_with_conventions` | Local Conventions survive round-trip |
| `test_roundtrip_unicode` | Unicode names and descriptions preserved |

---

### 2.6 Atomic file writer

**File:** `src/lexibrary/artifacts/writer.py` (new)

```python
def write_artifact(target: Path, content: str) -> Path:
    """Atomically write content to a file path.

    Creates parent directories if needed. Writes to a temp file first,
    then renames (atomic on same filesystem). Returns the target path.
    """
```

Generic atomic writer — not specific to `.aindex`. Reusable for design files, concept files, etc. in later phases.

This replaces the v1 `indexer/writer.py` (retired in Phase 1) with a more general-purpose utility.

**Tests:** `tests/test_artifacts/test_writer.py`

| Test | Verifies |
|------|----------|
| `test_write_creates_file` | File exists after write |
| `test_write_creates_parents` | Parent directories created automatically |
| `test_write_content_matches` | File content matches input |
| `test_write_overwrites` | Writing twice overwrites cleanly |
| `test_write_atomic` | No partial files left on simulated failure |

---

### 2.7 Index generator (core logic)

**File:** `src/lexibrary/indexer/generator.py` (new — in new `indexer/` module)

```python
def generate_aindex(
    directory: Path,
    project_root: Path,
    ignore_matcher: IgnoreMatcher,
    binary_extensions: set[str],
) -> AIndexFile:
    """Generate an AIndexFile for a single directory.

    Reads the directory listing, categorizes entries, generates
    structural descriptions (no LLM), and returns the model.
    """
```

**Key behaviours:**
- Lists directory contents via `list_directory_files()` from existing crawler
- For each file: detect language, count lines, build description
- For each subdirectory: check if child `.aindex` exists in `.lexibrary/` mirror, extract entry count from it; otherwise count direct children
- Generate billboard from dominant language
- Build `StalenessMetadata` with `source_hash` = hash of sorted directory listing
- Return `AIndexFile` model (not markdown — serialization is separate)

**Tests:** `tests/test_indexer/test_generator.py` (using `tmp_path` fixtures)

| Test | Verifies |
|------|----------|
| `test_generate_basic` | Produces correct `AIndexFile` for a directory with files and subdirs |
| `test_generate_empty_dir` | Handles empty directory |
| `test_generate_mixed_languages` | Billboard mentions multiple languages |
| `test_generate_binary_files` | Binary files get `"Binary file (ext)"` description |
| `test_generate_ignores_ignored` | Ignored files excluded from entries |
| `test_generate_subdir_with_child_aindex` | Uses child `.aindex` data for subdir description |
| `test_generate_subdir_without_child_aindex` | Falls back to direct listing count |

---

### 2.8 Index orchestrator

**File:** `src/lexibrary/indexer/orchestrator.py` (new)

```python
def index_directory(
    directory: Path,
    project_root: Path,
    config: LexibraryConfig,
) -> Path:
    """Generate and write a single .aindex file.

    Returns the path to the written .aindex file in .lexibrary/.
    """

def index_recursive(
    directory: Path,
    project_root: Path,
    config: LexibraryConfig,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> IndexStats:
    """Recursively index a directory tree bottom-up.

    Discovers directories deepest-first, generates .aindex for each,
    writes to .lexibrary/ mirror tree. Returns stats.
    """

@dataclass
class IndexStats:
    directories_indexed: int = 0
    files_found: int = 0
    errors: int = 0
```

**Key behaviours:**
- `index_directory`: calls generator → serializer → writer pipeline for one directory
- `index_recursive`: uses `discover_directories_bottom_up()` then calls `index_directory` for each. Bottom-up order ensures child `.aindex` files exist before parents reference them.
- Both construct `IgnoreMatcher` from config
- Both compute `aindex_path()` for output location
- Progress callback for CLI feedback

**Tests:** `tests/test_indexer/test_orchestrator.py` (using `tmp_path` fixtures)

| Test | Verifies |
|------|----------|
| `test_index_single_directory` | Writes `.aindex` to correct `.lexibrary/` mirror path |
| `test_index_recursive_bottom_up` | All directories get `.aindex`; child processed before parent |
| `test_index_recursive_parent_references_child` | Parent `.aindex` subdir description uses data from child `.aindex` |
| `test_index_stats` | Stats correctly count directories, files, errors |
| `test_index_creates_mirror_dirs` | `.lexibrary/` subdirectories created as needed |
| `test_index_skips_lexibrary_dir` | `.lexibrary/` itself is not indexed |

---

### 2.9 Wire `lexi index` CLI command

**File:** `src/lexibrary/cli.py`

Replace the stub with the real implementation:

```python
@app.command()
def index(
    directory: Annotated[Path, typer.Argument(help="Directory to index")] = Path("."),
    recursive: Annotated[bool, typer.Option("-r", "--recursive", help="Index recursively")] = False,
) -> None:
    """Generate .aindex for a directory (or recursively with -r)."""
```

**Behaviour:**
- Calls `_require_project_root()` (existing)
- Resolves `directory` relative to CWD
- Validates directory exists and is within project root
- If `--recursive`: calls `index_recursive()` with a Rich progress bar
- If not recursive: calls `index_directory()`
- Prints summary stats on completion via `rich.console.Console`

**Tests:** `tests/test_cli.py` — extend existing CLI tests

| Test | Verifies |
|------|----------|
| `test_index_single` | `lexi index src/` writes `.lexibrary/src/.aindex` |
| `test_index_recursive` | `lexi index -r .` writes `.aindex` for all directories |
| `test_index_no_project` | Error message when no `.lexibrary/` found |
| `test_index_nonexistent_dir` | Error message for missing directory |
| `test_index_outside_project` | Error message for directory outside project root |

---

### 2.10 Extend test fixtures

**File:** `tests/fixtures/sample_project/`

Extend the existing sample project to exercise Phase 2:

- Add a `src/utils/` subdirectory with 2-3 small Python files
- Add a binary file (e.g., `assets/logo.png`) to test binary detection
- Add a `.gitignore` that ignores `build/`
- Add a `build/` directory (should be ignored during indexing)

This fixture is used by integration tests in 2.7 and 2.8.

---

## Task Ordering

```
2.1  CrawlConfig ─────────────────────────────┐
2.2  AIndexEntry model update ─────────────────┤
                                               ├─→ 2.7 Generator ──→ 2.8 Orchestrator ──→ 2.9 CLI
2.3  Serializer ───────────────────────────────┤                           ↑
2.4  Parser ───────→ 2.5 Round-trip test ──────┤                           │
2.6  Atomic writer ────────────────────────────┘                           │
2.10 Test fixtures ────────────────────────────────────────────────────────┘
```

Tasks 2.1–2.6 and 2.10 are independent of each other and can be implemented in parallel. Tasks 2.7, 2.8, and 2.9 are sequential and depend on the earlier tasks.

---

## Acceptance Criteria

- [ ] `CrawlConfig` added to config schema with binary extensions and max file size
- [ ] `AIndexEntry` uses `entry_type: Literal["file", "dir"]` instead of `is_directory: bool`
- [ ] `serialize_aindex()` produces markdown matching the v2 format spec
- [ ] `parse_aindex()` correctly extracts all fields from serialized content
- [ ] Round-trip test: serialize → write → parse → compare passes
- [ ] `write_artifact()` writes atomically with parent directory creation
- [ ] `generate_aindex()` produces correct structural descriptions (no LLM)
- [ ] `lexi index <dir>` writes a single `.aindex` to `.lexibrary/<dir>/.aindex`
- [ ] `lexi index -r <dir>` writes `.aindex` for all descendant directories bottom-up
- [ ] Parent `.aindex` files reference child directory data correctly
- [ ] Ignored files/directories are excluded from `.aindex` entries
- [ ] Binary files are detected and described as `"Binary file ({ext})"`
- [ ] `.lexibrary/` mirror directories are created on demand
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] Linting passes: `uv run ruff check src/ tests/`
- [ ] Type checking passes: `uv run mypy src/`

---

## What This Phase Does NOT Do

- **No LLM calls** — descriptions are mechanical. Phase 4 adds LLM enrichment.
- **No change detection** — always regenerates. Revisit when LLM costs make skipping valuable.
- **No Local Conventions content** — section is always `(none)`. Future phase adds population mechanism.
- **No `lexi update` integration** — `lexi update` remains a stub. Phase 4 wires the full update pipeline.
- **No START_HERE.md generation** — Phase 4.
- **No token counting in Child Map** — deferred to when it's needed.
