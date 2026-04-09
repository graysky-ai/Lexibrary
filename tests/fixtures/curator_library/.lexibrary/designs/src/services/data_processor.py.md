---
description: Provides high-level data transformation and validation for the application, including batch processing, schema validation, and error recovery.
id: DS-010
updated_by: archivist
status: active
---

# src/services/data_processor.py

## Interface Contract

```python
@dataclass
class ProcessingResult:
    """Result of a data processing operation."""
    success: bool
    records_processed: int = 0
    errors: list[str] = field(default_factory=list)

def validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> bool:
    """Validate data against a JSON-like schema definition.

    Performs type-level validation of each field in the provided data dictionary
    against a schema that maps field names to expected Python types. This is a
    lightweight alternative to full JSON Schema validation, suitable for quick
    in-process checks where the overhead of a full schema validator is not
    warranted.

    The function checks two conditions per schema entry: (1) the key exists in
    the data dictionary, and (2) the value is an instance of the expected type.
    If either condition fails for any entry, the function returns False
    immediately without checking the remaining fields.

    Parameters
    ----------
    data : dict[str, Any]
        The data dictionary to validate. Extra keys not present in the schema
        are silently ignored (open-world assumption).
    schema : dict[str, Any]
        A mapping from field name to expected Python type (e.g. str, int,
        list). The schema does not support nested validation -- only top-level
        fields are checked.

    Returns
    -------
    bool
        True if all schema entries are satisfied, False otherwise.

    Examples
    --------
    >>> validate_schema({"name": "Alice", "age": 30}, {"name": str, "age": int})
    True
    >>> validate_schema({"name": "Alice"}, {"name": str, "age": int})
    False
    """
    ...

def process_batch(
    records: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    strict: bool = False,
) -> ProcessingResult:
    """Process a batch of records with optional strict validation.

    Iterates over the provided records and validates each against the schema.
    In strict mode, processing halts on the first validation failure and returns
    a result with success=False. In permissive mode (the default), invalid
    records are logged as errors but processing continues.

    The function uses ``validate_schema()`` internally for per-record checks.
    The result's ``records_processed`` field counts only records that passed
    validation; the ``errors`` field collects human-readable descriptions of
    each failure.

    Parameters
    ----------
    records : list[dict[str, Any]]
        The batch of data records to process.
    schema : dict[str, Any]
        Schema definition for validation (see ``validate_schema``).
    strict : bool
        If True, abort on first validation error and return immediately.
        Default is False (permissive mode).

    Returns
    -------
    ProcessingResult
        Aggregated result with counts and error details.

    Raises
    ------
    TypeError
        If records is not a list or schema is not a dict.

    Notes
    -----
    This function is designed for moderate batch sizes (up to ~100k records).
    For larger datasets, consider streaming or chunked approaches.
    """
    ...

def load_data_file(path: Path) -> list[dict[str, Any]]:
    """Load data records from a JSON file.

    Opens the file at the given path and deserializes the JSON content into a
    list of dictionaries. The file must contain a JSON array at the top level.

    Parameters
    ----------
    path : Path
        Path to the JSON data file.

    Returns
    -------
    list[dict[str, Any]]
        The deserialized records.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    json.JSONDecodeError
        If the file contents are not valid JSON.
    """
    ...

def transform_records(
    records: list[dict[str, Any]],
    mapping: dict[str, str],
) -> list[dict[str, Any]]:
    """Apply field name mapping to a list of records.

    Creates new dictionaries with keys renamed according to the provided
    mapping. Keys not present in the mapping are passed through unchanged.

    Parameters
    ----------
    records : list[dict[str, Any]]
        Input records.
    mapping : dict[str, str]
        Old-name -> new-name mapping.

    Returns
    -------
    list[dict[str, Any]]
        Records with renamed fields.
    """
    ...
```

## Dependencies

- `json` (stdlib) -- used by ``load_data_file()`` for JSON deserialization
- `pathlib.Path` (stdlib) -- file path handling in ``load_data_file()``
- `dataclasses` (stdlib) -- ``ProcessingResult`` dataclass definition

## Dependents

*(see `lexi lookup` for live reverse references)*

- `src/services/report_generator.py` -- imports ``ProcessingResult`` and ``process_batch()``
- `src/api/endpoints.py` -- calls ``process_batch()`` with request data
- `src/cli/data_commands.py` -- calls ``load_data_file()`` and ``transform_records()``

## Design Rationale

The data processor module was designed with several architectural goals in mind.

### Separation of Concerns

Validation, transformation, and I/O are implemented as separate functions rather
than bundled into a single class. This allows callers to compose only the steps
they need. For example, a CLI tool might call ``load_data_file`` and
``transform_records`` without ``validate_schema``, while an API endpoint might
validate inline without loading from disk.

### Strict vs. Permissive Processing

