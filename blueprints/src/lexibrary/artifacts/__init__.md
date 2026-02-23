# artifacts

**Summary:** Re-exports all Pydantic 2 data models for Lexibrarian output artifact types.

## Re-exports

`AIndexEntry`, `AIndexFile`, `ConceptFile`, `ConceptFileFrontmatter`, `DesignFile`, `DesignFileFrontmatter`, `StalenessMetadata`

## Dependents

- `lexibrarian.archivist.pipeline` -- imports `DesignFile`, `DesignFileFrontmatter`, `StalenessMetadata`, `AIndexEntry`
- `lexibrarian.indexer.generator` -- imports `AIndexEntry`, `AIndexFile`, `StalenessMetadata`
- CLI commands (`lookup`, `describe`) consume these models
