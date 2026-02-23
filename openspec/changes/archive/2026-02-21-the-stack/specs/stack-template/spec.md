## ADDED Requirements

### Requirement: Render post template
The system SHALL provide a `render_post_template()` function in `src/lexibrary/stack/template.py` with parameters:
- `post_id` (str) — the assigned `ST-NNN` ID
- `title` (str) — post title
- `tags` (list[str]) — at least one tag
- `author` (str) — agent session ID or human identifier
- `bead` (str | None) — optional Bead ID, default `None`
- `refs_files` (list[str] | None) — optional file references, default `None`
- `refs_concepts` (list[str] | None) — optional concept references, default `None`

The function SHALL return a markdown string containing YAML frontmatter with default values (`status: open`, `votes: 0`, `created` set to today's date) and a body scaffold with `## Problem` and `### Evidence` sections containing placeholder text.

#### Scenario: Render template with minimal args
- **WHEN** `render_post_template(post_id="ST-001", title="Test bug", tags=["bug"], author="agent-123")` is called
- **THEN** the output SHALL contain YAML frontmatter with `id: ST-001`, `title: "Test bug"`, `tags: [bug]`, `status: open`, `votes: 0`, and a `## Problem` section with placeholder text

#### Scenario: Render template with file refs
- **WHEN** `render_post_template()` is called with `refs_files=["src/foo.py", "src/bar.py"]`
- **THEN** the YAML frontmatter SHALL contain `refs:` with `files: [src/foo.py, src/bar.py]`

#### Scenario: Render template with bead
- **WHEN** `render_post_template()` is called with `bead="BEAD-42"`
- **THEN** the YAML frontmatter SHALL contain `bead: BEAD-42`

#### Scenario: Created date is today
- **WHEN** `render_post_template()` is called
- **THEN** the `created` field in frontmatter SHALL be today's date in ISO format
