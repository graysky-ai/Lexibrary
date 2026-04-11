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
source_hash: a97fef3831e2a98c984df783c819b3bb94a2bb9f1bca2327b7cebc18e8751676
interface_hash: 7f8639ce2d6978a3dbfd86f09c15af14639577105153cd278554b27653cef12b
design_hash: 20f1523d3f4a923bd08d76164470cd240a15cadfdf5bea2ba780c1d14363d59b
generated: 2026-04-11T07:30:23.172714
generator: lexibrary-v2
-->
