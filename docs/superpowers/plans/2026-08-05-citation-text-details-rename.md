# citation_text/citation_details Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `original_transcription`/`english_translation` to `citation_text`/`citation_details` project-wide, with no compatibility fallback left anywhere once each location is renamed.

**Architecture:** Rename the producer side first (schema.json, both `.pmt` prompts, Commissioner, Paleographer's runtime code, Voyageur's Census pipeline) while `Archivist.py` keeps working unchanged throughout, because its citation-building code already prefers `citation_text`/`citation_details` over the old names as a pre-existing partial fix. Only the final task touches `Archivist.py` itself, deleting that now-dead fallback entirely. This ordering means the full suite stays green after every task, not just at the end.

**Tech Stack:** Python, pytest, Pydantic (Commissioner), JSON Schema (schema.json), YAML front matter (.pmt files).

## Global Constraints

- This is a pure rename: no field's actual behavior, prompt instructions, or content quality changes - only the key/field name.
- No compatibility shim: once a location is renamed, the old name is deleted there, not kept as a fallback.
- Parish's translation behavior is unchanged (still a full literal translation); Scrip's synopsis behavior is unchanged.
- No AI attribution, "Co-Authored-By", or "Generated with Claude" text in any code, comment, or commit message.
- Run the affected test suite locally and confirm it passes before considering any task done; run the full suite at the end of every task, not just the last one.
- No comments explaining what code does - only ones explaining a non-obvious why (existing comments referencing the old names by name should be updated to the new names, not deleted, unless they no longer apply).

---

### Task 1: Rename in schema.json, both .pmt prompts, and Commissioner

