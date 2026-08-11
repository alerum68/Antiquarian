"""
Makes Archivist.py importable as a plain top-level module (matching how it's run
directly, e.g. `python Archivist.py`) when pytest is run from anywhere.

Also pins the env constants baked into the golden GEDCOM tests (see
Archivist/tests/golden/*.ged) BEFORE any module import triggers Utils.py's
load_dotenv()/os.getenv() reads, so the goldens are byte-identical on any
machine regardless of the developer's .env. Plain assignment (not setdefault)
deliberately overrides whatever load_dotenv would otherwise load.
"""

import os
import sys
from pathlib import Path

# Env constants encoded in the golden GEDCOM files (traced to Utils.py reads):
#   ORG_NAME          Utils.py:53  -> 1 TITL / 1 COPR / 1 NOTE (Michif Genealogical Society)
#   RESEARCHER        Utils.py:54  -> 1 NAME / 1 PUBL / 2 NAME/_TITL Researcher:
#   SUBM_ADDRESS      Utils.py:61  -> 2 ADDR in the @SUBM1@ record
#   MGS_GROUP_URL     Utils.py:62  -> _WEBTAG/_LINK "Facebook Group"
#   ANCESTRY_GROUP_URL Utils.py:63 -> _WEBTAG/_LINK "Ancestry Group"
#   ROOT_SOURCE_ID    Utils.py:64  -> 0 @S1@ SOUR / 1 SOUR @S1@
os.environ["ORG_NAME"] = "Michif Genealogical Society"
os.environ["RESEARCHER"] = "Jason Cole"
os.environ["SUBM_ADDRESS"] = "https://www.facebook.com/groups/149982655772008"
os.environ["MGS_GROUP_URL"] = "https://www.facebook.com/groups/149982655772008"
os.environ["ANCESTRY_GROUP_URL"] = "https://www.ancestry.com/groups/85343"
os.environ["ROOT_SOURCE_ID"] = "@S1@"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
