"""Default project configuration template."""

from __future__ import annotations

DEFAULT_PROJECT_CONFIG_TEMPLATE = """\
# Lexibrary project configuration
# This file is created by `lexictl init` and lives at .lexibrary/config.yaml
# Values here override the global config at ~/.config/lexibrary/config.yaml

# Scope root: only files under this path (relative to project root) get design files
# Set to "src/" to restrict design file generation to your source directory
scope_root: "."

# Project name (set during lexictl init)
project_name: ""

# Agent environments configured during init (e.g., claude, cursor)
agent_environment: []

# I Was Here (IWH) configuration
iwh:
  enabled: true                          # Enable IWH agent trace files

# LLM provider settings
llm:
  provider: anthropic                    # LLM provider: anthropic, openai, ollama
  model: claude-sonnet-4-6              # Model identifier
  api_key_env: ANTHROPIC_API_KEY         # Env var holding the API key
  api_key_source: env                    # How the API key is provided: env, dotenv, or manual
  max_retries: 3                         # Retry attempts on API failure
  timeout: 60                            # Request timeout in seconds

# Per-artifact token budgets (validation targets for generated content)
token_budgets:
  design_file_tokens: 400                # Full design file budget
  design_file_abridged_tokens: 100       # Abridged design file budget
  aindex_tokens: 200                     # .aindex routing table budget
  concept_file_tokens: 400               # Concept file budget

# Mapping strategies (glob patterns → generation strategy)
# Populated in Phase 4; empty list uses default 1:1 mapping
mapping:
  strategies: []

# Ignore patterns for file discovery
ignore:
  use_gitignore: true                    # Respect .gitignore files
  additional_patterns:
    - .lexibrary/START_HERE.md
    - ".lexibrary/**/*.md"
    - ".lexibrary/**/.aindex"
    - node_modules/
    - __pycache__/
    - .git/
    - .venv/
    - venv/
    - "*.lock"
    - .env
    - ".env.*"
    - "*.env"

# Background daemon settings
daemon:
  debounce_seconds: 2.0                  # Coalesce rapid file events (seconds)
  sweep_interval_seconds: 3600           # Full re-index safety net (seconds)
  sweep_skip_if_unchanged: true          # Skip sweep if no files changed since last run
  git_suppression_seconds: 5             # Suppress watchdog events after git operations
  watchdog_enabled: false                # Enable real-time file watching (opt-in)
  log_level: info                        # Daemon log level (debug, info, warning, error)

# Crawl behaviour
crawl:
  max_file_size_kb: 512               # Files larger than this (KB) are skipped during update
  binary_extensions:  # Extensions treated as binary
    - .png
    - .jpg
    - .jpeg
    - .gif
    - .ico
    - .svg
    - .webp
    - .mp3
    - .mp4
    - .wav
    - .ogg
    - .webm
    - .woff
    - .woff2
    - .ttf
    - .eot
    - .zip
    - .tar
    - .gz
    - .bz2
    - .7z
    - .rar
    - .pdf
    - .doc
    - .docx
    - .xls
    - .xlsx
    - .exe
    - .dll
    - .so
    - .dylib
    - .pyc
    - .pyo
    - .class
    - .o
    - .obj
    - .sqlite
    - .db

# AST-based interface extraction
ast:
  enabled: true                          # Enable interface skeleton extraction
  languages:                             # Languages to extract interfaces from
    - python
    - typescript
    - javascript
"""
