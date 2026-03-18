"""Tests for check_lookup_token_budget_exceeded validation check.

Covers: oversized design file detected, within-budget file not flagged,
no designs directory, registry presence.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.checks import check_lookup_token_budget_exceeded

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DESIGN_FILE_TEMPLATE = """\
---
description: Test module
updated_by: archivist
---

# {source_path}

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: {source_path}
source_hash: abcdef
design_hash: deadbeef
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""


def _setup_project(
    tmp_path: Path,
    *,
    lookup_total_tokens: int = 1200,
) -> tuple[Path, Path]:
    """Create a minimal project with config.yaml."""
    project_root = tmp_path
    lexibrary_dir = project_root / LEXIBRARY_DIR
    lexibrary_dir.mkdir()

    config = {"token_budgets": {"lookup_total_tokens": lookup_total_tokens}}
    (lexibrary_dir / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    return project_root, lexibrary_dir


def _write_design_file(
    lexibrary_dir: Path,
    rel_path: str,
    *,
    content: str | None = None,
    size_chars: int | None = None,
) -> Path:
    """Write a design file to .lexibrary/designs/<rel_path>."""
    design_path = lexibrary_dir / DESIGNS_DIR / rel_path
    design_path.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        design_path.write_text(content, encoding="utf-8")
    elif size_chars is not None:
        # Generate content of approximately the requested size
        design_path.write_text("x" * size_chars, encoding="utf-8")
    else:
        design_path.write_text(
            _DESIGN_FILE_TEMPLATE.format(source_path="src/example.py"),
            encoding="utf-8",
        )
    return design_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckLookupTokenBudgetExceeded:
    """Tests for check_lookup_token_budget_exceeded()."""

    def test_oversized_design_file_flagged(self, tmp_path: Path) -> None:
        """A design file exceeding lookup_total_tokens is flagged."""
        project_root, lexibrary_dir = _setup_project(tmp_path, lookup_total_tokens=100)
        # 500 chars ~= 125 tokens (chars/4), exceeds budget of 100
        _write_design_file(lexibrary_dir, "src/big.py.md", size_chars=500)

        issues = check_lookup_token_budget_exceeded(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "lookup_token_budget_exceeded"
        assert "125" in issue.message  # ~125 tokens
        assert "100" in issue.message  # budget
        assert "truncated" in issue.message
        assert issue.suggestion is not None

    def test_within_budget_not_flagged(self, tmp_path: Path) -> None:
        """A design file within the lookup budget produces no issues."""
        project_root, lexibrary_dir = _setup_project(tmp_path, lookup_total_tokens=1200)
        # Small file, well within budget
        _write_design_file(
            lexibrary_dir,
            "src/small.py.md",
            content=_DESIGN_FILE_TEMPLATE.format(source_path="src/small.py"),
        )

        issues = check_lookup_token_budget_exceeded(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_designs_directory(self, tmp_path: Path) -> None:
        """When .lexibrary/designs/ does not exist, returns empty list."""
        project_root, lexibrary_dir = _setup_project(tmp_path)
        # No designs directory created

        issues = check_lookup_token_budget_exceeded(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_files_only_oversized_flagged(self, tmp_path: Path) -> None:
        """Only design files exceeding the budget are flagged."""
        project_root, lexibrary_dir = _setup_project(tmp_path, lookup_total_tokens=100)
        # One large file (500 chars ~= 125 tokens > 100)
        _write_design_file(lexibrary_dir, "src/big.py.md", size_chars=500)
        # One small file (40 chars ~= 10 tokens < 100)
        _write_design_file(lexibrary_dir, "src/small.py.md", size_chars=40)

        issues = check_lookup_token_budget_exceeded(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "big.py.md" in issues[0].artifact


class TestLookupBudgetInAvailableChecks:
    """Verify lookup_token_budget_exceeded is registered."""

    def test_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "lookup_token_budget_exceeded" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["lookup_token_budget_exceeded"]
        assert check_fn is check_lookup_token_budget_exceeded
        assert severity == "info"
