// Curator: Comment Auditing (Sonnet)
//
// Three BAML functions for auditing comments and design file quality:
//
// 1. CuratorAuditComment — assesses staleness of TODO/FIXME/HACK markers
//    by analyzing the comment against surrounding code context.
//
// 2. CuratorAuditDescription — evaluates whether a design file's
//    frontmatter description accurately reflects the source file.
//
// 3. CuratorAuditSummary — evaluates whether a design file's Summary
//    section accurately reflects the source file's behavior.
//
// All functions use Sonnet tier. Comment auditing actions are Medium risk.

// --- Shared enums and types ---

enum CommentStaleness {
  STALE @alias("stale")
  CURRENT @alias("current")
  UNCERTAIN @alias("uncertain")
}

// --- Output types ---

class CommentAuditOutput {
  staleness CommentStaleness
  reasoning string
}

class DescriptionAuditOutput {
  quality_score float
  correction string
}

class SummaryAuditOutput {
  quality_score float
  rewrite string
}

// --- Functions ---

function CuratorAuditComment(
  comment_text: string,
  code_context: string
) -> CommentAuditOutput {
  client ConfigDriven
  prompt #"
    You are a Comment Auditor for a software project's knowledge library.
    Your job is to assess whether a TODO, FIXME, or HACK comment is still
    relevant by analyzing it against the surrounding code context.

    --- COMMENT ---
    {{ comment_text }}

    --- SURROUNDING CODE CONTEXT (plus/minus 20 lines) ---
    {{ code_context }}

    ASSESSMENT RULES:

    1. **stale**: The work described in the comment appears to have been
       completed. The surrounding code already implements the referenced
       functionality, fixes the referenced bug, or addresses the referenced
       concern. Be specific in your reasoning about what evidence shows
       completion.

    2. **current**: The work described in the comment has NOT been done.
       The code does not yet implement the referenced functionality or fix.
       The comment remains actionable.

    3. **uncertain**: You cannot determine staleness with confidence.
       This includes:
       - Comments containing external references (issue numbers like #123,
         JIRA-456, URLs) that require looking up external state
       - Comments where the referenced work is partially done
       - Comments where the intent is ambiguous

    IMPORTANT:
    - When a comment contains an external reference (issue number, ticket
      ID, URL), ALWAYS classify as `uncertain` and note that the external
      reference requires human review.
    - Err on the side of `uncertain` over `stale` when evidence is weak.
    - Your reasoning should reference specific code elements (function
      names, variable names, logic) that support your assessment.

    {{ ctx.output_format }}
  "#
}

function CuratorAuditDescription(
  description: string,
  source_content: string
) -> DescriptionAuditOutput {
  client ConfigDriven
  prompt #"
    You are a Description Auditor for a software project's knowledge library.
    Your job is to evaluate whether a design file's frontmatter description
    accurately reflects the corresponding source file's actual behavior and
    purpose.

    --- DESIGN FILE DESCRIPTION ---
    {{ description }}

    --- SOURCE FILE CONTENT ---
    {{ source_content }}

    EVALUATION RULES:

    1. **quality_score**: A float between 0.0 and 1.0 indicating how
       accurately the description reflects the source file:
       - 0.9-1.0: Description is accurate and complete
       - 0.7-0.89: Description is mostly accurate with minor gaps
       - 0.5-0.69: Description has notable inaccuracies or omissions
       - Below 0.5: Description contradicts or misrepresents the source

    2. **correction**: If `quality_score` is below 0.7, provide a corrected
       description that accurately captures the file's purpose and role.
       If `quality_score` is 0.7 or above, return an empty string.

    DESCRIPTION QUALITY CRITERIA:
    - Does it describe WHY the file exists (purpose), not just WHAT it
      contains (listing)?
    - Does it accurately reflect the current public API / exports?
    - Does it mention the file's role in the broader system?
    - Is it concise (one sentence, ideally under 120 characters)?
    - Does it avoid referencing deleted or renamed entities?

    {{ ctx.output_format }}
  "#
}

function CuratorAuditSummary(
  summary: string,
  source_content: string
) -> SummaryAuditOutput {
  client ConfigDriven
  prompt #"
    You are a Summary Auditor for a software project's knowledge library.
    Your job is to evaluate whether a design file's Summary section
    accurately reflects the corresponding source file's actual behavior.

    --- DESIGN FILE SUMMARY ---
    {{ summary }}

    --- SOURCE FILE CONTENT ---
    {{ source_content }}

    EVALUATION RULES:

    1. **quality_score**: A float between 0.0 and 1.0 indicating how
       accurately the summary reflects the source file:
       - 0.9-1.0: Summary is accurate and comprehensive
       - 0.7-0.89: Summary is mostly accurate with minor drift
       - 0.5-0.69: Summary has notable inaccuracies or stale content
       - Below 0.5: Summary significantly misrepresents the source

    2. **rewrite**: If `quality_score` is below 0.7, provide an updated
       summary that accurately captures the file's behavior and purpose.
       If `quality_score` is 0.7 or above, return an empty string.

    SUMMARY QUALITY CRITERIA:
    - Does it accurately describe the file's current behavior?
    - Does it reference the correct functions, classes, and patterns?
    - Does it avoid mentioning deleted or renamed entities?
    - Does it capture the file's relationship to the broader system?
    - Is it well-structured and easy to scan?
    - Does it focus on behavior and contracts, not implementation details?

    {{ ctx.output_format }}
  "#
}
