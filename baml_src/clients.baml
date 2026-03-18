// Lexibrary LLM client definitions
//
// All real client configuration is built at runtime via
// build_client_registry() in src/lexibrary/llm/client_registry.py.
// This compile-time stub satisfies the BAML compiler; the runtime
// ClientRegistry overrides it before any LLM call is made.

retry_policy DefaultRetry {
  max_retries 2
}

client<llm> ConfigDriven {
  provider openai
  options {
    model "gpt-5-nano"
    api_key ""
  }
}
