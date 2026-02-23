"""Unit tests for warning-severity validation checks.

Tests check_hash_freshness, check_token_budgets, check_orphan_concepts,
and check_deprecated_concept_usage.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.utils.hashing import hash_file
from lexibrary.validator.checks import (
    check_deprecated_concept_usage,
    check_hash_freshness,
    check_orphan_concepts,
    check_token_budgets,
)

# ---------------------------------------------------------------------------
# Helpers for writing test fixtures
# ---------------------------------------------------------------------------

_DESIGN_FILE_TEMPLATE = """\
---
description: {description}
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

## Wikilinks

{wikilinks}

<!-- lexibrary:meta
source: {source_path}
source_hash: {source_hash}
design_hash: deadbeef
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

_CONCEPT_FILE_TEMPLATE = """\
---
title: {title}
aliases: {aliases}
tags: {tags}
status: {status}
{superseded_line}
---

{body}
"""


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    source_hash: str = "abc123",
    description: str = "Test design file",
    wikilinks: str = "(none)",
) -> Path:
    """Write a design file to the expected mirror path."""
    design_path = lexibrary_dir / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(
        _DESIGN_FILE_TEMPLATE.format(
            description=description,
            source_path=source_path,
            source_hash=source_hash,
            wikilinks=wikilinks,
        ),
        encoding="utf-8",
    )
    return design_path


def _write_concept_file(
    lexibrary_dir: Path,
    title: str,
    *,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "active",
    superseded_by: str | None = None,
    body: str = "A concept description.",
) -> Path:
    """Write a concept file under .lexibrary/concepts/."""
    concepts_dir = lexibrary_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    aliases_yaml = "[" + ", ".join(aliases or []) + "]"
    tags_yaml = "[" + ", ".join(tags or ["general"]) + "]"
    superseded_line = f"superseded_by: {superseded_by}" if superseded_by else ""

    filename = title.lower().replace(" ", "-") + ".md"
    concept_path = concepts_dir / filename
    concept_path.write_text(
        _CONCEPT_FILE_TEMPLATE.format(
            title=title,
            aliases=aliases_yaml,
            tags=tags_yaml,
            status=status,
            superseded_line=superseded_line,
            body=body,
        ),
        encoding="utf-8",
    )
    return concept_path


def _write_config(project_root: Path, **overrides: object) -> None:
    """Write a minimal config.yaml."""
    config_dir = project_root / ".lexibrary"
    config_dir.mkdir(parents=True, exist_ok=True)
    lines = ["scope_root: ."]
    if "token_budgets" in overrides:
        budgets = overrides["token_budgets"]
        lines.append("token_budgets:")
        for key, val in budgets.items():  # type: ignore[union-attr]
            lines.append(f"  {key}: {val}")
    config_path = config_dir / "config.yaml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# check_hash_freshness
# ---------------------------------------------------------------------------


