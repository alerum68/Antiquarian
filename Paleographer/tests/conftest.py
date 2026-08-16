"""
Makes engine.py/postprocess.py importable as plain top-level modules (matching
how Paleographer.py itself imports them) when pytest is run from anywhere.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Provide safe fallbacks so Extract.py can be imported during test discovery
os.environ.setdefault("MASTER_DB_NAME", "MasterDB.json")
os.environ.setdefault("MODEL_NAME", "AI Assistant-2.0-flash")
