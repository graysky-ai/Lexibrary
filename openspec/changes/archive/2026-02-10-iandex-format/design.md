## Context

Lexibrary produces `.aindex` Markdown files — one per directory — that serve as navigational maps for AI agents. These files contain a directory summary, a table of files with token counts and descriptions, and a table of subdirectories with summaries. The indexer package is the component responsible for the in-memory representation, serialization, deserialization, and persistence of these files.

This is a pure data-format layer with no LLM or crawler dependencies. It sits between the crawler (which decides *what* to index) and the LLM layer (which produces summaries). The indexer only cares about structured data in, Markdown out, and vice versa.

Phase 1 (Foundation) provides the project scaffolding and package structure. This phase can be developed in parallel with Phases 2 and 4.

## Goals / Non-Goals

**Goals:**
- Define canonical dataclasses for `.aindex` file contents (`IandexData`, `FileEntry`, `DirEntry`)
- Produce deterministic, precisely formatted Markdown from structured data
- Parse existing `.aindex` files back into structured data for cache reuse
- Write `.aindex` files atomically to prevent corruption
- Guarantee round-trip fidelity: `generate → write → parse` yields identical data

**Non-Goals:**
- LLM integration or summary generation (Phase 4)
- Directory crawling or file discovery (Phase 5)
- Token counting (Phase 2)
- Configuration loading or CLI commands
- Supporting any format other than the single `.aindex` Markdown format

## Decisions

### 1. Dataclasses over Pydantic for data models

**Choice**: Use stdlib `@dataclass` for `IandexData`, `FileEntry`, and `DirEntry`.

**Rationale**: These are simple value types with no validation beyond what Python's type system provides. Pydantic would add unnecessary overhead and a dependency for internal data structures that are never deserialized from user input. The config layer (Phase 1) uses Pydantic where validation matters; the indexer models are internal.

**Alternative considered**: Pydantic models — rejected because these models carry no user-facing validation rules and are only constructed programmatically.

### 2. Markdown tables for file and directory listings

**Choice**: Use pipe-delimited Markdown tables for file entries (`| File | Tokens | Description |`) and directory entries (`| Directory | Description |`).

**Rationale**: Tables are the most LLM-parseable structured format within Markdown. They're also human-readable when rendered. The format is simple enough to generate and parse with string operations and basic regex.

**Alternative considered**: YAML front matter + bullet lists — rejected because it splits the document into two formats and is harder for LLMs to scan visually.

### 3. Atomic writes via temp-file-then-rename

**Choice**: Write to a temp file in the same directory, then `os.replace()` to the target path.

**Rationale**: `os.replace()` is atomic on POSIX systems when source and target are on the same filesystem. Creating the temp file in the target directory guarantees same-filesystem. This prevents partial/corrupt `.aindex` files if the process is interrupted.

**Alternative considered**: Direct write with no atomicity — rejected because interrupted writes would leave corrupt index files that the parser would have to handle as errors, degrading the incremental crawl experience.

### 4. Parser returns None for invalid input (no exceptions)

**Choice**: `parse_iandex()` returns `None` for missing, empty, or malformed files rather than raising exceptions.

**Rationale**: The parser is called speculatively during incremental crawls to check for cached data. Missing or corrupt files are expected conditions (first run, manual edits, version changes). Returning `None` lets the caller treat "no cache" uniformly without try/except blocks.

**Alternative considered**: Raising specific exceptions — rejected because it forces every call site to handle multiple exception types for what is fundamentally a "cache miss" scenario.

### 5. Alphabetical sorting of entries

**Choice**: Files and subdirectories are sorted case-insensitively by name in the generated output.

**Rationale**: Deterministic ordering ensures that re-generating an unchanged directory produces byte-identical output, which simplifies change detection and diff readability. Case-insensitive sort matches filesystem conventions and user expectations.

## Risks / Trade-offs

- **[Multi-line descriptions]** → The table format does not support multi-line descriptions. Mitigation: LLM prompts (Phase 4) will instruct the model to produce single-sentence summaries. The parser regex expects single-line cells.

- **[Pipe characters in descriptions]** → A literal `|` in a description would break table parsing. Mitigation: The generator should escape `|` as `\|` in description fields. The parser should handle `\|` as literal pipe.

- **[Large directories]** → Directories with hundreds of files will produce long tables. Mitigation: Not addressed in this phase; the crawler (Phase 5) will handle file-count limits via config.

- **[Platform atomicity]** → `os.replace()` atomicity is guaranteed on POSIX but not on all Windows configurations. Mitigation: Acceptable for v0.1; Windows support is a future concern.
