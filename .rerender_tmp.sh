#!/bin/bash
# Re-render all design files under src/lexibrary/<dir>
# Usage: bash rerender.sh <dir>
set -u
BASE="/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary"
DIR="${1:-}"
FAIL_LOG="/Users/shanngray/AI_Projects/Lexibrarian/.rerender_fail.log"
SUCCESS_LOG="/Users/shanngray/AI_Projects/Lexibrarian/.rerender_success.log"
: > "$FAIL_LOG"
: > "$SUCCESS_LOG"

count=0
total=$(find "$BASE/$DIR" -name '*.py' -not -path '*/baml_client/*' -not -path '*/__pycache__/*' 2>/dev/null | wc -l | tr -d ' ')
echo "Total files in $DIR: $total"

for f in $(find "$BASE/$DIR" -name '*.py' -not -path '*/baml_client/*' -not -path '*/__pycache__/*' 2>/dev/null | sort); do
  count=$((count+1))
  printf "[%d/%d] %s ... " "$count" "$total" "$f"
  if out=$(lexi design update --force "$f" 2>&1); then
    echo "$f" >> "$SUCCESS_LOG"
    echo "OK"
  else
    echo "$f" >> "$FAIL_LOG"
    echo "FAIL: $out"
    echo "FAIL: $out" >> "$FAIL_LOG"
  fi
done

echo "---"
echo "Success: $(wc -l < "$SUCCESS_LOG" | tr -d ' ')"
echo "Fail: $(wc -l < "$FAIL_LOG" | tr -d ' ')"