The ``strict`` parameter on ``process_batch`` addresses two common deployment
scenarios. In production pipelines, permissive mode collects all errors so
operators can fix them in a single pass. In automated testing or CI, strict mode
fails fast to surface the first issue.

### Error Recovery Strategy

``ProcessingResult`` captures errors as human-readable strings rather than
exception objects. This choice was made because:

1. Error details often need to be serialized to JSON for API responses or log
   aggregation.
2. Callers rarely need to programmatically inspect error types -- they just need
   to know which records failed and why.
3. String-based errors are simpler to test in assertions.

The trade-off is that structured error metadata (e.g., line number, field name)
must be encoded into the string. A future iteration could introduce an ``Error``
dataclass to provide both structured data and a human-readable message.

### Schema Validation Approach

The ``validate_schema`` function uses Python's ``isinstance`` rather than a full
JSON Schema library. This was a deliberate trade-off for several reasons:

- **Performance**: ``isinstance`` checks are orders of magnitude faster than
  JSON Schema validation for simple type checks.
- **Simplicity**: No external dependency is needed.
- **Sufficiency**: The application's schemas are flat (no nested structures),
  making ``isinstance`` adequate.

If nested validation becomes necessary, the function should be replaced with a
proper JSON Schema validator (e.g., ``jsonschema`` or Pydantic model
validation).

### Batch Processing Performance

The current implementation processes records sequentially in a Python loop.
Profiling shows this is adequate for batches up to approximately 100,000
records. Beyond that threshold, the following optimizations should be
considered:

1. **Chunked processing**: Split the batch into chunks and process each in a
   separate thread or process.
2. **Streaming validation**: Validate records as they are read from disk rather
   than loading the entire batch into memory.
3. **Vectorized operations**: If records can be represented as columnar data
   (e.g., pandas DataFrame), type checks can be vectorized.

### Transformation Pipeline

The ``transform_records`` function supports only field renaming. More complex
transformations (type coercion, default values, computed fields) are left to
the caller. This keeps the function simple and composable -- callers can chain
multiple ``transform_records`` calls or combine it with list comprehensions.

### Testing Strategy

The module is designed for easy unit testing:

- ``validate_schema`` is a pure function with no side effects.
- ``process_batch`` is deterministic given the same inputs.
- ``load_data_file`` is the only function with I/O, and it uses ``Path.open``
  which can be easily mocked or pointed at temporary files.
- ``transform_records`` is a pure function that returns new dictionaries.

### Future Considerations

Several enhancements are planned for future iterations:

1. **Async batch processing**: An ``async_process_batch`` variant that yields
   results incrementally, suitable for streaming APIs.
2. **Schema evolution**: Support for versioned schemas with automatic migration
   of records from older schema versions.
3. **Audit trail**: Recording which transformations were applied to each record,
   enabling rollback and compliance reporting.
4. **Custom validators**: A plugin mechanism for registering domain-specific
   validation functions beyond type checking.
5. **Error severity levels**: Classifying validation errors as warnings (proceed)
   vs. errors (skip record) vs. critical (abort batch).

## Historical Context

This module was introduced in sprint 12 as a replacement for the previous
``data_pipeline.py`` monolith. The refactoring split the monolith into three
focused modules: ``data_processor.py`` (validation and batch processing),
``data_io.py`` (file and database I/O), and ``data_transform.py`` (complex
transformations). The schema validation was previously handled by a custom
``SchemaChecker`` class that combined validation and error formatting, making
it difficult to test in isolation.

The ``strict`` parameter was added in sprint 15 after a production incident
where a malformed batch of 50,000 records was fully processed before the first
error was detected. The investigation revealed that 47,000 records had missing
required fields, and the permissive-only mode produced a 47,000-line error log
that was impractical to review.

## Cross-Cutting Concerns

### Logging

The module does not log directly. Callers are expected to log
``ProcessingResult.errors`` at the appropriate level. This avoids coupling the
module to a specific logging configuration.

### Metrics

No metrics are emitted by this module. The caller should record batch sizes,
processing durations, and error rates using the application's metrics framework.

### Security

The ``validate_schema`` function does not sanitize input values -- it only
checks types. Callers must perform their own sanitization (e.g., HTML escaping,
SQL parameterization) before using validated data in security-sensitive
contexts.

### Concurrency

All functions are thread-safe. ``validate_schema`` and ``transform_records`` are
pure functions. ``process_batch`` creates new ``ProcessingResult`` instances per
call. ``load_data_file`` uses ``Path.open`` which acquires a file descriptor
per call.

## Insights

- The design prioritises composition over inheritance: small, focused functions
  that callers chain together.
- The error model (string-based) is intentionally simple but may need
  structured errors if downstream systems require machine-readable error codes.
- Performance profiling (sprint 14) confirmed the sequential loop is not a
  bottleneck for current usage patterns (<10,000 records per batch in
  production).
