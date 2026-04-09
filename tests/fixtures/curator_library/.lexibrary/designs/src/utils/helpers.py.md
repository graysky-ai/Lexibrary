---
description: Provides text manipulation utilities (slugify, truncate).
id: DS-004
updated_by: archivist
status: active
---

# src/utils/helpers.py

## Interface Contract

```python
def slugify(text: str) -> str: ...
def truncate(text: str, max_length: int = 100) -> str: ...
```

## Dependencies

(none)

## Dependents

*(see `lexi lookup` for live reverse references)*

(none)

## Wikilinks

- [[NonexistentConcept]]
- [[Authentcation]]
- [[Superseded Concept]]

## Tags

- utils
- text

<!-- lexibrary:meta
source: src/utils/helpers.py
source_hash: 3d9c98506f7848f3fa61d9d39795ab439bfb60584b02d988ce1dab96e605c92a
interface_hash: eeee111122223333444455556666777788889999aaaabbbbccccddddeeeeffff
design_hash: 3333333333333333333333333333333333333333333333333333333333333333
generated: 2026-04-01T12:00:00.000000
generator: lexibrary-v2
-->
