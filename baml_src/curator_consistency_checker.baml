// Curator Consistency Checker — Haiku-class LLM sub-agent
//
// Performs lightweight read-only analysis on design files, returning
// structured fix instructions for the coordinator to execute.  The
// checker never modifies files directly; all writes go through the
// coordinator's dispatch phase.

class WikilinkAnalysis {
  target string
  resolved bool
  suggestions string[]
}

class DependencyInfo {
  source_path string
  listed_deps string[]
  listed_dependents string[]
}

class ConsistencyFixInstruction {
  action string
  target_wikilink string?
  replacement string?
  rationale string
}

function CuratorCheckConsistency(design_file_content: string, wikilink_analysis: WikilinkAnalysis[], dependency_graph: DependencyInfo[]) -> ConsistencyFixInstruction[] {
  client ConfigDriven
  prompt #"
    You are a Consistency Checker for the Lexibrary knowledge base.
    Your task is to analyze a design file and return structured fix
    instructions. You never modify files yourself — you only return
    instructions.

    --- DESIGN FILE CONTENT ---
    {{ design_file_content }}

    --- WIKILINK ANALYSIS ---
    {% for wl in wikilink_analysis %}
    - [[{{ wl.target }}]]: resolved={{ wl.resolved }}{% if wl.suggestions %}, suggestions={{ wl.suggestions }}{% endif %}
    {% endfor %}

    --- DEPENDENCY GRAPH ---
    {% for dep in dependency_graph %}
    - {{ dep.source_path }}: deps={{ dep.listed_deps }}, dependents={{ dep.listed_dependents }}
    {% endfor %}

    INSTRUCTIONS:
    1. For each unresolved wikilink:
       - If suggestions exist with high confidence, return action="add_alias" with replacement.
       - If no good match, return action="strip_wikilink" to remove the dead reference.
    2. For each dependency mismatch:
       - If a dep is listed but the reverse is missing, return action="add_reverse_dep".
       - If a reverse dep is orphaned (source no longer imports), return action="remove_reverse_dep".
    3. Suggest concept creation only when a domain term appears frequently (3+ files)
       without an existing concept.

    Return a JSON array of ConsistencyFixInstruction objects.
    Be conservative: only suggest changes you are confident about.

    {{ ctx.output_format }}
  "#
}
