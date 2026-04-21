// Archivist: generate a design file for a source file

function ArchivistGenerateDesignFile(
  source_path: string,
  source_content: string,
  interface_skeleton: string?,
  language: string?,
  existing_design_file: string?,
  available_artifacts: string[]?,
  symbol_enums: string?,
  symbol_call_paths: string?,
  symbol_branch_parameters: string?,
  include_data_flows: bool?
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

    {% if symbol_enums %}
    --- ENUMS AND CONSTANTS DEFINED IN THIS FILE ---
    {{ symbol_enums }}
    {% endif %}

    {% if symbol_call_paths %}
    --- CALL PATHS INTO AND OUT OF THIS FILE ---
    {{ symbol_call_paths }}
    {% endif %}

    {% if symbol_branch_parameters %}
    --- BRANCH PARAMETERS (functions whose parameters drive branching) ---
    {{ symbol_branch_parameters }}
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
    5. **complexity_warning**: Emit `complexity_warning` ONLY when the
       warning can cite a specific invariant, symbol name, file path, or
       version string (e.g. "Python 3.11+", "SQLite WAL mode", a named
       transaction boundary, a named private helper whose contract
       matters). Do NOT emit generic hedging cautions that would apply to
       any module of the same type (e.g. "be careful with `__init__.py`
       files"). Leave `complexity_warning` null when no specific invariant
       is load-bearing.
    6. **wikilinks**: ONLY use names from the available artifacts list above.
       Do not invent new names. Emit a wikilink ONLY when the target is a
       named concept/convention/playbook that MATERIALLY SHAPES the file's
       design. The bar is "would removing this link leave the design file
       meaningfully less informative?" — a passing mention of the name alone
       is not sufficient. If no available artifacts meet the bar, return an
       empty list. Every entry in this list MUST exactly match one of the
       provided artifact names. If no available artifacts section is present,
       list concept names (domain terms, patterns, or conventions) that a
       reader should understand using short noun phrases, applying the same
       material-shaping bar.
    7. **tags**: Emit AT MOST 3 short lowercase tags. Each tag SHOULD add
       signal not already derivable from the filename or the summary field.
       If fewer than 3 tags add non-derivable signal, emit only those; empty
       is acceptable.
    8. **enum_notes**: For every enum or named constant listed in the "ENUMS
       AND CONSTANTS" section, produce an entry with its role in the system.
       Keep role descriptions to one clause. If no enums are listed, leave
       enum_notes null.
    9. **call_path_notes**: If a "CALL PATHS" section is provided, write 1-3
       narrative entries summarising the most important call paths. Focus on
       the flow of *behaviour*, not the mechanical call sequence. Leave null
       if no call paths are provided.
    10. **data_flow_notes**: If `include_data_flows` is true and a "BRANCH
       PARAMETERS" section is provided, write one DataFlowNote per entry in
       that section. Use the function name as `location`, the parameter name
       as `parameter`, and write one sentence describing how the parameter
       value affects the function's behaviour as `effect`. Do NOT invent
       parameters not listed in the BRANCH PARAMETERS section. If
       `include_data_flows` is false or null, or no BRANCH PARAMETERS section
       is present, leave data_flow_notes null.

    When updating an existing design file, preserve any human/agent-added
    context that remains accurate. Prefer updating over replacing.

    {{ ctx.output_format }}
  "#
}
