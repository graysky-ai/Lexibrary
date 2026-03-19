# Lexibrary Convention Artifact Implementation Analysis

**Purpose:** Compare existing convention pattern against proposed playbooks plan to ensure implementation consistency.

**Date:** 2026-03-19  
**Scope:** Detailed architectural and API analysis of 12 key files

---

## 1. Artifact Models

### File: `src/lexibrary/artifacts/convention.py`

**Pydantic Models:**

```python
class ConventionFileFrontmatter(BaseModel):
    title: str
    scope: str = "project"                              # Directory path OR "project"
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent", "config"] = "user"
    priority: int = 0                                   # Determines sort order
    aliases: list[str] = []
    deprecated_at: datetime | None = None

class ConventionFile(BaseModel):
    frontmatter: ConventionFileFrontmatter
    body: str = ""
    rule: str = ""                                      # Extracted first paragraph
    file_path: Path | None = None
    
    @property
    def name(self) -> str: ...
    @property
    def scope(self) -> str: ...
```

**Slug Helpers:**

- `convention_slug(title: str) -> str`
  - Delegates to `slugify()` from `artifacts/slugs.py`
  - Lowers, replaces non-alphanumeric with hyphens, collapses consecutive hyphens
  - Max 60 char slug with word-boundary truncation

- `convention_file_path(title: str, conventions_dir: Path) -> Path`
  - Returns `conventions_dir / "<slug>.md"`
  - Appends numeric suffix (`-2`, `-3`, ...) if path exists

**Comparison to Playbooks Plan:**

✓ Models follow exact same structure (Frontmatter + File wrapper)  
✓ Slug helper delegation established (reuse `slugify()`)  
✓ Collision-append naming confirmed  
✗ Playbooks add: `trigger_files`, `actor`, `estimated_minutes`, `last_verified`, `superseded_by`  
✗ Playbooks replace `rule` with `overview` (same purpose: first paragraph)  
✓ Same status enum: draft/active/deprecated  
✓ Same source enum: user/agent/config  

---

## 2. Parser Implementation

### File: `src/lexibrary/conventions/parser.py`

**Key Functions:**

```python
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

def extract_rule(body: str) -> str:
    """Extract first paragraph (text before first blank line)."""
    stripped = body.strip()
    if not stripped:
        return ""
    parts = re.split(r"\n\s*\n", stripped, maxsplit=1)
    return parts[0].strip()

def parse_convention_file(path: Path) -> ConventionFile | None:
    """Parse a convention file into a ConventionFile model.
    
    Returns None if:
    - File doesn't exist
    - No YAML frontmatter found
    - Frontmatter fails validation
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None
    
    try:
        data = yaml.safe_load(fm_match.group(1))
        if not isinstance(data, dict):
            return None
        frontmatter = ConventionFileFrontmatter(**data)
    except (yaml.YAMLError, TypeError, ValueError):
        logger.debug("Failed to parse convention frontmatter in %s", path)
        return None
    
    body = text[fm_match.end() :]
    rule = extract_rule(body)
    
    return ConventionFile(
        frontmatter=frontmatter,
        body=body,
        rule=rule,
        file_path=path,
    )
```

**Error Handling:** Silent return None on missing/invalid; debug logging on parse failure

**Comparison to Playbooks Plan:**

✓ Template exactly matches playbooks `parser.py` pattern  
✓ Frontmatter regex identical  
✓ `extract_rule()` ↔ `extract_overview()` (same implementation)  
✓ Same error handling: None on missing/invalid, debug logging  
✓ Same body trimming logic  

---

## 3. Serializer Implementation

### File: `src/lexibrary/conventions/serializer.py`

**Function Signature:**

```python
def serialize_convention_file(convention: ConventionFile) -> str:
    """Serialize a ConventionFile to markdown with YAML frontmatter.
    
    Produces:
    - `---` delimited YAML frontmatter
    - Blank line after closing `---`
    - Full body text
    - Trailing newline
    """
    fm_data: dict[str, object] = {
        "title": convention.frontmatter.title,
        "scope": convention.frontmatter.scope,
        "tags": convention.frontmatter.tags,
        "status": convention.frontmatter.status,
        "source": convention.frontmatter.source,
        "priority": convention.frontmatter.priority,
    }
    
    if convention.frontmatter.aliases:
        fm_data["aliases"] = convention.frontmatter.aliases
    
    if convention.frontmatter.deprecated_at is not None:
        fm_data["deprecated_at"] = convention.frontmatter.deprecated_at.isoformat()
    
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    
    parts = [f"---\n{fm_str}\n---\n"]
    if convention.body:
        parts.append(convention.body)
    result = "".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    return result
```

**Key Patterns:**

- Optional fields only included when non-empty/non-None (aliases, deprecated_at)
- Datetimes serialized as ISO format strings
- `sort_keys=False` to preserve field order
- Trailing newline enforced

**Comparison to Playbooks Plan:**

✓ Template exactly matches playbooks `serializer.py` pattern  
✓ Optional field inclusion: `if field: fm_data["field"] = value`  
✓ ISO format datetime serialization  
✓ YAML dump preserves insertion order  
✓ Playbooks adds: `last_verified` as date string (not datetime), `trigger_files` as flow list  
✓ Plan mentions YAML comment above title — **not currently implemented in conventions** (future feature)  

---

## 4. Index Class API

