# stack/mutations

**Summary:** Mutation functions for Stack posts — add answers, vote, accept, and mark status changes; each function reads the post from disk, mutates, writes back, and re-parses for consistency.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `add_answer` | `(post_path: Path, author: str, body: str) -> StackPost` | Append a new answer with auto-incremented number and today's date |
| `record_vote` | `(post_path: Path, target: str, direction: str, author: str, comment?: str) -> StackPost` | Record up/downvote on `"post"` or `"A{n}"`; downvotes require a comment |
| `accept_answer` | `(post_path: Path, answer_num: int) -> StackPost` | Mark answer as accepted, set post status to `"resolved"` |
| `mark_duplicate` | `(post_path: Path, duplicate_of: str) -> StackPost` | Set status to `"duplicate"` and record the original post ID |
| `mark_outdated` | `(post_path: Path) -> StackPost` | Set status to `"outdated"` |

## Dependencies

- `lexibrarian.stack.models` -- `StackAnswer`, `StackPost`
- `lexibrarian.stack.parser` -- `parse_stack_post`
- `lexibrarian.stack.serializer` -- `serialize_stack_post`

## Dependents

- `lexibrarian.cli` -- `stack_answer`, `stack_vote`, `stack_accept` commands

## Key Concepts

- All mutations follow a load-mutate-save-reload pattern: `_load_post()` -> modify -> `_save_post()` -> `_load_post()` to ensure `raw_body` stays consistent
- `record_vote` target is either `"post"` (post-level vote) or `"A{n}"` format (answer-level vote); downvotes append a tagged comment `[downvote] author: comment` to the answer
- Answer numbers are auto-assigned as `max(existing) + 1`

## Dragons

- `record_vote` for post-level votes with comments: the comment is not persisted anywhere (no answer to attach to) — only the vote count on frontmatter is updated
