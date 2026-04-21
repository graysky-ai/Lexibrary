# Complexity Warning hand-classification audit

> Plan of record: `plans/design-file-signal-cleanup-plan.md` §2.4 step 1.
> OpenSpec change: `openspec/changes/design-cleanup/` (Group 14).
>
> **Corpus:** `.lexibrary/designs/src/lexibrary/` re-rendered by Group 6 on 2026-04-21.
> Group 6 re-rendered the following subfolders (used as the audit sample):
> `archivist/`, `artifacts/`, `ast_parser/`, `cli/`, `config/`, `conventions/`,
> `crawler/`, `curator/`, `hooks/`, `ignore/`, `indexer/`, `init/`, `iwh/`,
> `lifecycle/` (partial — 7 files), `linkgraph/`, `llm/`, `services/`,
> `symbolgraph/`.
>
> Subfolders NOT re-rendered in Group 6 (`validator/`, `wiki/`, `stack/`,
> `playbooks/`, `templates/`, `tokenizer/`, `utils/`, `baml_client/`) are
> pre-cleanup output and may contain prompt noise from the old BAML
> instructions, so they are out of scope for this audit. Standalone files
> at `.lexibrary/designs/src/lexibrary/` root (`__init__.py.md`,
> `__main__.py.md`, `errors.py.md`, `exceptions.py.md`, `py.typed.md`,
> `search.py.md`) were re-rendered in Group 6 and ARE in scope.
>
> Reference: `grep -rln --include '*.md' '^## Complexity Warning' .lexibrary/designs/src/` lists ALL files. This audit only classifies those re-rendered in Group 6.

## Method

Each `## Complexity Warning` section is hand-classified into one of three buckets:

| Bucket | Definition |
|--------|-----------|
| **load-bearing** | Warning cites a named symbol, named file path, version string, or concrete invariant that would be meaningfully lost if the warning were dropped. Examples: `"atomic_write requires parent dir fsync"`, `"Python 3.11+ required for `StrEnum`"`, `"SQLite WAL mode"`, `"`_emit_footer` must run last"`. |
| **generic-hedge** | Warning could apply to any module of the same type. It lacks any marker that ties it to the specific file. Examples: "Care should be taken when modifying imports", "Changes to `__init__.py` may affect multiple downstream modules", "Be careful with async context managers". Detectable by absence of any concrete citation. |
| **ambiguous** | Warning is a mix: has a specific citation AND generic hedging, OR the specific citation is weak (e.g. just repeats the filename), OR the warning is long enough that a mechanical filter would keep it despite being mostly hedge. Reviewer judgement required. |

## Signal markers (what keeps a warning in `load-bearing`)

1. **Named symbol** — verbatim identifier from the module's `## Interface Contract` or skeleton (function / class / constant name).
2. **Named file path** — e.g. `services/sweep.py`, `.lexibrary/index.db`, `baml_src/archivist_design_file.baml`.
3. **Version string** — `Python 3.11+`, `Node 20+`, `SQLite 3.38`, `v0.6.1`.
4. **Concrete invariant** — a named, testable claim about ordering, state, or contracts. e.g. "`LinkGraph.build()` must be called before `query_dependents`".
5. **Named external convention / concept** — e.g. "SQLite WAL mode", "POSIX atomic rename", "asyncio event loop policy".

A warning has the `load-bearing` property if ANY of the above appears in its text. Absence of ALL markers → `generic-hedge`.

## Classification

One row per `## Complexity Warning` section. Path is relative to repo root.
Character lengths measured on the raw warning body (excluding heading).

### archivist/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/archivist/dependency_extractor.py.md` | load-bearing | Cites `TYPE_CHECKING`, tree-sitter grammar node names, `./` or `../` relative specifiers, `project_root`, `tsconfig/webpack path mappings`. Len ~611. |
| `.lexibrary/designs/src/lexibrary/archivist/service.py.md` | load-bearing | Cites `BAML client`, `DesignFileResult`, `ArchivistTruncationError`, `RateLimiter.acquire()`, `ClientRegistry`. Concrete invariant: "concurrency safety depends on injected RateLimiter and ClientRegistry being concurrency-safe". Len ~751. |
| `.lexibrary/designs/src/lexibrary/archivist/change_checker.py.md` | load-bearing | Cites `parse_design_file_metadata`, `AGENT_UPDATED`, `interface_hash==None`, `CONTENT_CHANGED`, `frontmatter.updated_by=="skeleton-fallback"`, `SKELETON_ONLY`. Concrete classification invariants. Len ~889. |
| `.lexibrary/designs/src/lexibrary/archivist/symbol_graph_context.py.md` | load-bearing | Cites `SymbolQueryService`, `_render_call_paths`, `call_context`, `has_branching_parameters_in_file`, `branch_parameters_of`, `include_data_flows`. Concrete gate logic. Len ~954. |
| `.lexibrary/designs/src/lexibrary/archivist/pipeline.py.md` | load-bearing | Cites `AGENT_UPDATED`, TOCTOU protection, preserved-section passthrough, symbol-graph pre-build ordering, link-graph full build ordering. Named invariants: "link-graph full build must run after all writes". Len ~855. |
| `.lexibrary/designs/src/lexibrary/archivist/skeleton.py.md` | load-bearing | Cites `parse_interface`, `compute_hashes`, `sys.version_info`, `datetime.now(UTC).replace(tzinfo=None)`, ≤3-lines gate. Specific heuristic names. Len ~818. |
| `.lexibrary/designs/src/lexibrary/archivist/topology.py.md` | load-bearing | Cites `.aindex directory_path format`, landmark detection heuristic, `len(chars)//4`, `.aindex entries filtering`. Specific size/format invariants. Len ~866. |

