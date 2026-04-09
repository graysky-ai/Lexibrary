// Curator: Staleness Resolver (Opus)
//
// Regenerates a stale design file from current source content.
// Used when updated_by is NOT "agent" or "maintainer" — these files
// receive full mechanical regeneration rather than reconciliation.

class HashMismatchDetails {
  source_hash_stale bool
  interface_hash_stale bool
  stored_source_hash string?
  current_source_hash string?
  stored_interface_hash string?
  current_interface_hash string?
}

class StalenessResolverOutput {
  summary string
  interface_contract string
  dependencies DesignFileDependency[]
  tests string?
  complexity_warning string?
  wikilinks string[]
  tags string[]
}

function CuratorResolveStaleness(
  source_path: string,
  source_content: string,
  existing_design_content: string?,
  hash_mismatch: HashMismatchDetails
) -> StalenessResolverOutput {
  client ConfigDriven
  prompt #"
    You are the Curator Staleness Resolver for a software project's knowledge
    library. A design file has fallen out of sync with its source file. Your
    job is to regenerate the design file content from the current source.

    This is a FULL REGENERATION — the existing design file was written by an
    automated pipeline (not a human or AI agent), so there is no agent-specific
    knowledge to preserve. Generate fresh content from the source.

    SOURCE FILE: {{ source_path }}

    --- CURRENT SOURCE CONTENT ---
    {{ source_content }}

    {% if existing_design_content %}
    --- EXISTING DESIGN FILE (for reference only — regenerate from source) ---
    {{ existing_design_content }}
    {% endif %}

    --- HASH MISMATCH DETAILS ---
    Source hash stale: {{ hash_mismatch.source_hash_stale }}
    Interface hash stale: {{ hash_mismatch.interface_hash_stale }}
    {% if hash_mismatch.stored_source_hash %}Stored source hash: {{ hash_mismatch.stored_source_hash }}{% endif %}
    {% if hash_mismatch.current_source_hash %}Current source hash: {{ hash_mismatch.current_source_hash }}{% endif %}
    {% if hash_mismatch.stored_interface_hash %}Stored interface hash: {{ hash_mismatch.stored_interface_hash }}{% endif %}
    {% if hash_mismatch.current_interface_hash %}Current interface hash: {{ hash_mismatch.current_interface_hash }}{% endif %}

    INSTRUCTIONS:
    1. **summary**: Write a single sentence describing WHY this file exists
       and its role in the project — not just what it contains. Focus on the
       file's purpose and how it fits into the broader system.

    2. **interface_contract**: Produce a fenced code block showing the public
       API surface (classes, functions, constants, type aliases with their
       signatures). For non-code files, write a brief prose description.

    3. **dependencies**: List each import that resolves to a project-local
       file. Use the relative path within the project for `path` and a brief
       description for `description`. Exclude standard library and third-party.

    4. **tests**: If you can identify the corresponding test file or a
       description of test coverage, include it. Otherwise leave null.

    5. **complexity_warning**: Flag non-obvious behaviour, tricky edge cases,
       or architectural gotchas. Leave null if straightforward.

    6. **wikilinks**: List concept names (domain terms, patterns, conventions)
       that a reader should understand. Use short noun phrases.

    7. **tags**: Provide 3-7 short lowercase labels categorizing the file.

    {% if hash_mismatch.interface_hash_stale %}
    IMPORTANT: The interface hash has changed, meaning the public API surface
    has been modified. Pay special attention to accurately capturing the
    current interface contract.
    {% endif %}

    {{ ctx.output_format }}
  "#
}
