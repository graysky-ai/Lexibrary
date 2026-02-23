## ADDED Requirements

### Requirement: DetectedProject named tuple
The system SHALL define a `DetectedProject` named tuple with fields `name: str` and `source: str` (one of `"pyproject.toml"`, `"package.json"`, or `"directory"`).

#### Scenario: DetectedProject is a NamedTuple
- **WHEN** creating a `DetectedProject(name="myproject", source="pyproject.toml")`
- **THEN** `result.name` SHALL be `"myproject"` and `result.source` SHALL be `"pyproject.toml"`

### Requirement: DetectedLLMProvider named tuple
The system SHALL define a `DetectedLLMProvider` named tuple with fields `provider: str`, `api_key_env: str`, and `model: str`.

#### Scenario: DetectedLLMProvider is a NamedTuple
- **WHEN** creating a `DetectedLLMProvider(provider="anthropic", api_key_env="ANTHROPIC_API_KEY", model="claude-sonnet-4-6")`
- **THEN** all fields SHALL be accessible by name

### Requirement: Detect project name
`detect_project_name(project_root: Path) -> DetectedProject` SHALL detect the project name with the following precedence: `pyproject.toml` `[project].name` → `package.json` `name` → directory name fallback. It SHALL use `tomllib` (stdlib) for TOML parsing and `json` (stdlib) for JSON parsing.

#### Scenario: Detect from pyproject.toml
- **WHEN** `project_root` contains a `pyproject.toml` with `[project] name = "my-lib"`
- **THEN** the function SHALL return `DetectedProject(name="my-lib", source="pyproject.toml")`

#### Scenario: Detect from package.json when no pyproject.toml
- **WHEN** `project_root` has no `pyproject.toml` but has `package.json` with `"name": "my-app"`
- **THEN** the function SHALL return `DetectedProject(name="my-app", source="package.json")`

#### Scenario: Fallback to directory name
- **WHEN** `project_root` has neither `pyproject.toml` nor `package.json`
- **THEN** the function SHALL return `DetectedProject(name=project_root.name, source="directory")`

#### Scenario: Malformed pyproject.toml falls through
- **WHEN** `pyproject.toml` exists but has no `[project]` table or no `name` key
- **THEN** the function SHALL fall through to `package.json` or directory name

#### Scenario: Malformed package.json falls through
- **WHEN** `package.json` exists but has no `name` key or is invalid JSON
- **THEN** the function SHALL fall through to directory name

### Requirement: Detect scope roots
`detect_scope_roots(project_root: Path) -> list[str]` SHALL check for the existence of `src/`, `lib/`, and `app/` directories under `project_root` and return a list of those that exist.

#### Scenario: Detect src/ directory
- **WHEN** `project_root` contains a `src/` directory
- **THEN** the function SHALL return a list containing `"src/"`

#### Scenario: Detect multiple scope roots
- **WHEN** `project_root` contains both `src/` and `lib/` directories
- **THEN** the function SHALL return `["src/", "lib/"]` (or both in any order)

#### Scenario: No common directories found
- **WHEN** `project_root` contains none of `src/`, `lib/`, `app/`
- **THEN** the function SHALL return an empty list

### Requirement: Detect agent environments
`detect_agent_environments(project_root: Path) -> list[str]` SHALL detect agent environments from filesystem markers:
- `.claude/` directory OR `CLAUDE.md` file → `"claude"`
- `.cursor/` directory → `"cursor"`
- `AGENTS.md` file → `"codex"`

The returned list SHALL be deduplicated.

#### Scenario: Detect Claude from .claude/ directory
- **WHEN** `project_root` contains a `.claude/` directory
- **THEN** the result SHALL contain `"claude"`

#### Scenario: Detect Claude from CLAUDE.md file
- **WHEN** `project_root` contains a `CLAUDE.md` file (but no `.claude/`)
- **THEN** the result SHALL contain `"claude"`

#### Scenario: No duplicate from both .claude/ and CLAUDE.md
- **WHEN** `project_root` contains both `.claude/` directory and `CLAUDE.md` file
- **THEN** `"claude"` SHALL appear exactly once in the result

#### Scenario: Detect Cursor from .cursor/ directory
- **WHEN** `project_root` contains a `.cursor/` directory
- **THEN** the result SHALL contain `"cursor"`