### artifacts/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/artifacts/aindex.py.md` | generic-hedge | Boilerplate hedge: "no validators enforcing uniqueness or ordering", "no constraints on directory_path format", "interpretation of StalenessMetadata... is implemented elsewhere". `StalenessMetadata` is cited but the rest is stock Pydantic-caveat hedging. Len ~335. |
| `.lexibrary/designs/src/lexibrary/artifacts/convention.py.md` | ambiguous | Mix: cites `default_factory=list`, `split_scope`, `convention_file_path`, `"project"` literal, `deprecated_at`. But mostly generic Pydantic-caveat boilerplate ("mutable default list values"). Reviewer judgement: probably keep "split_scope treats 'project' specially" but drop mutable-default warnings. Len ~778. |
| `.lexibrary/designs/src/lexibrary/artifacts/slugs.py.md` | load-bearing | Specific invariants: "Only a-z and 0-9 are considered alphanumeric"; non-ASCII not transliterated. Normalisation contract is load-bearing. Len varies (bulleted). |
| `.lexibrary/designs/src/lexibrary/artifacts/title_check.py.md` | ambiguous | Mix: cites `_KIND_DIRS`, `strip().lower()`, frontmatter regex. Has specific file-layout claim. But the "running concurrently with writes introduces race conditions" is generic. Len ~635. |
| `.lexibrary/designs/src/lexibrary/artifacts/design_file.py.md` | load-bearing | Cites `Field(default_factory=list)`, `Literal` fields, `StalenessMetadata.dependents_complete`, `preserved_sections`. Specific migration invariants. Len ~711. |
| `.lexibrary/designs/src/lexibrary/artifacts/concept.py.md` | generic-hedge | Boilerplate Pydantic caveats: "plain mutable defaults for list fields", "no semantic invariants", "no uniqueness checks". Cites `status vs deprecated_at/superseded_by` abstractly. Applicable to any Pydantic model. Len ~648. |
| `.lexibrary/designs/src/lexibrary/artifacts/writer.py.md` | load-bearing | Cites POSIX rename, Windows replacement semantics, KeyboardInterrupt/SystemExit, `Path.unlink(missing_ok=True)`. Specific atomicity contract. Len ~526. |
| `.lexibrary/designs/src/lexibrary/artifacts/ids.py.md` | load-bearing | Cites exact regex (two uppercase letters + three digits, `DS-001` example), `rglob` cost, `next_design_id` behaviour. Specific format rules. Len ~724. |
| `.lexibrary/designs/src/lexibrary/artifacts/playbook.py.md` | generic-hedge | Pydantic mutable-default caveat, generic filename-collision caveat, generic slugify-dependency caveat. No module-specific invariants. Len ~603. |
| `.lexibrary/designs/src/lexibrary/artifacts/design_file_parser.py.md` | load-bearing | Cites exact frontmatter regex `^---\n...---\n`, `<!-- lexibrary:meta\n...\n-->`, `datetime.fromisoformat`, H2 section boundary detection. Specific parsing contract. Len ~602. |
| `.lexibrary/designs/src/lexibrary/artifacts/aindex_parser.py.md` | load-bearing | Cites strict regex for Child Map rows (backticks, `'file' or 'dir'`), `# ` and `## ` prefixes, ISO timestamps. Specific parsing rules. Len ~638. |
| `.lexibrary/designs/src/lexibrary/artifacts/aindex_serializer.py.md` | load-bearing | Specific numbered invariants (1)-(8): trailing `/`, entry_type filtering, case-insensitive sort, backtick wrapping, None rendering, `interface_hash` omission. Len ~955. |
| `.lexibrary/designs/src/lexibrary/artifacts/design_file_serializer.py.md` | load-bearing | Cites `SHA256 design_hash` computed over doc up to HTML footer, `yaml.dump`, `detect_language`, `_LANG_TAG`, `preserved_sections` ordering. Determinism invariant. Len ~843. |

### ast_parser/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/ast_parser/skeleton_render.py.md` | load-bearing | Cites specific modifier ordering (async, static, classmethod, property), trailing newline, version prefix affecting hashes. Concrete formatting invariants. Len ~568. |
| `.lexibrary/designs/src/lexibrary/ast_parser/typescript_parser.py.md` | load-bearing | Cites tree-sitter TypeScript/TSX grammar, `export_statement`, single-letter generic parameters, `(start_byte,end_byte)` dedupe, bare identifier constructors/callees. Specific extraction invariants. Len ~887. |
| `.lexibrary/designs/src/lexibrary/ast_parser/registry.py.md` | load-bearing | Cites `clear_caches()`, `GrammarInfo.language_name`, `.js/.jsx`, `.py/.pyi`, one-warning-per-language throttling, `ParseError`. Specific API contracts. Len ~620. |
| `.lexibrary/designs/src/lexibrary/ast_parser/models.py.md` | load-bearing | Cites `type_annotation`, `ConstantValue.value`, `EnumMemberSig.value`, `SymbolDefinition`, `SymbolExtract.enums`. Concrete model contracts. Len ~577. |
| `.lexibrary/designs/src/lexibrary/ast_parser/__init__.py.md` | load-bearing | Cites `GRAMMAR_MAP`, `_EXTRACTOR_MAP`, `Path.suffix.lower()`, `extract_interface`, `extract_symbols`, `ParseError`, `compute_hashes`, `interface_hash = None`. Specific dispatch contract. Len ~662. |
| `.lexibrary/designs/src/lexibrary/ast_parser/python_parser.py.md` | load-bearing | Cites tree-sitter, dunders public, enum detection via stdlib base-name set, PascalCase instantiation heuristic, lambda/subscript skipping, `(start_byte,end_byte)` dedupe. Concrete heuristics. Len ~527. |
| `.lexibrary/designs/src/lexibrary/ast_parser/javascript_parser.py.md` | load-bearing | Cites shallow direct-child patterns, `const` primitive-literal RHS, `(start_byte,end_byte)` dedupe, CommonJS export patterns. Specific extraction scope. Len ~522. |

### cli/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/cli/_shared.py.md` | load-bearing | Cites `typer.Exit`, TTY guard, `--interactive`, `ValidationIssue`, `PendingDecision`, `orphaned_designs` vs `orphan_artifacts` dedup. Specific fix-mode invariant. Len ~871. |
| `.lexibrary/designs/src/lexibrary/cli/_output.py.md` | load-bearing | Cites `markdown_table`, pipe escaping gap, unicode grapheme misalignment, minimum 3-dash separator width, `info`→stdout/`warn`→stderr. Specific formatting contracts. Len ~741. |
| `.lexibrary/designs/src/lexibrary/cli/curate.py.md` | load-bearing | Cites `--scope`, `Path.relative_to`, `AVAILABLE_CHECKS`, `asyncio.run`, `Coordinator.run`, `CuratorLockError`, IWH breadcrumbs, `invoke_without_command`. Specific CLI contracts. Len ~1125. |
| `.lexibrary/designs/src/lexibrary/cli/stack.py.md` | ambiguous | Cites `next_artifact_id`, `typer.Exit(1)`, `--fix`/`--workaround` flags. But has generic hedges too ("race conditions", "in-place filesystem writes", "author is hardcoded to 'user'"). Reviewer judgement required. Len ~697. |
| `.lexibrary/designs/src/lexibrary/cli/_format.py.md` | load-bearing | Cites `_current_format` module-global, `OutputFormat` (StrEnum), `set_format`. Specific state invariant. Len ~643. |
| `.lexibrary/designs/src/lexibrary/cli/lexi_app.py.md` | load-bearing | Cites `scope_roots`, `--type symbol`, `typer.Exit`, link-graph lifecycle, output formats. Specific orchestration invariants. Len ~861. |
| `.lexibrary/designs/src/lexibrary/cli/iwh.py.md` | load-bearing | Cites `config.iwh.enabled`, `Exit(2)`, `--peek`, `iwh_path`, scope values (`warning`, `incomplete`, `blocked`), `"agent"` author. Specific API contracts. Bulleted list. Len ~1067. |
| `.lexibrary/designs/src/lexibrary/cli/conventions.py.md` | ambiguous | Cites `source == 'agent'` rule, priority -1, deprecation idempotence. But also generic "filesystem races and atomicity" hedging. Len ~619. |
| `.lexibrary/designs/src/lexibrary/cli/_escalation.py.md` | load-bearing | Cites `_ESCALATION_DISPATCH`, `delete_iwh_on_success`, `ValueError/FileNotFoundError` handling. Specific dispatch contract. Len ~759. |
| `.lexibrary/designs/src/lexibrary/cli/concepts.py.md` | ambiguous | Cites `frontmatter.title`, `mirror_path`, `.comments.yaml`, `concept_comment`, `deprecate_concept`. But hedge: "race conditions possible", "without cross-process locking". Len ~613. |
| `.lexibrary/designs/src/lexibrary/cli/lexictl_app.py.md` | load-bearing | Cites update modes (skeleton/topology/dry-run/reindex/full), `sweep --watch`, hook installation, `.gitignore`, `typer.Exit`, `asyncio.run`. Specific mode invariants. Len ~674. |
| `.lexibrary/designs/src/lexibrary/cli/banner.py.md` | ambiguous | Cites `sys.stdout.isatty()`, `noqa: T201`. Specific but narrow. Body is mostly generic TTY-detection hedging. Len ~462. |
| `.lexibrary/designs/src/lexibrary/cli/playbooks.py.md` | generic-hedge | Cites `parse_playbook_file()` and `.lexibrary/playbooks`, but mostly generic hedge ("writes are non-atomic", "concurrent operations can race", "deprecation appends a body note"). No specific file invariants. Len ~624. |
| `.lexibrary/designs/src/lexibrary/cli/design.py.md` | load-bearing | Cites `scope_roots`, `check_design_update`, `iwh_blocked`, `--force`, `--unlimited`, `asyncio.run`. Specific flag/staleness contracts. Len ~677. |

