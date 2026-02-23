# crawler/engine

**Summary:** Main crawl orchestrator that wires directory discovery, file reading, change detection, LLM summarization, and `.aindex` writing in a bottom-up traversal.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `CrawlStats` | `@dataclass` | Counters: `directories_indexed`, `files_summarized`, `files_cached`, `files_skipped`, `llm_calls`, `errors` |
| `full_crawl` | `async (root, config, ignore_matcher, token_counter, llm_service, change_detector, *, dry_run, progress_callback) -> CrawlStats` | Orchestrate a complete bottom-up crawl; calls `change_detector.save()` after unless `dry_run` |

## Dependencies

- `lexibrarian.config.schema` — `LexibraryConfig`
- `lexibrarian.crawler.change_detector` — `ChangeDetector`
- `lexibrarian.crawler.discovery` — `discover_directories_bottom_up`, `list_directory_files`
- `lexibrarian.crawler.file_reader` — `read_file_for_indexing`
- `lexibrarian.ignore.matcher` — `IgnoreMatcher`
- `lexibrarian.llm.service` — `LLMService`, request/result dataclasses
- `lexibrarian.tokenizer.base` — `TokenCounter`
- `lexibrarian.utils.hashing` — `hash_file`
- `lexibrarian.utils.languages` — `detect_language`

## Key Concepts

- Small files (`< 2048 chars`) are batched into `summarize_files_batch()`; large files are sent individually
- On LLM error, `_resolve_summary()` falls back to the cached summary; if no cache, returns placeholder
- `_BATCH_CHAR_THRESHOLD = 2048` controls batching split

## Dragons

- References `config.crawl`, `config.output`, `FileEntry`, `DirEntry`, `IandexData`, `parse_iandex`, `generate_iandex`, `write_iandex` — all from the deleted `indexer` package; **this module will not import cleanly until these are restored or replaced**
- `config.crawl.binary_extensions`, `config.crawl.max_file_size_kb`, `config.crawl.max_files_per_llm_batch`, `config.output.index_filename` — none are in current schema