### File: `src/lexibrary/conventions/index.py`

**Class Signature:**

```python
class ConventionIndex:
    """In-memory index of convention files with scope-aware retrieval."""
    
    def __init__(self, conventions_dir: Path) -> None:
        self._conventions_dir = conventions_dir
        self.conventions: list[ConventionFile] = []
    
    def load(self) -> None:
        """Scan conventions directory and parse all .md files.
        Malformed files silently skipped."""
        self.conventions = []
        if not self._conventions_dir.is_dir():
            return
        
        for md_path in sorted(self._conventions_dir.glob("*.md")):
            convention = parse_convention_file(md_path)
            if convention is not None:
                self.conventions.append(convention)
    
    # Scope-aware retrieval
    def find_by_scope(self, file_path: str, scope_root: str = ".") -> list[ConventionFile]:
        """Return conventions applicable to file_path, ordered by specificity.
        
        Algorithm:
        1. Build ancestry chain from file's parent up to scope_root
        2. Collect conventions where scope == "project" OR normalized file path
           starts with convention's scope directory (with trailing /)
        3. Order: root-to-leaf (project first, then ., then deeper)
        4. Within scope: priority descending, then title alphabetically
        """
        ...
    
    def find_by_scope_limited(
        self,
        file_path: str,
        scope_root: str = ".",
        limit: int = 5,
    ) -> tuple[list[ConventionFile], int]:
        """Return at most limit conventions for file_path plus total count.
        When truncating, most-specific (leaf-ward) conventions kept."""
        all_conventions = self.find_by_scope(file_path, scope_root)
        total = len(all_conventions)
        if limit <= 0:
            return [], total
        if total <= limit:
            return all_conventions, total
        return all_conventions[-limit:], total  # Keep tail (most-specific)
    
    # Search and filter
    def search(self, query: str) -> list[ConventionFile]:
        """Search by case-insensitive substring against title, aliases, body, tags."""
        needle = query.strip().lower()
        if not needle:
            return []
        matches: dict[str, ConventionFile] = {}
        for conv in self.conventions:
            if _matches_convention(conv, needle):
                matches[conv.frontmatter.title] = conv
        return [matches[k] for k in sorted(matches.keys())]
    
    def by_tag(self, tag: str) -> list[ConventionFile]:
        """Return all conventions with tag (case-insensitive)."""
        needle = tag.strip().lower()
        results: dict[str, ConventionFile] = {}
        for conv in self.conventions:
            for t in conv.frontmatter.tags:
                if t.strip().lower() == needle:
                    results[conv.frontmatter.title] = conv
                    break
        return [results[k] for k in sorted(results.keys())]
    
    def by_status(self, status: str) -> list[ConventionFile]:
        """Return all conventions with given status."""
        norm = status.strip().lower()
        results: dict[str, ConventionFile] = {}
        for conv in self.conventions:
            if conv.frontmatter.status == norm:
                results[conv.frontmatter.title] = conv
        return [results[k] for k in sorted(results.keys())]
    
    def names(self) -> list[str]:
        """Return sorted list of all convention titles."""
        return sorted(c.frontmatter.title for c in self.conventions)
    
    def __len__(self) -> int:
        return len(self.conventions)
```

**Search Implementation Details:**

- `search()` uses dict deduplication by title (dict insertion order preserved)
- Results always sorted alphabetically by title
- **No `__iter__`** (consistent with playbooks plan)

**Comparison to Playbooks Plan:**

✓ Template exactly matches playbooks `index.py` pattern  
✓ Same public methods: `load()`, `find()` (via search), `search()`, `by_tag()`, `by_status()`, `names()`, `__len__()`  
✓ Playbooks add: `by_trigger_file(file_path: str) -> list[PlaybookFile]` (pathspec-based glob matching)  
✓ Same in-memory approach (no persistence)  
✓ Same sorting/ordering logic (by tag, status, title)  

---

## 5. Module Re-exports

### File: `src/lexibrary/conventions/__init__.py`

```python
from lexibrary.conventions.index import ConventionIndex
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.conventions.serializer import serialize_convention_file

__all__ = [
    "ConventionIndex",
    "parse_convention_file",
    "serialize_convention_file",
]
```

**Comparison to Playbooks Plan:**

✓ Playbooks follow same pattern: re-export main entry points  
✓ Add `PlaybookIndex` to playbooks `__init__.py`  

---

## 6. CLI Commands

### File: `src/lexibrary/cli/conventions.py`

**Command Structure:**

```python
convention_app = typer.Typer(
    help="Convention lifecycle management commands.",
    rich_markup_mode=None
)

@convention_app.command("new")
def convention_new(
    scope_value: str,                   # --scope
    body: str,                          # --body (first paragraph is the rule)
    tag: list[str] | None,              # --tag (repeatable)
    title: str | None,                  # --title (derived from body if omitted)
    source: str,                        # --source (user|agent, default=user)
    alias: list[str] | None,            # --alias (repeatable)
) -> None:
    """Create a convention file and return its path. Status defaults to draft."""
    # Derives title from body if not provided (first 60 chars)
    resolved_title = title if title else body[:60].strip()
    
    # Checks for duplicate slug
    # Sets defaults based on source:
    #   - source=agent: status=draft, priority=-1
    #   - source=user: status=active, priority=0

@convention_app.command("approve")
def convention_approve(slug: str) -> None:
    """Promote draft to active status."""
    # Parses convention, updates status, re-serializes

@convention_app.command("deprecate")
def convention_deprecate(slug: str) -> None:
    """Set status to deprecated, set deprecated_at timestamp."""

@convention_app.command("comment")
def convention_comment(slug: str, body: str) -> None:
    """Append a comment via lifecycle comment adapter."""
```

