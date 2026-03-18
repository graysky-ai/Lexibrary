// Archivist: generate a design file for a source file

function ArchivistGenerateDesignFile(
  source_path: string,
  source_content: string,
  interface_skeleton: string?,
  language: string?,
  existing_design_file: string?,
  available_concepts: string[]?
) -> DesignFileOutput {
  client ConfigDriven
  prompt #"
    You are the Archivist for a software project. Your job is to produce a
    structured design file that helps future readers (human or AI) understand
    a source file quickly.

    SOURCE FILE: {{ source_path }}
    {% if language %}LANGUAGE: {{ language }}{% endif %}

    --- SOURCE CONTENT ---
    {{ source_content }}

    {% if interface_skeleton %}
    --- INTERFACE SKELETON (public API surface) ---
    {{ interface_skeleton }}
    {% endif %}

    {% if existing_design_file %}
    --- EXISTING DESIGN FILE (preserve relevant human/agent context) ---
    {{ existing_design_file }}
    {% endif %}

    {% if available_concepts %}
    --- AVAILABLE CONCEPTS (prefer these names for wikilinks) ---
    {% for concept in available_concepts %}
    - {{ concept }}
    {% endfor %}
    {% endif %}

    INSTRUCTIONS:
    1. **summary**: Write a single sentence describing *why* this file exists
       and its role in the project — not just *what* it contains.
    2. **interface_contract**: Produce a fenced code block showing the public
       API surface (classes, functions, constants, type aliases). For non-code
       files, write a brief prose description of the file's structure and
       purpose instead.
    3. **dependencies**: List each import that resolves to a project-local file.
       Use the relative path within the project for `path` and a brief
       description of the dependency relationship for `description`. Exclude
       third-party and standard library imports.
    4. **tests**: If you can identify a corresponding test file or test
       description, include it. Otherwise leave null.
    5. **complexity_warning**: Flag any non-obvious behaviour, tricky edge
       cases, or architectural gotchas. Leave null if the file is
       straightforward.
    6. **wikilinks**: List concept names (domain terms, patterns, or
       conventions) that a reader should understand. Use short noun phrases.
       When available concepts are provided above, prefer using those exact
       names for wikilinks instead of inventing new ones.
    7. **tags**: Provide 3-7 short lowercase labels categorizing the file
       (e.g. "config", "parser", "pydantic-model", "cli", "async").

    When updating an existing design file, preserve any human/agent-added
    context that remains accurate. Prefer updating over replacing.

    {{ ctx.output_format }}
  "#
}
