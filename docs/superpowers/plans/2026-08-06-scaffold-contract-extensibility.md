# Scaffold Contract Extensibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Give Census a `.pmt` declaration file so `Commissioner.record_registry` recognizes it as a document type, proving the registry's existing `.pmt`-scanning mechanism generalizes to every record type without any code changes.

**Architecture:** Author `Paleographer/prompts/Census.pmt` with the same YAML front matter shape (`roles`, `extra_fields`) that `Parish.pmt`/`Scrip.pmt` already use, populated from the real field vocabulary `Voyageur/census_schema.py` and `Voyageur/field_maps/*.yaml` already produce. `Commissioner/record_registry.py` needs zero changes — it already scans every `.pmt` file it finds. This is validation-surface work only: nothing calls `parse_collection(..., "Census")` from live pipeline code yet.

**Tech Stack:** Python, Pydantic v2, pytest, YAML front matter.

## Global Constraints

- No changes to `Commissioner/models.py`, `Commissioner/fact_registry.py`, or `Commissioner/record_registry.py` — the `.pmt`-scanning mechanism already handles any file it finds.
- No changes to `Voyageur/census_schema.py`, `Voyageur/field_maps/*.yaml`, `Paleographer.py`, or `engine.py` — this plan only adds a declaration file; wiring it into a live gather or analysis run is later work.
- Full test suite must stay green after each task (`python -m pytest Commissioner/tests -q`, baseline 36 passing before this plan starts).
- No AI attribution or AI Assistant stamps in commits.

---

### Task 1: Author `Census.pmt` and make it visible to `record_registry`

**Files:**
- Create: `Paleographer/prompts/Census.pmt`
- Modify: `Commissioner/tests/test_record_registry.py:57-59` (the existing `test_unknown_document_type_raises` test hardcodes `"Census"` as its example of an *unrecognized* type — that assertion becomes false the moment `Census.pmt` exists, so it must be repointed at a type that will never exist, e.g. `"Wills"`)

**Interfaces:**
- Consumes: `Commissioner.record_registry._build_registry()` (already exists, unchanged) — scans `Paleographer/prompts/*.pmt`, keyed by `pmt_path.stem`.
- Produces: `get_document_types()` includes `"Census"`; `get_valid_roles("Census")` returns the frozenset of role names declared below; `validate_record_extra_fields("Census", {...})` / `validate_participant_extra_fields("Census", {...})` validate against the extra-fields models declared below.

- [ ] **Step 1: Fix the test that hardcodes "Census" as an unrecognized type**

`Commissioner/tests/test_record_registry.py:57-59` currently reads:

```python
def test_unknown_document_type_raises():
    with pytest.raises(UnknownDocumentTypeError, match="Census"):
        validate_record_extra_fields("Census", {})
```

Change it to use a type name that will never have a `.pmt` file:

```python
def test_unknown_document_type_raises():
    with pytest.raises(UnknownDocumentTypeError, match="Wills"):
        validate_record_extra_fields("Wills", {})
```

- [ ] **Step 2: Run the full Commissioner suite to confirm it still passes**

Run: `python -m pytest Commissioner/tests -q`
Expected: `36 passed` (same count as before — this step only changes what a test asserts against, not how many tests exist).

- [ ] **Step 3: Write failing tests for Census's registry entry**

Add to `Commissioner/tests/test_record_registry.py`, after `test_valid_roles_differ_by_document_type` (around line 68):

```python
def test_discovers_census_pmt_file():
    assert "Census" in get_document_types()


def test_census_record_extra_fields_validate():
    extra = validate_record_extra_fields(
        "Census",
        {
            "family_number": "12",
            "enumeration_district": "0042",
            "state": "Minnesota",
        },
    )
    assert extra.family_number == "12"
    assert extra.enumeration_district == "0042"
    assert extra.state == "Minnesota"


def test_census_participant_extra_fields_validate():
    extra = validate_participant_extra_fields(
        "Census", {"line_number": "7", "pid": "MXHY-ABC"}
    )
    assert extra.line_number == "7"
    assert extra.pid == "MXHY-ABC"


def test_census_roles_cover_standard_household_relationships():
    roles = get_valid_roles("Census")
    assert "Head" in roles
    assert "Wife" in roles
    assert "Son" in roles
    assert "Boarder" in roles
    assert "Coordinator" not in roles
```