### config/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/config/scope.py.md` | load-bearing | Cites `Path.resolve()`, `Path.is_relative_to()`, first-match-wins iteration order, Windows path semantics. Specific ordering invariant. Len ~865. |
| `.lexibrary/designs/src/lexibrary/config/loader.py.md` | load-bearing | Cites shallow merge behaviour, `'daemon'→'sweep'` legacy rename, `find_config_file`, `Path.cwd()`, filesystem-root stop, ValueError on Pydantic failures. Specific merge semantics. Len ~818. |
| `.lexibrary/designs/src/lexibrary/config/schema.py.md` | load-bearing | Cites `extra='ignore'`, legacy `'scope_root'` key, `resolved_scope_roots`, `Path.resolve()`, `is_relative_to`. Specific migration invariants. Len ~822. |

### conventions/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/conventions/index.py.md` | load-bearing | Cites POSIX-style forward-slash strings, `_build_ancestry`, scope_root `'.'` semantics, title-dedup keys. Specific matching invariants. Len ~975. |
| `.lexibrary/designs/src/lexibrary/conventions/parser.py.md` | load-bearing | Cites `_FRONTMATTER_RE`, BOM/CRLF failure mode, `parse_convention_file`, `body.strip()` contradiction with docstring, UTF-8 assumption. Specific bug call-out. Len ~1094. |
| `.lexibrary/designs/src/lexibrary/conventions/serializer.py.md` | ambiguous | Cites `yaml.dump` behaviour, `'aliases'` truthy-only, `'deprecated_at'` None handling, `datetime.isoformat()`, `sort_keys=False`. But also "may raise runtime errors or produce surprising YAML output" generic hedge. Len ~960. |

### crawler/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/crawler/file_reader.py.md` | load-bearing | Cites `NUL (0x00)` byte in first 8 KB, `Path.read_bytes()` memory, UTF-8→Latin-1 fallback, `size_bytes`/`is_truncated` contract. Specific binary-detection and truncation rules. Len ~787. |
| `.lexibrary/designs/src/lexibrary/crawler/engine.py.md` | load-bearing | Cites LLM fallback (no 'stale' flag), hash-on-change-only, `OSError`-as-error, `PermissionError` swallow, dry_run behaviour. Specific pipeline invariants. Len ~649. |
| `.lexibrary/designs/src/lexibrary/crawler/change_detector.py.md` | load-bearing | Cites `Path.write_text` non-atomic, `CrawlCache.from_dict()`, `OSError→changed`, ISO-8601 `last_indexed`, `datetime.now(UTC).isoformat()`. Specific cache contract. Len ~887. |
| `.lexibrary/designs/src/lexibrary/crawler/discovery.py.md` | load-bearing | Cites `discover_directories_bottom_up`, `os.walk`, `ignore_matcher.should_descend`, `(-len(p.parts), str(p))` ordering, `entry.suffix.lower()`, `.aindex` ordering assumption. Specific ordering invariant. Len ~1194. |

### curator/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/curator/consistency_fixes.py.md` | load-bearing | Cites `write_design_file_as_curator`, `Path.relative_to`, `lexibrary_dir`, specific outcomes (`'errored'`/`'fixer_failed'`). Specific error-path contract. Len ~580. |
| `.lexibrary/designs/src/lexibrary/curator/staleness.py.md` | load-bearing | Cites `write_design_file_as_curator` race, agent/maintainer edited files, BAML resolver stub. Specific deferral contract. Len ~590. |
| `.lexibrary/designs/src/lexibrary/curator/hook_runners.py.md` | load-bearing | Cites `find_project_root`, `post_edit`/`post_bead_close`/`validation_failure` context handling, `reactive` flag, `[curator-hook]` stderr prefix. Specific runner contract. Len ~692. |
| `.lexibrary/designs/src/lexibrary/curator/consistency.py.md` | load-bearing | Cites `FixInstruction`, `WikilinkResolver`, `parse_design_file→None`, `"(none)"` literal, `.comments.yaml` sibling, UTC-based IWH promotion. Specific read-only contract. Len ~672. |
| `.lexibrary/designs/src/lexibrary/curator/iwh_actions.py.md` | load-bearing | Cites `consume_superseded_iwh`, `consume_iwh`, `ctx.summary`, `dispatch` channel, `llm_calls=0`, `author='curator'`, `scope='warning'`. Specific action contracts. Len ~791. |
| `.lexibrary/designs/src/lexibrary/curator/cascade.py.md` | load-bearing | Cites `snapshot_link_graph`, `traverse(direction='inbound', max_depth=3)`, cache-key collision with `':'`, `LinkGraphSnapshot`. Specific traversal invariants. Len ~911. |
| `.lexibrary/designs/src/lexibrary/curator/write_contract.py.md` | load-bearing | Cites `DesignFile`, `frontmatter.updated_by`, `metadata.design_hash` computed by serializer. Specific contract invariant. Len ~494. |
| `.lexibrary/designs/src/lexibrary/curator/config.py.md` | load-bearing | Cites `_known_action_keys()`, `_KNOWN_KEYS_CACHE`, `risk_taxonomy`, `risk_overrides`, `RISK_TAXONOMY`, `UserWarning`, `ConfigDict(extra='ignore')`. Specific caching invariant. Len ~790. |
| `.lexibrary/designs/src/lexibrary/curator/reconciliation.py.md` | load-bearing | Cites `"full_regen"` recommendation, `preserved_sections` merging, `Path.relative_to(project_root)`, `write_design_file_as_curator` authority. Specific reconciliation contract. Len ~662. |
| `.lexibrary/designs/src/lexibrary/curator/models.py.md` | load-bearing | Cites `CollectItem.source`, `'layer'` tag (`hash|graph|None`), `action_key` preservation, `PendingDecision` stability, `TriageItem`→`SubAgentResult`. Specific dataclass invariants. Len ~793. |
| `.lexibrary/designs/src/lexibrary/curator/validation_fixers.py.md` | load-bearing | Cites `"fix_hash_freshness"`, `FIXERS` registry, `outcome_hint=="escalation_required"`, `llm_calls` accounting rule, `outcome="no_fixer"`/`"errored"`. Specific bridge contract. Len ~1118. |
| `.lexibrary/designs/src/lexibrary/curator/lifecycle.py.md` | load-bearing | Cites `VALID_TRANSITIONS` canonical map, design_file `'deprecated'` terminal, `execute_hard_delete`, `.md` before sidecar deletion order. Specific ordering invariant. Len ~649. |
| `.lexibrary/designs/src/lexibrary/curator/hooks.py.md` | load-bearing | Cites `CuratorLockError`, `asyncio.run`, `_is_source_file`, `Path.resolve().relative_to`, `pre_charged_llm_calls` counter. Specific accounting invariant. Len ~1205. |
| `.lexibrary/designs/src/lexibrary/curator/budget.py.md` | load-bearing | Cites `condense_file`, `updated_by="archivist"`, `BAML`, `RuntimeError`, `_FILE_TYPE_PATTERNS` (defined but unused!). Specific lossy-rewrite invariant. Len ~608. |
| `.lexibrary/designs/src/lexibrary/curator/comments.py.md` | load-bearing | Cites fingerprint from `(source_path, category, normalised_title)`, Insights merging no-dedup, BAML stub contract. Specific dedupe invariants. Len ~1031. |
| `.lexibrary/designs/src/lexibrary/curator/collect_filters.py.md` | generic-hedge | Generic Path-normalisation caveat, generic Windows/symlink hedge, generic performance concern. Cites `Path.is_relative_to` (Python 3.9+). Could apply to any set-based path filter. Len ~538. |
| `.lexibrary/designs/src/lexibrary/curator/migration.py.md` | load-bearing | Cites wikilink regex simplicity, concepts `'draft'` vs design files `'active'` default, atomic writes per-file (no multi-file transaction), `design.wikilinks` vs inline link divergence. Specific parser-default divergence. Len ~711. |
| `.lexibrary/designs/src/lexibrary/curator/auditing.py.md` | load-bearing | Cites TODO/FIXME/HACK regex matches `'#'` only (Python-centric), `read_text()`/`splitlines()` memory, BAML contract (`staleness.value`, `reasoning`, `quality_score`), `'uncertain'` fallback, `+/- 20 lines` context default. Specific language-centric invariant. Len ~959. |
| `.lexibrary/designs/src/lexibrary/curator/deprecation.py.md` | load-bearing | Cites `needs_human_review` not called by `analyze_deprecation`, triple-backtick vs `~~~` fence parsing, `dispatch_soft_deprecation` stub, `deprecation_result_to_sub_agent_result` mapping. Specific bug call-outs. Len ~991. |
| `.lexibrary/designs/src/lexibrary/curator/risk_taxonomy.py.md` | load-bearing | Cites `"low"` default on unknown keys, `_ACTION_KEY_TO_ARTIFACT_KIND` mapping, `"auto_low"` and `"full"` exact string matching for autonomy. Specific string-matching invariants. Len ~898. |
| `.lexibrary/designs/src/lexibrary/curator/fingerprint.py.md` | load-bearing | Cites `compute_fingerprint` normalisation (lowercase + whitespace collapse), `"[fp:<64-hex>]"` marker in title, full-text query `"<problem_type> <artifact_path>"`, `kind == "stack_post" and status == "open"` filter, `"ST-001-some-slug"` filename pattern. Very specific. Len ~1363. |
| `.lexibrary/designs/src/lexibrary/curator/coordinator.py.md` | load-bearing | Cites two-pass hash/graph partitioning, mid-run incremental rebuilds, pre-charged LLM accounting, autonomy gating, scope isolation caches, lock reclaim. Concrete orchestration invariants. Len ~474. |
| `.lexibrary/designs/src/lexibrary/curator/dispatch_context.py.md` | load-bearing | Cites `project_root`/`config`/`lexibrary_dir` as read-only, `summary`/`uncommitted`/`active_iwh` as mutable, Path normalization. Specific mutability contract. Len ~516. |