**Command Patterns:**

- All use `require_project_root()` to find `.lexibrary/`
- Slug-based file discovery (stem of filename)
- Error handling with `typer.Exit(1)` and context-sensitive messages
- Re-serialization after modifications

**Comparison to Playbooks Plan:**

✓ Template matches playbooks `cli/playbooks.py` pattern  
✓ Same commands planned: new, approve (→ activate), deprecate, comment  
✓ Playbooks add: list, show, edit, verify  
✓ Same slug-based file operations  
✓ Same lifecycle comment integration  
✓ Same defaults/fallbacks  

---

## 7. CLI Registration and Lookup Integration

### File: `src/lexibrary/cli/lexi_app.py` (partial)

**Registration:**

```python
lexi_app.add_typer(convention_app, name="convention")
```

**Lookup Integration Points:**

1. **Directory Lookup** (`_lookup_directory`):
```python
conventions_dir = project_root / ".lexibrary" / "conventions"
convention_index = ConventionIndex(conventions_dir)
convention_index.load()

if len(convention_index) > 0:
    display_limit = config.conventions.lookup_display_limit
    conventions, total_count = convention_index.find_by_scope_limited(
        rel_target,
        scope_root=config.scope_root,
        limit=display_limit,
    )
    if conventions:
        _render_conventions(conventions, total_count, display_limit, rel_target)
```

2. **File Lookup (Brief Mode)**:
```python
convention_index = ConventionIndex(conventions_dir)
convention_index.load()
if len(convention_index) > 0:
    brief_limit = min(config.conventions.lookup_display_limit, 5)
    convs, total = convention_index.find_by_scope_limited(
        rel_target,
        scope_root=config.scope_root,
        limit=brief_limit,
    )
    if convs:
        _render_conventions(convs, total, brief_limit, rel_target)
```

3. **File Lookup (Full Mode)**:
Same as above, using `config.conventions.lookup_display_limit` for display_limit

**Rendering Helper:**

```python
def _render_conventions(
    conventions: Sequence[object],
    total_count: int,
    display_limit: int,
    rel_target: str,
) -> None:
    """Render Applicable Conventions section grouped by scope.
    
    Groups by scope (project-first to deepest), orders by priority desc + title asc.
    Marks [draft] status.
    Shows rule or title as the main text.
    Truncation notice appended if total_count > display_limit.
    """
    info("\n## Applicable Conventions\n")
    
    # Group by scope
    groups: OrderedDict[str, list[ConventionFile]] = OrderedDict()
    for conv in typed_conventions:
        scope = conv.frontmatter.scope
        groups.setdefault(scope, []).append(conv)
    
    for scope, group in groups.items():
        scope_label = scope if scope != "project" else "project"
        info(f"### {scope_label}\n")
        for conv in group:
            draft_marker = " [draft]" if conv.frontmatter.status == "draft" else ""
            rule_text = conv.rule or conv.frontmatter.title
            info(f"- {rule_text}{draft_marker}")
        info("")
    
    if total_count > display_limit:
        omitted = total_count - display_limit
        info(f"... and {omitted} more -- run `lexi conventions {rel_target}` to see all\n")
```

**Orient Integration:**

```python
def _collect_library_stats(project_root: Path) -> str:
    """Collect library stats: concept count, convention count, open stack posts."""
    # Count conventions
    conventions_dir = lexibrary_root / "conventions"
    convention_count = 0
    if conventions_dir.is_dir():
        convention_count = len(list(conventions_dir.glob("*.md")))
    
    # Lines appended: `Conventions: {convention_count}`
```

**Comparison to Playbooks Plan:**

✓ Playbooks follow same registration pattern  
✓ Lookup integration: `playbook_index.by_trigger_file(rel_target)` in both directory and file modes  
✓ Playbooks add `_render_triggered_playbooks()` helper (similar to `_render_conventions`)  
✓ Playbooks add to `_truncate_lookup_sections` with priority 2 (shift issues→3, iwh→4, links→5)  
✓ Orient: add playbook count to stats  
✓ Same config-driven display limit: `config.conventions.lookup_display_limit`  

---

## 8. Search Integration

### File: `src/lexibrary/search.py`

**Search Result Dataclass:**

```python
@dataclass
class _ConventionResult:
    title: str
    scope: str
    status: str
    tags: list[str]
    rule: str
```

**SearchResults Container:**

```python
@dataclass
class SearchResults:
    concepts: list[_ConceptResult] = field(default_factory=list)
    conventions: list[_ConventionResult] = field(default_factory=list)
    design_files: list[_DesignFileResult] = field(default_factory=list)
    stack_posts: list[_StackResult] = field(default_factory=list)
    
    def has_results(self) -> bool:
        return bool(self.concepts or self.conventions or self.design_files or self.stack_posts)
    
    def render(self) -> None:
        # Dispatches to _render_json, _render_plain, _render_markdown
```

**Rendering Examples:**

