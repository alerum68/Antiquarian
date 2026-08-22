# Census Code Normalization — Design

> Branch: `worktree-census-code-normalization` (isolated worktree)

## Problem

FamilySearch's 1950 census index carries two parallel representations for several
fields: free-text transcription (often blank, inconsistently abbreviated, or
occasionally wrong) and a numeric/letter code matching the real 1950 Census Bureau
coding scheme. Confirmed against a real gather
(`JSON/Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS.json`):

- **Occupation**: `type_specific_fields.occupation` is `None` for every participant in
  the sample — the only occupation signal that exists is a numeric code
  (`type_specific_fields.unmapped.MISC_CODE_C_1950_CENSUS`) currently never surfaced
  or decoded anywhere.
- **Industry** / **Class of Worker**: same pattern
  (`MISC_CODE_C1_1950_CENSUS` / `MISC_CODE_C2_1950_CENSUS`), also unused.
- **Education**: `facts[].value` for the Education fact type is a raw code
  (`"S8"`) that `get_education_value()` currently returns as-is, undecoded.
- **Race**: real values seen include both `"W"` and `"White"` for the same field
  across different records — FamilySearch's own indexing is inconsistent, and
  nothing normalizes the abbreviated form today.
- **Nationality/Birthplace**: `type_specific_fields.unmapped.MISC_CODE_B_1950_CENSUS`
  is a compound code (citizenship-status prefix + birthplace code) that, once
  decoded, caught a real transcription error the written text got wrong (a
  Pembina County, ND household surnamed "Stullangson" — an Icelandic patronymic —
  transcribed as born in "Ireland"; the code decodes to Iceland).

`Commissioner/census_1950_codes.json` (and the other `census_<year>_codes.json`
files) already carry the lookup tables needed to decode all of these — populated
during this same working session, verified against the real gather.

## Non-goals

- No change to Voyageur/FS.py or the gather-time JSON shape. The JSON stays a raw,
  undecoded capture of what was actually indexed — decoding happens only when
  building the GEDCOM, matching the existing pattern (`get_occupation_value`,
  `get_education_value`, `is_foreign_birthplace` already live in `Archivist/Census.py`,
  not the gatherer).
- No new review-flag mechanism for code/text disagreements in this round (e.g. the
  Ireland/Iceland case) — YAGNI per the user's direction ("just use the Codes when
  possible"); worth a future follow-up, not built now.
- No attempt to decode the `Occupation Category` letter codes (`h`/`wk`/`ot`/`u`) —
  confirmed to be a different, FamilySearch-internal scheme with no dictionary
  entry anywhere, unrelated to the real `Item_C_Occupation` numeric codes. Dropped
  from the occupation fallback chain entirely rather than used as raw, undecoded text.
- No hard restriction to the 1950 census year in the code itself — the decode
  function is year-parameterized and gracefully returns nothing for any
  year/item/code that isn't in the dictionary, so other years (1900-1940, which
  already have populated Occupation/Industry/Class-of-Worker tables) benefit
  automatically wherever their raw JSON happens to use the same
  `MISC_CODE_*_<year>_CENSUS` unmapped-key convention 1950 uses. That convention is
  unverified for other years - no code changes are gated on it, but accuracy for
  years other than 1950 is unverified until checked against a real gather.

## Design

### 1. `Commissioner/census_codes.py` — new module, owns the lookup

```python
def decode(year: int, item: str, code: str) -> Optional[str]:
    """Looks up `code` under `item` in that year's census code dictionary.
    Returns None if the year has no dictionary file, the item doesn't exist, the
    code isn't found, or `code` is falsy - never raises for missing data."""
```

Loads `Commissioner/census_<year>_codes.json` lazily and caches the parsed dict per
year (module-level cache) so repeated per-participant lookups during a large gather
don't re-read/re-parse JSON from disk every time.

`Archivist/Census.py` importing `from Commissioner import census_codes` is not a new
kind of cross-module dependency - `Voyageur/FS.py` and `Paleographer/Extract.py`
already do `from Commissioner import normalization` / `from Commissioner.record_registry
import ...` the same way, confirming the project root is reliably on `sys.path` for
this pattern already.

A second function handles the one compound-code case (birthplace/nationality). Its
return type is a `(value, is_foreign)` tuple, not a bare string - the caller (the
Nationality logic in Section 3) needs to know *which table* resolved the code, since
a US-birthplace hit must never produce a NATI fact while a foreign-birthplace hit
must:

```python
def decode_birthplace(year: int, code: str) -> Tuple[Optional[str], bool]:
    """1950-style birthplace codes are either a bare Item_B1 (US) code, or a
    1-character Item_B3 citizenship prefix + Item_B2 (foreign) code. Tries the bare
    code against Item_B1 first; if that misses, strips the first character and
    tries the remainder against Item_B2. Returns (place, is_foreign) - (None, False)
    if neither resolves."""
```

Confirmed against real data: `"091"` → Item_B1 directly → `("Washington", False)`;
`"161"` → Item_B1 miss → strip `"1"` → `"61"` → Item_B2 →
`("Canada -- English", True)`; `"V39"` → Item_B1 miss → strip `"V"` → `"39"` →
Item_B2 → `("Iceland", True)`.

### 2. Surface the unused code fields into DataFrame columns

`Archivist/Census.py`'s `build_census_dataframe_from_unified` (the function that
flattens `type_specific_fields` into row columns for every participant) gets new
column extractions alongside the existing ones, reading from the previously-ignored
`unmapped` sub-dict, keyed by the year-templated FamilySearch field name:

