# crawler/file_reader

**Summary:** Reads source files for LLM summarization, handling binary detection, encoding fallback (UTF-8 then Latin-1), and size-based truncation.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `FileContent` | `@dataclass` | Result: `path`, `content: str`, `encoding`, `size_bytes`, `is_truncated: bool` |
| `is_binary_file` | `(path: Path) -> bool` | Check for null bytes in first 8 KB; returns `True` on read error |
| `read_file_for_indexing` | `(path: Path, max_size_kb: int = 512) -> FileContent | None` | Read text file; returns `None` for binary or undecodable files |

## Dependents

- `lexibrarian.crawler.engine` — calls `read_file_for_indexing`

## Key Concepts

- Binary detection: null byte (`\x00`) in first 8 KB
- Encoding fallback: try UTF-8, then Latin-1; return `None` if both fail
- `is_truncated` flag is forwarded to the LLM prompt via `FileSummaryRequest`