#### Scenario: Detect Codex from AGENTS.md
- **WHEN** `project_root` contains an `AGENTS.md` file
- **THEN** the result SHALL contain `"codex"`

#### Scenario: Detect multiple environments
- **WHEN** `project_root` contains `.claude/` and `.cursor/`
- **THEN** the result SHALL contain both `"claude"` and `"cursor"`

#### Scenario: No environments detected
- **WHEN** `project_root` has none of the marker files/directories
- **THEN** the function SHALL return an empty list

### Requirement: Check existing agent rules
`check_existing_agent_rules(project_root: Path, environment: str) -> str | None` SHALL search the relevant rules file for an existing Lexibrary section marker (`<!-- lexibrary:` in the file content). It SHALL return the file path if found, `None` otherwise.

#### Scenario: Lexibrary marker found in CLAUDE.md
- **WHEN** `environment` is `"claude"` and `CLAUDE.md` contains `<!-- lexibrary:`
- **THEN** the function SHALL return the path to `CLAUDE.md`

#### Scenario: No marker found
- **WHEN** the rules file exists but contains no `<!-- lexibrary:` marker
- **THEN** the function SHALL return `None`

#### Scenario: Rules file does not exist
- **WHEN** the rules file for the environment does not exist
- **THEN** the function SHALL return `None`

### Requirement: Detect LLM providers
`detect_llm_providers() -> list[DetectedLLMProvider]` SHALL check environment variables for known providers in priority order: `ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `GEMINI_API_KEY` → `OLLAMA_HOST`. It SHALL return a list of all providers whose env var is set.

#### Scenario: Anthropic key detected
- **WHEN** `ANTHROPIC_API_KEY` is set in the environment
- **THEN** the result SHALL contain a `DetectedLLMProvider` with `provider="anthropic"`, `api_key_env="ANTHROPIC_API_KEY"`, and an appropriate default model

#### Scenario: Multiple providers detected
- **WHEN** both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are set
- **THEN** the result SHALL contain both providers, with Anthropic first (priority order)

#### Scenario: No providers detected
- **WHEN** no known API key env vars are set
- **THEN** the function SHALL return an empty list

### Requirement: Detect project type
`detect_project_type(project_root: Path) -> str | None` SHALL detect the project type from marker files:
- `pyproject.toml` or `setup.py` → `"python"`
- `package.json` + `tsconfig.json` → `"typescript"`
- `package.json` (without tsconfig) → `"node"`
- `Cargo.toml` → `"rust"`
- `go.mod` → `"go"`

It SHALL return `None` if no type is detected.

#### Scenario: Python project detected
- **WHEN** `project_root` contains `pyproject.toml`
- **THEN** the function SHALL return `"python"`

#### Scenario: TypeScript project detected
- **WHEN** `project_root` contains both `package.json` and `tsconfig.json`
- **THEN** the function SHALL return `"typescript"`

#### Scenario: Node project detected (no tsconfig)
- **WHEN** `project_root` contains `package.json` but not `tsconfig.json`
- **THEN** the function SHALL return `"node"`

#### Scenario: Rust project detected
- **WHEN** `project_root` contains `Cargo.toml`
- **THEN** the function SHALL return `"rust"`

#### Scenario: Go project detected
- **WHEN** `project_root` contains `go.mod`
- **THEN** the function SHALL return `"go"`

#### Scenario: Unknown project type
- **WHEN** `project_root` contains none of the marker files
- **THEN** the function SHALL return `None`

### Requirement: Suggest ignore patterns
`suggest_ignore_patterns(project_type: str | None) -> list[str]` SHALL return a list of suggested `.lexignore` patterns based on the project type:
- `"python"` → `["**/migrations/", "**/__generated__/"]`
- `"node"` or `"typescript"` → `["dist/", "build/", "coverage/", ".next/"]`
- `"rust"` → `["target/"]`
- `"go"` → `["vendor/"]`
- `None` → empty list

#### Scenario: Python ignore patterns
- **WHEN** `project_type` is `"python"`
- **THEN** the result SHALL contain `"**/migrations/"` and `"**/__generated__/"`

#### Scenario: TypeScript ignore patterns
- **WHEN** `project_type` is `"typescript"`
- **THEN** the result SHALL contain `"dist/"`, `"build/"`, `"coverage/"`, and `".next/"`

#### Scenario: No project type returns empty
- **WHEN** `project_type` is `None`
- **THEN** the function SHALL return an empty list
