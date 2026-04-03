"""One-shot repair script for corrupted design file frontmatter.

Fixes 166 design files where PyYAML serialization caused description text
to bleed into the `id` field due to missing `sort_keys=False`.

Usage:
    uv run python tmp/repair_design_frontmatter.py --dry-run   # preview changes
    uv run python tmp/repair_design_frontmatter.py              # apply repairs
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Regex patterns from tasks.md shared content
VALID_ID_RE = re.compile(r"^DS-\d{3,}$")
CORRUPTED_ID_RE = re.compile(r"^(DS-\d{3,})\s+(.*)", re.DOTALL)

DESIGNS_DIR = Path(".lexibrary/designs")


def parse_frontmatter(text: str) -> tuple[dict[str, object], str] | None:
    """Parse YAML frontmatter and body from a design file.

    Returns (frontmatter_dict, body) or None if no frontmatter found.
    """
    if not text.startswith("---"):
        return None

    # Find the closing --- delimiter
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return None

    fm_text = text[4:end_idx]  # skip opening "---\n"
    body = text[end_idx + 4:]  # skip "\n---"

    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None

    if not isinstance(fm, dict):
        return None

    return fm, body


def repair_file(path: Path, dry_run: bool) -> str:
    """Attempt to repair a single design file.

    Returns: "repaired", "skipped", or "failed".
    """
    text = path.read_text(encoding="utf-8")
    result = parse_frontmatter(text)

    if result is None:
        return "failed"

    fm, body = result

    id_value = fm.get("id")
    if id_value is None:
        return "failed"

    id_str = str(id_value).strip()

    # Already valid -- skip
    if VALID_ID_RE.match(id_str):
        return "skipped"

    # Try to extract real ID from corrupted field
    match = CORRUPTED_ID_RE.match(id_str)
    if not match:
        return "failed"

    real_id = match.group(1)
    overflow_text = match.group(2).strip()

    # Reconstruct description: existing description + overflow text
    existing_desc = str(fm.get("description", "")).strip()
    if existing_desc and overflow_text:
        full_desc = existing_desc + " " + overflow_text
    elif overflow_text:
        full_desc = overflow_text
    else:
        full_desc = existing_desc

    # Collapse whitespace
    full_desc = " ".join(full_desc.split())

    # Update frontmatter
    fm["id"] = real_id
    fm["description"] = full_desc

    # Re-serialize frontmatter, preserving field order
    ordered_fm: dict[str, object] = {}
    # Put description first, id second (matches serializer output order)
    ordered_fm["description"] = fm.pop("description")
    ordered_fm["id"] = fm.pop("id")
    # Then remaining fields in original order
    for key, value in fm.items():
        ordered_fm[key] = value

    new_fm_text = yaml.dump(ordered_fm, default_flow_style=False, sort_keys=False).rstrip()
    new_text = "---\n" + new_fm_text + "\n---" + body

    if new_text == text:
        return "skipped"

    if dry_run:
        return "repaired"

    # Write back
    path.write_text(new_text, encoding="utf-8")

    # Post-write validation: re-parse and assert ID is valid
    verify_result = parse_frontmatter(new_text)
    if verify_result is None:
        print(f"  FAILURE: Could not re-parse {path}", file=sys.stderr)
        return "failed"

    verify_fm, _ = verify_result
    verify_id = str(verify_fm.get("id", ""))
    if not VALID_ID_RE.match(verify_id):
        print(f"  FAILURE: Post-write ID '{verify_id}' invalid in {path}", file=sys.stderr)
        return "failed"

    return "repaired"


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair corrupted design file frontmatter")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )
    args = parser.parse_args()

    if not DESIGNS_DIR.is_dir():
        print(f"Error: {DESIGNS_DIR} not found. Run from project root.", file=sys.stderr)
        sys.exit(1)

    files = sorted(DESIGNS_DIR.glob("**/*.md"))
    repaired = 0
    skipped = 0
    failed = 0

    for path in files:
        result = repair_file(path, args.dry_run)
        if result == "repaired":
            repaired += 1
            action = "would repair" if args.dry_run else "repaired"
            print(f"  {action}: {path}")
        elif result == "skipped":
            skipped += 1
        elif result == "failed":
            failed += 1
            print(f"  FAILED: {path}", file=sys.stderr)

    mode = "DRY RUN" if args.dry_run else "REPAIR"
    print(f"\n--- {mode} Summary ---")
    print(f"  Files repaired: {repaired}")
    print(f"  Files skipped:  {skipped}")
    print(f"  Failures:       {failed}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
