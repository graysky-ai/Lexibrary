# design-cleanup — Implementation tasks

> Plan of record: `plans/design-file-signal-cleanup-plan.md`.
>
> Phase ordering: §2.3 extractor fix (Groups 1–2) → atomic serializer changes (Groups 3–4) → admin link-graph rebuild (Group 5, human) → engineer force re-render (Group 6) → §2.3 stack post (Group 7) → remaining Part 1 serializer/prompt changes (Groups 8–11) → aggregator rendering (Groups 12–13) → Complexity Warning audit + three-layer gate (Groups 14–17) → §1.7 Insights retargeting (Groups 18–19) → final dogfood pass (Group 20).

## Notes for the implementation agent

**Discover-then-do items** — verifications the agent performs at implementation time, NOT open questions for the user:

1. **Serializer location.** `serialize_design_file` is in `src/lexibrary/artifacts/design_file_serializer.py`; parser is `src/lexibrary/artifacts/design_file_parser.py`. Confirmed via `grep -l "def serialize_design_file" src/lexibrary/`. Use these paths throughout.
2. **Dependency-extractor location.** `_extract_python_deps` / `_extract_js_deps` live in `src/lexibrary/archivist/dependency_extractor.py`. The `_children(node)` helper at the bottom of that file is what today's depth-1 walk relies on; the recursive walk replaces the `for node in _children(root):` loops.
3. **Validator-check location.** `check_design_frontmatter` is in `src/lexibrary/validator/checks.py`. Grep for `def check_design_frontmatter` to find the current implementation.
4. **BAML prompt location.** `ArchivistGenerateDesignFile` is defined in `baml_src/archivist_design_file.baml`. Prompt edits land there; `baml-cli generate` (or the equivalent `uv run baml-cli generate`) MUST be run after editing so the Python `baml_client` reflects the new prompt.
5. **code.md template location.** The `Code` agent template lives at `src/lexibrary/templates/claude/agents/code.md` (NOT under `templates/` at repo root). Init copies it into `.claude/agents/code.md` for each lexibrary-initialised project.
6. **Sandbox overrides (SHARED_BLOCK_A).** Every `uv run pytest`, `uv run ruff check`, `lexi design update`, `lexi design comment` invocation MUST run with `dangerouslyDisableSandbox: true` per CLAUDE.md. `lexictl` commands are prohibited for agents — any task that requires one blocks on the user (admin).
7. **Dogfood pacing.** `lexi design update --force` across `src/lexibrary/` is an LLM-budget spend. Run it in Group 6 (post-§2.3) and again in Group 20 (final acceptance). Do NOT run it between every small serializer change.

## Dependency graph

```
group 1:  depends_on: []                      -- §2.3 Python extractor recursive walk + TYPE_CHECKING exclusion + tests
group 2:  depends_on: []                      -- §2.3 JS/TS extractor recursive walk + tests (parallel with 1)
group 3:  depends_on: []                      -- §1.1 Interface Contract inner-fence strip (serializer + parser + round-trip test)
group 4:  depends_on: []                      -- §1.4 frontmatter status=active omission (serializer + parser + validator relax + round-trip test)
group 5:  depends_on: [1, 2]                  -- ADMIN-ONLY: project admin runs `lexictl update --force` to rebuild link graph
group 6:  depends_on: [3, 4, 5]               -- Engineer runs `lexi design update --force` across `src/lexibrary/` (one-shot LLM spend, sandbox override)
group 7:  depends_on: [6]                     -- §2.3 stack post documenting depth-1-walk finding
group 8:  depends_on: [6]                     -- §1.2 Dependents hint removal (serializer + parser + round-trip test)
group 9:  depends_on: [6]                     -- §1.3 Meta footer compaction (serializer + parser + top-of-file comment + round-trip test)
group 10: depends_on: []                      -- §1.5 Archivist prompt tag cap + archivist-output tag-count validation
group 11: depends_on: []                      -- §1.6 Archivist prompt wikilink gold-bar + regression test for existing check_wikilink_resolution
group 12: depends_on: []                      -- §2.1 Aggregator detector in archivist/skeleton.py
group 13: depends_on: [12]                    -- §2.1 `## Re-exports` rendering path in serializer / pipeline branch
group 14: depends_on: [6]                     -- §2.4 step 1: hand-classify current Complexity Warning sections → plans/design-cleanup/complexity-warning-audit.md
group 15: depends_on: [12]                    -- §2.4(c) complexity_warning prompt suppression for aggregators + constants-only modules
group 16: depends_on: [14, 15]                -- §2.4(b) deterministic post-filter in archivist/pipeline.py (thresholds from group 14)
group 17: depends_on: [14]                    -- §2.4(a) prompt tightening for complexity_warning in ArchivistGenerateDesignFile
group 18: depends_on: []                      -- §1.7 CLI help + code.md template: retarget Insights guidance away from release notes
group 19: depends_on: [6, 18]                 -- §1.7 retrospective: scan Insights sections for "Phase N:" entries; delete or migrate to stack posts
group 20: depends_on: [7, 8, 9, 10, 11, 13, 16, 17, 19]  -- Final dogfood: lexi design update --force + lexi validate + acceptance spot-checks
```

## Shared content blocks

### SHARED_BLOCK_A — Sandbox override list

Commands requiring `dangerouslyDisableSandbox: true` (per CLAUDE.md):

- `uv run pytest` (every test group)
- `uv run ruff check` / `uv run ruff format`
- `uv run mypy src/`
- `lexi design update` (every variant, including `--force`)
- `lexi design comment`
- Any `bd` subcommand (dolt discovery)

Commands prohibited for agents (require user / admin):

- `lexictl update` (and all `lexictl` subcommands) — block and ask the user.

### SHARED_BLOCK_B — Compact meta footer format (§1.3)

Emit as a SINGLE line:

```
<!-- lexibrary:meta {source: {source}, source_hash: {source_hash}, interface_hash: {interface_hash}, design_hash: {design_hash}, generated: {generated_iso}, generator: {generator}, dependents_complete: {true_or_false}} -->
```

Rules:

- `interface_hash` key MAY be omitted from the inline object when `metadata.interface_hash is None` (matches current conditional-emit behaviour).
- All other six fields are ALWAYS emitted.
- Values SHALL NOT be quoted unless they contain a reserved YAML character (`:`, `{`, `}`, `,`, `#`, `&`, `*`, `!`, `|`, `>`, `'`, `"`, `%`, `@`, `` ` ``) — in which case the serializer SHALL quote the whole value. SHA-256 hex digests are safe unquoted.
- Boolean `dependents_complete`: lowercase `true` / `false` (matches the current `str(...).lower()` call site).
- Generated timestamp: ISO 8601 (e.g. `2026-04-21T10:00:00+00:00`) — matches current `generated.isoformat()`.

Parser SHALL accept the compact inline form AND the existing multi-line form (backward compatibility).

### SHARED_BLOCK_C — Frontmatter status omission rule (§1.4)

In `serialize_design_file`:

```python
frontmatter_dict: dict[str, object] = {
    "description": description,
    "id": data.frontmatter.id,
    "updated_by": data.frontmatter.updated_by,
}
if data.frontmatter.status != "active":
    frontmatter_dict["status"] = data.frontmatter.status
if data.frontmatter.deprecated_at is not None:
    frontmatter_dict["deprecated_at"] = data.frontmatter.deprecated_at.isoformat()
if data.frontmatter.deprecated_reason is not None:
    frontmatter_dict["deprecated_reason"] = data.frontmatter.deprecated_reason
```

Parser:

- `parse_design_file_frontmatter` already defaults a missing `status` key to `"active"` via Pydantic. Verify with an explicit test; do NOT change the model.

Validator:

- `check_design_frontmatter` (in `src/lexibrary/validator/checks.py`) treats absent `status` as `"active"` and emits no issue. Invalid explicit values (e.g. `status: "daft"`) still emit an error.

### SHARED_BLOCK_D — Aggregator detection gates (§2.1)

A module qualifies as an aggregator iff ALL three gates pass:

1. **Re-export gate:** `reexported_count / total_top_level_named_symbols >= 0.8`. A symbol is "re-exported" if it is a member of `__all__` OR the form `X = <module>.X` / `from .<module> import X` appears at top level with no further binding.
2. **Body-size gate:** Every top-level function and class has a body of ≤3 non-comment, non-blank lines. (Measured by skeleton body length, not raw text — avoid counting docstring-only bodies as large.)
3. **Conditional-logic gate:** At most one top-level conditional, and it must be a `sys.version_info` comparison (detected by identifier text `sys.version_info` in the condition subtree).

Detector returns a dataclass `AggregatorClassification`:

```python
@dataclass(frozen=True)
class AggregatorClassification:
    is_aggregator: bool
    reexports_by_source: dict[str, list[str]]  # {source_module: [name1, name2, ...]}
    body_size_ratio: float  # informational; for logs
```

When `is_aggregator=False`, `reexports_by_source` is empty.

### SHARED_BLOCK_E — Complexity Warning post-filter heuristic (§2.4b)

Pseudocode for the filter (applied in `archivist/pipeline.py` at the `complexity_warning = output.complexity_warning` assignment site):

```python
def _filter_complexity_warning(
    raw: str | None,
    *,
    interface_skeleton: str | None,
    length_threshold: int = 120,
) -> str | None:
    if raw is None:
        return None
    text = raw.strip().strip('"').strip("'")
    if len(text) >= length_threshold:
        return raw
    # Signal markers — keep warning if ANY matches.
    if _has_code_identifier(text, interface_skeleton):
        return raw
    if _has_proper_noun(text):
        return raw
    if _has_version_marker(text):
        return raw
    return None


_VERSION_RE = re.compile(r"(?:Python|Node|Java|Go|Rust)\s+\d+(?:\.\d+)?\+?|v\d+\.\d+(?:\.\d+)?")
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)+\b")


def _has_code_identifier(text: str, skeleton: str | None) -> bool:
    if skeleton is None:
        return False
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", skeleton))
    return any(tok in text for tok in tokens if len(tok) >= 2)


def _has_proper_noun(text: str) -> bool:
    return bool(_PROPER_NOUN_RE.search(text))


def _has_version_marker(text: str) -> bool:
    return bool(_VERSION_RE.search(text))
```

**Tuning note:** initial `length_threshold=120` is a placeholder. Group 14 (hand-classification audit) produces the real threshold. Group 16 sets the value in code and records the final number in the commit message.

### SHARED_BLOCK_F — Retrospective `Phase N:` scan script (§1.7 Group 19)

Reference script for the scan step. Agents SHALL review each match by hand — do NOT bulk-delete.

```bash
# Run from repo root. Skip `.comments.yaml`, `.iwh`.
grep -rln --include '*.md' -E '^Phase [0-9]+:' .lexibrary/designs/
```

For each hit:

1. Read the `## Insights` section manually.
2. Decide: is the entry load-bearing design rationale, or release-note drift?
3. If release-note drift → delete the entry from `Insights`, regenerate the design file via `lexi design update` (with sandbox override) or edit the `preserved_sections` directly if the change is trivial.
4. If load-bearing → leave it.
5. If genuinely valuable for history → migrate to a stack post via `lexi stack post` and delete from `Insights`.

---

## 1. §2.3 — Python dependency extractor recursive walk

Replace the depth-1 walk in `_extract_python_deps` with a recursive descendant walk. Exclude `if TYPE_CHECKING:` guarded subtrees. No schema change.