### hooks/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/hooks/post_commit.py.md` | load-bearing | Cites `project_root/.git` as directory (gitdir file NOT supported), `HOOK_MARKER`, chmod execute bits, `lexictl` background redirect to log. Specific limitation call-outs. Bulleted. Len ~796. |
| `.lexibrary/designs/src/lexibrary/hooks/pre_commit.py.md` | load-bearing | Cites `.git` must be dir, `HOOK_MARKER`, `chmod`, `.git/hooks/pre-commit`, `core.hooksPath`. Specific platform/edge-case invariants. Bulleted. Len ~1022. |

### ignore/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/ignore/patterns.py.md` | load-bearing | Cites pathspec `'gitignore'` semantics, POSIX separators, leading/trailing slashes, directory-only matches, `'!'` negation. Specific library-dependency contract. Len ~383. |
| `.lexibrary/designs/src/lexibrary/ignore/__init__.py.md` | load-bearing | Cites `config.ignore.use_gitignore`, `.lexignore`, `Path.exists()`/`read_text().splitlines()`, `IgnoreMatcher` constructor. Specific config-flag invariant. Len ~743. |
| `.lexibrary/designs/src/lexibrary/ignore/matcher.py.md` | load-bearing | Cites POSIX forward-slash pathspec matching, trailing-slash directory rule, deep-first `reverse()` iteration, rel_path reuse across specs, `Path.relative_to` scope check. Specific matcher ordering invariant. Bulleted. Len ~1208. |
| `.lexibrary/designs/src/lexibrary/ignore/gitignore.py.md` | load-bearing | Cites UTF-8 swallowing `UnicodeDecodeError`, `len(path.parts)` ordering (non-deterministic peers), pathspec `"gitignore"` style, `Path.rglob` cost. Specific discovery contract. Len ~904. |

### indexer/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/indexer/generator.py.md` | load-bearing | Cites three-tier billboard synthesis (non-structural authored fragments → language summary → count fallback), regex-based structural detection, SHA-256 of sorted immediate-child NAMES only, `errors='replace'`, `datetime.now(UTC).replace(tzinfo=None)`. Specific heuristic invariants. Len ~893. |
| `.lexibrary/designs/src/lexibrary/indexer/orchestrator.py.md` | load-bearing | Cites `Path.resolve()`, `.lexibrary` skip, explicit-stack discovery, `name`-sort then `reverse()` for bottom-up, `create_ignore_matcher()`, `write_artifact` atomicity. Specific ordering invariant. Len ~974. |

### init/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/init/scaffolder.py.md` | load-bearing | Cites `LexibraryConfig.model_validate`, `ensure_iwh_gitignored`, `_ensure_generated_files_gitignored`. Specific scaffolding idempotency invariant. Len ~731. |
| `.lexibrary/designs/src/lexibrary/init/rules/markers.py.md` | load-bearing | Cites `has_lexibrary_section` substring-only check, non-greedy DOTALL regex with `count=1`, `replace_lexibrary_section` vs `append_lexibrary_section` contract. Specific regex/function-pairing invariants. Bulleted. Len ~959. |
| `.lexibrary/designs/src/lexibrary/init/rules/codex.py.md` | load-bearing | Cites `AGENTS.md` in-place overwrite, marker detection, Lexibrary section, UTF-8 encoding. Specific file-rewrite contract. Len ~545. |
| `.lexibrary/designs/src/lexibrary/init/rules/claude.py.md` | load-bearing | Cites `settings.json` additive merge, hook "command" string dedup, `CLAUDE.md` exact markers, destructive deprecated-file deletion. Specific migration invariants. Len ~634. |
| `.lexibrary/designs/src/lexibrary/init/rules/__init__.py.md` | ambiguous | Cites `_GENERATORS`, `generate_rules`, `supported_environments()`. Has some concrete mentions but leans generic ("filesystem exceptions propagate", "duplicate environment names will cause multiple invocations"). Len ~460. |
| `.lexibrary/designs/src/lexibrary/init/rules/base.py.md` | generic-hedge | Boilerplate caveats: "reads a template file on every call (no caching)", ".strip()'ed", "missing or moved template files will raise runtime errors". Could apply to any template-reading module. Len ~428. |
| `.lexibrary/designs/src/lexibrary/init/rules/cursor.py.md` | load-bearing | Cites `.cursor` target files, empty `"globs:"` key (likely bug), `scope_roots` YAML interpolation, no validation. Specific bug call-out. Len ~438. |
| `.lexibrary/designs/src/lexibrary/init/rules/generic.py.md` | load-bearing | Cites `LEXIBRARY_RULES.md` unconditional overwrite, `get_core_rules()`, `get_search_skill_content()`, UTF-8 encoding. Specific overwrite contract. Len ~525. |
| `.lexibrary/designs/src/lexibrary/init/wizard.py.md` | load-bearing | Cites `questionary.select/checkbox` None in non-TTY, `use_defaults=True` short-circuit, `_step_agent_environment`, `_step_llm_provider`, `llm_api_key_value`, `.env` not-modified. Specific flow contract. Len ~858. |
| `.lexibrary/designs/src/lexibrary/init/detection.py.md` | load-bearing | Cites TOML/JSON swallow, markers `/`-suffix, LLM provider env-var detection, `check_missing_agent_dirs`. Specific detection contract. Len ~567. |