JSON:
```python
for cv in self.conventions:
    records.append({
        "title": cv.title,
        "scope": cv.scope,
        "tags": cv.tags,
        "status": cv.status,
    })
```

Plain:
```python
for cv in self.conventions:
    info(f"{cv.title}\t{cv.scope}\t{', '.join(cv.tags)}\t{cv.status}")
```

Markdown:
```python
rows = [
    [
        cv.title,
        cv.scope,
        cv.status,
        cv.rule[:50] if cv.rule else "",
        ", ".join(cv.tags),
    ]
    for cv in self.conventions
]
info(markdown_table(["Title", "Scope", "Status", "Rule", "Tags"], rows))
```

**Search Function:**

```python
def _search_conventions(
    project_root: Path,
    *,
    query: str | None,
    tag: str | None,
    extra_tags: list[str],
    scope: str | None,
    status: str | None,
    include_deprecated: bool,
) -> list[_ConventionResult]:
    """Search conventions via ConventionIndex (file-scanning fallback).
    
    Supports list-all, multi-tag AND, status filtering, scope filtering,
    and deprecated hiding.
    """
    conventions_dir = project_root / ".lexibrary" / "conventions"
    if not conventions_dir.is_dir():
        return []
    
    index = ConventionIndex(conventions_dir)
    index.load()
    
    if len(index) == 0:
        return []
    
    # Primary search (query or tag)
    if query is not None:
        matches = index.search(query)
    elif tag is not None:
        matches = index.by_tag(tag)
    else:
        matches = list(index.conventions)  # List-all
    
    # Secondary filters
    # Apply tag filter again if query was primary (multi-tag AND)
    if tag is not None and query is not None:
        tag_lower = tag.strip().lower()
        matches = [
            c for c in matches
            if any(t.strip().lower() == tag_lower for t in c.frontmatter.tags)
        ]
    
    # Multi-tag AND
    if extra_tags:
        matches = [
            c
            for c in matches
            if all(any(t.strip().lower() == et for t in c.frontmatter.tags) for et in extra_tags)
        ]
    
    # Scope filter: convention scope is "project" OR is prefix of query scope
    if scope is not None:
        norm_scope = scope.strip("/")
        matches = [
            c
            for c in matches
            if c.frontmatter.scope == "project"
            or norm_scope.startswith(c.frontmatter.scope.strip("/"))
        ]
    
    # Status filter
    if status is not None:
        matches = [c for c in matches if c.frontmatter.status == status]
    
    # Hide deprecated by default
    if not include_deprecated and status != "deprecated":
        matches = [c for c in matches if c.frontmatter.status != "deprecated"]
    
    return [
        _ConventionResult(
            title=c.frontmatter.title,
            scope=c.frontmatter.scope,
            status=c.frontmatter.status,
            tags=list(c.frontmatter.tags),
            rule=c.rule,
        )
        for c in matches
    ]
```

**Unified Search Entry Point:**

```python
def unified_search(
    project_root: Path,
    *,
    query: str | None = None,
    tag: str | None = None,
    tags: list[str] | None = None,
    scope: str | None = None,
    link_graph: LinkGraph | None = None,
    artifact_type: str | None = None,
    status: str | None = None,
    include_deprecated: bool = False,
    # ... other parameters
) -> SearchResults:
    """Search across concepts, conventions, design files, and Stack posts.
    
    When link_graph provided: uses index-accelerated tag/FTS paths.
    When link_graph is None: falls back to file-scanning.
    """
    # Routing logic:
    if link_graph is not None and first_tag is not None:
        return _tag_search_from_index(...)
    
    if link_graph is not None and query is not None and first_tag is None:
        return _fts_search(...)
    
    # Fallback: file-scanning search
    results = SearchResults()
    
    search_conventions = artifact_type is None or artifact_type == "convention"
    
    if search_conventions:
        results.conventions = _search_conventions(
            project_root,
            query=query,
            tag=first_tag,
            extra_tags=resolved_tags[1:] if resolved_tags else [],
            scope=scope,
            status=status,
            include_deprecated=include_deprecated,
        )
    
    return results
```

**Valid Artifact Types:**

```python
VALID_ARTIFACT_TYPES = ("concept", "convention", "design", "stack")
```

**Comparison to Playbooks Plan:**

✓ Playbooks add `_PlaybookResult` dataclass with fields: title, status, actor, tags, overview  
✓ Playbooks add `playbooks: list[_PlaybookResult]` to SearchResults  
✓ Playbooks update `has_results()` to include playbooks  
✓ Playbooks add rendering in all three modes (json, plain, markdown)  
✓ Playbooks add `"playbook"` to `VALID_ARTIFACT_TYPES`  
✓ Playbooks add `_search_playbooks()` following same fallback pattern  
✓ Playbooks wire into `unified_search()` with `search_playbooks` flag  
✓ Playbooks support index-accelerated paths via LinkGraph (both tag and FTS)  

---

## 9. Lifecycle: Comment Adapter Pattern

### File: `src/lexibrary/lifecycle/convention_comments.py`

**Module Structure:**

