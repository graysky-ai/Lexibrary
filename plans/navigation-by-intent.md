# Navigation by Intent -- Deep Analysis

> **Status**: Split from `plans/start-here-reamagined.md` (Open Thread: Navigation by Intent).
> Needs investigation and prototyping before implementation decisions are made.
>
> **Source attribution**: Analysis grounded in `src/lexibrary/archivist/start_here.py`,
> `baml_src/archivist_start_here.baml`, `src/lexibrary/linkgraph/query.py`,
> `src/lexibrary/linkgraph/builder.py`, `src/lexibrary/search.py`,
> `src/lexibrary/artifacts/design_file.py`, `src/lexibrary/artifacts/aindex.py`,
> `src/lexibrary/cli/lexi_app.py`, and the hand-maintained table in `blueprints/START_HERE.md`.

---

## What Navigation by Intent Does

Navigation by Intent is a task-to-file routing table embedded in `START_HERE.md`. It maps
common agent development tasks (e.g., "Add a CLI command", "Modify the daemon") to the
specific file or directory the agent should read first. The format is a two-column markdown
table:

```
| Task | Read first |
| --- | --- |
| Add / modify an agent-facing CLI command | blueprints/src/lexibrary/cli/lexi_app.md |
| Modify design file generation pipeline   | blueprints/src/lexibrary/archivist/pipeline.md |
```

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

### The gold standard: `blueprints/START_HERE.md`

The hand-maintained Navigation by Intent table in `blueprints/START_HERE.md` (lines 169-212)
is the reference example of what this section should look like. It has 40 rows covering
Lexibrary's own development tasks. Analyzing what makes it effective:

**Task phrasing is action-oriented.** Every row starts with a verb phrase describing what
the developer wants to do: "Add / modify", "Change", "Modify", "Raise / handle". This
frames the table as a decision tool -- the agent finds the row matching their intent, not
the row matching a filename.

**Granularity is at the subpackage level.** The table does not route to individual functions
or to top-level directories. Instead, it targets the specific design file or subdirectory
that contains the relevant context. "Modify link graph queries" routes to
`blueprints/src/lexibrary/linkgraph/query.md`, not to `linkgraph/` (too broad) or to
`LinkGraph.reverse_deps()` (too narrow).

**Coverage is comprehensive but not exhaustive.** With 40 rows, the table covers every
subpackage in the project. It does not attempt to enumerate every possible task -- instead,
it picks the most common or most architecturally significant entry points for each area.

**Disambiguation is explicit.** Where two files serve similar purposes, the table
distinguishes them: "Add / modify an agent-facing CLI command" vs "Add / modify a
maintenance CLI command"; "Modify structural indexing (no LLM)" vs "Modify crawl logic
(LLM-based)". This prevents the agent from landing in the wrong file.

**Targets are design files, not source files.** The "Read first" column consistently points
to `blueprints/src/...` design files, which contain architectural context, interface
contracts, and dependency information. This aligns with the navigation protocol: read the
design file before editing the source file.

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

### What it produces

The LLM generates a `navigation_by_intent` string as part of the `StartHereOutput`
structured response. The prompt requests 5-10 rows. The `_assemble_start_here()` function
splices this string into the final `START_HERE.md` under the `## Navigation by Intent`
heading.

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

**5-10 rows is too few for non-trivial projects.** The hand-maintained Lexibrary table has
40 rows. A project with 15+ subpackages cannot be meaningfully covered in 5-10 rows. The
LLM must choose which areas to include, and without importance signals, it may choose
poorly.

**No file-level routing.** Billboard summaries are per-directory. The LLM sees
`src/lexibrary/archivist/: LLM pipeline for design file + START_HERE generation` but has
no visibility into the individual files within that directory. It cannot produce a row like
"Change change detection logic -> archivist/change_checker.py" because it does not know
`change_checker.py` exists or what it does.

**No dependency or connectivity information.** The LLM does not know that `search.py`
imports from `linkgraph/query.py`, or that `archivist/pipeline.py` is the most depended-upon
file in the archivist package. Without graph structure, it cannot infer which files are
architecturally central.

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

### 2. Design file frontmatter descriptions

**What it provides**: A one-line role/purpose statement for every source file that has a
design file. Stored in `DesignFileFrontmatter.description` (the `description` field, not
called "role"). Parsed by `parse_design_file()`.

**Example**: `description: "Read-only query interface for the link graph index"` (for
`linkgraph/query.py`)

**Contribution to navigation table**: This is the single most valuable additional input.
It provides file-level "what this does" descriptions that the LLM can invert into "what
task leads you here" entries. The description "Read-only query interface for the link graph
index" naturally maps to the task "Modify link graph queries".

