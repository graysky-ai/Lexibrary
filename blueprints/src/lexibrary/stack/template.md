# stack/template

**Summary:** Renders a new Stack post template with YAML frontmatter and placeholder body scaffold.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `render_post_template` | `(*, post_id, title, tags, author, bead?, refs_files?, refs_concepts?) -> str` | Render a new Stack post markdown template ready to be written to disk |

## Dependencies

- `yaml` -- `yaml.dump` for frontmatter serialization

## Dependents

- `lexibrarian.cli` -- `stack_post` command

## Key Concepts

- Frontmatter includes: `id`, `title`, `tags`, `status: "open"`, `created: date.today()`, `author`, `votes: 0`
- Optional fields: `bead` (only included if provided), `refs` (only included if `refs_concepts` or `refs_files` provided)
- Body contains `## Problem` and `### Evidence` sections with HTML comment placeholders for the user to fill in
