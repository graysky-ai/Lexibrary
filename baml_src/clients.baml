// Lexibrary LLM client definitions

retry_policy DefaultRetry {
  max_retries 2
}

client<llm> AnthropicClient {
  provider anthropic
  options {
    model "claude-sonnet-4-5-20250929"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 200
  }
}

client<llm> OpenAIClient {
  provider openai
  options {
    model "gpt-5-nano"
    api_key env.OPENAI_API_KEY
  }
}

client<llm> OpenAIBackup {
  provider openai
  options {
    model "gpt-5-mini"
    api_key env.OPENAI_API_KEY
    max_completion_tokens 200
  }
}

client<llm> OllamaClient {
  provider openai-generic
  options {
    base_url "http://localhost:11434/v1"
    model "llama3"
    max_tokens 200
    default_role "user"
  }
}

// Archivist clients — Phase 4 (higher token limit for design file generation)

client<llm> AnthropicArchivist {
  provider anthropic
  retry_policy DefaultRetry
  options {
    model "claude-sonnet-4-6"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 1500
  }
}

client<llm> OpenAIArchivist {
  provider openai
  retry_policy DefaultRetry
  options {
    model "gpt-5-mini"
    api_key env.OPENAI_API_KEY
    max_completion_tokens 1500
  }
}

client<llm> PrimaryClient {
  provider fallback
  retry_policy DefaultRetry
  options {
    strategy [OpenAIClient, OpenAIBackup]
  }
}
