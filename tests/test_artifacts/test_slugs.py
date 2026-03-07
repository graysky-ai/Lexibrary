"""Tests for shared slug-generation utilities and concept_slug helper."""

from __future__ import annotations

from lexibrary.artifacts.slugs import concept_slug, slugify

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_simple_title(self) -> None:
        assert slugify("Future annotations import") == "future-annotations-import"

    def test_special_characters(self) -> None:
        assert slugify("Use `from __future__` import") == "use-from-future-import"

    def test_underscores(self) -> None:
        assert slugify("snake_case_title") == "snake-case-title"

    def test_already_kebab(self) -> None:
        assert slugify("already-kebab-case") == "already-kebab-case"

    def test_leading_trailing_special(self) -> None:
        assert slugify("  --Hello World--  ") == "hello-world"

    def test_consecutive_special_chars(self) -> None:
        assert slugify("Use --- dashes & ampersands") == "use-dashes-ampersands"

    def test_long_title_truncation(self) -> None:
        long_title = (
            "This is a very long convention title that exceeds"
            " the sixty character limit by a significant margin"
        )
        slug = slugify(long_title)
        assert len(slug) <= 60
        assert not slug.endswith("-")

    def test_long_title_truncates_at_word_boundary(self) -> None:
        long_title = "a b c d e f g h i j k l m n o p q r s t u v w x y z alpha beta gamma delta"
        slug = slugify(long_title)
        assert len(slug) <= 60
        assert not slug.endswith("-")

    def test_empty_after_strip(self) -> None:
        slug = slugify("---")
        assert slug == ""

    def test_single_word(self) -> None:
        assert slugify("TypeScript") == "typescript"

    def test_mixed_case_and_numbers(self) -> None:
        assert slugify("Phase 3 Release") == "phase-3-release"

    def test_dots_and_at_signs(self) -> None:
        assert slugify("user@example.com pattern") == "user-example-com-pattern"

    def test_unicode_stripped(self) -> None:
        # Non-ASCII characters should be replaced with hyphens and collapsed
        assert slugify("cafe resume") == "cafe-resume"

    def test_multiple_underscores(self) -> None:
        assert slugify("__init__.py convention") == "init-py-convention"

    def test_tabs_and_newlines(self) -> None:
        assert slugify("hello\tworld\nnew") == "hello-world-new"

    def test_exact_60_chars(self) -> None:
        # A slug that's exactly 60 chars should not be truncated
        title = "a" * 60
        slug = slugify(title)
        assert slug == "a" * 60
        assert len(slug) == 60

    def test_61_chars_no_hyphen_boundary(self) -> None:
        # A single long word beyond 60 chars: no hyphen to split on
        title = "a" * 61
        slug = slugify(title)
        # Truncated to 60 since there's no hyphen to split at
        assert len(slug) == 60
        assert slug == "a" * 60


# ---------------------------------------------------------------------------
# concept_slug
# ---------------------------------------------------------------------------


class TestConceptSlug:
    def test_delegates_to_slugify(self) -> None:
        """concept_slug should produce the same result as slugify."""
        title = "Dependency Injection Pattern"
        assert concept_slug(title) == slugify(title)

    def test_simple_concept(self) -> None:
        assert concept_slug("Event Sourcing") == "event-sourcing"

    def test_concept_with_special_chars(self) -> None:
        assert concept_slug("CQRS/Event Sourcing") == "cqrs-event-sourcing"

    def test_importable_from_artifacts(self) -> None:
        from lexibrary.artifacts import concept_slug, slugify

        assert concept_slug is not None
        assert slugify is not None
