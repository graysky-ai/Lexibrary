# Plan: Rename `lexibrarian` to `lexibrary`

Reserve "Lexibrarian" for the future UI wrapper. This CLI/library project becomes
"Lexibrary" everywhere (CLIs stay `lexi` and `lexictl`).

## Scope

| Category | Files | Notes |
|---|---|---|
| Python source (`src/`) | ~77 | Imports, string literals, comments |
| Python tests (`tests/`) | ~86 | Imports, assertions |
| Blueprints (`blueprints/`) | ~100 | Paths in content + directory tree |
| OpenSpec (`openspec/`) | ~185 | Spec text |
| Plans (`plans/`) | ~20 | Plan text |
| Config (`pyproject.toml`, `.gitignore`, `generators.baml`) | 3 | Build system, ignore patterns |
| CLAUDE.md | 1 | Project instructions |
| Workspace file | 1 | `Lexibrarian.code-workspace` filename |
| **Total** | **~470** | |

Two case variants to replace:
- `lexibrarian` (lowercase) → `lexibrary` — Python package name, imports, paths
- `Lexibrarian` (title case) → `Lexibrary` — display/branding text

**No double-replacement risk**: neither source string is a substring of the target,
and neither is a substring of already-correct references like `LexibraryConfig` or
`.lexibrary/`.

---

## Decision: Daemon dotfiles

Currently three daemon runtime files use `.lexibrarian*` names:
- `.lexibrarian.log`
- `.lexibrarian.pid`
- `.lexibrarian_cache.json`

The config directory is already `.lexibrary/`. A naive rename would produce
`.lexibrary.log` sitting next to `.lexibrary/` — confusing.

**Options:**

| Option | Example | Pros | Cons |
|---|---|---|---|
| **A) Move into `.lexibrary/`** | `.lexibrary/daemon.log`, `.lexibrary/daemon.pid` | Clean namespace, everything in one place | Daemon files mixed with index data |
| **B) Prefix with `-daemon`** | `.lexibrary-daemon.log` | Clear separation, no collision | More dotfiles in root |
| **C) Leave as-is** | `.lexibrarian.log` (unchanged) | Zero risk | Inconsistent branding |

**Decision: Option A** — daemon files are project artifacts just like the
index. The `.lexibrary/` directory is already gitignored in bulk. This is the
cleanest long-term design.

New daemon file locations:
- `.lexibrarian.log` → `.lexibrary/daemon.log`
- `.lexibrarian.pid` → `.lexibrary/daemon.pid`
- `.lexibrarian_cache.json` → `.lexibrary/cache.json`

---

## Safety strategy

### Why this can't be incremental

Renaming `src/lexibrarian/` to `src/lexibrary/` breaks **every import** instantly.
There is no way to do a gradual migration — the directory rename and all import
updates must land in a single commit. Python has no built-in re-export/alias
mechanism for package directories.

### How we stay safe

1. **Clean baseline**: Commit all current work, confirm tests pass.
2. **Dedicated branch**: `rename/lexibrarian-to-lexibrary` — main stays untouched.
3. **Atomic core rename**: Directory moves + all code changes in one commit.
4. **Test after every phase**: Run full suite before committing each phase.
5. **Documentation separate**: Markdown changes can't break tests, committed separately.
6. **Rollback plan**: If anything goes wrong, `git checkout main` restores everything.

---

## Phases

### Phase 0: Pre-flight

- [x] Commit all uncommitted work on `main` (checkpoint)
- [x] Run `uv run pytest` — confirm green baseline (1853 passed)
- [x] Run `uv run ruff check src/ tests/` — confirm clean
- [x] Run `uv run mypy src/` — confirm clean (125 source files)
- [x] Create branch: `git checkout -b rename/lexibrarian-to-lexibrary`

### Phase 1: Core package rename (single atomic commit)

This is the critical phase. Everything here happens before a single commit.