**Files:**
- Modify: `Paleographer/schema.json:47-48`
- Modify: `Paleographer/prompts/Parish.pmt:138-141`
- Modify: `Paleographer/prompts/Scrip.pmt:138,145-146,151-152`
- Modify: `Commissioner/models.py:277-278`
- Modify: `Commissioner/tests/test_models.py:60-65`
- Test: `Commissioner/tests/test_models.py` (existing guardrail tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `Record.citation_text`, `Record.citation_details` (Commissioner's public field names, replacing `Record.original_transcription`/`Record.english_translation`). Every later task's code that constructs a record dict must use `"citation_text"`/`"citation_details"` as the keys.

- [ ] **Step 1: Update the failing guardrail test's expectations first**

In `Commissioner/tests/test_models.py`, in `EXPECTED_FIELDS["Record"]`, replace:
```python
    "Record": {
        "record_id", "page", "record_number", "event_type", "year", "event_date",
        "event_place", "english_translation", "original_transcription", "review",
        "review_reason", "continues_on_next_image", "continues_from_previous_image",
        "type_specific_fields", "participants",
    },
```
with:
```python
    "Record": {
        "record_id", "page", "record_number", "event_type", "year", "event_date",
        "event_place", "citation_text", "citation_details", "review",
        "review_reason", "continues_on_next_image", "continues_from_previous_image",
        "type_specific_fields", "participants",
    },
```

- [ ] **Step 2: Run the guardrail test to verify it now fails against the unchanged code**

Run: `python -m pytest Commissioner/tests/test_models.py::test_models_match_schema_json_field_names -v`
Expected: FAIL - `Record: expected {..., 'citation_text', 'citation_details', ...}, got {..., 'english_translation', 'original_transcription', ...}`

- [ ] **Step 3: Rename the two properties in schema.json**

In `Paleographer/schema.json`, replace:
```json
                "event_place": { "type": "string", "nullable": true },
                "english_translation": { "type": "string" },
                "original_transcription": { "type": "string" },
                "review": {
```
with:
```json
                "event_place": { "type": "string", "nullable": true },
                "citation_details": { "type": "string" },
                "citation_text": { "type": "string" },
                "review": {
```

- [ ] **Step 4: Rename the two fields in Commissioner/models.py**

In `Commissioner/models.py`, in the `Record` class, replace:
```python
    event_place: Optional[str] = None
    english_translation: Optional[str] = None
    original_transcription: Optional[str] = None
    review: bool = Field(
```
with:
```python
    event_place: Optional[str] = None
    citation_details: Optional[str] = None
    citation_text: Optional[str] = None
    review: bool = Field(
```

- [ ] **Step 5: Run the guardrail test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_models.py -v`
Expected: PASS (all tests, including the round-trip test - it never referenced these two fields directly, so it's unaffected)

- [ ] **Step 6: Rename the field references in Parish.pmt's prose**

In `Paleographer/prompts/Parish.pmt`, replace:
```
9. TRANSCRIPTION & TRANSLATION
- english_translation = full English translation.
- original_transcription = exact original French/Latin.
- Use English when filling in all structured fact fields. Use original_transcription just in the citation block.
```
with:
```
9. TRANSCRIPTION & TRANSLATION
- citation_details = full English translation.
- citation_text = exact original French/Latin.
- Use English when filling in all structured fact fields. Use citation_text just in the citation block.
```

- [ ] **Step 7: Rename the field references in Scrip.pmt's prose**

In `Paleographer/prompts/Scrip.pmt`, replace:
```
INSTRUCTION PRECEDENCE:
1. Preserve historical text exactly in raw_* fields and original_transcription.
2. Standardize only in std_* fields where explicitly instructed.
3. Never invent missing or unstated facts.

WORKFLOW:
1. Scan the image(s) to identify every distinct application or register entry.
2. For each document, transcribe the verbatim handwritten testimony, printed form responses,
   and margin notes into original_transcription.
3. Synthesize the "Commissioner's Review" summary into english_translation.
4. Extract all named participants (Claimant, Parents, Spouse, Children, Heirs, Witnesses, Commissioner).
5. Standardize names, split dit names, resolve maiden names, and format dates.
6. Populate the structured JSON.

COMMISSIONER'S REVIEW (english_translation field):
Populate english_translation with the "Commissioner's Review" — a comprehensive, clear AI summary
```
with:
```
INSTRUCTION PRECEDENCE:
1. Preserve historical text exactly in raw_* fields and citation_text.
2. Standardize only in std_* fields where explicitly instructed.
3. Never invent missing or unstated facts.

WORKFLOW:
1. Scan the image(s) to identify every distinct application or register entry.
2. For each document, transcribe the verbatim handwritten testimony, printed form responses,
   and margin notes into citation_text.
3. Synthesize the "Commissioner's Review" summary into citation_details.
4. Extract all named participants (Claimant, Parents, Spouse, Children, Heirs, Witnesses, Commissioner).
5. Standardize names, split dit names, resolve maiden names, and format dates.
6. Populate the structured JSON.

COMMISSIONER'S REVIEW (citation_details field):
Populate citation_details with the "Commissioner's Review" — a comprehensive, clear AI summary
```

- [ ] **Step 8: Run the full test suite**

Run: `python -m pytest --tb=short -q`
Expected: PASS, same count as before this task (schema.json and the .pmt prose aren't read by any test other than Commissioner's own guardrails, which already passed in Step 5)

- [ ] **Step 9: Commit**

```bash
git add Paleographer/schema.json Paleographer/prompts/Parish.pmt Paleographer/prompts/Scrip.pmt Commissioner/models.py Commissioner/tests/test_models.py
git commit -m "Rename original_transcription/english_translation to citation_text/citation_details in schema.json, prompts, and Commissioner"
```

---

### Task 2: Rename in Paleographer's runtime code and tests

**Files:**
- Modify: `Paleographer/engine.py:318-319`
- Modify: `Paleographer/Paleographer.py:256-257,934-935`
- Modify: `Paleographer/postprocess.py:209-231`
- Modify: `Paleographer/tests/test_paleographer_pipeline.py:144-145,269-270,346-347,370,378,402`
- Modify: `Paleographer/tests/test_postprocess.py:187-188,194-195,203-204,208,220-225,236-239,248-253,270-276,280,290,294-297`
- Modify: `Paleographer/tests/test_engine.py:387-388`
- Modify: `Paleographer/tests/test_schema.py:37-38,66-67,93,122`
- Test: all five files above, via pytest

**Interfaces:**
- Consumes: `Record.citation_text`/`Record.citation_details` naming from Task 1 (Paleographer's own record dicts must now use these keys to match what Commissioner and schema.json expect).
- Produces: every dict Paleographer constructs or reads with a `"citation_text"`/`"citation_details"` key instead of `"original_transcription"`/`"english_translation"`.

Archivist.py's citation-building code already checks `citation_text`/`citation_details` before falling back to the old names (its own pre-existing partial fix), so this task is safe on its own: nothing downstream breaks by Paleographer starting to produce the new names sooner.

- [ ] **Step 1: Rename in engine.py's continuation-prompt template**

In `Paleographer/engine.py`, replace:
```python
        transcription so far: {pending_record.get("original_transcription")}
        translation so far: {pending_record.get("english_translation")}
```
with:
```python
        transcription so far: {pending_record.get("citation_text")}
        translation so far: {pending_record.get("citation_details")}
```

- [ ] **Step 2: Rename in test_engine.py's fixture**

In `Paleographer/tests/test_engine.py`, replace:
```python
    pending = {
        "record_number": "44", "year": "1850", "event_type": "Baptism",
        "original_transcription": "Le 12 decembre, j'ai baptise",
        "english_translation": "On December 12, I baptized",
        "participants": [{"role_name": "Primary", "std_given": "Jean", "std_surname": "Gagne"}],
    }
```
with:
```python
    pending = {
        "record_number": "44", "year": "1850", "event_type": "Baptism",
        "citation_text": "Le 12 decembre, j'ai baptise",
        "citation_details": "On December 12, I baptized",
        "participants": [{"role_name": "Primary", "std_given": "Jean", "std_surname": "Gagne"}],
    }
```

- [ ] **Step 3: Run the engine test file**

Run: `python -m pytest Paleographer/tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 4: Rename in Paleographer.py's dict-builder and continuation-prompt template**

In `Paleographer/Paleographer.py`, replace:
```python
        "page": record.get("page"),
        "original_transcription": record.get("original_transcription"),
        "english_translation": record.get("english_translation"),
    }
```
with:
```python
        "page": record.get("page"),
        "citation_text": record.get("citation_text"),
        "citation_details": record.get("citation_details"),
    }
```

Then, further down in the same file, replace:
```python
        event_type: {pending_record.get("event_type")}
        transcription so far: {pending_record.get("original_transcription")}
        translation so far: {pending_record.get("english_translation")}
        participants captured so far: {json.dumps(participants_summary, ensure_ascii=False)}
```
with:
```python
        event_type: {pending_record.get("event_type")}
        transcription so far: {pending_record.get("citation_text")}
        translation so far: {pending_record.get("citation_details")}
        participants captured so far: {json.dumps(participants_summary, ensure_ascii=False)}
```

- [ ] **Step 5: Rename in postprocess.py's source-document builder and its docstring**

In `Paleographer/postprocess.py`, replace:
```python
def _source_document_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    """One record's own text, snapshotted as a source_documents list entry - see
    _merge_record_into. document_type/page identify WHICH physical document this text
    came from; Commissioner appends further entries to this same list later (certificate/
    grant downloads) using media_path instead of transcription text."""
    return {
        "document_type": _label_for(record),
        "page": record.get("page"),
        "original_transcription": record.get("original_transcription"),
        "english_translation": record.get("english_translation"),
    }


def _merge_record_into(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    """Merges `incoming` into `base` in place - `base` is what survives, `incoming` is
    discarded by the caller afterward. See merge_same_claim_records for when this runs.

    base's own top-level original_transcription/english_translation are left untouched
    (still just base's own text, unlabeled) - every document's text, including base's,
```
with:
```python
def _source_document_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    """One record's own text, snapshotted as a source_documents list entry - see
    _merge_record_into. document_type/page identify WHICH physical document this text
    came from; Commissioner appends further entries to this same list later (certificate/
    grant downloads) using media_path instead of transcription text."""
    return {
        "document_type": _label_for(record),
        "page": record.get("page"),
        "citation_text": record.get("citation_text"),
        "citation_details": record.get("citation_details"),
    }


def _merge_record_into(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    """Merges `incoming` into `base` in place - `base` is what survives, `incoming` is
    discarded by the caller afterward. See merge_same_claim_records for when this runs.

    base's own top-level citation_text/citation_details are left untouched
    (still just base's own text, unlabeled) - every document's text, including base's,
```

- [ ] **Step 6: Rename every occurrence in test_postprocess.py**

In `Paleographer/tests/test_postprocess.py`, there are 14 occurrences of `"original_transcription"` and 14 of `"english_translation"` (all as dict keys or dict-value assertions in test fixtures, e.g. `base["original_transcription"]`, `{"original_transcription": "witness text", ...}`). Replace every occurrence of the literal string `original_transcription` with `citation_text`, and every occurrence of the literal string `english_translation` with `citation_details`, throughout this file. This is a pure find-and-replace - the surrounding test logic, assertions, and structure are unchanged, only the key name changes.

Verify the count after: `grep -c "citation_text\|citation_details" Paleographer/tests/test_postprocess.py` should report at least 14 combined occurrences, and `grep -c "original_transcription\|english_translation" Paleographer/tests/test_postprocess.py` should report 0.

- [ ] **Step 7: Rename every occurrence in test_paleographer_pipeline.py**

In `Paleographer/tests/test_paleographer_pipeline.py`, replace every occurrence of `original_transcription` with `citation_text` and `english_translation` with `citation_details` (6 occurrences of each, in test fixture dicts and one keyword-argument call to a `_minimal_record(...)` helper, and one dict-key assertion `record_44["original_transcription"]`). Same pure find-and-replace as Step 6.

Verify: `grep -c "original_transcription\|english_translation" Paleographer/tests/test_paleographer_pipeline.py` should report 0 after.

- [ ] **Step 8: Rename every occurrence in test_schema.py**

In `Paleographer/tests/test_schema.py`, replace every occurrence of `english_translation` with `citation_details` and `original_transcription` with `citation_text` (4 occurrences of each, in fixture dicts used to test schema merging). Same pure find-and-replace.

Verify: `grep -c "original_transcription\|english_translation" Paleographer/tests/test_schema.py` should report 0 after.

- [ ] **Step 9: Run the full Paleographer test suite**

Run: `python -m pytest Paleographer/tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 10: Run the full project test suite**

Run: `python -m pytest --tb=short -q`
Expected: PASS, same total count as before this task

- [ ] **Step 11: Commit**

```bash
git add Paleographer/engine.py Paleographer/Paleographer.py Paleographer/postprocess.py Paleographer/tests/test_paleographer_pipeline.py Paleographer/tests/test_postprocess.py Paleographer/tests/test_engine.py Paleographer/tests/test_schema.py
git commit -m "Rename original_transcription/english_translation to citation_text/citation_details in Paleographer"
```

---

### Task 3: Rename in Voyageur's Census pipeline

**Files:**
- Modify: `Voyageur/census_schema.py:240`
- Modify: `Voyageur/Voyageur.py:228,815`
- Modify: `Voyageur/FS.py:364-365`

**Interfaces:**
- Consumes: `Record.citation_text`/`Record.citation_details` naming from Task 1.
- Produces: Census records now carry `"citation_text": ""` / `"citation_details": ""` instead of the old keys (Census never populates either field with real content, but the keys must match the shared schema).

No test files in `Voyageur/` reference these two fields (confirmed by search), so this task only touches the three source files.

- [ ] **Step 1: Rename in census_schema.py**

In `Voyageur/census_schema.py`, replace:
```python
                "event_place": place, "english_translation": "", "original_transcription": "",
```
with:
```python
                "event_place": place, "citation_details": "", "citation_text": "",
```

- [ ] **Step 2: Rename both occurrences in Voyageur.py**

In `Voyageur/Voyageur.py`, there are two occurrences of the exact same line, in two different builder functions. Replace each occurrence of:
```python
                "event_place": place, "english_translation": "", "original_transcription": "",
```
with:
```python
                "event_place": place, "citation_details": "", "citation_text": "",
```
and each occurrence of:
```python
        "english_translation": "", "original_transcription": "",
```
with:
```python
        "citation_details": "", "citation_text": "",
```
(One occurrence matches the first pattern at ~line 228 inside a household-record loop; the other matches the second pattern at ~line 815 inside a different per-row builder. Confirm both are changed - `grep -c "original_transcription\|english_translation" Voyageur/Voyageur.py` should report 0 after.)

- [ ] **Step 3: Rename in FS.py**

In `Voyageur/FS.py`, replace:
```python
        "english_translation": "",
        "original_transcription": "",
```
with:
```python
        "citation_details": "",
        "citation_text": "",
```

- [ ] **Step 4: Run the full project test suite**

Run: `python -m pytest --tb=short -q`
Expected: PASS, same total count as before this task (no existing test covers these three exact lines directly, since Census tests construct their own fixtures independently - this step exists to catch anything unexpected, not because a specific test targets this change)

- [ ] **Step 5: Commit**

```bash
git add Voyageur/census_schema.py Voyageur/Voyageur.py Voyageur/FS.py
git commit -m "Rename original_transcription/english_translation to citation_text/citation_details in Voyageur"
```

---

### Task 4: Collapse Archivist.py's citation building to citation_text/citation_details only

**Files:**
- Modify: `Archivist/Archivist.py:2641-2851`
- Modify: `Archivist/tests/test_archivist.py` (20 occurrences of `original_transcription`, 20 of `english_translation`)
- Modify: `Archivist/tests/test_census_ingestion.py:29-30`

**Interfaces:**
- Consumes: `citation_text`/`citation_details` keys now produced everywhere upstream (Tasks 1-3).
- Produces: `_build_citation_block(rec, part, tag_name, vol, media_uid, proof_status, target_software, document_type=None, page=None, citation_text=None, citation_details=None) -> str` - the `original_transcription`/`english_translation` parameters are removed entirely, not deprecated.

This is the only task that removes code rather than purely renaming it: `_build_citation_block` currently accepts both old and new parameter names with the new ones taking priority (the pre-existing partial fix). This task deletes the old ones.

- [ ] **Step 1: Remove the old-name parameters and their docstring reference**

In `Archivist/Archivist.py`, replace:
```python
def _build_citation_block(rec: dict, part: dict, tag_name: str, vol: str, media_uid: str,
                          proof_status: str, target_software: str, document_type: Optional[str] = None,
                          page: Optional[str] = None, original_transcription: Optional[str] = None,
                          english_translation: Optional[str] = None,
                          citation_text: Optional[str] = None,
                          citation_details: Optional[str] = None) -> str:
    """One SOUR citation block. build_general_citation calls this once per source
    document (or once, from rec's own top-level fields, when there's only one) - see
    that function for why. page/original_transcription/english_translation, when given,
    override rec's own top-level fields (a specific source_documents entry's own text);
    None falls back to rec's top-level fields, preserving the single-document path
    exactly as it always worked."""
```
with:
```python
def _build_citation_block(rec: dict, part: dict, tag_name: str, vol: str, media_uid: str,
                          proof_status: str, target_software: str, document_type: Optional[str] = None,
                          page: Optional[str] = None, citation_text: Optional[str] = None,
                          citation_details: Optional[str] = None) -> str:
    """One SOUR citation block. build_general_citation calls this once per source
    document (or once, from rec's own top-level fields, when there's only one) - see
    that function for why. page/citation_text/citation_details, when given,
    override rec's own top-level fields (a specific source_documents entry's own text);
    None falls back to rec's top-level fields, preserving the single-document path
    exactly as it always worked."""
```

- [ ] **Step 2: Collapse the fallback chain to a single name each**

In `Archivist/Archivist.py`, replace:
```python
    raw_orig = citation_text if citation_text is not None else (
        original_transcription if original_transcription is not None else (
            rec.get('citation_text') or rec.get('original_transcription')
        )
    )
    raw_trans = citation_details if citation_details is not None else (
        english_translation if english_translation is not None else (
            rec.get('citation_details') or rec.get('english_translation')
        )
    )
```
with:
```python
    raw_orig = citation_text if citation_text is not None else rec.get('citation_text')
    raw_trans = citation_details if citation_details is not None else rec.get('citation_details')
```

- [ ] **Step 3: Update the call site in build_general_citation**

In `Archivist/Archivist.py`, replace:
```python
        blocks.append(_build_citation_block(
            rec, part, tag_name, vol, doc_media_uid, proof_status, target_software,
            document_type=doc.get('document_type'), page=doc.get('page'),
            original_transcription=doc.get('original_transcription'),
            english_translation=doc.get('english_translation'),
            citation_text=doc.get('citation_text'),
            citation_details=doc.get('citation_details'),
        ))
```
with:
```python
        blocks.append(_build_citation_block(
            rec, part, tag_name, vol, doc_media_uid, proof_status, target_software,
            document_type=doc.get('document_type'), page=doc.get('page'),
            citation_text=doc.get('citation_text'),
            citation_details=doc.get('citation_details'),
        ))
```

- [ ] **Step 4: Run test_archivist.py to see it now fail**

Run: `python -m pytest Archivist/tests/test_archivist.py -v`
Expected: FAIL - multiple tests construct `rec` fixtures using `"original_transcription"`/`"english_translation"` keys, which `_build_citation_block` no longer reads at all (no fallback left), so citation text/translation will come out empty in the generated GEDCOM blocks and assertions on that text will fail.

- [ ] **Step 5: Rename every occurrence in test_archivist.py**

In `Archivist/tests/test_archivist.py`, replace every occurrence of the literal string `original_transcription` with `citation_text`, and every occurrence of `english_translation` with `citation_details` (20 occurrences of each, across test fixture dicts for `build_general_citation` and `_merge_record_into`-style tests). Pure find-and-replace - the test logic, assertions, and docstrings describing behavior are unchanged; only the fixture key names change. Note: one test docstring (around the "collapses_identical_original_and_translation" test) already references the words "English Translation:"/"Original Transcription:" as GEDCOM header labels being duplicated - those are prose describing the *header text* Archivist emits (a separate, pre-existing `GENERAL_CONFIG` default unrelated to this field rename) and should NOT be changed; only the dict *keys* `original_transcription`/`english_translation` change.

Verify: `grep -c "original_transcription\|english_translation" Archivist/tests/test_archivist.py` should report 0 after (aside from any occurrence inside a string literal describing header text, if present - check manually if the count seems off from 40).

- [ ] **Step 6: Rename in test_census_ingestion.py**

In `Archivist/tests/test_census_ingestion.py`, replace:
```python
            "year": "1900", "event_date": "", "event_place": "", "english_translation": "",
            "original_transcription": "", "review": False, "review_reason": None,
```
with:
```python
            "year": "1900", "event_date": "", "event_place": "", "citation_details": "",
            "citation_text": "", "review": False, "review_reason": None,
```

- [ ] **Step 7: Run Archivist's full test suite**

Run: `python -m pytest Archivist/tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 8: Run the full project test suite**

Run: `python -m pytest --tb=short -q`
Expected: PASS, same total count as the very first run before Task 1 - this rename is complete project-wide.

- [ ] **Step 9: Verify no occurrences remain anywhere**

Run: `grep -rn "original_transcription\|english_translation" --include=*.py --include=*.pmt --include=*.json .`
Expected: no output (aside from this plan file and the design spec, which are historical records of the change and are not live code - if the grep is run without excluding `docs/`, filter those out manually).

- [ ] **Step 10: Commit**

```bash
git add Archivist/Archivist.py Archivist/tests/test_archivist.py Archivist/tests/test_census_ingestion.py
git commit -m "Collapse Archivist.py citation building to citation_text/citation_details only"
```

---

## Self-Review

**Spec coverage:**
- schema.json, both `.pmt` prompts, Commissioner rename → Task 1.
- Paleographer's `engine.py`/`Paleographer.py`/`postprocess.py` and their tests → Task 2.
- Voyageur's Census pipeline (`census_schema.py`, `Voyageur.py`, `FS.py`) → Task 3.
- Archivist.py's fallback removal (no compatibility shim) and its tests → Task 4.
- "No behavior change" (Parish stays a full translation, Scrip stays a synopsis) → no task touches any prompt instruction beyond the field-name references themselves; verified by re-reading each `.pmt` edit against the original prose.
- "Tests stay green after each group, not just at the end" → every task ends with a full-suite run, not just its own subdirectory.

**Placeholder scan:** No TBD/TODO; every step shows exact before/after content or, for the highest-occurrence-count files, an exact literal string to find-and-replace plus a verification command with an expected count.

**Type consistency:** `Record.citation_text`/`Record.citation_details` (Task 1) are the same two names used in every subsequent task's code and test fixtures - Task 2's `record.get("citation_text")`, Task 3's dict literals, and Task 4's `_build_citation_block` parameters and `rec.get('citation_text')`/`rec.get('citation_details')` calls all match exactly.
