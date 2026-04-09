// Curator: Agent-Edit Reconciliation (Opus)
//
// Reconciles an agent-edited design file with current source content.
// Used when updated_by is "agent" or "maintainer", or when the
// change_checker classifies a file as AGENT_UPDATED (no metadata
// footer or design_hash drift).
//
// Section treatment during reconciliation:
//   - Summary: regenerate from source
//   - Interface: regenerate from source
//   - Dependencies: regenerate from source
//   - Dependents: regenerate from source
//   - Key Concepts: preserve if still accurate
//   - Dragons: preserve
//   - Custom notes: preserve
//   - Insights: preserve

class ReconciliationInput {
  source_path string
  source_content string
  agent_edited_design string
  source_diff string?
}

class ReconciliationOutput {
  summary string
  interface_contract string
  dependencies DesignFileDependency[]
  key_concepts string?
  dragons string?
  custom_notes string?
  insights string?
  confidence float
  recommendation string
}

function CuratorReconcileDesignFile(
  input: ReconciliationInput
) -> ReconciliationOutput {
  client ConfigDriven
  prompt #"
    You are the Curator Reconciliation Agent for a software project's
    knowledge library.  A design file was edited by an AI agent or
    human maintainer and has drifted from its source file.  Your job is
    to produce a reconciled design file that:

    1. Regenerates mechanical sections from current source (accurate)
    2. Preserves valuable agent-authored knowledge (no data loss)

    SOURCE FILE: {{ input.source_path }}

    --- CURRENT SOURCE CONTENT (authoritative) ---
    {{ input.source_content }}

    --- AGENT-EDITED DESIGN FILE (contains agent knowledge) ---
    {{ input.agent_edited_design }}

    {% if input.source_diff %}
    --- SOURCE DIFF (changes since design was last generated) ---
    {{ input.source_diff }}
    {% endif %}

    SECTION-BY-SECTION INSTRUCTIONS:

    1. **summary**: Regenerate from the current source content.  Write a
       single sentence describing WHY this file exists and its role in
       the project.  Do NOT copy the agent's summary — derive it fresh
       from the source.

    2. **interface_contract**: Regenerate from the current source.
       Produce a fenced code block showing the public API surface
       (classes, functions, constants, type aliases with signatures).
       For non-code files, write a brief prose description.

    3. **dependencies**: Regenerate from the current source.  List each
       import that resolves to a project-local file.  Use the relative
       path for `path` and a brief description for `description`.
       Exclude standard library and third-party imports.

    4. **key_concepts**: PRESERVE the agent's key concepts section if
       the concepts are still accurate given the current source.
       Remove any that reference deleted entities.  Return null if the
       agent had no key concepts or they are all stale.

    5. **dragons**: PRESERVE the agent's dragons/gotchas/warnings
       section verbatim.  These represent hard-won knowledge.  Return
       null if the agent had no dragons section.

    6. **custom_notes**: PRESERVE any other agent-authored notes,
       observations, or explanations that do not fit into the above
       sections.  Return null if none exist.

    7. **insights**: PRESERVE the existing Insights section verbatim.
       These were curated from sidecar comments and should not be
       modified.  Return null if no Insights section exists.

    8. **confidence**: A float between 0.0 and 1.0 indicating your
       confidence that the reconciled output is correct and complete:
       - 0.9-1.0: straightforward merge, high confidence
       - 0.6-0.8: some judgment calls, moderate confidence
       - below 0.6: significant uncertainty, recommend human review

    9. **recommendation**: One of:
       - "merge": the reconciled output should be written
       - "full_regen": agent edits are low-value (mangled archivist
         output or near-duplicate); recommend full regeneration instead
       - "human_review": significant agent content at risk; defer to
         human review

    IMPORTANT RULES:
    - The source content is AUTHORITATIVE for Summary, Interface,
      Dependencies, and Dependents.
    - Agent-authored content (Key Concepts, Dragons, Custom Notes,
      Insights) is PRESERVED unless clearly stale.
    - When in doubt, PRESERVE agent content — stale is better than lost.
    - If the agent edits look like mangled or slightly modified
      archivist output (no real new knowledge), set recommendation
      to "full_regen".

    {{ ctx.output_format }}
  "#
}