**Step 1.1 — Directory renames**
```bash
git mv src/lexibrarian src/lexibrary
git mv blueprints/src/lexibrarian blueprints/src/lexibrary
```

**Step 1.2 — Clean caches**
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm -rf .mypy_cache
```

**Step 1.3 — Python imports and package references**

Replace in all `.py` files under `src/` and `tests/`:
```
lexibrarian.  →  lexibrary.     (dotted module paths)
lexibrarian/  →  lexibrary/     (path strings in code)
"lexibrarian" →  "lexibrary"    (standalone string refs)
```

Use `sed` or scripted replacement. The key patterns:
- `from lexibrarian.` → `from lexibrary.`
- `import lexibrarian.` → `import lexibrary.`
- `import lexibrarian` → `import lexibrary` (bare import)
- `"lexibrarian"` in string literals
- `lexibrarian` in comments

A blanket `s/lexibrarian/lexibrary/g` on `.py` files is safe because:
- No `.py` file contains `lexibrary` + `rian` as separate tokens
- `LexibraryConfig` etc. don't contain the substring `lexibrarian`

**Step 1.4 — Title-case replacement in Python files**

Replace `Lexibrarian` → `Lexibrary` in all `.py` files. This catches:
- Display strings: `"Lexibrarian library"`, `"Lexibrarian-specific"`
- Comments: `# Lexibrarian project configuration`

**Step 1.5 — pyproject.toml** (7 lines)

| Line | Before | After |
|---|---|---|
| 44 | `lexi = "lexibrarian.cli:lexi_app"` | `lexi = "lexibrary.cli:lexi_app"` |
| 45 | `lexictl = "lexibrarian.cli:lexictl_app"` | `lexictl = "lexibrary.cli:lexictl_app"` |
| 52 | `packages = ["src/lexibrarian"]` | `packages = ["src/lexibrary"]` |
| 63 | `module = "lexibrarian.baml_client.*"` | `module = "lexibrary.baml_client.*"` |
| 72 | `module = "lexibrarian.crawler.engine"` | `module = "lexibrary.crawler.engine"` |
| 87 | `exclude = ["src/lexibrarian/baml_client/"]` | `exclude = ["src/lexibrary/baml_client/"]` |
| 105 | `"src/lexibrarian/crawler/engine.py"` | `"src/lexibrary/crawler/engine.py"` |

**Step 1.6 — baml_src/generators.baml**
```
output_dir "../src/lexibrarian"  →  output_dir "../src/lexibrary"
```

**Step 1.7 — CLAUDE.md**
```
src/lexibrarian/  →  src/lexibrary/
--cov=lexibrarian  →  --cov=lexibrary
```

**Step 1.8 — .gitignore**

Remove stale daemon dotfile entries (now inside `.lexibrary/`, already bulk-ignored):
- Remove `.lexibrarian_cache.json` line
- Remove `.lexibrarian.log` line

Also:
- `# Lexibrarian-specific` → `# Lexibrary-specific`
- `Lexibrarian.code-workspace` → `Lexibrary.code-workspace`

**Step 1.9 — Daemon dotfile constants (Option A: move into `.lexibrary/`)**

These need manual edits — the blanket `s/lexibrarian/lexibrary/g` will update the
substring but the filenames/paths themselves are changing structure:

| File | Old | New |
|---|---|---|
| `src/lexibrary/daemon/logging.py` | `_LOG_FILENAME = ".lexibrarian.log"` | `_LOG_FILENAME = "daemon.log"` + path now under `.lexibrary/` |
| `src/lexibrary/daemon/service.py` | `_PID_FILENAME = ".lexibrarian.pid"` | `_PID_FILENAME = "daemon.pid"` + path now under `.lexibrary/` |
| `src/lexibrary/daemon/watcher.py` | `_INTERNAL_FILES` frozenset with 3 dotfiles | Update to new paths inside `.lexibrary/` |
| `src/lexibrary/init/scaffolder.py` | `_DAEMON_GITIGNORE_PATTERNS` list | Remove daemon entries (`.lexibrary/` is already bulk-ignored) |
| `src/lexibrary/hooks/post_commit.py` | `>> .lexibrarian.log` in hook template | `>> .lexibrary/daemon.log` |
| `src/lexibrary/cli/lexictl_app.py` | `project_root / ".lexibrarian.pid"` | `project_root / ".lexibrary" / "daemon.pid"` |

