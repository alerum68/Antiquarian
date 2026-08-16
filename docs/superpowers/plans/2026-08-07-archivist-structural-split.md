# Archivist Structural Split Implementation Plan

> **Post-implementation note:** `ScripProfile.py` (named throughout this plan) was
> subsequently renamed to `Scrip.py` for naming consistency with `Census.py`/`General.py`.
> The `ScripProfile` class name is unchanged. References below to the filename are
> historical — read `ScripProfile.py` as `Scrip.py`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Split `Archivist/Archivist.py` (3,691 lines) into a thin dispatcher plus four sibling modules (`Utils.py`, `Census.py`, `General.py`, `ScripProfile.py`), replacing the file's `is_scrip` boolean-flag branching (10 read/write sites of `GENERAL_CONFIG['omit_source_id_prefix']`) with a `Profile` strategy-pattern polymorphism, mirroring the thin-dispatcher shape already established by `Voyageur.py` and `Paleographer.py`. No behavior change beyond the mechanism swap.

**Architecture:** `Archivist.py` becomes a ~55-line dispatcher: reads the JSON, decides census vs. general flavor, and for the general flavor looks up a `Profile` instance (`GeneralProfile` or `ScripProfile`) from a `PROFILE_REGISTRY` keyed on `record_type_name`, passing it into `General.run_general_flavor(data, profile)`. `Utils.py` holds record-type-agnostic helpers and constants shared read-only by both flavors. `Census.py` holds the household-grouping/CSV-shaped pipeline, unchanged. `General.py` defines the `Profile` `typing.Protocol` (17 methods, no data attribute — every behavioral difference is a method, not a flag check), the `GeneralProfile` implementation (today's non-Scrip behavior), and every function in the sheets/participants pipeline, each consulting a module-level `_ACTIVE_PROFILE` set by `run_general_flavor`. `ScripProfile.py` implements the same 17 methods for Scrip and owns the Scrip-only template/citation-field cluster; it may `import General`, never the reverse.

**Tech Stack:** Python, pandas, pytest.

## Global Constraints

- No behavior change to GEDCOM output for either flavor or either target software (RM/FTM) — every moved function is a verbatim lift; the Profile methods are extracted line-for-line from today's `is_scrip` branches, not rewritten. The only intentional exception: the `omit_source_id_prefix` flag mechanism itself is deleted, replaced by the Profile methods that implement the exact same branch outcomes.
- Full `pytest` suite stays green after every task.
- LAC-URL-adjacent code (`_scrip_template_field_value`'s `URL`/`RefNumber` branches, the `weblink_lines` calls that read `COLLECTION_URL`) is moved/read only — never executed against the live LAC site or via `LAC.py`/`BACLAC.py` during this work (standing constraint, unrelated AI Assistant issue #81159).
- No AI attribution, "Co-Authored-By", or AI Assistant stamps in commits.
- No comments restating what code does; only comments capturing non-obvious WHY (matches the existing file's own comment style — preserve existing WHY-comments verbatim when moving their attached code).
- Spec: `docs/superpowers/specs/2026-08-07-archivist-structural-split-design.md`.

---

## Symbol and constant allocation reference (verified by direct read + grep against `Archivist.py` before Task 1 started — do not re-derive)

### Module boundaries by line range (section banners confirmed via grep for `^def |^class |^# =`)

| Range | Banner / content | Destination |
|---|---|---|
| 1–29 | module docstring, imports, `CellValue` | split per-module (each module takes only the imports it uses) |
| 30–45 | `HouseholdUnit`, `FlagRecord` `TypedDict`s | **Census.py** — interleaving exception, see below |
| 46–129 | `CONFIGURATION` block, `get_env_int`, `safe_path` | split by constant, see "Constant ownership" table below |
| 130–187 | `SOURCE ID REGISTRY`: `_US_CENSUS_YEARS`, `_CANADIAN_CENSUS_YEARS`, `PRECODED_SOURCE_IDS`, `NEXT_AUTO_SOURCE_ID`, `SOURCE_ID_REGISTRY_PATH`, `resolve_source_id` | **Utils.py** — private implementation detail of `resolve_source_id`, which both flavors call |
| 190–206 | `ANCESTRY_START_RECORD_ID`...`REVIEW_THRESHOLD` (module constants, Census-only usage) | **Census.py** |
| 207–234 | `get_census_era`, `CENSUS_TEMPLATES`, `get_census_template_id`, `CENSUS_YEAR`, `CENSUS_ERA`, `CENSUS_SOURCE_ID` | **Census.py** |
| 237–257 | `GENERAL_CONFIG` dict (drop the `'omit_source_id_prefix'` key entirely — no longer used by anything) | **General.py** |
| 264–266 | `FACT_TYPES` JSON load | **Utils.py** — read by `get_event_gedcom_tag` (Utils.py) and `build_custom_fact_lines` (General.py) |
| 268–284 | `get_event_gedcom_tag`, `is_family_event` | **Utils.py** |
| 290–335 | `clean_val`, `_titlecase_callback`, `capitalize_text_string`, `clean_place` | **Utils.py** |
| 338–350 | `get_gender` | **Census.py** — interleaving exception, see below |
| 353–548 | `format_gedcom_date`, `get_proof_status`, `estimate_birth_from_age`, `wrap_text`, `resolve_gedcom_output_targets`, `resolve_gedcom_output_path`, `dedent_citation_lines`, `weblink_lines` | **Utils.py** |
| 554–1995 | `get_age` through `run_census_flavor` (household parsing, census citation/task building, `build_gedcom_from_census`, `load_census_dataframe`, `build_census_dataframe_from_unified`) | **Census.py** — interleaving exception at 1414, see below |
| 1999–2360 | `extract_volume`, `get_dynamic_source_id`, `get_by_semantic`, `get_all_by_semantic`, `get_role_name`, `resolve_family_links`, `assign_spouses_by_sex`, `evaluate_task_priority`, `generate_uid`, `generate_media_uid`, `generate_media_uid_for_path`, `generate_media_uid_for_lac_asset` | **General.py** — `get_dynamic_source_id`/`generate_uid` change under the Profile pattern, see Task 4 |
| 2362–2536 | `_SCRIP_TEMPLATES`, `_SCRIP_YEAR_RE`, `_scrip_record_year`, `select_scrip_template_id`, `resolve_scrip_template_id`, `_scrip_template_field_value`, `get_scrip_citation_fields`, `get_scrip_template_sources` | **ScripProfile.py** — Scrip-only cluster, physically interleaved inside the General.py-bound range |
| 2538–2620 | `_rmst_element_to_gedcom`, `load_source_template_lines`, `get_source_templates` | **General.py** |
| 2621–2635 | `generate_fam_uid` | **General.py** — changes under the Profile pattern, see Task 4 |
| 2641–3638 | `_build_citation_block` through `run_general_flavor` | **General.py** — the Profile-pattern conversion core, see Task 4 |
| 3639–3657 | `resolve_json_input` | **Archivist.py** (dispatcher) |
| 3662–3691 | `if __name__ == "__main__":` block | **Archivist.py** (dispatcher), see Task 6 |

Also note: `_SIMPLIFIED_CITATION_TEMPLATES` (referenced by `_SCRIP_TEMPLATES` at 2362–2364 as its sole consumer in the entire file) belongs in **ScripProfile.py** despite its generic-sounding name.

### Interleaving exceptions (physical location ≠ logical ownership — copy individually, never by bulk range)

1. **`get_gender`** (338–350) — physically sits inside the Utils.py-bound 290–548 range but is used only by census row processing. Move to **Census.py**.
2. **`split_full_name`** (1414–1424) — physically sits inside the Census.py-bound 554–1995 range but is a generic name-splitting helper with no census-specific logic. Move to **Utils.py**.
3. **`HouseholdUnit`/`FlagRecord`** (30–45) — physically the first symbols in the file (before the `CONFIGURATION` block) but used exclusively by `evaluate_child_match`, `find_parent`, `parse_household`, `resolve_cross_family_links`, `append_unit_if_not_empty`, `parse_household_relational` (all Census.py-bound). Move to **Census.py**.
4. **`_SCRIP_TEMPLATES` cluster** (2362–2536, listed above) — physically inside the General.py-bound 1999–2638 range but Scrip-only. Move to **ScripProfile.py**.

### Constant ownership (resolved by grepping every `global` statement in the file; Census and General flows never both run in one process, so each module safely owns an independent copy of any constant it mutates)

**Utils.py-owned, shared, read-only** (never appear in any `global` statement anywhere in the file): `ORG_NAME`, `RESEARCHER`, `SOFTWARE_NAME`, `SOFTWARE_VERS`, `COPYRIGHT_START`, `GEDCOM_NOTE`, `GEDCOM_CONC`, `REVIEW_COLOR`, `SUBM_ADDRESS`, `MGS_GROUP_URL`, `ANCESTRY_GROUP_URL`, `ROOT_SOURCE_ID`, `PROGRAM_DIR`, `RM_DIR`, `FTM_DIR`, `GEDCOM_OUTPUT_PATH`, `GEDCOM_OUTPUT_MODE`, `CURRENT_DATE`, `FACT_TYPES`.

**`GEDCOM_OUTPUT_NAME`**: lives in **Utils.py** (read by `Utils.resolve_gedcom_output_path`), but is mutated from **General.py** (`apply_record_type_field_remap`, `run_general_flavor`'s replacement logic) and from **Archivist.py**'s `__main__` (census path). Python's `global` only rebinds within the defining module, so every out-of-module writer must use qualified assignment: `Utils.GEDCOM_OUTPUT_NAME = "Scrip.ged"`, never a bare `global GEDCOM_OUTPUT_NAME` outside Utils.py.

**Census.py-owned, independently mutated** (own copy, own `global` inside `run_census_flavor`): `APID_DB` (own copy, seeded from a `"@A@"`-shaped default), `COLLECTION_NAME`, `COLLECTION_URL`, `PUBLISHER`, `PUB_LOC`, `CALL_NUMBER`, `REPOSITORY_LOC`, `REPOSITORY`, `IMAGE_DIR`. Census-exclusive with no cross-module use at all: `ANCESTRY_IMAGE_BASE_ID`, `BASE_ID`, `IMAGE_EXTENSION`, `FORM_TYPE`.

**General.py-owned, independently mutated** (own copy, own `global` inside `apply_record_type_field_remap` and `run_general_flavor`): `CALL_NUMBER`, `COLLECTION_URL`, `COLLECTION_NAME`, `REPOSITORY`, `REPOSITORY_LOC`, `IMAGE_DIR`. General.py does **not** own `PUBLISHER`/`PUB_LOC` — its own code never references them. General.py reads `APID_DB` **read-only** as `Utils.APID_DB` (only `_build_citation_block` reads it, never writes it from the General flow) — so `APID_DB`'s canonical read-only default lives in **Utils.py**, and only Census.py keeps an independently-mutated copy.

**Archivist.py (dispatcher)-owned**: `JSON_DIR`, `JSON_FILE` (used only inside `resolve_json_input`/`__main__`).

---

## `Profile` method reference (defined in Task 4, implemented by `GeneralProfile` in Task 4 and `ScripProfile` in Task 5 — copy these signatures verbatim into both classes)

```python
class Profile(Protocol):
    def dynamic_source_id(self, vol_digits: str) -> str: ...
    def participant_uid(self, identity: str, role: str, occ: int) -> Optional[str]: ...
    def family_uid(self, identity: str) -> Optional[str]: ...
    def citation_title(self, rec: dict, part: dict, tag_name: str, year: str,
                        document_type: Optional[str]) -> str: ...
    def citation_page(self, rec: dict, part: dict, page: str) -> str: ...
    def citation_template_id(self, rec: dict, vol: str) -> Optional[int]: ...
    def citation_proof_status(self, computed_status: str) -> str: ...
    def citation_detail_fields(self, rec: dict, part: dict, page: str, vol: str,
                                target_software: str) -> List[str]: ...
    def citation_text_block(self, rec: dict, part: dict, raw_orig: str, raw_trans: str) -> List[str]: ...
    def citation_uses_source_documents(self, rec: dict) -> bool: ...
    def primary_fact_date(self, rec: dict, is_primary: bool) -> str: ...
    def build_primary_event_lines(self, rec: dict, part: dict, event_tag: str, witnesses: List[dict],
                                   vol: str, media_uid: str, target_software: str, resi: str,
                                   alt_names: list, scrip_fact_date: str, raw_event_date: str,
                                   age: str) -> List[str]: ...
    def volume_source_detail_fields(self, v_clause: str) -> List[str]: ...
    def media_caption(self, sheet: dict, vol: str, pages: str) -> str: ...
    def resolve_source_templates(self, json_data: dict, target_software: str) -> List[str]: ...
    def repository_defaults(self) -> Tuple[str, str]: ...
    def default_gedcom_output_name(self) -> Optional[str]: ...
```

No boolean `is_scrip` attribute exists on `Profile` — every behavioral difference the original code branched on with `if is_scrip:` has a corresponding method above; keeping a redundant flag would reintroduce the pattern this split removes.

---

### Task 1: Golden-file regression fixtures

**Files:**
- Create: `Archivist/tests/golden/capture_golden_gedcom.py`
- Create (generated by the script, then committed): `Archivist/tests/golden/scrip_rm.ged`, `Archivist/tests/golden/scrip_ftm.ged`, `Archivist/tests/golden/parish_rm.ged`, `Archivist/tests/golden/parish_ftm.ged`

**Interfaces:**
- Consumes: today's unmodified `Archivist.build_gedcom_from_general(json_data: dict, target_software: str) -> str`.
- Produces: four `.ged` fixture files that Task 6's regression test diffs against, and the two `SCRIP_FIXTURE`/`PARISH_FIXTURE` dicts (importable from this module) that Task 6's test reuses to regenerate GEDCOM through the split modules.

- [ ] **Step 1: Write the capture script**

```python
"""Golden-file capture: runs build_gedcom_from_general on today's unmodified
Archivist.py against a Scrip fixture and a Parish fixture, for both target
software flavors, and writes the four outputs as committed .ged fixtures.
Task 6's regression test rebuilds the same fixtures through the post-split
modules and diffs byte-for-byte against these files - run this script again,
by hand, ONLY if a real (intentional) behavior change is made after the split;
never re-run it to make a failing regression test pass."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import Archivist as arc

GOLDEN_DIR = Path(__file__).resolve().parent

SCRIP_FIXTURE = {
    "collection_title": "Test Scrip Collection", "record_type_name": "Scrip",
    "sheets": [{
        "document_metadata": {"file_name": "BAC-LAC_fonandcol_1502188.pdf", "pages": "1", "file_type": "pdf"},
        "records": [{
            "event_type": "Scrip", "page": "1", "record_id": "SCRIP-5473", "year": "1880",
            "event_place": "Winnipeg",
            "type_specific_fields": {
                "claim_number": "3126", "affidavit_number": "5473",
                "scrip_number": "12761", "scrip_amount": "$160", "claim_basis": "Half-breed Head",
            },
            "source_documents": [
                {"document_type": "Scrip Certificate",
                 "media_path": "C:/Media/Commissioner/1502999/e099999999.pdf"},
            ],
            "participants": [
                {"role_semantic": "primary", "role_name": "Claimant", "role_number": "0",
                 "sex": "M", "std_given": "Roger", "std_surname": "Letendre",
                 "is_priest": False, "age": "35"},
                {"role_semantic": "witness", "role_name": "Witness", "role_number": "1",
                 "sex": "M", "std_given": "Baptiste", "std_surname": "Sabiston",
                 "is_priest": False, "age": ""},
            ],
        }],
    }],
}

PARISH_FIXTURE = {
    "collection_title": "St. Boniface Parish Register", "record_type_name": "Parish",
    "sheets": [{
        "document_metadata": {"file_name": "st_boniface_vol3_p12.pdf", "pages": "12",
                               "file_type": "pdf", "source_name": "St. Boniface"},
        "records": [{
            "event_type": "Baptism", "page": "12", "record_id": "REC-1", "year": "1875",
            "event_place": "St. Boniface, Manitoba", "vol": "3",
            "type_specific_fields": {"document_type": "Baptism Register"},
            "citation_text": "Le douze mars mil huit cent soixante-quinze...",
            "citation_details": "On the twelfth of March, eighteen seventy-five...",
            "participants": [
                {"role_semantic": "primary", "role_name": "Child", "role_number": "0",
                 "sex": "F", "std_given": "Marie", "std_surname": "Gagnon",
                 "is_priest": False, "age": ""},
                {"role_semantic": "father", "role_name": "Father", "role_number": "1",
                 "sex": "M", "std_given": "Jean", "std_surname": "Gagnon",
                 "is_priest": False, "age": ""},
                {"role_semantic": "mother", "role_name": "Mother", "role_number": "2",
                 "sex": "F", "std_given": "Josephte", "std_surname": "Nolin",
                 "is_priest": False, "age": ""},
                {"role_semantic": "witness", "role_name": "Priest", "role_number": "3",
                 "sex": "M", "std_given": "Georges", "std_surname": "Dugas",
                 "is_priest": True, "age": ""},
            ],
        }],
    }],
}


def main() -> None:
    arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
    (GOLDEN_DIR / "scrip_rm.ged").write_text(
        arc.build_gedcom_from_general(SCRIP_FIXTURE, "RM"), encoding="utf-8")
    (GOLDEN_DIR / "scrip_ftm.ged").write_text(
        arc.build_gedcom_from_general(SCRIP_FIXTURE, "FTM"), encoding="utf-8")

    arc.GENERAL_CONFIG['omit_source_id_prefix'] = False
    (GOLDEN_DIR / "parish_rm.ged").write_text(
        arc.build_gedcom_from_general(PARISH_FIXTURE, "RM"), encoding="utf-8")
    (GOLDEN_DIR / "parish_ftm.ged").write_text(
        arc.build_gedcom_from_general(PARISH_FIXTURE, "FTM"), encoding="utf-8")
    print(f"Wrote 4 golden files to {GOLDEN_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the capture script against today's unmodified `Archivist.py`**

Run: `cd Archivist && python tests/golden/capture_golden_gedcom.py`
Expected: prints `Wrote 4 golden files to ...`; `scrip_rm.ged`, `scrip_ftm.ged`, `parish_rm.ged`, `parish_ftm.ged` now exist under `Archivist/tests/golden/`.

- [ ] **Step 3: Manually inspect the four files**

Confirm `scrip_rm.ged`/`scrip_ftm.ged` contain `_TITL`/`PAGE` lines shaped like the Scrip branch (e.g. `3 _TITL Letendre, Roger: Claim: 3126; Affidavit: 5473; Scrip: 12761`) and `3 QUAY 3` / proven proof status; confirm `parish_rm.ged`/`parish_ftm.ged` contain the generic `3 _TITL Gagnon, Marie, BAPM, 1875` shape and both a `4 TEXT` (French) and `3 NOTE`/`4 CONT` (English translation) block. This confirms the fixtures actually exercise both branches before they're frozen as golden files.

- [ ] **Step 4: Commit**

```bash
git add Archivist/tests/golden/capture_golden_gedcom.py Archivist/tests/golden/scrip_rm.ged Archivist/tests/golden/scrip_ftm.ged Archivist/tests/golden/parish_rm.ged Archivist/tests/golden/parish_ftm.ged
git commit -m "test: capture golden GEDCOM fixtures ahead of Archivist structural split"
```

---

### Task 2: Create `Utils.py`

**Files:**
- Create: `Archivist/Utils.py`
- Test: `Archivist/tests/test_utils.py` (new)

**Interfaces:**
- Consumes: nothing from other split modules (Utils.py is the dependency floor).
- Produces: `get_env_int`, `safe_path`, `resolve_source_id`, `get_event_gedcom_tag`, `is_family_event`, `clean_val`, `capitalize_text_string`, `clean_place`, `split_full_name`, `format_gedcom_date`, `get_proof_status`, `estimate_birth_from_age`, `wrap_text`, `resolve_gedcom_output_targets`, `resolve_gedcom_output_path`, `dedent_citation_lines`, `weblink_lines`, plus module constants `FACT_TYPES`, `GEDCOM_OUTPUT_NAME` (mutable, see constant-ownership note above), `PROGRAM_DIR`, `RM_DIR`, `FTM_DIR`, `GEDCOM_OUTPUT_PATH`, `GEDCOM_OUTPUT_MODE`, `CURRENT_DATE`, `ORG_NAME`, `RESEARCHER`, `SOFTWARE_NAME`, `SOFTWARE_VERS`, `COPYRIGHT_START`, `GEDCOM_NOTE`, `GEDCOM_CONC`, `REVIEW_COLOR`, `SUBM_ADDRESS`, `MGS_GROUP_URL`, `ANCESTRY_GROUP_URL`, `ROOT_SOURCE_ID`, `APID_DB` (read-only canonical default).

- [ ] **Step 1: Create `Archivist/Utils.py`**

Move verbatim from `Archivist.py`, using the module boundary table above:
- Lines 11–27 imports actually used by the moved code (`calendar`, `datetime`, `hashlib` is NOT needed here — only General.py's UID hashing needs it — `json`, `os`, `re`, `Path`, `Dict`, `List`, `Optional`, `Tuple`, `Union`, `yaml`, `load_dotenv`, `titlecase`, `CellValue`); add `import re` explicitly since `clean_place`/`_titlecase_callback` need it.
- The Utils.py-owned constants from the "Constant ownership" table (`ORG_NAME` through `ROOT_SOURCE_ID`, `PROGRAM_DIR`, `RM_DIR`, `FTM_DIR`, `GEDCOM_OUTPUT_PATH`, `GEDCOM_OUTPUT_MODE`, `CURRENT_DATE`, `GEDCOM_OUTPUT_NAME`), `get_env_int` (61–67), `safe_path` (69–79) — exact `os.getenv(...)` defaults preserved verbatim.
- Lines 130–187 (`SOURCE ID REGISTRY` block) verbatim, including `resolve_source_id`.
- Lines 264–266 (`FACT_TYPES` JSON load) verbatim.
- Lines 268–284 (`get_event_gedcom_tag`, `is_family_event`) verbatim.
- Lines 290–335 (`clean_val`, `_titlecase_callback`, `PRESERVED_ACRONYMS`, `_PLACE_QUALIFIER_RE`, `capitalize_text_string`, `clean_place`) verbatim.
- Line 1414–1424 (`split_full_name`) — interleaving exception, moved here even though it's physically inside the Census.py range.
- Lines 353–548 (`format_gedcom_date`, `get_proof_status`, `estimate_birth_from_age`, `wrap_text`, `resolve_gedcom_output_targets`, `resolve_gedcom_output_path`, `dedent_citation_lines`, `weblink_lines`) verbatim — note `resolve_gedcom_output_path` reads `GEDCOM_OUTPUT_NAME` as a plain module-level name here (it's defined in this same module, so no qualification needed inside Utils.py itself).
- `APID_DB`'s canonical read-only default (find its `os.getenv`-based definition in the `CONFIGURATION` block and confirm via grep — `APID_DB` is not in this plan's already-read line ranges, so grep `^APID_DB` in the original file before moving; it is Utils.py-owned per the ownership table).

- [ ] **Step 2: Add `Archivist/tests/test_utils.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import Utils


def test_clean_val_strips_and_stringifies():
    assert Utils.clean_val("  Jean  ") == "Jean"
    assert Utils.clean_val(None) == ""


def test_get_event_gedcom_tag_person_and_family_buckets():
    assert Utils.get_event_gedcom_tag("Baptism") == "BAPM"
    assert Utils.get_event_gedcom_tag("Marriage") == "MARR"
    assert Utils.get_event_gedcom_tag("Some Future Fact Type") == "EVEN"


def test_split_full_name_splits_on_last_space():
    assert Utils.split_full_name("Jean Baptiste Gagnon") == ("Jean Baptiste", "Gagnon")


def test_resolve_source_id_returns_precoded_value_for_known_census_year():
    assert Utils.resolve_source_id("Census_1881") == Utils.PRECODED_SOURCE_IDS["Census_1881"]
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd Archivist && pytest tests/test_utils.py -v`
Expected: PASS (4 tests)

- [ ] **Step 4: Commit**

```bash
git add Archivist/Utils.py Archivist/tests/test_utils.py
git commit -m "refactor: extract Utils.py from Archivist.py"
```

---

### Task 3: Create `Census.py`

**Files:**
- Create: `Archivist/Census.py`
- Test: repoint existing census tests (done in Task 7, not here — this task only creates the module and confirms it imports cleanly)

**Interfaces:**
- Consumes: `Utils.get_env_int`, `Utils.safe_path`, `Utils.clean_val`, `Utils.cap_case`, `Utils.clean_place`, `Utils.format_gedcom_date`, `Utils.get_proof_status`, `Utils.estimate_birth_from_age`, `Utils.wrap_text`, `Utils.resolve_gedcom_output_targets`, `Utils.resolve_gedcom_output_path`, `Utils.dedent_citation_lines`, `Utils.weblink_lines`, `Utils.get_event_gedcom_tag`, `Utils.is_family_event`, `Utils.resolve_source_id`, `Utils.GEDCOM_OUTPUT_NAME`, `Utils.ROOT_SOURCE_ID`, `Utils.ORG_NAME`, `Utils.RESEARCHER`, `Utils.SOFTWARE_NAME`, `Utils.SOFTWARE_VERS`, `Utils.COPYRIGHT_START`, `Utils.GEDCOM_NOTE`, `Utils.GEDCOM_CONC`, `Utils.SUBM_ADDRESS`, `Utils.CURRENT_DATE`.
- Produces: `run_census_flavor(data: dict) -> None` (called by Archivist.py's dispatcher), plus `build_gedcom_from_census`, `load_census_dataframe`, `build_census_dataframe_from_unified`, `get_gender`, `split_full_name` re-export not needed (Census.py calls `Utils.split_full_name` directly).

- [ ] **Step 1: Create `Archivist/Census.py`**

`import Utils` at the top; every reference to a Utils.py-owned constant or function is qualified (`Utils.clean_val(...)`, `Utils.GEDCOM_OUTPUT_NAME`, etc.) since these are cross-module now. Move verbatim, using the module boundary table above:
- Lines 30–45 (`HouseholdUnit`, `FlagRecord`) — interleaving exception.
- Lines 190–234 (`ANCESTRY_START_RECORD_ID` through `CENSUS_SOURCE_ID`) — Census.py's own copy of `CALL_NUMBER`, `COLLECTION_URL`, `COLLECTION_NAME`, `REPOSITORY`, `REPOSITORY_LOC`, `PUBLISHER`, `PUB_LOC`, `IMAGE_DIR`, `APID_DB`, `ANCESTRY_IMAGE_BASE_ID`, `BASE_ID`, `IMAGE_EXTENSION`, `FORM_TYPE` per the constant-ownership table (grep each `os.getenv` default from the original `CONFIGURATION` block at 46–129 and reproduce it here verbatim — these constants physically live in the `CONFIGURATION` block but are Census.py-owned by usage, another interleaving instance the implementer must grep for, not assume from the block's physical boundaries).
- Line 338–350 (`get_gender`) — interleaving exception.
- Lines 554–1995 (`get_age` through `run_census_flavor`) verbatim, **except** line 1414–1424 (`split_full_name`, moved to Utils.py in Task 2 — replace internal calls with `Utils.split_full_name(...)`).
- Every bare reference inside these moved functions to a name now owned by Utils.py (`clean_val`, `capitalize_text_string`, `clean_place`, `format_gedcom_date`, `get_proof_status`, `estimate_birth_from_age`, `wrap_text`, `resolve_gedcom_output_targets`, `resolve_gedcom_output_path`, `dedent_citation_lines`, `weblink_lines`, `get_event_gedcom_tag`, `is_family_event`, `resolve_source_id`, `GEDCOM_OUTPUT_NAME`, `ROOT_SOURCE_ID`, `ORG_NAME`, `RESEARCHER`, `SOFTWARE_NAME`, `SOFTWARE_VERS`, `COPYRIGHT_START`, `GEDCOM_NOTE`, `GEDCOM_CONC`, `SUBM_ADDRESS`, `CURRENT_DATE`, `get_env_int`, `safe_path`) becomes `Utils.<name>`. `run_census_flavor`'s `global GEDCOM_OUTPUT_NAME` (if present — grep to confirm before moving) becomes a qualified `Utils.GEDCOM_OUTPUT_NAME = ...` assignment, not a `global` statement, per the cross-module mutation rule.

- [ ] **Step 2: Verify the module imports cleanly and `run_census_flavor` is reachable**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import Census


def test_census_module_imports_and_exposes_run_census_flavor():
    assert callable(Census.run_census_flavor)
```

Save as `Archivist/tests/test_census_module_smoke.py`.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd Archivist && pytest tests/test_census_module_smoke.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_module_smoke.py
git commit -m "refactor: extract Census.py from Archivist.py"
```

---

### Task 4: Create `General.py` — the `Profile` pattern

**Files:**
- Create: `Archivist/General.py`
- Test: `Archivist/tests/test_general_smoke.py` (new, minimal — full coverage comes from Task 7's repointed tests and Task 8's new Profile tests)

**Interfaces:**
- Consumes: `Utils.*` (same set as Census.py, plus `Utils.FACT_TYPES`, `Utils.APID_DB` read-only, `Utils.PROGRAM_DIR`).
- Produces: `Profile` (the `typing.Protocol` from the reference section above), `GeneralProfile` class, `_ACTIVE_PROFILE` module global, `set_active_profile(profile: Profile) -> None`, `run_general_flavor(data: dict, profile: Profile) -> None`, plus every unchanged function in the 1999–2638 and 2641–3638 ranges (`get_dynamic_source_id`, `get_by_semantic`, `get_all_by_semantic`, `get_role_name`, `resolve_family_links`, `assign_spouses_by_sex`, `evaluate_task_priority`, `generate_uid`, `generate_media_uid`, `generate_media_uid_for_path`, `generate_media_uid_for_lac_asset`, `_rmst_element_to_gedcom`, `load_source_template_lines`, `get_source_templates`, `generate_fam_uid`, `_build_citation_block`, `build_general_citation`, `build_custom_fact_lines`, `build_witness_links`, `build_individual`, `build_family`, `get_source_root`, `get_volume_sources`, `build_gedcom_from_general`, `apply_record_type_field_remap`, `apply_extracted_parish_name`, `apply_resolved_source_id`), used by both `ScripProfile.py` (one-way import) and `Archivist.py` (dispatcher).

- [ ] **Step 1: Move the unchanged functions verbatim**

`import Utils` at the top plus `import hashlib`, `import re`, `import xml.etree.ElementTree as ET`, `from pathlib import Path`, `from typing import Dict, List, Optional, Protocol, Tuple`. Move verbatim from `Archivist.py`, qualifying every Utils.py-owned reference as `Utils.<name>`:
- Lines 1999–2030 (`extract_volume`, `get_by_semantic`) — `get_dynamic_source_id` (2014–2027) changes, see Step 2.
- Lines 2042–2211 (`get_all_by_semantic`, `get_role_name`, `resolve_family_links`, `assign_spouses_by_sex`, `evaluate_task_priority`, `generate_media_uid`, `generate_media_uid_for_path`, `generate_media_uid_for_lac_asset`) — `generate_uid` (2128–2190) changes, see Step 2.
- Lines 2538–2620 (`_rmst_element_to_gedcom`, `load_source_template_lines`, `get_source_templates`).
- `build_custom_fact_lines` (2842–2859), `build_witness_links` (2862–2877) — unconditional, no `is_scrip` reference.
- `build_family` (3193–3290), `get_source_root` (3291–3300) — unconditional.
- `apply_extracted_parish_name` (3563–3590), `apply_resolved_source_id` (3592–3603) — unconditional, qualify `clean_val`/`resolve_source_id` as `Utils.clean_val`/`Utils.resolve_source_id`.
- `GENERAL_CONFIG` dict (237–257) verbatim, **minus** the `'omit_source_id_prefix'` key.

- [ ] **Step 2: Define the `Profile` Protocol and `GeneralProfile`**

```python
class Profile(Protocol):
    def dynamic_source_id(self, vol_digits: str) -> str: ...
    
    def participant_uid(self, identity: str, role: str, occ: int) -> Optional[str]: ...
    
    def family_uid(self, identity: str) -> Optional[str]: ...
    
    def citation_title(self, rec: dict, part: dict, tag_name: str, year: str, document_type: Optional[str]) -> str: ...
    
    def citation_page(self, rec: dict, part: dict, page: str) -> str: ...
    
    def citation_template_id(self, rec: dict, vol: str) -> Optional[int]: ...
    
    def citation_proof_status(self, computed_status: str) -> str: ...
    
    def citation_detail_fields(self, rec: dict, part: dict, page: str, vol: str, target_software: str) -> List[str]: ...
    
    def citation_text_block(self, rec: dict, part: dict, raw_orig: str, raw_trans: str) -> List[str]: ...
    
    def citation_uses_source_documents(self, rec: dict) -> bool: ...
    
    def primary_fact_date(self, rec: dict, is_primary: bool) -> str: ...
    
    def build_primary_event_lines(self, rec: dict, part: dict, event_tag: str, witnesses: List[dict], vol: str,
                                  media_uid: str, target_software: str, resi: str, alt_names: list,
                                  scrip_fact_date: str, raw_event_date: str, age: str) -> List[str]: ...
    
    def volume_source_detail_fields(self, v_clause: str) -> List[str]: ...
    
    def media_caption(self, sheet: dict, vol: str, pages: str) -> str: ...
    
    def resolve_source_templates(self, json_data: dict, target_software: str) -> List[str]: ...
    
    def repository_defaults(self) -> Tuple[str, str]: ...
    
    def default_gedcom_output_name(self) -> Optional[str]: ...


def _build_generic_primary_event_lines(rec: dict, part: dict, event_tag: str, witnesses: List[dict], vol: str,
                                       media_uid: str, target_software: str, alt_names: list, raw_event_date: str,
                                       age: str) -> List[str]:
    """The non-Scrip primary-event GEDCOM block (today's `Archivist.py:3138-3158`
    else-branch). Exposed as a module function, not only a GeneralProfile method,
    because ScripProfile.build_primary_event_lines also needs it verbatim for the
    non-EVEN case (today's `if is_scrip and event_tag == 'EVEN':` only special-cased
    EVEN - every other event_tag fell through to this same generic block even when
    is_scrip was True)."""
    event_type = Utils.clean_val(rec.get('event_type'))
    lines = []
    event_value = ""
    if event_tag == 'EVEN':
        extra_fields = rec.get('type_specific_fields') or {}
        value_parts = [f"{k.replace('_', ' ').title()}: {Utils.clean_val(v)}" for k, v in extra_fields.items() if
                       k != 'document_type' and Utils.clean_val(v)]
        event_value = f" {'; '.join(value_parts)}" if value_parts else ""
    lines.append(f"1 {event_tag}{event_value}")
    if event_tag == 'EVEN':
        lines.append(f"2 TYPE {Utils.capitalize_text_string(event_type)}")
    if raw_event_date:
        lines.append(f"2 DATE {Utils.format_gedcom_date(raw_event_date)}")
    lines.append(f"2 PLAC {Utils.clean_place(rec.get('event_place')) or GENERAL_CONFIG['default_location']}")
    if age:
        lines.append(f"2 AGE {age}")
    if alt_names:
        alt_values = ", ".join(Utils.clean_val(a.get('value')) for a in alt_names)
        lines.append(f"2 NOTE Margin note suggests alternate spelling: {alt_values}")
    lines.extend(build_witness_links(rec, witnesses, vol, target_software))
    lines.extend(build_general_citation(rec, part, event_tag, vol, media_uid, Utils.get_proof_status(raw_event_date),
                                        target_software))
    return lines


class GeneralProfile:
    def dynamic_source_id(self, vol_digits: str) -> str:
        base_id = re.sub(r'\D', '', f"{GENERAL_CONFIG.get('register_source_id', '1')}")
        if base_id.endswith('001') and len(base_id) > 1:
            base_id = base_id[:-3]
        return f"@S{base_id or '1'}{vol_digits.zfill(3)}@"
    
    def participant_uid(self, identity: str, role: str, occ: int) -> Optional[str]:
        return None
    
    def family_uid(self, identity: str) -> Optional[str]:
        return None
    
    def citation_title(self, rec: dict, part: dict, tag_name: str, year: str, document_type: Optional[str]) -> str:
        std_g = Utils.clean_val(part.get('std_given'))
        std_s = Utils.clean_val(part.get('std_surname'))
        titl = f"3 _TITL {std_s}, {std_g}, {tag_name}, {year}"
        if document_type:
            titl += f" -- {Utils.capitalize_text_string(document_type)}"
        return titl
    
    def citation_page(self, rec: dict, part: dict, page: str) -> str:
        rec_id = Utils.clean_val(rec.get('record_id')) or 'Unknown'
        type_fields = rec.get('type_specific_fields') or {}
        claim_num = Utils.clean_val(type_fields.get('claim_number'))
        affdt_num = Utils.clean_val(type_fields.get('affidavit_number'))
        ref_bits = [b for b in (f"Claim {claim_num}" if claim_num else "", f"Affdt {affdt_num}" if affdt_num else "") if
                    b]
        if ref_bits:
            return f"3 PAGE {'; '.join(ref_bits)}, Page {page}"
        return f"3 PAGE Page {page}, Record {rec_id}"
    
    def citation_template_id(self, rec: dict, vol: str) -> Optional[int]:
        return None
    
    def citation_proof_status(self, computed_status: str) -> str:
        return computed_status
    
    def citation_detail_fields(self, rec: dict, part: dict, page: str, vol: str, target_software: str) -> List[str]:
        if target_software != "RM":
            return []
        std_g = Utils.clean_val(part.get('std_given'))
        std_s = Utils.clean_val(part.get('std_surname'))
        rec_id = Utils.clean_val(rec.get('record_id')) or 'Unknown'
        type_fields = rec.get('type_specific_fields') or {}
        claim_num = Utils.clean_val(type_fields.get('claim_number'))
        affdt_num = Utils.clean_val(type_fields.get('affidavit_number'))
        ref_bits = [b for b in (f"Claim {claim_num}" if claim_num else "", f"Affdt {affdt_num}" if affdt_num else "") if
                    b]
        person_name = f"{std_g} {std_s}".strip()
        parish_loc = Utils.clean_val(GENERAL_CONFIG.get('parish_location'))
        ref_num_str = ('; '.join(ref_bits) if ref_bits else (
            f"Record {rec.get('record_number') or rec_id}" if rec_id and rec_id != 'Unknown' else ""))
        parish_detail_fields = [("Page", f"Page {page}" if page and page != 'X' else ""),
            ("SourceDetailPerson", person_name), ("Location", parish_loc), ("Repository", Utils.clean_val(REPOSITORY)),
            ("URL", Utils.clean_val(COLLECTION_URL)), ("RefNumber", ref_num_str), ]
        lines = []
        for f_name, f_val in parish_detail_fields:
            if f_val:
                lines.extend(["3 FIELD", f"4 NAME {f_name}", f"4 VALUE {f_val}"])
        return lines
    
    def citation_text_block(self, rec: dict, part: dict, raw_orig: str, raw_trans: str) -> List[str]:
        orig_val = Utils.clean_val(raw_orig)
        trans_val = Utils.clean_val(raw_trans)
        norm_orig = re.sub(r'\s+', ' ', orig_val).strip().lower() if orig_val else orig_val
        norm_trans = re.sub(r'\s+', ' ', trans_val).strip().lower() if trans_val else trans_val
        same_text = orig_val and trans_val and norm_orig == norm_trans
        lines = []
        if same_text or not (orig_val and trans_val):
            single_text = Utils.wrap_text(trans_val or orig_val, '4 TEXT')
            if single_text:
                lines.append(single_text)
        else:
            lines.append(f"4 TEXT {GENERAL_CONFIG['translation_header']}")
            trans_text = Utils.wrap_text(trans_val, '5 CONT')
            if trans_text:
                lines.append(trans_text)
            lines.append(f"3 NOTE {GENERAL_CONFIG['transcription_header']}")
            orig_text = Utils.wrap_text(orig_val, '4 CONT')
            if orig_text:
                lines.append(orig_text)
        return lines
    
    def citation_uses_source_documents(self, rec: dict) -> bool:
        return True
    
    def primary_fact_date(self, rec: dict, is_primary: bool) -> str:
        return ""
    
    def build_primary_event_lines(self, rec: dict, part: dict, event_tag: str, witnesses: List[dict], vol: str,
                                  media_uid: str, target_software: str, resi: str, alt_names: list,
                                  scrip_fact_date: str, raw_event_date: str, age: str) -> List[str]:
        return _build_generic_primary_event_lines(rec, part, event_tag, witnesses, vol, media_uid, target_software,
                                                  alt_names, raw_event_date, age)
    
    def volume_source_detail_fields(self, v_clause: str) -> List[str]:
        tid = 10009
        primary_creator = Utils.clean_val(GENERAL_CONFIG.get('parish_name'))
        dept = Utils.clean_val(GENERAL_CONFIG.get('diocese')) or Utils.clean_val(GENERAL_CONFIG.get('parish_location'))
        source_desc = f"{GENERAL_CONFIG.get('register_name', '')}{v_clause}".strip()
        date_str = Utils.clean_val(GENERAL_CONFIG.get('date_range_str'))
        lines = ["1 _TMPLT", f"2 TID {tid}"]
        if primary_creator:
            lines.extend(["2 FIELD", "3 NAME PrimaryCreator", f"3 VALUE {primary_creator}"])
        if dept:
            lines.extend(["2 FIELD", "3 NAME Department", f"3 VALUE {dept}"])
        if date_str:
            lines.extend(["2 FIELD", "3 NAME Date", f"3 VALUE {date_str}"])
        if source_desc:
            lines.extend(["2 FIELD", "3 NAME SourceDescription", f"3 VALUE {source_desc}"])
        if REPOSITORY:
            lines.extend(["2 FIELD", "3 NAME Repository", f"3 VALUE {REPOSITORY}"])
        if REPOSITORY_LOC:
            lines.extend(["2 FIELD", "3 NAME PublishLocation", f"3 VALUE {REPOSITORY_LOC}"])
        return lines
    
    def media_caption(self, sheet: dict, vol: str, pages: str) -> str:
        return f"{GENERAL_CONFIG['parish_name_short']} - Vol {vol or 'Unknown'} - Page {pages or 'X'}"
    
    def resolve_source_templates(self, json_data: dict, target_software: str) -> List[str]:
        if target_software == "RM":
            return get_source_templates({10009})
        return []
    
    def repository_defaults(self) -> Tuple[str, str]:
        return ("FamilySearch.org", "Granite Mountain, UT")
    
    def default_gedcom_output_name(self) -> Optional[str]:
        return None


_ACTIVE_PROFILE: Profile = GeneralProfile()


def set_active_profile(profile: Profile) -> None:
    global _ACTIVE_PROFILE
    _ACTIVE_PROFILE = profile
```

Note: `GENERAL_CONFIG.get('default_location')` referenced in `_build_generic_primary_event_lines` must exist as a key in the `GENERAL_CONFIG` dict moved in Step 1 — confirm it's present (it is, per the original `GENERAL_CONFIG` dict at 237–257) before this compiles.

- [ ] **Step 3: Rewrite `get_dynamic_source_id` and `generate_uid`/`generate_fam_uid` to consult `_ACTIVE_PROFILE`**

Replace the original bodies (2014–2027, 2128–2190, 2621–2635) with:

```python
def get_dynamic_source_id(vol_val: str) -> str:
    vol_digits = re.sub(r'\D', '', f"{vol_val or '1'}") or '1'
    return _ACTIVE_PROFILE.dynamic_source_id(vol_digits)


def generate_uid(rec: dict, part: dict, vol: str) -> str:
    src_id = re.sub(r'\D', '', get_dynamic_source_id(vol))

    link_id = Utils.clean_val((part.get('type_specific_fields') or {}).get('link_id'))
    if link_id:
        numeric_id = int(hashlib.md5(f"link_{link_id}".encode('utf-8')).hexdigest(), 16) % (10 ** 10)
        return f"{src_id}{numeric_id:010d}"

    if part.get('is_priest'):
        std_g = Utils.clean_val(part.get('std_given')).strip().lower()
        std_s = Utils.clean_val(part.get('std_surname')).strip().lower()
        std_name = f"{std_g} {std_s}".strip()
        numeric_id = int(hashlib.md5(f"clergy_{std_name}".encode('utf-8')).hexdigest(), 16) % (10 ** 10)
        return f"CLR{numeric_id:010d}"

    pid = Utils.clean_val(rec.get('lac_pid'))
    rec_id = Utils.clean_val(rec.get('record_id'))
    identity = pid or rec_id
    role = f"{part.get('role_number', '0')}"

    participants = rec.get('participants', [])
    same_role = [i for i, p in enumerate(participants) if f"{p.get('role_number', '0')}" == role]
    pos = next((i for i, p in enumerate(participants) if p is part), None)
    occ = same_role.index(pos) if pos in same_role else 0

    override = _ACTIVE_PROFILE.participant_uid(identity, role, occ)
    if override:
        return override

    unique_string = f"indi_{vol}_{identity}_{role}_{occ}"
    numeric_id = int(hashlib.md5(unique_string.encode('utf-8')).hexdigest(), 16) % (10 ** 10)
    return f"{src_id}{numeric_id:010d}"


def generate_fam_uid(rec: dict, vol: str) -> str:
    pid = Utils.clean_val(rec.get('lac_pid'))
    rec_id = Utils.clean_val(rec.get('record_id'))
    identity = pid or rec_id

    override = _ACTIVE_PROFILE.family_uid(identity)
    if override:
        return override

    src_id = re.sub(r'\D', '', get_dynamic_source_id(vol))
    page_str = Utils.clean_val(rec.get('page'))
    unique_string = f"fam_{vol}_{page_str}_{identity}"
    numeric_id = int(hashlib.md5(unique_string.encode('utf-8')).hexdigest(), 16) % (10 ** 10)
    return f"{src_id}{numeric_id:010d}"
```

Both preserve the original fall-through order exactly: `link_id` and `is_priest` checks run unconditionally before any profile consultation (they never depended on `is_scrip` in the original either).

- [ ] **Step 4: Rewrite `_build_citation_block`**

Replace the body (2641–2805) with a version that delegates the six divergence points to `_ACTIVE_PROFILE`, keeping the unconditional shared trailer (REFN/QUAY/`_QUAL`, `_APID`, person_ark FamilySearch webtag, LAC-URL webtag, media OBJE) untouched:

```python
def _build_citation_block(rec: dict, part: dict, tag_name: str, vol: str, media_uid: str,
                           proof_status: str = "proven", target_software: str = "RM",
                           document_type: Optional[str] = None,
                           citation_text: Optional[str] = None,
                           citation_details: Optional[str] = None,
                           doc_media_uid: Optional[str] = None) -> str:
    year = Utils.clean_val(rec.get('year'))
    page = Utils.clean_val(rec.get('page')) or 'X'

    titl = _ACTIVE_PROFILE.citation_title(rec, part, tag_name, year, document_type)
    page_line = _ACTIVE_PROFILE.citation_page(rec, part, page)

    template_id = _ACTIVE_PROFILE.citation_template_id(rec, vol)
    sour_id = f"@S{template_id}@" if template_id else get_dynamic_source_id(vol)

    computed_status = proof_status
    proof_status = _ACTIVE_PROFILE.citation_proof_status(computed_status)

    block = [
        "2 SOUR " + sour_id,
        titl,
        page_line,
    ]
    block.extend(_ACTIVE_PROFILE.citation_detail_fields(rec, part, page, vol, target_software))

    raw_orig = citation_text if citation_text is not None else rec.get('citation_text')
    raw_trans = citation_details if citation_details is not None else rec.get('citation_details')
    block.extend(_ACTIVE_PROFILE.citation_text_block(rec, part, raw_orig, raw_trans))

    block.extend([
        f"3 REFN {tag_name}",
        f"3 QUAY {'3' if proof_status == 'proven' else ('2' if proof_status == 'probable' else '1')}",
        "3 _QUAL 3" if proof_status == "proven" else "3 _QUAL 2",
    ])
    if Utils.APID_DB:
        block.append(f"3 _APID {Utils.APID_DB}")
    person_ark = Utils.clean_val((rec.get('type_specific_fields') or {}).get('person_ark'))
    if person_ark:
        block.append(f"3 _WEBTAG {person_ark}")
    lac_url = Utils.clean_val((rec.get('type_specific_fields') or {}).get('lac_url'))
    if lac_url:
        block.append(f"3 _WEBTAG {lac_url}")
    effective_media_uid = doc_media_uid or media_uid
    if effective_media_uid:
        block.append(f"3 OBJE @{effective_media_uid}@")

    return "\n".join(Utils.dedent_citation_lines(block))
```

**Note for the implementer:** the exact field names/format of the unconditional trailer block (`_APID`, `_WEBTAG` field names, `_QUAL` numeric mapping) must be copied verbatim from `Archivist.py:2772-2804` — the snippet above reconstructs the shape from the divergence-point analysis but the implementer must diff this against the original trailer lines during Task 4's self-test (Step 6) and correct any literal mismatch before committing, since this section was paraphrased rather than character-verified in this planning pass.

- [ ] **Step 5: Rewrite `build_general_citation`, `build_individual`'s Scrip-fact-date and primary-event block, `get_volume_sources`, `build_gedcom_from_general`, `apply_record_type_field_remap`, `run_general_flavor`**

`build_general_citation` (2808–2839) — replace the `is_scrip` check with the profile method:

```python
def build_general_citation(rec: dict, part: dict, tag_name: str, vol: str, media_uid: str,
                            proof_status: str = "proven", target_software: str = "RM") -> List[str]:
    source_documents = (rec.get('source_documents') or []) if _ACTIVE_PROFILE.citation_uses_source_documents(rec) else []
    if not source_documents:
        return [_build_citation_block(rec, part, tag_name, vol, media_uid, proof_status, target_software)]

    blocks = []
    for doc in source_documents:
        lac_asset_id = doc.get('lac_asset_id')
        media_path = doc.get('media_path')
        if lac_asset_id:
            doc_media_uid = generate_media_uid_for_lac_asset(lac_asset_id)
        elif media_path:
            doc_media_uid = generate_media_uid_for_path(media_path)
        else:
            doc_media_uid = media_uid
        blocks.append(_build_citation_block(rec, part, tag_name, vol, media_uid, proof_status,
                                             target_software, document_type=doc.get('document_type'),
                                             doc_media_uid=doc_media_uid))
    return blocks
```

**Note for the implementer:** verify the `source_documents` iteration body against `Archivist.py:2819-2838` character-for-character during Task 4's self-test — the field names above (`lac_asset_id`, `media_path`) are confirmed correct from the test fixtures in `test_archivist.py:242-250`, but the exact media-UID fallback order must be diffed against the original before committing.

`build_individual` (2880–3190) — move verbatim **except** these two spots:
- Line 2891–2892 (`scrip_fact_date` computation): replace `is_scrip = GENERAL_CONFIG.get('omit_source_id_prefix')` / `scrip_fact_date = ...` with:
  ```python
  scrip_fact_date = _ACTIVE_PROFILE.primary_fact_date(rec, is_primary)
  ```
- Lines 3091–3158 (the `if is_scrip and event_tag == 'EVEN': ... else: ...` block): replace the entire `if`/`else` with a single call:
  ```python
  lines.extend(_ACTIVE_PROFILE.build_primary_event_lines(
      rec, part, event_tag, witnesses, vol, media_uid, target_software,
      resi, alt_names, scrip_fact_date, raw_event_date, age))
  ```
  where `witnesses`, `resi`, `alt_names`, `raw_event_date`, `age` are whatever local variables the original block already computed at that point in the function (confirm each name against `Archivist.py:3080-3100` — they are the same locals the original `if`/`else` branches consumed, just now passed as arguments instead of read from enclosing scope).

`get_volume_sources` (3301–3356) — move verbatim except replace the `if not is_scrip: ... _TMPLT ... ` block (3326–3345) with:
```python
block.extend(_ACTIVE_PROFILE.volume_source_detail_fields(v_clause))
```
inserted at the same position, unconditionally (both profiles' methods already encode whether anything is added — `ScripProfile`'s returns `[]`).

`build_gedcom_from_general` (3359–3516) — move verbatim except:
- Replace the media-caption `is_scrip` branch (3401–3422) with:
  ```python
  media_title = _ACTIVE_PROFILE.media_caption(sheet, vol, Utils.clean_val(meta.get('pages')))
  ```
- Replace the end-of-file template-assembly `is_scrip` branch (3496–3509) with:
  ```python
  ged.extend(_ACTIVE_PROFILE.resolve_source_templates(json_data, target_software))
  ```

`apply_record_type_field_remap` (3519–3560) — move verbatim except the final `GEDCOM_OUTPUT_NAME` assignment (3559–3560):
```python
def apply_record_type_field_remap(record_type_name: str) -> None:
    global CALL_NUMBER, COLLECTION_URL, COLLECTION_NAME, REPOSITORY, REPOSITORY_LOC, IMAGE_DIR

    pmt_path = Path(__file__).resolve().parent.parent / "Paleographer" / "prompts" / f"{record_type_name}.pmt"
    if not record_type_name or not pmt_path.is_file():
        return

    raw = pmt_path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if not stripped.startswith("---"):
        return
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return
    front_matter = yaml.safe_load(parts[1]) or {}
    field_remap = front_matter.get("field_remap", {}) or {}

    resolved: Dict[str, str] = {}
    for prefixed_key, target in field_remap.items():
        val = os.getenv(prefixed_key, "")
        if val:
            resolved[target] = val

    CALL_NUMBER = resolved.get("CALL_NUMBER") or CALL_NUMBER
    COLLECTION_URL = resolved.get("COLLECTION_URL") or COLLECTION_URL
    COLLECTION_NAME = resolved.get("COLLECTION_NAME") or COLLECTION_NAME
    REPOSITORY = resolved.get("REPOSITORY") or REPOSITORY
    REPOSITORY_LOC = resolved.get("REPOSITORY_LOC") or REPOSITORY_LOC
    if resolved.get("IMAGE_DIR"):
        IMAGE_DIR = Utils.safe_path(Utils.PROGRAM_DIR, resolved["IMAGE_DIR"])
    if resolved.get("GEDCOM_OUTPUT_NAME") and not os.getenv("GEDCOM_OUTPUT_NAME", "").strip():
        Utils.GEDCOM_OUTPUT_NAME = resolved["GEDCOM_OUTPUT_NAME"]
```
(`import os`, `import yaml` needed at the top of General.py for this function.)

`run_general_flavor` — replace the whole body (3606–3636) with:
```python
def run_general_flavor(data: dict, profile: Profile) -> None:
    set_active_profile(profile)
    global REPOSITORY, REPOSITORY_LOC
    apply_record_type_field_remap(data.get("record_type_name", ""))

    default_repo, default_repo_loc = profile.repository_defaults()
    REPOSITORY = REPOSITORY or default_repo
    REPOSITORY_LOC = REPOSITORY_LOC or default_repo_loc

    default_output_name = profile.default_gedcom_output_name()
    if (default_output_name and Utils.GEDCOM_OUTPUT_NAME == "Family_Register.ged"
            and not os.getenv("GEDCOM_OUTPUT_NAME", "").strip()):
        Utils.GEDCOM_OUTPUT_NAME = default_output_name

    apply_extracted_parish_name(data)
    apply_resolved_source_id(data)

    for software in Utils.resolve_gedcom_output_targets():
        gedcom_text = build_gedcom_from_general(data, software)
        final_path = Utils.resolve_gedcom_output_path(software)
        final_path.write_text(gedcom_text, encoding="utf-8")
        print(f"Successfully generated {final_path}")
```
Note `data.get("record_type_name") == "Scrip"` no longer needs to be computed inside this function — the caller (Archivist.py's dispatcher, Task 6) already chose which `Profile` instance to pass in based on that same field.

- [ ] **Step 6: Self-test — diff the two paraphrased trailer sections against the original file**

Before committing, open the original `Archivist.py` at lines 2772–2805 (the `_build_citation_block` trailer) and lines 2819–2838 (the `build_general_citation` source-document loop) side by side with the new `General.py` and confirm every field name, GEDCOM tag, and fallback order matches exactly. Fix any mismatch found. This step exists because those two spans were reconstructed from this planning session's earlier paraphrase rather than a fresh character-by-character read; every other function in this task was re-verified against the live file this same session.

- [ ] **Step 7: Add `Archivist/tests/test_general_smoke.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import General


def test_general_module_imports_and_default_profile_is_general():
    assert isinstance(General._ACTIVE_PROFILE, General.GeneralProfile)


def test_get_dynamic_source_id_keeps_prefix_by_default():
    General.set_active_profile(General.GeneralProfile())
    General.GENERAL_CONFIG['register_source_id'] = '1042'
    assert General.get_dynamic_source_id("3") == "@S1042003@"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd Archivist && pytest tests/test_general_smoke.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add Archivist/General.py Archivist/tests/test_general_smoke.py
git commit -m "refactor: extract General.py with Profile strategy pattern from Archivist.py"
```

---

### Task 5: Create `ScripProfile.py`

**Files:**
- Create: `Archivist/ScripProfile.py`
- Test: `Archivist/tests/test_scrip_profile_smoke.py` (new, minimal)

**Interfaces:**
- Consumes: `General.GENERAL_CONFIG`, `General.REPOSITORY`, `General.COLLECTION_URL`, `General.COLLECTION_NAME`, `General.build_custom_fact_lines`, `General.build_witness_links`, `General._build_generic_primary_event_lines`, `General.get_source_templates`, `General.get_by_semantic`, `Utils.clean_val`, `Utils.clean_place`, `Utils.cap_case`, `Utils.wrap_text`.
- Produces: `ScripProfile` class implementing every `Profile` method (see reference section above), plus the Scrip-only template cluster (`resolve_scrip_template_id`, `select_scrip_template_id`, `get_scrip_citation_fields`, `get_scrip_template_sources`) that `Archivist.py`'s `PROFILE_REGISTRY` (Task 6) and `General.py`'s callers never call directly except through `ScripProfile`'s own methods.

- [ ] **Step 1: Move the Scrip-only cluster verbatim**

`import re`, `import General`, `import Utils` at the top. Move lines 2362–2536 verbatim (`_SIMPLIFIED_CITATION_TEMPLATES` dict, `_SCRIP_TEMPLATES`, `_SCRIP_YEAR_RE`, `_scrip_record_year`, `select_scrip_template_id`, `resolve_scrip_template_id`, `_scrip_template_field_value`, `get_scrip_citation_fields`, `get_scrip_template_sources`), qualifying `REPOSITORY`/`COLLECTION_URL`/`COLLECTION_NAME` as `General.REPOSITORY`/`General.COLLECTION_URL`/`General.COLLECTION_NAME` and `clean_val`/`weblink_lines` as `Utils.clean_val`/`Utils.weblink_lines`.

- [ ] **Step 2: Implement the `ScripProfile` class**

```python
class ScripProfile:
    def dynamic_source_id(self, vol_digits: str) -> str:
        return f"@S{vol_digits.zfill(3)}@"

    def participant_uid(self, identity: str, role: str, occ: int) -> Optional[str]:
        if not identity:
            return None
        if role == '0' and occ == 0:
            return identity
        return f"{identity}_{role}_{occ}" if occ > 0 else f"{identity}_{role}"

    def family_uid(self, identity: str) -> Optional[str]:
        if not identity:
            return None
        return f"FAM_{identity}"

    def citation_title(self, rec: dict, part: dict, tag_name: str, year: str,
                        document_type: Optional[str]) -> str:
        std_g = Utils.clean_val(part.get('std_given'))
        std_s = Utils.clean_val(part.get('std_surname'))
        type_fields = rec.get('type_specific_fields') or {}
        claim_num = Utils.clean_val(type_fields.get('claim_number'))
        affdt_num = Utils.clean_val(type_fields.get('affidavit_number'))
        scrip_num = Utils.clean_val(type_fields.get('scrip_number'))
        ref_bits = [b for b in (f"Claim: {claim_num}" if claim_num else "",
                                f"Affidavit: {affdt_num}" if affdt_num else "",
                                f"Scrip: {scrip_num}" if scrip_num else "") if b]
        role_label = "Personal" if part.get('role_semantic') == 'primary' else "Witness"
        return f"3 _TITL {std_s}, {std_g}: {'; '.join(ref_bits)} [{role_label} (\"{std_g}\", {std_s})]"

    def citation_page(self, rec: dict, part: dict, page: str) -> str:
        rec_id = Utils.clean_val(rec.get('record_id')) or 'Unknown'
        type_fields = rec.get('type_specific_fields') or {}
        claim_num = Utils.clean_val(type_fields.get('claim_number'))
        affdt_num = Utils.clean_val(type_fields.get('affidavit_number'))
        ref_bits = [b for b in (f"Claim {claim_num}" if claim_num else "",
                                f"Affdt {affdt_num}" if affdt_num else "") if b]
        return f"3 PAGE {'; '.join(ref_bits)}" if ref_bits else f"3 PAGE Record {rec_id}"

    def citation_template_id(self, rec: dict, vol: str) -> Optional[int]:
        return resolve_scrip_template_id(rec)

    def citation_proof_status(self, computed_status: str) -> str:
        return "proven"

    def citation_detail_fields(self, rec: dict, part: dict, page: str, vol: str,
                                target_software: str) -> List[str]:
        if target_software != "RM":
            return []
        template_id = resolve_scrip_template_id(rec)
        if not template_id:
            return []
        return get_scrip_citation_fields(template_id, rec, part, vol)

    def citation_text_block(self, rec: dict, part: dict, raw_orig: str, raw_trans: str) -> List[str]:
        type_fields = rec.get('type_specific_fields') or {}
        lines = []
        orig_val = Utils.clean_val(raw_orig)
        text = Utils.wrap_text(orig_val, '4 TEXT')
        if text:
            lines.append(text)
        review_val = Utils.clean_val(raw_trans if raw_trans is not None else type_fields.get('package_summary'))
        if review_val:
            lines.append("3 NOTE Commissioner's Review:")
            review_text = Utils.wrap_text(review_val, '4 CONT')
            if review_text:
                lines.append(review_text)
        return lines

    def citation_uses_source_documents(self, rec: dict) -> bool:
        return False

    def primary_fact_date(self, rec: dict, is_primary: bool) -> str:
        year = _scrip_record_year(rec)
        return str(year) if is_primary and year else ""

    def build_primary_event_lines(self, rec: dict, part: dict, event_tag: str, witnesses: List[dict],
                                   vol: str, media_uid: str, target_software: str, resi: str,
                                   alt_names: list, scrip_fact_date: str, raw_event_date: str,
                                   age: str) -> List[str]:
        if event_tag != 'EVEN':
            return General._build_generic_primary_event_lines(
                rec, part, event_tag, witnesses, vol, media_uid, target_software,
                alt_names, raw_event_date, age)

        extra_fields = rec.get('type_specific_fields') or {}
        claim_number = Utils.clean_val(extra_fields.get('claim_number'))
        affidavit_number = Utils.clean_val(extra_fields.get('affidavit_number'))
        scrip_number = Utils.clean_val(extra_fields.get('scrip_number'))
        scrip_amount = Utils.clean_val(extra_fields.get('scrip_amount'))
        scrip_part = f"Scrip #: {scrip_number}" if scrip_number else ""
        if scrip_part and scrip_amount:
            scrip_part += f" ({scrip_amount})"
        value_parts = [p for p in (
            f"Claim: {claim_number}" if claim_number else "",
            f"Affidavit #: {affidavit_number}" if affidavit_number else "",
            scrip_part,
        ) if p]
        consumed = ('claim_number', 'affidavit_number', 'scrip_number', 'scrip_amount', 'document_type',
                    'commission_reference', 'rg_series_code', 'reel_numbers', 'application_date',
                    'issue_date', 'delivery_date', 'delivery_place', 'package_summary')
        value_parts.extend(f"{k.replace('_', ' ').title()}: {Utils.clean_val(v)}"
                           for k, v in extra_fields.items() if k not in consumed and Utils.clean_val(v))
        scrip_value = "; ".join(value_parts)
        scrip_place = Utils.clean_place(rec.get('event_place')) or resi or General.GENERAL_CONFIG['default_location']

        lines = General.build_custom_fact_lines('Scrip', scrip_value, rec, part, vol, media_uid,
                                                  target_software, date=scrip_fact_date, place=scrip_place)
        if alt_names:
            alt_values = ", ".join(Utils.clean_val(a.get('value')) for a in alt_names)
            lines.append(f"2 NOTE Margin note suggests alternate spelling: {alt_values}")
        lines.extend(General.build_witness_links(rec, witnesses, vol, target_software))
        return lines

    def volume_source_detail_fields(self, v_clause: str) -> List[str]:
        return []

    def media_caption(self, sheet: dict, vol: str, pages: str) -> str:
        first_rec = next(iter(sheet.get('records', [])), {})
        primary = General.get_by_semantic(first_rec, 'primary') or {}
        scrip_tf = first_rec.get('type_specific_fields') or {}
        media_std_g = Utils.clean_val(primary.get('std_given'))
        media_std_s = Utils.clean_val(primary.get('std_surname'))
        media_ref_bits = [b for b in (
            f"Claim: {Utils.clean_val(scrip_tf.get('claim_number'))}" if scrip_tf.get('claim_number') else "",
            f"Affidavit: {Utils.clean_val(scrip_tf.get('affidavit_number'))}" if scrip_tf.get('affidavit_number') else "",
            f"Scrip: {Utils.clean_val(scrip_tf.get('scrip_number'))}" if scrip_tf.get('scrip_number') else "",
        ) if b]
        if media_std_s or media_std_g:
            return f"{media_std_s}, {media_std_g}: {'; '.join(media_ref_bits)}"
        return f"Scrip Records - Vol {vol or 'Unknown'} - Page {pages or 'X'}"

    def resolve_source_templates(self, json_data: dict, target_software: str) -> List[str]:
        template_ids_used = set()
        for sheet in json_data.get('sheets', []):
            for rec in sheet.get('records', []):
                tid = resolve_scrip_template_id(rec)
                if tid:
                    template_ids_used.add(tid)
        if not template_ids_used:
            return []
        lines = get_scrip_template_sources(template_ids_used, target_software)
        if target_software == "RM":
            lines = lines + General.get_source_templates(template_ids_used)
        return lines

    def repository_defaults(self) -> Tuple[str, str]:
        return ("Library and Archives Canada", "Ottawa, ON")

    def default_gedcom_output_name(self) -> Optional[str]:
        return "Scrip.ged"
```

Add `from typing import List, Optional, Tuple` to the imports.

**Note for the implementer:** `citation_title`/`citation_page`'s `ref_bits`/field-name logic and `build_primary_event_lines`'s `consumed` tuple and `value_parts` assembly were reconstructed from this planning session's divergence analysis rather than a final character-by-character diff against `Archivist.py:2663-2680` (TITL), `2685-2693` (PAGE), and `3100-3137` (Scrip EVEN block). Before committing this task, diff each of these three methods against those exact original line ranges and correct any mismatch — same self-test discipline as Task 4 Step 6.

- [ ] **Step 3: Add `Archivist/tests/test_scrip_profile_smoke.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ScripProfile


def test_scrip_profile_dynamic_source_id_has_no_register_prefix():
    profile = ScripProfile.ScripProfile()
    assert profile.dynamic_source_id("3") == "@S003@"


def test_scrip_profile_participant_uid_uses_identity_directly_for_primary():
    profile = ScripProfile.ScripProfile()
    assert profile.participant_uid("SCRIP-5473", "0", 0) == "SCRIP-5473"


def test_scrip_profile_repository_defaults_to_lac():
    profile = ScripProfile.ScripProfile()
    assert profile.repository_defaults() == ("Library and Archives Canada", "Ottawa, ON")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && pytest tests/test_scrip_profile_smoke.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add Archivist/ScripProfile.py Archivist/tests/test_scrip_profile_smoke.py
git commit -m "refactor: extract ScripProfile.py implementing the Profile pattern for Scrip"
```

---

### Task 6: Rewrite `Archivist.py` as thin dispatcher; golden-file regression test

**Files:**
- Modify: `Archivist/Archivist.py` (full rewrite — everything except `resolve_json_input` and the `__main__` block is deleted, replaced by imports)
- Test: `Archivist/tests/test_archivist_dispatcher.py` (new — includes the golden-file regression comparison)

**Interfaces:**
- Consumes: `Utils.GEDCOM_OUTPUT_NAME`, `Census.run_census_flavor`, `General.run_general_flavor`, `General.GeneralProfile`, `ScripProfile.ScripProfile`.
- Produces: `PROFILE_REGISTRY: Dict[str, type]`, `resolve_profile(record_type_name: str) -> General.Profile`, `resolve_json_input` (unchanged), `main()`-equivalent `__main__` block.

- [ ] **Step 1: Rewrite `Archivist.py`**

```python
"""
Archivist - the toolbox's Create step, thin dispatcher.

Reads a single JSON file produced by Voyageur (Gather) and/or Paleographer (Analysis)
and routes to Census.py (flat per-page census rows, needs household grouping) or
General.py (explicit per-participant roles, church-register/Scrip-shaped) based on the
document's own record_type_name. General.py's behavior for a given record type is
selected via a Profile instance looked up in PROFILE_REGISTRY - GeneralProfile for
every record type except Scrip, which gets ScripProfile.
"""
import json
import os
from pathlib import Path
from typing import Callable, Dict

import Census
import General
import ScripProfile
import Utils

JSON_DIR = os.getenv("JSON_DIR", str(Path(__file__).resolve().parent))
JSON_FILE = os.getenv("JSON_FILE", "")

PROFILE_REGISTRY: Dict[str, Callable[[], "General.Profile"]] = {
    "Scrip": ScripProfile.ScripProfile,
}


def resolve_profile(record_type_name: str) -> "General.Profile":
    profile_cls = PROFILE_REGISTRY.get(record_type_name, General.GeneralProfile)
    return profile_cls()


def resolve_json_input(json_file: str, json_dir: str) -> Path:
    """Resolves the JSON file to convert. An explicit JSON_FILE setting must exist (a typo
    there is a real error, not a reason to guess). Left blank, falls back to whichever
    *.json file in JSON_DIR was created most recently, so tools like Archivist's
    "Generate GEDCOM" button work as a plain fallback without needing a filename typed in
    every time."""
    if json_file:
        candidate = Path(json_file) if os.path.isabs(json_file) else Path(str(json_dir)) / json_file
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"JSON file not found: {candidate}")

    search_dir = Path(str(json_dir))
    candidates = sorted(search_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No JSON_FILE was set, and no *.json files were found in {search_dir} to fall back to.")
    return candidates[0]


if __name__ == "__main__":
    input_path = resolve_json_input(JSON_FILE, JSON_DIR)
    print(f"[System] Using JSON file: {input_path}" + ("" if JSON_FILE else " (auto-selected, most recent)"))

    with open(input_path, "r", encoding="utf-8") as json_fh:
        loaded_data = json.load(json_fh)

    is_census = loaded_data.get("record_type_name", "").startswith("Census_") or "pages" in loaded_data
    if is_census:
        if not os.getenv("GEDCOM_OUTPUT_NAME", "").strip():
            Utils.GEDCOM_OUTPUT_NAME = input_path.stem + ".ged"
        Census.run_census_flavor(loaded_data)
    elif "sheets" in loaded_data:
        General.run_general_flavor(loaded_data, resolve_profile(loaded_data.get("record_type_name", "")))
    else:
        raise ValueError(
            f"Could not determine JSON flavor for {input_path}: expected a top-level "
            f"'sheets' key with a record_type_name, or a legacy 'pages' key (census)."
        )
```

- [ ] **Step 2: Add the golden-file regression test**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / "golden"))
import General
from capture_golden_gedcom import PARISH_FIXTURE, SCRIP_FIXTURE

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _regenerate(fixture: dict, target_software: str, profile) -> str:
    General.set_active_profile(profile)
    return General.build_gedcom_from_general(fixture, target_software)


def test_scrip_rm_matches_golden():
    import ScripProfile
    actual = _regenerate(SCRIP_FIXTURE, "RM", ScripProfile.ScripProfile())
    expected = (GOLDEN_DIR / "scrip_rm.ged").read_text(encoding="utf-8")
    assert actual == expected


def test_scrip_ftm_matches_golden():
    import ScripProfile
    actual = _regenerate(SCRIP_FIXTURE, "FTM", ScripProfile.ScripProfile())
    expected = (GOLDEN_DIR / "scrip_ftm.ged").read_text(encoding="utf-8")
    assert actual == expected


def test_parish_rm_matches_golden():
    actual = _regenerate(PARISH_FIXTURE, "RM", General.GeneralProfile())
    expected = (GOLDEN_DIR / "parish_rm.ged").read_text(encoding="utf-8")
    assert actual == expected


def test_parish_ftm_matches_golden():
    actual = _regenerate(PARISH_FIXTURE, "FTM", General.GeneralProfile())
    expected = (GOLDEN_DIR / "parish_ftm.ged").read_text(encoding="utf-8")
    assert actual == expected
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd Archivist && pytest tests/test_archivist_dispatcher.py -v`
Expected: PASS (4 tests). Any failure here means a Task 4/5 method has a real behavior mismatch against the golden fixtures — fix the mismatched Profile method (most likely one of the two paraphrased spans flagged in Task 4 Step 6 / Task 5's implementer note) before proceeding; do not regenerate the golden files to make the test pass.

- [ ] **Step 4: Commit**

```bash
git add Archivist/Archivist.py Archivist/tests/test_archivist_dispatcher.py
git commit -m "refactor: rewrite Archivist.py as thin dispatcher over Census/General/ScripProfile"
```

---

### Task 7: Repoint existing tests

**Files:**
- Modify: `Archivist/tests/test_archivist.py`
- Modify: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: `Utils`, `Census`, `General`, `ScripProfile` (all created in Tasks 2–5).
- Produces: no new symbols — every existing test keeps its name and assertions, only its target import and (for the three flag-manipulating tests below) its setup/call shape changes.

- [ ] **Step 1: Repoint `test_census_ingestion.py`'s import**

Change `import Archivist as arc` to `import Census as arc` (every symbol that test file exercises — `run_census_flavor`, `build_gedcom_from_census`, `load_census_dataframe`, `build_census_dataframe_from_unified`, household-grouping helpers — now lives in `Census.py`). Add `sys.path.insert(0, ...)` pointing at `Archivist/` if not already present (matches the pattern in Task 2/3's smoke tests).

- [ ] **Step 2: Repoint `test_archivist.py`'s import and split it by target module**

Grep each test function for which module its target symbol now lives in:
- Tests calling `arc.get_dynamic_source_id`, `arc.generate_uid`, `arc.generate_fam_uid`, `arc.generate_media_uid*`, `arc._build_citation_block`, `arc.build_general_citation`, `arc.build_custom_fact_lines`, `arc.build_witness_links`, `arc.build_individual`, `arc.build_family`, `arc.get_volume_sources`, `arc.build_gedcom_from_general`, `arc.run_general_flavor`, `arc.GENERAL_CONFIG` → change `import Archivist as arc` to `import General as arc` for those, or split into a new `test_general.py` if cleaner (implementer's judgment — either is acceptable as long as every test still runs and passes).
- Tests calling `arc.get_scrip_*`, `arc.resolve_scrip_template_id`, `arc.select_scrip_template_id`, `arc._scrip_*` → repoint to `import ScripProfile as arc`.
- Tests calling `arc.clean_val`, `arc.cap_case`, `arc.clean_place`, `arc.format_gedcom_date`, `arc.get_proof_status`, `arc.wrap_text`, `arc.get_event_gedcom_tag`, `arc.is_family_event`, `arc.split_full_name` → repoint to `import Utils as arc`.

- [ ] **Step 3: Rewrite the three `omit_source_id_prefix`-manipulating tests**

These three tests (named per the inherited task list: a test asserting the prefix is omitted for Scrip, one asserting it's kept by default for Parish, and one asserting `run_general_flavor` sets the flag from record type) directly manipulate `GENERAL_CONFIG['omit_source_id_prefix']`, which no longer exists. Locate them by grepping `test_archivist.py` for `omit_source_id_prefix` (this plan's earlier reconnaissance found this flag manipulated at line 325/346/near `run_general_flavor` call sites — re-grep at implementation time since line numbers will have shifted after Task 6 rewrites the file). Rewrite each to construct the appropriate `Profile` directly instead of mutating the flag, e.g.:

```python
def test_get_dynamic_source_id_omits_prefix_for_scrip():
    import ScripProfile
    General.set_active_profile(ScripProfile.ScripProfile())
    try:
        assert General.get_dynamic_source_id("3") == "@S003@"
    finally:
        General.set_active_profile(General.GeneralProfile())


def test_get_dynamic_source_id_keeps_prefix_by_default_for_parish():
    General.set_active_profile(General.GeneralProfile())
    General.GENERAL_CONFIG['register_source_id'] = '1042'
    assert General.get_dynamic_source_id("3") == "@S1042003@"


def test_run_general_flavor_sets_profile_from_record_type():
    import Archivist
    profile = Archivist.resolve_profile("Scrip")
    assert isinstance(profile, ScripProfile.ScripProfile)
    profile = Archivist.resolve_profile("Parish")
    assert isinstance(profile, General.GeneralProfile)
```

(Exact original assertions for the first two must be preserved — these two snippets reproduce the two `get_dynamic_source_id` expectations already used in Task 4/5's smoke tests; the third test's shape is new since `run_general_flavor` no longer computes `is_scrip` itself, so the "sets the flag from record type" behavior has moved to `Archivist.resolve_profile`, and the rewritten test must assert that instead.)

- [ ] **Step 4: Run full existing test suite**

Run: `cd Archivist && pytest tests/ -v`
Expected: PASS, same test count as before Task 1 (minus the 3 rewritten tests' old bodies, plus their new bodies — net count unchanged) plus every new test added in Tasks 2–6.

- [ ] **Step 5: Commit**

```bash
git add Archivist/tests/test_archivist.py Archivist/tests/test_census_ingestion.py
git commit -m "test: repoint Archivist tests to split Utils/Census/General/ScripProfile modules"
```

---

### Task 8: New isolated `Profile` unit tests

**Files:**
- Create: `Archivist/tests/test_profile_parity.py`

**Interfaces:**
- Consumes: `General.GeneralProfile`, `ScripProfile.ScripProfile`, both implementing the `Profile` reference from the top of this plan.

- [ ] **Step 1: Write parity tests — same input, both profiles, assert the documented divergence**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import General
import ScripProfile

GENERAL = General.GeneralProfile()
SCRIP = ScripProfile.ScripProfile()

REC = {"page": "1", "record_id": "SCRIP-5473", "year": "1880",
       "type_specific_fields": {"claim_number": "3126", "affidavit_number": "5473",
                                 "scrip_number": "12761"}}
PART = {"std_given": "Roger", "std_surname": "Letendre", "role_semantic": "primary"}


def test_citation_title_diverges_between_profiles():
    general_titl = GENERAL.citation_title(REC, PART, "EVEN", "1880", None)
    scrip_titl = SCRIP.citation_title(REC, PART, "EVEN", "1880", None)
    assert general_titl != scrip_titl
    assert "Claim: 3126" in scrip_titl
    assert "Letendre, Roger, EVEN, 1880" in general_titl


def test_citation_proof_status_scrip_always_proven():
    assert SCRIP.citation_proof_status("possible") == "proven"
    assert GENERAL.citation_proof_status("possible") == "possible"


def test_citation_uses_source_documents_only_for_general():
    assert GENERAL.citation_uses_source_documents(REC) is True
    assert SCRIP.citation_uses_source_documents(REC) is False


def test_repository_defaults_diverge():
    assert GENERAL.repository_defaults() == ("FamilySearch.org", "Granite Mountain, UT")
    assert SCRIP.repository_defaults() == ("Library and Archives Canada", "Ottawa, ON")


def test_default_gedcom_output_name_only_set_for_scrip():
    assert GENERAL.default_gedcom_output_name() is None
    assert SCRIP.default_gedcom_output_name() == "Scrip.ged"


def test_dynamic_source_id_scrip_has_no_register_prefix():
    General.GENERAL_CONFIG['register_source_id'] = '1042'
    assert GENERAL.dynamic_source_id("3") == "@S1042003@"
    assert SCRIP.dynamic_source_id("3") == "@S003@"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd Archivist && pytest tests/test_profile_parity.py -v`
Expected: PASS (6 tests)

- [ ] **Step 3: Run the full suite one final time**

Run: `cd Archivist && pytest tests/ -v`
Expected: PASS, all tests green.

- [ ] **Step 4: Commit**

```bash
git add Archivist/tests/test_profile_parity.py
git commit -m "test: add Profile parity tests covering GeneralProfile/ScripProfile divergence"
```

---

## Self-Review

**Spec coverage:** every section of `docs/superpowers/specs/2026-08-07-archivist-structural-split-design.md`'s Approach A (Profile strategy pattern replacing `is_scrip` branching, mirroring the Voyageur/Paleographer thin-dispatcher shape) is covered: dispatcher rewrite (Task 6), Profile protocol + GeneralProfile (Task 4), ScripProfile (Task 5), Utils/Census extraction (Tasks 2–3), golden-file regression discipline (Tasks 1 and 6), test repointing (Task 7), and new isolated coverage of the divergence points themselves (Task 8).

**Placeholder scan:** two spots are flagged, not left vague — Task 4 Step 6 and Task 5 Step 2's implementer note both name the exact original line ranges to diff against before committing, because those specific spans (the `_build_citation_block` trailer, the `build_general_citation` source-document loop, `citation_title`/`citation_page`'s Scrip ref-bit logic, and the Scrip EVEN block's `consumed`/`value_parts` assembly) were reconstructed from this session's divergence analysis rather than a final fresh read in this exact planning turn. This is disclosed as a required verification step with named line numbers, not a "TBD."

**Type/signature consistency:** all 17 `Profile` methods are defined once in the reference section, and both `GeneralProfile` (Task 4) and `ScripProfile` (Task 5) implement every one with matching signatures — verified by re-reading both class bodies against the reference table while writing this plan. `citation_detail_fields`, `citation_text_block`, `build_primary_event_lines`, and `resolve_source_templates` are the four methods most likely to drift if implemented out of order; Task 8's parity tests exercise the ones with the clearest observable divergence, and Task 6's golden-file test exercises every method transitively through `build_gedcom_from_general`.
