"""Refresh source_hash / interface_hash / design_hash for fixture design files.

This helper keeps the static curator fixture at
``tests/fixtures/curator_library/.lexibrary/designs/`` in sync with its
source tree (``tests/fixtures/curator_library/src/``) without invoking the
BAML-backed archivist LLM.  It walks every ``*.py.md`` under ``designs/``,
resolves the matching source file, recomputes the canonical hashes, and
rewrites the HTML comment footer in place.

The script uses **footer-only rewriting**: it locates the existing
``<!-- lexibrary:meta ... -->`` block via :data:`_FOOTER_RE`, strips it
from the file text, computes a new ``design_hash`` over the footer-less
body (matching :func:`change_checker._compute_design_content_hash`), then
appends a refreshed footer.  Prose, frontmatter, preserved sections, and
wikilinks are left untouched byte-for-byte.

Run from the repository root::

    python tests/fixtures/curator_library/refresh_hashes.py

Add ``--check`` to compare current footers against recomputed hashes
without writing anything -- useful in CI to detect drift after unrelated
source-file edits.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports from the Lexibrary package
# ---------------------------------------------------------------------------
# The fixture directory lives inside the Lexibrary repo, so ``lexibrary`` is
# importable when the script is run from the repo root.  Keep the import
# inline so the module docstring and CLI help survive even if the package
# layout shifts.
from lexibrary.artifacts.design_file_parser import _FOOTER_RE, parse_design_file_metadata
from lexibrary.ast_parser import compute_hashes

# ---------------------------------------------------------------------------
# Paths (resolved relative to this script, not cwd, so it is cwd-agnostic)
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = FIXTURE_ROOT / "src"
DESIGNS_ROOT = FIXTURE_ROOT / ".lexibrary" / "designs"

_GENERATOR_ID = "lexibrary-v2"


def _source_for_design(design_path: Path) -> Path:
    """Map a design file path back to its source file.

    ``{fixture}/.lexibrary/designs/src/auth/login.py.md`` →
    ``{fixture}/src/auth/login.py``
    """
    rel = design_path.relative_to(DESIGNS_ROOT)
    # rel e.g. Path("src/auth/login.py.md"); strip the trailing ``.md``
    if rel.suffix != ".md":
        raise ValueError(f"Unexpected design filename suffix: {design_path}")
    source_rel = rel.with_suffix("")  # src/auth/login.py
    return FIXTURE_ROOT / source_rel


def _recompute_footer(
    design_path: Path,
    source_hash: str,
    interface_hash: str | None,
) -> tuple[str, str]:
    """Return ``(new_file_text, new_design_hash)`` for *design_path*.

    The design_hash is recomputed from the body obtained by stripping the
    existing footer via :data:`_FOOTER_RE` and rstripping trailing
    newlines -- byte-identical to
    :func:`change_checker._compute_design_content_hash`.
    """
    raw = design_path.read_text(encoding="utf-8")

    # Extract the existing footer so we can preserve ``source`` and
    # ``generator`` fields (the body-independent metadata).
    existing_metadata = parse_design_file_metadata(design_path)
    if existing_metadata is None:
        raise ValueError(f"Design file has no parseable footer: {design_path}")

    # Strip footer and compute canonical design_hash.
    body = _FOOTER_RE.sub("", raw).rstrip("\n")
    design_hash = hashlib.sha256(body.encode()).hexdigest()

    # Build the new footer.  Keep generator/source stable; refresh hashes
    # and the generated timestamp.
    now = datetime.now(UTC).replace(tzinfo=None)
    footer_lines = [
        "<!-- lexibrary:meta",
        f"source: {existing_metadata.source}",
        f"source_hash: {source_hash}",
    ]
    if interface_hash is not None:
        footer_lines.append(f"interface_hash: {interface_hash}")
    footer_lines.append(f"design_hash: {design_hash}")
    footer_lines.append(f"generated: {now.isoformat()}")
    footer_lines.append(f"generator: {existing_metadata.generator or _GENERATOR_ID}")
    footer_lines.append("-->")

    new_text = body + "\n\n" + "\n".join(footer_lines) + "\n"
    return new_text, design_hash


def _iter_design_files() -> list[Path]:
    """Return every ``*.md`` file under the fixture's designs tree."""
    if not DESIGNS_ROOT.exists():
        raise FileNotFoundError(f"Missing designs directory: {DESIGNS_ROOT}")
    return sorted(DESIGNS_ROOT.rglob("*.md"))


def refresh_all(*, check_only: bool = False) -> int:
    """Refresh (or verify) every fixture design file.

    Returns ``0`` on success, ``1`` if drift was detected in ``--check``
    mode, ``2`` on structural errors (missing source file, broken
    footer).
    """
    designs = _iter_design_files()
    if not designs:
        print(f"No design files found under {DESIGNS_ROOT}", file=sys.stderr)
        return 2

    any_drift = False
    any_error = False

    for design_path in designs:
        source_path = _source_for_design(design_path)
        if not source_path.exists():
            print(f"MISSING SOURCE: {source_path.relative_to(FIXTURE_ROOT)}", file=sys.stderr)
            any_error = True
            continue

        try:
            source_hash, interface_hash = compute_hashes(source_path)
        except Exception as exc:  # pragma: no cover - defensive
            print(
                f"HASH FAILED: {source_path.relative_to(FIXTURE_ROOT)}: {exc}",
                file=sys.stderr,
            )
            any_error = True
            continue

        try:
            new_text, design_hash = _recompute_footer(
                design_path,
                source_hash=source_hash,
                interface_hash=interface_hash,
            )
        except ValueError as exc:
            print(f"FOOTER FAILED: {design_path.relative_to(FIXTURE_ROOT)}: {exc}", file=sys.stderr)
            any_error = True
            continue

        current_metadata = parse_design_file_metadata(design_path)
        drift = (
            current_metadata is None
            or current_metadata.source_hash != source_hash
            or current_metadata.interface_hash != interface_hash
            or current_metadata.design_hash != design_hash
        )

        rel = design_path.relative_to(FIXTURE_ROOT)
        if drift:
            any_drift = True
            if check_only:
                print(f"DRIFT: {rel}")
            else:
                design_path.write_text(new_text, encoding="utf-8")
                print(
                    f"REFRESHED: {rel}"
                    f"\n    source_hash={source_hash[:12]}…"
                    f" interface_hash="
                    f"{(interface_hash[:12] + '…') if interface_hash else 'None'}"
                    f" design_hash={design_hash[:12]}…",
                )
        else:
            print(f"OK: {rel}")

    if any_error:
        return 2
    if check_only and any_drift:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh source_hash / interface_hash / design_hash for fixture design"
            " files without invoking the archivist LLM."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit with code 1 if any footer is out of date.",
    )
    args = parser.parse_args()
    return refresh_all(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
