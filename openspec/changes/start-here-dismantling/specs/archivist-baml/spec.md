## REMOVED Requirements

### Requirement: StartHereOutput BAML type
**Reason**: START_HERE generation is removed entirely. Topology is now procedural, not LLM-generated. The `StartHereOutput` type in `baml_src/types.baml` and the corresponding Python class are no longer needed.
**Migration**: Delete `StartHereOutput` class from `baml_src/types.baml`. Run `baml-cli generate` to regenerate Python client.

### Requirement: ArchivistGenerateStartHere BAML function
**Reason**: START_HERE generation is removed entirely. The BAML function `ArchivistGenerateStartHere` in `baml_src/archivist_start_here.baml` is no longer needed.
**Migration**: Delete `baml_src/archivist_start_here.baml` entirely. Run `baml-cli generate` to regenerate Python client.
