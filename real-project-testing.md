# Testing Lexibrary on Real Projects

## Setup

You're running from source, so no separate install is needed. All commands use `uv run` from the Lexibrarian project directory.

Two CLIs are involved:
- **`lexi`** — agent-facing commands (index, lookup, search, concepts, stack). Run from the Lexibrarian project dir with an absolute path to the target repo.
- **`lexictl`** — maintenance commands (init, update, validate, status). Run from **inside** the target repo (it uses your cwd).

Shell aliases for convenience (add to `~/.zshrc`):

```bash
alias lexi="cd ~/AI_Projects/Lexibrarian && uv run lexi"
alias lexictl="cd ~/AI_Projects/Lexibrarian && uv run lexictl"
```

Or use inline subshells without aliases:

```bash
(cd ~/AI_Projects/Lexibrarian && uv run lexi index /tmp/test-repo)
(cd /tmp/test-repo && uv run --project ~/AI_Projects/Lexibrarian lexictl init)
```

## Quick Start

### 1. Clone a test repo into /tmp

```bash
git clone https://github.com/<owner>/<repo> /tmp/test-repo
```

Using `/tmp` keeps things disposable — macOS cleans it periodically, and you can `rm -rf` it anytime.

### 2. Initialize Lexibrary in the test repo

`lexictl init` must be run **from inside** the target repo (it uses your working directory):

```bash
cd /tmp/test-repo
uv run --project ~/AI_Projects/Lexibrarian lexictl init
```

This creates `.lexibrary/` with a `config.yaml`, agent rules, and `.lexignore`.

### 3. Index the project

Run from the Lexibrarian directory, passing the absolute path to the test repo:

```bash
cd ~/AI_Projects/Lexibrarian

# Index the root directory only
uv run lexi index /tmp/test-repo

# Index recursively (all subdirectories)
uv run lexi index -r /tmp/test-repo
```

This creates `.aindex` files inside `/tmp/test-repo/.lexibrary/`.

### 4. Explore the results

```bash
# Look up design info for a specific file
uv run lexi lookup /tmp/test-repo/src/main.py

# Search across indexed content
uv run lexi search "authentication"
uv run lexi search --tag auth
uv run lexi search --scope /tmp/test-repo/src "config"

# List/search concepts
uv run lexi concepts
uv run lexi concepts "error handling"

# Update a directory's billboard description
uv run lexi describe /tmp/test-repo/src "Core application source"
```

### 5. Concepts and Stack (manual knowledge layer)

```bash
# Create a concept file
uv run lexi concept new "dependency injection"

# Link a concept to a source file's design file
uv run lexi concept link /tmp/test-repo/src/container.py

# Post a Stack Q&A entry
uv run lexi stack post

# Search/browse Stack posts
uv run lexi stack list
uv run lexi stack search "how does routing work"
```

## Available Commands Reference

### `lexi` — agent-facing commands

| Command | Description |
|---------|-------------|
| `lexi index [DIR]` | Generate `.aindex` files (`-r` for recursive) |
| `lexi lookup FILE` | Return design file for a source file |
| `lexi search [QUERY]` | Search concepts, design files, Stack posts |
| `lexi describe DIR DESC` | Update billboard description in `.aindex` |
| `lexi concepts [TOPIC]` | List or search concept files |
| `lexi concept new TOPIC` | Create a new concept file |
| `lexi concept link FILE` | Add wikilink to a file's design file |
| `lexi stack post` | Create a new Stack Q&A post |
| `lexi stack search QUERY` | Search Stack posts |
| `lexi stack list` | List Stack posts |
| `lexi stack view ID` | View a Stack post |
| `lexi stack answer ID` | Add answer to a Stack post |
| `lexi stack vote ID` | Vote on a post or answer |
| `lexi stack accept ID` | Accept an answer |

### `lexictl` — maintenance commands (run from inside target repo)

| Command | Description |
|---------|-------------|
| `lexictl init` | Initialize Lexibrary in the current directory (runs setup wizard) |
| `lexictl init --defaults` | Initialize with all detected defaults (non-interactive) |
| `lexictl update` | Regenerate design files for the whole project |
| `lexictl update PATH` | Regenerate design file for a single file or directory |
| `lexictl update --changed-only FILE...` | Update only specified files (for git hooks/CI) |
| `lexictl validate` | Run consistency checks on the library |
| `lexictl status` | Show library health and staleness summary |
| `lexictl setup --update` | Update agent environment rule files |
| `lexictl setup --hooks` | Install git post-commit hook for automatic updates |
| `lexictl sweep` | Run a one-shot library update sweep |
| `lexictl sweep --watch` | Run periodic sweeps in the foreground |

## Handling Ongoing Development

Since you run from source, **every code change takes effect immediately** — no reinstall needed.

### What this means in practice

- Fix a bug in lexibrary -> next `uv run lexi` call uses the fix
- Break something -> next call might fail or produce bad output
- Only the test repo in `/tmp` is affected, never your real projects

### Safe workflow

1. **Before a test session:** make sure your working tree is clean or on a known-good commit
2. **During development:** feel free to re-run commands against the test repo — it's throwaway
3. **If something breaks the index:** just delete the cloned repo and start fresh
4. **To compare before/after a change:**
   ```bash
   # Clone two copies
   git clone https://github.com/<owner>/<repo> /tmp/test-before
   git clone https://github.com/<owner>/<repo> /tmp/test-after

   # Init and index "before" on current commit
   (cd /tmp/test-before && uv run --project ~/AI_Projects/Lexibrarian lexictl init --defaults)
   uv run lexi index -r /tmp/test-before

   # Make your changes to lexibrary, then init and index "after"
   (cd /tmp/test-after && uv run --project ~/AI_Projects/Lexibrarian lexictl init --defaults)
   uv run lexi index -r /tmp/test-after

   # Compare .aindex files (stored inside .lexibrary/)
   diff -r /tmp/test-before/.lexibrary /tmp/test-after/.lexibrary
   ```

### Good test repos

Pick repos that vary in size and language to stress different scenarios:

- **Small Python:** a CLI tool or library with ~20 files
- **Medium multi-language:** a web app with frontend + backend
- **Large monorepo:** to test performance and recursive indexing
- **Your own projects:** repos you know well, so you can judge output quality

## Cleanup

```bash
rm -rf /tmp/test-repo
```

That's it. Lexibrary only writes inside the target directory (`.lexibrary/` contains config, agent rules, and all `.aindex` files), so deleting the clone removes everything.
