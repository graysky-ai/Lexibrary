# Harness Engineering Opportunities — Implementation Status

Date: 2026-03-19  
Branch: `feature-playbooks`

---

## Summary

**Overall Status: 3 implemented, 4 partially implemented, 2 not started**

Key finding: Playbook system (artifact 9) is **substantially complete** with all core modules, CLI commands, and validator integration done. Most other opportunities represent **enhancements to existing patterns** rather than new systems. Validator remediation is partially actionable. Dependency policy, context bundling, and role-specific templates remain unstarted.

---

## 1. Actionable Validator Remediation

**Status:** PARTIALLY IMPLEMENTED

**Evidence:**
- File: `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/validator/checks.py`
- 124 suggestions exist across checks
- Sample suggestions found:
  - "Remove the design file or restore the source file."
  - "Fix YAML syntax in frontmatter block."
  - "Add a 'title' field to the frontmatter."
  - "Update or remove the file reference."

**Current gaps:**
- Most suggestions are generic guidance text, not agent-actionable commands
- No `lexi` commands in suggestions (e.g., `Run 'lexi concept new ...'`)
- Examples using deprecated `lexictl` commands (e.g., "Run `lexictl update` to rebuild the linkgraph")
- Suggestions lack specific next steps to resolve issues programmatically

**To complete:** Upgrade suggestions to include explicit CLI commands (e.g., "Run `lexi concept new --scope project --body 'description'`").

---

## 2. Convention-from-Failure Workflow

**Status:** NOT STARTED

**Evidence:**
- File: `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/cli/conventions.py`
- Current `convention_new()` command (lines 22-100) supports:
  - `--scope`, `--body`, `--tag`, `--title`, `--source`, `--alias`
- **No `--from-failure` flag exists**

**To implement:** Add a `--from-failure` flag that:
- Accepts a validation check name or Stack post reference
- Pre-populates convention body with failure context
- Streamlines workflow from failure detection → convention creation

---

## 3. Convention Enforcement Levels

**Status:** NOT STARTED

**Evidence:**
- File: `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/artifacts/convention.py`
- `ConventionFileFrontmatter` (lines 14-24) has fields:
  - `title`, `scope`, `tags`, `status`, `source`, `priority`, `aliases`, `deprecated_at`
- **No `enforcement` field exists**

**To implement:** Add `enforcement` field to support enforcement levels:
  - Example: `enforcement: Literal["required", "recommended", "informational"]`
  - Enables validator to weight convention violations differently
  - Allows agents to adapt behavior based on policy strength

---

## 4. Dependency Direction Policy

**Status:** NOT STARTED

**Evidence:**
- File: `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/config/schema.py`
- Config has: `CrawlConfig`, `TokenizerConfig`, `LLMConfig`, `TokenBudgetConfig`, `MappingConfig`, `IgnoreConfig`, `SweepConfig`, `ASTConfig`
- **No `DependencyPolicyConfig` class exists**
- Validator has no `check_dependency_direction()` function

**To implement:** 
- Add `DependencyPolicyConfig` to schema with fields like `allowed_forward_edges`, `forbidden_patterns`, `cycle_handling`
- Implement `check_dependency_direction()` validator check
- Integrate with link graph traversal

---

## 5. Bundled Context Command

**Status:** PARTIALLY IMPLEMENTED

**Evidence:**
- File: `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/cli/lexi_app.py` (lines 1142-1145)
- Hidden command exists: `@lexi_app.command("context-dump", hidden=True)` 
- **Status:** Deprecated alias for `orient()`; not a proper context bundling system

**Current state:**
- `context-dump` is legacy, not a design feature
- No `/src/lexibrary/context/` module
- No `/src/lexibrary/mcp/` module

**To implement:**
- Create `/src/lexibrary/context/` module with context bundling logic
- Create public `lexi context` command (not hidden) with options like:
  - `--scope <path>` — limit context to directory
  - `--depth <n>` — control dependency traversal depth
  - `--format json|markdown` — output format
  - `--output <file>` — write to file
- Optional: MCP server wrapper for Claude integration

---

## 6. Role-Specific Agent Rule Templates

**Status:** NOT STARTED

**Evidence:**
- File: Check for `/.lexibrary/roles/` directory
- Result: **Does not exist**
- No role template files in `.lexibrary/` structure

**To implement:**
- Create `.lexibrary/roles/` directory
- Add role definition files (e.g., `architect.md`, `maintainer.md`, `contributor.md`)
- Each role file specifies:
  - Agent capabilities and restrictions
  - Preferred artifact types and workflows
  - Convention interpretation rules
  - Escalation triggers
- Auto-generate per-role `.cursor/rules/` snippets

