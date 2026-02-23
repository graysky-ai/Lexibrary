# artifacts

**Summary:** Re-exports all Pydantic 2 data models for Lexibrary output artifact types.

## Re-exports

`AIndexEntry`, `AIndexFile`, `ConceptFile`, `ConceptFileFrontmatter`, `DesignFile`, `DesignFileFrontmatter`, `StalenessMetadata`

## Dependents

- `lexibrary.archivist.pipeline` -- imports `DesignFile`, `DesignFileFrontmatter`, `StalenessMetadata`, `AIndexEntry`
- `lexibrary.indexer.generator` -- imports `AIndexEntry`, `AIndexFile`, `StalenessMetadata`
- CLI commands (`lookup`, `describe`) consume these models
