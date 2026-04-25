{hook_marker}
# — Lexibrary auto-update (installed by lexictl upgrade) —
CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD)
if [ -n "$CHANGED_FILES" ]; then
    lexictl update --changed-only $CHANGED_FILES >> .lexibrary/lexictl.log 2>&1 &
fi
# — end Lexibrary —
