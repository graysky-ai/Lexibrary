# IWH Issues — Session 2: Audit & Remaining Work

## Audit Summary

The previous agent completed TG1–TG4 and most of TG5. All new code (27 new tests) passes. However, 2 pre-existing tests are now **broken** by rule content changes, TG5 has unfinished items, and TG6 was never started.

---

## Issues Found

### BUG-1: Two pre-existing rule tests now fail

The previous agent changed the rule content in `base.py` (replacing manual `.iwh` file references with CLI commands) but did not update two pre-existing tests that assert on the old content.

**Failing tests:**

1. `tests/test_init/test_rules/test_base.py::TestGetCoreRules::test_iwh_read_act_delete` (line 105)
   - Asserts `"delete" in get_core_rules().lower()`
   - The rules now say "consume the signal" instead of "delete"
   - **Fix:** Update assertion to check for `"consume"` instead of `"delete"`, or add "delete" back to the rules text in a contextually appropriate way

2. `tests/test_init/test_rules/test_base.py::TestGetOrientSkillContent::test_contains_iwh_check` (line 141)
   - Asserts `".iwh" in get_orient_skill_content()`
   - The orient skill now says `lexi iwh list` / `lexi iwh read` instead of referencing `.iwh` files directly
   - **Fix:** Update assertion to check for `"lexi iwh"` or `"IWH"` instead of `".iwh"`

### BUG-2: `# type: ignore[arg-type]` on write_iwh call (minor)

`src/lexibrary/cli/lexi_app.py:913` — `scope` is a `str` but `write_iwh()` expects `IWHScope` (a `Literal["warning", "incomplete", "blocked"]`). The runtime works because the value is validated beforehand, but mypy will flag it.

**Fix:** Cast the scope: `scope=scope  # type: ignore[arg-type]` → `scope=cast(IWHScope, scope)` (import `cast` from `typing`). Or convert after validation: `validated_scope: IWHScope = scope  # type: ignore[assignment]`. The simplest fix is to keep the ignore but add a comment explaining why.

### STYLE-1: MonkeyPatch usage in TestIWH (test_lexi.py)

Tests in `TestIWH` (lines 2309–2470) instantiate `pytest.MonkeyPatch()` directly instead of using the `monkeypatch` fixture. In `test_iwh_write_creates_signal` (line 2312), the fixture parameter `monkeypatch` is shadowed by a new instance, and the first test never calls `undo()`. This works but is fragile and non-idiomatic.

**Fix (optional):** Refactor to use the `monkeypatch` fixture parameter consistently. Low priority — tests pass and cleanup is automatic when the fixture is used.

---

## Remaining Work

### TG5 (Partially Done): Docs & Rule Alignment — Finish

**Status:** Rules and docs updated. Three items remain.

#### TG5-A: Delete stale root files

Both files still exist and should be deleted:

- `TODO.md` — contains only "Add in i-was-here changes" (obsolete)
- `i-was-here.md` — superseded by `docs/agent/iwh.md` and the overview spec

```bash
git rm TODO.md i-was-here.md
```

#### TG5-B: Fix 2 broken pre-existing tests (BUG-1 above)

Edit `tests/test_init/test_rules/test_base.py`:

1. **`test_iwh_read_act_delete`** (line 105–109): The rules now instruct agents to "consume" signals via `lexi iwh read`, not to manually "delete" `.iwh` files. Update the assertion:
   ```python
   def test_iwh_read_act_delete(self) -> None:
       """Core rules instruct agents to read and consume .iwh signals."""
       result = get_core_rules().lower()
       assert "read" in result
       assert "consume" in result
   ```

2. **`test_contains_iwh_check`** (line 141–144): The orient skill now references CLI commands, not raw file paths. Update the assertion:
   ```python
   def test_contains_iwh_check(self) -> None:
       """Orient skill instructs checking for IWH signals."""
       result = get_orient_skill_content()
       assert "lexi iwh list" in result
   ```

#### TG5-C: Add 2 new IWH-specific test assertions

Add to `tests/test_init/test_rules/test_base.py` in `TestGetCoreRules`:

```python
def test_core_rules_references_lexi_iwh_write(self) -> None:
    """Core rules reference lexi iwh write for leaving work incomplete."""
    result = get_core_rules()
    assert "lexi iwh write" in result

def test_core_rules_references_lexi_iwh_list(self) -> None:
    """Core rules reference lexi iwh list for checking signals."""
    result = get_core_rules()
    assert "lexi iwh list" in result
```

Add to `TestGetOrientSkillContent`:

```python
def test_orient_skill_does_not_reference_ls_iwh(self) -> None:
    """Orient skill does NOT contain raw 'ls .iwh' instructions."""
    result = get_orient_skill_content()
    assert "ls .iwh" not in result
    assert "ls .lexibrary" not in result
```

---

### TG6 (Not Started): Tracking Document Cleanup

#### TG6-A: Update `plans/analysis-hooks-skills-commands-rules.md`

1. **C3** (line 472): Change status from `**Open**` to `**RESOLVED** by iwh-gap-fix`
2. **Appendix A** (lines 534–535): Change `lexi iwh write` and `lexi iwh read` from `**MISSING (referenced in rules)**` to `Done`
3. **Appendix C** (line 586): Change status from `**Open**` to `**RESOLVED** by iwh-gap-fix`

