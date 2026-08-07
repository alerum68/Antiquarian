"""
Paleographer: thin dispatcher for AI-driven document extraction and Scrip-specific
enrichment.

Extraction (record-type-generic, driven entirely by the active .pmt file) lives in
Extract.py. Scrip-only enrichment (enrich, crosscheck, partition, resolve-names)
lives in ScripTools.py. Scriptorium.py launches this as a subprocess with
cwd=Paleographer/, so Extract.py and ScripTools.py import as plain sibling modules.
"""

import sys

ENRICHMENT_MODES = ("enrich", "crosscheck", "partition", "resolve-names")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ENRICHMENT_MODES:
        import ScripTools
        ScripTools.main()
    else:
        import Extract
        Extract.main()


if __name__ == "__main__":
    main()
