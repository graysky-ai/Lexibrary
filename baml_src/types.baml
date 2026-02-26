// Lexibrary type definitions

class FileSummary {
  summary string
}

class FileInput {
  filename string
  language string
  content string
}

class BatchFileSummary {
  filename string
  summary string
}

// Archivist types — Phase 4

class DesignFileDependency {
  path string
  description string
}

class DesignFileOutput {
  summary string
  interface_contract string
  dependencies DesignFileDependency[]
  tests string?
  complexity_warning string?
  wikilinks string[]
  tags string[]
}
