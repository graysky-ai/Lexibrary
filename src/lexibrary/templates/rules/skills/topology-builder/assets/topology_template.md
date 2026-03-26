# Project Topology

*Replace this paragraph with a one-sentence description of the project's purpose and primary output artifact.*

**{{PROJECT_NAME}}** is {{ONE_SENTENCE_PURPOSE}}.

## Directory Tree Legend

Directory descriptions in the tree below are synthesised keyword fragments drawn from the individual file descriptions within that directory. Fragments are separated by `;` — each fragment describes a **different file** in that directory, not multiple aspects of the same file. Use these fragments to decide which directory to explore next without opening every file.

## Entry Points

*List every executable surface: CLIs, HTTP servers, task runners, importable top-level modules. Add or remove rows as needed.*

| Command / Import | Role | Entry File |
|-----------------|------|-----------|
| `{{command_1}}` | {{role_1}} | `{{path/to/entry_1.py}}` |
| `{{command_2}}` | {{role_2}} | `{{path/to/entry_2.py}}` |

*Note any registration mechanism (e.g. `pyproject.toml` console scripts, `Dockerfile` CMD, `package.json` scripts).*

## Project Config

*Fill in the actual values for this project. Add rows for additional tooling.*

| Property | Value |
|----------|-------|
| Language / runtime | `{{Python X.Y}}` |
| Build system | `{{hatchling / setuptools / ...}}` |
| Package manager | `{{uv / pip / poetry / ...}}` |
| Type checker | `{{mypy / pyright / none}}` |
| Linter / formatter | `{{ruff / flake8 / eslint / ...}}` |
| Test runner | `{{pytest / jest / ...}}` |

## Directory Tree

*Paste the tree output from `lexi orient` (or equivalent) here. Directory annotations come from the billboard summaries in each `.aindex` file — see the legend above.*

```
{{PROJECT_NAME}}/ -- {{root billboard fragment}}
  {{dir_1}}/ -- {{billboard fragment 1a}}; {{billboard fragment 1b}}
    {{subdir_1a}}/ -- {{billboard fragment}}
  {{dir_2}}/ -- {{billboard fragment 2a}}; {{billboard fragment 2b}}
  {{dir_3}}/ -- {{billboard fragment 3a}}
    {{subdir_3a}}/ -- {{billboard fragment}}
    {{subdir_3b}}/ -- {{billboard fragment}}
```

## Key Architectural Insights

*Explain the non-obvious design decisions that a new agent is most likely to get wrong. Each subsection should answer "why does it work this way?" rather than "what does it do?"*

*Review guidance: When updating this section, review each existing insight individually against the current source files, CLAUDE.md, README, and `lexi concepts` output. Remove any insight that is outdated, redundant with those sources, or no longer accurate. Only add a new insight if it meets this bar: "an agent would plausibly make the wrong assumption without this." This section should be curated, not accumulated -- prune aggressively.*

### {{Insight Title 1}}

*Example: "Two-CLI Design" or "Dogfooding Loop" or "Event-Sourced State".*

{{Explanation of the design decision and its consequences for editing code in this project.}}

### {{Insight Title 2}}

{{Explanation.}}

## Core Modules

*Group modules by category (e.g. CLI, data models, services, utilities). Each table row should give an agent enough context to decide whether this is the right file to open.*

### {{Category 1 — e.g. "CLI Layer"}}

*{{Brief description of what all files in this category share.}}*

| Module | Purpose |
|--------|---------|
| `{{path/to/module_a.py}}` | {{One-sentence role.}} |
| `{{path/to/module_b.py}}` | {{One-sentence role.}} |

### {{Category 2 — e.g. "Domain Models / Schemas"}}

*{{Brief description.}}*

| Module | Purpose |
|--------|---------|
| `{{path/to/module_c.py}}` | {{One-sentence role.}} |
| `{{path/to/module_d.py}}` | {{One-sentence role.}} |

### {{Category 3 — e.g. "Services / Orchestration"}}

| Module | Purpose |
|--------|---------|
| `{{path/to/module_e.py}}` | {{One-sentence role.}} |

### {{Category 4 — e.g. "Utilities"}}

| Module | Purpose |
|--------|---------|
| `{{path/to/module_f.py}}` | {{One-sentence role.}} |

## Test Structure

*Mirror the source layout so an agent can find the test file for any module instantly.*

*Test directory mapping: Each `tests/test_<subdir>/` directory maps to a corresponding `src/<subdir>/` source directory. Use this mapping to locate existing tests and decide where new tests belong.*

| Test directory | Source directory |
|----------------|-----------------|
| `tests/test_{{subdir_1}}/` | `src/{{package}}/{{subdir_1}}/` |
| `tests/test_{{subdir_2}}/` | `src/{{package}}/{{subdir_2}}/` |

| Test file | Covers |
|-----------|--------|
| `tests/{{test_module_a.py}}` | `{{path/to/module_a.py}}` |
| `tests/{{test_module_b.py}}` | `{{path/to/module_b.py}}` |
| `tests/{{subdir/test_module_c.py}}` | `{{path/to/module_c.py}}` |

*Test fixtures live in `{{tests/fixtures/}}`. Shared helpers are in `{{tests/conftest.py}}`.*

*Convention: When adding tests for a module that already has a test file, add new test cases to the existing file rather than creating a new one. Create a new test file only when covering a module that has no existing test file.*