```python
"""Convention-file comment operations.

Thin layer on top of shared comment primitives in lexibrary.lifecycle.comments.
These functions accept a convention file path, derive the sibling `.comments.yaml` path,
and delegate to generic read/append/count helpers.
"""

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment

def convention_comment_path(convention_path: Path) -> Path:
    """Derive the `.comments.yaml` path from a convention file path.
    
    Example:
    .lexibrary/conventions/use-dataclasses.md
    -> .lexibrary/conventions/use-dataclasses.comments.yaml
    """
    return convention_path.with_suffix(".comments.yaml")

def append_convention_comment(
    convention_path: Path,
    body: str,
) -> None:
    """Append a comment to a convention's comment file.
    
    Derives the sibling `.comments.yaml` path, creates ArtefactComment with
    current UTC timestamp, delegates to append_comment().
    """
    comment_file_path = convention_comment_path(convention_path)
    comment = ArtefactComment(
        body=body,
        date=datetime.now(tz=UTC),
    )
    append_comment(comment_file_path, comment)

def read_convention_comments(convention_path: Path) -> list[ArtefactComment]:
    """Read all comments for a convention from its comment file.
    
    Returns empty list if `.comments.yaml` doesn't exist.
    """
    comment_file_path = convention_comment_path(convention_path)
    return read_comments(comment_file_path)

def convention_comment_count(convention_path: Path) -> int:
    """Count comments for a convention.
    
    Returns 0 if `.comments.yaml` doesn't exist.
    """
    comment_file_path = convention_comment_path(convention_path)
    return comment_count(comment_file_path)
```

**Integration in CLI:**

```python
# In cli/conventions.py:
from lexibrary.lifecycle.convention_comments import (
    append_convention_comment,
    convention_comment_path,
)

@convention_app.command("comment")
def convention_comment(slug: str, *, body: str) -> None:
    append_convention_comment(conv_path, body)
    comment_file = convention_comment_path(conv_path)
    info(f"Comment added for convention '{slug}' -- {comment_file.relative_to(project_root)}")
```

**Comparison to Playbooks Plan:**

✓ Playbooks create `lifecycle/playbook_comments.py` following identical pattern  
✓ Same functions: `playbook_comment_path()`, `append_playbook_comment()`, `read_playbook_comments()`, `playbook_comment_count()`  
✓ Same sibling `.comments.yaml` strategy  
✓ Same UTC timestamp handling  
✓ Playbooks integrate into `cli/playbooks.py` comment command (same pattern)  
✓ Playbooks add re-export to `lifecycle/__init__.py`  

---

## 10. Validation Checks

### File: `src/lexibrary/validator/checks.py` (excerpt)

**Check Function Signature Pattern:**

```python
def check_*(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]:
    """Generic validation check.
    
    Returns list of ValidationIssues with:
    - severity: "error", "warning", or "info"
    - check: check function name
    - message: human-readable issue description
    - artifact: relative path to artifact
    - suggestion: optional remediation advice
    """
    ...
```

**Convention Checks (from module docstring):**

```python
# Error-severity:
# - convention_frontmatter: required fields, valid enums

# Warning-severity:
# - convention_orphaned_scope: convention scope path doesn't exist

# Info-severity:
# - convention_stale: last_verified outdated (if implemented)
# - convention_gap: no conventions cover a file
# - convention_consistent_violation: conflict between conventions
```

**Wikilink Resolution Check (relevant to playbooks):**

```python
def check_wikilink_resolution(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Parse design files and Stack posts for wikilinks, verify each resolves."""
    issues: list[ValidationIssue] = []
    
    concepts_dir = lexibrary_dir / "concepts"
    index = ConceptIndex.load(concepts_dir)
    stack_dir = lexibrary_dir / "stack"
    convention_dir = lexibrary_dir / "conventions"
    resolver = WikilinkResolver(index, stack_dir=stack_dir, convention_dir=convention_dir)
    
    # Check design file wikilinks
    for design_path in _iter_design_files(lexibrary_dir):
        design = parse_design_file(design_path)
        if design is None:
            continue
        
        for link_text in design.wikilinks:
            result = resolver.resolve(link_text)
            if isinstance(result, UnresolvedLink):
                suggestion = ""
                if result.suggestions:
                    suggestion = f"Did you mean [[{result.suggestions[0]}]]?"
                rel_path = _rel(design_path, project_root)
                issues.append(
                    ValidationIssue(
                        severity="error",
                        check="wikilink_resolution",
                        message=f"[[{link_text}]] does not resolve",
                        artifact=rel_path,
                        suggestion=suggestion,
                    )
                )
    
    # Also check Stack posts...
    return issues
```

**Comparison to Playbooks Plan:**

✓ Playbooks add four new checks: playbook_frontmatter, playbook_wikilinks, playbook_staleness, playbook_deprecated_ttl  
✓ Same function signature pattern  
✓ Same issue reporting with severity/check/message/artifact/suggestion  
✓ Wikilink check already supports conventions; playbooks extend via WikilinkResolver  

---

## 11. Wikilink Resolver

### File: `src/lexibrary/wiki/resolver.py` (excerpt)

**Resolution Chain:**

