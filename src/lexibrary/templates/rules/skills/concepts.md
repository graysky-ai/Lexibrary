# /lexi-concepts — Concept Search

Use this **before making architectural decisions** to check whether the
project already has conventions, patterns, or design rationale that
constrain your choices. Also use it when you encounter a wikilink
(e.g., ``[[Some Concept]]``) and need to understand what it refers to.

## When to use

- Before introducing a new pattern or abstraction -- check if one already exists
- When you encounter a wikilink in a design file or concept page
- When reviewing code that uses domain-specific terminology

## Usage

- `lexi concepts <topic>` -- search for concepts matching a topic
- `lexi concepts --tag <tag>` -- filter concepts by tag (e.g., `--tag convention`, `--tag pattern`)
- `lexi concepts --all` -- list all concepts in the project wiki
