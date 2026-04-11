"""Data processing service with comprehensive validation pipeline.

Provides high-level data transformation and validation for the application.
Includes batch processing, schema validation, and error recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProcessingResult:
    """Result of a data processing operation."""

    success: bool
    records_processed: int = 0
    errors: list[str] = field(default_factory=list)


def validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> bool:
    """Validate data against a JSON-like schema definition."""
    for key, expected_type in schema.items():
        if key not in data:
            return False
        if not isinstance(data[key], expected_type):
            return False
    return True


def process_batch(
    records: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    strict: bool = False,
) -> ProcessingResult:
    """Process a batch of records with optional strict validation.

    Parameters
    ----------
    records:
        List of data records to process.
    schema:
        Schema definition for validation.
    strict:
        If True, abort on first validation error.

    Returns
    -------
    ProcessingResult
        Aggregated result of the batch processing operation.
    """
    result = ProcessingResult(success=True)
    for i, record in enumerate(records):
        if not validate_schema(record, schema):
            result.errors.append(f"Record {i} failed validation")
            if strict:
                result.success = False
                return result
        else:
            result.records_processed += 1
    return result


def load_data_file(path: Path) -> list[dict[str, Any]]:
    """Load data records from a JSON file."""
    import json

    with path.open() as f:
        return json.load(f)


def transform_records(
    records: list[dict[str, Any]],
    mapping: dict[str, str],
) -> list[dict[str, Any]]:
    """Apply field name mapping to a list of records."""
    return [{mapping.get(k, k): v for k, v in record.items()} for record in records]
