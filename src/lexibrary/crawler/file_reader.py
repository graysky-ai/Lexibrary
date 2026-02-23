"""Binary detection and size-limited file reading for LLM summarization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_BINARY_CHECK_SIZE = 8192


@dataclass
class FileContent:
    """Content read from a file for indexing."""

    path: Path
    content: str
    encoding: str
    size_bytes: int
    is_truncated: bool


def is_binary_file(path: Path) -> bool:
    """Detect if a file is binary by checking for null bytes in the first 8KB.

    Returns True for binary files or files that cannot be read.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_CHECK_SIZE)
        return b"\x00" in chunk
    except OSError:
        return True


def read_file_for_indexing(
    path: Path,
    max_size_kb: int = 512,
) -> FileContent | None:
    """Read a text file for LLM summarization.

    Detects binary files, handles UTF-8 and Latin-1 encodings,
    and truncates files exceeding the size limit.

    Returns None for binary or undecodable files.
    """
    if is_binary_file(path):
        return None

    max_bytes = max_size_kb * 1024

    try:
        raw = path.read_bytes()
    except OSError:
        return None

    size_bytes = len(raw)
    is_truncated = size_bytes > max_bytes
    if is_truncated:
        raw = raw[:max_bytes]

    # Try UTF-8 first, then Latin-1 fallback
    for encoding in ("utf-8", "latin-1"):
        try:
            content = raw.decode(encoding)
            return FileContent(
                path=path,
                content=content,
                encoding=encoding,
                size_bytes=size_bytes,
                is_truncated=is_truncated,
            )
        except (UnicodeDecodeError, ValueError):
            continue

    return None
