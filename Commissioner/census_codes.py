"""
Decodes the numeric/letter codes the real Census Bureau enumerator recorded (and
FamilySearch's index carries alongside, or instead of, its own transcription) into
readable text, using the year-specific Commissioner/census_<year>_codes.json
dictionaries. Archivist/Census.py is the consumer - decoding happens at
GEDCOM-build time, never at gather time, so the JSON stays a raw capture and a
dictionary fix never requires re-gathering.
"""

import json
import os
from typing import Dict, Optional, Tuple

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_CODE_CACHE: Dict[int, Dict[str, Dict[str, str]]] = {}


def _load_year_codes(year: int) -> Dict[str, Dict[str, str]]:
    if year not in _CODE_CACHE:
        path = os.path.join(_MODULE_DIR, f"census_{year}_codes.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _CODE_CACHE[year] = json.load(f)
        except (OSError, json.JSONDecodeError):
            _CODE_CACHE[year] = {}
    return _CODE_CACHE[year]


def decode(year: int, item: str, code: Optional[str]) -> Optional[str]:
    """Looks up `code` under `item` in that year's census code dictionary. Returns
    None if the year has no dictionary file, the item doesn't exist, the code isn't
    found, or `code` is falsy - never raises for missing data."""
    if not code:
        return None
    return _load_year_codes(year).get(item, {}).get(str(code))


def decode_birthplace(year: int, code: Optional[str]) -> Tuple[Optional[str], bool]:
    """1950-style birthplace codes are either a bare Item_B1 (US) code, or a
    1-character Item_B3 citizenship prefix + Item_B2 (foreign) code. Tries the bare
    code against Item_B1 first; if that misses, strips the first character and
    tries the remainder against Item_B2. Returns (place, is_foreign) - (None, False)
    if neither resolves."""
    if not code:
        return None, False
    us_place = decode(year, "Item_B1_Birthplace_US", code)
    if us_place:
        return us_place, False
    if len(code) >= 2:
        foreign_place = decode(year, "Item_B2_Birthplace_Foreign", code[1:])
        if foreign_place:
            return foreign_place, True
    return None, False