class TestCheckHashFreshness:
    """Tests for check_hash_freshness."""

    def test_fresh_hashes_pass(self, tmp_path: Path) -> None:
        """When source_hash matches current SHA-256, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "fresh.py"
        source_file.write_text("def hello(): pass\n", encoding="utf-8")

        # Compute current hash and write matching design file
        current_hash = hash_file(source_file)
        _write_design_file(
            lexibrary_dir,
            "src/fresh.py",
            source_hash=current_hash,
        )

        issues = check_hash_freshness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_stale_hash_produces_warning(self, tmp_path: Path) -> None:
        """When source_hash doesn't match, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "stale.py"
        source_file.write_text("def updated(): pass\n", encoding="utf-8")

        # Write design file with wrong hash
        _write_design_file(
            lexibrary_dir,
            "src/stale.py",
            source_hash="old_stale_hash_value",
        )

        issues = check_hash_freshness(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "hash_freshness"
        assert "stale" in issue.message.lower()
        assert "lexictl update" in issue.suggestion.lower()

    def test_missing_source_skipped(self, tmp_path: Path) -> None:
        """When source file doesn't exist, hash freshness is not checked."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Design file exists but source does not
        _write_design_file(
            lexibrary_dir,
            "src/gone.py",
            source_hash="whatever",
        )

        issues = check_hash_freshness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_design_files(self, tmp_path: Path) -> None:
        """No design files means no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_hash_freshness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_files_mixed(self, tmp_path: Path) -> None:
        """Multiple design files: fresh ones pass, stale ones warn."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()

        # Fresh file
        fresh = src_dir / "fresh.py"
        fresh.write_text("pass\n", encoding="utf-8")
        _write_design_file(lexibrary_dir, "src/fresh.py", source_hash=hash_file(fresh))

        # Stale file
        stale = src_dir / "stale.py"
        stale.write_text("changed\n", encoding="utf-8")
        _write_design_file(lexibrary_dir, "src/stale.py", source_hash="wrong_hash")

        issues = check_hash_freshness(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "stale.py" in issues[0].artifact

    def test_no_src_dir(self, tmp_path: Path) -> None:
        """If .lexibrary/src/ doesn't exist, no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_hash_freshness(project_root, lexibrary_dir)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# check_token_budgets
# ---------------------------------------------------------------------------


class TestCheckTokenBudgets:
    """Tests for check_token_budgets."""

    def test_within_budget_passes(self, tmp_path: Path) -> None:
        """Artifacts within budget produce no warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create a small design file (well within default 400 token limit)
        _write_design_file(lexibrary_dir, "src/small.py")

        issues = check_token_budgets(project_root, lexibrary_dir)
        # Filter to design file issues only -- START_HERE etc. not created
        design_issues = [i for i in issues if "src/" in i.artifact]
        assert len(design_issues) == 0

    def test_over_budget_warns(self, tmp_path: Path) -> None:
        """Artifacts exceeding budget produce warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        # Set very low budget so our template exceeds it
        _write_config(
            project_root,
            token_budgets={"design_file_tokens": 10},
        )

        # Create a design file (template has ~100+ tokens)
        _write_design_file(lexibrary_dir, "src/big.py")

        issues = check_token_budgets(project_root, lexibrary_dir)
        design_issues = [i for i in issues if "src/" in i.artifact]
        assert len(design_issues) == 1
        issue = design_issues[0]
        assert issue.severity == "warning"
        assert issue.check == "token_budgets"
        assert "Over budget" in issue.message
        assert "limit 10" in issue.message

    def test_start_here_over_budget(self, tmp_path: Path) -> None:
        """START_HERE.md over budget produces warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(
            project_root,
            token_budgets={"start_here_tokens": 5},
        )

        start_here = lexibrary_dir / "START_HERE.md"
        start_here.write_text(
            "A sufficiently long start here document for testing.", encoding="utf-8"
        )

        issues = check_token_budgets(project_root, lexibrary_dir)
        start_issues = [i for i in issues if i.artifact == "START_HERE.md"]
        assert len(start_issues) == 1
        assert start_issues[0].severity == "warning"

    def test_concept_over_budget(self, tmp_path: Path) -> None:
        """Concept files over budget produce warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(
            project_root,
            token_budgets={"concept_file_tokens": 5},
        )

        _write_concept_file(
            lexibrary_dir,
            "Big Concept",
            body="This is a very long concept body that should exceed the budget.",
        )

        issues = check_token_budgets(project_root, lexibrary_dir)
        concept_issues = [i for i in issues if "concepts/" in i.artifact]
        assert len(concept_issues) == 1
        assert concept_issues[0].severity == "warning"

    def test_aindex_over_budget(self, tmp_path: Path) -> None:
        """Aindex files over budget produce warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(
            project_root,
            token_budgets={"aindex_tokens": 5},
        )

        aindex_dir = lexibrary_dir / "src"
        aindex_dir.mkdir(parents=True)
        aindex_file = aindex_dir / ".aindex"
        aindex_file.write_text(
            "A long aindex file content that exceeds the budget limit.",
            encoding="utf-8",
        )

        issues = check_token_budgets(project_root, lexibrary_dir)
        aindex_issues = [i for i in issues if ".aindex" in i.artifact]
        assert len(aindex_issues) == 1
        assert aindex_issues[0].severity == "warning"

    def test_empty_lexibrary(self, tmp_path: Path) -> None:
        """Empty .lexibrary produces no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        issues = check_token_budgets(project_root, lexibrary_dir)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# check_orphan_concepts
# ---------------------------------------------------------------------------


class TestCheckOrphanConcepts:
    """Tests for check_orphan_concepts."""

    def test_referenced_concept_passes(self, tmp_path: Path) -> None:
        """Concepts referenced by wikilinks produce no warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a concept
        _write_concept_file(lexibrary_dir, "Authentication")

        # Create a design file that references the concept
        _write_design_file(
            lexibrary_dir,
            "src/auth.py",
            wikilinks="- [[Authentication]]",
        )

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_orphan_concept_warns(self, tmp_path: Path) -> None:
        """Concepts with zero inbound references produce warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a concept with no references anywhere
        _write_concept_file(lexibrary_dir, "Orphan Concept")

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "orphan_concepts"
        assert "no inbound" in issue.message.lower()
        assert "[[Orphan Concept]]" in issue.suggestion

    def test_alias_reference_counts(self, tmp_path: Path) -> None:
        """Referencing a concept by alias prevents orphan warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a concept with an alias
        _write_concept_file(lexibrary_dir, "Authentication", aliases=["Auth", "AuthN"])

        # Reference by alias in a design file
        _write_design_file(
            lexibrary_dir,
            "src/login.py",
            wikilinks="- [[Auth]]",
        )

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_stack_post_reference_counts(self, tmp_path: Path) -> None:
        """Wikilinks in Stack posts count as inbound references."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create concept
        _write_concept_file(lexibrary_dir, "Caching")

        # Create a stack post with a wikilink
        stack_dir = lexibrary_dir / "stack"
        stack_dir.mkdir()
        post = stack_dir / "Q-001.md"
        post.write_text(
            "---\nid: Q-001\ntitle: Cache question\ntags:\n  - test\n"
            "status: open\ncreated: 2026-01-01\nauthor: tester\n---\n\n"
            "## Problem\n\nRelated to [[Caching]].\n",
            encoding="utf-8",
        )

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_cross_reference_between_concepts(self, tmp_path: Path) -> None:
        """Wikilinks between concept files count as inbound references."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Two concepts that reference each other
        _write_concept_file(
            lexibrary_dir,
            "Authorization",
            body="Related to [[Authentication]].",
        )
        _write_concept_file(
            lexibrary_dir,
            "Authentication",
            body="See also [[Authorization]].",
        )

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_concepts_dir(self, tmp_path: Path) -> None:
        """No concepts directory means no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_orphans(self, tmp_path: Path) -> None:
        """Multiple orphan concepts each produce a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(lexibrary_dir, "Orphan A")
        _write_concept_file(lexibrary_dir, "Orphan B")

        issues = check_orphan_concepts(project_root, lexibrary_dir)
        assert len(issues) == 2
        names = {i.artifact for i in issues}
        assert "concepts/Orphan A" in names
        assert "concepts/Orphan B" in names


# ---------------------------------------------------------------------------
# check_deprecated_concept_usage
# ---------------------------------------------------------------------------


class TestCheckDeprecatedConceptUsage:
    """Tests for check_deprecated_concept_usage."""

    def test_active_concept_no_warning(self, tmp_path: Path) -> None:
        """References to active concepts produce no warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(lexibrary_dir, "Active Concept", status="active")
        _write_design_file(
            lexibrary_dir,
            "src/app.py",
            wikilinks="- [[Active Concept]]",
        )

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_deprecated_usage_warns(self, tmp_path: Path) -> None:
        """References to deprecated concepts produce warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "Old Pattern",
            status="deprecated",
        )
        _write_design_file(
            lexibrary_dir,
            "src/legacy.py",
            wikilinks="- [[Old Pattern]]",
        )

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "deprecated_concept_usage"
        assert "[[Old Pattern]]" in issue.message
        assert "Remove reference" in issue.suggestion

    def test_deprecated_with_superseded_by(self, tmp_path: Path) -> None:
        """Deprecated concept with superseded_by shows replacement in suggestion."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "Old Auth",
            status="deprecated",
            superseded_by="New Auth",
        )
        _write_concept_file(
            lexibrary_dir,
            "New Auth",
            status="active",
        )
        _write_design_file(
            lexibrary_dir,
            "src/login.py",
            wikilinks="- [[Old Auth]]",
        )

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "[[New Auth]]" in issues[0].suggestion

    def test_deprecated_alias_detected(self, tmp_path: Path) -> None:
        """Referencing a deprecated concept by alias also triggers a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "Legacy Logging",
            aliases=["OldLog"],
            status="deprecated",
            superseded_by="Structured Logging",
        )
        _write_design_file(
            lexibrary_dir,
            "src/logger.py",
            wikilinks="- [[OldLog]]",
        )

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "[[Structured Logging]]" in issues[0].suggestion

    def test_no_deprecated_concepts(self, tmp_path: Path) -> None:
        """No deprecated concepts means no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(lexibrary_dir, "Healthy Concept", status="active")
        _write_design_file(
            lexibrary_dir,
            "src/app.py",
            wikilinks="- [[Healthy Concept]]",
        )

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_concepts_dir(self, tmp_path: Path) -> None:
        """No concepts directory means no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_stack_post_references_deprecated(self, tmp_path: Path) -> None:
        """Deprecated concept references in Stack posts also trigger warnings."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "Deprecated Pattern",
            status="deprecated",
            superseded_by="New Pattern",
        )

        # Create a stack post referencing the deprecated concept
        stack_dir = lexibrary_dir / "stack"
        stack_dir.mkdir()
        post = stack_dir / "Q-010.md"
        post.write_text(
            "---\nid: Q-010\ntitle: Pattern question\ntags:\n  - test\n"
            "status: open\ncreated: 2026-01-01\nauthor: tester\n---\n\n"
            "## Problem\n\nUsing [[Deprecated Pattern]] incorrectly.\n",
            encoding="utf-8",
        )

        issues = check_deprecated_concept_usage(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "stack/" in issues[0].artifact
        assert "[[New Pattern]]" in issues[0].suggestion