- [ ] **Step 4: Run the new tests to verify they fail for the right reason**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -k census -v`
Expected: FAIL — `"Census" in get_document_types()` is false, and `validate_record_extra_fields("Census", ...)` raises `UnknownDocumentTypeError` (no `Census.pmt` exists yet).

- [ ] **Step 5: Author `Paleographer/prompts/Census.pmt`**

Create `Paleographer/prompts/Census.pmt` with this exact content:

```
---
roles:
  "1": {name: "Head", semantic: primary, context: "The householder on whose row the family/dwelling entry begins; the person to whom every other household member's relationship is recorded."}
  "2": {name: "Wife", semantic: spouse}
  "3": {name: "Husband", semantic: spouse}
  "4": {name: "Son", semantic: child}
  "5": {name: "Daughter", semantic: child}
  "6": {name: "Father", semantic: father}
  "7": {name: "Mother", semantic: mother}
  "8": {name: "Father-In-Law", semantic: father_in_law}
  "9": {name: "Mother-In-Law", semantic: mother_in_law}
  "10": {name: "Brother"}
  "11": {name: "Sister"}
  "12": {name: "Grandson"}
  "13": {name: "Granddaughter"}
  "14": {name: "Nephew"}
  "15": {name: "Niece"}
  "16": {name: "Cousin"}
  "17": {name: "Boarder"}
  "18": {name: "Servant"}
  "19": {name: "Lodger"}
  "0": {name: "Other", context: "Any household member whose relationship to the head doesn't match one of the above (e.g. partner, employee, ward, inmate of an institutional dwelling)."}
defaults:
  record:
    event_type: "Census (family)"
extra_fields:
  record:
    - {name: family_number, type: string}
    - {name: enumeration_district, type: string}
    - {name: roll_number, type: string}
    - {name: film_number, type: string}
    - {name: state, type: string}
    - {name: county, type: string}
    - {name: city, type: string}
    - {name: country, type: string}
    - {name: apid_db, type: string}
  participant:
    - {name: line_number, type: string}
    - {name: pid, type: string}
    - {name: extracted_url, type: string}
    - {name: fsftid, type: string}
    - {name: person_ark, type: string}
    - {name: familysearch_url, type: string}
---

You are an expert genealogist specializing in historical census enumeration
records (US federal census, Canadian census, and similar household-enumeration
schedules). You are given a scanned census image and the household/participant
data Voyageur already gathered from an online index (Ancestry or FamilySearch)
for that same image. Extract or correct the household entry into JSON, matching
the shared record schema (one record per household/dwelling, with a
participants[] array of individuals).

WHAT'S ALREADY KNOWN:
Every field already populated from the index is a transcriber's best effort at
reading the same image you're looking at now, not a guess - treat it as reliable
unless the image clearly shows otherwise. Your job is primarily to fill in what
the index left blank: a column the transcriber skipped, a person present on the
image but missing from the index entirely, or a field the index's table
structure has no place for at all (e.g. marginal notes, enumerator remarks,
a relationship-to-head value the index truncated or omitted).

READING THE IMAGE:
- Household grouping: every person on the same dwelling/family line range belongs
  to one record. Preserve the enumeration order as it appears on the page - it is
  itself genealogical evidence of household composition.
- Names: transcribe exactly as written, preserving spelling variants; do not
  standardize spelling. Use dit-names/aliases where the image shows one.
- Ages, birthplaces, occupations, and other per-person columns: read directly off
  the image's column headers for this schedule/year; column meaning varies by
  census year, so infer the year and schedule type from the image itself, not
  from an assumption.
- Relationship to head: use the role vocabulary declared above. If the image
  shows a relationship term not on that list, use "Other" and record the literal
  term in that participant's type_specific_fields so a human can review it.

