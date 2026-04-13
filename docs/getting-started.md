# Getting Started

This guide walks you through installing Lexibrary, initializing it in a project, generating your first design files, and verifying the output.

## Prerequisites

- **Python 3.11 or later** -- Lexibrary requires Python 3.11+. Check your version with `python --version`.
- **uv (recommended) or pip** -- Lexibrary uses [uv](https://docs.astral.sh/uv/) as its package manager. pip works as well.
- **An LLM API key** -- Lexibrary generates design files using an LLM. You need one of the following environment variables set:
  - `ANTHROPIC_API_KEY` (default provider)
  - `OPENAI_API_KEY`
  - `GEMINI_API_KEY`
  - `OLLAMA_HOST` (for local models)

## Installation

### With uv (recommended)

```bash
# Clone the repository
git clone <repository-url>
cd lexibrary

# Install all dependencies
uv sync

# Verify the installation
uv run lexi --help
uv run lexictl --help
```

### With pip

```bash
# Clone the repository
git clone <repository-url>
cd lexibrary

# Install in development mode
pip install -e .

# For AST-based interface extraction (optional)
pip install -e ".[ast]"

# Verify the installation
lexi --help
lexictl --help
```

After installation, two CLI commands are available:

| Command | Audience | Purpose |
|---------|----------|---------|
| `lexictl` | Operators / team members | Setup, maintenance, design file generation, validation |
| `lexi` | AI agents | Lookups, search, concepts, Stack Q&A |

## Initialize a Project

Navigate to the root of the project you want to index, then run:

```bash
lexictl init
```

This launches an 8-step wizard that detects your project configuration and guides you through setup:

1. **Project name** -- Detected from `pyproject.toml`, `package.json`, or the directory name.
2. **Scope root** -- Which directory tree to index (default: `.` for the whole project, or `src/` if detected).
3. **Agent environment** -- Which AI agent tools you use (e.g., `claude`, `cursor`). Lexibrary generates agent rules for each.
4. **LLM provider** -- Which LLM to use for generating design files. Auto-detects available API keys.
5. **Ignore patterns** -- Additional paths to exclude from indexing, based on detected project type.
6. **Token budgets** -- Target sizes for generated artifacts. Defaults work well for most projects.
7. **I Was Here (IWH)** -- Whether to enable agent trace files for multi-agent workflows.
8. **Summary and confirmation** -- Review all settings before creating the project skeleton.

After confirmation, Lexibrary creates the `.lexibrary/` directory containing your `config.yaml` and initial skeleton.

### Non-interactive mode

For CI pipelines or scripting, skip the wizard prompts and accept all detected defaults:

```bash
lexictl init --defaults
```

### Re-initialization guard

If `.lexibrary/` already exists, `lexictl init` will refuse to run. To change settings after initialization, edit `.lexibrary/config.yaml` directly or run:

```bash
lexictl setup --update
```

## Generate Design Files

Once initialized, generate design files for your entire project:

```bash
lexictl update
```

This command:

1. Discovers all source files under every directory listed in `scope_roots` (respecting ignore patterns).
2. Compares each file's SHA-256 hash against the hash stored in its existing design file (if any).
3. Classifies the type of change (unchanged, content-only, interface-changed, new file).
4. Sends changed files to the configured LLM for design file generation.
5. Writes design files into the `.lexibrary/` mirror tree.
6. Regenerates `TOPOLOGY.md` with the updated project topology.
7. Builds the link graph index.

A progress bar shows the update status. When complete, you see a summary:

```
Update summary:
  Files scanned:       42
  Files unchanged:     0
  Files created:       42
  Files updated:       0
  Files agent-updated: 0
  .aindex refreshed:   8
TOPOLOGY.md regenerated.
```

### Updating a single file

To regenerate the design file for one source file:

```bash
lexictl update path/to/file.py
```

### Updating specific changed files

For git hooks or CI, update only the files that changed:

```bash
lexictl update --changed-only path/to/file1.py path/to/file2.py
```

## Verify the Output

After running `lexictl update`, check the health of your library:

```bash
lexictl status
```

This displays a dashboard showing:

- **Files** -- How many source files are tracked and how many have stale design files.
- **Concepts** -- Count of active, draft, and deprecated concepts.
- **Stack** -- Count of open and resolved Stack Q&A posts.
- **Link graph** -- Number of artifacts and links indexed.
- **Issues** -- Error and warning counts from validation checks.
- **Updated** -- How recently design files were last generated.

For a quick single-line health check (useful in scripts):

```bash
lexictl status --quiet
```

To run the full suite of validation checks:

```bash
lexictl validate
```

This runs 13 consistency checks across your library and reports issues grouped by severity (error, warning, info).

## Next Steps

With Lexibrary initialized and your design files generated, you can:

- **Learn how it works** -- Read [How It Works](how-it-works.md) for a conceptual overview of the artifact lifecycle and change detection.
- **Understand the output** -- Read [Library Structure](library-structure.md) for a detailed breakdown of everything in `.lexibrary/`.
- **Configure it** -- Read [Configuration](configuration.md) for the full `config.yaml` reference.
- **Set up CI** -- Read [CI Integration](ci-integration.md) for git hooks and CI pipeline recipes.
- **Explore the CLI** -- Read [CLI Reference](cli-reference.md) for every command, flag, and argument.
