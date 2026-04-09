// Curator: Deprecation Analyst (Opus)
//
// Evaluates whether an artifact should be deprecated, produces cascade
// analysis, and generates concrete migration edits for dependent artifacts.
// The coordinator supplies pre-computed dependency data from the link graph;
// the sub-agent focuses on judgment (should we deprecate? what edits?).

// --- Input types ---

enum ArtifactKind {
  Concept @alias("concept")
  Convention @alias("convention")
  DesignFile @alias("design_file")
  StackPost @alias("stack_post")
  Playbook @alias("playbook")
}

class DeprecationWorkItem {
  artifact_path string
  artifact_kind ArtifactKind
  current_status string
  target_status string
  superseded_by string?
  deprecated_reason string?
  dependents string[]
  transitive_dependents string[]
  dependent_count int
}

// --- Output types ---

enum DeprecationAction {
  Deprecate @alias("deprecate")
  HardDelete @alias("hard_delete")
  Propose @alias("propose")
  Skip @alias("skip")
}

enum MigrationEditType {
  ReplaceWikilink @alias("replace_wikilink")
  UpdateConceptRef @alias("update_concept_ref")
  RemoveReference @alias("remove_reference")
}

class AffectedArtifact {
  path string
  impact string
}

class MigrationEdit {
  artifact_path string
  edit_type MigrationEditType
  old_value string
  new_value string?
}

class DeprecationResult {
  action DeprecationAction
  migration_brief string?
  cascade_summary AffectedArtifact[]
  migration_edits MigrationEdit[]?
  confidence float
  rationale string
}

// --- Function ---

function CuratorDeprecateArtifact(work_item: DeprecationWorkItem) -> DeprecationResult {
  client ConfigDriven
  prompt #"
    You are the Deprecation Analyst for a software project's knowledge library.
    Your job is to evaluate whether an artifact should be deprecated and, if so,
    produce a cascade analysis and concrete migration edits for dependent
    artifacts.

    ARTIFACT UNDER REVIEW:
    - Path: {{ work_item.artifact_path }}
    - Kind: {{ work_item.artifact_kind }}
    - Current status: {{ work_item.current_status }}
    - Target status: {{ work_item.target_status }}
    {% if work_item.superseded_by %}- Superseded by: {{ work_item.superseded_by }}{% endif %}
    {% if work_item.deprecated_reason %}- Deprecation reason: {{ work_item.deprecated_reason }}{% endif %}

    DEPENDENCY DATA (pre-computed from link graph):
    - Direct dependents ({{ work_item.dependents | length }}):
    {% for dep in work_item.dependents %}
      - {{ dep }}
    {% endfor %}
    - Transitive dependents ({{ work_item.transitive_dependents | length }}):
    {% for dep in work_item.transitive_dependents %}
      - {{ dep }}
    {% endfor %}
    - Total dependent count: {{ work_item.dependent_count }}

    INSTRUCTIONS:

    1. **Evaluate deprecation**: Decide whether the artifact should be
       deprecated, hard-deleted, proposed for human review, or skipped.
       Consider: Is the artifact truly obsolete? Are there active dependents
       that would break? Is there a valid successor?

    2. **Action selection**:
       - `deprecate`: The artifact should transition to deprecated status.
         Use when the artifact is genuinely obsolete and migration is feasible.
       - `hard_delete`: The artifact is already deprecated, past its TTL, and
         has zero remaining references. Safe to remove permanently.
       - `propose`: The situation is ambiguous or high-risk. Flag for human
         review with a clear rationale.
       - `skip`: The artifact should NOT be deprecated. It is still actively
         used or the deprecation request is premature.

    3. **Cascade analysis**: For each affected artifact (direct dependents),
       describe the expected impact. Be specific about what breaks or needs
       updating.

    4. **Migration edits**: When dependents exist and a successor is available
       (`superseded_by` is set), generate concrete `replace_wikilink` edits
       mapping old references to the successor. When no successor exists,
       generate `remove_reference` edits. Only generate `update_concept_ref`
       edits for frontmatter reference updates in dependent concepts or
       conventions.

    5. **Confidence**: A float between 0.0 and 1.0 indicating your confidence
       in the recommended action. Use lower values when the decision is
       ambiguous or when you lack context.

    6. **Rationale**: Explain your reasoning clearly. Reference specific
       dependents or patterns that influenced your decision.

    RULES:
    - If `superseded_by` is set and the successor exists, prefer `deprecate`
      with migration edits over `skip`.
    - If there are many dependents (>5) and no clear successor, prefer
      `propose` over `deprecate`.
    - Never recommend `hard_delete` unless `current_status` is already
      `deprecated` and `dependent_count` is 0.
    - An empty `migration_edits` list is valid when there are no dependents.
    - Set `migration_brief` to null when there are no dependents to migrate.

    {{ ctx.output_format }}
  "#
}