CITATION FIELDS:
citation_text and citation_details describe what's on the image (enumeration
district, sheet/page number, dwelling and family numbers, date of enumeration)
- not a restatement of the household data itself, which belongs in the record
and participant fields.

Only extract what the image actually shows. Never infer a value the image does
not support, even if it would be historically plausible.
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -k census -v`
Expected: PASS — all 4 new tests green.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest Commissioner/tests -q`
Expected: `40 passed` (36 baseline + 4 new Census tests; the repointed `test_unknown_document_type_raises` still counts as 1 of the original 36).

- [ ] **Step 8: Commit**

```bash
git add Paleographer/prompts/Census.pmt Commissioner/tests/test_record_registry.py
git commit -m "Add Census.pmt so Commissioner's record_registry recognizes Census as a document type"
```

---

### Task 2: Round-trip `parse_collection()` against a realistic Census payload

**Files:**
- Modify: `Commissioner/tests/test_record_registry.py` (add after the Scrip round-trip tests, around line 299)

**Interfaces:**
- Consumes: `Commissioner.record_registry.parse_collection(raw_json: dict, document_type: str) -> Collection` (existing, unchanged); the `Census.pmt` declarations from Task 1.
- Produces: proof that a dict shaped exactly like `Voyageur/census_schema.py`'s real `normalize_census_pages()` output validates end-to-end through `parse_collection()`.

- [ ] **Step 1: Write a fixture payload matching `normalize_census_pages()`'s real output shape**

Add to `Commissioner/tests/test_record_registry.py`:

```python
SAMPLE_CENSUS_PAYLOAD = {
    "collection_title": "Test 1900 Census Collection",
    "sheets": [
        {
            "page_id": "12",
            "document_metadata": {
                "source_name": "United States Census (Population Schedule)",
                "source_location": "Minnesota, USA",
            },
            "records": [
                {
                    "page": "12",
                    "record_number": "4",
                    "event_type": "Census (family)",
                    "year": "1900",
                    "event_place": "Township of Example, Example County, Minnesota",
                    "citation_text": "",
                    "citation_details": "",
                    "review": False,
                    "continues_on_next_image": False,
                    "continues_from_previous_image": False,
                    "type_specific_fields": {
                        "family_number": "4",
                        "enumeration_district": "0042",
                        "state": "Minnesota",
                        "county": "Example County",
                    },
                    "participants": [
                        {
                            "role_name": "Head",
                            "std_given": "Baptiste",
                            "std_surname": "Gagnon",
                            "is_priest": False,
                            "sex": "M",
                            "age": "42",
                            "review": False,
                            "type_specific_fields": {"line_number": "17", "pid": "MXHY-ABC"},
                        },
                        {
                            "role_name": "Wife",
                            "std_given": "Marie",
                            "std_surname": "Gagnon",
                            "is_priest": False,
                            "sex": "F",
                            "age": "39",
                            "review": False,
                            "type_specific_fields": {"line_number": "18", "pid": "MXHY-ABD"},
                        },
                        {
                            "role_name": "Son",
                            "std_given": "Louis",
                            "std_surname": "Gagnon",
                            "is_priest": False,
                            "sex": "M",
                            "age": "12",
                            "review": False,
                            "type_specific_fields": {"line_number": "19", "pid": "MXHY-ABE"},
                        },
                    ],
                }
            ],
        }
    ],
}


def test_parse_collection_validates_census_payload_end_to_end():
    collection = parse_collection(SAMPLE_CENSUS_PAYLOAD, document_type="Census")
    record = collection.sheets[0].records[0]
    assert record.type_specific_fields["family_number"] == "4"
    participants = record.participants
    assert participants[0].role_name == "Head"
    assert participants[0].type_specific_fields["pid"] == "MXHY-ABC"
    assert participants[1].role_name == "Wife"
    assert participants[2].role_name == "Son"


def test_parse_collection_rejects_invalid_role_for_census():
    bad_payload = {
        **SAMPLE_CENSUS_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_CENSUS_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_CENSUS_PAYLOAD["sheets"][0]["records"][0],
                        "participants": [
                            {
                                **SAMPLE_CENSUS_PAYLOAD["sheets"][0]["records"][0]["participants"][0],
                                "role_name": "Coordinator",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    with pytest.raises(InvalidRoleError, match="Coordinator"):
        parse_collection(bad_payload, document_type="Census")
```

