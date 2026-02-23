# crawler/discovery

**Summary:** Filesystem traversal that discovers all directories deepest-first and lists files in a directory, separating indexable from binary/ignored.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `discover_directories_bottom_up` | `(root: Path, ignore_matcher: IgnoreMatcher) -> list[Path]` | Walk tree via `os.walk`, prune ignored dirs, return sorted deepest-first |
| `list_directory_files` | `(directory: Path, ignore_matcher: IgnoreMatcher, binary_extensions: set[str]) -> tuple[list[Path], list[Path]]` | Split directory files into `(indexable, skipped)` |

## Dependencies

- `lexibrarian.ignore.matcher` — `IgnoreMatcher`

## Dependents

- `lexibrarian.crawler.engine` — calls both functions

## Key Concepts

- Deepest-first sort ensures child `.aindex` files exist before their parent is processed
- `dirnames` is pruned in-place so `os.walk` skips entire ignored subtrees
- `binary_extensions` filtering is by suffix, not binary content detection (for speed)
