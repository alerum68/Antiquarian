"""
Voyageur - the toolbox's Gather step.

Thin dispatcher: each repository gets its own sub-script (A.py for Ancestry, FS.py for
FamilySearch, LAC.py for Library and Archives Canada, and more Major Repositories to come),
so adding a new one never touches this file - only a new sub-script. Which one runs is
passed as the first CLI argument, the same convention Paleographer already uses for its own
debug-filename argument. "Merged" isn't a repository of its own - it's Merged.py, which
orchestrates A.py's and FS.py's gathers back-to-back and merges the results.
"""

import sys

SOURCES = ("A", "FS", "LAC", "Merged")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SOURCES:
        print(f"[ERROR] Usage: python Voyageur.py <source>, where <source> is one of: "
              f"{', '.join(SOURCES)}.")
        sys.exit(1)

    module = __import__(sys.argv[1])
    module.main()


if __name__ == "__main__":
    main()