**How to collect**: Scan all `.md` files under `.lexibrary/src/` (the design file mirror
tree), parse each with `parse_design_file()`, extract `design.frontmatter.description` and
`design.source_path`. This is a filesystem scan with YAML parsing -- no LLM needed, no
database required.

**Volume**: One entry per source file with a design file. For Lexibrary, this would be
~70-80 entries. For large projects, could be hundreds.

### 3. Design file dependencies and wikilinks

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
provides a more reliable source for the same relationships (see items 6 and 7).

### 4. Concept titles and tags

**What it provides**: Domain vocabulary entries with title, aliases, lifecycle status, and
tags. Stored in `.lexibrary/concepts/*.md` files. Indexed in the link graph `artifacts`
table (kind = "concept") with FTS and tag support.

**Contribution to navigation table**: Concepts represent the project's domain language.
If a concept called "Rate Limiting" exists with tags ["performance", "api"], and it has
`linked_files` pointing to `src/api/rate_limiter.py`, this creates a mapping from domain
concern to source file. An LLM could generate a row: "Modify rate limiting behavior ->
api/rate_limiter.py" by combining the concept title with its linked files.

**How to access**: Via `LinkGraph.search_by_tag()` for tag-based lookup, or by scanning
concept files directly. The `ConceptFile.linked_files` field provides the concept-to-file
mapping. The builder processes these as `concept_file_ref` links in the link graph.

### 5. Stack post titles and tags

**What it provides**: Actual questions asked by agents working on the project. Stack posts
have titles (e.g., "How to add a new tokenizer backend"), tags, scoped file references
(`refs.files`), and concept references (`refs.concepts`).

**Contribution to navigation table**: Stack post titles are the most direct signal of
real agent workflows. If multiple Stack posts reference files in `tokenizer/`, that
suggests agents frequently work in that area. The titles themselves can seed the "Task"
column: a Stack post titled "How do I add a new language parser?" directly suggests the
navigation row "Add a language parser -> ast_parser/".

Stack post frequency and vote counts provide an organic ranking signal. A question with
high votes was apparently common or important. The `StackPostFrontmatter.votes` field and
`StackPostFrontmatter.status` field (open/resolved/outdated) are available.

**How to access**: Via `StackIndex.search()` for text queries, `StackIndex.by_tag()` for
tag filtering, `StackIndex.by_scope()` for file-scoped filtering. The builder processes
these as `stack_file_ref` and `stack_concept_ref` links.

**Limitation**: Stack posts only exist if agents have asked questions. For new projects or
projects with few Stack posts, this data source is empty or sparse.

### 6. Link graph edge counts (in-degree as importance proxy)

**What it provides**: The number of inbound links to each artifact. Queryable via
`LinkGraph.reverse_deps(path)`, which returns all `LinkResult` objects pointing at a given
artifact. The count of these results is the in-degree.

**Contribution to navigation table**: High in-degree files are architecturally central --
they are imported, referenced, or depended upon by many other files. These are strong
candidates for navigation table rows because they are the files agents are most likely to
need to understand when working on dependent code.

**Available link types** (from `builder.py`):
- `ast_import` -- source file A imports source file B (extracted via tree-sitter)
- `design_source` -- design file links to its source file
- `wikilink` -- design file or concept references a concept
- `concept_file_ref` -- concept links to a source file
- `stack_file_ref` -- Stack post references a source file
- `stack_concept_ref` -- Stack post references a concept
- `design_stack_ref` -- design file references a Stack post

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

### 7. Link graph reverse_deps (dependency chains)

**What it provides**: The `LinkGraph.reverse_deps(path, link_type=None)` method returns all
artifacts that link *to* a given artifact. The `LinkGraph.traverse(start_path, max_depth,
link_types, direction)` method performs multi-hop graph traversal in either direction.

**Contribution to navigation table**: Beyond raw in-degree counts, the graph structure
reveals *clusters* of related files. If five files in `archivist/` all import from
`config/schema.py`, that suggests a dependency cluster. The traversal API can identify
these clusters: starting from a file, which other files are reachable within 2 hops?

This could inform table construction by grouping files into "neighborhoods" -- instead of
listing 40 individual rows, the table could have rows like "Work on the archivist pipeline"
pointing to the cluster root, with the understanding that the agent should read the
traversal neighborhood.

**Limitation**: The traversal API returns `TraversalNode` objects (artifact_id, path, kind,
depth, via_link_type) but not edge counts or importance scores. Transforming traversal
output into table rows requires additional processing logic.

---

## Design Options

### Option 1: LLM-generated with enriched inputs

Keep the current architecture -- a single LLM call produces the navigation table -- but
feed substantially richer inputs than the current billboard-only approach.

**Enriched inputs would include**:
- Billboard summaries (current)
- Design file descriptions (file-level "what this does")
- Top-N files by `ast_import` in-degree (importance ranking)
- Concept titles and their linked files (domain vocabulary cross-references)
- Stack post titles and tags (real workflow signals, if available)