```python
class WikilinkResolver:
    """Resolves wikilink references against concepts, conventions, and stack posts.
    
    Resolution chain (first match wins):
    
    1. Strip [[]] brackets if present
    2. Stack post pattern match (ST-NNN)
    3. Convention exact title match (case-insensitive) — convention-first
    4. Convention alias match (case-insensitive)
    5. Exact concept name match (case-insensitive)
    6. Concept alias match (case-insensitive)
    7. Fuzzy match via difflib.get_close_matches()
    8. Unresolved — attach 3 suggestions from fuzzy matching
    """
    
    def __init__(
        self,
        index: ConceptIndex,
        stack_dir: Path | None = None,
        convention_dir: Path | None = None,
    ) -> None:
        self._index = index
        self._stack_dir = stack_dir
        self._convention_index: ConventionIndex | None = None
        
        if convention_dir is not None and convention_dir.is_dir():
            self._convention_index = ConventionIndex(convention_dir)
            self._convention_index.load()
    
    def resolve(self, raw: str) -> ResolvedLink | UnresolvedLink:
        """Resolve a single wikilink string."""
        stripped = _strip_brackets(raw)
        
        # Stack post pattern
        if _STACK_RE.match(stripped):
            stack_id = stripped.upper()
            path = self._find_stack_file(stack_id)
            if path is not None:
                return ResolvedLink(
                    raw=raw,
                    name=stack_id,
                    kind="stack",
                    path=path,
                )
            return UnresolvedLink(raw=raw)
        
        # Convention exact title match (convention-first)
        conv = self._find_convention_exact(stripped)
        if conv is not None:
            return ResolvedLink(
                raw=raw,
                name=conv.frontmatter.title,
                kind="convention",
                path=None,
            )
        
        # Convention alias match
        conv = self._find_convention_alias(stripped)
        if conv is not None:
            return ResolvedLink(
                raw=raw,
                name=conv.frontmatter.title,
                kind="convention",
                path=None,
            )
        
        # [... concept exact, concept alias, fuzzy match ...]
        
        return UnresolvedLink(raw=raw, suggestions=suggestions)
    
    def _find_convention_exact(self, name: str) -> ConventionFile | None:
        """Find convention by exact title (case-insensitive)."""
        if self._convention_index is None:
            return None
        needle = name.strip().lower()
        for conv in self._convention_index.conventions:
            if conv.frontmatter.title.strip().lower() == needle:
                return conv
        return None
    
    def _find_convention_alias(self, name: str) -> ConventionFile | None:
        """Find convention by alias (case-insensitive)."""
        if self._convention_index is None:
            return None
        needle = name.strip().lower()
        for conv in self._convention_index.conventions:
            for alias in conv.frontmatter.aliases:
                if alias.strip().lower() == needle:
                    return conv
        return None

@dataclass(frozen=True)
class ResolvedLink:
    """A wikilink successfully resolved."""
    raw: str
    name: str
    kind: str  # "concept", "stack", "alias", or "convention"
    path: Path | None = None

@dataclass(frozen=True)
class UnresolvedLink:
    """A wikilink that could not be resolved."""
    raw: str
    suggestions: list[str] = field(default_factory=list)
```

**Comparison to Playbooks Plan:**

✓ Playbooks add `[[playbook: title]]` as a recognized link type  
✓ Follows same exact-match → alias-match → fuzzy pattern  
✓ Case-insensitive matching  
✓ Fuzzy suggestions support  
✓ Integration point: add `_find_playbook_exact()` and `_find_playbook_alias()` methods  

---

## 12. Configuration Model

### File: `src/lexibrary/config/schema.py` (excerpt)

**Convention Configuration:**

```python
class ConventionConfig(BaseModel):
    """Convention system configuration."""
    
    model_config = ConfigDict(extra="ignore")
    
    lookup_display_limit: int = 5
    deprecation_confirm: Literal["human", "maintainer"] = "human"

class LexibraryConfig(BaseModel):
    """Top-level Lexibrary configuration."""
    
    model_config = ConfigDict(extra="ignore")
    
    scope_root: str = "."
    project_name: str = ""
    agent_environment: list[str] = Field(default_factory=list)
    concepts: ConceptConfig = Field(default_factory=ConceptConfig)
    conventions: ConventionConfig = Field(default_factory=ConventionConfig)
    convention_declarations: list[ConventionDeclaration] = Field(default_factory=list)
    # ... other configs
    deprecation: DeprecationConfig = Field(default_factory=DeprecationConfig)
    stack: StackConfig = Field(default_factory=StackConfig)
    # ...

class DeprecationConfig(BaseModel):
    """Deprecation lifecycle configuration."""
    
    model_config = ConfigDict(extra="ignore")
    
    ttl_commits: int = 50
    comment_warning_threshold: int = 10

class StackConfig(BaseModel):
    """Stack post staleness lifecycle configuration."""
    
    model_config = ConfigDict(extra="ignore")
    
    staleness_confirm: Literal["human", "maintainer"] = "human"
    staleness_ttl_commits: int = 200
    staleness_ttl_short_commits: int = 100
    lookup_display_limit: int = 3
```

**Comparison to Playbooks Plan:**

✓ Playbooks add `PlaybookConfig` class with:
  - `staleness_commits: int = 100`
  - `staleness_days: int = 180`
✓ Playbooks extend `LexibraryConfig`:
  - `playbooks: PlaybookConfig = Field(default_factory=PlaybookConfig)`
✓ Same Pydantic ConfigDict(extra="ignore") pattern for extensibility
✓ Same Literal type hints for enums
✓ Same Field(default_factory=...) pattern for nested objects

---

## Summary: Pattern Consistency Checklist

### Models & Slug Helpers ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Frontmatter class | ConventionFileFrontmatter | PlaybookFileFrontmatter | Identical template |
| File wrapper class | ConventionFile | PlaybookFile | Identical template |
| Slug function | slugify() delegate | slugify() delegate | Identical |
| Path collision-append | convention_file_path() | playbook_file_path() | Identical |
| First-paragraph extraction | extract_rule() | extract_overview() | Same logic, different name |

