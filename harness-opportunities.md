# Harness Engineering Opportunities for Lexibrary

**Date:** 2026-03-14
**Source analysis:** [oai-harness-engineering-analysis.md](oai-harness-engineering-analysis.md)
**Purpose:** Detailed implementation briefs for each opportunity, written so a fresh agent can turn any one into a plan without needing the original research.

---

## Table of Contents

1. [Actionable Validator Remediation](#1-actionable-validator-remediation)
2. [Convention-from-Failure Workflow](#2-convention-from-failure-workflow)
3. [Convention Enforcement Levels](#3-convention-enforcement-levels)
4. [Dependency Direction Policy](#4-dependency-direction-policy)
5. [Bundled Context Command](#5-bundled-context-command)
6. [Role-Specific Agent Rule Templates](#6-role-specific-agent-rule-templates)
7. [MCP Server for Lexi Commands](#7-mcp-server-for-lexi-commands)
8. [Project-Level Reference Artifacts](#8-project-level-reference-artifacts)
9. [Maintenance Playbook](#9-maintenance-playbook)

---

## 1. Actionable Validator Remediation

> **Cross-reference:** The Curator agent's validation sweep (§2.3) will consume these actionable
> suggestions to self-correct during automated sweeps. See
> [curator-agent.md §2.3](curator-agent.md#23-validation-sweep).

### What It Solves

Lexibrary's validator already has a `suggestion` field on `ValidationIssue` (defined in `src/lexibrary/validator/report.py:29-36`), and many checks populate it. However, existing suggestions are descriptive ("Fix YAML syntax in frontmatter block", "Update or remove the file reference") rather than prescriptive with specific commands. Harness engineering shows that linter error messages that **teach the agent how to fix the issue** turn validation into continuous education. When an agent runs `lexi validate` and gets "Run `lexi concept new ScopeRoot` to create the concept", it can self-correct in a single step.

### How to Implement

**No new fields needed.** The `suggestion` field already exists on `ValidationIssue` and is already rendered in the table output by `ValidationReport.render()` at `src/lexibrary/validator/report.py:151-155`. The work is upgrading every check function in `src/lexibrary/validator/checks.py` to provide agent-actionable suggestions.

**File to modify:** `src/lexibrary/validator/checks.py` (~900 lines, contains all check functions)

**Pattern to follow for each check:**

```python
# BEFORE (current):
ValidationIssue(
    severity="error",
    check="wikilink_resolution",
    message=f"Unresolved wikilink [[{link_name}]]",
    artifact=str(rel_path),
    suggestion="",  # or vague text
)

# AFTER (upgraded):
ValidationIssue(
    severity="error",
    check="wikilink_resolution",
    message=f"Unresolved wikilink [[{link_name}]]",
    artifact=str(rel_path),
    suggestion=f"Run `lexi concept new {link_name}` to create the concept, or remove the [[{link_name}]] wikilink from the file.",
)
```

**Specific upgrades needed per check category:**

| Check | Current suggestion quality | Upgraded suggestion |
|---|---|---|
| `wikilink_resolution` | Has fuzzy-match suggestions already | Add `lexi concept new <name>` as alternative |
| `hash_freshness` | Empty or generic | "Source file changed. Run `lexi design update <source_file>` to regenerate the design file." |
| `orphan_concepts` | Generic | "No design files reference this concept. Either add `[[ConceptName]]` to a relevant design file, or run `lexi concept deprecate <slug>`." |
| `orphaned_designs` | "Remove the design file or restore the source file." | Good as-is, but could add the rm command |
| `convention_gap` | Generic | "Convention '<title>' applies to <scope> but <N>/<M> files follow it. Review non-conforming files or narrow the convention scope." |
| `convention_orphaned_scope` | Generic | "Convention scope '<scope>' no longer exists. Run `lexi convention deprecate <slug>` to retire this convention." |
| `stack_staleness` | Generic | "Stack post <id> has had no activity. Run `lexi stack comment <id> --body 'still relevant'` to keep it, or `lexi stack outdated <id> --reason '...'` to archive." |
| `deprecated_concept_usage` | Generic | "Design file references deprecated concept [[Name]]. Use [[NewName]] instead (superseded_by)." |
| `config_valid` | Generic | Include the specific validation error from Pydantic |
| All frontmatter checks | "Add '<field>' to frontmatter." | Good pattern, keep it |

**Testing:** Each check has tests in `tests/test_validator/`. Update test assertions to verify suggestion text is non-empty and contains relevant command/action.

### Complexity and Value

- **Complexity:** Low. Pure string changes across existing check functions. No new models, no new config, no architectural changes.
- **Value:** High. Every `lexi validate` run becomes a self-healing feedback loop. Agents can parse suggestions and act on them without human intervention.
- **Estimated scope:** ~40 check functions to audit; ~25 need suggestion upgrades.

---

## 2. Convention-from-Failure Workflow

> **Cross-reference:** The Curator agent proposes a speculative use case (§2.10) where it detects
> recurring validation failure patterns and auto-proposes conventions. See
> [curator-agent.md §2.10](curator-agent.md#210-convention-from-failure-detection-speculative).

### What It Solves

Harness engineering's core principle: "Anytime an agent makes a mistake, engineer a solution so the agent never makes that mistake again." Currently in Lexibrary, an agent can create a convention (`lexi convention new`) and a Stack post (`lexi stack post`), but there's no single workflow that connects "agent made mistake X" to "convention created to prevent X." The feedback loop exists in pieces but requires multiple steps and manual reasoning about scope, tags, and body content.

### How to Implement

Add a `--from-failure` flag to `lexi convention new` that accepts a failure description and generates a convention with pre-populated fields.

**File to modify:** `src/lexibrary/cli/conventions.py` (the `convention_new` function, lines 22-99)

**New flag:**

```python
@convention_app.command("new")
def convention_new(
    *,
    # ... existing params ...
    from_failure: Annotated[
        str | None,
        typer.Option("--from-failure", help="Describe the agent failure to prevent. Generates convention body with rule and rationale."),
    ] = None,
) -> None:
```

**Behavior when `--from-failure` is provided:**

1. If `--body` is also provided, error out ("Cannot use --from-failure with --body")
2. Generate convention body from the failure description:
   ```
   Do not <inferred prohibition from failure description>.

   **Rationale:** This convention was created after an agent failure:
   > <failure description>

   **Prevention:** <restatement as positive instruction>
   ```
3. If `--title` not provided, derive from failure (e.g., "Prevent: <first 50 chars of failure>")
4. If `--source` not provided, default to `"agent"` (since this is typically agent-initiated)
5. Auto-tag with `"failure-prevention"` in addition to any `--tag` values

**Example usage:**

```bash
lexi convention new \
  --from-failure "Agent imported from cli/ into types/ layer, violating dependency direction" \
  --scope "src/types/" \
  --tag "architecture"
```

Would generate:

```markdown
---
title: "Prevent: Agent imported from cli into types layer"
scope: src/types/
tags: [failure-prevention, architecture]
status: draft
source: agent
priority: -1
aliases: []
---
Do not import from cli/ or any downstream layer into src/types/. The types layer must only depend on standard library and external packages.

**Rationale:** This convention was created after an agent failure:
> Agent imported from cli/ into types/ layer, violating dependency direction

**Prevention:** All imports in src/types/ must be from the standard library, third-party packages, or other files within src/types/.
```

**Optionally:** Also create a Stack post linking to the convention, so the failure is documented in the Q&A knowledge base too. This could be a `--also-post-stack` flag that calls `lexi stack post` internally.

**Model changes:** None. The existing `ConventionFileFrontmatter` and `ConventionFile` models handle all needed fields.

**Serializer:** Uses existing `serialize_convention_file()` from `src/lexibrary/conventions/serializer.py`.

### Complexity and Value

- **Complexity:** Low. One new flag on an existing command, body text generation logic, no model changes.
- **Value:** High. Closes the failure-to-prevention loop in a single command. Makes the CLAUDE.md debugging workflow actionable: agent encounters failure -> `lexi convention new --from-failure "..."` -> future agents are protected.
- **Estimated scope:** ~50 lines of new code in `conventions.py`, plus tests.

---

## 3. Convention Enforcement Levels

### What It Solves

Lexibrary's validator reports convention gaps as `info` severity. Conventions are "educational and suggestion-based." Harness engineering argues that critical conventions (like dependency direction rules, naming standards, import restrictions) must be **mechanically enforced** — blocking commits or CI — to be reliable at scale. Not all conventions need this: stylistic preferences can stay advisory. The gap is the lack of a per-convention enforcement knob.

### How to Implement

**Step 1: Add `enforcement` field to `ConventionFileFrontmatter`**

File: `src/lexibrary/artifacts/convention.py`

```python
class ConventionFileFrontmatter(BaseModel):
    title: str
    scope: str = "project"
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent", "config"] = "user"
    priority: int = 0
    aliases: list[str] = []
    deprecated_at: datetime | None = None
    enforcement: Literal["advisory", "warn", "enforce"] = "advisory"  # NEW
```

- `advisory` (default, backward-compatible): reported as `info` severity (current behavior)
- `warn`: reported as `warning` severity
- `enforce`: reported as `error` severity (blocks CI if `lexictl validate --ci` is used in pipeline)

**Step 2: Update validator checks to respect enforcement level**

File: `src/lexibrary/validator/checks.py`

The `check_convention_gap` and `check_convention_consistent_violation` functions currently hardcode `severity="info"`. They need to:

1. Parse the convention file to get its `enforcement` level
2. Map enforcement to severity: `advisory` -> `info`, `warn` -> `warning`, `enforce` -> `error`
3. Use the mapped severity in the `ValidationIssue`

This means the check functions need access to the convention's frontmatter, not just its scope/rule. Currently `check_convention_gap` loads conventions via `ConventionIndex` which provides full `ConventionFile` objects — so the data is already available.

**Step 3: Update `AVAILABLE_CHECKS` registry**

File: `src/lexibrary/validator/__init__.py` (lines 80-128)

The registry currently maps each check to a **fixed** default severity. With enforcement levels, the severity becomes dynamic. Two approaches:

- **Option A (simpler):** Keep the registry default as-is (`"info"`) but let the check function itself emit issues at variable severities. The severity filter in `validate_library()` already operates on the *check's* default severity (for deciding which checks to run), not on individual issue severity. This means enforced convention issues would always be emitted regardless of `--severity` filter. This is arguably correct — if you marked a convention as `enforce`, you always want to see it.

- **Option B:** Change the registry to support variable severity. More complex, less necessary.

Recommend **Option A** — it's backward-compatible and the behavior is intuitive.

**Step 4: Add `--enforcement` option to `lexi convention new`**

File: `src/lexibrary/cli/conventions.py`

```python
enforcement: Annotated[
    str,
    typer.Option("--enforcement", help="Enforcement level: advisory, warn, or enforce."),
] = "advisory",
```

**Step 5: Add global default to config**

File: `src/lexibrary/config/schema.py` — `ConventionConfig` class (line 156)

```python
class ConventionConfig(BaseModel):
    lookup_display_limit: int = 5
    deprecation_confirm: Literal["human", "maintainer"] = "human"
    default_enforcement: Literal["advisory", "warn", "enforce"] = "advisory"  # NEW
```

This lets project maintainers set a global default. Per-convention `enforcement` overrides the global.

**Step 6: Update serializer**

File: `src/lexibrary/conventions/serializer.py` — ensure the `enforcement` field is included in serialized YAML frontmatter.

**Step 7: Update parser**

File: `src/lexibrary/conventions/parser.py` — no changes needed if using Pydantic; the model handles deserialization automatically. But verify that old convention files without `enforcement` field gracefully default to `"advisory"`.

### Complexity and Value

- **Complexity:** Medium. Touches model, config, validator, CLI, serializer, and parser. But each change is small and well-contained.
- **Value:** High. This is the bridge between Lexibrary's advisory model and harness engineering's enforcement model. Critical for dependency direction enforcement (Opportunity #4) which needs this as prerequisite.
- **Estimated scope:** ~100 lines across 6 files, plus tests for each severity level mapping.

### Dependencies

- The serializer (`src/lexibrary/conventions/serializer.py`) must handle the new field.
- Test files: `tests/test_conventions/test_serializer.py`, `tests/test_conventions/test_parser.py`, `tests/test_artifacts/test_convention_models.py`, `tests/test_validator/test_orchestrator.py`.

---

## 4. Dependency Direction Policy

### What It Solves

OpenAI's most impactful harness engineering practice: enforcing strict unidirectional dependency layering (Types -> Config -> Repo -> Service -> Runtime -> UI). Violations are caught by deterministic linters. This constrains the agent's solution space, which paradoxically makes agents more productive because they can't explore architectural dead ends.

Lexibrary already tracks dependencies (forward and reverse) via the linkgraph and has a `forward_dependencies` validator check. But it doesn't enforce **directionality** — it knows A depends on B but doesn't know whether that dependency is architecturally valid.

### How to Implement

**Step 1: Add `dependency_policy` to config**

File: `src/lexibrary/config/schema.py`

```python
class DependencyLayer(BaseModel):
    """A single layer in the dependency policy."""
    model_config = ConfigDict(extra="ignore")

    name: str
    directories: list[str]  # e.g., ["src/types/", "src/models/"]


class DependencyPolicyConfig(BaseModel):
    """Dependency direction enforcement policy."""
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    layers: list[DependencyLayer] = Field(default_factory=list)
    rule: Literal["downstream_only"] = "downstream_only"
    # downstream_only: each layer may only import from layers above it in the list


class LexibraryConfig(BaseModel):
    # ... existing fields ...
    dependency_policy: DependencyPolicyConfig = Field(default_factory=DependencyPolicyConfig)
```

**Example config:**

```yaml
dependency_policy:
  enabled: true
  rule: downstream_only
  layers:
    - name: types
      directories: [src/lexibrary/artifacts/]
    - name: config
      directories: [src/lexibrary/config/]
    - name: core
      directories: [src/lexibrary/conventions/, src/lexibrary/wiki/, src/lexibrary/stack/, src/lexibrary/linkgraph/]
    - name: services
      directories: [src/lexibrary/validator/, src/lexibrary/search.py, src/lexibrary/init/]
    - name: cli
      directories: [src/lexibrary/cli/]
```

Layers are ordered top-to-bottom. A file in `cli/` can import from `services/`, `core/`, `config/`, and `types/`. A file in `types/` can only import from standard library and external packages.

**Step 2: Add `check_dependency_direction` validator check**

File: `src/lexibrary/validator/checks.py`

```python
def check_dependency_direction(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Enforce dependency direction policy from config."""
    config = load_config(lexibrary_dir)
    policy = config.dependency_policy
    if not policy.enabled or not policy.layers:
        return []

    # Build layer index: directory_prefix -> layer_index
    layer_index: dict[str, int] = {}
    for i, layer in enumerate(policy.layers):
        for dir_path in layer.directories:
            layer_index[dir_path.rstrip("/")] = i

    issues: list[ValidationIssue] = []
    designs_dir = lexibrary_dir / "designs"

    for md_path in sorted(designs_dir.rglob("*.md")):
        design = parse_design_file(md_path)
        if design is None:
            continue

        source_layer = _find_layer(design.source_path, layer_index)
        if source_layer is None:
            continue  # File not in any defined layer

        for dep_path in design.dependencies:
            dep_layer = _find_layer(dep_path, layer_index)
            if dep_layer is None:
                continue
            if dep_layer > source_layer:
                # Importing from a lower (downstream) layer — violation!
                issues.append(ValidationIssue(
                    severity="error",
                    check="dependency_direction",
                    message=f"Imports from downstream layer: {dep_path}",
                    artifact=design.source_path,
                    suggestion=f"Move the dependency to {dep_path} upward, or restructure so {design.source_path} does not depend on a downstream layer.",
                ))

    return issues
```

**Step 3: Register the check**

File: `src/lexibrary/validator/__init__.py`

```python
AVAILABLE_CHECKS["dependency_direction"] = (check_dependency_direction, "error")
```

**Step 4: Surface in `lexi lookup`**

When `lexi lookup <file>` runs for a file in a defined layer, include a line like:
```
Layer: types (may only import from: standard library, external packages)
```

This gives agents immediate architectural context before editing.

**How the linkgraph provides dependency data:**

The linkgraph `links` table has `link_type = "ast_import"` edges between artifacts. The `forward_dependencies` check already traverses these. The new check follows the same pattern but adds the layer policy lookup.

Alternatively, if the linkgraph is unavailable, the check can fall back to parsing design file frontmatter `dependencies` lists (which list import paths).

**Current dependency data available:**

- Design file frontmatter has a `dependencies` field (list of imported file paths)
- The design file parser at `src/lexibrary/artifacts/design_file_parser.py` extracts this
- The `check_forward_dependencies` function in `checks.py` already loads and iterates these

### Complexity and Value

- **Complexity:** Medium. New config model, new validator check, optional lookup enhancement. The dependency data is already available in design files.
- **Value:** Very high. This is the single highest-leverage idea from harness engineering. Constraining the solution space is what makes agents reliable at scale. Without direction enforcement, agents can (and do) create circular dependencies and violate layering.
- **Estimated scope:** ~150 lines of new code across config, validator, and optionally lookup.
- **Prerequisite for:** Opportunity #3 (enforcement levels) makes this more powerful — dependency direction violations at `enforce` level block CI.

### Key Design Decisions for the Implementing Agent

1. **Layer matching uses longest prefix.** If a file is at `src/lexibrary/config/loader.py`, and layers define `src/lexibrary/config/` and `src/lexibrary/`, the more specific match wins.
2. **Files not in any layer are ignored.** The check only validates files that fall within a defined layer. External packages are always allowed.
3. **The check uses design file `dependencies`, not AST parsing directly.** This means it works even when the linkgraph is unavailable (graceful degradation).
4. **Tests should cover:** violation detection, no-violation baseline, files outside layers, config disabled, empty layers list.

---

## 5. Bundled Context Command

### What It Solves

Harness engineering emphasizes tiered context with progressive disclosure: "an agent should receive exactly the context it needs for its current task — no more, no less." Lexibrary already has the three tiers (CLAUDE.md -> `lexi lookup` -> `lexi search`), but when an agent is about to edit a file, it needs to make multiple calls: `lexi lookup <file>`, check for IWH signals, find relevant Stack posts, get applicable conventions. A single `lexi context <file>` command would bundle exactly the right Tier 2 context in one call, optimized for token budget.

### How to Implement

**New command:** `lexi context <file>`

File: `src/lexibrary/cli/lexi_app.py` — add a new command

```python
@lexi_app.command("context")
def lexi_context(
    file_path: Annotated[str, typer.Argument(help="Source file to get editing context for.")],
    *,
    budget: Annotated[int | None, typer.Option("--budget", help="Max token budget for output.")] = None,
) -> None:
    """Bundle all context needed before editing a file into a single output."""
```

**What it returns (in order, truncated to fit token budget):**

1. **Design file summary** — description, public interface, dependencies (from `lexi lookup` logic)
2. **Applicable conventions** — all active conventions for this file's scope, with rules
3. **IWH signals** — any pending signals for this file's directory
4. **Relevant Stack posts** — open posts referencing this file (from linkgraph `reverse_deps` with `link_type="stack_ref"`)
5. **Dependency warnings** — if dependency direction policy is configured, show the file's layer and allowed import directions

**Implementation approach:**

The `lexi lookup` command already composes most of this (see `lexi_app.py` `lexi_lookup` function). The `context` command reuses the same underlying logic but:
- Includes IWH signals (lookup doesn't currently show these)
- Includes relevant Stack posts with their problem/status
- Adds dependency direction context if policy is configured
- Respects a token budget, truncating lower-priority sections first

**Core logic location:** The lookup-upgrade plan (referenced in MEMORY.md) already calls for extracting lookup logic into `src/lexibrary/lookup.py` returning a `LookupResult` dataclass. The `context` command would build on that same extracted module, adding the extra sections.

**If `lookup.py` doesn't exist yet:** The implementing agent should check. If not, the context command can compose from existing modules directly:
- Design file: `parse_design_file()` from `src/lexibrary/artifacts/design_file_parser.py`
- Conventions: `ConventionIndex` from `src/lexibrary/conventions/index.py`
- IWH: scan for `.iwh` files in the file's directory
- Stack posts: `reverse_deps()` on `LinkGraph` for stack refs, or `StackIndex.by_scope()`

**Token budget management:**

Current token budget config is in `src/lexibrary/config/schema.py` `TokenBudgetConfig` class. Add a `context_total_tokens` budget (default: 2000). Use `ApproximateCounter` from `src/lexibrary/tokenizer/approximate.py` to measure output and truncate.

### Complexity and Value

- **Complexity:** Medium. New command composing existing queries, with token budget management.
- **Value:** Medium-high. Reduces multiple CLI calls to one, which matters for agent token efficiency. Also serves as the natural foundation for an MCP `context` tool (Opportunity #7).
- **Estimated scope:** ~200 lines for the command + rendering logic, plus tests.

---

## 6. Role-Specific Agent Rule Templates

### What It Solves

Harness engineering emphasizes agent specialization: focused agents with restricted tool access outperform general-purpose agents with full access. A code review agent shouldn't be editing files. A research agent shouldn't be refactoring code. Lexibrary already has the two-CLI split (lexi = agent-facing, lexictl = maintenance-only), but it generates one-size-fits-all CLAUDE.md rules. Different agent roles need different instructions.

### How to Implement

**Step 1: Define role templates**

Create template files in `src/lexibrary/templates/` (this directory already exists for agent rule templates):

- `roles/implementer.md` — Default role. Full editing permissions. Current CLAUDE.md content.
- `roles/reviewer.md` — Read-only. Can run `lexi lookup`, `lexi search`, `lexi validate`. Cannot edit source files. Can create Stack posts (to flag issues). Cannot run `lexictl`.
- `roles/researcher.md` — Search and document. Can run all `lexi` read commands. Can create concepts and Stack posts. Cannot edit source files.
- `roles/maintainer.md` — Entropy management. Can run `lexi validate`, `lexi design update`, `lexi iwh clean`. Can edit design files and conventions. Cannot edit source files.

**Step 2: Generate role files during `lexictl setup`**

File: `src/lexibrary/cli/lexictl_app.py` or wherever the setup/init logic lives

```bash
lexictl setup --roles          # Generate all role templates
lexictl setup --roles reviewer  # Generate specific role
```

Output location: `.lexibrary/roles/<role>.md`

**Step 3: Add `role` field to CLAUDE.md generation**

When `lexictl setup --env claude` generates CLAUDE.md, it generates the default (implementer) role. Role-specific files are generated alongside it. The user's CLAUDE.md can include a pointer:

```markdown
## Agent Roles
Role-specific instructions are in `.lexibrary/roles/`:
- `reviewer.md` — For code review agents (read-only)
- `researcher.md` — For search and documentation agents
- `maintainer.md` — For entropy management agents
```

**Step 4: Integration with Claude Code hooks**

Role files can be loaded by PreToolUse hooks based on the current agent's declared role, or simply referenced manually when spawning specialized sub-agents.

**Template content examples:**

**reviewer.md:**
```markdown
# Agent Role: Reviewer

You are a code review agent. Your job is to analyze code quality, find issues, and document them.

## Permitted Actions
- Run `lexi lookup <file>` to understand files
- Run `lexi search` to find related context
- Run `lexi validate` to check library health
- Run `lexi stack post` to document issues found
- Read any file in the codebase

## Prohibited Actions
- Do NOT edit any source files
- Do NOT run `lexictl` commands
- Do NOT create or modify design files
- Do NOT create conventions

## Workflow
1. Run `lexi orient` to understand project structure
2. For each file to review, run `lexi lookup <file>`
3. Read the file and analyze for issues
4. For each issue found, run `lexi stack post --title "..." --problem "..." --tag review`
```

### Complexity and Value

- **Complexity:** Low. Template files + minor setup command changes. No model or core logic changes.
- **Value:** Medium. Prevents agent role confusion and unsolicited refactoring. Most useful when teams run multiple concurrent agents (a pattern harness engineering promotes).
- **Estimated scope:** ~4 template files, ~50 lines of setup command changes, plus tests.

---

## 7. MCP Server for Lexi Commands

### What It Solves

Harness engineering emphasizes making all team tools agent-accessible, preferably via CLI or MCP (Model Context Protocol). Stripe's "Toolshed" connects agents to 400+ internal tools via MCP servers. Lexibrary currently exposes everything through the `lexi` CLI, which agents call via `Bash` tool invocations. An MCP server would let IDEs and agent frameworks call `lookup`, `search`, `validate`, `orient`, etc. as native tools — reducing shell-out overhead, enabling structured JSON responses natively, and opening integration with non-CLI agent platforms.

### How to Implement

**Prerequisite:** Core logic extraction from CLI glue code. The MEMORY.md notes this is already planned: "`lexi lookup` core logic must live in `src/lexibrary/lookup.py` (returning `LookupResult` dataclass), NOT in CLI glue code." The search module (`src/lexibrary/search.py`) is already partially extracted — `unified_search()` is a standalone function that returns `SearchResults`.

**Step 1: Verify/complete core logic extraction**

Check which commands already have extracted core logic vs. which are still in CLI glue:
- `search` -> `src/lexibrary/search.py:unified_search()` — already extracted
- `lookup` -> may still be in CLI glue (check `lexi_app.py` `lexi_lookup` function)
- `validate` -> `src/lexibrary/validator/__init__.py:validate_library()` — already extracted
- `orient` -> likely in CLI glue
- `impact` -> likely in CLI glue

For commands still in CLI glue, extract core logic into standalone functions that return dataclasses.

**Step 2: Create MCP server module**

New file: `src/lexibrary/mcp_server.py` (or `src/lexibrary/mcp/` package)

Use the `mcp` Python SDK (`pip install mcp`). Define tools:

```python
@server.tool("lexi_lookup")
async def mcp_lookup(file_path: str, full: bool = False) -> dict:
    """Look up a file's role, dependencies, and conventions before editing."""
    result = lookup(project_root, file_path, full=full)
    return result.to_dict()

@server.tool("lexi_search")
async def mcp_search(query: str = None, tag: str = None, type: str = None) -> dict:
    """Search across concepts, conventions, design files, and Stack posts."""
    results = unified_search(project_root, query=query, tag=tag, artifact_type=type)
    return results.to_dict()  # Need to add to_dict() to SearchResults

@server.tool("lexi_validate")
async def mcp_validate(severity: str = None, check: str = None) -> dict:
    """Run library health checks."""
    report = validate_library(project_root, lexibrary_dir, severity_filter=severity, check_filter=check)
    return report.to_dict()
```

**Step 3: Add CLI entry point**

```bash
lexi mcp serve           # Start MCP server (stdio transport)
lexi mcp serve --port N  # Start MCP server (HTTP transport)
```

**Step 4: Generate MCP config for Claude Code**

During `lexictl setup --env claude`, generate `.mcp.json` or update `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lexibrary": {
      "command": "uv",
      "args": ["run", "lexi", "mcp", "serve"]
    }
  }
}
```

### Complexity and Value

- **Complexity:** Medium-high. Requires core logic extraction (partially done), MCP SDK integration, new module, new CLI subcommand.
- **Value:** High for adoption. MCP is becoming the standard protocol for tool integration. This positions Lexibrary as a first-class tool for any agent platform, not just CLI-based ones.
- **Estimated scope:** ~300 lines for the MCP server, plus core logic extraction work.
- **New dependency:** `mcp` Python SDK (add to `pyproject.toml`).

### Key Design Decisions

1. **Stdio transport first.** Claude Code, Cursor, and most MCP clients use stdio. HTTP transport is nice-to-have for remote setups.
2. **Read-only tools only.** The MCP server should only expose `lexi` (agent-facing, read-only) commands, not `lexictl` (maintenance) commands. This maintains the security model.
3. **Return structured JSON always.** MCP tools return dictionaries; no markdown rendering needed.
4. **Project root discovery:** The server needs to find the project root. Use `find_project_root()` from `src/lexibrary/utils/root.py`.

---

## 8. Project-Level Reference Artifacts

### What It Solves

Harness engineering integrates dynamic context from runtime systems — observability dashboards, CI pipelines, deployment status. Lexibrary is entirely static-context: it indexes what's in the repo but has no awareness of external systems. This doesn't mean Lexibrary needs to integrate directly with Grafana or Datadog, but it should provide a structured way to **point agents at external resources** and tell them how to query for dynamic data.

### How to Implement

**New artifact type:** Reference files in `.lexibrary/references/`

**Step 1: Define the model**

New file: `src/lexibrary/artifacts/reference.py`

```python
class ReferenceFrontmatter(BaseModel):
    title: str
    type: Literal["ci", "observability", "runbook", "dashboard", "api", "other"] = "other"
    url: str = ""
    query_command: str = ""  # CLI command agents can run to get live data
    tags: list[str] = []
    scope: str = "project"  # Which part of codebase this is relevant to
    created_at: datetime | None = None

class ReferenceFile(BaseModel):
    frontmatter: ReferenceFrontmatter
    body: str = ""
    file_path: Path | None = None
```

**Step 2: Add parser and serializer**

Following the same pattern as `src/lexibrary/conventions/parser.py` and `src/lexibrary/conventions/serializer.py`.

**Step 3: Add CLI commands**

File: New `src/lexibrary/cli/references.py`

```bash
lexi reference new --title "CI Pipeline" --type ci --url "https://..." --query-command "gh run list --limit 5" --scope "project" --body "Check CI status before opening PRs."
lexi reference list                    # List all references
lexi reference list --type ci          # Filter by type
lexi reference list --scope "src/api/" # Filter by scope
```

**Step 4: Integrate into `lexi lookup` and `lexi context`**

When `lexi lookup src/api/handler.py` runs, include any references scoped to `src/api/` or `project`:

```
## External References
- CI Pipeline: https://github.com/org/repo/actions (run `gh run list --limit 5`)
- API Latency Dashboard: https://grafana.internal/d/api-latency
```

**Step 5: Include in search**

Add `"reference"` to `VALID_ARTIFACT_TYPES` in `src/lexibrary/search.py` and add `_search_references()` function.

**Step 6: Include in linkgraph**

Add `kind = "reference"` to the artifacts table. References can be linked to specific files via `scope`.

**Example reference files:**

```yaml
# .lexibrary/references/ci-pipeline.md
---
title: CI Pipeline
type: ci
url: https://github.com/org/repo/actions
query_command: "gh run list --limit 5 --json status,conclusion,name"
tags: [ci, testing]
scope: project
---
Check CI status before opening PRs. Green CI is required for merge.
Use `gh run view <id>` for detailed logs of a specific run.
```

```yaml
# .lexibrary/references/api-metrics.md
---
title: API Latency Dashboard
type: observability
url: https://grafana.internal/d/api-latency
query_command: ""
tags: [observability, api]
scope: src/api/
---
This dashboard tracks p50/p95/p99 latency for all API endpoints.
If you're modifying request handling code, check this dashboard after deployment.
```

### Complexity and Value

- **Complexity:** Medium. New artifact type following existing patterns (model, parser, serializer, CLI, search integration, linkgraph integration). Each piece is small but there are several.
- **Value:** Medium. Bridges the gap between Lexibrary's static world and the dynamic external systems agents need. The `query_command` field is the key innovation — it gives agents an executable path to dynamic data.
- **Estimated scope:** ~400 lines across new files + integration points.

---

## 9. Maintenance Playbook

### What It Solves

OpenAI runs periodic "garbage collection" agents that scan for documentation drift, naming divergence, and constraint violations, then autonomously open cleanup PRs. Lexibrary has `lexictl sweep --watch` for re-indexing and `lexictl validate --fix` for auto-fixing some issues, but these are reactive tools, not a structured autonomous workflow. A maintenance playbook defines exactly what a periodic maintenance agent should do, in what order, and how to handle each category of issue.

### How to Implement

**Approach A: Structured prompt file (simplest)**

Create a maintenance playbook as a Markdown file that agents can follow:

New file: `.lexibrary/playbooks/maintenance.md` (generated by `lexictl setup`)

```markdown
# Maintenance Playbook

Run this playbook periodically to manage entropy in the codebase.

## Step 1: Assess Library Health
```bash
lexi validate --format json
```
Parse the JSON output and categorize issues by severity.

## Step 2: Fix Auto-Fixable Issues
For each issue where the suggestion contains a specific `lexi` command, run that command.

## Step 3: Update Stale Design Files
For each `hash_freshness` warning:
```bash
lexi design update <source_file>
```

## Step 4: Clean Expired IWH Signals
```bash
lexi iwh list
```
For signals older than 72 hours with scope "incomplete", consume them.

## Step 5: Review Convention Compliance
For each `convention_gap` issue, assess whether:
- The convention scope should be narrowed
- The non-conforming files should be updated
- The convention should be deprecated

## Step 6: Archive Stale Stack Posts
For each `stack_staleness` issue:
```bash
lexi stack outdated <post_id> --reason "No activity for >90 days"
```

## Step 7: Document Findings
Create a Stack post summarizing maintenance actions taken:
```bash
lexi stack post --title "Maintenance run <date>" --tag maintenance --problem "Periodic entropy check" --finding "Fixed N issues, archived M posts" --fix
```
```

**Approach B: CLI command (more powerful)**

Add `lexictl maintain` command that executes the playbook programmatically:

File: `src/lexibrary/cli/lexictl_app.py`

```python
@lexictl_app.command("maintain")
def lexictl_maintain(
    *,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without doing it."),
    auto_fix: bool = typer.Option(False, "--fix", help="Auto-fix fixable issues."),
) -> None:
    """Run the maintenance playbook: validate, fix, clean, report."""
```

This would:
1. Run `validate_library()` and collect issues
2. If `--fix`, run auto-fix logic for fixable issues
3. Clean expired IWH signals
4. Report summary

**Approach C: Claude Code cron integration**

Use Claude Code's `/loop` skill or cron capabilities to schedule the playbook:

```
/loop 24h lexictl maintain --fix
```

### Recommended Approach

Start with **Approach A** (playbook file) — it's zero code and immediately useful. Then evolve to **Approach B** (`lexictl maintain`) which codifies the playbook as executable logic.

### Complexity and Value

- **Complexity:** Low for playbook file; Medium for CLI command.
- **Value:** Medium. Formalizes entropy management into a repeatable process. Most useful for teams running Lexibrary on larger codebases where entropy compounds.
- **Estimated scope:** Playbook file: 1 file, ~100 lines of Markdown. CLI command: ~150 lines of Python.

---

## Implementation Priority Matrix

| # | Opportunity | Complexity | Value | Dependencies | Recommended Order |
|---|---|---|---|---|---|
| 1 | Actionable Validator Remediation | Low | High | None | 1st |
| 2 | Convention-from-Failure Workflow | Low | High | None | 2nd |
| 3 | Convention Enforcement Levels | Medium | High | None (but enables #4) | 3rd |
| 4 | Dependency Direction Policy | Medium | Very High | #3 (optional, works without) | 4th |
| 5 | Bundled Context Command | Medium | Medium-High | Lookup extraction (may exist) | 5th |
| 9 | Maintenance Playbook | Low | Medium | #1 (suggestions make playbook more useful) | 6th |
| 6 | Role-Specific Agent Templates | Low | Medium | None | 7th |
| 8 | Project-Level References | Medium | Medium | None | 8th |
| 7 | MCP Server | Medium-High | High | Lookup extraction, search extraction | 9th (last — most prerequisites) |

---

## Codebase Map for Implementing Agents

Key files referenced across opportunities:

| File | Purpose | Touched By |
|---|---|---|
| `src/lexibrary/validator/report.py` | `ValidationIssue` model with `suggestion` field | #1 |
| `src/lexibrary/validator/checks.py` | All ~40 check functions | #1, #4 |
| `src/lexibrary/validator/__init__.py` | `AVAILABLE_CHECKS` registry, `validate_library()` orchestrator | #1, #3, #4 |
| `src/lexibrary/artifacts/convention.py` | `ConventionFileFrontmatter` model | #2, #3 |
| `src/lexibrary/cli/conventions.py` | `convention_new`, `convention_approve`, `convention_deprecate` commands | #2, #3 |
| `src/lexibrary/conventions/parser.py` | `parse_convention_file()`, `extract_rule()` | #3 |
| `src/lexibrary/conventions/serializer.py` | `serialize_convention_file()` | #2, #3 |
| `src/lexibrary/config/schema.py` | All config models (`LexibraryConfig`, `ConventionConfig`, etc.) | #3, #4 |
| `src/lexibrary/cli/lexi_app.py` | All `lexi` CLI commands | #5, #7 |
| `src/lexibrary/search.py` | `unified_search()`, `SearchResults`, `VALID_ARTIFACT_TYPES` | #7, #8 |
| `src/lexibrary/linkgraph/query.py` | `LinkGraph` class, all query methods | #4, #5, #7, #8 |
| `src/lexibrary/cli/lexictl_app.py` | All `lexictl` commands | #6, #9 |
| `src/lexibrary/artifacts/design_file_parser.py` | `parse_design_file()`, design frontmatter | #4, #5 |
| `src/lexibrary/conventions/index.py` | `ConventionIndex` for convention loading | #3, #5 |
| `tests/test_validator/` | Validator test suite (multiple files) | #1, #3, #4 |
| `tests/test_conventions/` | Convention test suite | #2, #3 |
| `tests/test_cli/` | CLI test suite | #2, #5, #6 |

### Key Patterns to Follow

1. **All modules start with `from __future__ import annotations`**
2. **Output through `_output.py` helpers** (`info`, `warn`, `error`, `hint`, `markdown_table`) — no bare `print()`
3. **Config is Pydantic 2 models** validated from YAML via PyYAML
4. **CLI is Typer** with `Annotated` type hints for options
5. **Tests use pytest + `tmp_path`** for filesystem tests
6. **Graceful degradation** — linkgraph operations return `None` when unavailable; callers branch on `None` for fallback
7. **Two-CLI security model** — `lexi` is read-only/agent-safe; `lexictl` is mutable/human-only
