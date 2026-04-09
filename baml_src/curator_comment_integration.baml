// Curator: Comment Integration (Sonnet)
//
// Integrates sidecar comments into the Insights section of a design file.
// Each comment is classified as durable (integrate), ephemeral (prune),
// or actionable (promote to Stack post / IWH signal).
//
// The sub-agent writes ONLY the Insights section — no other section
// of the design file is modified.

class SidecarComment {
  body string
  date string
}

enum CommentDisposition {
  DURABLE
  EPHEMERAL
  ACTIONABLE
}

class CommentClassificationOutput {
  comment_index int
  disposition CommentDisposition
  insight_text string?
  promotion_title string?
  promotion_problem string?
  rationale string
}

class CommentIntegrationOutput {
  insights_section string
  classifications CommentClassificationOutput[]
}

function CuratorIntegrateComments(
  design_file_content: string,
  comments: SidecarComment[],
  source_file_content: string?
) -> CommentIntegrationOutput {
  client ConfigDriven
  prompt #"
    You are the Comment Curator for a software project's knowledge library.
    Your job is to process sidecar comments left by agents on design files
    and produce an updated Insights section.

    Write the Insights section ONLY. Do not modify any other section.

    --- DESIGN FILE ---
    {{ design_file_content }}

    --- SIDECAR COMMENTS ---
    {% for comment in comments %}
    [{{ loop.index0 }}] ({{ comment.date }}): {{ comment.body }}
    {% endfor %}

    {% if source_file_content %}
    --- SOURCE FILE (for context) ---
    {{ source_file_content }}
    {% endif %}

    CLASSIFICATION RULES:
    Classify each comment into exactly one disposition:

    1. **DURABLE** — Design rationale, gotchas, cross-file contracts,
       historical context ("We chose X because...", "This looks wrong but
       is correct because...", "Callers must ensure..."). These become
       permanent entries in the Insights section.

    2. **EPHEMERAL** — Progress notes, obvious-from-diff observations,
       operational annotations ("Updated the tests", "Refactored to use
       new API", "WIP: still needs cleanup"). These are pruned after TTL.
       Do NOT include these in the Insights section.

    3. **ACTIONABLE** — Bug reports, questions, suggestions that need
       tracking ("process_batch silently swallows TimeoutError", "Should
       we add rate limiting here?"). These are promoted to Stack posts.
       For actionable items, provide a clear promotion_title and
       promotion_problem.

    INSIGHTS SECTION RULES:
    - Content that BELONGS: design rationale, dragons/gotchas, cross-file
      contracts, historical context
    - Content that does NOT belong: progress notes (ephemeral), code
      descriptions (Summary's job), bug reports (promote to Stack)
    - Use bullet points for individual insights
    - Be concise — each insight should be 1-3 sentences
    - If the design file already has an Insights section, APPEND new
      insights to the existing content (do not replace)
    - If there are no durable insights, return an empty string for
      insights_section

    {{ ctx.output_format }}
  "#
}
