---
description: Defines the User data model.
id: DS-003
updated_by: agent
status: active
---

# src/models/user.py

## Interface Contract

```python
@dataclass
class User:
    id: str
    username: str
    email: str
    def display_name(self) -> str: ...
    def is_admin(self) -> bool: ...
```

## Dependencies

(none)

## Dependents

*(see `lexi lookup` for live reverse references)*

- src/auth/login.py

## Wikilinks

- [[Deprecated Target Concept]]

## Tags

- models
- user

<!-- lexibrary:meta
source: src/models/user.py
source_hash: cccc111122223333444455556666777788889999aaaabbbbccccddddeeeeffff
interface_hash: dddd111122223333444455556666777788889999aaaabbbbccccddddeeeeffff
design_hash: 2222222222222222222222222222222222222222222222222222222222222222
generated: 2026-03-10T08:00:00.000000
generator: lexibrary-v2
-->
