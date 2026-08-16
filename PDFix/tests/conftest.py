import sys
from pathlib import Path

# PDFix's folder and module share the same name, so unlike Paleographer/tests'
# convention (insert Paleographer/ so bare "import engine" finds Paleographer/engine.py),
# inserting PDFix/ here would collide with Paleographer/engine.py's own
# "from PDFix.PDFix import ..." package-style import. Insert the repo root instead, and
# import PDFix.PDFix the same way engine.py does, so both conventions coexist.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