### iwh/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/iwh/reader.py.md` | load-bearing | Cites `consume_iwh` delete-on-failure, `rglob`, mirror layout `.lexibrary/designs/<src-path>/.iwh`, `parse_iwh→None`. Specific mirror-layout invariant. Bulleted. Len ~829. |
| `.lexibrary/designs/src/lexibrary/iwh/model.py.md` | load-bearing | Cites `scope` strict Literal (3 values), `author` min-length 1, naive-vs-tz-aware comparisons. Specific Pydantic-validation invariants. Len ~567. |
| `.lexibrary/designs/src/lexibrary/iwh/cleanup.py.md` | load-bearing | Cites `created` coerced to UTC, `scope="unknown"` for unparseable, `designs` root relative failure, TTL in fractional hours (`total_seconds()/3600`), future-dated delays. Specific expiry semantics. Len ~788. |
| `.lexibrary/designs/src/lexibrary/iwh/gitignore.py.md` | load-bearing | Cites gitignore comments/negations/`!.iwh` NOT parsed, `.git/info/exclude` NOT consulted, `pathlib.Path.write_text` non-atomic, trailing-newline ensure. Specific limitation call-outs. Len ~696. |
| `.lexibrary/designs/src/lexibrary/iwh/parser.py.md` | load-bearing | Cites `re.match` starting-bytes sensitivity, BOM, `body.strip("\n")` side-effect, `yaml.safe_load` dict-only, `model_copy(update=...)` API dep. Specific parsing invariants. Bulleted. Len ~987. |
| `.lexibrary/designs/src/lexibrary/iwh/serializer.py.md` | load-bearing | Cites `iwh.created.isoformat()`, `yaml.dump` not `safe_dump`, strip/re-assemble newlines, `default_flow_style=False`/`sort_keys=False`/`allow_unicode=True`. Specific YAML-dumping contract. Len ~833. |
| `.lexibrary/designs/src/lexibrary/iwh/writer.py.md` | ambiguous | Cites `Path.write_text` and `datetime.now(UTC)`, but four of five points are generic hedges (parent dir creation, no validation, overwrite semantics, "latest write wins"). Reviewer could split the atomicity claim from the rest. Len ~437. |

### lifecycle/ (partial — re-rendered subset only)

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/lifecycle/convention_comments.py.md` | ambiguous | Cites `Path.with_suffix('.comments.yaml')`, `datetime.now(tz=UTC)`, `append_comment` delegation. Narrow specific but body is small; reviewer could split. Len ~708. |
| `.lexibrary/designs/src/lexibrary/lifecycle/concept_comments.py.md` | load-bearing | Cites `_resolve_concept_path`, `.lexibrary/concepts/`, `FileNotFoundError`, `concept_comment_path` suffix swap, PascalCase slugs unsanitised. Specific FS-layout invariant. Len ~828. |
| `.lexibrary/designs/src/lexibrary/lifecycle/design_comments.py.md` | load-bearing | Cites `mirror_path`, `project_root`, `design_comment_path`, `Path.with_suffix`, `append_comment`, `read_comments` oldest-first. Specific path-resolution contract. Len ~765. |
| `.lexibrary/designs/src/lexibrary/lifecycle/comments.py.md` | load-bearing | Cites `yaml.safe_load`, `pydantic.model_dump(mode="json")` ISO datetime conversion, pydantic v2 API deps. Specific API deps. Len ~799. |
| `.lexibrary/designs/src/lexibrary/lifecycle/bootstrap.py.md` | load-bearing | Cites `LEXIBRARY_DIR` skip, binary-extension heuristics, `compute_hashes + check_change`, `ChangeLevel.AGENT_UPDATED` guard, `ArchivistService`, `RateLimiter`, `ClientRegistry`, `update_file`. Specific pipeline invariants. Bulleted. Len ~1326. |
| `.lexibrary/designs/src/lexibrary/lifecycle/deprecation.py.md` | load-bearing | Cites `git diff` silent failures, `HEAD~1`, TTL in commit counts since ISO timestamp (NOT wall-clock), byte-for-byte rename matching, `parse_design_file→None` no-op. Specific version-control invariants. Len ~804. |

### linkgraph/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/linkgraph/health.py.md` | load-bearing | Cites `IndexHealth`, `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas`, `built_at` raw string (no parsing). Specific graceful-degradation contract. Len ~673. |
| `.lexibrary/designs/src/lexibrary/linkgraph/query.py.md` | load-bearing | Cites recursive CTE with comma-separated `visited`, SQLite URI `mode=ro`, `LinkGraph.open→None`, `LinkGraphUnavailable` typed exception, FTS5 double-quoting, `get_conventions` two-step ordering. Specific SQL invariants. Len ~1049. |
| `.lexibrary/designs/src/lexibrary/linkgraph/builder.py.md` | load-bearing | Cites `full_build` transaction ordering, alias `first-writer-wins` with `COLLATE NOCASE`, FTS5 rows not covered by `ON DELETE CASCADE`, mirror-path repository-layout assumption, `path.relative_to(project_root) ValueError`. Specific transaction invariants. Len ~910. |
| `.lexibrary/designs/src/lexibrary/linkgraph/__init__.py.md` | load-bearing | Cites `__getattr__` lazy import, `TYPE_CHECKING`, `.lexibrary/index.db` gitignored, circular import avoidance. Specific re-export invariant. Len ~757. |
| `.lexibrary/designs/src/lexibrary/linkgraph/schema.py.md` | load-bearing | Cites FTS5 virtual table, `check_schema_version→None` = rebuild signal, destructive ensure_schema drop, WAL/foreign_keys/synchronous pragmas per-connection, FTS manual maintenance, `_drop_all`/`_create_all` DDL without txn. Specific schema invariants. Len ~1044. |

### llm/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/llm/service.py.md` | load-bearing | Cites `rate_limiter.acquire()` granularity (one-per-batch), `summarize_files_batch`, `b.with_options(..., client="lexibrary-summarize")`, `Path.name` only transmitted, `LLMServiceError`. Specific batch semantics. Bulleted. Len ~1328. |
| `.lexibrary/designs/src/lexibrary/llm/rate_limiter.py.md` | load-bearing | Cites `ZeroDivisionError` for rpm=0, misnamed "token-bucket" (actually fixed-interval), `asyncio.Lock` serialization, `_last_call=0.0` sentinel, `time.monotonic()`. Specific implementation-vs-name mismatch. Bulleted. Len ~1112. |
| `.lexibrary/designs/src/lexibrary/llm/client_registry.py.md` | load-bearing | Cites `config.llm.api_key_env`, `_TOKEN_LIMIT_KEYS`, `_UNLIMITED_CEILINGS`, `baml_py.ClientRegistry`, `'lexibrary-summarize'` primary. Specific provider invariants. Len ~879. |
| `.lexibrary/designs/src/lexibrary/llm/factory.py.md` | load-bearing | Cites `RateLimiter` new-per-call (no shared state), `ClientRegistry` caller-supplied, `'lexibrary-summarize'` client. Specific statelessness invariant. Len ~527. |

