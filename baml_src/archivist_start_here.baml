// Archivist: generate START_HERE.md content from project topology

function ArchivistGenerateStartHere(
  project_name: string,
  directory_tree: string,
  aindex_summaries: string,
  existing_start_here: string?
) -> StartHereOutput {
  client AnthropicArchivist
  prompt #"
    You are the Archivist for a software project called "{{ project_name }}".
    Your job is to produce a START_HERE.md that orients new readers (human or
    AI) to the project structure in under 800 tokens total.

    --- DIRECTORY TREE ---
    {{ directory_tree }}

    --- .aindex SUMMARIES (per-directory descriptions) ---
    {{ aindex_summaries }}

    {% if existing_start_here %}
    --- EXISTING START_HERE.md (preserve relevant context) ---
    {{ existing_start_here }}
    {% endif %}

    INSTRUCTIONS — produce each section concisely:

    1. **topology**: An ASCII tree or Mermaid diagram showing the top-level
       project structure. Include only directories and key files — not every
       leaf file. Aim for 10-20 lines.

    2. **ontology**: Define 5-15 key domain terms used in this project. One
       line per term: `**term** — definition`. Focus on terms a newcomer
       would not immediately understand.

    3. **navigation_by_intent**: A markdown table mapping common tasks to
       the file or directory to read first. Format:
       | Task | Read first |
       | --- | --- |
       Include 5-10 rows covering the most common development tasks.

    4. **navigation_protocol**: 3-5 bullet instructions telling a reader
       how to use the .lexibrary knowledge layer effectively (e.g. "read
       the design file before editing a source file").

    Keep total output under 500-800 tokens. Be specific to this project —
    avoid generic advice.

    {{ ctx.output_format }}
  "#
}
