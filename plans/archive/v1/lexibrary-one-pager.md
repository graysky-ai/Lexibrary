# Lexibrary — One-Pager

**Lexibrary** is an AI-friendly codebase indexer that produces `.aindex` files: structured Markdown maps that help language models and AI coding assistants navigate codebases without reading every file. The tool **Lexibrary** implements this system.

---

## Technical

**What it does.** Lexibrary crawls a project bottom-up, writes a `.aindex` file in each directory containing:

- A 1–3 sentence directory summary (LLM-generated)
- A table of files with token counts and one-sentence descriptions
- A table of subdirectories with their summaries

**Architecture.** Config is Pydantic-validated from `lexibrary.toml`. A pathspec-based matcher applies `.gitignore` and config patterns. The crawler uses SHA-256 hashes to detect changes; only modified files are re-summarized. LLM prompts live in BAML (provider-agnostic); supported backends are Anthropic, OpenAI, and Ollama. A daemon combines `watchdog` file events, debouncing, and periodic full sweeps for continuous indexing.

**Cost control.** Batched file summaries, incremental hashing, short output caps (~80 tokens/file, ~150/dir), truncation of large files, and support for cheaper models (e.g. GPT-4o-mini, Claude Haiku) keep API usage low.

---

## Business

**Problem.** AI coding assistants hit context limits quickly. Feeding entire codebases is impractical; random file sampling is unreliable. Developers waste time pasting files or re-explaining structure.

**Value.** Lexibrary gives AI assistants a compact, hierarchical map. They can decide what to read instead of guessing, reducing token burn and improving relevance. Teams get:

- **Faster AI-assisted workflows** — less context waste, fewer failed suggestions
- **Easier onboarding** — humans and agents can understand layout at a glance
- **Predictable cost** — configurable providers, batching, and incremental updates

**Audience.** Software teams using Cursor, GitHub Copilot, or custom agent workflows on large or multi-repo codebases.

---

## Research

**Context optimization.** LLMs are limited by context windows. Lexibrary treats codebase navigation as a retrieval problem: lightweight, LLM-generated summaries act as a structured index. This fits research on context-efficient RAG and selective context injection for coding agents.

**Artifact design.** `.aindex` files are human-readable, version-controllable Markdown. They sit alongside code, not in a separate DB. That aligns with work on transparent, inspectable AI tooling and hybrid human–agent workflows.

**Incremental indexing.** Hash-based change detection and batched re-summarization support continuous integration of edits, echoing ideas from incremental compilation and live programming environments applied to AI-augmented development.

---

## Summary

| Dimension    | Essence                                                                 |
|-------------|-------------------------------------------------------------------------|
| **Technical** | Bottom-up crawler, BAML/LLM summaries, pathspec ignore, daemon, incremental hashing |
| **Business**  | Lower context waste, faster AI-assisted coding, configurable cost for teams |
| **Research**  | Context-efficient retrieval, inspectable AI artifacts, incremental indexing for agents |