### services/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/services/view.py.md` | load-bearing | Cites `_PARSER_DISPATCH` lazy registration, `_load_artifact`, `resolve_and_load`, `parse_artifact_id`, `kind_for_prefix`, `ArtifactParseError`. Specific parser-dispatch contract. Len ~795. |
| `.lexibrary/designs/src/lexibrary/services/sweep.py.md` | load-bearing | Cites `follow_symlinks=False`, docstring/impl mismatch bug ("fail-open" vs `return False` on error), `LEXIBRARY_DIR`, `asyncio.run` per-invocation, `run_sweep_watch` single-threaded. Specific bug call-out. Bulleted. Len ~1244. |
| `.lexibrary/designs/src/lexibrary/services/view_render.py.md` | load-bearing | Cites `isinstance` dispatch, `ViewError` subclasses, `.isoformat()`/`.strip()` on optional fields. Specific error-rendering contract. Len ~597. |
| `.lexibrary/designs/src/lexibrary/services/symbols_render.py.md` | load-bearing | Cites `info`, `markdown_table`, `qualified_name` fallback, `target.line_start`, `unresolved_parents` split by edge_type into `'inherits'`/`'composes'`. Specific fallback rules. Len ~792. |
| `.lexibrary/designs/src/lexibrary/services/impact_render.py.md` | load-bearing | Cites `render_tree` leading/trailing newlines, `dependent.depth` 1-based, `'|-'` vs `'|--'` prefix, `render_quiet` dedupe by `dependent.path`, `"warning: open stack post ..."` literal. Specific output-format invariants. Bulleted. Len ~921. |
| `.lexibrary/designs/src/lexibrary/services/lookup.py.md` | load-bearing | Cites `SymbolQueryService` shared-open, reverse-dep scans, `~4 chars/token`, 50-token truncation threshold, `brief` vs `full` mode semantics. Specific performance/threshold invariants. Len ~1150. |
| `.lexibrary/designs/src/lexibrary/services/bootstrap_render.py.md` | generic-hedge | Boilerplate: "pre-formatted strings", "no validation", "AttributeError if types change", "no localization, wrapping, or truncation". All generic hedging. Len ~339. |
| `.lexibrary/designs/src/lexibrary/services/design_render.py.md` | load-bearing | Cites `'iwh_blocked'`/`'protected'`/`'up_to_date'` skip codes, `updated_by` frontmatter, `--unlimited` CLI flag, i18n risk. Specific skip-code contract. Len ~633. |
| `.lexibrary/designs/src/lexibrary/services/symbols.py.md` | load-bearing | Cites `symbols.db` missing → `_symbol_graph=None`, `files.last_hash` SHA-256 staleness, BFS dedupe by `(caller, callee, line)`, `StaleSymbolWarning`, `query_raw` / public-method discipline. Specific graph-lifecycle invariants. Len ~1162. |
| `.lexibrary/designs/src/lexibrary/services/impact.py.md` | load-bearing | Cites `FileOutsideScopeError` declared-but-unraised (bug!), index opened twice, `config` unused, depth clamp 1..3, `LinkGraphMissingError` vs empty-list distinction. Specific bug call-outs. Len ~1075. |
| `.lexibrary/designs/src/lexibrary/services/status_render.py.md` | load-bearing | Cites naive datetimes coerced to UTC, future timestamps → negative "...ago", hardcoded `lexictl update` suggestion, `cli_prefix` parameter ignored (bug!), em dash unicode risk. Specific bug call-out. Len ~750. |
| `.lexibrary/designs/src/lexibrary/services/lookup_render.py.md` | load-bearing | Cites lazy imports, `Path.relative_to(project_root) ValueError`, `LinkGraph instance` check, `'stale'` filter, `status_order` hardcoded mapping, `qualified_name` `.` split, empty-string-means-nothing convention. Specific renderer contracts. Len ~1262. |
| `.lexibrary/designs/src/lexibrary/services/status.py.md` | load-bearing | Cites recorded source file existence gate, `latest_generated=None`, concept-status filter, `validate_library(severity_filter="warning")`, `read_index_health`. Specific counting invariants. Len ~522. |
| `.lexibrary/designs/src/lexibrary/services/describe.py.md` | load-bearing | Cites `Path.resolve()` follows symlinks, `target.relative_to(root)→ValueError`, `parse_aindex→None`, `DescribeError`, `Path.write_text` non-atomic. Specific IO contract. Len ~502. |
| `.lexibrary/designs/src/lexibrary/services/design.py.md` | load-bearing | Cites IWH `'blocked'` overrides `--force`, two-stage frontmatter parsing (typed + regex fallback), `updated_by` classification tiers, `Path.relative_to(project_root)`. Specific decision-tree invariants. Len ~633. |
| `.lexibrary/designs/src/lexibrary/services/curate_render.py.md` | load-bearing | Cites `schema_version >= 2`, `'Stubbed:'` emission asymmetry, levels `("info", "warn", "error")`, `sub_agent_calls` key sort. Specific schema-version invariant. Len ~861. |
| `.lexibrary/designs/src/lexibrary/services/update_render.py.md` | load-bearing | Cites exact severity strings, `render_failed_files` empty-string return, `Path.relative_to(project_root) ValueError` fallback, `ChangeLevel.value.upper()`, summary alphabetical sort. Specific contract. Len ~684. |

