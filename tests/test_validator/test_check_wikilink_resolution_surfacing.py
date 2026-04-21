"""Regression test for §1.6 wikilink gold-bar — validator surfacing guarantee.

The design-cleanup change (§1.6) tightens the archivist prompt so that
wikilinks are only emitted when the target MATERIALLY SHAPES the file's
design. Stricter authoring implies that some previously-tolerable passing
references will be dropped, and — symmetrically — that dangling wikilinks
authored by humans or older LLM runs MUST continue to surface through
``lexi validate`` rather than silently accumulating.

The spec delta for §1.6 explicitly frames the deliverable as a regression
test, not a new validator check: ``check_wikilink_resolution`` already
emits error-severity ``ValidationIssue`` objects for dangling targets in
both design files and Stack posts. This module locks that contract in
place so a future refactor of the resolver, the parser, or the check
itself cannot regress the §1.6 surfacing guarantee without breaking a
test named after the clause it defends.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.validator.checks import check_wikilink_resolution

# ---------------------------------------------------------------------------
# Helpers — minimal design-file fixture authored to exercise the wikilink path
# ---------------------------------------------------------------------------


def _write_design_file_with_wikilink(
    lexibrary_dir: Path,
    source_path: str,
    wikilink_target: str,
) -> Path:
    """Write a minimal valid design file containing a single wikilink.

    Returns the path to the design file.
    """
    design_path = lexibrary_dir / "designs" / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    content = f"""---
description: Test design file for wikilink surfacing regression
id: DS-001
updated_by: archivist
---

# {source_path}

## Interface Contract

```python
def example(): ...
```

## Dependencies

(none)

## Dependents

(none)

## Wikilinks

- [[{wikilink_target}]]

<!-- lexibrary:meta
source: {source_path}
source_hash: abc123
design_hash: def456
generated: {now}
generator: test
-->
"""
    design_path.write_text(content, encoding="utf-8")
    return design_path


# ---------------------------------------------------------------------------
# §1.6 regression: dangling wikilink surfaces as error-severity issue
# ---------------------------------------------------------------------------


class TestWikilinkResolutionSurfacing:
    """§1.6 regression — ``check_wikilink_resolution`` must surface dangling
    targets authored against the tightened prompt.
    """

    def test_dangling_wikilink_emits_error_issue(self, tmp_path: Path) -> None:
        """A design file with a wikilink to a non-existent concept produces
        exactly one error-severity ``ValidationIssue`` whose ``check`` field
        is ``"wikilink_resolution"`` and whose message names the unresolved
        target. This is the narrow contract §1.6 depends on — stricter
        prompt authoring only makes sense if the validator keeps surfacing
        targets that do not resolve.
        """
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Concepts directory exists but contains no matching concept.
        (lexibrary_dir / "concepts").mkdir(parents=True)

        # Source file exists so other checks have nothing to flag.
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "example.py").write_text("# example", encoding="utf-8")

        # Design file references a concept that does not exist.
        _write_design_file_with_wikilink(
            lexibrary_dir,
            "src/example.py",
            wikilink_target="NonExistentConceptForSixOneSix",
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)

        # Contract: the dangling wikilink surfaces as a single error issue.
        assert len(issues) == 1, (
            f"expected exactly one issue for a single dangling wikilink; "
            f"got {len(issues)}: {issues}"
        )

        issue = issues[0]
        assert issue.severity == "error", (
            f"§1.6 requires error-severity surfacing; got {issue.severity!r}"
        )
        assert issue.check == "wikilink_resolution", (
            f"§1.6 regression test requires check name 'wikilink_resolution'; got {issue.check!r}"
        )
        assert "NonExistentConceptForSixOneSix" in issue.message, (
            f"§1.6 regression test requires the unresolved target in the "
            f"message; got {issue.message!r}"
        )
        assert "does not resolve" in issue.message, (
            f"§1.6 regression test requires a 'does not resolve' phrase to "
            f"signal the failure mode; got {issue.message!r}"
        )
