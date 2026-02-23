# iwh/parser

**Summary:** Parses `.iwh` files from markdown format with YAML frontmatter into `IWHFile` models. Returns `None` on any parse failure (missing file, invalid frontmatter, validation error).

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `parse_iwh` | `(path: Path) -> IWHFile \| None` | Parse an `.iwh` file; returns `None` if file missing, no valid frontmatter, or validation fails |

## Dependencies

- `lexibrarian.iwh.model` -- `IWHFile`
- `yaml` (PyYAML) -- frontmatter parsing
- `re` -- `_FRONTMATTER_RE` regex for `---` delimited frontmatter

## Dependents

- `lexibrarian.iwh.reader` -- `read_iwh()` and `consume_iwh()` delegate to `parse_iwh()`

## Key Concepts

- Uses the same `---`-delimited YAML frontmatter regex pattern as `stack/parser.py`
- Never raises exceptions -- all errors are caught and `None` is returned
- Body is everything after the closing `---` delimiter, stripped of leading/trailing newlines