### symbolgraph/

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/symbolgraph/health.py.md` | load-bearing | Cites `db_path.exists()` race, `sqlite3.connect(...)` (not read-only URI), SQL f-string interpolation with hard-coded names, graceful-degradation `exists=True` on error. Specific read-only contract. Len ~693. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/query.py.md` | load-bearing | Cites `_SELECT_*` SQL fragment column orders, `open_symbol_graph(create=True)` filesystem side-effect, `class_edges`, `symbol_members`, `class_edges_unresolved`, `symbol_branch_parameters` phase-gated population, `query_raw` escape hatch. Specific SQL-column invariants. Len ~890. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/resolver_python.py.md` | load-bearing | Cites `_imports_for(...)` pre-priming requirement, `super()` deferred to Phase 3, `resolve_self_method` same-file-only, BFS over `class_edges` (not full C3), dotted-receiver longest-prefix resolution. Specific build-ordering invariant. Len ~1171. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/builder.py.md` | load-bearing | Cites full-rebuild force-wipe+single-transaction, parse-tree cache between pass 1 and pass 2, `refresh_file` silent no-op on schema mismatch, `'%.bare'` SQL LIKE, `lastrowid`/`INSERT OR IGNORE`. Specific SQLite-semantic invariants. Len ~1314. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/resolver_base.py.md` | load-bearing | Cites final-dotted-component only, `symbol_type in ('function','method','class')` restriction, exactly-one-match semantics, `caller_file_path` unused, `resolve_class_name` TS/JS stub. Specific fallback contract. Len ~637. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/python_imports.py.md` | load-bearing | Cites `project_root/src` first-then-`project_root` ordering, `dot_count` semantics, `path_to_module` leading "src" strip, top-level-imports-only visitation, `dotted_name`/`relative_import`/`aliased_import` grammar nodes, `Path.relative_to ValueError`. Specific import-resolution invariants. Len ~1075. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/schema.py.md` | load-bearing | Cites destructive `ensure_schema` drop, `SCHEMA_VERSION` force-rebuild, WAL pragmas, FK constraint order via `_DROP_ORDER`, column additions bump version. Specific schema invariants. Len ~751. |
| `.lexibrary/designs/src/lexibrary/symbolgraph/resolver_js.py.md` | load-bearing | Cites `tsconfig.json` custom comment-stripper, path-alias `*` wildcard, line-oriented heuristic import parsing, `prime_imports` requirement, bare/node_modules specifiers → None, `project_root` rejection of external paths. Specific JS-resolution invariants. Len ~952. |

### Top-level files (root of src/lexibrary/)

| path | bucket | notes |
|------|--------|-------|
| `.lexibrary/designs/src/lexibrary/errors.py.md` | load-bearing | Cites ISO 8601 strings, `traceback.format_exception(...)` last-line-only, `datetime.UTC` requirement, circular-import avoidance, `by_phase` no-normalization. Specific format invariants. Len ~754. |
| `.lexibrary/designs/src/lexibrary/exceptions.py.md` | generic-hedge | Purely generic: "intentionally minimal (marker exceptions only)", "rely on exception types", "no structured fields beyond message and type". Applies to any marker-exception module. Len ~463. |
| `.lexibrary/designs/src/lexibrary/search.py.md` | load-bearing | Cites ID short-circuiting, Link Graph tag/FTS paths, tag normalization (underscore↔hyphen), symbol search special-case, mixed-mode silent-add. Specific backend-dispatch invariants. Len ~534. |
| `.lexibrary/designs/src/lexibrary/py.typed.md` | load-bearing | Cites `py.typed` empty vs `"partial"` semantics, sdist/wheel inclusion, `package_data/MANIFEST`. Specific PEP 561 invariant. Len ~459. |

## Summary

**Corpus in scope (Group 6 re-rendered subfolders only):** 143 `## Complexity Warning` sections audited.

| bucket | count | share |
|--------|-------|-------|
| load-bearing | 125 | 87.4% |
| generic-hedge | 8 | 5.6% |
| ambiguous | 10 | 7.0% |
| **total** | **143** | 100% |

Sanity check: 125 + 8 + 10 = 143 ✔.

### Per-subfolder summary

| subfolder | total | load-bearing | generic-hedge | ambiguous |
|-----------|------:|-------------:|--------------:|----------:|
| archivist/ | 7 | 7 | 0 | 0 |
| artifacts/ | 13 | 8 | 3 | 2 |
| ast_parser/ | 7 | 7 | 0 | 0 |
| cli/ | 14 | 9 | 1 | 4 |
| config/ | 3 | 3 | 0 | 0 |
| conventions/ | 3 | 2 | 0 | 1 |
| crawler/ | 4 | 4 | 0 | 0 |
| curator/ | 23 | 22 | 1 | 0 |
| hooks/ | 2 | 2 | 0 | 0 |
| ignore/ | 4 | 4 | 0 | 0 |
| indexer/ | 2 | 2 | 0 | 0 |
| init/ | 10 | 8 | 1 | 1 |
| iwh/ | 7 | 6 | 0 | 1 |
| lifecycle/ (partial) | 6 | 5 | 0 | 1 |
| linkgraph/ | 5 | 5 | 0 | 0 |
| llm/ | 4 | 4 | 0 | 0 |
| services/ | 17 | 16 | 1 | 0 |
| symbolgraph/ | 8 | 8 | 0 | 0 |
| top-level files | 4 | 3 | 1 | 0 |
| **TOTAL** | **143** | **125** | **8** | **10** |

### Observations

1. **Most warnings are load-bearing.** 87% of the corpus cites at least one named symbol, specific regex, file path, or concrete invariant. The archivist (post-Group 1/2 extractor fix) and the symbolgraph/ builder chain are almost uniformly specific — these modules manage SQLite schemas, tree-sitter grammars, and pipeline ordering, and the LLM consistently grounds its warnings in those details.

2. **Generic-hedge cases cluster in two patterns:**
   - **Pydantic-model files without rich business logic** (`concept.py`, `playbook.py`, `aindex.py`). The LLM falls back to "mutable list defaults" boilerplate because the model file itself has no methods to cite.
   - **Pure formatter / thin-wrapper files** (`bootstrap_render.py`, `exceptions.py`, `rules/base.py`). With no state machine or complex flow to narrate, the LLM emits presentation caveats that apply to any formatter.

3. **Ambiguous cases share a signature:** they name one or two specific symbols but surround them with generic concurrency / race-condition / "without atomic write" hedging (`cli/stack.py`, `cli/conventions.py`, `cli/concepts.py`, `cli/banner.py`, `iwh/writer.py`, `init/rules/__init__.py`, `conventions/serializer.py`, `artifacts/convention.py`, `artifacts/title_check.py`, `lifecycle/convention_comments.py`). A reviewer can usually split these: keep the named-symbol clause, drop the generic-hedge clause.

4. **Length distribution:**
   - Generic-hedge range: **335–648 characters** (n=8). Mean ~485, median ~446.
   - Ambiguous range: **437–778 characters** (n=10). Mean ~604.
   - Load-bearing range: **474–1363 characters** (n=125). Mean ~834, median ~820. Many long warnings (1000+) are load-bearing because they enumerate numbered invariants.

5. **Signal-marker coverage:** every load-bearing warning in the corpus contains at least one of: named symbol (`X.y`, `_UPPER_CONST`), named file path (`src/lexibrary/...`, `.lexibrary/...`, `baml_src/...`), version string (`Python 3.11+`, `Node 20+`), or SQL keyword with backticked column name. The generic-hedge and ambiguous buckets often have symbol-like tokens but no grounding in specific behaviour (e.g. `Path.is_relative_to` as a library-dep mention without any specific invariant around it).

## Thresholds derived for Group 16 (§2.4b post-filter)

### Length threshold

| candidate | would drop (generic-hedge) | would drop (load-bearing) | recommendation |
|-----------|---------------------------:|--------------------------:|----------------|
| 100 chars | 0 / 8 (0%)                | 0 / 125                   | too low — misses all |
| 300 chars | 0 / 8 (0%)                | 0 / 125                   | too low — shortest generic-hedge is 335 |
| 400 chars | 4 / 8 (50%)               | 0 / 125                   | captures half of generic-hedge |
| **500 chars** | **6 / 8 (75%)**       | **2 / 125 (1.6%)**        | **chosen — see below** |
| 600 chars | 8 / 8 (100%)              | 5 / 125 (4%)              | too aggressive — starts eating load-bearing |

**Chosen length threshold: 500 characters.** This keeps nearly all load-bearing warnings above the cutoff while filtering 75% of pure generic-hedge cases. The two load-bearing warnings below 500 chars (`ignore/patterns.py` @ 383, `artifacts/slugs.py` bulleted with short body) both have strong signal-marker hits (pathspec library name, explicit a-z/0-9 alphanumeric rule), so they are preserved by the signal-marker path and do NOT need the length gate.

