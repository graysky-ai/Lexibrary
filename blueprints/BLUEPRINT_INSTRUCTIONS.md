# Blueprint Library — Setup Instructions

**Purpose:** A hand-maintained knowledge layer for the Lexibrary codebase, used by agents building Lexibrary itself. This is a simplified pseudo-lexibrary with a different name and location so agents don't confuse it with the `.lexibrary/` output that Lexibrary *produces*.

**Root:** `blueprints/` (this directory)
**NOT** `.lexibrary/` — that name is reserved for Lexibrary's own output format.

---

## Directory Structure to Create

```
blueprints/
  BLUEPRINT_INSTRUCTIONS.md   ← this file (already exists)
  START_HERE.md               ← bootloader: topology + navigation by intent
  HANDOFF.md                  ← session relay: overwrite on every handoff
  src/
    lexibrary/
      cli.md
      config/
        __init__.md
        defaults.md
        loader.md
        schema.md
      crawler/
        __init__.md
        change_detector.md
        discovery.md
        engine.md
        file_reader.md
      daemon/
        __init__.md
        debouncer.md
        scheduler.md
        service.md
        watcher.md
      ignore/
        __init__.md
        gitignore.md
        matcher.md
        patterns.md
      indexer/
        __init__.md
        generator.md
        parser.md
        writer.md
      llm/
        __init__.md
        factory.md
        rate_limiter.md
        service.md
      tokenizer/
        __init__.md
        anthropic_counter.md
        approximate.md
        base.md
        factory.md
        tiktoken_counter.md
      utils/
        __init__.md
        hashing.md
        languages.md
        logging.md
        paths.md
```

No `.aindex` files yet — navigate via `BLUEPRINT_INSTRUCTIONS.md` and `START_HERE.md` until `.aindex` population is added.

The `baml_client/` package is auto-generated — skip it. Document `baml_src/*.baml` as a group in a single `baml_src.md` instead.

---

## Design File Format

Each `.md` file in `blueprints/src/` follows this template. Keep it tight — aim for 150–300 tokens per file.

```markdown
# <module-name>

**Summary:** One sentence — what this module does and why it exists.

## Interface
<!-- Public functions/classes an agent needs to know to USE this module. -->
<!-- Skip internal helpers. -->

| Name | Signature | Purpose |
| --- | --- | --- |
| `FunctionOrClass` | `(args) -> return` | What it does |

## Dependencies
<!-- Lexibrary-internal imports only. List as bullet paths. -->
- `lexibrary.config.schema` — LexibraryConfig

## Dependents
<!-- Which modules import THIS one. -->
- `lexibrary.crawler.engine`

## Key Concepts
<!-- Wikilink-style references to cross-cutting ideas. No graph infra — just names. -->
- SHA-256 change detection
- BAML prompt definitions

## Dragons
<!-- Optional. Only add if there's a real gotcha. -->
- ...
```

Omit any section that would be empty. `__init__.md` files only need Summary + what the package re-exports.

---

## START_HERE.md Format

`blueprints/START_HERE.md` is the bootloader. Keep it under 600 tokens.

Required sections:
1. **Project Topology** — ASCII tree or Mermaid of the `src/lexibrary/` package structure.
2. **Package Map** — one-line description per subpackage.
3. **Navigation by Intent** — task → file mapping table. Examples:
   - "Add a CLI command" → `blueprints/src/lexibrary/cli.md`
   - "Change ignore patterns" → `blueprints/src/lexibrary/ignore/`
   - "Modify LLM prompts" → `baml_src/`
   - "Change .aindex output format" → `blueprints/src/lexibrary/indexer/`
4. **Key Constraints** — pull the most critical constraints from `CLAUDE.md` (e.g., `from __future__ import annotations`, pathspec pattern name, no bare `print()`).
5. **Navigation Protocol** — one-line instructions: "Before editing a file, read its design file in `blueprints/src/`."

---

## HANDOFF.md Format

`blueprints/HANDOFF.md` is a post-it note, not a document. 5–8 lines max. Overwrite it completely on every session end — never append.

```markdown
# Handoff

**Task:** [one line — what is being done]
**Status:** [one line — where things stand right now]
**Next step:** [one line — what the next agent should do first]
**Key files:** [2–3 file paths]
**Watch out:** [one line — gotcha for the next agent]
```

