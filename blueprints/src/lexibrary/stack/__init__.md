# stack

**Summary:** Public API re-exports for the Stack Q&A knowledge base module.

## Re-exports

`StackAnswer`, `StackIndex`, `StackPost`, `StackPostFrontmatter`, `StackPostRefs`, `accept_answer`, `add_answer`, `mark_duplicate`, `mark_outdated`, `parse_stack_post`, `record_vote`, `render_post_template`, `serialize_stack_post`

## Dependents

- `lexibrarian.cli` -- `stack_*` commands import individual submodules directly (lazy imports)
- `lexibrarian.search` -- imports `StackIndex` from `stack.index`
- `lexibrarian.wiki.resolver` -- resolves `ST-NNN` wikilinks against stack directory
