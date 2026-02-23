# stack

**Summary:** Public API re-exports for the Stack Q&A knowledge base module.

## Re-exports

`StackAnswer`, `StackIndex`, `StackPost`, `StackPostFrontmatter`, `StackPostRefs`, `accept_answer`, `add_answer`, `mark_duplicate`, `mark_outdated`, `parse_stack_post`, `record_vote`, `render_post_template`, `serialize_stack_post`

## Dependents

- `lexibrary.cli` -- `stack_*` commands import individual submodules directly (lazy imports)
- `lexibrary.search` -- imports `StackIndex` from `stack.index`
- `lexibrary.wiki.resolver` -- resolves `ST-NNN` wikilinks against stack directory
