## Context

Phase 1 delivered: Pydantic config system, CLI skeleton with `lexi init` / `lexi index` stubs, project scaffolding into `.lexibrary/`, artifact data models (`AIndexFile`, `AIndexEntry`, `StalenessMetadata`), and the ignore system. The `lexi index` command exists but is a stub.

Phase 2 makes indexing real. The output format is v2 `.aindex` — a structured markdown file written to the `.lexibrary/` mirror tree (e.g., `src/auth/` → `.lexibrary/src/auth/.aindex`). Generation is structural-only (no LLM): descriptions come from file extension, language detection, and line counts.

**Current state of key files:**
- `src/lexibrary/artifacts/aindex.py` — `AIndexFile`, `AIndexEntry` (with `is_directory: bool`), `StalenessMetadata` defined
- `src/lexibrary/config/schema.py` — `CrawlConfig` exists with `max_file_size_kb` but no `binary_extensions`
- `src/lexibrary/cli.py` — `lexi index` is a stub
- `src/lexibrary/indexer/` — does not exist yet

## Goals / Non-Goals

**Goals:**
- Implement `lexi index <dir>` and `lexi index -r <dir>` end-to-end
- Produce v2 `.aindex` files with Child Map table, Local Conventions (empty), and staleness metadata footer
- Bottom-up recursive traversal so child `.aindex` files exist before parent references them
- Serializer/parser pair that round-trips cleanly
- Atomic file writes (temp file → rename) to prevent partial writes
- All ignored files/directories excluded from Child Map entries
- Binary file detection via extension list in `CrawlConfig`

**Non-Goals:**
- LLM-generated descriptions (Phase 4)
- Change detection / skip-if-unchanged (Phase 4)
- Local Conventions content population (future phase)
- `lexi update` integration (Phase 4)
- Token counting in Child Map (deferred)
- `START_HERE.md` generation (Phase 4)

## Decisions

### D-001: `entry_type: Literal["file", "dir"]` replaces `is_directory: bool`

**Decision:** Replace `AIndexEntry.is_directory: bool` with `entry_type: Literal["file", "dir"]`.

**Rationale:** The v2 `.aindex` format uses a `Type` column with values `file` and `dir`. Storing the same information as a string literal eliminates a boolean-to-string translation in the serializer, is more explicit in the type signature, and maps directly to the markdown column value. Phase 1 has no persisted data so this is a clean break.

**Alternative considered:** Keep `is_directory: bool` and translate in the serializer. Rejected — creates unnecessary impedance mismatch between model and format.

### D-002: Serializer and parser are separate modules from the model

**Decision:** `aindex_serializer.py` and `aindex_parser.py` are standalone modules, not methods on `AIndexFile`.

**Rationale:** Keeps the data model pure (no I/O or format knowledge). Serialization and parsing are the complex parts with their own test suites. Separating concerns makes each module independently testable and replaceable. The model stays a dumb data container.

**Alternative considered:** `AIndexFile.to_markdown()` / `AIndexFile.from_markdown()` class methods. Rejected — couples format logic to the data model; harder to replace the format in future.

### D-003: Structural descriptions only (no LLM)

**Decision:** Phase 2 descriptions are mechanical:
- Files: `"{Language} source ({N} lines)"` or `"Binary file (.ext)"`
- Subdirectories: `"Contains {N} files"` or `"Contains {N} files, {M} subdirectories"`
- Billboard: dominant language or `"Mixed-language directory ({lang1}, {lang2})"` or `"Empty directory."`

**Rationale:** LLM calls add cost, latency, and API key requirements. Phase 2 validates the serialization/parsing pipeline with zero infrastructure. Phase 4 replaces mechanical descriptions with LLM prose using the same pipeline.

### D-004: Bottom-up traversal order

**Decision:** `index_recursive()` uses `discover_directories_bottom_up()` (deepest-first BFS) so child `.aindex` files exist when parent directories are processed.

**Rationale:** Parent `.aindex` entries for subdirectories read child `.aindex` files to compute descriptions like "Contains 5 files, 2 subdirectories." If traversal were top-down, child `.aindex` wouldn't exist yet. Bottom-up ensures data is available when needed.

### D-005: Always regenerate (no change detection in Phase 2)

**Decision:** Every `lexi index` invocation regenerates targeted `.aindex` files unconditionally.

**Rationale:** Without LLM calls, generation is cheap — just filesystem reads and string operations. Change detection adds complexity (cache files, hash management) with no meaningful benefit at this phase. Revisit in Phase 4 when LLM costs make skipping valuable.

### D-006: Generator returns model, orchestrator handles I/O

**Decision:** `generate_aindex()` returns an `AIndexFile` model (pure function, no I/O). `index_directory()` calls generator → serializer → writer in sequence.

**Rationale:** Separates computation from side effects. The generator is fully testable with `tmp_path` fixtures without touching the real filesystem for output. Clean pipeline: model → string → file.

### D-007: Atomic writes via temp-file rename

**Decision:** `write_artifact()` writes to a `.tmp` file alongside the target, then renames. Creates parent directories as needed.

**Rationale:** Prevents partial files if the process is interrupted mid-write. `os.rename()` / `Path.rename()` is atomic on the same filesystem (POSIX guarantee). Generic utility — not `.aindex`-specific, reusable for design files, concept files in later phases.

### D-008: `binary_extensions` in `CrawlConfig`

**Decision:** Add `binary_extensions: list[str]` to the existing `CrawlConfig` Pydantic model.

**Rationale:** `CrawlConfig` already exists with `max_file_size_kb`. Binary extension detection belongs in crawl config (it governs how files are processed during indexing). Defaults cover common image, audio, video, font, archive, document, compiled, and database formats.

## Risks / Trade-offs

- **Language detection accuracy** → Uses extension-to-language mapping (no Tree-sitter in Phase 2). Unknown extensions fall back to `"Unknown"`. Mitigation: good-enough for structural descriptions; Phase 4 can improve with AST parsing.
- **Large directories** → Generating `.aindex` for a directory with thousands of files produces a large Child Map. Mitigation: no hard limit in Phase 2; `max_file_size_kb` addresses file reads, not directory size. Phase 4 can add truncation.
- **`entry_type` breaking change** → Any code using `AIndexEntry.is_directory` will fail at import or runtime. Mitigation: only Phase 1 tests reference the field; all are updated in this change.
- **Mirror tree depth** → Deep project trees produce deeply nested `.lexibrary/` subdirectories. `Path.mkdir(parents=True)` handles this; no risk.
- **Ignored directories in recursive traversal** → Must not recurse into ignored directories (e.g., `node_modules/`, `.git/`). Mitigation: `discover_directories_bottom_up()` uses `IgnoreMatcher` to filter — same as crawler engine.

## Open Questions

- **Q-001 (Phase 4):** When `lexi update` regenerates `.aindex`, how should it preserve agent/human-authored Local Conventions? Options: parse-and-reinject vs. treat as untouchable section. Not needed for Phase 2 (Local Conventions always `(none)`).
