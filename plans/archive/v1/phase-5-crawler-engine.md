# Phase 5: Crawler Engine

**Goal:** The core crawl orchestrator — bottom-up directory traversal, file reading, change detection, and wiring together the LLM service, tokenizer, and indexer.
**Milestone:** `lexi crawl` produces `.aindex` files for an entire project tree.
**Depends on:** Phase 1 (config, ignore, utils), Phase 2 (tokenizer), Phase 3 (indexer), Phase 4 (LLM service).

This is the central integration phase. It consumes everything built in Phases 1-4.

---

## 5.1 File Reader

### File: `src/lexibrary/crawler/file_reader.py`

Reads files for LLM summarization with binary detection and size limits.

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class FileContent:
    path: Path
    content: str
    encoding: str
    size_bytes: int
    is_truncated: bool

def is_binary_file(path: Path, sample_size: int = 8192) -> bool:
    """Quick binary detection: read first N bytes, check for null bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except OSError:
        return True  # treat unreadable files as binary

def read_file_for_indexing(path: Path, max_size_kb: int = 512) -> FileContent | None:
    """Read a file for LLM summarization.

    Returns None if the file is binary or unreadable.
    Truncates to max_size_kb if the file is larger.
    """
    if is_binary_file(path):
        return None

    size_bytes = path.stat().st_size
    max_bytes = max_size_kb * 1024
    is_truncated = size_bytes > max_bytes

    try:
        # Try UTF-8 first
        raw = path.read_bytes()
        if is_truncated:
            raw = raw[:max_bytes]
        content = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        try:
            content = raw.decode("latin-1")
            encoding = "latin-1"
        except Exception:
            return None

    return FileContent(
        path=path,
        content=content,
        encoding=encoding,
        size_bytes=size_bytes,
        is_truncated=is_truncated,
    )
```

Key considerations:
- Binary detection uses null-byte heuristic (fast, works for most cases)
- UTF-8 first, Latin-1 fallback (covers ~99% of source code)
- Truncation happens at the byte level before decoding
- Returns `None` for unreadable files — caller handles gracefully

---

## 5.2 Discovery

### File: `src/lexibrary/crawler/discovery.py`

Directory and file discovery with ignore filtering.

```python
from __future__ import annotations
import os
from pathlib import Path
from ..ignore.matcher import IgnoreMatcher

def discover_directories_bottom_up(root: Path, matcher: IgnoreMatcher) -> list[Path]:
    """Return all directories under root, sorted deepest-first.

    Uses os.walk with topdown=True so we can prune ignored directories,
    then reverses the result for bottom-up ordering.
    """
    directories: list[Path] = []

    for dirpath, dirnames, _ in os.walk(root, topdown=True):
        current = Path(dirpath)

        # Prune ignored directories in-place (prevents os.walk from descending)
        dirnames[:] = [
            d for d in dirnames
            if matcher.should_descend(current / d)
        ]

        directories.append(current)

    # Reverse for bottom-up (deepest first)
    directories.sort(key=lambda p: len(p.parts), reverse=True)
    return directories


def list_directory_files(
    directory: Path,
    matcher: IgnoreMatcher,
    binary_extensions: set[str],
    max_size_kb: int,
) -> tuple[list[Path], list[Path]]:
    """List files in a single directory.

    Returns:
        (indexable_files, skipped_files)
        - indexable_files: text files within size limit, not ignored
        - skipped_files: binary/oversized/ignored files (listed in .aindex with generic description)
    """
    indexable: list[Path] = []
    skipped: list[Path] = []

    try:
        entries = sorted(directory.iterdir())
    except PermissionError:
        return [], []

    for entry in entries:
        if not entry.is_file():
            continue
        if matcher.is_ignored(entry):
            continue

        ext = entry.suffix.lower()
        if ext in binary_extensions:
            skipped.append(entry)
            continue

        try:
            size_kb = entry.stat().st_size / 1024
        except OSError:
            skipped.append(entry)
            continue

        # Even large files are indexable (they get truncated by file_reader)
        # but we can mark them as skipped if desired
        indexable.append(entry)

    return indexable, skipped
```

---

## 5.3 Change Detector

### File: `src/lexibrary/crawler/change_detector.py`

Hash-based change detection with a JSON cache file.

```python
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from ..utils.hashing import hash_file

CACHE_VERSION = 1

@dataclass
class FileState:
    hash: str
    tokens: int
    summary: str
    last_indexed: str  # ISO 8601

@dataclass
class CrawlCache:
    version: int = CACHE_VERSION
    files: dict[str, FileState] = field(default_factory=dict)


class ChangeDetector:
    """Detects file changes using SHA-256 hashes.

    Stores state in .lexibrary_cache.json at the project root.
    """

    def __init__(self, cache_path: Path):
        self._cache_path = cache_path
        self._cache = CrawlCache()
        self._dirty = False

    def load(self) -> None:
        """Load cache from disk. No-op if file doesn't exist."""
        if not self._cache_path.is_file():
            return
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if raw.get("version") != CACHE_VERSION:
                return  # incompatible version, start fresh
            files = {}
            for key, val in raw.get("files", {}).items():
                files[key] = FileState(**val)
            self._cache = CrawlCache(version=CACHE_VERSION, files=files)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass  # corrupted cache, start fresh

    def save(self) -> None:
        """Write cache to disk if dirty."""
        if not self._dirty:
            return
        data = {
            "version": self._cache.version,
            "files": {k: asdict(v) for k, v in self._cache.files.items()},
        }
        self._cache_path.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        self._dirty = False

    def has_changed(self, file_path: Path) -> bool:
        """Check if a file has changed since last index."""
        key = str(file_path)
        current_hash = hash_file(file_path)
        cached = self._cache.files.get(key)
        if cached is None:
            return True
        return cached.hash != current_hash

    def get_cached(self, file_path: Path) -> FileState | None:
        """Get cached state for a file, or None if not cached."""
        return self._cache.files.get(str(file_path))

    def update(self, file_path: Path, file_hash: str, tokens: int, summary: str) -> None:
        """Update cache for a file after indexing."""
        self._cache.files[str(file_path)] = FileState(
            hash=file_hash,
            tokens=tokens,
            summary=summary,
            last_indexed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._dirty = True

    def prune_deleted(self, existing_files: set[str]) -> None:
        """Remove entries for files that no longer exist."""
        stale = [k for k in self._cache.files if k not in existing_files]
        for k in stale:
            del self._cache.files[k]
        if stale:
            self._dirty = True

    def clear(self) -> None:
        """Clear all cached state (for --full crawl)."""
        self._cache = CrawlCache()
        self._dirty = True
```

### Cache file location
- `.lexibrary_cache.json` at the project root
- Added to `.gitignore` by `lexi init`

---

## 5.4 Crawl Engine

### File: `src/lexibrary/crawler/engine.py`

The main orchestrator. Ties together discovery, file reading, change detection, tokenizer, LLM service, and indexer.

```python
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from ..config.schema import LexibraryConfig
from ..ignore.matcher import IgnoreMatcher, create_ignore_matcher
from ..tokenizer import TokenCounter
from ..llm.service import LLMService, FileSummaryRequest, DirectorySummaryRequest
from ..indexer import IandexData, FileEntry, DirEntry
from ..indexer.generator import generate_iandex
from ..indexer.writer import write_iandex
from ..indexer.parser import parse_iandex
from ..utils.hashing import hash_file
from ..utils.languages import detect_language
from .discovery import discover_directories_bottom_up, list_directory_files
from .change_detector import ChangeDetector
from .file_reader import read_file_for_indexing, is_binary_file

log = logging.getLogger(__name__)

@dataclass
class CrawlStats:
    directories_indexed: int = 0
    files_summarized: int = 0
    files_cached: int = 0
    files_skipped: int = 0
    llm_calls: int = 0
    errors: int = 0


async def full_crawl(
    root: Path,
    config: LexibraryConfig,
    llm_service: LLMService,
    tokenizer: TokenCounter,
    matcher: IgnoreMatcher,
    change_detector: ChangeDetector,
    dry_run: bool = False,
    progress_callback=None,  # callable(current: int, total: int, dir_name: str)
) -> CrawlStats:
    """Run a full bottom-up crawl of the project tree.

    Algorithm:
    1. Discover all directories (deepest first)
    2. For each directory:
       a. List files, detect changes
       b. Read and summarize changed files (via LLM)
       c. Reuse cached summaries for unchanged files
       d. Count tokens for changed files
       e. Read child subdirectory .aindex summaries
       f. Generate directory summary (via LLM)
       g. Write .aindex file
       h. Update cache
    """
    stats = CrawlStats()
    binary_exts = set(config.crawl.binary_extensions)

    # Step 1: Discover directories
    directories = discover_directories_bottom_up(root, matcher)
    total = len(directories)
    log.info("Found %d directories to index", total)

    # Step 2: Process each directory
    for i, directory in enumerate(directories):
        if progress_callback:
            progress_callback(i + 1, total, directory.name)

        await _index_directory(
            directory=directory,
            root=root,
            config=config,
            llm_service=llm_service,
            tokenizer=tokenizer,
            matcher=matcher,
            change_detector=change_detector,
            binary_exts=binary_exts,
            stats=stats,
            dry_run=dry_run,
        )

    # Save cache
    if not dry_run:
        change_detector.save()

    return stats


async def _index_directory(
    directory: Path,
    root: Path,
    config: LexibraryConfig,
    llm_service: LLMService,
    tokenizer: TokenCounter,
    matcher: IgnoreMatcher,
    change_detector: ChangeDetector,
    binary_exts: set[str],
    stats: CrawlStats,
    dry_run: bool,
) -> None:
    """Index a single directory."""

    # List files
    indexable_files, skipped_files = list_directory_files(
        directory, matcher, binary_exts, config.crawl.max_file_size_kb,
    )

    # Separate changed vs cached files
    changed_files: list[Path] = []
    cached_entries: list[FileEntry] = []

    for file_path in indexable_files:
        if change_detector.has_changed(file_path):
            changed_files.append(file_path)
        else:
            cached = change_detector.get_cached(file_path)
            if cached:
                cached_entries.append(FileEntry(
                    name=file_path.name,
                    tokens=cached.tokens,
                    description=cached.summary,
                ))
                stats.files_cached += 1

    # Add binary/skipped files with generic descriptions
    skipped_entries: list[FileEntry] = []
    for file_path in skipped_files:
        skipped_entries.append(FileEntry(
            name=file_path.name,
            tokens=0,
            description=f"Binary file ({file_path.suffix.lstrip('.')})",
        ))
        stats.files_skipped += 1

    # Read and summarize changed files
    new_entries: list[FileEntry] = []
    if changed_files:
        new_entries = await _summarize_changed_files(
            files=changed_files,
            config=config,
            llm_service=llm_service,
            tokenizer=tokenizer,
            change_detector=change_detector,
            stats=stats,
            dry_run=dry_run,
        )

    # Collect all file entries
    all_file_entries = sorted(
        cached_entries + new_entries + skipped_entries,
        key=lambda e: e.name.lower(),
    )

    # Read child subdirectory summaries from their .aindex files
    subdir_entries: list[DirEntry] = []
    try:
        for child in sorted(directory.iterdir()):
            if child.is_dir() and matcher.should_descend(child):
                child_iandex = child / config.output.filename
                child_data = parse_iandex(child_iandex)
                if child_data:
                    subdir_entries.append(DirEntry(
                        name=child.name + "/",
                        description=child_data.summary,
                    ))
                else:
                    subdir_entries.append(DirEntry(
                        name=child.name + "/",
                        description="(not yet indexed)",
                    ))
    except PermissionError:
        pass

    # Generate directory summary via LLM
    file_list_str = "\n".join(
        f"- {e.name} ({e.tokens} tokens): {e.description}"
        for e in all_file_entries
    )
    subdir_list_str = "\n".join(
        f"- {e.name}: {e.description}"
        for e in subdir_entries
    )

    dir_summary = await llm_service.summarize_directory(
        DirectorySummaryRequest(
            directory=directory,
            file_list=file_list_str,
            subdir_list=subdir_list_str,
        )
    )
    stats.llm_calls += 1

    # Build IandexData
    dir_name = directory.name + "/" if directory != root else directory.name + "/"
    iandex_data = IandexData(
        directory_name=dir_name,
        summary=dir_summary,
        files=all_file_entries,
        subdirectories=subdir_entries,
    )

    # Write .aindex
    if not dry_run:
        content = generate_iandex(iandex_data)
        write_iandex(directory, content, filename=config.output.filename)

    stats.directories_indexed += 1
    log.debug("Indexed: %s (%d files, %d subdirs)", directory, len(all_file_entries), len(subdir_entries))


async def _summarize_changed_files(
    files: list[Path],
    config: LexibraryConfig,
    llm_service: LLMService,
    tokenizer: TokenCounter,
    change_detector: ChangeDetector,
    stats: CrawlStats,
    dry_run: bool,
) -> list[FileEntry]:
    """Read, count tokens, and summarize changed files."""
    entries: list[FileEntry] = []

    # Read all files
    requests: list[FileSummaryRequest] = []
    file_tokens: dict[str, int] = {}

    for file_path in files:
        content = read_file_for_indexing(file_path, config.crawl.max_file_size_kb)
        if content is None:
            # Became binary or unreadable since discovery
            entries.append(FileEntry(name=file_path.name, tokens=0, description="Binary or unreadable file"))
            stats.files_skipped += 1
            continue

        tokens = tokenizer.count(content.content)
        file_tokens[str(file_path)] = tokens

        requests.append(FileSummaryRequest(
            path=file_path,
            content=content.content,
            language=detect_language(file_path.name),
            is_truncated=content.is_truncated,
        ))

    # Batch small files, individual calls for large ones
    batch_threshold = 2048  # chars — files under this go into batch call
    batch_requests = [r for r in requests if len(r.content) < batch_threshold]
    individual_requests = [r for r in requests if len(r.content) >= batch_threshold]

    # Batch calls (groups of max_files_per_llm_batch)
    batch_size = config.crawl.max_files_per_llm_batch
    for i in range(0, len(batch_requests), batch_size):
        chunk = batch_requests[i : i + batch_size]
        results = await llm_service.summarize_files_batch(chunk)
        stats.llm_calls += 1
        for result in results:
            tokens = file_tokens.get(str(result.path), 0)
            entries.append(FileEntry(
                name=result.path.name, tokens=tokens, summary=result.summary,
            ))
            if not dry_run:
                file_hash = hash_file(result.path)
                change_detector.update(result.path, file_hash, tokens, result.summary)
            stats.files_summarized += 1

    # Individual calls
    for req in individual_requests:
        result = await llm_service.summarize_file(req)
        stats.llm_calls += 1
        tokens = file_tokens.get(str(result.path), 0)
        entries.append(FileEntry(
            name=result.path.name, tokens=tokens, description=result.summary,
        ))
        if not dry_run:
            file_hash = hash_file(result.path)
            change_detector.update(result.path, file_hash, tokens, result.summary)
        stats.files_summarized += 1

    return entries
```

---

## 5.5 `__init__.py`

### File: `src/lexibrary/crawler/__init__.py`

```python
from .engine import full_crawl, CrawlStats

__all__ = ["full_crawl", "CrawlStats"]
```

---

## 5.6 Tests

### File: `tests/test_crawler/test_file_reader.py`

| Test | What it verifies |
|------|-----------------|
| `test_read_text_file` | Returns `FileContent` with correct content and encoding |
| `test_read_binary_returns_none` | Binary file returns `None` |
| `test_read_large_file_truncated` | File > max_size_kb is truncated, `is_truncated=True` |
| `test_read_nonexistent` | Nonexistent file returns `None` |
| `test_is_binary_null_bytes` | File with null bytes detected as binary |
| `test_is_binary_text_file` | Normal text file returns `False` |

### File: `tests/test_crawler/test_discovery.py`

| Test | What it verifies |
|------|-----------------|
| `test_discover_bottom_up_ordering` | Deepest directories come first |
| `test_discover_prunes_ignored` | Ignored directories are not traversed |
| `test_list_directory_files` | Returns correct indexable/skipped split |
| `test_list_directory_ignores_binary_ext` | `.png` files go to skipped |
| `test_list_directory_empty` | Empty directory returns empty lists |

### File: `tests/test_crawler/test_change_detector.py`

| Test | What it verifies |
|------|-----------------|
| `test_new_file_is_changed` | Uncached file reports as changed |
| `test_unchanged_file` | File with same hash reports as not changed |
| `test_modified_file` | File with different hash reports as changed |
| `test_save_and_load_roundtrip` | Save cache, create new detector, load, verify entries match |
| `test_prune_deleted` | Entries for deleted files are removed |
| `test_clear` | Clear removes all entries |
| `test_corrupted_cache` | Corrupted JSON file is handled gracefully (start fresh) |

### File: `tests/test_crawler/test_engine.py`

Integration test with mocked LLM:

| Test | What it verifies |
|------|-----------------|
| `test_full_crawl_creates_iandex_files` | Create a fixture project tree, mock LLM, run `full_crawl`, verify `.aindex` files exist in every directory |
| `test_full_crawl_bottom_up` | Verify child `.aindex` exists before parent processes |
| `test_incremental_crawl` | Run twice, verify second run uses cache (fewer LLM calls) |
| `test_dry_run_no_writes` | `dry_run=True` produces stats but no `.aindex` files |
| `test_crawl_stats` | Verify `CrawlStats` counts are correct |

### Test fixtures: `tests/fixtures/sample_project/`

Create a small project tree:
```
sample_project/
├── main.py           # "print('hello')"
├── README.md         # "# Sample"
├── image.png         # binary file (a few null bytes)
├── src/
│   ├── app.py        # small Python file
│   └── utils.py      # small Python file
└── tests/
    └── test_app.py   # small test file
```

---

## Acceptance Criteria

- [ ] `full_crawl()` produces `.aindex` files in every non-ignored directory
- [ ] Directories are processed bottom-up (child before parent)
- [ ] Changed files are re-summarized; unchanged files use cached summaries
- [ ] Binary files are listed with `tokens=0` and generic description
- [ ] Small files are batched into single LLM calls
- [ ] `--dry-run` produces stats without writing any files
- [ ] Cache is persisted and loaded correctly across runs
- [ ] Corrupted/missing cache is handled gracefully (fresh start)
- [ ] `CrawlStats` accurately reflects what happened
- [ ] All tests pass: `uv run pytest tests/test_crawler -v`
