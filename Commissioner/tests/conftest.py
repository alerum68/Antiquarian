"""
Makes `Commissioner` importable as a package (e.g. `from Commissioner import models`)
when pytest is run from anywhere, the same way every other module's tests/conftest.py
puts its own module on sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