- The module deliberately avoids external dependencies to keep the import graph
  shallow and test setup minimal.
- Schema validation uses an open-world assumption (extra keys are allowed),
  which matches the application's forward-compatibility requirements for API
  payloads.
- The ``transform_records`` function creates new dictionaries rather than
  mutating in place, which prevents subtle aliasing bugs when the same record
  list is used in multiple contexts.

## Implementation Notes

### Record Iteration Pattern

The core iteration pattern in ``process_batch`` uses ``enumerate`` to track
record indices for error reporting. This is preferred over manual index
management because it is more Pythonic and less error-prone. The pattern looks
like:

```python
for i, record in enumerate(records):
    if not validate_schema(record, schema):
        result.errors.append(f"Record {i} failed validation")
```

One subtlety is that the index is 0-based, which matches how the records are
stored internally. Callers who display these indices to users should add 1 for
human-friendly numbering.

### JSON Loading Considerations

The ``load_data_file`` function uses ``json.load`` (streaming decoder) rather
than ``json.loads`` (string decoder) for memory efficiency. For files larger
than available RAM, callers should use ``ijson`` or a similar streaming JSON
parser instead of this function.

The function does not validate the structure of the loaded data -- it assumes
the file contains a JSON array. A future version could add a ``validate``
parameter that checks the top-level structure before returning.

### Field Mapping Edge Cases

The ``transform_records`` function handles several edge cases:

1. **Empty mapping**: Returns copies of the original records with no changes.
2. **Overlapping keys**: If a mapping has ``{"a": "b", "b": "c"}``, the
   function processes each key independently. The original ``"a"`` becomes
   ``"b"`` and the original ``"b"`` becomes ``"c"``.
3. **Missing source keys**: If a mapping references a key not in a record,
   that mapping entry is silently ignored for that record.
4. **None values**: None values are preserved during transformation.

### Error Message Format

Error messages in ``ProcessingResult.errors`` follow a consistent format:
``"Record {index} failed validation"``. This format was chosen because:

- It identifies the failing record by position.
- It is parseable by log aggregation tools that use regex extraction.
- It is human-readable for manual debugging.

A future enhancement could include the specific field(s) that failed validation
to speed up debugging. This would require ``validate_schema`` to return error
details rather than a boolean.

## Performance Benchmarks

Performance testing conducted in sprint 14 produced the following results on a
standard development machine (M1 MacBook Pro, 16 GB RAM):

| Batch Size | Duration (ms) | Records/sec | Memory (MB) |
|-----------|--------------|-------------|-------------|
| 100       | 0.3          | 333,333     | 0.1         |
| 1,000     | 2.8          | 357,142     | 0.8         |
| 10,000    | 27.5         | 363,636     | 7.6         |
| 50,000    | 138.2        | 361,836     | 38.1        |
| 100,000   | 281.4        | 355,366     | 76.2        |

Key observations:

- Throughput is approximately linear with batch size, indicating no quadratic
  behavior in the current implementation.
- Memory usage scales linearly with batch size because ``ProcessingResult``
  stores error strings for each failing record.
- The approximate tokenizer estimates match actual tiktoken counts within 15%
  for this type of content.

### Strict Mode Performance Impact

Strict mode (``strict=True``) can significantly reduce processing time when
errors occur early in the batch, because processing halts on the first failure.
In the worst case (error in the last record), strict mode has the same
performance as permissive mode. In the best case (error in the first record),
strict mode returns in microseconds regardless of batch size.

## Migration Guide

If migrating from the legacy ``DataPipeline`` class:

1. Replace ``DataPipeline(schema=s).process(records)`` with
   ``process_batch(records, s)``.
2. Replace ``DataPipeline(schema=s).strict_process(records)`` with
   ``process_batch(records, s, strict=True)``.
3. Replace ``DataPipeline.load(path)`` with ``load_data_file(path)``.
4. Replace ``DataPipeline(mapping=m).transform(records)`` with
   ``transform_records(records, m)``.
5. Error handling: The old ``DataPipelineError`` exception is replaced by the
   ``ProcessingResult.errors`` list. Update exception handlers to check the
   result object instead.

## API Versioning

This module follows semantic versioning within the internal API contract:

- **v1.0** (sprint 12): Initial implementation with ``validate_schema``,
  ``process_batch``, and ``load_data_file``.
- **v1.1** (sprint 13): Added ``transform_records`` for field renaming.
- **v1.2** (sprint 15): Added ``strict`` parameter to ``process_batch``.
- **v2.0** (planned): Structured error objects in ``ProcessingResult``.

## Wikilinks

- [[Authentication]]
- [[DataProcessing]]

## Tags

- services
- data
- validation
- batch-processing

<!-- lexibrary:meta
source: src/services/data_processor.py
source_hash: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
interface_hash: b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3
design_hash: c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
generated: 2026-04-01T12:00:00.000000
generator: lexibrary-v2
-->