**Important**: These daemon files now assume `.lexibrary/` exists at runtime.
The daemon/logging setup should `mkdir -p` the directory if it doesn't exist.
Check that `lexi init` creates `.lexibrary/` before the daemon can write to it
(it already does — `scaffolder.py` creates the directory).

**Step 1.10 — Reinstall and test**
```bash
uv sync
uv run pytest --cov=lexibrary
uv run ruff check src/ tests/
uv run mypy src/
```

**Step 1.11 — Commit**
```bash
git add -A
git commit -m "Rename Python package lexibrarian → lexibrary"
```

### Phase 2: Documentation rename (separate commit)

Replace both `lexibrarian` → `lexibrary` and `Lexibrarian` → `Lexibrary` in:
- All `.md` files under `blueprints/`
- All `.md` files under `openspec/`
- All `.md` files under `plans/`
- `lexibrary-overview.md` (check for any stale refs)

This phase cannot break tests. Blanket replacement is safe for the same substring
reasons as Phase 1.

```bash
git add -A
git commit -m "Update documentation: Lexibrarian → Lexibrary"
```

### Phase 3: Remaining file renames

- [ ] `mv Lexibrarian.code-workspace Lexibrary.code-workspace`
- [ ] Regenerate BAML client: `uv run baml generate` (updates `inlinedbaml.py`)
- [ ] Run tests one final time
- [ ] Commit

### Phase 4: Merge

- [ ] Final full test suite: `uv run pytest --cov=lexibrary`
- [ ] Lint + type check pass
- [ ] `git checkout main && git merge rename/lexibrarian-to-lexibrary`
- [ ] Delete branch

---

## Verification checklist (post-merge)

- [ ] `uv run lexi --help` works
- [ ] `uv run lexictl --help` works
- [ ] `uv run pytest --cov=lexibrary` all green
- [ ] `uv run ruff check src/ tests/` clean
- [ ] `uv run mypy src/` clean
- [ ] `grep -ri "lexibrarian" src/ tests/ pyproject.toml CLAUDE.md .gitignore` returns nothing
- [ ] `grep -ri "lexibrarian" blueprints/ openspec/ plans/` returns nothing
  (except this plan file and any deliberate historical references)
- [ ] `uv run lexi init` in a temp directory creates `.lexibrary/` correctly
- [ ] Blueprint paths match source paths (`blueprints/src/lexibrary/` mirrors `src/lexibrary/`)

---

## Risk register

| Risk | Mitigation |
|---|---|
| Missed import breaks runtime | Full test suite after Phase 1 |
| `uv sync` fails with new package path | Verify `packages = ["src/lexibrary"]` before sync |
| BAML codegen breaks | Regenerate in Phase 3, test again |
| Daemon dotfile collision | Decided upfront, tested explicitly |
| Stale `.pyc` / `.mypy_cache` | Clean in Step 1.2 |
| Merge conflicts if other work lands on main | Branch from latest main, merge promptly |
| Display strings still say "Lexibrarian" | Grep verification in checklist |

---

## What stays unchanged

- CLI names: `lexi`, `lexictl` (no change)
- Config directory: `.lexibrary/` (already correct)
- Python symbols: `LexibraryConfig`, `LexibraryNotFoundError`, etc. (already correct)
- Distribution name in pyproject.toml: `name = "lexibrary"` (already correct)
- Project root directory name on disk: `~/AI_Projects/Lexibrarian/` (optional, cosmetic)
