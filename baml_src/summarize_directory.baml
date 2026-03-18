// Directory summarization

function SummarizeDirectory(dirname: string, file_list: string, subdir_list: string) -> string {
  client ConfigDriven
  prompt #"
    Summarize the purpose of the following directory in 1-2 sentences ONLY.
    Focus on what the directory contains and its role in the project.
    Be concise and specific.

    Directory: {{ dirname }}

    Files:
    {{ file_list }}

    Subdirectories:
    {{ subdir_list }}
  "#
}
