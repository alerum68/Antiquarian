# Close Out Open GitHub Issues (#3, #4, #5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement Tasks 1-3 task-by-task. Tasks 4-5 are **not** implementer tasks — see their callouts. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Close out the three open GitHub issues on this repo (#3 Voyageur field-map normalization, #4 Archivist unified tree ingestion, #5 Scriptorium FIELD_REMAP relocation) by finishing the specific remaining gaps each issue's own comment thread already identifies, and fix a repo-hygiene bug where `docs/superpowers/` is gitignored locally but 25 files under it are already tracked and pushed to GitHub. Issue #81159 (the LAC.py/AI Assistant-Desktop GPU-crash blocker) is explicitly out of scope — nothing here touches `Voyageur/LAC.py`, `Voyageur/BACLAC.py`, or the LAC site.

**Architecture:** All three issues already have substantial progress landed (confirmed by reading their comment threads against the current code). What remains is: (1) a pure audit-and-close for #5, which is already done in code; (2) a small, testable extraction in Voyageur's census-gather orchestration to close #3's "no direct test coverage" gap; (3) wiring the already-existing generic `facts[]` fact vocabulary into Archivist's church-flavor GEDCOM renderer to close #4's "write-only for church records" gap; (4)-(5) two manual, non-automatable live-data verification checkpoints (#3's `familysearch_census.yaml` DRAFT status, and end-to-end real-gather verification for both #3 and #4) that require an actual live Ancestry/FamilySearch browser session and are the user's to run, not an implementer subagent's.

**Tech Stack:** Python, pytest, PyYAML (field maps), pandas (Archivist DataFrame path — untouched by this plan), gh CLI (issue audit/close).

## Global Constraints