**Implementation**:
- New collector functions in `start_here.py`: `_collect_design_descriptions()`,
  `_collect_importance_ranking()`, `_collect_concept_summaries()`,
  `_collect_stack_summaries()`
- Update `StartHereRequest` with new fields
- Update `archivist_start_here.baml` with new input sections and revised instructions
- Increase row count guidance from "5-10" to "15-30" (scaled by project size)

**Quality**: High. The LLM excels at editorial judgement -- deciding which tasks matter,
phrasing them naturally, choosing the right granularity. Richer inputs give it the data to
make good decisions.

**Cost**: One LLM call per full update. Input tokens increase significantly (design
descriptions for 80 files + concept summaries + Stack titles). Estimated 2000-4000 input
tokens depending on project size.

**Freshness**: Regenerated on every `lexictl update` (full). Stale after `update
--changed-only`. This is acceptable -- the navigation table should be stable across minor
changes.

**Implementation effort**: Medium. The collector functions are straightforward (filesystem
scans, link graph queries). The BAML prompt rewrite requires iteration to get good output.
The data plumbing (StartHereRequest changes, service changes) is mechanical.

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
5. Collect design file descriptions for the selected files
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
2. For each top-ranked file, use its `DesignFileFrontmatter.description` as the "Read
   first" context
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

Keep a static Navigation by Intent table in START_HERE for the most common tasks (generated
via Option 1 or Option 2), and add a `lexi navigate` command for ad-hoc queries that fall
outside the table.

**Static table**: 10-20 rows covering the most architecturally significant entry points.
Generated by an LLM with enriched inputs (Option 1 approach).

**Dynamic command**: For everything else. "The table doesn't cover what I need? Run
`lexi navigate <description>`."

**Quality**: Best of both worlds. The static table provides zero-query orientation for
common tasks; the dynamic command handles the long tail.

**Cost**: One LLM call per full update (for the static table). Zero cost for the dynamic
command.

**Freshness**: Static table updates on full rebuild. Dynamic command is always current.

**Implementation effort**: Highest total effort (both the enriched-input LLM pipeline and
the navigate command). But the components are independently useful and can be shipped
incrementally: navigate command first (lower risk), enriched static table second.

---

## What Makes a Good Navigation Table

### Analysis of the hand-maintained `blueprints/START_HERE.md` table

The hand-maintained table has 40 rows. Examining its patterns:

**Task column patterns**:
- Most rows start with "Add / modify" (14 rows) -- for extensible subsystems where the
  most common task is adding or changing a component
- "Modify" (12 rows) -- for subsystems where the task is changing existing behavior
- "Change" (10 rows) -- for configuration, schema, or format changes
- "Raise / handle" (1 row) -- unique framing for error handling
- "Install or modify" (1 row) -- for setup/installation tasks

The "Add / modify" pattern is used for subsystems that are designed to be extended
(CLI commands, language parsers, tokenizer backends, agent rules, validation checks).
"Modify" is used for pipeline/logic changes. "Change" is used for data model and format
changes. This verb choice signals to the agent whether they are adding something new or
changing something existing.

**Specificity**: Each row targets a single concern. Rows do not say "Work on the archivist"
(too vague) or "Modify ArchivistService.generate_design_file() method" (too specific).
The granularity is consistently at the subpackage or significant-file level.

**Disambiguation pairs**: The table explicitly distinguishes:
- Agent-facing CLI vs maintenance CLI
- Design file generation pipeline vs archivist LLM service vs change detection logic
- Structural indexing (no LLM) vs crawl logic (LLM-based)
- Link graph schema vs build pipeline vs queries vs health
- Validation checks vs report models vs orchestrator

These disambiguation pairs are critical for preventing mis-routing. They require knowledge
of the codebase architecture, not just file listings.

**Coverage**: Every top-level subpackage has at least one row. Many have 2-4 rows for
distinct concerns within the package. The table is approximately proportional to package
complexity: `archivist/` (3 rows), `linkgraph/` (4 rows), `cli/` (3 rows),
`artifacts/` (3 rows), `utils/` (4 rows).

### How many rows is optimal?

The hand-maintained table's 40 rows is likely near the upper bound for usefulness. An
agent scanning a table much longer than 40 rows may not find the matching entry faster
than doing a targeted search. The token cost is also relevant: at approximately 15-20
tokens per row, 40 rows consume ~700 tokens, which is a significant chunk of the
START_HERE budget.

For the LLM-generated version, a reasonable target is:

- **Small projects** (< 10 source files): 5-10 rows
- **Medium projects** (10-50 source files): 10-20 rows
- **Large projects** (50+ source files): 20-35 rows

The row count should scale with the number of distinct *concerns* in the project, not the
number of files. A project with 100 files but only 5 subpackages may need only 10-15 rows.

