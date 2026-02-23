# init/detection

**Summary:** Pure detection functions for project auto-discovery. All functions take `project_root: Path` and return typed results with no I/O side effects.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `DetectedProject` | `NamedTuple(name: str, source: str)` | Result of project name detection; `source` is `"pyproject.toml"`, `"package.json"`, or `"directory"` |
| `DetectedLLMProvider` | `NamedTuple(provider: str, api_key_env: str, model: str)` | Result of LLM provider detection from env vars |
| `detect_project_name` | `(project_root: Path) -> DetectedProject` | Detect project name with precedence: pyproject.toml -> package.json -> directory name |
| `detect_scope_roots` | `(project_root: Path) -> list[str]` | Check for common source directories (`src/`, `lib/`, `app/`) and return those that exist |
| `detect_agent_environments` | `(project_root: Path) -> list[str]` | Detect agent environments from filesystem markers (`.claude/`, `CLAUDE.md`, `.cursor/`, `AGENTS.md`) |
| `check_existing_agent_rules` | `(project_root: Path, environment: str) -> str \| None` | Search for `<!-- lexibrarian:` marker in agent rules files; returns file path if found |
| `detect_llm_providers` | `() -> list[DetectedLLMProvider]` | Check env vars for known LLM providers in priority order (anthropic, openai, google, ollama) |
| `detect_project_type` | `(project_root: Path) -> str \| None` | Detect project type from marker files; returns `"python"`, `"typescript"`, `"node"`, `"rust"`, `"go"`, or `None` |
| `suggest_ignore_patterns` | `(project_type: str \| None) -> list[str]` | Return suggested `.lexignore` patterns for a given project type |

## Dependencies

- None (only stdlib: `json`, `os`, `tomllib`, `pathlib`)

## Dependents

- `lexibrarian.init.wizard` -- calls all detection functions during the 8-step wizard flow

## Key Concepts

- All functions are pure and side-effect-free (no stdout, no Rich output) for easy testing with `tmp_path`
- Provider detection uses env var presence, not value, to determine availability
- Agent environment detection uses filesystem markers (`_AGENT_MARKERS` registry)
- Project type detection follows a fixed precedence: python > typescript > node > rust > go
