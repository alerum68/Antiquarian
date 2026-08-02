"""
Makes lac_client.py importable as a plain top-level module when pytest is run from
anywhere, matching ScriptoriumMCP/tests/conftest.py's pattern.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
