"""Main crawl orchestrator wiring discovery, file reader, change detector, and LLM."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.crawler.change_detector import ChangeDetector
from lexibrary.crawler.discovery import (
    discover_directories_bottom_up,
    list_directory_files,
)
from lexibrary.crawler.file_reader import read_file_for_indexing
from lexibrary.errors import ErrorSummary
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.llm.service import (
    DirectorySummaryRequest,
    FileSummaryRequest,
    FileSummaryResult,
    LLMService,
)
from lexibrary.tokenizer.base import TokenCounter
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.languages import detect_language

logger = logging.getLogger(__name__)

_BATCH_CHAR_THRESHOLD = 2048


@dataclass
class CrawlStats:
    """Statistics from a crawl run."""

    directories_indexed: int = 0
    files_summarized: int = 0
    files_cached: int = 0
    files_skipped: int = 0
    llm_calls: int = 0
    errors: int = 0
    error_summary: ErrorSummary = field(default_factory=ErrorSummary)


async def full_crawl(
    root: Path,
    config: LexibraryConfig,
    ignore_matcher: IgnoreMatcher,
    token_counter: TokenCounter,
    llm_service: LLMService,
    change_detector: ChangeDetector,
    *,
    dry_run: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> CrawlStats:
    """Orchestrate a complete bottom-up crawl of the project tree.

    Discovers directories deepest-first, processes each directory
    (read files, detect changes, summarize via LLM, generate .aindex),
    and returns crawl statistics.
    """
    stats = CrawlStats()
    binary_exts = set(config.crawl.binary_extensions)
    index_filename = config.output.index_filename

    # Discover directories bottom-up
    directories = discover_directories_bottom_up(root, ignore_matcher)
    total = len(directories)

    for idx, directory in enumerate(directories, start=1):
        if progress_callback is not None:
            dir_name = str(directory.relative_to(root)) if directory != root else "."
            progress_callback(idx, total, dir_name)

        try:
            await _index_directory(
                directory=directory,
                root=root,
                config=config,
                ignore_matcher=ignore_matcher,
                token_counter=token_counter,
                llm_service=llm_service,
                change_detector=change_detector,
                binary_exts=binary_exts,
                index_filename=index_filename,
                stats=stats,
                dry_run=dry_run,
            )
            stats.directories_indexed += 1
        except Exception as exc:
            logger.warning("Error indexing %s", directory, exc_info=True)
            stats.errors += 1
            stats.error_summary.add("crawl", exc, path=str(directory))

    # Save cache after crawl (unless dry run)
    if not dry_run:
        change_detector.save()

    return stats


async def _index_directory(
    *,
    directory: Path,
    root: Path,
    config: LexibraryConfig,
    ignore_matcher: IgnoreMatcher,
    token_counter: TokenCounter,
    llm_service: LLMService,
    change_detector: ChangeDetector,
    binary_exts: set[str],
    index_filename: str,
    stats: CrawlStats,
    dry_run: bool,
) -> None:
    """Process a single directory: read files, summarize, write .aindex."""
    indexable_files, skipped_files = list_directory_files(directory, ignore_matcher, binary_exts)

    # Build file entries
    file_entries: list[FileEntry] = []

    # Handle skipped (binary) files
    for sf in skipped_files:
        ext = sf.suffix.lstrip(".") or "binary"
        file_entries.append(FileEntry(name=sf.name, tokens=0, description=f"Binary file ({ext})"))
        stats.files_skipped += 1

    # Categorize indexable files: changed vs cached
    changed_files: list[tuple[Path, str]] = []  # (path, hash)
    for fp in indexable_files:
        if change_detector.has_changed(fp):
            try:
                fhash = hash_file(fp)
            except OSError:
                stats.errors += 1
                continue
            changed_files.append((fp, fhash))
        else:
            cached = change_detector.get_cached(fp)
            if cached is not None:
                file_entries.append(
                    FileEntry(name=fp.name, tokens=cached.tokens, description=cached.summary)
                )
                stats.files_cached += 1

    # Summarize changed files via LLM
    if changed_files:
        summaries = await _summarize_changed_files(
            changed_files=changed_files,
            config=config,
            token_counter=token_counter,
            llm_service=llm_service,
            change_detector=change_detector,
            stats=stats,
        )
        file_entries.extend(summaries)

    # Build subdirectory entries from child .aindex files
    subdir_entries: list[DirEntry] = []
    try:
        subdirs = sorted(
            d for d in directory.iterdir() if d.is_dir() and not ignore_matcher.is_ignored(d)
        )
    except PermissionError:
        subdirs = []

    for subdir in subdirs:
        iandex_path = subdir / index_filename
        child_data = parse_iandex(iandex_path)
        if child_data is not None:
            subdir_entries.append(DirEntry(name=subdir.name, description=child_data.summary))
        else:
            subdir_entries.append(DirEntry(name=subdir.name, description="(not yet indexed)"))

    # Generate directory summary via LLM
    file_list = (
        "\n".join(f"- {fe.name} ({fe.tokens} tokens): {fe.description}" for fe in file_entries)
        or "(no files)"
    )
    subdir_list = (
        "\n".join(f"- {de.name}/: {de.description}" for de in subdir_entries)
        or "(no subdirectories)"
    )

    dir_name = directory.relative_to(root).as_posix() if directory != root else directory.name

    dir_summary = await llm_service.summarize_directory(
        DirectorySummaryRequest(path=directory, file_list=file_list, subdir_list=subdir_list)
    )
    stats.llm_calls += 1

    # Build and write .aindex
    iandex_data = IandexData(
        directory_name=dir_name,
        summary=dir_summary,
        files=file_entries,
        subdirectories=subdir_entries,
    )
    content = generate_iandex(iandex_data)

    if not dry_run:
        write_iandex(directory, content, filename=index_filename)


def _resolve_summary(
    result: FileSummaryResult,
    path: Path,
    change_detector: ChangeDetector,
) -> str:
    """Pick the best available summary after an LLM call.

    On success, returns the LLM summary. On error, falls back to the
    previously cached summary if one exists, otherwise returns a placeholder.
    """
    # TODO: Add a 'stale' flag or column to track files where we fell back to
    # a cached summary so we can detect persistent LLM failures and re-queue them.
    if not result.error:
        return result.summary
    cached = change_detector.get_cached(path)
    if cached is not None:
        logger.info("Using cached summary for %s (LLM error)", path)
        return cached.summary
    return "no summary generated"


async def _summarize_changed_files(
    *,
    changed_files: list[tuple[Path, str]],
    config: LexibraryConfig,
    token_counter: TokenCounter,
    llm_service: LLMService,
    change_detector: ChangeDetector,
    stats: CrawlStats,
) -> list[FileEntry]:
    """Read and summarize changed files, updating the cache.

    Batches small files; processes large files individually.
    """
    file_entries: list[FileEntry] = []

    # Read files and build summary requests
    small_requests: list[tuple[FileSummaryRequest, Path, str, int]] = []
    large_requests: list[tuple[FileSummaryRequest, Path, str, int]] = []

    for fp, fhash in changed_files:
        fc = read_file_for_indexing(fp, max_size_kb=config.crawl.max_file_size_kb)
        if fc is None:
            # Unreadable after hash — treat as skipped
            ext = fp.suffix.lstrip(".") or "unknown"
            desc = f"Binary file ({ext})"
            file_entries.append(FileEntry(name=fp.name, tokens=0, description=desc))
            stats.files_skipped += 1
            continue

        tokens = token_counter.count(fc.content)
        language = detect_language(fp.name)
        request = FileSummaryRequest(
            path=fp, content=fc.content, language=language, is_truncated=fc.is_truncated
        )

        if len(fc.content) < _BATCH_CHAR_THRESHOLD:
            small_requests.append((request, fp, fhash, tokens))
        else:
            large_requests.append((request, fp, fhash, tokens))

    # Batch small files
    batch_size = config.crawl.max_files_per_llm_batch
    for i in range(0, len(small_requests), batch_size):
        batch = small_requests[i : i + batch_size]
        requests = [r[0] for r in batch]
        results = await llm_service.summarize_files_batch(requests)
        stats.llm_calls += 1

        for (_req, fp, fhash, tokens), result in zip(batch, results, strict=True):
            summary = _resolve_summary(result, fp, change_detector)
            file_entries.append(FileEntry(name=fp.name, tokens=tokens, description=summary))
            if not result.error:
                change_detector.update(fp, fhash, tokens, summary)
            stats.files_summarized += 1

    # Individual large files
    for req, fp, fhash, tokens in large_requests:
        result = await llm_service.summarize_file(req)
        stats.llm_calls += 1
        summary = _resolve_summary(result, fp, change_detector)
        file_entries.append(FileEntry(name=fp.name, tokens=tokens, description=summary))
        if not result.error:
            change_detector.update(fp, fhash, tokens, summary)
        stats.files_summarized += 1

    return file_entries
