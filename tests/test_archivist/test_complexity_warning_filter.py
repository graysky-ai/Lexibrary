"""Tests for the deterministic complexity_warning post-filter (§2.4b, Group 16).

Verifies the behaviour of :func:`_filter_complexity_warning` in
``lexibrary.archivist.pipeline`` — a pure function that decides whether the
LLM's ``complexity_warning`` string is load-bearing enough to surface in the
rendered design file, or whether it should be dropped as generic hedging.

The filter composes with the Group 15 suppression gate (which zeroes
aggregators + constants-only modules) by being idempotent on ``None`` input —
``None`` in, ``None`` out, no synthesis.

Contract reference: ``archivist-pipeline`` spec delta and
``plans/design-cleanup/complexity-warning-audit.md`` (Group 14, §
"Group 16 implementation notes for the agent").

Audit-derived thresholds exercised here:

- Length threshold: 500 chars (not the 120 placeholder in SHARED_BLOCK_E).
- Signal markers: skeleton identifier, dotted call path, proper noun,
  version string, SQL keyword, file-path literal, CLI flag.
"""

from __future__ import annotations

from lexibrary.archivist.pipeline import _filter_complexity_warning


class TestLengthGate:
    """Length threshold alone is enough to preserve a warning."""

    def test_short_warning_no_signal_dropped(self) -> None:
        """Short warning with no signal marker → dropped (None)."""
        raw = "Be careful when modifying imports."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton="def run(): ...",
                length_threshold=500,
            )
            is None
        )

    def test_long_warning_no_signal_preserved(self) -> None:
        """Warning ≥ threshold, no signal markers → PRESERVED.

        The filter keeps when EITHER length OR signal-marker holds, so a
        long-but-generic warning survives the length gate. This is the
        intentional design recorded in the archivist-pipeline spec delta —
        long warnings almost always contain at least some load-bearing
        material even if not regex-detectable.
        """
        raw = "a" * 550  # pure filler, no identifiers / dots / flags / paths
        result = _filter_complexity_warning(
            raw,
            interface_skeleton=None,
            length_threshold=500,
        )
        assert result == raw

    def test_short_generic_under_threshold_dropped(self) -> None:
        """Explicit case from the audit: a 400-char generic hedge is dropped.

        Mirrors the ``artifacts/aindex.py`` generic-hedge bucket (335 chars)
        and similar under-threshold hedges.
        """
        raw = (
            "Changes to this module may affect multiple downstream modules. "
            "Care should be taken when modifying imports or adding mutable "
            "default values."
        )
        # Sanity: input is short enough to exercise length gate.
        assert len(raw) < 500
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton="class Aindex: ...",  # no overlap
                length_threshold=500,
            )
            is None
        )


class TestSkeletonIdentifierMarker:
    """A verbatim identifier from the skeleton preserves the warning."""

    def test_identifier_from_skeleton_preserved(self) -> None:
        """Warning cites a function name that appears in the skeleton."""
        skeleton = "def atomic_write(path, content): ...\nclass Writer: ..."
        raw = "atomic_write must fsync the parent directory."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=skeleton,
                length_threshold=500,
            )
            == raw
        )

    def test_identifier_not_in_skeleton_dropped(self) -> None:
        """Warning cites an identifier that does NOT appear in the skeleton.

        With no other signal marker, a short warning is dropped.
        """
        skeleton = "def unrelated(): ...\n"
        raw = "Remember to call setup() before teardown()."
        # No dotted form (just bare ``setup`` / ``teardown``), no proper noun
        # sequence, no version / SQL / path / flag.
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=skeleton,
                length_threshold=500,
            )
            is None
        )

    def test_single_char_identifier_ignored(self) -> None:
        """Tokens of length <2 in the skeleton are not used as markers.

        This is the explicit ``len(tok) >= 2`` rule from the SHARED_BLOCK_E
        pseudocode — single-letter locals like ``x`` would otherwise match
        everything.
        """
        skeleton = "def f(x, y):\n    return x + y\n"
        raw = "Avoid using x values above 100."  # bare 'x'
        # The skeleton's 'f', 'x', 'y' are all len<=1 and skipped; 'return'
        # IS len>=2 but not present in the warning text. So no identifier
        # match, and the short warning is dropped.
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=skeleton,
                length_threshold=500,
            )
            is None
        )

    def test_none_skeleton_falls_through_to_other_markers(self) -> None:
        """``None`` skeleton → no identifier matches, other markers may save."""
        raw = "See --force flag."  # CLI flag marker should preserve
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestVersionMarker:
    """Warnings with version strings are preserved."""

    def test_python_version_preserved(self) -> None:
        """``Python 3.11+`` preserves an otherwise generic warning."""
        raw = "Python 3.11+ required."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_node_version_preserved(self) -> None:
        raw = "Node 20 minimum."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_semver_tag_preserved(self) -> None:
        """``v0.6.1`` marker preserves the warning."""
        raw = "Behaviour changed in v0.6.1."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestProperNounMarker:
    """Multi-word CamelCase phrases are preserved."""

    def test_multi_word_proper_noun_preserved(self) -> None:
        """``SQLite WAL Mode`` triples match the proper-noun regex.

        The regex requires at least two CamelCase tokens separated by a
        space, so a single capitalised word is NOT enough on its own.
        """
        raw = "Relies on SQLite WAL Mode."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_single_capitalised_word_alone_dropped(self) -> None:
        """A single ``Linux`` token is not enough.

        Note — the warning also doesn't match any other markers: no dots, no
        version, no file path, no CLI flag.
        """
        raw = "Linux-only code path."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            is None
        )


