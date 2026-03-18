// Single file summarization

function SummarizeFile(filename: string, language: string, content: string, is_truncated: bool) -> FileSummary {
  client ConfigDriven
  prompt #"
    Summarize the following {{ language }} file in 1-2 sentences ONLY.
    Focus on what the file does, its main purpose, and key exports or interfaces.
    Be concise and specific.
    {% if is_truncated %}
    Note: The file content has been truncated. Summarize based on what is visible.
    {% endif %}

    Filename: {{ filename }}

    Content:
    {{ content }}

    {{ ctx.output_format }}
  "#
}
