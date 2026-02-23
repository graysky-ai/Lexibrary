## 1. Concept Filtering Options

- [ ] 1.1 Add `--tag` option (repeatable `list[str]`) to the `concepts` command in `src/lexibrary/cli/lexi_app.py`
- [ ] 1.2 Add `--status` option (choice of `active`, `draft`, `deprecated`) to the `concepts` command in `src/lexibrary/cli/lexi_app.py`
- [ ] 1.3 Add `--all` boolean flag to the `concepts` command in `src/lexibrary/cli/lexi_app.py`
- [ ] 1.4 Implement filtering logic: start from full result set, apply `--tag` filter via `ConceptIndex.by_tag()`, apply `--status` filter inline, exclude deprecated by default unless `--all` or `--status deprecated` is specified
- [ ] 1.5 Ensure positional `topic` search combines with `--tag`/`--status` using AND logic (intersect result sets)

## 2. Agent Help Command

- [ ] 2.1 Register `help` as a `@lexi_app.command()` in `src/lexibrary/cli/lexi_app.py` — must not call `require_project_root()`
- [ ] 2.2 Implement help output using Rich panels covering: command groups (lookup & navigation, concepts & knowledge, stack Q&A, indexing), common workflows (at least 3), and navigation tips
- [ ] 2.3 Ensure all agent-facing commands are referenced: `lookup`, `index`, `describe`, `concepts`, `concept new`, `concept link`, `stack` subcommands, `search`, and `help`

## 3. Tests

- [ ] 3.1 Add tests for `lexi concepts --tag <t>` filtering in `tests/test_cli/` — verify tag filter returns correct subset, multiple tags use AND logic
- [ ] 3.2 Add tests for `lexi concepts --status <s>` filtering — verify each status value filters correctly, `--status deprecated` overrides default exclusion
- [ ] 3.3 Add tests for `lexi concepts --all` flag — verify deprecated concepts are included when flag is set
- [ ] 3.4 Add tests for default deprecated exclusion — verify bare `lexi concepts` hides deprecated concepts
- [ ] 3.5 Add tests for combined filters — verify `topic` + `--tag` + `--status` narrow with AND logic
- [ ] 3.6 Add tests for `lexi help` command — verify it succeeds without a project root and outputs expected sections
- [ ] 3.7 Run full test suite (`uv run pytest`) and lint (`uv run ruff check`) to confirm no regressions

## 4. Blueprint Updates

- [ ] 4.1 Update `blueprints/src/lexibrary/cli/lexi_app.md` to document the new `help` command and the `--tag`, `--status`, `--all` options on `concepts`

## 5. Backlog Cleanup

- [ ] 5.1 Update `plans/BACKLOG.md`: mark `lexi help`, `lexi concepts --tag`, `lexi concepts --status`, and `lexi concepts --all` as `resolved` with reference to this change
