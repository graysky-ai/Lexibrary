# Handoff

**Task:** Update blueprints/ design documentation to reflect current codebase state
**Status:** Complete — all design files created/updated; `lexi init` and `lexi index [-r]` are fully implemented
**Next step:** Implement remaining stub CLI commands; start with `lexi update` (re-index changed files)
**Key files:** `blueprints/src/lexibrary/indexer/orchestrator.md`, `blueprints/src/lexibrary/crawler/engine.md`, `blueprints/src/lexibrary/config/schema.md`
**Watch out:** `crawler/engine.py` is broken — references v1 indexer types (`IandexData`, `FileEntry`, `DirEntry`) and missing config fields (`config.output`); use `indexer/orchestrator.py` for indexing work
