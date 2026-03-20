#!/usr/bin/env bash
# lexi-post-edit.sh -- Claude Code PostToolUse hook
# Auto-generates skeleton design files for new/edited source files and
# queues them for LLM enrichment.  Falls back to a reminder message when
# skeleton generation is not possible.
# After skeleton/reminder logic, runs `lexi impact` to warn about
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
    BASE_MSG="Remember to update the corresponding design file after editing source files. Set updated_by: agent in the frontmatter."
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
    BASE_MSG="Remember to update the corresponding design file after editing source files. Set updated_by: agent in the frontmatter."
else
    # Design file missing -- generate skeleton and queue for enrichment
    # Use lexictl update --skeleton which creates a quick skeleton (no LLM)
    # and appends the file to the enrichment queue.
    SKELETON_OUTPUT=$(cd "$PROJECT_DIR" && lexictl update --skeleton "$FILE_PATH" 2>&1 || true)

    if echo "$SKELETON_OUTPUT" | grep -q "Skeleton generated"; then
        BASE_MSG="Auto-generated skeleton design file for this source file and queued it for LLM enrichment. Set updated_by: agent in the frontmatter if you make further edits."
    else
        # Skeleton generation failed or not available -- fall back to reminder
        BASE_MSG="No design file found for this source file. Remember to update the corresponding design file after editing source files. Set updated_by: agent in the frontmatter."
    fi
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
