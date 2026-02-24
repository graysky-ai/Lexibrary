## Context

Lexibrary currently requires users to set API keys as shell environment variables before running any LLM-powered commands. This is the right approach for CI/CD and power users, but is a friction point for developers who habitually use `.env` files, are new to shell environment configuration, or switch between machines frequently.

Two separate problems are bundled here:
1. **Accessibility**: the wizard offers no guidance on where/how to store keys; it only records the env var name.
2. **Security gap**: `.env` files are not in Lexibrary's default ignore list. If a user runs `lexictl update` in a project with an `.env` file containing an API key, that file will be read as source content and sent to the Archivist LLM.

The BAML layer already handles key security correctly (keys go in HTTP Authorization headers, not prompts). The concern is purely about `.env` files being indexed as source.

## Goals / Non-Goals

**Goals:**
- Close the `.env`-as-source security gap (add to default ignore patterns)
- Give users a multi-choice API key storage path during init: `env`, `dotenv`, or `manual`
- For `dotenv` choice: write the key to `.env`, gitignore it, lexignore it
- Load `.env` at CLI startup when `api_key_source == "dotenv"` (before config or BAML init)
- Zero behaviour change for users who already use env vars (`api_key_source` defaults to `"env"`)

**Non-Goals:**
- System keychain integration (tracked in backlog)
- CI/CD secrets management
- Multi-key rotation or key expiry
- Validating the API key at init time (would require an LLM call)

## Decisions

### D-1: `api_key_source` as an explicit config field (not auto-detection)

Auto-detecting the key source (e.g., "is `.env` present? load it") would silently load credentials without user intent. An explicit `api_key_source: "env" | "dotenv" | "manual"` field in `LLMConfig` makes the loading behaviour deterministic and auditable. Users can see and change it in `config.yaml`.

**Alternatives considered:** Auto-load any `.env` unconditionally at startup. Rejected — surprises users who have a `.env` for other tools and don't want it affecting Lexibrary.

### D-2: Load dotenv at CLI entry point, not in config loader or factory

dotenv must be loaded before `load_config()` runs (so env vars are populated for config validation) and before the BAML factory runs. The right seam is a Typer startup callback in both `lexi_app.py` and `lexictl_app.py`. Each callback:
1. Calls `find_project_root()` to locate the project (already used for config lookup)
2. Reads `config.llm.api_key_source` — but this creates a chicken-and-egg: we need config to know we should load dotenv, but we need dotenv to configure the LLM.

**Resolution**: Load `find_project_root()` and read `.lexibrary/config.yaml` as raw YAML (no Pydantic) to check `llm.api_key_source` before full config init, then load dotenv if needed, then proceed with full config load. Or, simpler: always attempt to load `.env` if it exists and `api_key_source == "dotenv"` in the raw YAML. Use `python-dotenv`'s `load_dotenv(override=False)` so that already-set env vars are not clobbered.

**Simpler alternative accepted**: In both CLI startup callbacks, attempt `load_dotenv(project_root / ".env", override=False)` only when `api_key_source == "dotenv"` is found in the raw YAML. If the raw YAML read fails, skip silently (fallback to normal env var behaviour).

### D-3: Wizard writes the key via `python-dotenv`'s `set_key()`, not raw file append

`dotenv.set_key(dotenv_path, key_name, key_value)` safely upserts a single variable in a `.env` file without clobbering existing content. This is the correct API and avoids DIY line-editing.

### D-4: Both `.lexignore` and `IgnoreConfig.additional_patterns` get `.env` patterns

The ignore-system has two layers: default `additional_patterns` in `IgnoreConfig` (schema defaults) and `.lexignore` written by the scaffolder at `lexictl init` time. Adding patterns to both layers means:
- Existing projects that never re-run `lexictl init` are protected via schema defaults.
- New projects get an explicit `.lexignore` entry as a visible reminder.

### D-5: Wizard `api_key_value` is an in-memory-only field

`WizardAnswers.api_key_value` holds the raw key entered by the user only for the duration of the wizard run. It is written immediately to `.env` via `set_key()` and never persisted to config or returned beyond the wizard orchestration. The summary table in Step 8 shows `"[stored in .env]"` or `"[from environment]"` — never the actual key value.

## Risks / Trade-offs

- **`.env` already exists**: `set_key()` handles upsert safely; the wizard should note if `.env` already has the variable set. Risk is low.
- **`.gitignore` already contains `.env`**: Adding a duplicate `.env` entry to `.gitignore` is harmless (gitignore deduplicates). The scaffolder should check before appending.
- **`find_project_root()` fails at CLI startup**: If the user runs a command outside a Lexibrary project, `find_project_root()` returns `None`. In this case, skip dotenv loading entirely — the error will surface naturally when the config loader fails.
- **`python-dotenv` version**: Bounded range `>=1.0.0,<2.0.0` — the `set_key()` API has been stable since 1.0.

## Migration Plan

1. Add `python-dotenv` to `pyproject.toml`, bump lockfile.
2. Add `api_key_source` field to `LLMConfig` schema and defaults template (both default `"env"` — no behaviour change for existing users).
3. Add `.env` patterns to `IgnoreConfig.additional_patterns` defaults.
4. Update scaffolder to write `.env` patterns to `.lexignore`.
5. Extend wizard Step 4 with storage-method sub-step.
6. Add startup dotenv loading to both CLI entry points.

No migration required for existing projects — defaults preserve current behaviour entirely.

## Open Questions

- Should `lexictl setup --update` re-prompt the storage method if `api_key_source` already exists in config? Lean: no, only re-prompt if `api_key_source` is unset or `"manual"`.
