#!/usr/bin/env bash
# lexi-pre-edit.sh -- Claude Code PreToolUse hook
# Runs `lexi lookup` before file edits to inject design context.
#
# Output uses the hookSpecificOutput wrapper required by Claude Code:
#   {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "..."}}

set -euo pipefail

# Read tool input JSON from stdin
INPUT=$(cat)

# Extract file_path from the tool input
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Handle both Edit and Write tool input shapes
path = data.get('file_path') or data.get('path', '')
print(path)
" 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Run lexi lookup and capture output for additionalContext
LOOKUP_OUTPUT=$(lexi lookup "$FILE_PATH" 2>/dev/null || true)

if [ -n "$LOOKUP_OUTPUT" ]; then
    jq -n --arg ctx "$LOOKUP_OUTPUT" '{
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": $ctx
      }
    }'
fi

exit 0
