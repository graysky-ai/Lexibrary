# stack/serializer

**Summary:** Serializes a `StackPost` model to markdown format with YAML frontmatter, problem/evidence sections, and answer blocks.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `serialize_stack_post` | `(post: StackPost) -> str` | Serialize to markdown string with YAML frontmatter |

## Output Format

```
---
id: ST-001
title: ...
tags: [...]
status: open
created: 2026-01-15
author: user
...
---

## Problem

<problem text>

### Evidence

- <evidence item>

## Answers

### A1

**Date:** 2026-01-15 | **Author:** user | **Votes:** 0

<answer body>

#### Comments

<comment lines>
```

## Dependencies

- `lexibrarian.stack.models` -- `StackPost`

## Dependents

- `lexibrarian.stack.mutations` -- `_save_post()` calls `serialize_stack_post`

## Key Concepts

- YAML frontmatter includes all `StackPostFrontmatter` fields, including `refs` sub-object and nullable fields (`bead`, `duplicate_of`)
- Accepted answers get `| **Accepted:** true` appended to the metadata line
- Ensures trailing newline
