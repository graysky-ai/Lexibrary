"""Validation report models for library health checks.

Provides ValidationIssue, ValidationSummary, and ValidationReport dataclasses
with Rich rendering and JSON output support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from rich.console import Console
from rich.table import Table
from rich.text import Text

Severity = Literal["error", "warning", "info"]

# Rendering symbols per severity
_SEVERITY_SYMBOLS: dict[Severity, tuple[str, str]] = {
    "error": ("\u2717", "red"),  # cross mark
    "warning": ("\u26a0", "yellow"),  # warning triangle
    "info": ("\u2139", "blue"),  # info circle
}

# Display order: errors first, then warnings, then info
_SEVERITY_ORDER: list[Severity] = ["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding from a check."""

    severity: Severity
    check: str
    message: str
    artifact: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable dictionary."""
        return {
            "severity": self.severity,
            "check": self.check,
            "message": self.message,
            "artifact": self.artifact,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ValidationSummary:
    """Aggregate counts by severity."""

    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    @property
    def total(self) -> int:
        """Total number of issues across all severities."""
        return self.error_count + self.warning_count + self.info_count

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-serializable dictionary."""
        return {
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "total": self.total,
        }


@dataclass
class ValidationReport:
    """Aggregated validation results with rendering capabilities."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def summary(self) -> ValidationSummary:
        """Compute summary counts from the issue list."""
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        infos = sum(1 for i in self.issues if i.severity == "info")
        return ValidationSummary(
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
        )

    def has_errors(self) -> bool:
        """Return True if any error-severity issues exist."""
        return any(i.severity == "error" for i in self.issues)

    def has_warnings(self) -> bool:
        """Return True if any warning-severity issues exist."""
        return any(i.severity == "warning" for i in self.issues)

    def exit_code(self) -> int:
        """Return process exit code: 0=clean, 1=errors, 2=warnings only."""
        if self.has_errors():
            return 1
        if self.has_warnings():
            return 2
        return 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary of the full report."""
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": self.summary.to_dict(),
        }

    def render(self, console: Console) -> None:
        """Render the report to a Rich console, grouped by severity."""
        if not self.issues:
            console.print(Text("No validation issues found.", style="bold green"))
            return

        # Group issues by severity
        grouped: dict[Severity, list[ValidationIssue]] = {sev: [] for sev in _SEVERITY_ORDER}
        for issue in self.issues:
            grouped[issue.severity].append(issue)

        # Render each non-empty severity group
        for sev in _SEVERITY_ORDER:
            group = grouped[sev]
            if not group:
                continue

            symbol, color = _SEVERITY_SYMBOLS[sev]
            label = sev.capitalize() + "s"
            console.print()
            console.print(Text(f"{symbol} {label} ({len(group)})", style=f"bold {color}"))

            table = Table(show_header=True, show_lines=False, pad_edge=False)
            table.add_column("Check", style="dim")
            table.add_column("Artifact", style="cyan")
            table.add_column("Message")
            table.add_column("Suggestion", style="dim italic")

            for issue in group:
                table.add_row(
                    issue.check,
                    issue.artifact,
                    issue.message,
                    issue.suggestion or "-",
                )

            console.print(table)

        # Summary line
        s = self.summary
        console.print()
        parts: list[str] = []
        if s.error_count:
            parts.append(f"[red]{s.error_count} error(s)[/red]")
        if s.warning_count:
            parts.append(f"[yellow]{s.warning_count} warning(s)[/yellow]")
        if s.info_count:
            parts.append(f"[blue]{s.info_count} info[/blue]")
        console.print("Summary: " + ", ".join(parts))
