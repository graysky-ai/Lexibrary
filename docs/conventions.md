# Conventions

Conventions are prescriptive project rules stored as markdown files in `.lexibrary/conventions/`. They encode coding patterns, naming rules, and scope-aware guidelines that Lexibrary surfaces automatically during file lookups.

Unlike [concepts](concepts.md), which capture cross-cutting design vocabulary and architectural decisions, conventions are **directive**: they tell agents and developers what to do (or not do) in specific parts of the codebase.

## What Conventions Are

A convention consists of:

- A **rule** -- the prescriptive first paragraph (e.g., "Every Python module must include `from __future__ import annotations`")
- A **scope** -- either `project` (applies everywhere) or a directory path like `src/auth` (applies only within that subtree)
- A **status** -- `draft`, `active`, or `deprecated`
- A **source** -- `user` (manually created), `agent` (proposed by a coding agent), or `config` (declared in project configuration)

Conventions are stored in `.lexibrary/conventions/` as markdown files with YAML frontmatter. They are surfaced automatically by `lexi lookup` when a file falls within the convention's scope.

## Scope Model

Conventions use a directory-scoped inheritance model. When `lexi lookup <file>` runs, it collects all conventions where:

- The scope is `project` (applies to all files), **or**
- The file's path starts with the convention's scope directory

Conventions are sorted by scope depth (project-wide first, then root-to-leaf), then by priority (descending), then by title. This means more specific conventions appear after broader ones, and higher-priority conventions within the same scope appear first.

A convention scoped to `src/auth` applies to `src/auth/models.py` and `src/auth/handlers/login.py`, but not to `src/api/routes.py`.

Multi-directory scoping is supported: pass comma-separated paths to `--scope` (e.g., `--scope "src/lexibrary/cli/, src/lexibrary/services/"`) to apply a convention to multiple directories.

### Display limits

By default, `lexi lookup` shows up to 5 conventions per file. This limit is configurable via `conventions.lookup_display_limit` in `.lexibrary/config.yaml`. See [Configuration](configuration.md) for details.

## Creating Conventions

### Via CLI

Use `lexi convention new` to create a convention:

```bash
lexi convention new \
  --scope src/auth \
  --body "All endpoints require an auth decorator before the route handler" \
  --tag security --tag patterns
```

Options:

| Option | Required | Description |
|--------|----------|-------------|
| `--scope TEXT` | Yes | `project` for repo-wide, or comma-separated directory paths |
| `--body TEXT` | Yes | Convention body text; the first paragraph becomes the rule |
| `--tag TEXT` | No | Tag for categorization (repeatable) |
| `--title TEXT` | No | Convention title; derived from first 60 chars of body if omitted |
| `--source TEXT` | No | `user` (default) or `agent` |
| `--alias TEXT` | No | Short alias for the convention (repeatable) |

The convention is saved to `.lexibrary/conventions/` with an auto-generated filename based on an artifact ID and the title slug (e.g., `CV-001-future-annotations-import.md`).

**Source behavior:**

- `--source user` (default): created with `status: active` and `priority: 0`
- `--source agent`: created with `status: draft` and `priority: -1`; requires approval before it takes effect

### Via Configuration

Conventions can be declared in `.lexibrary/config.yaml` under the `convention_declarations` key:

```yaml
convention_declarations:
  - body: "Use `from __future__ import annotations` in every module"
    scope: project
    tags: [python, imports]
  - body: "pathspec pattern name must be 'gitignore'"
    scope: src/lexibrary/ignore
    tags: [pathspec]
```

Config-declared conventions are materialized into `.lexibrary/conventions/` files with `source: config` and `status: active` by the build pipeline. See [Configuration](configuration.md) for the full `convention_declarations` schema.

## File Anatomy

A convention file is a markdown document with YAML frontmatter:

```yaml
---
title: Future annotations import
id: CV-001
scope: project
tags: [python, imports]
status: active
source: user
priority: 0
---

Every Python module must include `from __future__ import annotations` as the
first import. This enables PEP 604 union syntax (`X | Y`) and forward
references without string quoting.

**Rationale**: Consistency across the codebase enables modern type annotation
patterns and avoids runtime evaluation of type hints.
```

### Frontmatter Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | required | Convention name (max 60 chars in slug) |
| `id` | string | required | Artifact ID (e.g., `CV-001`); auto-assigned by `lexi convention new` |
| `scope` | string | `"project"` | `"project"` for global, or directory path(s) like `"src/auth"` |
| `tags` | list | `[]` | Categorization tags for search and filtering |
| `status` | string | `"draft"` | One of: `"draft"`, `"active"`, `"deprecated"` |
| `source` | string | `"user"` | One of: `"user"`, `"agent"`, `"config"` |
| `priority` | integer | `0` | Sort order within same scope; higher values appear first |
| `aliases` | list | `[]` | Short aliases for the convention |

### Body Structure

- **First paragraph** (up to the first blank line) is extracted as the convention's **rule** -- the prescriptive statement shown in lookup output
- **Remaining text** is the full body; may include rationale, examples, exceptions, and wikilinks to concepts (`[[ConceptName]]`)

## Approving and Deprecating

### Approving conventions

Agent-created conventions start as `draft` and must be approved before they appear in lookup output for non-draft contexts:

```bash
lexi convention approve CV-001-future-annotations-import
```

The argument is the convention's file slug (filename without `.md`). This promotes the convention from `draft` to `active`.

### Deprecating conventions

Mark a convention as obsolete:

```bash
lexi convention deprecate CV-001-future-annotations-import
```

This sets `status: deprecated` and records a `deprecated_at` timestamp. Deprecated conventions are excluded from `lexi lookup` output by default.

### Adding comments

Append review notes or context to a convention's sidecar comment file:

```bash
lexi convention comment CV-001-future-annotations-import \
  --body "Verified this still applies after Python 3.12 upgrade"
```

## Listing and Searching

Use `lexi conventions` (note the plural) to browse conventions:

```bash
lexi conventions                          # All active conventions
lexi conventions src/auth                 # Conventions applying to src/auth
lexi conventions --status draft           # Draft conventions only
lexi conventions --tag python             # Filter by tag
lexi conventions --all                    # Include deprecated
```

Use `lexi search --type convention <query>` for full-text search across all conventions.

## Conventions vs Concepts

| Aspect | Conventions | Concepts |
|--------|-------------|----------|
| **Purpose** | Prescriptive rules ("do this") | Design vocabulary ("what this means") |
| **Scope** | Directory-scoped with inheritance | Global |
| **Surfaced via** | `lexi lookup <file>` (automatic) | Wikilinks in design files, `lexi search` |
| **Provenance** | Tracked (`source` field: user/agent/config) | Not tracked |
| **Aliasing** | Supported via `aliases` field | Supported via `aliases` field |
| **Lifecycle** | draft/active/deprecated with approval workflow | draft/active/deprecated |

Conventions can reference concepts using wikilinks (`[[ConceptName]]`) in their body text. This creates cross-references that are tracked in the link graph.
