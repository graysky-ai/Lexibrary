# archivist/change_checker

**Summary:** Classifies how a source file has changed relative to its existing design file by comparing content and interface hashes from the metadata footer.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `ChangeLevel` | `Enum` | Classification enum: `UNCHANGED`, `AGENT_UPDATED`, `CONTENT_ONLY`, `CONTENT_CHANGED`, `INTERFACE_CHANGED`, `NEW_FILE` |
| `check_change` | `(source_path, project_root, content_hash, interface_hash) -> ChangeLevel` | Compare current source hashes against the design file footer to determine update action |

## Dependencies

- `lexibrarian.artifacts.design_file_parser` -- `_FOOTER_RE`, `parse_design_file_metadata`
- `hashlib` (stdlib)

## Dependents

- `lexibrarian.archivist.pipeline` -- uses `check_change` and `ChangeLevel` for per-file update decisions
- `lexibrarian.archivist.__init__` -- re-exports `ChangeLevel`, `check_change`

## Key Concepts

- Design file path convention: `.lexibrary/<relative-source-path>.md`
- Design content hash covers frontmatter + body, excludes HTML comment footer, to avoid false agent-edit detection on footer-only refreshes
- `AGENT_UPDATED` means design file exists but was hand-edited by an agent (design hash mismatch)
- `CONTENT_ONLY` means source body changed but public interface is unchanged (code files only)
