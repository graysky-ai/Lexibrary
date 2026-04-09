---
title: Old Auth Pattern
id: CV-001
scope: src/old_auth/
tags:
- auth
- patterns
status: active
source: agent
priority: 0
---
All authentication modules under `src/old_auth/` must use token-based validation rather than session cookies. This convention references a path that has been renamed to `src/auth/`.
