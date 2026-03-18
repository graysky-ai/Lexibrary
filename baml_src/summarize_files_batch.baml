// Batch file summarization

function SummarizeFilesBatch(files: FileInput[]) -> BatchFileSummary[] {
  client ConfigDriven
  prompt #"
    Summarize each of the following files in ONLY 1-2 sentences each.
    Focus on what each file does, its main purpose, and key exports or interfaces.
    Be concise and specific. Return one summary per file.

    {% for file in files %}
    --- File: {{ file.filename }} ({{ file.language }}) ---
    {{ file.content }}

    {% endfor %}

    {{ ctx.output_format }}
  "#
}
