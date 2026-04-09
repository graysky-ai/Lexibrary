---
description: Handles user authentication with username/password credentials.
id: DS-001
updated_by: archivist
status: active
---

# src/auth/login.py

## Interface Contract

```python
def authenticate(username: str, password: str) -> bool: ...
```

## Dependencies

- src/models/user.py

## Dependents

*(see `lexi lookup` for live reverse references)*

- src/auth/session.py

## Wikilinks

- [[Authentication]]

## Tags

- auth
- login

<!-- lexibrary:meta
source: src/auth/login.py
source_hash: deadbeef0000111122223333444455556666777788889999aaaabbbbccccdddd
interface_hash: abcdef0000111122223333444455556666777788889999aaaabbbbccccddd0
design_hash: 0000000000000000000000000000000000000000000000000000000000000000
generated: 2026-03-15T10:30:00.000000
generator: lexibrary-v2
-->