**Caveat.** SHARED_BLOCK_E currently uses `length_threshold=120`. That is WAY too low — only warnings in the single-sentence-pitch range would survive. Group 16 SHALL raise the default from `120` to `500`.

The filter is NOT a pure length drop. It uses `OR`: keep-if-long OR keep-if-signal. So even warnings below 500 chars survive when any signal-marker matches — which is exactly what we want for the 2 short-but-load-bearing cases.

### Signal-marker regex extensions

SHARED_BLOCK_E defaults:

- `_VERSION_RE = r"(?:Python|Node|Java|Go|Rust)\s+\d+(?:\.\d+)?\+?|v\d+\.\d+(?:\.\d+)?"`
- `_PROPER_NOUN_RE = r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)+\b"`
- `_has_code_identifier(text, skeleton)` — intersect tokens from text with tokens from skeleton.

**Extension 1 — Dotted-path identifier.** Many load-bearing warnings cite dotted identifiers (`Path.resolve()`, `datetime.now(UTC)`, `yaml.safe_load`, `frontmatter.updated_by`, `config.llm.api_key_env`, `sys.version_info`). The `_has_code_identifier` path SHOULD catch these via the skeleton intersection, BUT only when the dotted path is spelled identically in the skeleton. Many warnings cite `Path.resolve()` without `Path.resolve` ever appearing in the skeleton (it's a stdlib call). Add:

```python
_DOTTED_IDENT_RE = re.compile(r"\b[a-z][a-zA-Z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,}\b")
```

Accepts any `lower.CamelOrLower.something` — catches `yaml.safe_load`, `Path.resolve`, `datetime.now`, `frontmatter.updated_by`, `config.llm.api_key_env`. A passing mention of "filesystem race" does NOT match (no dots).

**Extension 2 — SQLite/schema keywords.** Several load-bearing warnings cite SQLite-specific terms (`FTS5`, `WAL`, `PRAGMA`, `COLLATE NOCASE`, `INSERT OR IGNORE`, `ON DELETE CASCADE`, `lastrowid`). These are neither CamelCase-proper-noun sequences nor dotted identifiers, so the existing regex misses them. Add:

```python
_SQL_MARKER_RE = re.compile(
    r"\b(?:FTS\d|WAL\b|PRAGMA|COLLATE\s+\w+|INSERT\s+OR\s+IGNORE|ON\s+DELETE\s+CASCADE|"
    r"lastrowid|sqlite3\.\w+|SCHEMA_VERSION|PathSpec|gitignore)\b"
)
```

**Extension 3 — File path literal.** Several warnings cite `.lexibrary/...`, `.git/...`, `src/lexibrary/...`, `baml_src/...`. Add:

```python
_FILE_PATH_RE = re.compile(
    r"(?:\.lexibrary/|\.git/|src/lexibrary/|baml_src/|\.cursor/|\.claude/|"
    r"\.comments\.yaml|\.aindex|\.iwh|py\.typed)"
)
```

**Extension 4 — CLI flag literal.** Warnings cite `--force`, `--unlimited`, `--scope`, `--peek`, `--type`, `--watch`, `--interactive`. The bare double-dash form is a strong load-bearing marker (the warning is tied to a specific flag). Add:

```python
_CLI_FLAG_RE = re.compile(r"--[a-z][a-z0-9-]+")
```

### Final filter shape (for Group 16)

```python
def _filter_complexity_warning(
    raw: str | None,
    *,
    interface_skeleton: str | None,
    length_threshold: int = 500,
) -> str | None:
    if raw is None:
        return None
    text = raw.strip().strip('"').strip("'")
    # Long enough → keep.
    if len(text) >= length_threshold:
        return raw
    # Any signal marker → keep.
    if _has_code_identifier(text, interface_skeleton):
        return raw
    if _DOTTED_IDENT_RE.search(text):
        return raw
    if _has_proper_noun(text):
        return raw
    if _has_version_marker(text):
        return raw
    if _SQL_MARKER_RE.search(text):
        return raw
    if _FILE_PATH_RE.search(text):
        return raw
    if _CLI_FLAG_RE.search(text):
        return raw
    return None
```

### Expected Group 16 acceptance

- **Target:** drop ≥80% of the 8 generic-hedge entries.
- **Constraint:** drop 0 of the 125 load-bearing entries.
- **Ambiguous bucket:** expected to be filtered case-by-case. Entries where the "specific" clause survives the filter (because of a signal-marker match) will keep the whole warning. Entries where only hedge clauses remain after LLM drift will be filtered. This is acceptable — the `## Complexity Warning` section is a signal device, not a document-section contract.

The 500-char threshold alone drops 6 of 8 generic-hedge entries. The two that slip through (`playbook.py` @ 603, `concept.py` @ 648) are above the cutoff and must be caught by prompt-tightening (Group 17) — the filter alone cannot distinguish "Pydantic-boilerplate text that happens to be 600 chars" from "genuine specific warning that happens to be 600 chars".

### Group 16 implementation notes for the agent

1. In `_filter_complexity_warning`, use `length_threshold=500` (NOT the `120` placeholder in SHARED_BLOCK_E).
2. Add the four new regexes (`_DOTTED_IDENT_RE`, `_SQL_MARKER_RE`, `_FILE_PATH_RE`, `_CLI_FLAG_RE`) per the patterns above. Place near the other `_RE` module-globals.
3. Update the `_has_*` helper set to include three new predicates (dotted, SQL, file path, CLI flag) OR inline the `*_RE.search()` calls directly as in the final filter shape above.
4. Extend the test suite (`tests/test_archivist/test_complexity_warning_filter.py` — Group 16.4) with one case per new regex: dotted `yaml.safe_load` preserved; SQL `FTS5` preserved; path `.lexibrary/index.db` preserved; CLI flag `--force` preserved. Plus the short-generic-hedge-drop case.

### Cross-reference for Group 16.6 (acceptance guard)

The 8 generic-hedge entries that SHOULD be dropped after Group 16:

1. `.lexibrary/designs/src/lexibrary/artifacts/aindex.py.md` (335 chars)
2. `.lexibrary/designs/src/lexibrary/artifacts/concept.py.md` (648 chars — ABOVE threshold, needs prompt-tightening to drop)
3. `.lexibrary/designs/src/lexibrary/artifacts/playbook.py.md` (603 chars — ABOVE threshold, needs prompt-tightening to drop)
4. `.lexibrary/designs/src/lexibrary/cli/playbooks.py.md` (624 chars — ABOVE threshold)
5. `.lexibrary/designs/src/lexibrary/curator/collect_filters.py.md` (538 chars — ABOVE threshold, cites `Path.is_relative_to`)
6. `.lexibrary/designs/src/lexibrary/init/rules/base.py.md` (428 chars)
7. `.lexibrary/designs/src/lexibrary/services/bootstrap_render.py.md` (339 chars)
8. `.lexibrary/designs/src/lexibrary/exceptions.py.md` (463 chars)

5 of 8 entries are ABOVE the 500-char threshold (barely). The filter will NOT drop them alone — they pass the length gate AND may match a signal-marker regex (e.g. `Path.is_relative_to` in `collect_filters` matches `_DOTTED_IDENT_RE`). For these, the prompt-tightening in Group 17 is the primary control.

The 125 load-bearing entries that MUST be preserved:

(full list is the audit table above — every row bucketed `load-bearing`). Group 16.6 cross-reference is: after the re-render, run `grep -rln "^## Complexity Warning" .lexibrary/designs/src/lexibrary/` and confirm every path in the load-bearing column still produces a hit.
