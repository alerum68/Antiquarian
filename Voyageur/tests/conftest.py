"""
Makes FS.py importable as a plain top-level module (matching how it's run directly)
when pytest is run from anywhere.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
