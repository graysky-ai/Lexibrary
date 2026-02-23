## ADDED Requirements

### Requirement: IWH path computation
The system SHALL provide `iwh_path(project_root: Path, source_directory: Path) -> Path` in `src/lexibrary/utils/paths.py` that computes the `.iwh` file path in the `.lexibrary/` mirror tree.

#### Scenario: Subdirectory IWH path
- **WHEN** calling `iwh_path(project_root, project_root / "src" / "auth")`
- **THEN** it SHALL return `project_root / ".lexibrary" / "src" / "auth" / ".iwh"`

#### Scenario: Project root IWH path
- **WHEN** calling `iwh_path(project_root, project_root)`
- **THEN** it SHALL return `project_root / ".lexibrary" / ".iwh"`

#### Scenario: Nested directory IWH path
- **WHEN** calling `iwh_path(project_root, project_root / "src" / "auth" / "middleware")`
- **THEN** it SHALL return `project_root / ".lexibrary" / "src" / "auth" / "middleware" / ".iwh"`
