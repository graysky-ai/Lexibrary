---
title: Expired Deprecated Convention
id: CV-002
scope: src/legacy/
tags:
- deprecated
- expired
- testing
status: deprecated
source: agent
priority: 0
deprecated_at: '2025-01-10T08:00:00+00:00'
---
All modules under `src/legacy/` must use synchronous I/O only. This convention was deprecated when the legacy module was removed and has no remaining references. It exists to test convention hard deletion when TTL is exceeded.