### Parser & Serializer ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Frontmatter regex | _FRONTMATTER_RE | _FRONTMATTER_RE | Identical |
| Error handling | Silent None on failure | Silent None on failure | Identical |
| Optional field serialization | if field: fm_data["field"] = value | if field: fm_data["field"] = value | Identical |
| DateTime format | .isoformat() | .isoformat() (for deprecated_at) | Identical |
| Date format | N/A | .isoformat() (for last_verified) | New, follows pattern |

### Index API ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| load() | scan .md files, parse each | scan .md files, parse each | Identical |
| search(query) | substring match on title/aliases/tags/body | substring match (same searchable fields) | Identical |
| by_tag(tag) | case-insensitive exact match | case-insensitive exact match | Identical |
| by_status(status) | enum value match | enum value match | Identical |
| names() | sorted list of titles | sorted list of titles | Identical |
| Additional | find_by_scope, find_by_scope_limited | by_trigger_file() | New method (not in convention) |

### CLI Commands ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| new command | convention new --title --scope --body --tag --alias --source | playbook new --title --trigger-file --tag --actor --source | Same structure, different options |
| approve/activate | convention approve <slug> | playbook activate (implied) | Same pattern |
| deprecate | convention deprecate <slug> | playbook deprecate <slug> | Identical |
| comment | convention comment <slug> --body | playbook comment <slug> --body | Identical |
| Additional | N/A | playbook list, show, edit, verify | New commands (not conflicts) |

### Search Integration ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Result dataclass | _ConventionResult | _PlaybookResult | Same template |
| SearchResults field | conventions: list[_ConventionResult] | playbooks: list[_PlaybookResult] | Same pattern |
| Rendering | _render_markdown, _render_json, _render_plain | same three modes | Identical |
| File-scanning fallback | _search_conventions() | _search_playbooks() | Identical pattern |
| Index-accelerated paths | _tag_search_from_index, _fts_search | same (extend existing) | Extend not replace |

### Lookup Integration ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Directory lookup | ConventionIndex.find_by_scope_limited() | PlaybookIndex.by_trigger_file() | Both methods used, different semantics |
| File lookup (brief) | Same as directory | Same pattern for playbooks | Identical integration style |
| File lookup (full) | Token-budget-aware rendering | Same (add to truncation logic) | Extends existing pattern |
| Rendering helper | _render_conventions() | _render_triggered_playbooks() | Same template |
| Orient stats | Count playbooks via .glob("*.md") | Same counting pattern | Identical |

### Wikilink Resolution ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Exact match | _find_convention_exact() | _find_playbook_exact() | Same pattern |
| Alias match | _find_convention_alias() | _find_playbook_alias() | Same pattern |
| Resolution chain | Convention-first in chain | Playbook insertion point TBD | Extend existing chain |

### Lifecycle Comments ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Path derivation | convention_comment_path() | playbook_comment_path() | Same template |
| Append function | append_convention_comment() | append_playbook_comment() | Same template |
| Read function | read_convention_comments() | read_playbook_comments() | Same template |
| Count function | convention_comment_count() | playbook_comment_count() | Same template |
| Core delegation | append_comment, read_comments, comment_count | Same delegation | Identical |
| UTC timestamp | datetime.now(tz=UTC) | Same | Identical |

### Configuration ✓

| Pattern | Convention | Playbook Plan | Status |
|---------|-----------|---------------|--------|
| Config section class | ConventionConfig | PlaybookConfig | Same Pydantic template |
| Integration into LexibraryConfig | conventions: ConventionConfig | playbooks: PlaybookConfig | Same Field pattern |
| Staleness thresholds | N/A (separate in DeprecationConfig) | staleness_commits, staleness_days | New, follows Stack pattern |

---

## Key Implementation Insights

### 1. Delegation and Composition Pattern

All artifact types follow a three-layer pattern:
1. **Core artifact** (`artifacts/X.py`): Pydantic models + slug helpers
2. **Lifecycle** (`X/parser.py`, `X/serializer.py`, `X/index.py`): File I/O and in-memory indexing
3. **CLI** (`cli/X.py`): Command implementations
4. **Integration** (modifications to `search.py`, `lexi_app.py`, `resolver.py`, etc.): Discovery and context

### 2. Optional Field Serialization Pattern

When serializing to YAML:
```python
if convention.frontmatter.aliases:  # Only if non-empty
    fm_data["aliases"] = convention.frontmatter.aliases

if convention.frontmatter.deprecated_at is not None:  # Only if non-None
    fm_data["deprecated_at"] = convention.frontmatter.deprecated_at.isoformat()
```

Playbooks add `last_verified: date | None` → serialize as `.isoformat()` when non-None (same pattern).

### 3. Case-Insensitive Matching with Deduplication

When returning multiple results:
```python
matches: dict[str, ConventionFile] = {}
for conv in self.conventions:
    if _matches_convention(conv, needle):
        matches[conv.frontmatter.title] = conv  # Deduplicate by title
return [matches[k] for k in sorted(matches.keys())]  # Sort by title
```

This pattern ensures no duplicates and consistent ordering.

### 4. Scope as a First-Class Concept

