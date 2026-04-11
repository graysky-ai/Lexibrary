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
source_hash: b104b590c96558ac05f1d1021ea421886b3a7cb68d39aa88c169e29f31c6eb25
interface_hash: 39b041eeebaff2560ee868f3e87e007e0cd87aad601a99f5b3dd62ad74a06dce
design_hash: 7c21fe0890b4ca13ef6038f7c2cfedb8b0f8a3b5d596c49bc5f8efe78bcf177d
generated: 2026-04-11T07:30:23.171329
generator: lexibrary-v2
-->
