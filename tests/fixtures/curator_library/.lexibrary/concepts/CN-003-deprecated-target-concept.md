---
title: Deprecated Target Concept
id: CN-003
aliases: [dep-target]
tags:
- deprecation
- testing
status: active
---
This concept is an active concept with multiple inbound references. It exists to test cascade analysis and autonomy gating when a curator proposes deprecating a well-referenced artifact.

## Details

The concept is referenced by three design files: login.py.md, session.py.md, and user.py.md. Any deprecation action must account for these dependents and produce migration edits.