### How stable should the table be across updates?

The table should be *architecturally stable*: it should not change when a bug fix is
committed, but it should update when a new subpackage is added, a package is restructured,
or a significant new entry point is created. This aligns with the current trigger:
regeneration happens only on full `lexictl update`, not on `update --changed-only`.

The `existing_start_here` input in the BAML prompt serves this purpose -- the LLM is told
to "preserve relevant context" from the previous version, encouraging stability. However,
this mechanism is fragile: an LLM might still reorganize or rephrase rows across
regenerations, causing unnecessary churn.

---

## Open Questions

1. **Can we measure table quality?** The fundamental metric would be: given a task, does
   the table point the agent to the right file on the first try? This is hard to measure
   without agent telemetry. A proxy metric might be: for each row in the hand-maintained
   table, does the generated table produce an equivalent row? This gives a "gold standard
   coverage" score, but only for projects where a hand-maintained table exists.

2. **Should the table be regenerated on every full update or only when architecture
   changes?** Currently it regenerates on every `lexictl update` (full). If the inputs
   have not materially changed (same set of design files, same top-N in-degree files,
   same concept set), the output should be identical or near-identical. Could skip
   regeneration by hashing the inputs and comparing to the previous hash.

3. **Should Navigation by Intent be its own artifact (not embedded in START_HERE)?** If it
   becomes a separate file (e.g., `.lexibrary/NAVIGATION.md`), it could have its own
   regeneration lifecycle, its own staleness detection, and its own token budget. START_HERE
   would include a pointer to it. The downside is one more file for agents to discover.

4. **Could Stack post frequency data seed the task column?** If a project has 20 Stack
   posts and 8 of them are about authentication, that strongly suggests "Modify
   authentication" should be a navigation row. The question is whether Stack post volume
   is sufficient in practice. For new projects with no Stack posts, this data source is
   empty.

5. **Should the table differentiate between Lexibrary artifacts and source files as
   targets?** The hand-maintained table routes to design files in `blueprints/`. The
   generated version would route to design files in `.lexibrary/src/`. But should some rows
   route directly to source files (for projects without comprehensive design file coverage)?
   Or to directories (for large subsystems where no single file is the right starting
   point)?

6. **How should the table handle monorepos or multi-package projects?** A project with
   `packages/auth/`, `packages/billing/`, `packages/api/` has three largely independent
   concern areas. Should the table be structured hierarchically (package-level rows with
   sub-rows)? Or should it be flat with package prefixes in the task column?

7. **What is the interaction between Navigation by Intent and `lexi lookup`?** If an agent
   uses the navigation table to find a file and then runs `lexi lookup` on that file, the
   two should be complementary: the table gets the agent to the right area, `lexi lookup`
   provides the deep context. Should the navigation table rows be designed with this
   two-step flow in mind?

8. **Can the enriched-input approach degrade gracefully?** If a project has design files
   but no link graph (index not built), or a link graph but no concept files, the enriched
   inputs are partially available. The collector functions need to handle missing data
   sources without failing, falling back to billboard-only when richer inputs are unavailable.

---

## Relationship to Other Plans

### `plans/start-here-reamagined.md`

This document is a direct split from the "Open Thread: Navigation by Intent" section
(lines 276-304) of `start-here-reamagined.md`. The decisions made in that document frame
the context here:

- Navigation by Intent is the **only section proposed to remain LLM-generated** in the
  reimagined START_HERE
- Topology becomes procedural, Ontology becomes a pointer, Convention Index is removed,
  Navigation Protocol is removed
- This means Navigation by Intent carries more weight in the slimmer START_HERE -- it
  becomes the primary LLM-generated value-add of the document

### Dependency: Conventions as a first-class artifact

If conventions become their own artifact (as proposed in the conventions open thread of
`start-here-reamagined.md`), the navigation table may need rows that route to conventions.
For example: "Understand coding standards for this project -> run `lexi conventions`" or
"Check conventions before editing -> run `lexi lookup <file>`". This is a minor concern
but should be tracked.

### Dependency: `lexi navigate` command (Option 4/5)

If the dynamic `lexi navigate` command is implemented (as part of the hybrid Option 5),
the static table's role shifts from "comprehensive routing" to "common-case routing." The
table can afford to be smaller and more focused, deferring edge cases to the command. This
influences the row count target and the LLM prompt design.

### Relationship to `plans/lookup-upgrade.md` and `plans/search-upgrade.md`

The `lexi lookup` and `lexi search` commands are the primary query tools agents use for
navigating the knowledge layer. Navigation by Intent is a *pre-computed* navigation aid;
`lexi lookup` and `lexi search` are *on-demand* navigation aids. Improvements to lookup
(richer output, better formatting) and search (better relevance ranking) reduce the
pressure on the navigation table to be comprehensive.
