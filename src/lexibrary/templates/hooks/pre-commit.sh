{hook_marker}
# — Lexibrary pre-commit validation (installed by lexictl setup --hooks) —
if ! lexictl validate --ci --severity error; then
    echo ""
    echo "Lexibrary validation failed."
    echo "Fix the issues above, or bypass with: git commit --no-verify"
    exit 1
fi
# — end Lexibrary pre-commit —
