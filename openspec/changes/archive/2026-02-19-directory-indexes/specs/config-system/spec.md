## ADDED Requirements

### Requirement: CrawlConfig with binary extensions
The `CrawlConfig` Pydantic model in `src/lexibrary/config/schema.py` SHALL include a `binary_extensions: list[str]` field containing file extensions (with leading dot) that are treated as binary. Files with these extensions SHALL be described as `"Binary file (.ext)"` by the index generator rather than having their lines counted.

The field SHALL default to a comprehensive list covering: image formats (`.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.svg`, `.webp`), audio/video (`.mp3`, `.mp4`, `.wav`, `.ogg`, `.webm`), fonts (`.woff`, `.woff2`, `.ttf`, `.eot`), archives (`.zip`, `.tar`, `.gz`, `.bz2`, `.7z`, `.rar`), documents (`.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`), executables/compiled (`.exe`, `.dll`, `.so`, `.dylib`, `.pyc`, `.pyo`, `.class`, `.o`, `.obj`), and database (`.sqlite`, `.db`).

`CrawlConfig` SHALL also be wired into `LexibraryConfig` as `crawl: CrawlConfig = Field(default_factory=CrawlConfig)`.

#### Scenario: CrawlConfig added to LexibraryConfig
- **WHEN** a default `LexibraryConfig` is created
- **THEN** it SHALL have a `crawl` attribute that is a `CrawlConfig` instance

#### Scenario: Default binary extensions include common formats
- **WHEN** a `CrawlConfig` is created with default values
- **THEN** `binary_extensions` SHALL contain at least `.png`, `.jpg`, `.pyc`, `.zip`, `.exe`, `.pdf`, `.mp4`

#### Scenario: Custom binary extensions override defaults
- **WHEN** `LexibraryConfig` is loaded from a config file specifying `crawl.binary_extensions`
- **THEN** `config.crawl.binary_extensions` SHALL contain only the configured values

#### Scenario: CrawlConfig tolerates extra fields
- **WHEN** a `CrawlConfig` is created with an unknown extra field
- **THEN** the extra field SHALL be ignored (not raise a validation error)
