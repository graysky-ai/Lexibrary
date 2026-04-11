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
source_hash: e5ffd5a06d20de141e2e334fb9a9f39ab018a1a006480dd0bb724a4b8dd54252
interface_hash: 5ed51f87dc0c012922f7caca69e99aaa906480c320cc11f91dce9f3bb329c564
design_hash: bfa024d7675e4dfbc460712742b9bcf2784a7ea6b71f77459d4d3744b1ab3d9e
generated: 2026-04-11T07:30:23.172430
generator: lexibrary-v2
-->