- Never touch `Voyageur/LAC.py`, `Voyageur/BACLAC.py`, or browse to the LAC site — issue #81159 is unresolved (see project memory `constraint_lac_scripts_blocked`).
- No AI attribution, "Co-Authored-By", or AI Assistant/AI Assistant stamps in code, commits, or PRs (AI Assistant.md).
- Run the relevant tool's test suite locally before declaring any task finished (AI Assistant.md).
- Closing or commenting on a GitHub issue is a visible, shared-state action — confirm with the human partner before running `gh issue close`/`gh issue comment`, even though this plan names the exact command to run.
- Do not touch `parse_household`/`parse_household_relational`/era detection/the `role_semantic` vocabulary/citation assembly in `Archivist/Archivist.py` — these were independently confirmed correct against the design spec (issue #9) and are explicitly out of scope for every task below.

---

### Task 1: Untrack `docs/superpowers/` (gitignored locally, still tracked on GitHub)

**Files:**
- Modify: `.gitignore` (commit the existing uncommitted `/docs/superpowers/` line — already present in the working tree, added before this plan, never committed)
- Untrack (keep on disk): all 25 files currently under `docs/superpowers/plans/` and `docs/superpowers/specs/` (confirm exact list with `git ls-files docs/superpowers` at execution time — new plan/spec files may have been added since this plan was written)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing later tasks depend on.

`.gitignore` already has a `/docs/superpowers/` line (sitting as an uncommitted local edit — `git diff HEAD -- .gitignore` shows it, confirmed via `git log --all -S"/docs/superpowers/" -- .gitignore` returning zero commits, i.e. it was never actually committed by anyone). A gitignore rule only stops *new* untracked files from being added — it does nothing for files already tracked before the rule existed, which is exactly why these 25 files are still on GitHub despite the rule. This is the same bug already fixed once for `AI Assistant.md` (commit `d70813f`, "Untrack AI Assistant.md - keep it local, not committed") — apply the identical fix here.

- [ ] **Step 1: Confirm the current tracked list and the uncommitted gitignore line**

Run:
```bash
git diff HEAD -- .gitignore
git ls-files docs/superpowers
```
Expected: the diff shows the `+/docs/superpowers/` line; the file list shows every currently-tracked file under `docs/superpowers/plans/` and `docs/superpowers/specs/`.

- [ ] **Step 2: Untrack the directory, keeping the files on disk**

```bash
git rm -r --cached docs/superpowers
```
Expected: `git status` now shows every previously-tracked file under `docs/superpowers/` as deleted-from-index (staged), while the files themselves remain unchanged on disk (verify with `ls docs/superpowers/plans/` — files still present).

- [ ] **Step 3: Stage the gitignore line and commit**

```bash
git add .gitignore
git commit -m "Untrack docs/superpowers/ - keep it local, not committed"
```

- [ ] **Step 4: Verify**

Run: `git ls-files docs/superpowers` → expect empty output.
Run: `git status --short` → expect clean (or only unrelated pending changes).

---

### Task 2: Audit and close Issue #5 (Scriptorium FIELD_REMAP relocation)

**Files:**
- No source changes — this task is verification-only.

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Confirm the old mechanism is fully gone**

Run:
```bash
git grep -n "FIELD_REMAP\|_record_type_family\|_peek_record_family" -- '*.py'
```
Expected: the only hit is a historical comment in `Voyageur/FS.py` referencing the old name for context (`# generalizes Scriptorium.py's existing _record_type_family() ...`). No live code defines or calls any of these three names anymore.

- [ ] **Step 2: Confirm Scriptorium.py never computes a generic runtime setting itself**

Run:
```bash
grep -n "run_env\[" Scriptorium.py
```
Expected: only `run_env['PYTHONUNBUFFERED']` and `run_env['PYTHONIOENCODING']` — process-level env vars, not app settings. Then read `Scriptorium.py`'s `_get_pmt_field_remap` method (currently around line 1614) and confirm its docstring and body: it only *reads* a `.pmt`'s `field_remap` table for the GUI's own display purposes (e.g. picking which image-dir field to browse from), and never writes a resolved generic key into the child process's `.env`. Confirm `Archivist/Archivist.py`'s `apply_record_type_field_remap` (around line 3519) and `Paleographer/engine.py`'s `resolve_setting`-equivalent mechanism are what actually resolve generic names — each script resolving its own settings from its own `.env`, independent of Scriptorium.

- [ ] **Step 3: Post the audit findings and close the issue**

This step is GitHub-visible — confirm with the human partner before running it. Once confirmed:
```bash
gh issue close 5 --comment "Verified done: FIELD_REMAP/_record_type_family/_peek_record_family no longer exist anywhere in Scriptorium.py (confirmed via git grep). Scriptorium.py's _get_pmt_field_remap only reads a .pmt's field_remap table for its own display purposes; Archivist.py's apply_record_type_field_remap and Paleographer's own resolve_setting mechanism each resolve their own generic runtime settings from their own .env independently of Scriptorium. Landed across b43b33d (Paleographer + Archivist: resolve own settings from own .env via field_remap) and the Archivist/Paleographer structural work that followed it."
```

- [ ] **Step 4: Nothing to commit** — this task changes no tracked files.

---

### Task 3: Extract testable normalize-and-validate call sites in Voyageur (Issue #3)

**Files:**
- Modify: `Voyageur/census_schema.py` (add `normalize_and_validate_census`)
- Modify: `Voyageur/A.py:98-110` (add `normalize_ancestry_census_gather`, use it at the call site)
- Modify: `Voyageur/FS.py:766-778` (add `normalize_familysearch_census_gather`, use it at the call site)
- Test: `Voyageur/tests/test_census_schema.py` (new test for the wrapper)
- Test: `Voyageur/tests/test_a.py` (new file — A.py has no test file today)
- Test: `Voyageur/tests/test_fs.py` (new test for the FS.py extraction)

**Interfaces:**
- Consumes: `census_schema.normalize_census_pages(raw, field_map_name, collection_title, record_type_name) -> dict` and `census_schema.validate_against_commissioner(normalized, collection_title) -> None` (both already exist and are already unit-tested — do not modify their bodies).
- Produces: `census_schema.normalize_and_validate_census(raw, field_map_name, collection_title, record_type_name) -> dict`; `A.normalize_ancestry_census_gather(raw_gather: dict) -> dict`; `FS.normalize_familysearch_census_gather(raw_census: dict, collection_title: str) -> dict`. Later tasks do not depend on these.

This closes the gap named in issue #3's own progress comment: *"A.py/FS.py's own main() orchestration (the normalization call site) has no direct test coverage - only census_schema.py itself is unit-tested. main() is heavily I/O-bound (browser, filesystem polling), not trivially testable without significant mocking."* The fix is to pull the pure translation logic (deriving `collection_title`/`record_type_name` and calling normalize+validate) out of each `main()` into a small, I/O-free function that a test can call directly — leaving `main()` itself doing only file I/O around it.

- [ ] **Step 1: Add the shared wrapper to `Voyageur/census_schema.py`**

Add directly after `validate_against_commissioner`'s definition:

```python
def normalize_and_validate_census(raw: dict, field_map_name: str, collection_title: str,
                                  record_type_name: str) -> dict:
    """Normalizes then validates in one call - the exact pair both A.py and FS.py apply at
    census gather time. Pulled out as its own function so each call site is one line and
    testable without duplicating the normalize+validate pairing."""
    normalized = normalize_census_pages(raw, field_map_name, collection_title, record_type_name)
    validate_against_commissioner(normalized, collection_title)
    return normalized
```

- [ ] **Step 2: Write the failing tests for the wrapper**

Add to `Voyageur/tests/test_census_schema.py`:

```python
def test_normalize_and_validate_census_returns_normalized_doc():
    raw = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M", "Age": "40",
                        "Relationship to Head": "Head", "Family Number": "5"}, "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_and_validate_census(raw, "ancestry_census", "1900 US Census", "Census_1900")

    assert doc["record_type_name"] == "Census_1900"
    assert doc["collection_title"] == "1900 US Census"
    assert len(doc["sheets"]) == 1
```

- [ ] **Step 3: Run it to verify it fails**

Run: `pytest Voyageur/tests/test_census_schema.py::test_normalize_and_validate_census_returns_normalized_doc -v`
Expected: FAIL with `AttributeError: module 'census_schema' has no attribute 'normalize_and_validate_census'`

- [ ] **Step 4: Run it again after Step 1's implementation to verify it passes**

Run: `pytest Voyageur/tests/test_census_schema.py -v`
Expected: all PASS, including the new test.

- [ ] **Step 5: Extract and wire the A.py call site**

Replace `Voyageur/A.py:98-110`:
```python
    # Normalize at gather time: translate Ancestry's own raw column header text into the
    # shared record schema's field names via the declarative field map, so Archivist never
    # has to guess among several possible header spellings downstream. Overwrites the same
    # file in place - Archivist still just reads whatever JSON_FILE points to.
    with open(final_json, "r", encoding="utf-8") as f:
        raw_gather = json.load(f)
    census_year_raw = raw_gather.get("census_year", "")
    collection_title = f"{census_year_raw} US Federal Census - {raw_gather.get('location', '')}".strip(" -")
    normalized = census_schema.normalize_census_pages(
        raw_gather, "ancestry_census", collection_title, f"Census_{census_year_raw}")
    census_schema.validate_against_commissioner(normalized, collection_title)
    with open(final_json, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
```
with:
```python
    # Normalize at gather time: translate Ancestry's own raw column header text into the
    # shared record schema's field names via the declarative field map, so Archivist never
    # has to guess among several possible header spellings downstream. Overwrites the same
    # file in place - Archivist still just reads whatever JSON_FILE points to.
    with open(final_json, "r", encoding="utf-8") as f:
        raw_gather = json.load(f)
    normalized = normalize_ancestry_census_gather(raw_gather)
    with open(final_json, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
```

Add this function near the top of `Voyageur/A.py`, after `parse_ancestry_url` (or any existing helper section, before `main()`):
```python
def normalize_ancestry_census_gather(raw_gather: dict) -> dict:
    """Translates a raw Ancestry census gather into the shared record schema, deriving
    collection_title/record_type_name from the gather's own census_year/location - the
    exact translation main() applies at gather time, pulled out here so it's testable
    without a browser session."""
    census_year_raw = raw_gather.get("census_year", "")
    collection_title = f"{census_year_raw} US Federal Census - {raw_gather.get('location', '')}".strip(" -")
    return census_schema.normalize_and_validate_census(
        raw_gather, "ancestry_census", collection_title, f"Census_{census_year_raw}")
```

- [ ] **Step 6: Write the failing test for `A.normalize_ancestry_census_gather`**

Create `Voyageur/tests/test_a.py`:
```python
"""Tests for A.py's census-gather normalization call site (Issue #3 test-coverage gap)."""
import A


def test_normalize_ancestry_census_gather_derives_title_and_record_type():
    raw_gather = {
        "census_year": "1880", "location": "Kent County, Michigan",
        "pages": [{
            "page_number": 12, "state": "Michigan", "county": "Kent", "city": "",
            "country": "USA", "roll_number": "T9_1", "repository": "Ancestry.com",
            "people": [
                {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                            "Age": "40", "Relationship to Head": "Head", "Family Number": "5"},
                 "pid": "p1"},
            ],
        }],
    }

    normalized = A.normalize_ancestry_census_gather(raw_gather)

    assert normalized["record_type_name"] == "Census_1880"
    assert normalized["collection_title"] == "1880 US Federal Census - Kent County, Michigan"
    assert len(normalized["sheets"]) == 1
```

- [ ] **Step 7: Run it to verify it fails, then implement, then verify it passes**

Run: `pytest Voyageur/tests/test_a.py -v` → FAIL (`normalize_ancestry_census_gather` not yet wired if Step 5 wasn't done first; do Step 5 before this if running strictly TDD-serially). After Step 5's code is in place:
Run: `pytest Voyageur/tests/test_a.py -v` → PASS.

- [ ] **Step 8: Extract and wire the FS.py call site**

Replace `Voyageur/FS.py:766-778`:
```python
    if record_family == "census":
        print("\n[System] Converting raw scrape into census Gather JSON...")
        raw_census = build_census_json(raw_data, items_raw, catalog_items)
        # Normalize at gather time: translate FamilySearch's own raw column header text
        # into the shared record schema's field names via the declarative field map, the
        # same as A.py does for Ancestry - so Archivist reads one shape regardless of
        # source, and never has to guess among several possible header spellings.
        collection_title = raw_data.get("collection_title", "")
        final_data = census_schema.normalize_census_pages(
            raw_census, "familysearch_census", collection_title,
            f"Census_{raw_census.get('census_year', '')}")
        census_schema.validate_against_commissioner(final_data, collection_title)
        clean_name = build_clean_census_filename(raw_census.get("census_year", ""), final_data)
```
with:
```python
    if record_family == "census":
        print("\n[System] Converting raw scrape into census Gather JSON...")
        raw_census = build_census_json(raw_data, items_raw, catalog_items)
        # Normalize at gather time: translate FamilySearch's own raw column header text
        # into the shared record schema's field names via the declarative field map, the
        # same as A.py does for Ancestry - so Archivist reads one shape regardless of
        # source, and never has to guess among several possible header spellings.
        final_data = normalize_familysearch_census_gather(raw_census, raw_data.get("collection_title", ""))
        clean_name = build_clean_census_filename(raw_census.get("census_year", ""), final_data)
```

Add this function near the top of `Voyageur/FS.py`, alongside its other module-level helpers (before `main()`):
```python
def normalize_familysearch_census_gather(raw_census: dict, collection_title: str) -> dict:
    """Translates a raw FamilySearch census gather (already grouped into Voyageur's own
    {census_year, pages: [...]} shape by build_census_json) into the shared record schema -
    the exact translation main() applies at gather time, pulled out here so it's testable
    without a browser session."""
    return census_schema.normalize_and_validate_census(
        raw_census, "familysearch_census", collection_title, f"Census_{raw_census.get('census_year', '')}")
```

- [ ] **Step 9: Write the failing test for `FS.normalize_familysearch_census_gather`**

Add to `Voyageur/tests/test_fs.py`:
```python
def test_normalize_familysearch_census_gather_derives_record_type():
    raw_census = {
        "census_year": "1900",
        "pages": [{
            "page_number": 3, "state": "Ohio", "county": "Lucas", "city": "", "country": "USA",
            "repository": "FamilySearch",
            "people": [
                {"columns": {"Given Name": "Marie", "Surname": "Boucher", "Gender": "F",
                            "Age": "35", "Relationship to Head": "Head", "Family Number": "2"},
                 "pid": "p2"},
            ],
        }],
    }

    normalized = FS.normalize_familysearch_census_gather(raw_census, "1900 US Census - Ohio")

    assert normalized["record_type_name"] == "Census_1900"
    assert normalized["collection_title"] == "1900 US Census - Ohio"
    assert len(normalized["sheets"]) == 1
```

- [ ] **Step 10: Run it to verify it fails, then verify it passes after Step 8**

Run: `pytest Voyageur/tests/test_fs.py -v` → PASS once Step 8's code is in place.

- [ ] **Step 11: Run the full Voyageur suite**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS, including the 3 new ones (`test_a.py`, plus the additions to `test_census_schema.py` and `test_fs.py`).

- [ ] **Step 12: Commit**

```bash
git add Voyageur/census_schema.py Voyageur/A.py Voyageur/FS.py Voyageur/tests/test_census_schema.py Voyageur/tests/test_a.py Voyageur/tests/test_fs.py
git commit -m "Voyageur: extract testable normalize-and-validate call sites for A.py/FS.py census gathers"
```

- [ ] **Step 13: Post progress on Issue #3**

GitHub-visible — confirm with the human partner before running:
```bash
gh issue comment 3 --body "Closes the test-coverage gap flagged in the earlier progress comment: A.py's and FS.py's census normalization call sites are now pulled into normalize_ancestry_census_gather()/normalize_familysearch_census_gather() (plus census_schema.normalize_and_validate_census()), each directly unit-tested without needing a browser session. Remaining gaps: familisearch_census.yaml is still DRAFT pending a real live gather, and neither path has been live-verified end-to-end yet - tracked as manual checkpoints, not closing this issue until those land."
```

---

### Task 4: Wire `facts[]` into Archivist's church-flavor renderer (Issue #4)

**Files:**
- Modify: `Archivist/Archivist.py:3061` (insert generic facts loop in `build_individual`, between the RESI block and the BIRT block)
- Test: `Archivist/tests/test_archivist.py` (new tests)

**Interfaces:**
- Consumes: `build_custom_fact_lines(fact_name, value, rec, part, vol, media_uid, target_software, date="", place="") -> List[str]` (existing, unmodified — already used for Race/dit Name/Scrip) and `FACT_TYPES` (existing module-level dict loaded from `FactTypes.json`, unmodified).
- Produces: nothing later tasks depend on.

This closes the exact gap named in issue #4's audit-comment: *"facts[] (the new generic per-participant fact array) has no consumer anywhere in Archivist.py yet... wire facts[] through the same FactTypes.json-driven generic rendering build_custom_fact_lines already uses for race/dit_name - otherwise the field is write-only and never reaches the GEDCOM."* Confirmed via code reading: `build_individual` (Archivist/Archivist.py:2880) is the **only** call site (line 3471), reached only from the church/general-flavor loop over `rec.get('participants', [])` directly — census never reaches `build_individual` at all (it has its own separate DataFrame-based rendering path via `build_dynamic_events_and_notes`, which already consumes `facts[]` via `FACT_TYPE_TO_COLUMN` before `build_individual` would ever see it). So this change is correctly scoped to church/general records only, with no risk of double-rendering a fact for census.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_archivist.py`:
```python
def test_build_individual_renders_generic_facts_via_fact_types():
    rec = {"event_type": "Baptism", "page": "1", "record_id": "REC-1", "event_place": "Quebec",
           "participants": [make_participant("primary", given="Jean", surname="Gagnon")]}
    primary = rec["participants"][0]
    primary["facts"] = [{"fact_type": "Occupation", "value": "Farmer"}]

    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)

    assert "1 EVEN Farmer" in joined
    assert "2 TYPE Occupation" in joined


def test_build_individual_skips_unknown_fact_type_gracefully():
    rec = {"event_type": "Baptism", "page": "1", "record_id": "REC-2", "event_place": "Quebec",
           "participants": [make_participant("primary", given="Marie", surname="Boucher")]}
    primary = rec["participants"][0]
    primary["facts"] = [{"fact_type": "", "value": "irrelevant"}]

    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)

    assert "irrelevant" not in joined
```

- [ ] **Step 2: Run to verify both fail**

Run: `pytest Archivist/tests/test_archivist.py::test_build_individual_renders_generic_facts_via_fact_types Archivist/tests/test_archivist.py::test_build_individual_skips_unknown_fact_type_gracefully -v`
Expected: first FAILs (`"1 EVEN Farmer"` not in output), second PASSes trivially already (nothing to fix — keep it as a regression guard).

- [ ] **Step 3: Implement**

In `Archivist/Archivist.py`, insert immediately after the RESI block (currently ending at line 3061, right before the `if b_date or b_place:` BIRT block at line 3063):
```python
    # Generic per-participant facts (fact_type drawn from FactTypes.json's shared
    # vocabulary - see Voyageur/census_schema.py's household_tally/facts[] convention).
    # Census records never reach this function (they render via the separate DataFrame
    # path in run_census_flavor, which already consumes facts[] before build_individual
    # would see it) - this is church/general-flavor's own consumer, closing the gap where
    # the field was write-only for anything but census.
    for fact in part.get('facts', []) or []:
        fact_type = clean_val(fact.get('fact_type', ''))
        if not fact_type:
            continue
        indi.extend(build_custom_fact_lines(fact_type, fact.get('value', ''), rec, part, vol, media_uid,
                                            target_software, date=fact.get('date', ''), place=fact.get('place', '')))
```

- [ ] **Step 4: Run to verify both pass**

Run: `pytest Archivist/tests/test_archivist.py -v`
Expected: all PASS (27+ existing tests plus the 2 new ones).

- [ ] **Step 5: Commit**

```bash
git add Archivist/Archivist.py Archivist/tests/test_archivist.py
git commit -m "Archivist: consume facts[] generically in build_individual for church-flavor records"
```

- [ ] **Step 6: Post progress on Issue #4**

GitHub-visible — confirm with the human partner before running:
```bash
gh issue comment 4 --body "Closes the facts[] write-only gap flagged against the #8 audit: build_individual (the church/general-flavor renderer - census never reaches this function, it has its own separate DataFrame path that already consumes facts[]) now iterates part['facts'] and renders each through build_custom_fact_lines, the same FactTypes.json-driven mechanism already used for Race/dit Name/Scrip. No .pmt populates facts[] yet, so this has no visible effect today - it's ready for the next record type that does. Remaining gap before closing this issue: end-to-end live verification against a real gathered census file, which depends on Issue #3's own live-verification checkpoint landing first."
```

---

### Task 5 (Manual checkpoint — NOT an implementer task): Live-verify `familysearch_census.yaml`

> This task requires an actual live FamilySearch browser session with real login credentials. No implementer subagent can execute this — it is the user's own step. Included here so the plan is complete and the issue has a concrete path to closing, not because an agent should attempt it.

- [ ] Run a real FamilySearch census gather via `Voyageur/FS.py` for at least one census year not yet spot-checked.
- [ ] Inspect the resulting normalized JSON's `sheets[].records[].participants[]` — specifically each participant's `type_specific_fields.unmapped` (per `census_schema.py`'s "never dropped or guessed, flagged for review" convention) — for any real FamilySearch column header text that `Voyageur/field_maps/familysearch_census.yaml` doesn't yet map.
- [ ] Add any missing header mappings to `Voyageur/field_maps/familysearch_census.yaml`, following the existing entries' format.
- [ ] Once a real gather round-trips with zero unmapped headers (or all remaining unmapped headers are genuinely source-specific noise, not missed real fields), remove the file's DRAFT status note.
- [ ] Confirm with the human partner, then close out this portion via `gh issue comment 3 --body "familysearch_census.yaml confirmed against a live gather on <date> - DRAFT status removed."`

---

### Task 6 (Manual checkpoint — NOT an implementer task): End-to-end live verification and final issue closure

> Also requires a live browser session. Depends on Task 4 landing first (or being run in the same session).

- [ ] Run a full real gather (Ancestry or FamilySearch) through to a generated GEDCOM via Archivist, for at least one census year.
- [ ] Confirm the household/relationship resolution (`parse_household`/`parse_household_relational`) produces correct `role_semantic` assignments against the real data — this exercises `build_census_dataframe_from_unified` (Archivist/Archivist.py) end-to-end for the first time against non-synthetic input.
- [ ] Confirm with the human partner, then close both remaining issues:
  ```bash
  gh issue close 3 --comment "Live-verified end-to-end on <date> against a real gather - closing."
  gh issue close 4 --comment "Live-verified end-to-end on <date> against a real gathered census file via #3's checkpoint - closing."
  ```

---

## Self-Review

**Spec coverage:** #5 → Task 1 (verify+close, already done in code). #3 → Task 2 (test-coverage gap, code) + Task 4 (DRAFT-status gap, manual). #4 → Task 3 (facts[] gap, code) + Task 5 (live-verification gap, manual, shared with #3's own live-verification need). Every remaining gap named in each issue's own comment thread has a task.

**Placeholder scan:** No TBD/TODO; all code blocks are complete and copy-pasteable; manual tasks are explicitly labeled as such rather than disguised as implementer steps.

**Type consistency:** `normalize_and_validate_census(raw, field_map_name, collection_title, record_type_name) -> dict` matches its two call sites' argument order in Tasks 2 Steps 5/8. `build_custom_fact_lines`'s signature in Task 3 matches its existing definition (Archivist/Archivist.py:2842) exactly, including keyword-only `date`/`place`.

**Scope guard:** No task touches `Voyageur/LAC.py`/`BACLAC.py`. No task touches `parse_household`/`parse_household_relational`/era detection/citation assembly, per the Global Constraints and issue #4's own explicit "not redesigned" note.
