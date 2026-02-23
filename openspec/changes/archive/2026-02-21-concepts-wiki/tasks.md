## 1. ConceptFile Model Update

- [x] 1.1 Replace stub `ConceptFile` model in `src/lexibrary/artifacts/concept.py` with full `ConceptFileFrontmatter` (title, aliases, tags, status, superseded_by) and `ConceptFile` (frontmatter, body, summary, related_concepts, linked_files, decision_log) models
- [x] 1.2 Update `src/lexibrary/artifacts/__init__.py` to re-export `ConceptFileFrontmatter`
- [x] 1.3 Write unit tests for model validation (status enum, superseded_by, defaults)

## 2. Wiki Module — Parser & Serializer

- [x] 2.1 Create `src/lexibrary/wiki/__init__.py` with public API re-exports
- [x] 2.2 Create `src/lexibrary/wiki/parser.py` with `parse_concept_file()` — YAML frontmatter extraction, body parsing, summary/wikilink/decision_log/linked_files extraction
- [x] 2.3 Create `src/lexibrary/wiki/serializer.py` with `serialize_concept_file()` — YAML frontmatter + raw body output
- [x] 2.4 Create `src/lexibrary/wiki/template.py` with `render_concept_template()` and `concept_file_path()` (PascalCase naming)
- [x] 2.5 Write unit tests for parser (valid files, missing frontmatter, invalid fields, body section extraction)
- [x] 2.6 Write unit tests for serializer and round-trip integrity
- [x] 2.7 Write unit tests for template rendering and PascalCase path derivation

## 3. Concept Index

- [x] 3.1 Create `src/lexibrary/wiki/index.py` with `ConceptIndex` class — `load()`, `search()`, `find()`, `names()`, `by_tag()` methods
- [x] 3.2 Implement normalized substring search across names, aliases, tags, summaries
- [x] 3.3 Write unit tests for index loading, search, find, by_tag (using tmp_path concept files)

## 4. Wikilink Resolver

- [x] 4.1 Create `src/lexibrary/wiki/resolver.py` with `ResolvedLink`, `UnresolvedLink` dataclasses and `WikilinkResolver` class
- [x] 4.2 Implement resolution chain: bracket stripping → guardrail pattern (GR-NNN) → exact name → alias → fuzzy match → unresolved with suggestions
- [x] 4.3 Implement `resolve_all()` batch resolution method
- [x] 4.4 Write unit tests for each resolution step and edge cases

## 5. Design File Integration

- [x] 5.1 Update `src/lexibrary/artifacts/design_file_serializer.py` to wrap wikilinks in `[[brackets]]` (avoid double-wrapping)
- [x] 5.2 Update `src/lexibrary/artifacts/design_file_parser.py` to strip `[[]]` brackets from wikilinks (handle both bracketed and unbracketed formats)
- [x] 5.3 Write tests for updated serializer wikilink bracket format
- [x] 5.4 Write tests for parser bracket stripping and backward compatibility

## 6. Archivist Concept Awareness

- [x] 6.1 Add `available_concepts` (string[]?) parameter to `ArchivistGenerateDesignFile` BAML function in `baml_src/archivist_design_file.baml` and update prompt to prefer existing concept names for wikilinks
- [x] 6.2 Add `available_concepts` field to `DesignFileRequest` dataclass in `src/lexibrary/archivist/service.py` and pass to BAML call
- [x] 6.3 Update `update_file()` in `src/lexibrary/archivist/pipeline.py` to accept and pass `available_concepts` parameter
- [x] 6.4 Update `update_project()` in `src/lexibrary/archivist/pipeline.py` to load concept names from `.lexibrary/concepts/` and pass to `update_file()`
- [x] 6.5 Write tests for service and pipeline concept awareness (mock BAML calls)

## 7. CLI Commands

- [x] 7.1 Implement `lexi concepts [topic]` command — list all concepts in Rich table or search by topic
- [x] 7.2 Implement `lexi concept new <name> [--tag TAG]...` command — create concept file from template with PascalCase filename
- [x] 7.3 Implement `lexi concept link <concept-name> <source-file>` command — add wikilink to design file
- [x] 7.4 Write CLI tests with `typer.testing.CliRunner` for all three commands (including error cases)