#### TG6-B: Update `plans/BACKLOG.md`

Add a resolved entry to the CLI Gaps table:

```markdown
| critical | resolved | `lexi iwh write/read/list`, `lexictl iwh clean` | Delivered via IWH gap fix. `find_all_iwh()` discovery, archivist IWH awareness, docs/rules aligned. |
```

#### TG6-C: Update blueprints (4 files)

These blueprints need to reflect the new code:

1. **`blueprints/src/lexibrary/iwh/reader.md`** — Add documentation for `find_all_iwh()`: signature, behavior (walks `.lexibrary/` via `rglob`, reverses mirror paths, skips unparseable files, returns sorted list).

2. **`blueprints/src/lexibrary/cli/lexi_app.md`** — Add IWH subgroup section documenting:
   - `iwh_app` Typer subgroup registered as `lexi iwh`
   - `lexi iwh write [directory]` — flags: `--scope/-s`, `--body/-b`, `--author`; config-disabled exit; scope validation; uses `iwh_path()` + `write_iwh()`
   - `lexi iwh read [directory]` — flags: `--peek`; config-disabled exit; defaults to consume, peek uses `read_iwh()`
   - `lexi iwh list` — calls `find_all_iwh()`, Rich table with age calculation, config-disabled exit
   - Updated `lexi help` output includes IWH Signals section

3. **`blueprints/src/lexibrary/cli/lexictl_app.md`** — Add IWH subgroup section documenting:
   - `iwh_ctl_app` Typer subgroup registered as `lexictl iwh`
   - `lexictl iwh clean` — flags: `--older-than N`; uses `find_all_iwh()` for discovery, deletes matching `.iwh` files, reports count

4. **`blueprints/src/lexibrary/archivist/pipeline.md`** — Document IWH awareness in `update_file()`:
   - Check added between scope check (step 1) and hash computation (step 2)
   - Only when `config.iwh.enabled` is True
   - `blocked` → log warning + skip (return `FileResult(change=UNCHANGED)`)
   - `incomplete` → log info + proceed
   - `warning` → no special handling
   - Uses `read_iwh()` (non-consuming) — archivist doesn't delete signals
   - Imports aliased as `_iwh_path` to avoid collision

---

### Final: Run Full Test Suite + Lint + Type Check

After all fixes, run:

```bash
# Full test suite
uv run pytest --cov=lexibrary

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

---

## Task Checklist

- [ ] TG5-A: Delete `TODO.md` and `i-was-here.md`
- [ ] TG5-B: Fix 2 broken tests in `test_base.py` (`test_iwh_read_act_delete`, `test_contains_iwh_check`)
- [ ] TG5-C: Add 3 new IWH assertions to `test_base.py`
- [ ] TG6-A: Update `plans/analysis-hooks-skills-commands-rules.md` (C3 resolved, Appendix A/C)
- [ ] TG6-B: Add resolved entry to `plans/BACKLOG.md`
- [ ] TG6-C: Update 4 blueprint files (reader.md, lexi_app.md, lexictl_app.md, pipeline.md)
- [ ] (Optional) BUG-2: Fix `type: ignore` in `lexi_app.py:913`
- [ ] (Optional) STYLE-1: Refactor `TestIWH` monkeypatch usage
- [ ] Run full test suite — all tests must pass (currently 2 failures)
- [ ] Run `ruff check src/ tests/`
- [ ] Run `mypy src/`

## Key File Reference

| File | Status | Action Needed |
|------|--------|---------------|
| `src/lexibrary/iwh/reader.py` | Done | — |
| `src/lexibrary/iwh/__init__.py` | Done | — |
| `src/lexibrary/cli/lexi_app.py` | Done | Optional: fix type ignore |
| `src/lexibrary/cli/lexictl_app.py` | Done | — |
| `src/lexibrary/archivist/pipeline.py` | Done | — |
| `src/lexibrary/init/rules/base.py` | Done | — |
| `docs/agent/iwh.md` | Done | — |
| `docs/agent/orientation.md` | Done | — |
| `tests/test_iwh/test_find_all.py` | Done | — |
| `tests/test_cli/test_lexi.py` (TestIWH) | Done | Optional: monkeypatch cleanup |
| `tests/test_cli/test_lexictl.py` (TestIWHClean) | Done | — |
| `tests/test_archivist/test_pipeline.py` (TestIWHAwareness) | Done | — |
| `tests/test_init/test_rules/test_base.py` | **Needs fix** | Fix 2 broken tests + add 3 new |
| `TODO.md` | **Delete** | Stale file |
| `i-was-here.md` | **Delete** | Superseded |
| `plans/analysis-hooks-skills-commands-rules.md` | **Needs update** | Mark C3, Appendix A/C resolved |
| `plans/BACKLOG.md` | **Needs update** | Add resolved IWH entry |
| `blueprints/src/lexibrary/iwh/reader.md` | **Needs update** | Document find_all_iwh() |
| `blueprints/src/lexibrary/cli/lexi_app.md` | **Needs update** | Document IWH subgroup |
| `blueprints/src/lexibrary/cli/lexictl_app.md` | **Needs update** | Document IWH subgroup |
| `blueprints/src/lexibrary/archivist/pipeline.md` | **Needs update** | Document IWH awareness |
