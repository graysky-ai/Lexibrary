"""Structured error collection for pipeline runs."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class ErrorRecord:
    """A single error encountered during a pipeline run."""

    timestamp: str
    phase: str
    path: str | None
    error_type: str
    message: str
    traceback: str | None


@dataclass
class ErrorSummary:
    """Aggregated error collection for a pipeline run."""

    records: list[ErrorRecord] = field(default_factory=list)

    def add(self, phase: str, error: Exception, path: str | None = None) -> None:
        """Capture an error with metadata."""
        self.records.append(
            ErrorRecord(
                timestamp=datetime.now(UTC).isoformat(),
                phase=phase,
                path=path,
                error_type=type(error).__name__,
                message=str(error),
                traceback=traceback.format_exception(error)[-1].strip()
                if error.__traceback__
                else None,
            )
        )

    @property
    def count(self) -> int:
        return len(self.records)

    def by_phase(self) -> dict[str, list[ErrorRecord]]:
        """Group errors by phase for reporting."""
        grouped: dict[str, list[ErrorRecord]] = {}
        for rec in self.records:
            grouped.setdefault(rec.phase, []).append(rec)
        return grouped

    def has_errors(self) -> bool:
        return self.count > 0


def format_error_summary(summary: ErrorSummary) -> None:
    """Print a grouped error summary to stderr."""
    from lexibrary.cli._output import error, info  # noqa: PLC0415

    if not summary.has_errors():
        return

    info("")
    error(f"Errors ({summary.count}):")

    for phase, records in summary.by_phase().items():
        info(f"\n  {phase} -- {len(records)} error(s)")
        for rec in records:
            path_str = f" {rec.path}" if rec.path else ""
            info(f"    [{rec.error_type}]{path_str}: {rec.message}")