class TestDottedIdentifierMarker:
    """Dotted call paths (``Path.resolve``, ``yaml.safe_load``) are preserved."""

    def test_dotted_path_resolve_preserved_via_skeleton(self) -> None:
        """``Path.resolve`` — leading uppercase, so ``_DOTTED_IDENT_RE`` (which
        requires a lowercase-leading identifier) does NOT match.

        In practice ``Path`` is always in the skeleton for modules using it,
        so the identifier marker path preserves the warning. The audit's
        commentary example for ``_DOTTED_IDENT_RE`` (line 367 — "catches
        `Path.resolve`") is wrong about which regex wins, but the outcome
        (warning preserved) is correct because of the skeleton-identifier
        fallback.
        """
        raw = "Path.resolve follows symlinks."
        # Without skeleton: no regex matches (Path.resolve starts uppercase).
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            is None
        )
        # With ``Path`` in the skeleton: identifier marker preserves it.
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton="from pathlib import Path\n",
                length_threshold=500,
            )
            == raw
        )

    def test_dotted_yaml_safe_load_preserved(self) -> None:
        """``yaml.safe_load`` — a common load-bearing marker in the audit."""
        raw = "Uses yaml.safe_load."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_dotted_frontmatter_updated_by_preserved(self) -> None:
        """Deep dotted path from the audit: ``frontmatter.updated_by``."""
        raw = "Check frontmatter.updated_by."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestSqlMarker:
    """SQLite-specific keywords are preserved."""

    def test_fts5_preserved(self) -> None:
        """``FTS5`` alone preserves the warning."""
        raw = "Uses FTS5 virtual table."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_wal_preserved(self) -> None:
        raw = "Depends on WAL pragma."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_collate_nocase_preserved(self) -> None:
        raw = "Alias matches use COLLATE NOCASE."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_insert_or_ignore_preserved(self) -> None:
        raw = "Relies on INSERT OR IGNORE idempotency."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestFilePathMarker:
    """Project-specific path literals are preserved."""

    def test_lexibrary_index_db_preserved(self) -> None:
        """``.lexibrary/index.db`` preserves the warning."""
        raw = "Reads .lexibrary/index.db."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_src_lexibrary_path_preserved(self) -> None:
        raw = "Scans src/lexibrary/ at startup."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_baml_src_path_preserved(self) -> None:
        raw = "Prompt lives in baml_src/."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_aindex_marker_preserved(self) -> None:
        raw = "Emits .aindex artefacts per directory."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestCliFlagMarker:
    """Double-dash CLI flags are preserved."""

    def test_force_flag_preserved(self) -> None:
        """``--force`` preserves the warning."""
        raw = "Override with --force."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_unlimited_flag_preserved(self) -> None:
        raw = "Use --unlimited to bypass the budget."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )

    def test_compound_flag_preserved(self) -> None:
        """Hyphenated flag ``--help-extended`` preserves the warning."""
        raw = "See --help-extended."
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestNoneIdempotent:
    """The filter never synthesises: ``None`` input → ``None`` output."""

    def test_none_input_returns_none_with_skeleton(self) -> None:
        """LLM returned ``None`` → result ``None`` even when skeleton present."""
        assert (
            _filter_complexity_warning(
                None,
                interface_skeleton="def f(): ...",
                length_threshold=500,
            )
            is None
        )

    def test_none_input_returns_none_without_skeleton(self) -> None:
        assert (
            _filter_complexity_warning(
                None,
                interface_skeleton=None,
                length_threshold=500,
            )
            is None
        )


class TestQuoteStripping:
    """The filter strips wrapping quotes before measuring length / scanning."""

    def test_quoted_short_generic_still_dropped(self) -> None:
        """Wrapping in quotes does not save a short generic warning.

        The filter strips ``\"`` and ``'`` before computing length and
        scanning for markers, so a generic hedge in quotes drops the same
        way as unquoted.
        """
        raw = '"Be careful when touching this."'
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            is None
        )

    def test_quoted_input_with_marker_returns_raw(self) -> None:
        """When preserved, the filter returns the ORIGINAL (quoted) string.

        Quote stripping is a SCAN-time normalisation; the return value is
        ``raw``, not the stripped text.
        """
        raw = '"Requires Python 3.11+."'
        assert (
            _filter_complexity_warning(
                raw,
                interface_skeleton=None,
                length_threshold=500,
            )
            == raw
        )


class TestDefaultThreshold:
    """The default length threshold of 500 matches the Group 14 audit."""

    def test_default_threshold_is_500(self) -> None:
        """Calling without ``length_threshold`` uses 500 (not 120)."""
        # 480 chars — under the 500 audit default, above the 120 placeholder.
        raw = "a" * 480
        # No signal markers present — filler 'a' is not CamelCase, not a
        # dotted path, etc.
        result = _filter_complexity_warning(
            raw,
            interface_skeleton=None,
        )
        assert result is None

    def test_default_threshold_preserves_at_500(self) -> None:
        """At length exactly 500, a filler warning is preserved."""
        raw = "a" * 500
        result = _filter_complexity_warning(
            raw,
            interface_skeleton=None,
        )
        assert result == raw