Conventions have `scope: str = "project"` — a directory path that enables hierarchical applicability.
Playbooks don't have scope; instead they have `trigger_files: list[str]` (glob patterns).
Both use `find_by_scope()` / `by_trigger_file()` to answer: "which of these apply to this file?"

### 5. Lookup Display Limits

Both conventions and playbooks use `config.lookup_display_limit` to cap results in lookup output.
When truncated, a message appends: "... and N more -- run `lexi {type} {path}` to see all"

### 6. Token Budget Awareness

Full lookup mode includes multiple sections:
- Design file (always shown, highest priority)
- Conventions (always shown, second priority)
- Issues / IWH / Links (supplementary, truncated to fit budget)

Playbooks add as a **new section with priority 2**, shifting existing sections.

### 7. Index Integration (Not Deferred)

Playbooks are indexed in `index.db` alongside conventions, designs, and concepts.
- `_tag_search_from_index()` extended with `_KIND_PLAYBOOK = "playbook"`
- `_fts_search()` extended similarly
- File-scanning fallback (`_search_playbooks()`) when index unavailable

### 8. Deprecation Lifecycle Pattern

Stack posts use: `status: Literal["open", "resolved", "outdated", "duplicate", "stale"]`
Conventions use: `status: Literal["draft", "active", "deprecated"]` + `deprecated_at: datetime | None`
Playbooks follow conventions pattern (not stack pattern).

Staleness checks use `_count_commits_since()` + calendar fallback.

### 9. Comment System is Artifact-Agnostic

All artifacts share the same `lifecycle/comments.py` core:
- `read_comments(comment_file: Path) -> list[ArtefactComment]`
- `append_comment(comment_file: Path, comment: ArtefactComment) -> None`
- `comment_count(comment_file: Path) -> int`

Thin adapters (`convention_comments.py`, `playbook_comments.py`) derive the `.comments.yaml` sibling path and delegate.

### 10. Wikilink Resolution Chain Is Extensible

Current order:
1. Stack post pattern (ST-NNN)
2. **Convention exact + alias** (convention-first)
3. Concept exact + alias
4. Fuzzy match

Playbooks integrate by adding `_find_playbook_exact()` / `_find_playbook_alias()` methods.
Insertion point TBD in implementation (likely before concepts, or as a parallel convention check).

---

## Implementation Readiness Assessment

### Phase 1 (Models) — READY ✓
- All artifact model patterns established and consistent
- Slug helpers follow existing `slugify()` delegation pattern
- Pydantic v2 patterns are standard across project
- No blockers

### Phase 2 (Parser/Serializer) — READY ✓
- Regex and optional field patterns established
- `extract_overview()` ↔ `extract_rule()` naming choice documented
- YAML comment preservation is NEW (not in conventions, documented in plan)
- No blockers

### Phase 3 (Index) — READY ✓
- Index API matches convention pattern exactly
- `by_trigger_file()` is new method (not a breaking change)
- Pathspec integration for glob matching is standard dependency
- No blockers

### Phase 4 (CLI) — READY ✓
- Convention command patterns are well-established
- All command types (new, approve, deprecate, comment) have precedent
- `lexi playbook list`, `show`, `edit`, `verify` are non-controversial additions
- No blockers

### Phase 5 (Integration) — READY ✓
- Search result dataclass, rendering, and fallback patterns established
- Lookup integration points identified (directory, file brief, file full)
- Token budget system ready to extend
- Wikilink resolver extension path clear
- Comment adapter pattern proven
- No blockers

### Phase 6 (Validation) — READY ✓
- Check function signature and pattern established
- Frontmatter validation precedent (concepts, conventions, designs, stack)
- Wikilink check supports conventions already (easy to extend)
- Staleness checks follow stack/convention patterns
- No blockers

---

## Deferred Features (Per Plan)

These are intentionally not in v1 but fit the established patterns:

1. **Config-seeded playbook_declarations** — Would follow `convention_declarations` pattern
2. **Agent-capture from IWH history** — Would leverage existing IWH infrastructure
3. **Playbook run execution tracking** — Would need new `runs/` artifact type
4. **Migration from conventions** — Would be a helper command (precedent: no similar command exists)
5. **Distributed playbooks** — Would extend path resolution (new)

---

## Conclusion

The playbooks implementation plan is **architecturally sound and ready for implementation**. Every major component (models, parser, serializer, index, CLI, search, lookup, wikilinks, comments, validation, config) has a direct precedent in the conventions system.

Key consistencies:
- Same Pydantic model structure
- Same parser/serializer patterns (YAML frontmatter + markdown body)
- Same in-memory index API (load, search, by_tag, by_status, names)
- Same CLI command lifecycle (new, approve/activate, deprecate, comment)
- Same search integration (result dataclass, rendering modes, fallback file-scanning)
- Same lookup display logic (scope matching, truncation, token budget)
- Same wikilink resolution extension pattern
- Same lifecycle comment adapter pattern
- Same validation check signature

The only new concepts are:
- `trigger_files` (globs) instead of `scope` (paths)
- `actor` field (informational, no enforcement in v1)
- `last_verified: date` instead of deprecation-only tracking
- `by_trigger_file()` index method (uses pathspec, like gitignore patterns)
- `_render_triggered_playbooks()` lookup helper
- Playbooks in token budget calculation (priority 2)

All are natural extensions of existing patterns, not breaking changes.