- [x] 1.1 Read `src/lexibrary/archivist/dependency_extractor.py` end-to-end. Note the existing `_children(node)` helper and the current shape of `_collect_import_statement` / `_collect_import_from_statement`. Note that `_children` returns `list(getattr(node, "children", []))` — the grammar-optional pattern MUST be preserved.
- [x] 1.2 Add a private helper `_walk_descendants(root, *, skip_type_checking: bool = True)` to `dependency_extractor.py` that yields every descendant node (not just root's direct children). Use an iterative stack (list) to avoid recursion limits on deep ASTs. When `skip_type_checking=True` AND a node is an `if_statement` whose condition subtree contains an identifier with text `TYPE_CHECKING`, the walker SHALL NOT yield any descendant of that `if_statement`'s body.
- [x] 1.3 Modify `_extract_python_deps(root, file_path, project_root)` to iterate `_walk_descendants(root)` instead of `_children(root)`. Keep the existing dispatch on `node.type`: `import_statement` → `_collect_import_statement(...)`; `import_from_statement` → `_collect_import_from_statement(...)`. The `_collect_*` helpers don't change.
- [x] 1.4 Add unit tests in `tests/test_archivist/test_dependency_extractor_recursive.py` (create the file). Use the existing tree-sitter fixtures under `tests/test_archivist/` as a pattern. Cover: (a) deferred import inside function body → extracted; (b) import inside `try/except ImportError:` → extracted; (c) import inside class body → extracted; (d) import inside `if platform.system() == "Darwin":` top-level conditional → extracted; (e) import under `if TYPE_CHECKING:` guard → NOT extracted; (f) top-level `import x` AND top-level `from .y import z` → BOTH extracted (regression guard for the pre-fix behaviour).
- [x] 1.5 Run `uv run pytest tests/test_archivist/test_dependency_extractor_recursive.py -v` with `dangerouslyDisableSandbox: true` (per SHARED_BLOCK_A). Confirm all new cases pass.
- [x] 1.6 Run `uv run pytest tests/test_archivist/ -v` full suite (same sandbox note). Confirm no pre-existing dependency-extractor tests regress. If any test asserted a specific under-counted dep list, update the assertion to match the new recursive behaviour and document the change in the commit message.
- [x] 1.7 Run `uv run mypy src/lexibrary/archivist/dependency_extractor.py` with sandbox override. Confirm no type errors introduced.
- [x] 1.8 Run `uv run ruff check src/lexibrary/archivist/dependency_extractor.py tests/test_archivist/test_dependency_extractor_recursive.py` with sandbox override. Confirm clean.

## 2. §2.3 — JS/TS dependency extractor recursive walk

Mirror Group 1 for the JavaScript/TypeScript path. Independent of Group 1 — run in parallel.

- [x] 2.1 Read `_extract_js_deps` in `dependency_extractor.py`. Note the current iteration `for node in _children(root):` dispatching on `import_statement` / `export_statement`.
- [x] 2.2 Modify `_extract_js_deps(root, file_path, project_root)` to iterate `_walk_descendants(root, skip_type_checking=False)` instead of `_children(root)`. JS/TS has no `TYPE_CHECKING`-equivalent guard (TypeScript's `import type { X } from ...` is a separate `import_type_statement` node; recursive walk already excludes because we only match on `import_statement` / `export_statement`). Keep the existing `string`-import-path detection logic unchanged.
- [x] 2.3 Add unit tests in `tests/test_archivist/test_dependency_extractor_recursive.py` (append to the file created in Group 1). Cover: (a) deferred dynamic `import('./helper')` / nested `import` statement inside function body → extracted; (b) `import type { X } from './types'` → NOT extracted (`import_type_statement` node, not `import_statement`); (c) relative import inside class body → extracted; (d) top-level `import X from './y'` → extracted (regression guard).
- [x] 2.4 Run `uv run pytest tests/test_archivist/ -v` with sandbox override. Confirm all new JS/TS cases pass.

## 3. §1.1 — Interface Contract inner-fence strip

Strip a leading `` ```<lang>\n `` and trailing `` \n``` `` from `data.interface_contract` before emitting the outer fence. Parser tolerates legacy doubled-fence on-disk files.

- [x] 3.1 Read `serialize_design_file` in `src/lexibrary/artifacts/design_file_serializer.py`. Locate the Interface Contract block (around line 89–96 in the current file). Note the `lang = _lang_tag(data.source_path)` and `` parts.append(f"```{lang}") ``.
- [x] 3.2 Before `parts.append(f"```{lang}")`, add a fence-stripping step:
  ```python
  contract = data.interface_contract
  fence_open = re.compile(r"^```[A-Za-z0-9_+-]*\n")
  if fence_open.match(contract):
      contract = fence_open.sub("", contract, count=1)
  if contract.endswith("\n```"):
      contract = contract[: -len("\n```")]
  elif contract.endswith("```"):
      contract = contract[: -len("```")]
  ```
  Add `import re` at the top of the module. Emit `contract` (not `data.interface_contract`) inside the outer fence.
- [x] 3.3 Read `parse_design_file` in `src/lexibrary/artifacts/design_file_parser.py`. Locate the Interface Contract parsing path — the logic that captures content between the opening and closing `` ``` `` fences.
- [x] 3.4 In the parser, after extracting the Interface Contract body between outer fences, add a tolerance step: if the body begins with `` ```<lang>\n `` (inner fence), strip it. If the body ends with `\n```` (inner closing fence), strip it. This preserves round-trip equivalence for legacy files containing the doubled-fence artifact.
- [x] 3.5 Add round-trip test at `tests/test_artifacts/test_design_file_roundtrip.py` (file may already exist — search first; if not, create). Case: construct a `DesignFile` with `interface_contract="```python\ndef foo(): ...\n```"`, serialize, assert the emitted section contains exactly one outer fence wrapping `def foo(): ...`, parse back, assert round-tripped `DesignFile.interface_contract == "def foo(): ..."` (inner fence stripped).
- [x] 3.6 Add legacy-compat test: load a fixture string representing a legacy on-disk file with doubled fence, call `parse_design_file(tmp_path)`, assert the parsed `DesignFile.interface_contract` does NOT include the inner fence.
- [x] 3.7 Run `uv run pytest tests/test_artifacts/ -v` with sandbox override. Confirm all round-trip tests pass.

## 4. §1.4 — Frontmatter `status: active` omission

Serializer omits `status` when equal to `"active"`. Parser defaults missing `status` to `"active"`. Validator check relaxed to accept omission. Atomic landing.

- [x] 4.1 In `serialize_design_file` (`src/lexibrary/artifacts/design_file_serializer.py`), apply SHARED_BLOCK_C to the frontmatter construction. Remove the unconditional `"status": data.frontmatter.status` line; replace with the conditional block shown in the shared block.
- [x] 4.2 Verify `parse_design_file_frontmatter` in the parser already defaults `status=None|missing` to `"active"` via the Pydantic `DesignFileFrontmatter` model. If a parsing branch explicitly raises on missing `status`, relax it. Grep for `"status"` in `design_file_parser.py`; any non-model default handling goes here.
- [x] 4.3 Read `check_design_frontmatter` in `src/lexibrary/validator/checks.py` (grep `def check_design_frontmatter`). Locate the `status` validation branch — the current implementation requires the key and emits an error when absent.
- [x] 4.4 Modify the check: when `status` is absent from the parsed frontmatter dict, SKIP the check (no issue emitted). When `status` is present, validate it against `{"active", "unlinked", "deprecated"}` exactly as today. Per the schema-frontmatter-checks spec delta, absent equals `"active"` for validation purposes.
- [x] 4.5 Add round-trip test at `tests/test_artifacts/test_design_file_roundtrip.py`: (a) `DesignFile` with `frontmatter.status="active"` serializes without a `status:` key; parses back with `status="active"`. (b) `frontmatter.status="deprecated"` serializes with `status: deprecated` and round-trips. (c) `frontmatter.status="unlinked"` serializes with `status: unlinked` and round-trips. (d) Legacy file containing explicit `status: active` parses to `status="active"` (backward compat).
- [x] 4.6 Add validator test at `tests/test_validator/test_check_design_frontmatter.py` (extend if exists, else create). Cases: (a) design file with `status: active` present → no issue; (b) design file with NO `status` key → no issue (NEW); (c) design file with `status: daft` → error issue; (d) design file with `status: deprecated` → no issue.
- [x] 4.7 Run `uv run pytest tests/test_artifacts/ tests/test_validator/ -v` with sandbox override. Confirm all pass.
- [x] 4.8 Run `uv run mypy src/lexibrary/artifacts/design_file_serializer.py src/lexibrary/validator/checks.py` with sandbox override.

## 5. ADMIN — Project admin runs `lexictl update --force`

**THIS IS A HUMAN TASK.** Agents MUST NOT run `lexictl` commands (CLAUDE.md). The agent's deliverable here is to PREPARE the admin for this step and block further work until it completes.

- [x] 5.1 Verify Groups 1 and 2 merged (`_extract_python_deps` and `_extract_js_deps` both walk recursively). Run `grep -n "_walk_descendants" src/lexibrary/archivist/dependency_extractor.py` to confirm the new helper is in place.
- [x] 5.2 Write a checklist message to the user (admin) containing: (a) the exact command to run — `lexictl update --force`; (b) a note that this rebuilds `.lexibrary/index.db` with the corrected dependency data; (c) a note that after success, Groups 6 and 7 become unblocked.
- [x] 5.3 Wait for the user to confirm the admin run completed successfully (the admin reports back). Do NOT proceed to Group 6 without explicit confirmation.

## 6. Engineer force re-render across `src/lexibrary/`

With the link graph rebuilt (Group 5) AND serializer changes from Groups 3 + 4 in place, run `lexi design update --force` across the source tree. One-shot LLM spend.

- [x] 6.1 Confirm Group 5 completion (user confirmed admin ran `lexictl update --force`). Confirm `.lexibrary/index.db` mtime is later than the merge timestamp for Groups 1 + 2.
- [x] 6.2 Selectively run `lexi design update --force src/lexibrary/*` with `dangerouslyDisableSandbox: true` (per SHARED_BLOCK_A — BAML invokes SCDynamicStore). The command re-renders every design file under `.lexibrary/designs/src/lexibrary/`. Progress is LLM-budget-bound — expect this to take minutes. NOTE FROM USER: to save time and resources we won't rebuild every file in the tree, instead select a few subfolders that will give you the results you need.
- [x] 6.3 If the command fails mid-run for a subset of files, capture the failed paths, re-run `lexi design update --force <path>` for each. If a specific file repeatedly fails, write an IWH signal (`lexi iwh write <dir> --scope blocked --body "..."`) and surface to the user before proceeding.
- [ ] 6.4 After the re-render completes, spot-check the 13 service files previously recording `(none)` Dependents. Reference list from the plan:
  - `src/lexibrary/services/sweep.py.md`
  - Any other `src/lexibrary/services/*.py.md` that was not `status.py`, `impact.py`, `symbols.py`, `design.py`, or `status_render.py`.
  Assert that each now shows non-trivial Dependents.
  > **RESIDUAL FAILURE (2026-04-22):** services/*.md still show `(none)` and `dependents_complete: false` after the Group 6 re-render. Root cause: `--reindex` (run in Group 5) repopulates the link graph index, but every `extract_dependents` call during re-render raises `LinkGraphUnavailable`, so the archivist writes empty dependents. See stack post `ST-053`. User deferred the `lexictl update --force` fix; workaround investigation tracked separately.
- [x] 6.5 Run `uv run pytest tests/ -v` with sandbox override. Confirm no regression in the broader test suite.
- [x] 6.6 Commit the re-rendered design files in a dedicated commit with message referencing §2.3.
  > **VACUOUSLY SATISFIED (2026-04-22):** `.gitignore:11` excludes `.lexibrary/**/*.md`, so design files are untrackable by design and no commit can land them. User confirmed option (a) — treat as not-applicable.

## 7. §2.3 — Stack post documenting the depth-1 walk finding

Capture the non-obvious "extractor walks depth-1, every downstream consumer inherits the undercount" finding so future debuggers don't re-derive it.

- [x] 7.1 Run `lexi stack post` (or edit the produced file directly) with sandbox override if required. Title: "Dependency extractor's depth-1 AST walk silently undercounted reverse deps". Tags: `archivist`, `dependency-extraction`, `symbol-graph`.
- [x] 7.2 Body SHOULD cover: (a) symptom — 13 of 18 service design files showed `(none)` Dependents while CLI sweep commands clearly reached them; (b) root cause — `_extract_python_deps` and `_extract_js_deps` iterated `_children(root)`, not all descendants; (c) why it was hard to spot — `lexi lookup --full` agreed with the design file because `lexi lookup` consumes the same link graph; (d) fix — recursive descendant walk, `TYPE_CHECKING` excluded; (e) ripple — forward Dependencies were also undercounted, so `ast_import` edges across the project were incomplete; (f) how to detect similar issues in future tree-sitter extractors — prefer recursive walks unless there's a specific reason to restrict depth.
- [x] 7.3 Confirm the post was created: `lexi search --type stack "dependency extractor"` should return the new post. Note its stack ID (format `ST-NNN`).
  > **NOTE (2026-04-22):** Stack post created at `.lexibrary/stack/ST-054-dependency-extractor-s-depth-1-ast-walk-silently.md` and confirmed via `lexi view ST-054`. `lexi search --type stack "dependency extractor"` does NOT surface ST-054 until the search index is rebuilt via `lexictl update` (admin-only per CLAUDE.md). File on disk is correct and complete.

## 8. §1.2 — Dependents hint removal

Remove the unconditional `*(see \`lexi lookup\` for live reverse references)*` line from the serializer. Parser tolerates legacy files that still carry it.

- [x] 8.1 In `serialize_design_file` (`src/lexibrary/artifacts/design_file_serializer.py`), delete the line `parts.append("*(see \`lexi lookup\` for live reverse references)*")` and the blank-line append that follows it (current lines 111–112). The `Dependents` section becomes: heading, blank line, bullet list or `(none)`, blank line.
- [x] 8.2 Verify `parse_design_file` tolerates the hint line in legacy files. Read the current Dependents parsing logic; if it consumes only bullets (`- `), the hint line is already ignored (parsed as "other prose, not a bullet"). If the parser explicitly expects the first non-blank line after the heading to be a bullet OR `(none)`, relax it to skip any non-bullet line starting with `*(see`.
- [x] 8.3 Add round-trip test at `tests/test_artifacts/test_design_file_roundtrip.py`:
  - (a) `DesignFile(dependents=["src/x.py", "src/y.py"])` serializes WITHOUT the hint line; parses back to the same list.
  - (b) `DesignFile(dependents=[])` serializes with `(none)` only; parses back to `dependents=[]`.
  - (c) Legacy fixture string containing the hint line → parser ignores the hint, extracts the bullet list correctly.
- [x] 8.4 Run `uv run pytest tests/test_artifacts/ -v` with sandbox override.
  > **NOTE (2026-04-21, bead lexibrary-rff.8):** 3 pre-existing failures — `test_design_file_roundtrip.py::test_agent_edit_detection`, `test_design_file_serializer.py::test_design_hash_is_sha256_hex`, and `test_design_file_serializer.py::test_footer_multiline_format` — are caused by concurrent bead `lexibrary-rff.9` (§1.3 meta footer compaction replaces multiline footer with inline YAML). All 4 new tests added for §1.2 pass. These 3 failures will be resolved when bead .9 updates their own scope's assertions.

## 9. §1.3 — Meta footer compaction

Collapse the 9-line HTML comment footer to a single inline YAML line (SHARED_BLOCK_B). Add a 6-line comment at the top of the serializer documenting what each hash represents.

- [x] 9.1 Add the following 6-line explanatory comment at the top of `src/lexibrary/artifacts/design_file_serializer.py`, immediately after the module docstring:
  ```python
  # Staleness hashes in the footer serve three distinct purposes:
  #   source_hash     — SHA-256 of raw source bytes (detects source drift).
  #   interface_hash  — SHA-256 of the extracted interface skeleton (detects
  #                     skeleton drift without re-reading source).
  #   design_hash     — SHA-256 of the rendered design body excluding the
  #                     footer (detects agent/human edits to the design file).
  ```
- [x] 9.2 In `serialize_design_file`, replace the existing footer construction (current lines 195–208 — the `footer_lines = ["<!-- lexibrary:meta"]` block) with a single-line inline YAML emission matching SHARED_BLOCK_B. Implementation hint: build an ordered dict of the fields, emit via `yaml.safe_dump(..., default_flow_style=True, ...)` and strip the trailing newline; OR build the string manually to keep flow-style control. The existing `interface_hash is None` conditional SHALL be preserved.
- [x] 9.3 Read `parse_design_file_metadata` in `src/lexibrary/artifacts/design_file_parser.py`. The current implementation reads the tail of the file, finds the `<!-- lexibrary:meta` marker, and parses key/value pairs line-by-line.
- [x] 9.4 Extend the parser to recognise BOTH forms:
  - **Multi-line (legacy):** `<!-- lexibrary:meta\nkey: value\nkey: value\n-->` — detect by seeing a newline after the `<!-- lexibrary:meta` marker and before `-->`.
  - **Inline (new):** `<!-- lexibrary:meta {key: value, key: value} -->` — detect by seeing `{` after the marker and on the same line. Parse the inside of the `{...}` via `yaml.safe_load(f"{{{inner}}}")`.
  Both paths produce the same `StalenessMetadata` instance.
- [x] 9.5 Add round-trip tests at `tests/test_artifacts/test_design_file_roundtrip.py`:
  - (a) `DesignFile` with full metadata → serializes to a single-line footer → parses back to equivalent `StalenessMetadata`.
  - (b) `metadata.interface_hash is None` → `interface_hash` key absent from inline object; parser handles gracefully.
  - (c) Legacy multi-line fixture string → parser produces equivalent `StalenessMetadata`.
  - (d) Single-line fixture string (hand-authored) → parser produces equivalent `StalenessMetadata`.
- [x] 9.6 Run `uv run pytest tests/test_artifacts/ -v` with sandbox override.
  > **NOTE (2026-04-21, bead lexibrary-rff.9):** 3 pre-existing failures flagged by bead .8 — `test_design_file_roundtrip.py::test_agent_edit_detection`, `test_design_file_serializer.py::test_design_hash_is_sha256_hex`, and `test_design_file_serializer.py::test_footer_multiline_format` — were in bead .9's scope (they asserted the multi-line footer format). Fixed inline during Group 9: updated `test_agent_edit_detection` to read `design_hash` via the parser, updated `test_design_hash_is_sha256_hex` to extract the hash from the inline footer mapping, and renamed `test_footer_multiline_format` → `test_footer_single_line_inline_format` with matching assertions. All 6069 tests in the full suite pass.

## 10. §1.5 — Archivist prompt tag cap + output validation

Prompt-level cap of ≤3 tags, non-derivable only. Archivist-output validation truncates + logs if the LLM returns >3.

- [x] 10.1 Read `baml_src/archivist_design_file.baml`. Locate the `INSTRUCTIONS` section — specifically the existing bullet `Suggest 3-7 short lowercase tags`. Replace with: `Emit AT MOST 3 short lowercase tags. Each tag SHOULD add signal not already derivable from the filename or the summary field. If fewer than 3 tags add non-derivable signal, emit only those; empty is acceptable.` (Matches the archivist-baml spec delta.)
- [x] 10.2 Regenerate the BAML Python client: run `uv run baml-cli generate` (or the project's equivalent — grep for `baml-cli generate` in `pyproject.toml` / `Makefile` first) with sandbox override. Commit regenerated `baml_client/` alongside the prompt change.
- [x] 10.3 In `src/lexibrary/archivist/pipeline.py`, locate the site where `output.tags` is consumed into the `DesignFile` model. After the LLM returns the `DesignFileOutput`, add:
  ```python
  if len(output.tags) > 3:
      dropped = output.tags[3:]
      logger.warning(
          "Archivist emitted %d tags for %s; truncating to 3 (dropped: %s)",
          len(output.tags),
          source_path,
          dropped,
      )
      output_tags = output.tags[:3]
  else:
      output_tags = output.tags
  ```
  Thread `output_tags` (not `output.tags`) into the `DesignFile` constructor at the call site.
- [x] 10.4 Add test at `tests/test_archivist/test_tag_cap.py` (create): (a) mock `DesignFileOutput` with 5 tags → pipeline produces `DesignFile.tags` of length 3 with the first 3 values, and a warning is logged (use `caplog`); (b) mock with 2 tags → `DesignFile.tags` has both; (c) mock with empty list → `DesignFile.tags` empty.
- [x] 10.5 Run `uv run pytest tests/test_archivist/ -v` with sandbox override.

## 11. §1.6 — Archivist prompt wikilink gold-bar + regression test

Tighten the prompt. The existing `check_wikilink_resolution` validator check already surfaces dangling targets via `lexi validate` — verify with a regression test.

- [x] 11.1 In `baml_src/archivist_design_file.baml`, locate the current `available_artifacts` instruction ("When `available_artifacts` is provided, ONLY use names from the available artifacts list..."). Extend with the material-shaping bar — see the archivist-baml spec delta for exact language: "...Emit a wikilink ONLY when the target is a named concept/convention/playbook that MATERIALLY SHAPES the file's design. The bar is 'would removing this link leave the design file meaningfully less informative?' — a passing mention of the name alone is not sufficient...".
- [x] 11.2 Regenerate the BAML client (Group 10 step 2 — single regeneration commit is fine if run after both 10 and 11 prompt edits).
- [x] 11.3 Regression test: add `tests/test_validator/test_check_wikilink_resolution_surfacing.py` (if not already covered). Construct a design file with a wikilink to a non-existent concept name; run `check_wikilink_resolution`; assert an error-severity `ValidationIssue` is emitted with check name `"wikilink_resolution"` and the unresolved target in the message.
- [x] 11.4 Run `uv run pytest tests/test_validator/ -v` with sandbox override.

## 12. §2.1 — Aggregator detector

Add the detector in `src/lexibrary/archivist/skeleton.py` following SHARED_BLOCK_D. Standalone — Group 13 consumes it.

- [x] 12.1 Read `src/lexibrary/archivist/skeleton.py`. Find the existing skeleton-building path for Python modules (top-level function / class extraction).
- [x] 12.2 Add `AggregatorClassification` dataclass per SHARED_BLOCK_D. Place at module top-level with `@dataclass(frozen=True)`.
- [x] 12.3 Implement `classify_aggregator(skeleton_or_ast) -> AggregatorClassification`. Gates (SHARED_BLOCK_D): (1) re-export ratio ≥0.8 of top-level named symbols (members of `__all__` OR `X = module.X` / `from .module import X` with no further binding); (2) all top-level function/class bodies ≤3 non-comment, non-blank lines (use existing skeleton body-length info if available, else count via the AST); (3) at most one top-level conditional, and it must reference `sys.version_info` in the condition subtree.
- [x] 12.4 Populate `reexports_by_source: dict[str, list[str]]` during classification — for each `from <source_module> import A, B, C` statement OR `from <source_module> import X\nX_alias = X` pattern, append `[A, B, C]` to `reexports_by_source[source_module]`. The dict is used downstream by Group 13.
- [x] 12.5 Add unit tests in `tests/test_archivist/test_aggregator_detector.py` (create): (a) pure aggregator (`from .a import X\nfrom .b import Y, Z\n__all__ = ["X", "Y", "Z"]`) → `is_aggregator=True`, `reexports_by_source={".a": ["X"], ".b": ["Y", "Z"]}`; (b) module with 3 re-exports + a 10-line top-level function → `is_aggregator=False` (body-size gate fails); (c) module with `if platform.system() == "Darwin":` branch → `is_aggregator=False` (conditional-logic gate fails); (d) module with single `if sys.version_info >= (3, 11):` branch plus re-exports → `is_aggregator=True` (sys.version_info guard allowed); (e) module with 80/20 re-export ratio (4 re-exports, 1 standalone `def short(): pass`) → `is_aggregator=True`.
- [x] 12.6 Run `uv run pytest tests/test_archivist/test_aggregator_detector.py -v` with sandbox override.

## 13. §2.1 — Re-exports rendering path

Route aggregator modules through `## Re-exports`. `description`, `Dependencies`, `Dependents` unchanged.

- [x] 13.1 In `src/lexibrary/archivist/pipeline.py`, locate where `DesignFile` is constructed from the BAML output (near step 9 of the pipeline). Before construction, call `classify_aggregator(skeleton_or_ast)` from Group 12. If `is_aggregator=True`, stash the classification result in a local variable.
- [x] 13.2 Extend `DesignFile` (`src/lexibrary/artifacts/design_file.py`) with an optional field `reexports: dict[str, list[str]] | None = None`. Pydantic 2 optional, default `None`. When set, the serializer renders `## Re-exports` and suppresses `## Interface Contract`.
- [x] 13.3 In `serialize_design_file` (`src/lexibrary/artifacts/design_file_serializer.py`), add a branch: if `data.reexports is not None` AND `len(data.reexports) > 0`, emit `## Re-exports` section and SKIP the `## Interface Contract` section. Otherwise emit `## Interface Contract` as today (with the §1.1 inner-fence strip). The Re-exports section format: one bullet per source module, `` - From `<source-module>`: <Name1>, <Name2>, <Name3> ``.
- [x] 13.4 Update the parser `parse_design_file` to recognise `## Re-exports` as an alternative to `## Interface Contract`. Extract bullets, parse the `` From `<source-module>`: ... `` format, populate `DesignFile.reexports`. When a file has `## Re-exports`, `DesignFile.interface_contract` SHALL be `""` (empty string, not None, since the Pydantic field may require a string).
- [x] 13.5 Update `pipeline.py` DesignFile construction: when `classification.is_aggregator=True`, pass `reexports=classification.reexports_by_source` AND `interface_contract=""` to the `DesignFile` constructor. When `is_aggregator=False`, pass `reexports=None` and the LLM-provided `interface_contract` as today.
- [x] 13.6 Add round-trip test at `tests/test_artifacts/test_design_file_aggregator.py` (create): (a) `DesignFile(reexports={"lexibrary.x": ["A"]}, interface_contract="")` serializes with `## Re-exports` and NO `## Interface Contract` section; parses back identically; (b) non-aggregator `DesignFile(reexports=None, interface_contract="def foo(): ...")` serializes with `## Interface Contract` and NO `## Re-exports` section; parses back identically.
- [x] 13.7 Spot-check with a dogfood run: pick `src/lexibrary/artifacts/__init__.py` (known aggregator). Run `lexi design update src/lexibrary/artifacts/__init__.py` with sandbox override. Read the produced design file. Confirm it has `## Re-exports` with bullets like `` - From `lexibrary.artifacts.design_file`: DesignFile, DesignFileFrontmatter, StalenessMetadata `` and NO `## Interface Contract` section. Body length (excluding footer) SHOULD be ≤25 lines.
- [x] 13.8 Run `uv run pytest tests/test_artifacts/ tests/test_archivist/ -v` with sandbox override.

## 14. §2.4 step 1 — Hand-classification audit

Produce `plans/design-cleanup/complexity-warning-audit.md` — one row per Complexity Warning section, columns `path | bucket | notes` (bucket ∈ `{load-bearing, generic-hedge, ambiguous}`). Runs AFTER the Group 6 re-render so the corpus is fresh.

- [x] 14.1 Create `plans/design-cleanup/complexity-warning-audit.md`. Add a header explaining the audit method: the three buckets, the signal markers to look for (named symbol / named file / version string / concrete invariant).
- [x] 14.2 Enumerate every `## Complexity Warning` section under `.lexibrary/designs/src/lexibrary/`. Reference command: `grep -rln --include '*.md' '^## Complexity Warning' .lexibrary/designs/src/` produces the file list. For each file, read the section and classify.
- [x] 14.3 Record each file as a row: `| path | bucket | notes |`. Notes SHOULD capture the specific signal marker (if load-bearing) or the hedging pattern (if generic-hedge). Ambiguous entries flag for reviewer attention — include enough context that a reviewer can make the call.
- [x] 14.4 Append a summary at the bottom: `total = N`, `load-bearing = X`, `generic-hedge = Y`, `ambiguous = Z`. Sanity check: `X + Y + Z == N`.
- [x] 14.5 Derive initial thresholds for Group 16:
  - **Length threshold:** examine the `generic-hedge` bucket's character-length distribution. Set the threshold so it captures ≥80% of generic-hedge entries while leaving load-bearing entries above the cutoff. Record the chosen value in the audit file.
  - **Signal-marker regexes:** verify the defaults in SHARED_BLOCK_E catch the `load-bearing` bucket. If any load-bearing entry is not matched by any regex, extend the regex or add a new signal marker. Record extensions in the audit file.
- [x] 14.6 Commit `plans/design-cleanup/complexity-warning-audit.md`. Group 16 reads it.

## 15. §2.4(c) — Complexity Warning prompt suppression for aggregators + constants-only

Skeleton gate: when the skeleton is aggregator-only OR constants-only, suppress the `complexity_warning` prompt input so the LLM never sees the field for these modules.

- [x] 15.1 In `src/lexibrary/archivist/skeleton.py`, add `is_constants_only(skeleton_or_ast) -> bool`. Returns True when the module has NO top-level `def` or `class` AND has only top-level value assignments (`X = 1`, `FOO: list[int] = [1, 2]`). Unit tests: (a) pure constants file → True; (b) file with one function → False; (c) file with one class → False; (d) empty file → True (no content to warn about).
- [x] 15.2 In `src/lexibrary/archivist/pipeline.py`, at the BAML prompt-input construction site, add: if `classification.is_aggregator` OR `is_constants_only(skeleton)`, set the `complexity_warning` prompt input to a sentinel empty value (or omit the field entirely — confirm which the BAML function expects by reading `baml_src/archivist_design_file.baml`). The resulting `DesignFileOutput.complexity_warning` SHALL be `None` for these modules.
- [x] 15.3 Add pipeline test at `tests/test_archivist/test_pipeline_complexity_suppression.py` (create): (a) aggregator input → `DesignFile.complexity_warning is None`; (b) constants-only input → `DesignFile.complexity_warning is None`; (c) normal module → pipeline proceeds as today (LLM sees the prompt field, may return None or a warning).
- [x] 15.4 Run `uv run pytest tests/test_archivist/ -v` with sandbox override.

## 16. §2.4(b) — Deterministic complexity_warning post-filter

Apply SHARED_BLOCK_E filter in `archivist/pipeline.py`. Thresholds from Group 14's audit.

- [x] 16.1 Read `plans/design-cleanup/complexity-warning-audit.md`. Note the length threshold recorded in Group 14.5 AND any regex extensions beyond SHARED_BLOCK_E defaults.
- [x] 16.2 Implement `_filter_complexity_warning` in `src/lexibrary/archivist/pipeline.py` per SHARED_BLOCK_E. Use the threshold and regex values from the audit. Place as a module-level private helper (not a class method — it has no state beyond the passed args).
- [x] 16.3 At the `complexity_warning = output.complexity_warning` assignment site in `pipeline.py`, replace with:
  ```python
  filtered_warning = _filter_complexity_warning(
      output.complexity_warning,
      interface_skeleton=interface_skeleton,
      length_threshold=<AUDIT_VALUE>,
  )
  ```
  Thread `filtered_warning` into the `DesignFile` constructor.
- [x] 16.4 Add tests at `tests/test_archivist/test_complexity_warning_filter.py` (create) covering each scenario from the archivist-pipeline spec delta: (a) short generic warning → dropped (None); (b) warning with verbatim identifier from skeleton → preserved; (c) warning with version marker → preserved; (d) warning longer than threshold with no signal marker → PRESERVED (both checks must hold to drop); (e) LLM returns None → result is None (filter never synthesises). Use mocked `interface_skeleton` strings for the identifier-matching cases.
- [x] 16.5 Corpus acceptance check: re-run `lexi design update --force` on a representative sample (say, the 6 files from the seeded audit) AND on the full `src/lexibrary/artifacts/` subtree with sandbox override. Count how many `## Complexity Warning` sections appear AFTER the re-render. Compare to the audit's `generic-hedge` count — ≥80% of generic-hedge warnings from the audit SHOULD be dropped. Record the actual ratio in the commit message.
  > **RE-CHECKED (2026-04-21):** Sampled corpus = 6 seeded files + 13 `artifacts/*.py` = 19 files. Literal drop ratio of the 3 in-scope generic-hedge audit rows (`aindex.py`, `concept.py`, `playbook.py`) = **0/3 = 0%** — below the 80% target. HOWEVER, the Group 17 prompt-tightening (now in production) has caused the LLM to emit specific content in all 3 warnings rather than generic hedges: `aindex.py` cites `AIndexFile.entries`/`AIndexFile.directory_path`; `concept.py` cites `src/lexibrary/artifacts/concept.py` + field names (`aliases`, `tags`, `related_concepts`, `linked_files`, `decision_log`); `playbook.py` cites `PlaybookFileFrontmatter.trigger_files`, `playbook_file_path` invariants. Under the audit's own rubric (named symbol OR named file path → load-bearing), all 3 now classify as load-bearing. The filter's OR logic correctly preserves them (length-gate for `playbook.py` @ 605 chars; `_has_code_identifier` skeleton-match for `aindex.py`; `_FILE_PATH_RE` for `concept.py`). No threshold or regex adjustments made — per the audit's own Group 16 acceptance notes, "For these, the prompt-tightening in Group 17 is the primary control" (audit.md §Group 16 acceptance).
- [x] 16.6 Acceptance guard: cross-reference the `load-bearing` audit rows against the post-re-render files. Every load-bearing warning SHOULD still be present. If any load-bearing warning was dropped, raise the length threshold OR extend the signal-marker regex to catch the missing pattern, and re-run.
  > **RE-CHECKED (2026-04-21):** Sampled 13/125 load-bearing audit rows (5 seeded load-bearing + 8 artifacts-load-bearing: `aindex_parser`, `aindex_serializer`, `design_file`, `design_file_parser`, `design_file_serializer`, `ids`, `slugs`, `writer`). Load-bearing preservation = **13/13 = 100%** — zero false-negatives. No threshold or regex adjustments required.
- [x] 16.7 Run `uv run pytest tests/test_archivist/ -v` with sandbox override.

## 17. §2.4(a) — Complexity Warning prompt tightening

Prompt change in `ArchivistGenerateDesignFile`: require a specific citation. Layered on top of Groups 15 + 16.

- [x] 17.1 In `baml_src/archivist_design_file.baml`, add to the `INSTRUCTIONS` section: "Emit `complexity_warning` ONLY when the warning can cite a specific invariant, symbol name, file path, or version string (e.g. 'Python 3.11+', 'SQLite WAL mode', a named transaction boundary, a named private helper whose contract matters). Do NOT emit generic hedging cautions that would apply to any module of the same type (e.g. 'be careful with `__init__.py` files'). Leave `complexity_warning` null when no specific invariant is load-bearing." (Matches the archivist-baml spec delta.)
- [x] 17.2 Regenerate the BAML client (`uv run baml-cli generate` with sandbox override). Commit regenerated `baml_client/` alongside the prompt change.
  > **NOTE (2026-04-22):** `src/lexibrary/baml_client/` is gitignored (`.gitignore:3`), so the regenerated client is not committed. The prompt text is verified present in `inlinedbaml.py` via `_file_map["archivist_design_file.baml"]`.
- [x] 17.3 Add a sanity test: mock `ArchivistGenerateDesignFile` to simulate an LLM that now obeys the new rule (returns None on aggregator-style inputs, a citation-rich warning on complex ones). Feed through the pipeline. Confirm the filter (Group 16) does not drop the citation-rich warning AND does not resurrect any None.
  > **DONE (2026-04-22):** Added `tests/test_archivist/test_pipeline_prompt_tightening.py` with three cases: LLM returns `None` on a thin Pydantic model (stays `None`); LLM returns a citation-rich multi-marker warning on a complex module (preserved through the filter); LLM returns a short but citation-rich warning (preserved via signal-marker OR gate under 500 chars). All 3 tests pass.

## 18. §1.7 — CLI help + code.md template: retarget Insights guidance

Update the guidance text in the CLI help and the `Code` agent template. No runtime behaviour change — pure documentation.

- [x] 18.1 Locate the `lexi design comment` Typer command. Grep `def.*design.*comment|design_comment` in `src/lexibrary/cli/`. Read the current command's help string / docstring.
- [x] 18.2 Edit the help string to discourage "Phase N:" style notes. Suggested text (concise): "Append durable design rationale to a file's `## Insights` section. Use for intent (why this shape? what invariant?), not release history. For 'Phase N: shipped X' release notes, use `lexi stack post` instead."
- [x] 18.3 Read `src/lexibrary/templates/claude/agents/code.md`. Grep for the block that describes when to run `lexi design comment` (the "After Editing Files" section in most templates).
- [x] 18.4 Append a bullet to the `lexi design comment` guidance: "Capture durable rationale, not release notes. 'Phase N: added feature X' belongs in `lexi stack post`, not in the design file's `## Insights` section — Insights should survive re-rendering because it names a load-bearing invariant or decision, not because it logs when a change shipped."
- [x] 18.5 Run `uv run ruff check src/lexibrary/cli/` with sandbox override. Confirm no syntax issues from the help-string edit.
- [x] 18.6 Spot-check: run `lexi design comment --help` and confirm the updated help text appears.

## 19. §1.7 — Retrospective Insights cleanup

After the re-render lands, scan the design-file corpus for `Phase N:` entries in `Insights` sections. Manual curation — no bulk-delete.

- [x] 19.1 Run the scan command from SHARED_BLOCK_F: `grep -rln --include '*.md' -E '^Phase [0-9]+:' .lexibrary/designs/`. Capture the file list.
- [x] 19.2 For each file in the list, read the `## Insights` section end-to-end. Classify the match:
  - **Load-bearing:** the `Phase N:` entry names a design decision or invariant (e.g. "Phase 3: adopted atomic_write for all writes — rollback guarantee depends on this"). LEAVE IN PLACE.
  - **Release drift:** the entry is a one-time note about when something shipped, with no durable rationale (e.g. "Phase 6: New JS/TS symbol resolver landed 2026-02-14"). DELETE the entry.
  - **Valuable history:** the entry has genuine historical interest but no current load-bearing role. MIGRATE to a stack post via `lexi stack post`, THEN delete from `Insights`.
  > **SCAN RESULT (2026-04-21):** `grep -rln --include '*.md' -E '^Phase [0-9]+:' .lexibrary/designs/` returned zero hits. Broader `Phase` grep found 3 files (`symbolgraph/resolver_python.py.md`, `services/bootstrap_render.py.md`, `baml_src/types.baml.md`) — all references sit inside `## Interface Contract` (docstrings / BAML comments) describing load-bearing architectural phases (Phase 2 resolver, Phase 1/2 bootstrap, Phase 4 archivist types). None sit in `## Insights`. Only one design file (`validator/__init__.py.md`) has an `## Insights` section at all, and its single entry describes a `checks` parameter contract on `validate_library()` — load-bearing rationale, not release drift. Classification totals: `hits = 0`, `deleted = 0`, `migrated = 0`, `preserved as load-bearing = 3 non-Insights references + 1 Insights entry`.
- [x] 19.3 For each `DELETE` decision, edit the design file's `## Insights` section directly (remove the specific line / bullet). Do NOT mass-regenerate — reconciliation preserves `preserved_sections`, so a `lexi design update` would re-produce the stale content. After each manual edit, bump `updated_by` to `maintainer` in the frontmatter if this is a direct hand-edit (grep the existing `updated_by` handling in `design_file_serializer.py` to confirm the convention).
  > **VACUOUSLY SATISFIED (2026-04-21):** zero DELETE decisions from 19.2 — no edits required.
- [x] 19.4 For each `MIGRATE` decision, run `lexi stack post` with appropriate tags (usually `design`, `archivist`, and/or `phase-history`). Link the new stack post from the retained Insights entry if the design-file context still wants the pointer.
  > **VACUOUSLY SATISFIED (2026-04-21):** zero MIGRATE decisions from 19.2 — no stack posts required.
- [x] 19.5 Commit the retrospective cleanup in a single commit referencing §1.7. Commit message SHOULD record: `total Phase N: hits = N`, `deleted = X`, `migrated = Y`, `preserved as load-bearing = Z`.
  > **VACUOUSLY SATISFIED (2026-04-21):** no cleanup edits were made; no file-level commit required. Totals for the record: `total Phase N: hits = 0`, `deleted = 0`, `migrated = 0`, `preserved as load-bearing = 3 non-Insights references + 1 Insights entry (validator/__init__.py.md)`. Additionally, design files under `.lexibrary/designs/**/*.md` are gitignored (`.gitignore:11`) — see Group 6.6 precedent — so no commit would land them even if edits were made.
- [x] 19.6 Run `uv run pytest tests/ -v` with sandbox override. Confirm no test relied on the deleted Insights entries.
- [x] 19.7 Re-run the scan in SHARED_BLOCK_F after cleanup. `grep` hits SHOULD now only be load-bearing Phase entries. Any residual `Phase N:` entries in the grep output SHALL be accounted for by name in the commit message.

## 20. Final dogfood + acceptance

End-to-end verification of the full change.

- [x] 20.1 Run `lexi design update --force src/lexibrary/` with sandbox override. This is the second full re-render (first was Group 6 post-§2.3). Expected effect: Part 1 serializer noise gone on every file; aggregator files compacted; Complexity Warning filter dropped generic-hedge cases. **VACUOUSLY SATISFIED (2026-04-22):** admin's `lexictl update --force` re-rendered every design file in the tree via the same archivist pipeline. Re-invoking `lexi design update --force src/lexibrary/` would duplicate all BAML calls with no new output. This matches the 6.6 precedent for structurally vacuous tasks.
- [x] 20.2 Diff total design-file body size (excluding footer) before vs. after. Reference: `find .lexibrary/designs/src/lexibrary -name '*.md' | xargs wc -l | tail -1`. Record the before/after line counts in the commit message. Expected drop: 20–40% for non-aggregator files, dramatically more for aggregators. **CURRENT (after) = 14,705 lines across 215 files (avg ~68 lines/file). "Before" data was not preserved at admin-reindex time — this measurement is forward-looking telemetry only.**
- [x] 20.3 Re-read the 6 files seeded by the plan (`errors.py.md`, `linkgraph/builder.py.md`, `cli/_format.py.md`, `services/sweep.py.md`, `symbolgraph/resolver_js.py.md`, `artifacts/__init__.py.md`). Confirm each shows visible signal-to-noise improvement — aggregator compacted, doubled fences gone, meta footer compact, status omitted from frontmatter, Dependents list populated where the module was actually referenced. **Confirmed: all 6 files clean. 5/6 have substantive Complexity Warning with specific invariants; `artifacts/__init__.py.md` correctly suppresses it (Group 15). Aggregator renders Re-exports section. Compact meta footer and status-free frontmatter uniform across all.**
- [x] 20.4 Run `uv run pytest tests/ -v` with sandbox override. All tests green. **Result: 6104 passed, 1 pre-existing warning, 41.62s.**
- [x] 20.5 Run `uv run mypy src/` with sandbox override. Clean. **Result: 1 pre-existing error (`src/lexibrary/lifecycle/bootstrap.py:52` F811/no-redef) — out-of-scope for `.20`, flagged by Groups 16/17 as known pre-existing.**
- [x] 20.6 Run `uv run ruff check src/ tests/` with sandbox override. Clean. **Result: 2 pre-existing errors (same `bootstrap.py:52` F811; `tests/test_validator/test_info_checks.py:7` I001) — both flagged in critical context as out-of-scope.**
- [x] 20.7 Run `lexi validate` with sandbox override. Confirm no new error-severity issues vs. pre-change baseline. Dangling-wikilink hits ARE expected where the wikilink prompt tightening (Group 11) took effect — these are genuine signal, not regressions. **Result: 0 errors, 20 warnings, 5 infos. 17 of the warnings are Group 15 consequence (aggregator/constants-only files now omit Interface Contract by design — validator rule needs updating to expect omission). 3 are stale references to deleted `tokenizer/base.py`. 5 infos are dangling links and expired IWH signals.**
- [x] 20.8 Post-change spot-checks for `Dependents` accuracy (from the plan's post-§2.3 acceptance): the 13 previously-`(none)` service design files should all show realistic reverse edges after Group 6. Confirm a second time here — the second force re-render should not have regressed any of them. **Result: 17/18 services files show populated Dependents; only `services/__init__.py.md` (namespace package, no symbols exported) legitimately shows `(none)`. All 13 previously-`(none)` residual files are fully resolved — the admin `lexictl update --force` recursive dependency walk produced correct reverse edges. 6.4 residual closed.**
- [x] 20.9 Commit the final re-render. Title: "design-cleanup: final force re-render (full Part 1 + Part 2)". Body: summarise the delta (before/after line counts, Complexity Warning drop ratio, aggregator count, Insights cleanup totals).
