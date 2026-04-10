# Playbooks

Playbooks are step-by-step procedural guides stored in `.lexibrary/playbooks/`. They document repeatable workflows -- such as version bumps, release procedures, or migration steps -- so that agents and developers can follow a consistent process each time.

Playbooks are discovered automatically by `lexi lookup` when a file matches a playbook's trigger-file glob patterns, and they can be searched with `lexi search --type playbook`.

## What Playbooks Are

A playbook consists of:

- A **title** -- a semantic name describing the procedure (e.g., "Version Bump")
- **Trigger files** -- glob patterns that associate the playbook with specific files or directories
- **Steps** -- numbered checklist items that walk through the procedure
- A **status** -- `draft`, `active`, or `deprecated`
- Optional metadata: tags, estimated time, verification date, and deprecation info

Playbooks are stored in `.lexibrary/playbooks/` as markdown files with YAML frontmatter and an ID-prefixed filename (e.g., `PB-001-version-bump.md`).

## Creating Playbooks

### Via CLI

Use `lexi playbook new` to scaffold a new playbook:

```bash
lexi playbook new "Version Bump" \
  --trigger-file "pyproject.toml" \
  --trigger-file "src/lexibrary/__init__.py" \
  --tag release --tag versioning \
  --estimated-minutes 15
```

Arguments and options:

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `TITLE` | Yes | Semantic name for the playbook |
| `--trigger-file TEXT` | No | Glob pattern for file-context discovery (repeatable) |
| `--tag TEXT` | No | Categorization tag (repeatable) |
| `--estimated-minutes INT` | No | Estimated time in minutes to complete the procedure |

This creates a scaffolded markdown file in `.lexibrary/playbooks/` with placeholder sections for Overview, Steps, and Notes. The playbook starts in `draft` status.

**Title collision detection:** If a playbook with the same title or slug already exists, the command fails with an error. Cross-type collisions (e.g., a concept with the same title) produce a warning but allow creation.

### Manual creation

Playbook files can also be created manually in `.lexibrary/playbooks/`. The filename must follow the pattern `PB-<NNN>-<slug>.md` (e.g., `PB-002-deploy-staging.md`).

## File Anatomy

A playbook file is a markdown document with YAML frontmatter:

```yaml
---
# title: use a semantic name that describes the procedure
title: Version Bump
trigger_files: [pyproject.toml, src/lexibrary/__init__.py]
tags: [release, versioning]
status: active
source: user
id: PB-001
estimated_minutes: 15
---

## Overview

This playbook walks through the process of bumping the project version,
updating the changelog, and tagging the release.

## Steps

1. [ ] Update version in `pyproject.toml`
2. [ ] Update version in `src/lexibrary/__init__.py`
3. [ ] Update `CHANGELOG.md` with new version section
4. [ ] Run tests: `uv run pytest`
5. [ ] Commit changes with message "Bump version to X.Y.Z"
6. [ ] Tag the commit: `git tag vX.Y.Z`

## Notes

Related: [[concept: Semantic Versioning]]
```

### Frontmatter Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | required | Semantic name; used for slug generation and search |
| `id` | string | required | Artifact ID (e.g., `PB-001`); auto-assigned by `lexi playbook new` |
| `trigger_files` | list | `[]` | Glob patterns for file-context discovery |
| `tags` | list | `[]` | Categorization tags |
| `status` | string | `"draft"` | One of: `"draft"`, `"active"`, `"deprecated"` |
| `source` | string | `"user"` | One of: `"user"`, `"agent"` |
| `estimated_minutes` | integer | `null` | Estimated time to complete in minutes |
| `last_verified` | date | `null` | Date the playbook was last verified as accurate |
| `deprecated_at` | datetime | `null` | Timestamp when the playbook was deprecated |
| `superseded_by` | string | `null` | Slug of the replacement playbook, if deprecated |
| `aliases` | list | `[]` | Alternative names for search |

### Body Sections

The scaffolded template includes three sections:

- **Overview** -- What the playbook does and when to use it
- **Steps** -- Numbered checklist items (`1. [ ] Step description`) for the procedure
- **Notes** -- Related playbooks, concepts, or other context

The **overview** (first non-frontmatter paragraph or Overview section content) is used in search result summaries.

## Approve / Verify / Deprecate Lifecycle

### Approving

New playbooks start as `draft`. Promote a playbook to `active` when it has been reviewed and is ready for use:

```bash
lexi playbook approve PB-001-version-bump
```

The argument is the playbook's file slug (filename stem without `.md`).

### Verifying

Mark a playbook as recently verified (confirming its steps are still accurate):

```bash
lexi playbook verify PB-001-version-bump
```

This updates the `last_verified` frontmatter field to today's date. Regular verification prevents playbooks from becoming stale.

### Deprecating

Mark a playbook as obsolete:

```bash
lexi playbook deprecate PB-001-version-bump \
  --superseded-by PB-003-new-version-bump \
  --reason "Replaced with automated release workflow"
```

Options:

| Option | Description |
|--------|-------------|
| `--superseded-by TEXT` | Slug of the playbook that replaces this one |
| `--reason TEXT` | Reason for deprecation; appended as a blockquote to the body |

This sets `status: deprecated`, records a `deprecated_at` timestamp, and optionally links to the replacement playbook.

### Adding comments

Append review notes or context to a playbook's sidecar comment file:

```bash
lexi playbook comment PB-001-version-bump \
  --body "Step 3 needs updating after CHANGELOG format change"
```

Comments are stored in a separate sidecar file alongside the playbook, preserving the playbook's content while accumulating review history.

## Trigger-Glob Matching

Trigger-file patterns use pathspec gitignore-style glob syntax. When `lexi lookup <file>` runs, it checks each playbook's `trigger_files` patterns against the file being looked up.

Examples:

| Pattern | Matches |
|---------|---------|
| `pyproject.toml` | Only `pyproject.toml` at the project root |
| `src/lexibrary/cli/**` | Any file under `src/lexibrary/cli/` |
| `*.py` | Any Python file at the root level |
| `**/*.py` | Any Python file anywhere in the project |

**Specificity ranking:** When multiple playbooks match a file, they are ranked by glob specificity -- patterns with more literal path segments rank higher. Within the same specificity level, playbooks are ordered alphabetically by title. This means a playbook triggered by `src/lexibrary/cli/lexi_app.py` ranks above one triggered by `src/**`.

**Directory matching:** Playbooks can also match against directories. When looking up a directory, a synthetic file path is constructed to test against trigger patterns, so `src/lexibrary/cli/**` matches both files within and the directory itself.

### Display limits

By default, `lexi lookup` shows up to 5 playbooks per file. This is configurable via `playbooks.lookup_display_limit` in `.lexibrary/config.yaml`. See [Configuration](configuration.md) for details.

## Staleness Detection

Playbooks can become stale as the codebase evolves. Lexibrary tracks playbook freshness through two mechanisms:

- **Commit-based staleness:** A playbook is considered stale if more than `playbooks.staleness_commits` commits (default: 100) have occurred since it was last verified.
- **Time-based staleness:** A playbook is considered stale if more than `playbooks.staleness_days` days (default: 180) have passed since its `last_verified` date.

To reset staleness, verify the playbook after confirming its steps are still accurate:

```bash
lexi playbook verify PB-001-version-bump
```

Staleness thresholds are configurable in `.lexibrary/config.yaml`:

```yaml
playbooks:
  staleness_commits: 100
  staleness_days: 180
```

See [Configuration](configuration.md) for the full playbook configuration reference.