---

## Populating Design Files — What Each Module Does

Use these summaries as starting points. Read the actual source before writing — the source is canonical.

| Source file | Role |
| --- | --- |
| `cli.py` | Typer app entry point. All `lexi` subcommands (`init`, `update`, `daemon`, `status`). Wires config loading → crawler/daemon. |
| `config/schema.py` | Pydantic 2 models for the full config hierarchy: `LexibraryConfig`, `LLMConfig`, `CrawlConfig`, `TokenizerConfig`, etc. |
| `config/loader.py` | Loads and merges global (`~/.config/lexibrary/`) + project (`.lexibrary/config.yaml`) configs. Returns validated `LexibraryConfig`. |
| `config/defaults.py` | Renders the default `config.yaml` template for `lexi init`. |
| `crawler/engine.py` | Main orchestrator. Wires discovery → file reader → change detector → LLM → indexer writer. Bottom-up crawl logic lives here. |
| `crawler/discovery.py` | Filesystem traversal. `discover_directories_bottom_up()` + `list_directory_files()`. Respects ignore rules. |
| `crawler/file_reader.py` | Reads a source file for indexing — handles encoding, size limits, truncation. |
| `crawler/change_detector.py` | SHA-256 content hashing. Compares stored hashes to decide if a file needs re-indexing. |
| `daemon/service.py` | Async daemon orchestrator. Starts watcher + debouncer + periodic sweep. Handles PID file, signals, graceful shutdown. |
| `daemon/watcher.py` | Watchdog event handler. Converts filesystem events into debounced crawl triggers. |
| `daemon/debouncer.py` | Coalesces rapid filesystem events into single crawl calls with a configurable delay. |
| `daemon/scheduler.py` | Periodic sweep: runs a full crawl on a configurable interval to catch any missed changes. |
| `ignore/matcher.py` | Core ignore logic. Combines `.gitignore` patterns + config `exclude` patterns via pathspec. |
| `ignore/gitignore.py` | Loads and parses `.gitignore` files up the directory tree. |
| `ignore/patterns.py` | Default ignore patterns (build dirs, caches, generated files). |
| `indexer/__init__.py` | Data models: `IandexData`, `FileEntry`, `DirEntry`. The canonical in-memory representation of a `.aindex`. |
| `indexer/generator.py` | Renders `IandexData` → markdown string (the `.aindex` file content). |
| `indexer/parser.py` | Parses an existing `.aindex` markdown file → `IandexData`. Enables incremental updates. |
| `indexer/writer.py` | Writes the rendered markdown to disk at the correct `.aindex` path. |
| `llm/service.py` | BAML client wrapper. Dispatches `FileSummaryRequest` and `DirectorySummaryRequest` to the LLM with retry + rate limit. |
| `llm/factory.py` | Constructs `LLMService` from config. Handles provider selection. |
| `llm/rate_limiter.py` | Token-bucket rate limiter to stay within provider RPM/TPM limits. |
| `tokenizer/base.py` | `TokenCounter` ABC. All tokenizer backends implement this interface. |
| `tokenizer/factory.py` | Creates the right `TokenCounter` from config (`tiktoken`, `anthropic`, `approximate`). |
| `tokenizer/tiktoken_counter.py` | tiktoken-backed counter for OpenAI-compatible models. |
| `tokenizer/anthropic_counter.py` | Anthropic API-backed token counting (exact, slower). |
| `tokenizer/approximate.py` | Fast approximation (chars ÷ 4). Fallback when no backend available. |
| `utils/hashing.py` | `hash_file()` — SHA-256 content hash for change detection. |
| `utils/languages.py` | `detect_language()` — maps file extension → language name for LLM context. |
| `utils/logging.py` | Configures the logging setup for the CLI and daemon. |
| `utils/paths.py` | Path resolution utilities: project root discovery (walks up for `.lexibrary/`), output path computation. |

---

## Workflow for Populating

1. Create `blueprints/START_HERE.md` first — it's the entry point.
2. Create `blueprints/HANDOFF.md` (blank template is fine on first pass).
3. For each source file in the table above: read the actual source, then write its design file in `blueprints/src/lexibrary/`.
4. Start with the modules you're actively working on — no need to do all at once.
5. Keep design files updated as you change source files. The source is truth; the design file is the explanation.
