#!/usr/bin/env python3
"""Compatibility wrapper for querying the registered Lenny pack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    print(
        "[advisor-memory] search_lenny_pack.py is deprecated; prefer "
        "search_library_pack.py --pack-name lenny ...",
        file=sys.stderr,
    )
    script = Path(__file__).with_name("search_library_pack.py")
    argv = [sys.executable, str(script)]
    args = sys.argv[1:]
    if "--pack-name" not in args:
        argv.extend(["--pack-name", "lenny"])
    argv.extend(args)
    completed = subprocess.run(argv)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
