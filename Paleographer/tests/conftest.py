"""
Makes engine.py/postprocess.py importable as plain top-level modules (matching
how Paleographer.py itself imports them) when pytest is run from anywhere.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
