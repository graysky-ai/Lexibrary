# Navigation by Intent -- Deep Analysis

> **Status**: Analysis in progress. Key architectural decisions resolved (see §Resolved
> Decisions). Option selection pending — next pass will choose an approach and convert to
> implementation plan.
>
> **Building concurrently** with the START_HERE restructure (`plans/start-here-reimagined.md`).
> Designs should target the finished restructure, not the current 4-section START_HERE format.
>
> **Source attribution**: Analysis grounded in `src/lexibrary/archivist/start_here.py`,
> `baml_src/archivist_start_here.baml`, `src/lexibrary/linkgraph/query.py`,
> `src/lexibrary/linkgraph/builder.py`, `src/lexibrary/search.py`,
> `src/lexibrary/artifacts/design_file.py`, `src/lexibrary/artifacts/aindex.py`,
> `src/lexibrary/cli/lexi_app.py`, the hand-maintained table in `blueprints/START_HERE.md`,
> and the conventions implementation in `src/lexibrary/conventions/`.

---

## What Navigation by Intent Does

Navigation by Intent is a task-to-file routing table. It maps common agent development tasks
(e.g., "Add a CLI command", "Modify the daemon") to the specific file or directory the agent
should read first. The format is a two-column markdown table:

```
| Task | Read first |
| --- | --- |
| Add / modify an agent-facing CLI command | .lexibrary/src/lexibrary/cli/lexi_app.md |
| Modify design file generation pipeline   | .lexibrary/src/lexibrary/archivist/pipeline.md |
```

Currently this table is embedded in `.lexibrary/START_HERE.md`. Per the decisions below, it
will move to its own artifact file (`.lexibrary/NAVIGATION.md`).

### Why it matters

Agents operating on unfamiliar codebases waste significant context window and time on
exploratory navigation: running `ls`, reading READMEs, grepping for keywords, and gradually
assembling a mental model of where things live. Navigation by Intent short-circuits this
process by providing a pre-computed lookup table keyed on *what the agent wants to do*
rather than *what files exist*. The agent scans the table, finds the matching task, and
goes straight to the relevant file.

This is the only START_HERE section with no real alternative elsewhere in Lexibrary. The
directory tree tells you *what exists*; the ontology tells you *what terms mean*; Navigation
by Intent tells you *where to go based on what you want to accomplish*. That distinction --
routing by intent rather than by structure -- is what makes the section uniquely valuable.

---

## Properties of a Good Navigation Table

These are design requirements for generated tables, derived from analysis of what makes
task-to-file routing effective in practice.

### Task phrasing is action-oriented

Every row should start with a verb phrase describing what the developer wants to do:
"Add / modify", "Change", "Modify", "Raise / handle". This frames the table as a decision
tool -- the agent finds the row matching their intent, not the row matching a filename.

Verb choice should signal whether the agent is *adding* something new or *changing* something
existing:

- **"Add / modify"** -- for extensible subsystems where the most common task is adding or
  changing a component (CLI commands, language parsers, agent rules, validation checks)
- **"Modify"** -- for pipeline/logic changes where the subsystem exists and needs alteration
- **"Change"** -- for configuration, schema, or format changes

### Granularity is at the subpackage level

Rows should not route to individual functions (too narrow) or to top-level directories (too
broad). The right level is the specific design file or subdirectory that contains the
relevant context. "Modify link graph queries" routes to
`.lexibrary/src/lexibrary/linkgraph/query.md`, not to `linkgraph/` (too broad) or to
`LinkGraph.reverse_deps()` (too narrow).

### Disambiguation is explicit

Where two files serve similar purposes, the table must distinguish them. For example:
"Add / modify an agent-facing CLI command" vs "Add / modify a maintenance CLI command";
"Modify structural indexing (no LLM)" vs "Modify crawl logic (LLM-based)". These
disambiguation pairs are critical for preventing mis-routing. They require knowledge of the
codebase architecture, not just file listings.

### Coverage is proportional to complexity

Every top-level subpackage should have at least one row. Complex packages should have 2-4
rows for distinct concerns within the package. The table should be approximately proportional
to package complexity.

### Targets are design files within `.lexibrary/src/`

The "Read first" column should consistently point to design files or sub-directories within
`.lexibrary/src/`. Design files contain architectural context, interface contracts, and
dependency information. This aligns with the navigation protocol: read the design file before
editing the source file. All indexed projects are expected to have complete design file
coverage.

> **Open question**: How does this interact with `lexi lookup`? If the table routes to
> `.lexibrary/src/foo/bar.md`, and the agent wants deeper context, they would currently need
> to figure out the corresponding source path and run `lexi lookup src/foo/bar.py`. Should
> `lexi lookup` be extended to accept design file paths as well? See §Critical
> Considerations for further discussion.

---

## Current Generation: Strengths and Weaknesses

### What the LLM receives today

The `generate_start_here()` pipeline in `src/lexibrary/archivist/start_here.py` assembles
two inputs for the LLM:

1. **Directory tree** -- built by `_build_directory_tree()`, which walks the project
   filesystem excluding `.lexibrary/`, `.git/`, and ignored patterns. This is a raw ASCII
   tree showing every visible file and directory.

