// Archivist: generate a design file for a source file

function ArchivistGenerateDesignFile(
  source_path: string,
  source_content: string,
  interface_skeleton: string?,
  language: string?,
  existing_design_file: string?,
  available_artifacts: string[]?
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

    {% if available_artifacts %}
    --- AVAILABLE ARTIFACTS (prefer these names for wikilinks) ---
    {% for artifact in available_artifacts %}
    - {{ artifact }}
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
    6. **wikilinks**: ONLY use names from the available artifacts list above.
       Do not invent new names. If no available artifacts are relevant, return
       an empty list. Every entry in this list MUST exactly match one of the
       provided artifact names. If no available artifacts section is present,
       list concept names (domain terms, patterns, or conventions) that a
       reader should understand using short noun phrases.
    7. **tags**: Provide 3-7 short lowercase labels categorizing the file
       (e.g. "config", "parser", "pydantic-model", "cli", "async").

    When updating an existing design file, preserve any human/agent-added
    context that remains accurate. Prefer updating over replacing.

    {{ ctx.output_format }}
  "#
}
