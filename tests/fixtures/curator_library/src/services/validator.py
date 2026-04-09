"""Input validation service for the application.

Provides schema-based validation, field sanitization, and error
reporting for incoming data records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationError:
    """A single validation failure."""

    field: str
    message: str
    code: str = "invalid"


@dataclass
class ValidationResult:
    """Aggregated result of a validation pass."""

    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)


# TODO: add validation for nested objects -- only top-level fields are checked
# This is stale because validate_record already handles nested dicts below.


def validate_record(
    record: dict[str, Any],
    schema: dict[str, type],
    *,
    allow_extra: bool = True,
) -> ValidationResult:
    """Validate a single data record against a type schema.

    Parameters
    ----------
    record:
        The data record to validate.
    schema:
        Mapping of field names to expected types.
    allow_extra:
        If False, extra fields not in schema are rejected.

    Returns
    -------
    ValidationResult
        Validation outcome with error details.
    """
    result = ValidationResult()

    # Check required fields
    for field_name, expected_type in schema.items():
        if field_name not in record:
            result.valid = False
            result.errors.append(
                ValidationError(
                    field=field_name,
                    message=f"Missing required field: {field_name}",
                    code="missing_field",
                )
            )
            continue

        value = record[field_name]

        # Handle nested dict validation
        if isinstance(expected_type, dict) and isinstance(value, dict):
            nested_result = validate_record(value, expected_type)
            if not nested_result.valid:
                result.valid = False
                for err in nested_result.errors:
                    result.errors.append(
                        ValidationError(
                            field=f"{field_name}.{err.field}",
                            message=err.message,
                            code=err.code,
                        )
                    )
            continue

        if not isinstance(value, expected_type):
            result.valid = False
            result.errors.append(
                ValidationError(
                    field=field_name,
                    message=(
                        f"Expected {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    ),
                    code="wrong_type",
                )
            )

    # Check for extra fields
    if not allow_extra:
        extra = set(record.keys()) - set(schema.keys())
        for field_name in sorted(extra):
            result.valid = False
            result.errors.append(
                ValidationError(
                    field=field_name,
                    message=f"Unexpected field: {field_name}",
                    code="extra_field",
                )
            )

    return result


def sanitize_string(value: str, *, max_length: int = 1000) -> str:
    """Strip dangerous characters and enforce length limits."""
    # Remove null bytes
    cleaned = value.replace("\x00", "")
    # Truncate to max length
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned.strip()


# FIXME: this function silently drops records with encoding errors
# This is a current/valid FIXME -- the function does indeed drop them.
def decode_records(raw_data: bytes) -> list[dict[str, Any]]:
    """Decode raw bytes into a list of data records.

    Records with encoding errors are silently dropped.
    """
    import json

    try:
        text = raw_data.decode("utf-8", errors="ignore")
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []


# TODO(shanngray): implement rate limiting for batch validation calls
# This is a valid current TODO -- rate limiting is not yet implemented.
def validate_batch(
    records: list[dict[str, Any]],
    schema: dict[str, type],
) -> list[ValidationResult]:
    """Validate a batch of records and return per-record results."""
    return [validate_record(r, schema) for r in records]
