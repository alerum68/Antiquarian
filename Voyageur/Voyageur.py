"""
Voyageur - thin dispatcher for the GUI's A/FS/LAC gather buttons.

Scriptorium.py launches this as a subprocess with cwd=Voyageur/ and the source code
(A/FS/LAC) as sys.argv[1], so A/FS/LAC import as plain sibling modules and each
provider's own main() sees exactly the CLI arguments Scriptorium.py meant for it.
"""

import sys

SOURCES = ("A", "FS", "LAC")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SOURCES:
        print(f"[ERROR] Usage: python Voyageur.py <source>, where <source> is one of: "
              f"{', '.join(SOURCES)}.")
        sys.exit(1)
    source = sys.argv[1]
    del sys.argv[1]
    if source == "A":
        import A
        A.main()
    elif source == "FS":
        import FS
        FS.main()
    elif source == "LAC":
        import LAC
        LAC.main()


if __name__ == "__main__":
    main()