```python
unmapped = pts.get('unmapped') or {}
if unmapped.get(f'MISC_CODE_C_{census_year_str}_CENSUS'):
    row['Occupation Code'] = unmapped[f'MISC_CODE_C_{census_year_str}_CENSUS']
if unmapped.get(f'MISC_CODE_C1_{census_year_str}_CENSUS'):
    row['Industry Code'] = unmapped[f'MISC_CODE_C1_{census_year_str}_CENSUS']
if unmapped.get(f'MISC_CODE_C2_{census_year_str}_CENSUS'):
    row['Class of Worker Code'] = unmapped[f'MISC_CODE_C2_{census_year_str}_CENSUS']
if unmapped.get(f'MISC_CODE_B_{census_year_str}_CENSUS'):
    row['Birthplace Code'] = unmapped[f'MISC_CODE_B_{census_year_str}_CENSUS']
```

(`census_year_str` is already computed earlier in this function from
`record_type_name`.) This is purely additive - no existing column or behavior in
this function changes.

### 3. Consume the codes, code-first, in each fact builder

**Global Constraint (per explicit user direction): code-first, not code-fallback.**
When a code is present and decodes successfully, use the decoded value. Written/
transcribed text is the fallback for when no code exists or the code doesn't decode
- not the other way around. This reverses the initially-proposed
text-first-with-code-fallback design; the Ireland/Iceland finding is why.

- **`get_occupation_value`** (`Census.py:1056`): new priority order —
  1. Decoded `row['Occupation Code']` via `Commissioner.census_codes.decode(year, "Item_C_Occupation", code)`
  2. `Usual Occupation` (existing)
  3. `Occupation` (existing)
  4. `Trade or Profession` (existing)
  - `Occupation Category` is removed from this chain entirely (Non-goals).
  - `industry` (used later in the same function to build the "at Employer, working in
    Industry" string) gets the same treatment: decoded `row['Industry Code']` via
    `Item_C_Industry` first, else the existing `row.get('Industry')` text.
  - The `'Class of Worker'` note field (built separately, further down in the same
    function) gets the same treatment: decoded `row['Class of Worker Code']` via
    `Item_C_Class_Of_Worker` first, else existing `row.get('Class of Worker')` text.

- **`get_education_value`** (`Census.py:1093`): decode the raw grade code first
  (normalizing a literal `"O"` to `"0"` before lookup - confirmed by the user this
  is the correct mapping, not a separate code), via
  `Commissioner.census_codes.decode(year, "Education", code)`; fall back to the
  existing raw-value behavior only if decode returns `None` (e.g. a code not in the
  table, or an older year with no Education table yet).

- **Race** (`Census.py:1904-1905` writing `row['Race']`, and wherever that column is
  consumed for the `1 FACT ... 2 TYPE Race` GEDCOM line): decode the raw race value
  via `Commissioner.census_codes.decode(year, "Race", raw_value)` first; if the raw
  value isn't a known code (because it's already spelled out, e.g. `"White"`), fall
  back to the existing `capitalize_text_string` behavior. One path handles both the
  abbreviated and already-spelled-out cases without special-casing.

- **Nationality** (`Census.py:1627` `nat_val` logic): try
  `Commissioner.census_codes.decode_birthplace(year, row['Birthplace Code'])` first
  when that column is present, and branch on whether it actually resolved
  (`value is not None`), not just on `is_foreign`:
  - **Resolved, foreign** (`value` set, `is_foreign=True`): use `value` as `nat_val`
    directly - the code confirmed foreign birth and gave the place.
  - **Resolved, US** (`value` set, `is_foreign=False`): the code confirmed this
    person is *not* foreign-born - suppress `nat_val` entirely (no NATI fact),
    overriding any stale/incorrect `Nationality` text or foreign-looking
    `birth_place` string. The code is authoritative once it resolves at all, per
    the code-first constraint - it doesn't just supply a value, it can also rule
    one out.
  - **Unresolved** (`value is None` - no `Birthplace Code` column, or a code the
    dictionary doesn't have): fall back unchanged to the existing text-based logic
    - `row['Nationality']` text, else `birth_place` text when
    `is_foreign_birthplace(birth_place)` says so.

### 4. Verification

- Unit tests for `Commissioner/census_codes.py`: `decode()` for each item type
  (found, not found, unknown year, unknown item), `decode_birthplace()` for all
  three confirmed real cases (`"091"`→Washington/US, `"161"`→Canada--English/foreign,
  `"V39"`→Iceland/foreign) plus a fully-unresolvable code.
- Unit tests for each updated fact builder in `Census.py`, covering: code present
  and decodes (code wins even when text is also present - proves code-first, not
  just code-as-fallback), code present but unknown (falls back to text), no code at
  all (existing text-only behavior unchanged), neither code nor text (existing
  empty/absent behavior unchanged).
- Regenerate the real GEDCOM from `JSON/Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS.json`
  and hand-inspect: the "Stullangson" household's Nationality fact should now read
  "Iceland" (or however `Item_B2`'s `"Iceland"` gets rendered), not "Ireland"; the
  farmer household (`Occupation Code "100"`/`Industry Code "105"`/`Class of Worker
  Code "3"`) should render Occupation "Farmers (owners and tenants)", Industry
  "Agriculture" in the occupation note, and "Class of Worker: In own business" in
  the notes.
- Full `Archivist/tests/` and `Commissioner/tests/` suites green.

## Files touched

- `Commissioner/census_codes.py` — new file, `decode()` and `decode_birthplace()`.
- `Commissioner/tests/test_census_codes.py` — new test file.
- `Archivist/Census.py` — `build_census_dataframe_from_unified` (new column
  extraction), `get_occupation_value`, `get_education_value`, the Race fact-building
  line (~1904-1905 and wherever `row['Race']` is consumed), the Nationality logic
  (~1627).
- `Archivist/tests/test_census_ingestion.py` (or wherever the closest existing
  coverage for these functions lives) — updated/new tests for code-first behavior.
