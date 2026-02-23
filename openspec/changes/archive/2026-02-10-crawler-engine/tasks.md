## 1. Config Update

- [x] 1.1 Add `binary_extensions` field to `CrawlConfig` in `src/lexibrary/config/schema.py` with default list of common binary extensions
- [x] 1.2 Add `binary_extensions` to the default config template in `src/lexibrary/config/defaults.py`

## 2. File Reader

- [x] 2.1 Create `src/lexibrary/crawler/file_reader.py` with `FileContent` dataclass, `is_binary_file()`, and `read_file_for_indexing()`
- [x] 2.2 Create `tests/test_crawler/test_file_reader.py` with tests for binary detection, text reading, truncation, Latin-1 fallback, and unreadable files

## 3. Directory Discovery

- [x] 3.1 Create `src/lexibrary/crawler/discovery.py` with `discover_directories_bottom_up()` and `list_directory_files()`
- [x] 3.2 Create `tests/test_crawler/test_discovery.py` with tests for bottom-up ordering, ignore pruning, file listing, binary extension filtering, and empty directories

## 4. Change Detector

- [x] 4.1 Create `src/lexibrary/crawler/change_detector.py` with `FileState`, `CrawlCache`, and `ChangeDetector` classes
- [x] 4.2 Create `tests/test_crawler/test_change_detector.py` with tests for new/unchanged/modified detection, save/load roundtrip, pruning, clearing, and corrupted cache handling

## 5. Crawl Engine

- [x] 5.1 Create `src/lexibrary/crawler/engine.py` with `CrawlStats`, `full_crawl()`, `_index_directory()`, and `_summarize_changed_files()`
- [x] 5.2 Update `src/lexibrary/crawler/__init__.py` to export `full_crawl` and `CrawlStats`
- [x] 5.3 Create test fixtures at `tests/fixtures/sample_project/` with a small project tree (Python files, README, binary file, nested directories)
- [x] 5.4 Create `tests/test_crawler/test_engine.py` with integration tests: full crawl creates .aindex files, bottom-up ordering, incremental crawl caching, dry-run mode, and stats accuracy

## 6. Verification

- [x] 6.1 Run full test suite: `uv run pytest tests/test_crawler -v`
- [x] 6.2 Run type checking: `uv run mypy src/lexibrary/crawler/`
- [x] 6.3 Run linting and formatting: `uv run ruff check src/lexibrary/crawler/ tests/test_crawler/` and `uv run ruff format src/lexibrary/crawler/ tests/test_crawler/`
