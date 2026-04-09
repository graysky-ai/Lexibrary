---
description: Provides text formatting utilities (bold markers, code blocks).
id: DS-005
updated_by: archivist
status: active
---

# src/utils/formatting.py

## Interface Contract

```python
def bold(text: str) -> str: ...
def code_block(text: str, lang: str = "") -> str: ...
```

## Dependencies

(none)

## Dependents

*(see `lexi lookup` for live reverse references)*

(none)

## Wikilinks

- [[Superseded Concept]]

## Tags

- utils
- formatting

<!-- lexibrary:meta
source: src/utils/formatting.py
source_hash: 019ee7fbcab436116351a1037a9dcf6b6f02f82262c171c5f96ed45b68f67564
interface_hash: ffff111122223333444455556666777788889999aaaabbbbccccddddeeeeffff
design_hash: 4444444444444444444444444444444444444444444444444444444444444444
generated: 2026-04-01T12:00:00.000000
generator: lexibrary-v2
-->