---

## 7. MCP Server

**Status:** NOT STARTED

**Evidence:**
- Checked for `/src/lexibrary/mcp_server.py` — **does not exist**
- Checked for `/src/lexibrary/mcp/` directory — **does not exist**
- No MCP protocol imports in codebase

**To implement:**
- Create `src/lexibrary/mcp/` module with MCP server implementation
- Expose as `uv run lexi mcp-server` or standalone service
- Endpoints for:
  - `lookup` — lexi lookup functionality
  - `search` — lexi search
  - `orient` — project orientation
  - Artifact CRUD operations

---

## 8. Project-Level Reference Artifacts

**Status:** NOT STARTED

**Evidence:**
- Checked for `/src/lexibrary/artifacts/reference.py` — **does not exist**
- Checked for `/.lexibrary/references/` directory — **does not exist**
- Artifact modules only include: aindex, concept, convention, design_file, playbook

**To implement:**
- Create `src/lexibrary/artifacts/reference.py` with `ReferenceFile` model
- Support reference types: API docs, external specs, architectural glossary
- Create `.lexibrary/references/` directory for instances
- Integrate with wikilink resolver and search
- Example reference: "REST API Patterns", "PostgreSQL Constraints", "CloudFormation Limits"

---

## 9. Maintenance Playbook

**Status:** SUBSTANTIALLY COMPLETE (playbook system) + PARTIALLY IMPLEMENTED (maintenance)

**Evidence:**

### Playbook System (NEW — Complete)
- **File:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/artifacts/playbook.py` — ✅ Exists
- **File:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/playbooks/` directory — ✅ Exists with:
  - `__init__.py` (re-exports)
  - `parser.py` (parse_playbook_file)
  - `serializer.py` (serialize_playbook_file)
  - `index.py` (PlaybookIndex with FTS support)
  - `template.py` (render_playbook_template)
- **File:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/cli/playbooks.py` — ✅ Exists with:
  - `playbook_new()` command
  - Integration with lexi_app
- **File:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/lifecycle/playbook_comments.py` — ✅ Exists
- **Integration:** Validator checks, search, CLI — ✅ Integrated
- **Test coverage:** `/tests/test_playbook_*.py` files — ✅ Present (6 files)

### Maintenance-Specific Playbooks (Partial)
- Playbook template supports:
  - `trigger_files` (glob patterns for discovery)
  - `tags`, `status`, `source`, `estimated_minutes`
  - `last_verified`, `deprecated_at`, `superseded_by`
- **No:** 
  - `maintained_by` field (assignee tracking)
  - `lexictl maintain` command
  - Dedicated maintenance playbook in `.lexibrary/playbooks/`

**.lexibrary/playbooks/ inventory:**
- `adding-a-new-artifact-type.md`
- `adding-a-new-cli-command.md`
- `adding-a-new-design-file.md`
- `creating-a-concept-file.md`
- `dogfooding-disambiguation.md`
- `running-validation-checks.md`

**To complete:** 
- Create `.lexibrary/playbooks/maintenance.md` with maintenance workflows
- Optional: Add `maintained_by` field to playbook frontmatter
- Optional: `lexictl maintain` command (currently prohibited — requires admin approval)

---

## Recommendations

### High Priority (Foundation)
1. **#1 Validator Remediation** — Upgrade suggestions to include CLI commands (blocks effective error handling)
2. **#4 Dependency Direction** — Critical for scale (prevents circular dependency bugs)
3. **#5 Context Command** — Public bundled context improves agent UX

### Medium Priority (Consistency)
4. **#2 Convention-from-Failure** — Streamlines failure→policy workflow
5. **#3 Convention Enforcement** — Enables enforcement-aware validation
6. **#8 Reference Artifacts** — Natural extension of concept/convention patterns

### Lower Priority (Polish)
7. **#7 MCP Server** — Enables broader tool integration (not urgent for CLI use)
8. **#6 Role Templates** — Useful for multi-agent coordination (deferred scaling)

### Already Complete
9. **#9 Maintenance Playbook** — Playbook system is production-ready; maintenance playbooks exist

---

## Git Status

Current branch: `feature-playbooks`

New/modified files related to playbooks:
- `?? .lexibrary/playbooks/` (index.db-shm, index.db-wal)
- `?? src/lexibrary/artifacts/playbook.py` — NEW
- `?? src/lexibrary/cli/playbooks.py` — NEW
- `?? src/lexibrary/lifecycle/playbook_comments.py` — NEW
- `?? src/lexibrary/playbooks/` — NEW (4 modules)
- `?? tests/test_playbook_*.py` — NEW (6 test files)
- Modified: cli, search, validator, config integration

