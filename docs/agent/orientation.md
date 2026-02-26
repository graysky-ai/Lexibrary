# Orientation -- Session Start Protocol

Every session in a Lexibrary-managed codebase should begin with these three steps. They take less than a minute and prevent you from working blind.

## Step 1: Read `.lexibrary/TOPOLOGY.md`

This is the single most important file for orientation. Read it first.

```
cat .lexibrary/TOPOLOGY.md
```

`TOPOLOGY.md` contains the **project topology** -- an annotated directory tree showing every package and module with brief descriptions drawn from `.aindex` billboard summaries. The tree uses adaptive depth based on project scale:

- **Small projects** (10 or fewer directories): full tree with no filtering
- **Medium projects** (11--40 directories): depth limited to 2 levels plus hotspot directories
- **Large projects** (41+ directories): depth limited to 1 level plus hotspots and top directories by child count

After reading `TOPOLOGY.md`, you know the project structure and where to find things. For coding rules and navigation-by-intent, consult the project's agent rules file (e.g., `CLAUDE.md`, `.cursor/rules/`) which contains key constraints and intent-to-file mappings.

## Step 2: Check for IWH Signal Files

IWH (I Was Here) files are ephemeral signals left by a previous agent session to communicate incomplete work, warnings, or blocked tasks. They live in the `.lexibrary/` mirror tree (e.g., `.lexibrary/src/auth/.iwh` for the `src/auth/` directory).

Check for IWH signals across the project:

```
lexi iwh list
```

If signals are present, consume them for each directory:

```
lexi iwh read <directory>
```

The `read` command displays the signal contents and deletes it automatically. Each signal contains:

- **`scope`** -- the severity: `warning`, `incomplete`, or `blocked`
- **`author`** -- who created the signal
- **`created`** -- when the signal was created
- **Body** -- free-form markdown describing the situation

### How to Act on an IWH Signal

1. Run `lexi iwh read <directory>` to consume and understand the signal
2. Act on any instructions in the body (e.g., complete the incomplete work, address the warning)
3. If you cannot fully act on it, write a new signal: `lexi iwh write <directory> --scope incomplete --body "updated status"`

## Step 3: Get Library Health Overview

Run `lexi search` or `lexi concepts` to verify the library is accessible and understand what knowledge is available:

```
lexi concepts
```

This lists all concept files in the project, showing their name, status (active/draft/deprecated), tags, and a brief summary. It confirms the library is functional and gives you an overview of the project's vocabulary and architectural concepts.

If the operator has set up the `/lexi-orient` skill in your environment, you can run it as a single command that performs all three steps:

1. Reads `.lexibrary/TOPOLOGY.md`
2. Checks for IWH signals via `lexi iwh list`
3. Displays library health

## After Orientation

Once oriented, you are ready to work. Before editing any file:

1. Run `lexi lookup <file>` to read its design file, conventions, and dependents (see [Lookup Workflow](lookup-workflow.md))
2. After editing, update the design file to reflect your changes (see [Update Workflow](update-workflow.md))

These per-file steps are covered in the workflow documents linked above.
