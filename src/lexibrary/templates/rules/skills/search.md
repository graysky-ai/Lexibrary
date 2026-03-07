# /lexi-search — Cross-Artifact Search

Use this to **map the territory before zooming in**. When you receive a
task that touches unfamiliar parts of the codebase, start with a broad
search to discover what exists before diving into specific files.

## When to use

- Starting work in an unfamiliar area of the codebase
- Investigating how a concept or pattern is used across the project
- Looking for prior art before implementing something new

## Usage

Run `lexi search <query>` to perform a unified search that combines:

- **Concept lookup** -- matching concepts from the wiki by title, alias, or tag
- **Stack search** -- matching Stack Q&A posts by title or content
- **Design file search** -- matching design files by source path or content

Review all results to build a complete picture before proceeding.
Follow up with `lexi lookup <file>` on specific files of interest.
