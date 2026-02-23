## 1. StackPost Models & Module Setup

- [x] 1.1 Create `src/lexibrary/stack/` package with `__init__.py` re-exporting `StackPost`, `StackAnswer`, `StackPostFrontmatter`, `StackPostRefs`
- [x] 1.2 Create `src/lexibrary/stack/models.py` with `StackPostRefs`, `StackPostFrontmatter`, `StackAnswer`, `StackPost` Pydantic 2 models
- [x] 1.3 Write unit tests for model validation (required fields, tag min_length, status enum, vote defaults)

## 2. Stack Parser

- [x] 2.1 Create `src/lexibrary/stack/parser.py` with `parse_stack_post(path: Path) -> StackPost | None`
- [x] 2.2 Implement YAML frontmatter extraction into `StackPostFrontmatter`
- [x] 2.3 Implement `## Problem` and `### Evidence` section extraction
- [x] 2.4 Implement `### A{n}` answer block parsing (metadata line, body, `#### Comments`)
- [x] 2.5 Write unit tests for parser (valid posts, no answers, multiple answers with comments, accepted answers, nonexistent file, malformed file)

## 3. Stack Serializer

- [x] 3.1 Create `src/lexibrary/stack/serializer.py` with `serialize_stack_post(post: StackPost) -> str`
- [x] 3.2 Implement YAML frontmatter serialization with nested `refs` block
- [x] 3.3 Implement body serialization (Problem, Evidence, Answers with metadata lines and Comments)
- [x] 3.4 Write unit tests for serializer (no answers, with answers, accepted answer, negative votes)
- [x] 3.5 Write round-trip tests (serialize → parse → compare)

## 4. Stack Template

- [x] 4.1 Create `src/lexibrary/stack/template.py` with `render_post_template()` function
- [x] 4.2 Write unit tests for template rendering (minimal args, with file refs, with bead, created date)

## 5. Stack Index

- [x] 5.1 Create `src/lexibrary/stack/index.py` with `StackIndex` class and `build()` classmethod
- [x] 5.2 Implement `search()` method (case-insensitive full-text across titles, problems, answers, tags)
- [x] 5.3 Implement `by_tag()`, `by_scope()`, `by_status()`, `by_concept()` filter methods
- [x] 5.4 Write unit tests for index building, search, and all filter methods

## 6. Stack Mutations

- [x] 6.1 Create `src/lexibrary/stack/mutations.py` with `add_answer()` function
- [x] 6.2 Implement `record_vote()` with upvote/downvote logic and comment appending
- [x] 6.3 Implement `accept_answer()`, `mark_duplicate()`, `mark_outdated()` functions
- [x] 6.4 Write unit tests for all mutations (add answer, vote up/down, downvote requires comment, accept answer, mark duplicate, mark outdated, append-only body invariant)

## 7. Design File Integration

- [x] 7.1 Rename `guardrail_refs` to `stack_refs` in `artifacts/design_file.py` DesignFile model
- [x] 7.2 Update `artifacts/design_file_serializer.py`: rename `## Guardrails` section to `## Stack`
- [x] 7.3 Update `artifacts/design_file_parser.py`: recognize both `## Stack` and `## Guardrails` headers, parse into `stack_refs`
- [x] 7.4 Remove `artifacts/guardrail.py` and update `artifacts/__init__.py` exports (remove `GuardrailThread`)
- [x] 7.5 Update any references to `guardrail_refs` or `GuardrailThread` across the codebase (imports, BAML prompts, tests)
- [x] 7.6 Write tests for updated serializer (## Stack section) and parser (backward compat with ## Guardrails)

## 8. Wikilink Resolver Update

- [x] 8.1 Update `wiki/resolver.py`: change `ResolvedLink.kind` from `"guardrail"` to `"stack"`, add `stack_dir` parameter to constructor
- [x] 8.2 Replace `GR-NNN` pattern detection with `ST-NNN` pattern, implement glob-based file lookup in `.lexibrary/stack/`
- [x] 8.3 Update resolver tests (replace GR-NNN test cases with ST-NNN, add stack file resolution tests)

## 9. CLI Commands — Stack Group

- [x] 9.1 Remove `guardrail_app` and `guardrails` command stubs from `cli.py`
- [x] 9.2 Add `stack_app` Typer sub-group to `cli.py`
- [x] 9.3 Implement `lexi stack post` command (auto-assign ID, create file, print path)
- [x] 9.4 Implement `lexi stack search` command (query + tag/scope/status/concept filters)
- [x] 9.5 Implement `lexi stack answer` command (append answer to post)
- [x] 9.6 Implement `lexi stack vote` command (up/down with --comment enforcement for downvotes)
- [x] 9.7 Implement `lexi stack accept` command (mark answer accepted, set resolved)
- [x] 9.8 Implement `lexi stack view` command (formatted full post display)
- [x] 9.9 Implement `lexi stack list` command (compact list with status/tag filters)
- [x] 9.10 Write CLI tests with `typer.testing.CliRunner` for all stack commands

## 10. Unified Search

- [x] 10.1 Implement `lexi search` command: query concepts via `ConceptIndex`, design files via frontmatter scan, Stack posts via `StackIndex`
- [x] 10.2 Implement grouped result display (Concepts, Design Files, Stack) with Rich formatting
- [x] 10.3 Support `--tag` and `--scope` flags across all artifact types
- [x] 10.4 Write integration tests for cross-artifact search

## 11. Init & Scaffolding Update

- [x] 11.1 Update `init/scaffolder.py`: replace `guardrails/` directory creation with `stack/`
- [x] 11.2 Write test verifying `lexi init` creates `.lexibrary/stack/` and does not create `.lexibrary/guardrails/`
