---
title: Authentication
id: CN-001
aliases: [auth, login]
tags:
- security
- auth
status: active
---
Authentication is the process of verifying user identity via credentials (username/password). The system uses a simple credential check in the login module.

## Details

The login module (`src/auth/login.py`) provides the `authenticate()` function as the primary authentication entry point. Sessions are managed separately by `SessionManager` in `src/auth/session.py`.
