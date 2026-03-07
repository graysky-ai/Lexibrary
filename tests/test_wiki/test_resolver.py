"""Tests for wikilink resolver — resolution chain and batch resolution."""

from __future__ import annotations

from pathlib import Path

from lexibrary.wiki.index import ConceptIndex
from lexibrary.wiki.resolver import (
    ResolvedLink,
    UnresolvedLink,
    WikilinkResolver,
    _strip_brackets,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONCEPT_TEMPLATE = """\
---
title: {title}
aliases: {aliases}
tags: {tags}
status: active
---
{title} is a test concept.
"""


def _write_concept(
    directory: Path,
    filename: str,
    title: str,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    """Write a minimal concept file and return its path."""
    aliases_yaml = "[" + ", ".join(aliases or []) + "]"
    tags_yaml = "[" + ", ".join(tags or []) + "]"
    path = directory / filename
    path.write_text(
        _CONCEPT_TEMPLATE.format(title=title, aliases=aliases_yaml, tags=tags_yaml),
        encoding="utf-8",
    )
    return path


def _build_index(tmp_path: Path) -> ConceptIndex:
    """Create a small concept index for testing."""
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir()
    _write_concept(concepts_dir, "Pydantic.md", "Pydantic", aliases=["pydantic-v2"])
    _write_concept(concepts_dir, "TreeSitter.md", "Tree-sitter", aliases=["tree sitter", "ts"])
    _write_concept(concepts_dir, "Pathspec.md", "Pathspec", tags=["ignore"])
    _write_concept(concepts_dir, "BAML.md", "BAML", aliases=["baml-lang"])
    return ConceptIndex.load(concepts_dir)


def _build_stack_dir(tmp_path: Path) -> Path:
    """Create a stack directory with sample post files."""
    stack_dir = tmp_path / "stack"
    stack_dir.mkdir()
    (stack_dir / "ST-001-auth-question.md").write_text("# ST-001\n", encoding="utf-8")
    (stack_dir / "ST-042-config-issue.md").write_text("# ST-042\n", encoding="utf-8")
    return stack_dir


# ---------------------------------------------------------------------------
# Bracket stripping
# ---------------------------------------------------------------------------


class TestStripBrackets:
    def test_strips_brackets(self) -> None:
        assert _strip_brackets("[[Pydantic]]") == "Pydantic"

    def test_strips_with_whitespace(self) -> None:
        assert _strip_brackets("  [[Pydantic]]  ") == "Pydantic"

    def test_no_brackets(self) -> None:
        assert _strip_brackets("Pydantic") == "Pydantic"

    def test_partial_brackets(self) -> None:
        assert _strip_brackets("[[Pydantic") == "[[Pydantic"

    def test_empty_brackets(self) -> None:
        # [[]] would not match the regex (.+?) requires at least 1 char
        assert _strip_brackets("[[]]") == "[[]]"


# ---------------------------------------------------------------------------
# Stack post pattern (ST-NNN)
# ---------------------------------------------------------------------------


class TestStackResolution:
    def test_stack_pattern_with_file(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        stack_dir = _build_stack_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        result = resolver.resolve("ST-001")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "stack"
        assert result.name == "ST-001"
        assert result.path is not None
        assert result.path.name == "ST-001-auth-question.md"

    def test_stack_with_brackets(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        stack_dir = _build_stack_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        result = resolver.resolve("[[ST-042]]")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "stack"
        assert result.name == "ST-042"

    def test_stack_case_insensitive(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        stack_dir = _build_stack_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        result = resolver.resolve("st-001")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "stack"
        assert result.name == "ST-001"

    def test_stack_not_found(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        stack_dir = _build_stack_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        result = resolver.resolve("ST-999")
        assert isinstance(result, UnresolvedLink)
        assert result.raw == "ST-999"

    def test_stack_no_stack_dir(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)  # no stack_dir
        result = resolver.resolve("ST-001")
        assert isinstance(result, UnresolvedLink)

    def test_stack_four_digits(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        stack_dir = tmp_path / "stack4"
        stack_dir.mkdir()
        (stack_dir / "ST-1234-big-post.md").write_text("# ST-1234\n", encoding="utf-8")
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        result = resolver.resolve("ST-1234")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "stack"


# ---------------------------------------------------------------------------
# Exact name match
# ---------------------------------------------------------------------------


class TestExactNameMatch:
    def test_exact_match(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("Pydantic")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "concept"
        assert result.name == "Pydantic"

    def test_exact_match_case_insensitive(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("pydantic")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "concept"
        assert result.name == "Pydantic"

    def test_exact_match_with_brackets(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("[[Pydantic]]")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "concept"
        assert result.name == "Pydantic"

    def test_exact_match_hyphenated(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("Tree-sitter")
        assert isinstance(result, ResolvedLink)
        assert result.name == "Tree-sitter"


# ---------------------------------------------------------------------------
# Alias match
# ---------------------------------------------------------------------------


class TestAliasMatch:
    def test_alias_match(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("pydantic-v2")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "alias"
        assert result.name == "Pydantic"

    def test_alias_with_brackets(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("[[baml-lang]]")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "alias"
        assert result.name == "BAML"

    def test_alias_case_insensitive(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("PYDANTIC-V2")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "alias"
        assert result.name == "Pydantic"


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------


class TestFuzzyMatch:
    def test_fuzzy_resolves_close_match(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        # "Pydanticc" is close to "Pydantic"
        result = resolver.resolve("Pydanticc")
        assert isinstance(result, ResolvedLink)
        assert result.name == "Pydantic"

    def test_fuzzy_returns_unresolved_with_suggestions(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        # "xyzzy_not_real" matches nothing
        result = resolver.resolve("xyzzy_not_real")
        assert isinstance(result, UnresolvedLink)
        assert result.raw == "xyzzy_not_real"


# ---------------------------------------------------------------------------
# Unresolved
# ---------------------------------------------------------------------------


class TestUnresolved:
    def test_completely_unknown(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("CompletelyUnknownConcept12345")
        assert isinstance(result, UnresolvedLink)
        assert result.raw == "CompletelyUnknownConcept12345"

    def test_empty_index(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        index = ConceptIndex.load(empty_dir)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("Anything")
        assert isinstance(result, UnresolvedLink)


# ---------------------------------------------------------------------------
# Batch resolution (resolve_all)
# ---------------------------------------------------------------------------


class TestResolveAll:
    def test_resolve_all_mixed(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        stack_dir = _build_stack_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        links = ["[[Pydantic]]", "[[ST-001]]", "[[baml-lang]]", "UnknownThing12345"]
        resolved, unresolved = resolver.resolve_all(links)

        assert len(resolved) == 3
        assert len(unresolved) == 1
        assert resolved[0].name == "Pydantic"
        assert resolved[1].name == "ST-001"
        assert resolved[1].kind == "stack"
        assert resolved[2].name == "BAML"
        assert unresolved[0].raw == "UnknownThing12345"

    def test_resolve_all_empty(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        resolved, unresolved = resolver.resolve_all([])
        assert resolved == []
        assert unresolved == []

    def test_resolve_all_all_resolved(self, tmp_path: Path) -> None:
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        resolved, unresolved = resolver.resolve_all(["Pydantic", "BAML", "Pathspec"])
        assert len(resolved) == 3
        assert len(unresolved) == 0

    def test_resolve_all_all_unresolved(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        index = ConceptIndex.load(empty_dir)
        resolver = WikilinkResolver(index)
        resolved, unresolved = resolver.resolve_all(["Foo", "Bar"])
        assert len(resolved) == 0
        assert len(unresolved) == 2


# ---------------------------------------------------------------------------
# Resolution priority / chain order
# ---------------------------------------------------------------------------


class TestResolutionPriority:
    def test_stack_takes_priority_over_concept(self, tmp_path: Path) -> None:
        """If a concept were named ST-001, stack pattern still wins."""
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        _write_concept(concepts_dir, "ST001.md", "ST-001")
        index = ConceptIndex.load(concepts_dir)
        stack_dir = _build_stack_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir)
        result = resolver.resolve("ST-001")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "stack"

    def test_exact_name_takes_priority_over_alias(self, tmp_path: Path) -> None:
        """If one concept is named 'Foo' and another has alias 'Foo',
        the exact name match wins."""
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        _write_concept(concepts_dir, "Foo.md", "Foo")
        _write_concept(concepts_dir, "Bar.md", "Bar", aliases=["Foo"])
        index = ConceptIndex.load(concepts_dir)
        resolver = WikilinkResolver(index)
        result = resolver.resolve("Foo")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "concept"
        assert result.name == "Foo"


# ---------------------------------------------------------------------------
# Convention helpers
# ---------------------------------------------------------------------------

_CONVENTION_TEMPLATE = """\
---
title: {title}
scope: {scope}
tags: {tags}
status: active
aliases: {aliases}
---
{body}
"""


def _write_convention(
    directory: Path,
    filename: str,
    title: str,
    scope: str = "project",
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    body: str = "",
) -> Path:
    """Write a minimal convention file and return its path."""
    aliases_yaml = "[" + ", ".join(aliases or []) + "]"
    tags_yaml = "[" + ", ".join(tags or []) + "]"
    if not body:
        body = f"{title} is a test convention."
    path = directory / filename
    path.write_text(
        _CONVENTION_TEMPLATE.format(
            title=title,
            scope=scope,
            tags=tags_yaml,
            aliases=aliases_yaml,
            body=body,
        ),
        encoding="utf-8",
    )
    return path


def _build_convention_dir(tmp_path: Path) -> Path:
    """Create a conventions directory with sample convention files."""
    conv_dir = tmp_path / "conventions"
    conv_dir.mkdir()
    _write_convention(
        conv_dir,
        "auth-decorator.md",
        "All endpoints require auth decorator",
        aliases=["auth-decorator", "auth-rule"],
    )
    _write_convention(
        conv_dir,
        "no-bare-print.md",
        "No bare print statements",
        scope="src/",
        aliases=["no-print"],
    )
    return conv_dir


# ---------------------------------------------------------------------------
# Convention title resolution
# ---------------------------------------------------------------------------


class TestConventionTitleResolution:
    def test_convention_exact_title(self, tmp_path: Path) -> None:
        """[[Convention Title]] resolves to kind='convention'."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("[[All endpoints require auth decorator]]")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "All endpoints require auth decorator"
        assert result.path is None

    def test_convention_exact_title_case_insensitive(self, tmp_path: Path) -> None:
        """Convention title match is case-insensitive."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("all endpoints require auth decorator")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "All endpoints require auth decorator"

    def test_convention_exact_title_no_brackets(self, tmp_path: Path) -> None:
        """Convention title resolves without brackets."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("No bare print statements")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "No bare print statements"


# ---------------------------------------------------------------------------
# Convention alias resolution
# ---------------------------------------------------------------------------


class TestConventionAliasResolution:
    def test_convention_alias(self, tmp_path: Path) -> None:
        """[[alias]] resolves to convention kind."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("[[auth-decorator]]")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "All endpoints require auth decorator"

    def test_convention_alias_case_insensitive(self, tmp_path: Path) -> None:
        """Convention alias match is case-insensitive."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("AUTH-DECORATOR")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "All endpoints require auth decorator"

    def test_convention_second_alias(self, tmp_path: Path) -> None:
        """Second alias on a convention also resolves."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("auth-rule")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "All endpoints require auth decorator"

    def test_convention_alias_no_print(self, tmp_path: Path) -> None:
        """Alias on a different convention resolves correctly."""
        index = _build_index(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("[[no-print]]")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "No bare print statements"


# ---------------------------------------------------------------------------
# Convention-first precedence
# ---------------------------------------------------------------------------


class TestConventionFirstPrecedence:
    def test_convention_wins_over_concept_alias(self, tmp_path: Path) -> None:
        """When both a convention alias and concept alias match,
        convention wins (convention-first order)."""
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        _write_concept(concepts_dir, "AuthConcept.md", "Auth Concept", aliases=["auth-decorator"])
        index = ConceptIndex.load(concepts_dir)

        conv_dir = tmp_path / "conventions"
        conv_dir.mkdir()
        _write_convention(
            conv_dir,
            "auth-conv.md",
            "Auth Convention",
            aliases=["auth-decorator"],
        )

        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("auth-decorator")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "Auth Convention"

    def test_convention_title_wins_over_concept_title(self, tmp_path: Path) -> None:
        """When a convention title and concept title are the same,
        convention wins."""
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        _write_concept(concepts_dir, "SharedName.md", "Shared Name")
        index = ConceptIndex.load(concepts_dir)

        conv_dir = tmp_path / "conventions"
        conv_dir.mkdir()
        _write_convention(conv_dir, "shared-name.md", "Shared Name")

        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        result = resolver.resolve("Shared Name")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "convention"
        assert result.name == "Shared Name"

    def test_stack_still_wins_over_convention(self, tmp_path: Path) -> None:
        """Stack pattern resolution still takes highest priority."""
        index = _build_index(tmp_path)
        stack_dir = _build_stack_dir(tmp_path)
        conv_dir = _build_convention_dir(tmp_path)
        resolver = WikilinkResolver(index, stack_dir=stack_dir, convention_dir=conv_dir)
        result = resolver.resolve("ST-001")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "stack"


# ---------------------------------------------------------------------------
# Convention fuzzy matching
# ---------------------------------------------------------------------------


class TestConventionFuzzyMatch:
    def test_fuzzy_match_suggests_conventions(self, tmp_path: Path) -> None:
        """Convention titles appear in fuzzy-match suggestions."""
        empty_dir = tmp_path / "empty_concepts"
        empty_dir.mkdir()
        index = ConceptIndex.load(empty_dir)

        conv_dir = tmp_path / "conventions"
        conv_dir.mkdir()
        _write_convention(
            conv_dir,
            "auth-decorator.md",
            "Auth Decorator Rule",
            aliases=["auth-decorator"],
        )

        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        # "auth-decorato" is close to "auth-decorator" alias
        result = resolver.resolve("auth-decorato")
        assert isinstance(result, UnresolvedLink)
        assert len(result.suggestions) > 0

    def test_fuzzy_match_pool_includes_convention_aliases(self, tmp_path: Path) -> None:
        """The fuzzy match pool contains convention aliases."""
        empty_dir = tmp_path / "empty_concepts"
        empty_dir.mkdir()
        index = ConceptIndex.load(empty_dir)

        conv_dir = tmp_path / "conventions"
        conv_dir.mkdir()
        _write_convention(
            conv_dir,
            "conv.md",
            "Some Convention",
            aliases=["my-special-alias"],
        )

        resolver = WikilinkResolver(index, convention_dir=conv_dir)
        all_names = resolver._all_names_and_aliases()
        assert "Some Convention" in all_names
        assert "my-special-alias" in all_names


# ---------------------------------------------------------------------------
# Resolver without convention_dir
# ---------------------------------------------------------------------------


class TestResolverWithoutConventionDir:
    def test_no_convention_dir_skips_convention_checks(self, tmp_path: Path) -> None:
        """When convention_dir is not provided, convention resolution is skipped."""
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        _write_concept(concepts_dir, "Auth.md", "Auth", aliases=["auth-decorator"])
        index = ConceptIndex.load(concepts_dir)

        # No convention_dir passed — should fall through to concept alias
        resolver = WikilinkResolver(index)
        result = resolver.resolve("auth-decorator")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "alias"
        assert result.name == "Auth"

    def test_nonexistent_convention_dir_skips(self, tmp_path: Path) -> None:
        """When convention_dir points to a nonexistent directory, resolution skips conventions."""
        index = _build_index(tmp_path)
        missing_dir = tmp_path / "no-such-dir"
        resolver = WikilinkResolver(index, convention_dir=missing_dir)
        # Convention resolution should be skipped; concept should resolve
        result = resolver.resolve("Pydantic")
        assert isinstance(result, ResolvedLink)
        assert result.kind == "concept"
        assert result.name == "Pydantic"

    def test_convention_names_excluded_from_fuzzy_pool_without_dir(self, tmp_path: Path) -> None:
        """Without convention_dir, _all_names_and_aliases contains only concepts."""
        index = _build_index(tmp_path)
        resolver = WikilinkResolver(index)
        all_names = resolver._all_names_and_aliases()
        # Should only have concept names/aliases
        assert "Pydantic" in all_names
        assert "pydantic-v2" in all_names
        # No convention names should be present
        # 4 concepts + 4 aliases (pydantic-v2, tree sitter, ts, baml-lang)
        assert len(all_names) == 8
