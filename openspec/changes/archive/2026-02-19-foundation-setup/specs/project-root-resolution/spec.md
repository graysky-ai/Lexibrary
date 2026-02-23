## ADDED Requirements

### Requirement: Walk-up root discovery
The system SHALL provide a `find_project_root(start: Path) -> Path` function that walks upward from `start` through parent directories until it finds a directory containing `.lexibrary/`, returning that directory as the project root.

#### Scenario: .lexibrary/ found in start directory
- **WHEN** calling `find_project_root(path)` from a directory that directly contains `.lexibrary/`
- **THEN** it returns that directory path

#### Scenario: .lexibrary/ found in parent directory
- **WHEN** calling `find_project_root(path)` from a subdirectory whose grandparent contains `.lexibrary/`
- **THEN** it walks upward and returns the grandparent directory path

#### Scenario: .lexibrary/ not found raises LexibraryNotFoundError
- **WHEN** calling `find_project_root(path)` from a directory tree with no `.lexibrary/`
- **THEN** it raises `LexibraryNotFoundError` (not SystemExit)

#### Scenario: Walk stops at filesystem root
- **WHEN** calling `find_project_root(Path("/"))` on a system with no `.lexibrary/` anywhere
- **THEN** it raises `LexibraryNotFoundError` without infinite looping

### Requirement: LexibraryNotFoundError exception
The system SHALL define a `LexibraryNotFoundError` exception class in `src/lexibrary/exceptions.py` that callers can catch and handle independently of `SystemExit`.

#### Scenario: LexibraryNotFoundError is catchable
- **WHEN** catching `LexibraryNotFoundError` from `find_project_root()`
- **THEN** it is a subclass of `Exception` (not `SystemExit`) and can be caught normally

#### Scenario: CLI commands display a friendly message on LexibraryNotFoundError
- **WHEN** running any `lexi` command from a directory with no `.lexibrary/`
- **THEN** the CLI prints a clear error message (via `rich.console.Console`) explaining that `.lexibrary/` was not found and suggesting `lexi init`, then exits with code 1

### Requirement: Project root used for path resolution
The system SHALL resolve all library paths (design files, `.aindex` files, config) relative to the project root returned by `find_project_root()`.

#### Scenario: Config path derived from project root
- **WHEN** `find_project_root()` returns `/project`
- **THEN** the project config path is `/project/.lexibrary/config.yaml`

#### Scenario: Mirror path derived from project root
- **WHEN** `find_project_root()` returns `/project` and the source file is `/project/src/auth/login.py`
- **THEN** the design file path is `/project/.lexibrary/src/auth/login.py.md`