2. **Billboard summaries** -- collected by `_collect_aindex_summaries()`, which iterates
   `sorted(lexibrary_root.rglob(".aindex"))`, parses each `.aindex` file, and outputs
   `<directory_path>: <billboard>` lines. Billboards are one-line directory-level
   descriptions (from the `AIndexFile.billboard` field).

These two inputs are injected into the BAML prompt (`baml_src/archivist_start_here.baml`)
as `{{ directory_tree }}` and `{{ aindex_summaries }}`. The prompt instructs the LLM to
produce a "markdown table mapping common tasks to the file or directory to read first"
with "5-10 rows covering the most common development tasks."

Optionally, if a previous `START_HERE.md` exists, its content is included under
`{{ existing_start_here }}` with the instruction "preserve relevant context."

The `StartHereRequest` dataclass has four fields: `project_name`, `directory_tree`,
`aindex_summaries`, and `existing_start_here`. The BAML function
`ArchivistGenerateStartHere` mirrors these four parameters.

### What it produces

The LLM generates a `navigation_by_intent` string as part of the `StartHereOutput`
structured response (which also includes `topology`, `ontology`, and `navigation_protocol`).
The `_assemble_start_here()` function splices all four into the final `START_HERE.md`.

The entire START_HERE output is constrained to 500-800 tokens by the BAML prompt. With
four sections sharing this budget, the navigation table gets perhaps 150-200 tokens --
enough for 5-10 rows but no more.

### Where it falls short

**The LLM has no knowledge of workflows or tasks.** Billboard summaries describe what a
directory *contains* ("LLM pipeline for design file + START_HERE generation"), not what
*tasks* lead an agent to that directory. The LLM must infer tasks from structural
descriptions, which works for obvious cases ("Modify design file generation" from a billboard
about design file generation) but fails for cross-cutting concerns, multi-step workflows,
or tasks that span multiple directories.

**The LLM has no knowledge of file importance.** All directories appear equally weighted in
the billboard list. A directory containing the most-imported module in the project looks
the same as a directory containing a rarely-used utility. The LLM cannot prioritize rows
based on which files agents actually need most often.

**5-10 rows is too few for non-trivial projects.** A project with 15+ subpackages cannot
be meaningfully covered in 5-10 rows. The LLM must choose which areas to include, and
without importance signals, it may choose poorly.

**No file-level routing.** Billboard summaries are per-directory. The LLM sees
`src/lexibrary/archivist/: LLM pipeline for design file + START_HERE generation` but has
no visibility into the individual files within that directory. It cannot produce a row like
"Change change detection logic -> archivist/change_checker.py" because it does not know
`change_checker.py` exists or what it does.

**No dependency or connectivity information.** The LLM does not know that `search.py`
imports from `linkgraph/query.py`, or that `archivist/pipeline.py` is the most depended-upon
file in the archivist package. Without graph structure, it cannot infer which files are
architecturally central.

**File-level descriptions exist but are unused.** Each `.aindex` file contains an `entries`
list where each `AIndexEntry` has a per-file `description`. These descriptions are
generated from design file frontmatter and represent file-level "what this does" summaries.
The current `_collect_aindex_summaries()` function ignores entries entirely, extracting only
the directory-level `billboard` field. This is the lowest-hanging fruit for improvement.

### Examples of what billboard-only generation might get wrong

- **Missing specialized entry points.** If the billboard for `config/` says "Config schema
  and loader", the LLM might generate a single row "Change configuration -> config/". But a
  useful table would distinguish "Change config keys or defaults -> config/schema.py" from
  "Change config loading logic -> config/loader.py" from "Change default config template ->
  config/defaults.py". This requires file-level descriptions, not just directory billboards.

- **Missing cross-cutting tasks.** A task like "Add a new artifact type" touches
  `artifacts/` (model), `linkgraph/builder.py` (indexing), `archivist/pipeline.py`
  (generation), and `cli/` (CLI commands). No single billboard signals this. The LLM would
  likely route to `artifacts/` alone, leaving the agent to discover the other touchpoints
  through exploration.

- **Incorrect priority ordering.** The LLM might prioritize `daemon/` (interesting-sounding)
  over `config/` (boring-sounding), even though config changes are far more common in
  practice. Without frequency signals, the LLM's editorial instincts may not match actual
  usage patterns.

---

## Available Data Sources

Each potential input is analyzed for what it provides and how it could improve the
navigation table.

### 1. Billboard summaries (current input)

**What it provides**: One-line directory-level description for every indexed directory.
Stored in `AIndexFile.billboard`. Collected by `_collect_aindex_summaries()` in
`start_here.py`.

**Format**: `"src/lexibrary/archivist/: LLM pipeline for design file + START_HERE generation"`

