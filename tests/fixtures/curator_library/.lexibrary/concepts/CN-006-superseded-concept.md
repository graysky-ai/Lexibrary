---
title: Superseded Concept
id: CN-006
aliases: [old-auth-flow]
tags:
- auth
- migration
- testing
status: active
superseded_by: Authentication
---
This concept describes the original authentication flow that has been replaced by the current [[Authentication]] approach. It has a `superseded_by` field pointing to the active successor concept and active dependents that still reference it, making it a candidate for migration execution tests.

## Details

When this concept is deprecated, the curator should generate migration edits to replace `[[Superseded Concept]]` wikilinks with `[[Authentication]]` in all dependent design files.
