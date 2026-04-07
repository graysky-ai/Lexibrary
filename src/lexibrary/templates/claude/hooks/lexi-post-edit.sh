#!/usr/bin/env bash
# lexi-post-edit.sh -- Claude Code PostToolUse hook
# Reminds agents to update design files after editing source files and
# suggests `lexi design update <file>` for missing or stale design files.
# After design-file guidance, runs `lexi impact` to warn about
# downstream dependents that may need updating.
#
# Output uses the hookSpecificOutput wrapper required by Claude Code:
#   {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}

set -euo pipefail

# Read tool input JSON from stdin
INPUT=$(cat)

# Extract file_path from the tool input
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
path = data.get('file_path') or data.get('path', '')
print(path)
" 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Skip non-source paths -- no action needed for library/config files
case "$FILE_PATH" in
    *.lexibrary/*|*blueprints/*|*.claude/*|*.cursor/*|*.git/*)
        exit 0
        ;;
esac

# Resolve project root (look for .lexibrary directory)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$PROJECT_DIR" ]; then
    # Fallback: walk up from the file to find .lexibrary
    DIR=$(dirname "$FILE_PATH")
    while [ "$DIR" != "/" ]; do
        if [ -d "$DIR/.lexibrary" ]; then
            PROJECT_DIR="$DIR"
            break
        fi
        DIR=$(dirname "$DIR")
    done
fi

# Accumulate the additionalContext message in BASE_MSG, emit once at the end.
BASE_MSG=""

# If no project root found, just emit a reminder and exit
if [ -z "$PROJECT_DIR" ] || [ ! -d "$PROJECT_DIR/.lexibrary" ]; then
    BASE_MSG="Run \`lexi design update <file>\` to regenerate the design file. If the command fails, write an IWH signal. Use \`lexi design comment\` to add rationale for behavioral, contract, or cross-file changes."
    jq -n --arg ctx "$BASE_MSG" '{
      "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": $ctx
      }
    }'
    exit 0
fi

# Resolve relative path from project root
REL_PATH=$(python3 -c "
import sys, os
file_path = os.path.abspath('$FILE_PATH')
project_dir = os.path.abspath('$PROJECT_DIR')
try:
    rel = os.path.relpath(file_path, project_dir)
    print(rel)
except ValueError:
    print('')
" 2>/dev/null || true)

if [ -z "$REL_PATH" ]; then
    exit 0
fi

# Check if design file already exists
DESIGN_FILE="$PROJECT_DIR/.lexibrary/designs/$REL_PATH.md"

if [ -f "$DESIGN_FILE" ]; then
    # Design file exists -- remind agent to keep it updated
    BASE_MSG="Run: lexi design update $REL_PATH -- to regenerate the design file. Use \`lexi design comment $REL_PATH --body \"...\"\` to add rationale for behavioral, contract, or cross-file changes."
else
    # Design file missing -- suggest generating via lexi design update
    BASE_MSG="No design file found for this source file. Run: lexi design update $REL_PATH -- to generate a design file via the archivist pipeline."
fi

# --- Dependents warning via lexi impact ---
# Run lexi impact to discover downstream files that import/depend on
# the edited file.  Failures are silently ignored (graceful degradation).
DEPENDENTS=""
if command -v lexi >/dev/null 2>&1; then
    DEPENDENTS=$(cd "$PROJECT_DIR" && lexi impact "$FILE_PATH" --depth 1 --quiet 2>/dev/null || true)
fi

# Append dependents list to additionalContext if non-empty
if [ -n "$DEPENDENTS" ]; then
    DEPENDENTS_WARNING="Dependents that may need updating: $DEPENDENTS"
    BASE_MSG="$BASE_MSG $DEPENDENTS_WARNING"
fi

# Emit the final combined additionalContext
jq -n --arg ctx "$BASE_MSG" '{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": $ctx
  }
}'

exit 0
