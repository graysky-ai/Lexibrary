// Curator: Budget Trimmer (Sonnet)
//
// Condenses knowledge-layer files that exceed their token budgets.
// The sub-agent receives the full file content, a target token budget,
// and section priority hints indicating which sections to preserve.
// It returns condensed content and a manifest of what was trimmed.
//
// This is a LOSSY transformation (High risk). Under auto_low the
// coordinator only proposes condensation; under full it executes.

class CondensedFileOutput {
  condensed_content string
  trimmed_sections string[]
}

function CuratorCondenseFile(
  file_content: string,
  budget_target: int,
  section_priority_hints: string[]
) -> CondensedFileOutput {
  client ConfigDriven
  prompt #"
    You are the Budget Trimmer for a software project's knowledge library.
    A knowledge-layer file (design file, START_HERE.md, or HANDOFF.md) has
    exceeded its token budget. Your job is to condense the file content to
    fit within the target budget while preserving the most important
    information.

    --- FILE CONTENT ---
    {{ file_content }}

    --- BUDGET ---
    Target token budget: {{ budget_target }} tokens

    --- SECTION PRIORITY (highest to lowest) ---
    {% for section in section_priority_hints %}
    {{ loop.index }}. {{ section }}
    {% endfor %}

    CONDENSATION RULES:

    1. **Preserve high-priority sections in full.** The sections listed in
       the priority hints (above) MUST be preserved without loss. These
       typically include Interface, Dependencies, and Insights.

    2. **Preserve structural elements.** Frontmatter (YAML between `---`
       markers), section headings, and footer metadata MUST remain intact.

    3. **Trim lower-priority content first.** Remove or shorten in this
       order of preference:
       a. Verbose summaries and redundant descriptions
       b. Duplicate or overlapping examples
       c. Extended prose that restates what the code already shows
       d. Bullet points that add marginal value

    4. **Maintain coherence.** The condensed file must still read as a
       complete, well-structured document. Do not leave dangling references
       or orphaned sections.

    5. **Document what was trimmed.** For each section or block you remove
       or shorten, add a concise entry to `trimmed_sections` describing
       what was removed and why (e.g., "Removed 3 redundant examples from
       Summary section", "Shortened verbose description in Dependencies").

    6. **Fit within budget.** The condensed content MUST be shorter than
       the original. Aim to fit within the target token budget, though
       exact token counting is approximate.

    {{ ctx.output_format }}
  "#
}
