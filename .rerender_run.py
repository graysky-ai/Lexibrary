#!/usr/bin/env python3
"""Re-render design files under src/lexibrary/<dir>.

Usage: python3 .rerender_run.py <dir-relative-to-src-lexibrary>
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: rerender_run.py <subdir>")
        return 2
    subdir = sys.argv[1]
    base = pathlib.Path("/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary")
    target_root = base / subdir
    if not target_root.exists():
        print(f"Not found: {target_root}")
        return 2

    log_dir = pathlib.Path("/Users/shanngray/AI_Projects/Lexibrarian")
    fail_log = log_dir / ".rerender_fail.log"
    ok_log = log_dir / ".rerender_success.log"

    files: list[pathlib.Path] = []
    if target_root.is_file():
        files = [target_root]
    else:
        for path in sorted(target_root.rglob("*.py")):
            parts = path.parts
            if "baml_client" in parts or "__pycache__" in parts:
                continue
            files.append(path)

    if not files:
        print(f"No .py files under {target_root}")
        return 0

    total = len(files)
    print(f"Total files in {subdir}: {total}")
    with fail_log.open("a", encoding="utf-8") as fl, ok_log.open("a", encoding="utf-8") as ol:
        for idx, f in enumerate(files, 1):
            print(f"[{idx}/{total}] {f} ... ", end="", flush=True)
            result = subprocess.run(
                ["lexi", "design", "update", "--force", str(f)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print("OK")
                ol.write(str(f) + "\n")
            else:
                first_line = (result.stderr or result.stdout or "").strip().splitlines()
                msg = first_line[0] if first_line else "FAIL (no message)"
                print(f"FAIL: {msg}")
                fl.write(f"{f}\t{msg}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