- [ ] **Step 2: Run the two new tests to verify they pass**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -k "census_payload or invalid_role_for_census" -v`
Expected: PASS — both tests green. (They should pass immediately since `Census.pmt` already exists from Task 1; this task adds coverage, it doesn't require new production code.)

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest Commissioner/tests -q`
Expected: `42 passed` (40 from Task 1 + these 2 new tests).

- [ ] **Step 4: Commit**

```bash
git add Commissioner/tests/test_record_registry.py
git commit -m "Add Census round-trip and invalid-role coverage to record_registry tests"
```

---

## Explicitly deferred (not part of this plan)

- **`unmapped` type_specific_fields key**: `census_schema.py`'s `_normalize_participant` stores unmapped source columns as a nested dict under `type_specific_fields["unmapped"]`. Commissioner's extra-field type map (`string`/`int`/`float`/`bool`/`date`/`enum`) has no type for a nested dict, and this plan's Global Constraints forbid changing `record_registry.py` to add one. `Census.pmt` does not declare an `unmapped` field, so a real Census record carrying unmapped columns will fail `parse_collection()` with `extra="forbid"` today. That's expected and acceptable: nothing in this plan calls `parse_collection()` from live Voyageur code, so no real gather is affected. Resolving it (likely by JSON-serializing `unmapped` to a string in `census_schema.py`, or declaring a different validation posture for Census) belongs to the sub-project that actually wires Voyageur's Census gather through `parse_collection()`.
- **Merge precedence between index data and Paleographer's image analysis** (index wins by default, token-saving; AI-overwrite is an opt-in setting) — belongs to the sub-project that wires Paleographer's analysis pass against the scaffold, per the design spec.
- **Wiring `Census.pmt` into an actual Paleographer or Voyageur run** — no `field_remap`/`settings_sections`/env-var plumbing is added in this plan, since nothing runs Census through Paleographer's CLI yet.
- **Role vocabulary gap for non-AI producers of `role_name`.** `Paleographer/prompts/Census.pmt`'s `roles` block is enforced by `Commissioner/record_registry.py`'s `validate_role_name()` as a hard allow-list. Census.pmt's own AI prose instructs the model to fall back to `"Other"` for a role it doesn't recognize, but `Voyageur/census_schema.py`'s index-sourced `role_name` (the raw source column value, title-cased) has no such fallback and no relationship-normalization step — so common census relationship terms not on Census.pmt's 21-entry list (e.g. Son-In-Law, Daughter-In-Law, Sister-In-Law, Brother-In-Law, Stepson, Stepdaughter, Grandfather, Grandmother, Aunt, Uncle, Roomer, Inmate, Patient, Ward, Housekeeper, Partner, Visitor, Half-Brother, and title-casing variants like "Mother in Law" vs "Mother-In-Law") would raise `InvalidRoleError` if actually run through `parse_collection()` today. No impact now since nothing calls `parse_collection()` from production code yet. Deferred to sub-project 2 (wiring Voyageur's Census gather to `parse_collection()`), which must decide whether to broaden Census.pmt's role list, or add a relationship-normalization step in `census_schema.py` with an `Other` fallback so index-sourced and AI-sourced `role_name` values converge on the same declared vocabulary.
- **Task 2's round-trip fixture is hand-shaped, not real Voyageur output.** `SAMPLE_CENSUS_PAYLOAD` in `Commissioner/tests/test_record_registry.py` proves a Census-shaped dict validates through `parse_collection()`, but it is not literally `normalize_census_pages()`'s output — it omits `facts` and `alternate_names` (which have their own validation shape in `Commissioner/models.py`) and the `unmapped` catch-all (already noted above as excluded from Census.pmt's declared fields). Deferred to sub-project 2, which should validate real Voyageur Census output directly, not just a shaped-alike fixture, so these gaps surface before they'd otherwise be found in production.
