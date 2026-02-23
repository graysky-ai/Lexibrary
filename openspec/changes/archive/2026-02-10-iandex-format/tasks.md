## 1. Data Models

- [x] 1.1 Create `src/lexibrary/indexer/__init__.py` with `FileEntry`, `DirEntry`, and `IandexData` dataclasses
- [x] 1.2 Create `tests/test_indexer/__init__.py` (empty, makes it a test package)

## 2. Generator

- [x] 2.1 Create `src/lexibrary/indexer/generator.py` with `generate_iandex()` function
- [x] 2.2 Implement H1 header, summary paragraph, and section structure with blank line separation
- [x] 2.3 Implement Files table with backtick-wrapped names, token counts, descriptions
- [x] 2.4 Implement Subdirectories table with backtick-wrapped names (enforce trailing `/`) and descriptions
- [x] 2.5 Implement case-insensitive alphabetical sorting for both files and subdirectories
- [x] 2.6 Implement `(none)` marker for empty sections
- [x] 2.7 Implement pipe character escaping (`|` → `\|`) in descriptions
- [x] 2.8 Ensure output ends with trailing newline
- [x] 2.9 Create `tests/test_indexer/test_generator.py` with tests: basic generation, no files, no subdirs, empty, sorting, trailing slash, trailing newline, pipe escaping

## 3. Writer

- [x] 3.1 Create `src/lexibrary/indexer/writer.py` with `write_iandex()` function
- [x] 3.2 Implement atomic write via temp-file-then-rename with `os.replace()`
- [x] 3.3 Implement cleanup of temp file on failure
- [x] 3.4 Implement UTF-8 encoding and custom filename support
- [x] 3.5 Create `tests/test_indexer/test_writer.py` with tests: file creation, content match, overwrite, atomic (no partial files on failure)

## 4. Parser

- [x] 4.1 Create `src/lexibrary/indexer/parser.py` with `parse_iandex()` function
- [x] 4.2 Implement H1 parsing for directory name
- [x] 4.3 Implement summary extraction (lines between H1 and first H2, joined with spaces)
- [x] 4.4 Implement Files table row parsing via regex
- [x] 4.5 Implement Subdirectories table row parsing via regex
- [x] 4.6 Implement `None` returns for missing, empty, and malformed files
- [x] 4.7 Implement `get_cached_file_entries()` helper function
- [x] 4.8 Create `tests/test_indexer/test_parser.py` with tests: basic parse, nonexistent file, malformed, empty sections, cached entries

## 5. Round-Trip Verification

- [x] 5.1 Create `tests/test_indexer/test_roundtrip.py` with tests: round-trip with data, round-trip empty, round-trip Unicode
- [x] 5.2 Run full test suite: `uv run pytest tests/test_indexer -v` — all tests pass