**Contribution to navigation table**: Provides the structural backbone -- which directories
exist and roughly what they do. Sufficient for coarse routing ("Modify the archivist pipeline
-> archivist/") but not for fine-grained file-level routing.

**Limitation**: Directory-level only. No file-level detail, no connectivity, no importance
ranking, no task vocabulary.

### 2. `.aindex` file-level entries

**What it provides**: Per-file descriptions for every source file within an indexed
directory. Stored in `AIndexFile.entries` as a list of `AIndexEntry` objects. Each entry
has `name`, `entry_type`, and `description` fields. Filter `entry_type == "file"` for
source file descriptions.

**Example**: An `.aindex` for `src/lexibrary/linkgraph/` might contain an entry:
`name: "query.py", entry_type: "file", description: "Read-only query interface for the link graph index"`

**Contribution to navigation table**: This is the cheapest path to file-level descriptions.
The data is the same as design file frontmatter descriptions (`.aindex` entries are
generated from frontmatter), but already aggregated per-directory. The existing
`_collect_aindex_summaries()` function iterates `.aindex` files already -- extending it to
also extract file entries requires minimal code change.

**How to collect**: Extend `_collect_aindex_summaries()` to iterate `parsed.entries`,
filtering for `entry_type == "file"`, and output `<directory_path>/<name>: <description>`
lines alongside the existing billboard lines.

**Volume**: One entry per source file. Same volume as design file frontmatter, but collected
in a single pass over `.aindex` files rather than a separate traversal of the design file
tree.

**Relationship to design file frontmatter**: The content is identical -- `.aindex` entries
are generated from design file frontmatter descriptions. The `.aindex` path is preferred
for collection because the data is already aggregated per-directory and the collection
infrastructure already exists. Design file parsing (data source #3) is only needed if
additional frontmatter fields beyond `description` are required.

### 3. Design file frontmatter descriptions

**What it provides**: A one-line role/purpose statement for every source file that has a
design file. Stored in `DesignFileFrontmatter.description` (the `description` field, not
called "role"). Parsed by `parse_design_file()`.

**Example**: `description: "Read-only query interface for the link graph index"` (for
`linkgraph/query.py`)

**Contribution to navigation table**: File-level "what this does" descriptions that the LLM
can invert into "what task leads you here" entries. The description "Read-only query
interface for the link graph index" naturally maps to the task "Modify link graph queries".

**How to collect**: Scan all `.md` files under `.lexibrary/src/` (the design file mirror
tree), parse each with `parse_design_file()`, extract `design.frontmatter.description` and
`design.source_path`. This is a filesystem scan with YAML parsing -- no LLM needed, no
database required.

**Volume**: One entry per source file with a design file. For Lexibrary, this would be
~70-80 entries. For large projects, could be hundreds.

**When to prefer over `.aindex` entries**: Only when additional design file fields are
needed (e.g., `dependencies`, `dependents`, `wikilinks`, `tags`). For description-only
collection, `.aindex` entries (data source #2) are more efficient.

### 4. Design file dependencies and wikilinks

**What it provides**: Explicit dependency and cross-reference lists for every design file.
`DesignFile.dependencies` lists files this module depends on; `DesignFile.wikilinks` lists
concept names referenced; `DesignFile.dependents` lists files that depend on this module.

**Contribution to navigation table**: Dependency information helps identify *architecturally
central* files -- files with many dependents are important entry points. If
`config/schema.py` is depended on by 15 other files, it is likely a common edit target and
deserves a row in the table. Wikilinks connect files to domain concepts, enabling
concept-based routing: "Working on authentication? Start with these files."

**Limitation**: The `dependencies` and `dependents` lists in design files are populated by
the archivist LLM. They may not be exhaustive or perfectly accurate. The link graph
provides a more reliable source for the same relationships (see items 8 and 9).

### 5. Concept titles and tags

**What it provides**: Domain vocabulary entries with title, aliases, lifecycle status, and
tags. Stored in `.lexibrary/concepts/*.md` files. Indexed in the link graph `artifacts`
table (kind = "concept") with FTS and tag support.

**Contribution to navigation table**: Concepts represent the project's domain language.
If a concept called "Rate Limiting" exists with tags ["performance", "api"], and it has
`linked_files` pointing to `src/api/rate_limiter.py`, this creates a mapping from domain
concern to source file. An LLM could generate a row: "Modify rate limiting behavior ->
.lexibrary/src/api/rate_limiter.md" by combining the concept title with its linked files.

**How to access**: Via `LinkGraph.search_by_tag()` for tag-based lookup, or by scanning
concept files directly. The `ConceptFile.linked_files` field provides the concept-to-file
mapping. The builder processes these as `concept_file_ref` links in the link graph.

### 6. Convention scopes and bodies

**What it provides**: Project-wide and directory-scoped coding standards with lifecycle
metadata. Conventions are a first-class artifact type (Phase 5, already implemented).
Stored in `.lexibrary/conventions/*.md` files and indexed in the link graph with their
own `conventions` table.

Each convention has:
- `scope`: `"project"` (applies everywhere) or a directory path (e.g., `"src/auth"`)
- `body`: Full convention text
- `status`: `"draft"`, `"active"`, `"deprecated"`
- `source`: `"user"`, `"agent"`, `"config"`
- `priority`: Integer for specificity ordering

**Contribution to navigation table**: Convention scopes signal which directories have
explicit coding standards -- directories with many conventions are "hot" areas that agents
frequently need to understand. Convention bodies reference concepts via `[[wikilinks]]`
(tracked as `convention_concept_ref` links), connecting standards to domain vocabulary.

A convention saying "Always use the adapter pattern for new tokenizer backends" implies
the task "Add a tokenizer backend" exists and is common enough to standardize. The LLM
could use convention content to generate or validate navigation rows.

Conventions also suggest navigation rows of a different kind: routing to the conventions
themselves. For example: "Check coding standards for this directory ->
`lexi conventions <path>`".

**How to access**: Via `LinkGraph.get_conventions(directory_paths)` for scope-aware
retrieval (supports inheritance -- root conventions apply to all subdirectories).
Via `ConventionIndex.search()` for text queries, `ConventionIndex.by_tag()` for tag
filtering.

### 7. Stack post titles and tags

**What it provides**: Actual questions asked by agents working on the project. Stack posts
have titles (e.g., "How to add a new tokenizer backend"), tags, scoped file references
(`refs.files`), and concept references (`refs.concepts`).

**Contribution to navigation table**: Stack post titles are the most direct signal of
real agent workflows. If multiple Stack posts reference files in `tokenizer/`, that
suggests agents frequently work in that area. The titles themselves can seed the "Task"
column: a Stack post titled "How do I add a new language parser?" directly suggests the
navigation row "Add a language parser -> .lexibrary/src/ast_parser/".

Stack post frequency and vote counts provide an organic ranking signal. A question with
high votes was apparently common or important. The `StackPostFrontmatter.votes` field and
`StackPostFrontmatter.status` field (open/resolved/outdated) are available.

**How to access**: Via `StackIndex.search()` for text queries, `StackIndex.by_tag()` for
tag filtering, `StackIndex.by_scope()` for file-scoped filtering. The builder processes
these as `stack_file_ref` and `stack_concept_ref` links.

**Limitation**: Stack posts only exist if agents have asked questions. For new projects or
projects with few Stack posts, this data source is empty or sparse. Stack data should be
treated as a supplementary input, not a primary one.

### 8. Link graph edge counts (in-degree as importance proxy)

**What it provides**: The number of inbound links to each artifact. Queryable via
`LinkGraph.reverse_deps(path)`, which returns all `LinkResult` objects pointing at a given
artifact. The count of these results is the in-degree.

**Contribution to navigation table**: High in-degree files are architecturally central --
they are imported, referenced, or depended upon by many other files. These are strong
candidates for navigation table rows because they are the files agents are most likely to
need to understand when working on dependent code.

**Available link types** (from `linkgraph/schema.py`):
- `ast_import` -- source file A imports source file B (extracted via tree-sitter)
- `design_source` -- design file links to its source file
- `wikilink` -- design file or concept references a concept
- `concept_file_ref` -- concept links to a source file
- `stack_file_ref` -- Stack post references a source file
- `stack_concept_ref` -- Stack post references a concept
- `design_stack_ref` -- design file references a Stack post
- `convention_concept_ref` -- convention body references a concept

For importance ranking, `ast_import` in-degree is the most useful: a file imported by
many other source files is structurally central. `concept_file_ref` and `stack_file_ref`
in-degree also signal importance -- files referenced by domain concepts or Stack questions
are frequently relevant.

**How to compute**: For each source artifact, call `reverse_deps(path)` and count results.
Or issue a raw SQL query against the link graph for efficiency:
```sql
SELECT a.path, COUNT(*) as in_degree
FROM links l JOIN artifacts a ON l.target_id = a.id
WHERE l.link_type = 'ast_import'
GROUP BY a.path
ORDER BY in_degree DESC
LIMIT 20
```

This is not exposed as a convenience method on `LinkGraph` today. A `top_by_in_degree()`
or similar query would be needed.

**Limitation: in-degree measures structural centrality, not edit frequency.** A file like
`exceptions.py` might be imported by everything but rarely edited. A file like
`config/defaults.py` might have low in-degree but be the most commonly changed file.
In-degree is a useful heuristic for "architecturally important" but not necessarily for
"frequently edited by agents." Git commit frequency (`git log`) would be a complementary
signal for edit frequency, though it requires shell access and is not available through
the link graph.

### 9. Link graph reverse_deps (dependency chains)

**What it provides**: The `LinkGraph.reverse_deps(path, link_type=None)` method returns all
artifacts that link *to* a given artifact. The `LinkGraph.traverse(start_path, max_depth,
link_types, direction)` method performs multi-hop graph traversal in either direction.

**Contribution to navigation table**: Beyond raw in-degree counts, the graph structure
reveals *clusters* of related files. If five files in `archivist/` all import from
`config/schema.py`, that suggests a dependency cluster. The traversal API can identify
these clusters: starting from a file, which other files are reachable within 2 hops?

This could inform table construction by grouping files into "neighborhoods" -- instead of
listing many individual rows, the table could have rows like "Work on the archivist
pipeline" pointing to the cluster root, with the understanding that the agent should read
the traversal neighborhood.

**Limitation**: The traversal API returns `TraversalNode` objects (artifact_id, path, kind,
depth, via_link_type) but not edge counts or importance scores. Transforming traversal
output into table rows requires additional processing logic.

---

## Design Options

### Architectural note: own-artifact implications

The decision that Navigation by Intent will be its own file (`.lexibrary/NAVIGATION.md`)
rather than a section of `START_HERE.md` has significant implications for all options:

1. **Dedicated generation pipeline.** Navigation can have its own function
   (`generate_navigation()`) with its own BAML prompt, separate from `generate_start_here()`.
   The prompt can be single-purpose and detailed.

2. **Independent token budget.** The current 800-token constraint on START_HERE no longer
   applies. NAVIGATION.md can be as large as needed (within reason -- row count is the
   governing constraint, not tokens).

3. **Independent regeneration.** Input hashing can determine whether regeneration is needed,
   independent of whether START_HERE or other artifacts need updating.

4. **Richer inputs.** Without competing with topology/ontology/protocol for input token
   budget, the generation prompt can accept all available data sources.

These implications make all LLM-based options more viable than they appeared when navigation
was a subsection competing for budget within START_HERE.

### Option 1: LLM-generated with enriched inputs

Keep the current architecture -- a single LLM call produces the navigation table -- but
feed substantially richer inputs than the current billboard-only approach.

**Enriched inputs would include**:
- Billboard summaries (current)
- `.aindex` file-level entry descriptions (cheap to collect, same data as design frontmatter)
- Top-N files by `ast_import` in-degree (importance ranking)
- Concept titles and their linked files (domain vocabulary cross-references)
- Convention scopes (signals which areas have explicit standards)
- Stack post titles and tags (real workflow signals, if available)

**Implementation**:
- New or extended collector functions in a dedicated generation module:
  `_collect_file_descriptions()` (extends `.aindex` collection to include entries),
  `_collect_importance_ranking()`, `_collect_concept_summaries()`,
  `_collect_convention_summaries()`, `_collect_stack_summaries()`
- New BAML function and prompt dedicated to navigation generation
- New dataclass for the navigation generation request
- Row count as a configurable parameter (default: 20)

**Quality**: High. The LLM excels at editorial judgement -- deciding which tasks matter,
phrasing them naturally, choosing the right granularity. Richer inputs give it the data to
make good decisions.

**Cost**: One LLM call per generation. Estimated input size:
- Billboard summaries (~30 directories): ~600 tokens
- File-level descriptions (~80 files): ~1600 tokens
- Top-20 in-degree ranking: ~200 tokens
- Concept summaries (~20 concepts): ~400 tokens
- Convention summaries: ~200 tokens
- Stack post titles (~15 posts): ~300 tokens
- **Total: ~3300 input tokens** (varies significantly by project size)

**Freshness**: Regenerated only when inputs change (input hashing). Stable across minor
code changes.

**Implementation effort**: Medium. The `.aindex` entry collection is a minor extension of
existing code. The BAML prompt requires iteration. The importance ranking query is new.
Data plumbing is mechanical.

### Option 2: Partially procedural

Use algorithmic heuristics to identify "important" files and directories, then ask the LLM
only to generate task descriptions for the pre-selected files.

**Algorithm**:
1. Rank all source files by `ast_import` in-degree (files imported by many others are
   important)
2. Rank directories by aggregate child count and depth (large/deep directories are
   complex)
3. Include all files above a threshold in-degree (e.g., top 20%)
4. Include all directories that contain above-threshold files
5. Collect `.aindex` entry descriptions for the selected files
6. Ask the LLM: "Given these files and their descriptions, generate a task label for each"

**Quality**: Good for identifying *which files matter*. Weaker on *task phrasing* because
the LLM gets a list of files to describe rather than freedom to choose which tasks to
highlight. May miss cross-cutting tasks that do not correspond to any single high-importance
file.

**Cost**: Lower than Option 1. The LLM input is smaller (only the selected files, not the
full project). The procedural ranking does the heavy lifting.

**Freshness**: The procedural ranking can run without an LLM call. Only the task-label
generation step requires the LLM. Could cache task labels and regenerate only when the
file set changes.

**Implementation effort**: Medium-high. Requires a new in-degree ranking query on the link
graph (not currently exposed by `LinkGraph`), file selection heuristics, and a new BAML
prompt for task-label generation.

### Option 3: Fully procedural

No LLM involvement. Generate the entire table from heuristics and existing metadata.

**Algorithm**:
1. Rank files by `ast_import` in-degree
2. For each top-ranked file, use its `.aindex` entry description as context
3. Generate the "Task" column by pattern transformation:
   - If description starts with a verb ("Parse .aindex files"), convert to imperative
     ("Modify .aindex parsing")
   - If description is noun-form ("Pydantic 2 models for design files"), generate
     "Change <description>"
   - Apply heuristic templates: "Add / modify" for extensible components, "Change" for
     config/schema, "Modify" for logic/pipeline

**Quality**: Low-to-medium. Pattern-based task labels are mechanical and often read
unnaturally. "Change Read-only query interface for the link graph index" is not a good task
description. Would require significant template engineering to produce natural-sounding
rows. Completely misses cross-cutting and workflow-based tasks.

**Cost**: Zero LLM cost. Runs instantly.

**Freshness**: Always current. Can regenerate on every update (including `--changed-only`)
with negligible cost.

**Implementation effort**: Medium. The ranking query and description collection are
shared with Option 2. The task-label generation logic requires template engineering and
testing.

### Option 4: Dynamic command (`lexi navigate <task description>`)

Replace the static table entirely with a CLI command that takes a free-text task
description and returns suggested files using FTS + link graph queries.

**Implementation**:
- New command: `lexi navigate "add a new CLI command"`
- Backend: Run `unified_search()` with the task description as the query. Also try
  `LinkGraph.full_text_search()` directly for broader matching.
- Rank results by combining FTS relevance with in-degree importance.
- Return top 3-5 files with their descriptions.

**Quality**: High for well-phrased queries. Poor for vague or exploratory queries. The
agent must know enough about what they want to do to formulate a search query -- which is
exactly the cold-start problem the static table solves.

**Cost**: No LLM cost (FTS + SQL queries only). Minimal compute per invocation.

**Freshness**: Always current. Queries the live index.

**Implementation effort**: Low-medium. The search infrastructure (`unified_search`,
`full_text_search`) already exists. The new command is a thin wrapper with result ranking.
The main work is designing the ranking algorithm.

### Option 5: Hybrid (static table + dynamic command)

Keep a static Navigation by Intent table in `NAVIGATION.md` for the most common tasks
(generated via Option 1 or Option 2), and add a `lexi navigate` command for ad-hoc
queries that fall outside the table.

**Static table**: ~20 rows covering the most architecturally significant entry points.
Generated by an LLM with enriched inputs (Option 1 approach).

**Dynamic command**: For everything else. "The table doesn't cover what I need? Run
`lexi navigate <description>`."

**Quality**: Best of both worlds. The static table provides zero-query orientation for
common tasks; the dynamic command handles the long tail.

**Cost**: One LLM call per generation (for the static table). Zero cost for the dynamic
command.

**Freshness**: Static table updates when inputs change (hash-gated). Dynamic command is
always current.

**Implementation effort**: Highest total effort (both the enriched-input LLM pipeline and
the navigate command). But the components are independently useful and can be shipped
incrementally. The enriched static table (Option 1) is lower risk and should ship first --
it builds on the existing pipeline with no new CLI surface area. The navigate command can
follow as a separate piece of work.

### Emerging possibility: Layered generation (procedural base + LLM polish)

The own-artifact decision opens a variant worth considering: use Option 3 (fully procedural)
to generate a deterministic base table, then optionally run an LLM pass to polish task
labels, merge related rows, and add cross-cutting entries.

**How it would work**:
1. Procedurally rank files and generate a base table (always available, deterministic)
2. Hash the base table inputs
3. If hash differs from previous generation, run an LLM call with the base table +
   enriched inputs (concepts, conventions, Stack posts) to produce a polished version
4. If hash matches, reuse the cached polished version

**Advantages**:
- Works without LLM access (procedural base is always available)
- Deterministic file selection (LLM only handles phrasing and editorial decisions)
- Input hashing gates both the procedural step and the LLM step
- The LLM gets a structured starting point rather than open-ended generation

**Disadvantages**:
- Two-pass architecture is more complex
- The procedural base may anchor the LLM's output, limiting creative reorganization
- More code to maintain

This is not a formal option yet, but worth evaluating alongside Options 1-5.

---

## Critical Considerations

### Collection path: `.aindex` entries vs design file parsing

The `.aindex` entries and design file frontmatter descriptions contain the same data
(entries are generated from frontmatter). For description-only collection, `.aindex`
entries are strictly better:
- Already aggregated per-directory (one file per directory vs one file per source file)
- Existing collection infrastructure (`_collect_aindex_summaries()`) iterates `.aindex`
  files and can be extended with minimal code
- No YAML parsing of individual design files required

Design file parsing is only needed if additional fields are required (dependencies,
dependents, wikilinks, tags). For the initial implementation, `.aindex` entries should be
the primary collection path.

### Cross-cutting task detection

None of the five options reliably detect cross-cutting tasks ("Add a new artifact type"
touches artifacts/, linkgraph/builder.py, archivist/pipeline.py, and cli/). This is a
known limitation.

In practice, the navigation table routes to *starting points*, not complete task plans. The
design file's dependency list handles "what else to read" once the agent is in the right
area. Cross-cutting task detection is a non-goal for v1 -- the table's job is to get the
agent to the right neighborhood, not to enumerate every file they'll need.

The LLM may still generate cross-cutting rows from enriched inputs (concept links that
span multiple packages, Stack posts that reference files in different directories), but
this is a bonus, not a requirement.

### The `lexi lookup` integration question

The navigation table and `lexi lookup` form a natural two-step pipeline:

1. Agent scans navigation table -> finds relevant design file path
2. Agent reads the design file or runs `lexi lookup` for deeper context

Currently, `lexi lookup` accepts **source file paths** (e.g., `src/lexibrary/search.py`)
and resolves them to design files internally. But if the navigation table routes to
**design file paths** (e.g., `.lexibrary/src/lexibrary/search.md`), there is a mismatch --
the agent has a design file path but `lexi lookup` expects a source path.

Three resolution paths:
1. **Extend `lexi lookup`** to accept both source and design file paths. If given a design
   file path, resolve to the corresponding source file and proceed normally.
2. **Route to source paths in the table.** The "Read first" column shows source paths; the
   agent runs `lexi lookup` on them. The design file is accessed indirectly.
3. **Route to design file paths, agent reads directly.** The agent reads the design file
   via their file-reading tool. No `lexi lookup` needed for the initial orientation.

Option 1 is the most ergonomic. This should be coordinated with `plans/lookup-upgrade.md`.

### In-degree as importance proxy: limitations

`ast_import` in-degree measures structural centrality (how many files import this file),
not edit frequency (how often agents modify this file). A file like `exceptions.py` might
have high in-degree but rarely need editing. A file like `config/defaults.py` might have
low in-degree but be the most commonly changed file.

For navigation table construction, structural centrality is still useful -- it identifies
files that agents need to *understand* (because they're depended upon), which correlates
with files they'll encounter during development. But it is not a perfect proxy for "files
agents most often need to work on."

Supplementary signals:
- Git commit frequency (`git log --format=... -- <file>`) would indicate edit frequency
  but requires shell access and is not available through the link graph
- Stack post file references indicate which files agents ask questions about
- Convention scopes indicate which areas have explicit standards (suggesting complexity)

For v1, `ast_import` in-degree is a reasonable starting heuristic. Supplementary signals
can be layered on in future iterations.

### The `existing_start_here` feedback loop (stability)

The current pipeline feeds the previous START_HERE back to the LLM with "preserve relevant
context." With enriched inputs, the LLM receives both the previous table and richer data.
This creates a risk: the LLM might ignore the previous table in favor of the new data,
causing rows to oscillate between regenerations.

Since NAVIGATION.md will be its own file, the stability mechanism should be explicit:
- The previous NAVIGATION.md content is fed back as a separate input
- The prompt instructs: "preserve existing rows unless the underlying file no longer
  exists or the description has materially changed"
- Input hashing gates regeneration entirely -- if the inputs haven't changed, the LLM
  is not called at all

The input hashing approach is the primary stability mechanism. The prompt-level
preservation instruction is a secondary safeguard for cases where inputs change
incrementally (e.g., one new file added).

### Graceful degradation requirements

The enriched-input approach must handle missing data sources without failing. Possible
states:

| State | Available inputs | Fallback behavior |
| --- | --- | --- |
| Full index | All sources | Full enriched generation |
| No link graph | Billboards + `.aindex` entries | Billboard + file descriptions only; no importance ranking |
| No concepts | Everything except concepts | Skip concept input section |
| No conventions | Everything except conventions | Skip convention input section |
| No Stack posts | Everything except Stack | Skip Stack input section |
| No `.aindex` files | Directory tree only | Degenerate case: directory-tree-only generation |
| No `.lexibrary/` at all | Nothing | Skip navigation generation entirely |

Each collector function should return an empty/default value when its data source is
unavailable. The BAML prompt should handle empty input sections gracefully (conditional
rendering via `{% if %}` blocks).

---

## Row Count

The default target is **20 rows**, exposed as an advanced configuration item
(`navigation_rows` or similar in `.lexibrary/config.yaml`).

Is number of rows the right measurement? Alternatives considered:

- **Token count**: More precise for context window budgeting, but less intuitive for users
  to configure. A row count implicitly bounds token usage (~15-20 tokens/row, so 20 rows ≈
  300-400 tokens).
- **Subpackage coverage**: "One row per subpackage" scales naturally but doesn't account
  for subpackages that need multiple rows (disambiguation pairs).
- **Adaptive**: Scale row count automatically based on project size. Requires heuristics
  for what "project size" means (file count? subpackage count? distinct concern count?).

Row count is the simplest and most predictable control. It can serve as a starting point,
with adaptive scaling explored later if manual tuning proves insufficient.

The row count should scale with the number of distinct *concerns* in the project, not the
number of files. A project with 100 files but only 5 subpackages may need only 10-15 rows.
Rough guidance for the prompt:

- **Small projects** (< 10 source files): 5-10 rows
- **Medium projects** (10-50 source files): 10-20 rows
- **Large projects** (50+ source files): 20-30 rows

The configured default of 20 covers most medium-to-large projects. The LLM prompt should
use the configured value as guidance, not a hard constraint -- "approximately N rows" rather
than "exactly N rows."

---

## Resolved Decisions

### 1. Navigation by Intent is its own artifact file

**Decision**: Navigation by Intent will live in `.lexibrary/NAVIGATION.md`, not embedded
in `START_HERE.md`. START_HERE will include a pointer to it.

**Rationale**: Own file enables independent regeneration lifecycle, own staleness detection
via input hashing, own token budget, and a dedicated generation function with specialized
BAML prompt. The downside (one more file for agents to discover) is mitigated by the
pointer in START_HERE.

### 2. Rows route to `.lexibrary/src/` paths

**Decision**: The "Read first" column routes to design files or sub-directories within
`.lexibrary/src/`. All indexed projects are expected to have complete design file coverage.

**Rationale**: Design files contain architectural context, interface contracts, and
dependency information. Routing to design files aligns with the navigation protocol (read
the design file before editing source). Source file paths are insufficient for orientation;
raw directory paths are too coarse.

### 3. Default row count is 20, configurable

**Decision**: Default to 20 rows. Expose as an advanced configuration item. The LLM prompt
uses this as guidance ("approximately N rows"), not a hard constraint.

### 4. Skip regeneration when inputs haven't changed

**Decision**: Hash the collected inputs (billboards, file descriptions, importance ranking,
concepts, conventions, Stack titles). Compare to the hash stored from the previous
generation. Skip the LLM call if the hash matches.

**Rationale**: The navigation table should be architecturally stable. It should update when
a new subpackage is added or a package is restructured, but not when a bug fix is committed.
Input hashing makes regeneration proportional to structural change.

### 5. Stack post frequency is a supplementary input

**Decision**: Stack post titles, tags, and file references are valuable inputs to the LLM
but cannot be the sole basis for the table. For new projects or projects with few Stack
posts, this data source is empty.

### 6. Conventions are available as an input source

**Decision**: Phase 5 conventions are already implemented. Convention scopes, bodies, and
concept links are available data sources. They should be included in the enriched inputs
where the chosen option supports LLM input.

### 7. Building concurrently with START_HERE restructure

**Decision**: This plan targets the finished restructure, not the current 4-section
START_HERE format. The generation pipeline should be designed for NAVIGATION.md as a
standalone artifact from the start, not as a subsection that later gets extracted.

### 8. Graceful degradation is a design requirement

**Decision**: Every collector function must handle missing data sources without failing.
The generation pipeline must produce useful output even with partial inputs (see
§Graceful degradation requirements for the full state matrix).

---

## Open Questions

1. **Which option (or combination)?** Options 1-5 plus the layered generation variant are
   still open. The next pass will select an approach based on quality/effort tradeoffs.

2. **How should `lexi lookup` handle design file paths?** If the table routes to
   `.lexibrary/src/foo.md` and the agent runs `lexi lookup .lexibrary/src/foo.md`, should
   lookup resolve this to the source path and proceed? This needs coordination with
   `plans/lookup-upgrade.md`.

3. **What stability mechanism beyond input hashing?** Input hashing prevents unnecessary
   regeneration. But when inputs *do* change incrementally, should the prompt include the
   previous table with explicit row-preservation instructions? Or is the LLM's own
   consistency sufficient?

4. **How should the table handle monorepos or multi-package projects?** Lexibrary is
   currently building for monorepos, but the navigation table design hasn't addressed
   multi-package structure. A project with `packages/auth/`, `packages/billing/`,
   `packages/api/` has three largely independent concern areas. Should the table be
   structured hierarchically, flat with package prefixes, or one table per package?
   Important concern for later; not blocking for v1.

5. **Is number of rows the right size measurement?** Alternatives (token count, adaptive
   scaling by project size) may be worth exploring after the initial implementation proves
   out the basic approach. See §Row Count for analysis.

---

## Relationship to Other Plans

### `plans/start-here-reimagined.md`

This document was split from the "Open Thread: Navigation by Intent" section of
`start-here-reimagined.md`. Work proceeds concurrently. Key framing from that document:

- Navigation by Intent is the **only section proposed to remain LLM-generated** in the
  reimagined START_HERE
- Topology becomes procedural, Ontology becomes a pointer, Convention Index is removed,
  Navigation Protocol is removed
- Since Navigation by Intent is now its own file (`.lexibrary/NAVIGATION.md`), the
  reimagined START_HERE becomes even slimmer -- it is primarily a structural overview
  with pointers to NAVIGATION.md, conventions, and the ontology

### Conventions (Phase 5 -- already implemented)

Conventions are a first-class artifact type with full lifecycle management (`lexi convention
new/approve/deprecate`), scope-aware inheritance via `LinkGraph.get_conventions()`, and
link graph integration including `convention_concept_ref` wikilinks.

Convention data is available as an input source for navigation generation. The navigation
table may also include rows that route to conventions themselves (e.g., "Check coding
standards -> `lexi conventions`").

### `lexi navigate` command (Option 4/5)

If the dynamic `lexi navigate` command is implemented (as part of Option 5), the static
table's role shifts from "comprehensive routing" to "common-case routing." The table can
afford to be smaller and more focused, deferring edge cases to the command. This influences
the row count target and the LLM prompt design.

### `plans/lookup-upgrade.md` and `plans/search-upgrade.md`

The `lexi lookup` and `lexi search` commands are the primary query tools agents use for
navigating the knowledge layer. Navigation by Intent is a *pre-computed* navigation aid;
`lexi lookup` and `lexi search` are *on-demand* navigation aids. Improvements to lookup
(richer output, better formatting) and search (better relevance ranking) reduce the
pressure on the navigation table to be comprehensive.

**Specific dependency**: If the navigation table routes to `.lexibrary/src/` paths, `lexi
lookup` may need to accept design file paths as input (see Open Question #2). This should
be coordinated with the lookup upgrade plan.
