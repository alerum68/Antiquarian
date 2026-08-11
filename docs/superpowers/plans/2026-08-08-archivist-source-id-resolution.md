# Archivist Source ID Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Replace Scrip's collision-prone `@S{vol}@` source-ID formula and HBCA's hardcoded shared `@S10009@` with real, live-verified platform collection identifiers (LAC's MIKAN number, Archives of Manitoba Keystone's REFD number), and capture FamilySearch's collection code (`cc`) for future use, while leaving Parish/Census's existing working schemes untouched.

**Architecture:** Each platform's collection identifier is captured as close to its source as possible (LAC's MIKAN during Paleographer's existing live-metadata enrichment pass; Keystone's REFD during a new, parallel Paleographer enrichment pass for HBCA) and stored in `type_specific_fields`/`source_documents`, the same places sibling metadata (`rg_series_code`, `reel_numbers`, `keystone_urls`) already live. Consumption happens in `Archivist/General.py`: the `Profile.dynamic_source_id()` protocol method gains an optional `rec` parameter so `ScripProfile` can read `collection_mikan` when present (falling back to today's formula otherwise), and a new `source_id_override` parameter on `_build_citation_block` lets `HBCAProfile` route each of a record's `source_documents` to its own resolved Source. A new `owns_source_records()` profile hook stops the generic `get_volume_sources()` from emitting a redundant, now-orphaned block for profiles (HBCA) that build their own complete source templates.

**Tech Stack:** Python, BeautifulSoup (`lac_client.py`'s existing HTML parsing), pytest, existing golden-file GEDCOM regression tests (`Archivist/tests/golden/`).

## Global Constraints

- **Backward compatible by construction.** Every new field (`collection_mikan`, `resolved_source_id`) is optional and additive. When absent, every changed function must fall back to exactly its current behavior — this is what keeps the existing golden-file tests (`Archivist/tests/test_archivist_dispatcher.py::test_scrip_*_matches_golden`, `test_parish_*_matches_golden`) passing unchanged throughout this plan, since none of today's fixture data carries these new fields.
- **No change to Parish/Census/manual source ID resolution.** `GeneralProfile.dynamic_source_id()` (the `REGISTER_SOURCE_ID`-driven scheme) and `Utils.PRECODED_SOURCE_IDS` (Census) are out of scope — confirmed as an open question in the design spec, not resolved during brainstorming. Do not touch `GeneralProfile.dynamic_source_id()`'s body in any task.
- **FS's `cc` is captured but not yet wired into source-ID resolution** in this plan (same reasoning — which record types/profiles should consume it wasn't resolved during brainstorming). Task 7 stops at getting `cc` into the JSON.
- **Full `pytest` suite stays green after every task.** Run the whole suite (not just the task's own test file) before each commit, since Profile protocol signature changes (Task 4) ripple across three files.
- Follow existing import patterns exactly: Paleographer modules import sibling `Voyageur` modules via the `_REPO_ROOT` sys.path insert + try/except cascade already established in `Paleographer/ScripTools.py:24-34`.

---

## File Structure

- **Modify:** `Voyageur/lac_client.py` — `RecordMetadata` gains `collection_mikan`; `get_record_metadata()` parses it from the hierarchy breadcrumb already present in the fetched page.
- **Modify:** `Voyageur/LAC.py` — `download_pid_bundle()` threads `collection_mikan` into its returned bundle dict.
- **Modify:** `Paleographer/ScripTools.py` — `enrich_record_from_lac_metadata()` and `cross_check_claim_record()` merge `collection_mikan` into `record['type_specific_fields']`.
- **Modify:** `Archivist/General.py` — `Profile` protocol's `dynamic_source_id()` gains an optional `rec` parameter; `get_dynamic_source_id()` and its three per-record call sites (`generate_uid`, `generate_fam_uid`, `_build_citation_block`) pass `rec` through; `_build_citation_block` gains `source_id_override`; `build_general_citation`'s existing per-`source_documents` loop passes it; `get_volume_sources`/`build_gedcom_from_general` dedupe by resolved source ID instead of raw volume and gain the `owns_source_records()` guard.
- **Modify:** `Archivist/Scrip.py` — `ScripProfile.dynamic_source_id()` reads `collection_mikan` from `rec['type_specific_fields']` when given, falling back to the existing `vol_digits` formula.
- **Modify:** `Voyageur/FS.py`, `Voyageur/Voyageur.js` — capture FamilySearch's `cc` URL parameter alongside `item_id`, threaded into the citation dict.
- **Modify:** `Voyageur/HBCA.py` — new `parse_keystone_refd()` function; `query_keystone_for_code()`'s return dict gains a `refd` key.
- **Create:** `Paleographer/HBCATools.py` — `enrich_hbca_json_data()`, mirroring `ScripTools.enrich_json_data()`'s pattern: reads each record's AI-extracted `type_specific_fields.hbca_references`, resolves each to a Keystone REFD, and populates `record['source_documents']`.
- **Modify:** `Paleographer/Paleographer.py` — dispatch a new `enrich-hbca` mode to `HBCATools.main()`.
- **Modify:** `Archivist/HBCA.py` — `HBCAProfile.resolve_source_templates()` rewritten to emit one block per distinct REFD actually used (read from `source_documents`) instead of the single hardcoded `@S10009@` block; `owns_source_records()` returns `True`.
- **Test:** `Voyageur/tests/test_lac.py`, `Paleographer/tests/test_crosscheck.py`, `Archivist/tests/test_profile_parity.py`, `Archivist/tests/test_general_smoke.py`, `Archivist/tests/test_archivist_dispatcher.py` (golden regression), `Voyageur/tests/test_fs.py`, `Voyageur/tests/test_hbca_keystone.py`, `Archivist/tests/test_hbca_profile.py`, new `Paleographer/tests/test_hbcatools.py`.

---

### Task 1: LAC MIKAN parsing in `lac_client.py`

**Files:**
- Modify: `Voyageur/lac_client.py:80-92` (`RecordMetadata`), `Voyageur/lac_client.py:122-163` (`get_record_metadata`)
- Test: `Voyageur/tests/test_lac.py`

**Interfaces:**
- Produces: `RecordMetadata.collection_mikan: Optional[str]` — the MIKAN number (digits only, as a string) of the item's immediate parent in LAC's hierarchy breadcrumb, or `None` if the hierarchy has fewer than 2 levels.

- [ ] **Step 1: Write the failing test**

Add to `Voyageur/tests/test_lac.py` (fixture HTML condensed from a real captured LAC record page, PID 1502188 — "Scrip affidavit for Letendre, Roger", confirmed live during this design's investigation: fonds id=30 → branch id=134031 → series id=134034 → item id=1502188):

```python
def test_get_record_metadata_extracts_collection_mikan(monkeypatch):
    html = """
    <html><head><title>Scrip affidavit for Letendre, Roger (3 digital object(s))</title></head>
    <body>
    <div id="jq-container-body-recordmediaphysicalmanifestationcontainernotefonandcol1502188">C-14930 : Copy No. 1</div>
    <div id="jq-container-body-recordcontrolnumbercode151textfonandcol1502188">RG15-D-II-8-a</div>
    <div id="jq-context-hierarchycontext-fonandcol1502188">
      <ul id="jq-context-ul-hierarchycontext-fonandcol1502188">
        <li class="CFCS-table-indent-0">
          <div class="CFCS-display-table-row"><div class="CFCS-display-table-cell">
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=30&lang=eng">Department of the Interior fonds</a>
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=446&lang=eng" title="Fonds du ministere de l'Interieur"><img src="/images/equiv.png"></a>
          </div></div>
        </li>
        <li class="CFCS-table-indent-1">
          <div class="CFCS-display-table-row"><div class="CFCS-display-table-cell">
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=134031&lang=eng">Dominion Lands Branch</a>
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=164132&lang=eng" title="Direction des terres federales"><img src="/images/equiv.png"></a>
          </div></div>
        </li>
        <li class="CFCS-table-indent-2">
          <div class="CFCS-display-table-row"><div class="CFCS-display-table-cell">
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=134034&lang=eng">Metis and Original White Settlers affidavits</a>
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=164144&lang=eng" title="Affidavits des Metis"><img src="/images/equiv.png"></a>
          </div></div>
        </li>
        <li class="CFCS-table-indent-3">
          <div class="CFCS-display-table-row"><div class="CFCS-display-table-cell">
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=1502188&lang=eng">Scrip affidavit for Letendre, Roger</a>
          </div></div>
        </li>
      </ul>
    </div>
    </body></html>
    """

    class FakeResp:
        status_code = 200
        content = html.encode("utf-8")

    class FakeScraper:
        def get(self, url, timeout=None):
            return FakeResp()

    monkeypatch.setattr(lac_client, "_get_scraper", lambda: FakeScraper())

    metadata = lac_client.get_record_metadata("1502188")

    assert metadata.collection_mikan == "134034"


def test_get_record_metadata_collection_mikan_none_when_hierarchy_too_shallow(monkeypatch):
    html = """
    <html><head><title>Some Record (1 digital object(s))</title></head>
    <body>
    <div id="jq-context-hierarchycontext-fonandcol999">
      <ul id="jq-context-ul-hierarchycontext-fonandcol999">
        <li class="CFCS-table-indent-0">
          <div class="CFCS-display-table-row"><div class="CFCS-display-table-cell">
            <a href="https://central.bac-lac.gc.ca:443/.redirect?app=FonAndCol&id=999&lang=eng">Some Record</a>
          </div></div>
        </li>
      </ul>
    </div>
    </body></html>
    """

    class FakeResp:
        status_code = 200
        content = html.encode("utf-8")

    class FakeScraper:
        def get(self, url, timeout=None):
            return FakeResp()

    monkeypatch.setattr(lac_client, "_get_scraper", lambda: FakeScraper())

    metadata = lac_client.get_record_metadata("999")

    assert metadata.collection_mikan is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Voyageur/tests/test_lac.py -k collection_mikan -v`
Expected: FAIL with `AttributeError: 'RecordMetadata' object has no attribute 'collection_mikan'`

- [ ] **Step 3: Implement**

In `Voyageur/lac_client.py`, add the field to `RecordMetadata` (after `series_code`, `lac_client.py:88-92`):

```python
    series_code: Optional[str]  # e.g. "RG15-D-II-8-a" - ...
    collection_mikan: Optional[str]  # LAC's own numeric catalog ID (MIKAN) for the item's
    # immediate parent in its hierarchy breadcrumb (fonds -> branch -> series -> item) -
    # e.g. "134034" for "Metis and Original White Settlers affidavits". None if the
    # hierarchy has fewer than 2 levels. Structural (relative to the leaf item), not a
    # fixed depth, so it holds for any LAC-gathered record type, not just Scrip.
```

Then in `get_record_metadata()` (after the `control_el`/`series_code` block, `lac_client.py:159-160`), add the parsing and thread it into the return:

```python
    hierarchy_el = soup.find(id=re.compile(r"^jq-context-ul-hierarchycontext"))
    collection_mikan = None
    if hierarchy_el:
        level_ids = []
        for li in hierarchy_el.find_all("li", recursive=False):
            link = next((a for a in li.find_all("a", href=True) if a.get_text(strip=True)), None)
            if link:
                id_match = re.search(r"[?&]id=(\d+)", link["href"])
                if id_match:
                    level_ids.append(id_match.group(1))
        if len(level_ids) >= 2:
            collection_mikan = level_ids[-2]

    return RecordMetadata(pid=pid, title=title, digital_object_count=digital_object_count,
                          reel_numbers=reel_numbers, series_code=series_code,
                          collection_mikan=collection_mikan)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Voyageur/tests/test_lac.py -k collection_mikan -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite to check for RecordMetadata construction breakage**

Run: `pytest -q`
Expected: PASS. (`RecordMetadata` is a dataclass with no default for the new field, so any other test constructing it directly, not through `get_record_metadata()`, will fail loudly with a clear `TypeError: missing 1 required positional argument` — fix any such call site by adding `collection_mikan=None`.)

- [ ] **Step 6: Commit**

```bash
git add Voyageur/lac_client.py Voyageur/tests/test_lac.py
git commit -m "feat(lac): parse collection MIKAN number from hierarchy breadcrumb"
```

---

### Task 2: Thread `collection_mikan` through `download_pid_bundle`

**Files:**
- Modify: `Voyageur/LAC.py:279-311`
- Test: `Voyageur/tests/test_lac.py`

**Interfaces:**
- Consumes: `lac_client.RecordMetadata.collection_mikan` (Task 1)
- Produces: `download_pid_bundle(pid, media_dir, ...)`'s returned dict gains a `"collection_mikan"` key.

- [ ] **Step 1: Write the failing test**

```python
def test_download_pid_bundle_includes_collection_mikan(monkeypatch, tmp_path):
    fake_metadata = lac_client.RecordMetadata(
        pid="1502188", title="Scrip affidavit for Letendre, Roger",
        digital_object_count=3, reel_numbers=["C-14930"],
        series_code="RG15-D-II-8-a", collection_mikan="134034",
    )
    monkeypatch.setattr(lac_client, "get_record_metadata", lambda pid: fake_metadata)
    monkeypatch.setattr(lac_client, "get_manifest", lambda pid: [])

    bundle = LAC.download_pid_bundle("1502188", str(tmp_path))

    assert bundle["collection_mikan"] == "134034"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Voyageur/tests/test_lac.py -k download_pid_bundle_includes_collection_mikan -v`
Expected: FAIL with `KeyError: 'collection_mikan'`

- [ ] **Step 3: Implement**

In `Voyageur/LAC.py`, `download_pid_bundle` (`LAC.py:305-311`):

```python
    return {
        "pid": pid,
        "lac_catalog_title": metadata.title,
        "reel_numbers": metadata.reel_numbers,
        "series_code": metadata.series_code,
        "collection_mikan": metadata.collection_mikan,
        "source_documents": entries,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Voyageur/tests/test_lac.py -k download_pid_bundle_includes_collection_mikan -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Voyageur/LAC.py Voyageur/tests/test_lac.py
git commit -m "feat(lac): thread collection_mikan through download_pid_bundle"
```

---

### Task 3: Merge `collection_mikan` into `type_specific_fields` (ScripTools.py)

**Files:**
- Modify: `Paleographer/ScripTools.py:472-554` (`cross_check_claim_record`, `enrich_record_from_lac_metadata`)
- Test: `Paleographer/tests/test_crosscheck.py`

**Interfaces:**
- Consumes: `bundle["collection_mikan"]` (Task 2), `metadata.collection_mikan` (Task 1)
- Produces: `record["type_specific_fields"]["collection_mikan"]`

- [ ] **Step 1: Write the failing tests**

Add to `Paleographer/tests/test_crosscheck.py` (matching that file's existing fixture/mocking conventions for `cross_check_claim_record` and `enrich_record_from_lac_metadata` — read the file's existing tests for the exact monkeypatch targets it uses for `voyageur_lac.download_pid_bundle` and `lac_client.get_record_metadata` before writing these, and follow the same pattern):

```python
def test_cross_check_claim_record_merges_collection_mikan(monkeypatch):
    record = {"document_metadata": {"file_name": "e000016743.pdf"}}
    monkeypatch.setattr(
        ScripTools.voyageur_lac, "download_pid_bundle",
        lambda pid, media_dir, document_type_override=None: {
            "lac_catalog_title": "Scrip affidavit for Letendre, Roger",
            "reel_numbers": ["C-14930"],
            "series_code": "RG15-D-II-8-a",
            "collection_mikan": "134034",
            "source_documents": [],
        },
    )
    monkeypatch.setattr(ScripTools, "build_claim_search_queries", lambda rec: [])

    result = ScripTools.cross_check_claim_record(record, cookies={}, media_dir="media")

    assert result["type_specific_fields"]["collection_mikan"] == "134034"


def test_enrich_record_from_lac_metadata_merges_collection_mikan():
    sheet = {"document_metadata": {}}
    record = {}
    metadata = ScripTools.lac_client.RecordMetadata(
        pid="1502188", title="Scrip affidavit for Letendre, Roger",
        digital_object_count=3, reel_numbers=["C-14930"],
        series_code="RG15-D-II-8-a", collection_mikan="134034",
    )

    ScripTools.enrich_record_from_lac_metadata(sheet, record, metadata)

    assert record["type_specific_fields"]["collection_mikan"] == "134034"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Paleographer/tests/test_crosscheck.py -k collection_mikan -v`
Expected: FAIL with `KeyError: 'collection_mikan'`

- [ ] **Step 3: Implement**

In `Paleographer/ScripTools.py`, `cross_check_claim_record` (`ScripTools.py:485-490`):

```python
            record["lac_catalog_title"] = fix_mojibake(own_bundle["lac_catalog_title"])
            type_fields = record.setdefault("type_specific_fields", {})
            if own_bundle.get("reel_numbers"):
                type_fields["reel_numbers"] = ", ".join(own_bundle["reel_numbers"])
            if own_bundle.get("series_code"):
                type_fields["rg_series_code"] = own_bundle["series_code"]
            if own_bundle.get("collection_mikan"):
                type_fields["collection_mikan"] = own_bundle["collection_mikan"]
```

And `enrich_record_from_lac_metadata` (`ScripTools.py:538-542`):

```python
    type_fields = record.setdefault("type_specific_fields", {})
    if metadata.series_code and not type_fields.get("rg_series_code"):
        type_fields["rg_series_code"] = metadata.series_code
    if metadata.reel_numbers and not type_fields.get("reel_numbers"):
        type_fields["reel_numbers"] = ", ".join(metadata.reel_numbers)
    if metadata.collection_mikan and not type_fields.get("collection_mikan"):
        type_fields["collection_mikan"] = metadata.collection_mikan
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Paleographer/tests/test_crosscheck.py -k collection_mikan -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Paleographer/ScripTools.py Paleographer/tests/test_crosscheck.py
git commit -m "feat(scriptools): merge collection_mikan into type_specific_fields"
```

---

### Task 4: `Profile.dynamic_source_id()` gains optional `rec` parameter

**Files:**
- Modify: `Archivist/General.py:102-107` (`GeneralProfile`), `Archivist/General.py:289-291` (`get_dynamic_source_id`), `Archivist/General.py:362-364,518-520,538-539,1007-1008` (call sites), `Archivist/Scrip.py:313-315` (`ScripProfile`), `Archivist/HBCA.py:28-30` (`HBCAProfile`)
- Test: `Archivist/tests/test_profile_parity.py`

**Interfaces:**
- Produces: `Profile.dynamic_source_id(self, vol_digits: str, rec: Optional[dict] = None) -> str` (new protocol shape — every implementation ignores `rec` except `ScripProfile`, changed in Task 5). `get_dynamic_source_id(vol_val: str, rec: Optional[dict] = None) -> str`.

- [ ] **Step 1: Write the failing test**

The existing `test_dynamic_source_id_scrip_has_no_register_prefix` in `Archivist/tests/test_profile_parity.py` already asserts `SCRIP.dynamic_source_id("3") == "@S003@"` with no `rec` — this must keep passing unchanged (proves the default stays backward compatible). Add a new test alongside it for the `rec`-aware call shape (still asserting today's fallback behavior, since Task 5 is what makes `ScripProfile` actually use `rec`):

```python
def test_dynamic_source_id_accepts_optional_rec_param():
    # GeneralProfile and HBCAProfile must accept (and ignore) a rec kwarg without erroring.
    assert GENERAL.dynamic_source_id("3", rec={"type_specific_fields": {}}) == GENERAL.dynamic_source_id("3")
```

Add to `Archivist/tests/test_hbca_profile.py` (mirroring its existing style — read the file first for its exact fixture conventions):

```python
def test_hbca_dynamic_source_id_accepts_optional_rec_param():
    profile = HBCA.HBCAProfile()
    assert profile.dynamic_source_id("1", rec={}) == profile.dynamic_source_id("1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Archivist/tests/test_profile_parity.py Archivist/tests/test_hbca_profile.py -k optional_rec -v`
Expected: FAIL with `TypeError: dynamic_source_id() got an unexpected keyword argument 'rec'`

- [ ] **Step 3: Implement**

`Archivist/General.py`, `GeneralProfile.dynamic_source_id` (`General.py:103-107`):

```python
    def dynamic_source_id(self, vol_digits: str, rec: Optional[dict] = None) -> str:
        base_id = re.sub(r'\D', '', f"{GENERAL_CONFIG.get('register_source_id', '1')}")
        if base_id.endswith('001') and len(base_id) > 1:
            base_id = base_id[:-3]
        return f"@S{base_id or '1'}{vol_digits.zfill(3)}@"
```

`Archivist/General.py`, `get_dynamic_source_id` (`General.py:289-291`):

```python
def get_dynamic_source_id(vol_val: str, rec: Optional[dict] = None) -> str:
    vol_digits = re.sub(r'\D', '', f"{vol_val or '1'}") or '1'
    return _ACTIVE_PROFILE.dynamic_source_id(vol_digits, rec)
```

Update the three per-record call sites to pass `rec` (each already has `rec` in scope):

`General.py:362` (`generate_uid`): `src_id = re.sub(r'\D', '', get_dynamic_source_id(vol, rec))`

`General.py:519` (`generate_fam_uid`): `src_id = re.sub(r'\D', '', get_dynamic_source_id(vol, rec))`

`General.py:539` (`_build_citation_block`): `sour_id = f"@S{template_id}@" if template_id else get_dynamic_source_id(vol, rec)`

`General.py:1007-1008` (`get_volume_sources` — left as `get_dynamic_source_id(vol)` for now, since it doesn't have a single `rec` in scope yet; changed in Task 6):

Leave unchanged in this task.

`Archivist/Scrip.py`, `ScripProfile.dynamic_source_id` (`Scrip.py:314-315`) — accept and ignore for now (Task 5 implements the real logic):

```python
    def dynamic_source_id(self, vol_digits: str, rec: Optional[dict] = None) -> str:
        return f"@S{vol_digits.zfill(3)}@"
```

`Archivist/HBCA.py`, `HBCAProfile.dynamic_source_id` (`HBCA.py:29-30`):

```python
    def dynamic_source_id(self, vol_digits: str, rec: Optional[dict] = None) -> str:
        return f"@S{HBCA_TEMPLATE_ID}@"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Archivist/tests/test_profile_parity.py Archivist/tests/test_hbca_profile.py -v`
Expected: PASS, including the pre-existing `test_dynamic_source_id_scrip_has_no_register_prefix` unchanged.

- [ ] **Step 5: Run the full test suite and the golden regression explicitly**

Run: `pytest -q` then `pytest Archivist/tests/test_archivist_dispatcher.py -v`
Expected: PASS. The golden files must be byte-identical to before this task — confirms the signature change alone caused zero behavior change.

- [ ] **Step 6: Commit**

```bash
git add Archivist/General.py Archivist/Scrip.py Archivist/HBCA.py Archivist/tests/test_profile_parity.py Archivist/tests/test_hbca_profile.py
git commit -m "refactor(archivist): Profile.dynamic_source_id accepts optional rec"
```

---

### Task 5: `ScripProfile.dynamic_source_id` uses `collection_mikan`

**Files:**
- Modify: `Archivist/Scrip.py:314-315`
- Test: `Archivist/tests/test_profile_parity.py`

**Interfaces:**
- Consumes: `rec['type_specific_fields']['collection_mikan']` (Task 3)
- Produces: `ScripProfile.dynamic_source_id(vol_digits, rec)` returns `@S{collection_mikan}@` when available.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_profile_parity.py`:

```python
def test_dynamic_source_id_scrip_uses_collection_mikan_when_present():
    rec_with_mikan = {"type_specific_fields": {"collection_mikan": "134034"}}
    assert SCRIP.dynamic_source_id("3", rec=rec_with_mikan) == "@S134034@"


def test_dynamic_source_id_scrip_falls_back_without_collection_mikan():
    assert SCRIP.dynamic_source_id("3", rec={"type_specific_fields": {}}) == "@S003@"
    assert SCRIP.dynamic_source_id("3", rec=None) == "@S003@"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Archivist/tests/test_profile_parity.py -k collection_mikan -v`
Expected: FAIL — `test_dynamic_source_id_scrip_uses_collection_mikan_when_present` asserts `@S134034@`, gets `@S003@`.

- [ ] **Step 3: Implement**

`Archivist/Scrip.py`:

```python
    def dynamic_source_id(self, vol_digits: str, rec: Optional[dict] = None) -> str:
        if rec:
            collection_mikan = Utils.clean_val((rec.get('type_specific_fields') or {}).get('collection_mikan'))
            if collection_mikan:
                return f"@S{collection_mikan}@"
        return f"@S{vol_digits.zfill(3)}@"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Archivist/tests/test_profile_parity.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite + golden regression**

Run: `pytest -q` then `pytest Archivist/tests/test_archivist_dispatcher.py -v`
Expected: PASS unchanged (the golden Scrip fixture has no `collection_mikan` in its `type_specific_fields`, so falls through to the unchanged formula).

- [ ] **Step 6: Commit**

```bash
git add Archivist/Scrip.py Archivist/tests/test_profile_parity.py
git commit -m "feat(scrip): use collection_mikan for source ID when available"
```

---

### Task 6: `get_volume_sources` dedupes by resolved source ID; `owns_source_records()` hook

**Files:**
- Modify: `Archivist/General.py:102-267` (add `owns_source_records` to `GeneralProfile`), `Archivist/General.py:1002-1033` (`get_volume_sources`), `Archivist/General.py:1064-1138` (`build_gedcom_from_general`), `Archivist/Scrip.py` (`ScripProfile.owns_source_records`), `Archivist/HBCA.py` (`HBCAProfile.owns_source_records` — added here as `False`; flipped to `True` in Task 11 once HBCA fully owns its own source blocks)
- Test: `Archivist/tests/test_general_smoke.py`, golden regression via `Archivist/tests/test_archivist_dispatcher.py`

**Interfaces:**
- Consumes: `get_dynamic_source_id(vol, rec)` (Task 4)
- Produces: `Profile.owns_source_records(self) -> bool` (new protocol method, default `False`). `get_volume_sources(sources_used: Dict[str, str], target_software: str) -> list` (signature change: was `volumes_used: set`, now a dict mapping resolved source ID to a representative `vol` string for display text).

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_general_smoke.py` (read the file first for its existing fixture-building helpers and mirror them):

```python
def test_get_volume_sources_dedupes_by_resolved_source_id():
    General.set_active_profile(Scrip.ScripProfile())
    try:
        sources_used = {
            "@S134034@": "1319",  # two different volumes, same collection_mikan
        }
        blocks = General.get_volume_sources(sources_used, "RM")
        sour_headers = [line for line in blocks if line.startswith("0 ")]
        assert sour_headers == ["0 @S134034@ SOUR"]
    finally:
        General.set_active_profile(General.GeneralProfile())


def test_build_gedcom_from_general_emits_one_source_for_shared_collection_mikan():
    json_data = {
        "record_type_name": "Scrip",
        "sheets": [
            {
                "document_metadata": {"file_name": "a.jpg", "file_type": "jpg", "volume": "1319"},
                "records": [{
                    "record_id": "R1", "page": "1", "year": "1880",
                    "type_specific_fields": {"collection_mikan": "134034", "claim_number": "1"},
                    "participants": [{"role_semantic": "primary", "std_given": "A", "std_surname": "B",
                                       "role_name": "Claimant"}],
                }],
            },
            {
                "document_metadata": {"file_name": "b.jpg", "file_type": "jpg", "volume": "1320"},
                "records": [{
                    "record_id": "R2", "page": "1", "year": "1880",
                    "type_specific_fields": {"collection_mikan": "134034", "claim_number": "2"},
                    "participants": [{"role_semantic": "primary", "std_given": "C", "std_surname": "D",
                                       "role_name": "Claimant"}],
                }],
            },
        ],
    }
    General.set_active_profile(Scrip.ScripProfile())
    try:
        ged = General.build_gedcom_from_general(json_data, "RM")
    finally:
        General.set_active_profile(General.GeneralProfile())

    assert ged.count("0 @S134034@ SOUR") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Archivist/tests/test_general_smoke.py -k "dedupes_by_resolved_source_id or shared_collection_mikan" -v`
Expected: FAIL — with today's code, `get_volume_sources` takes a `set` not a `dict` (first test errors on iteration), and the second test's two different volumes each produce their own `0 @S...@ SOUR` block (two blocks, not one — since today's `dynamic_source_id` isn't yet reached in this collapsed form).

- [ ] **Step 3: Implement**

`Archivist/General.py`, `GeneralProfile` — add alongside its other methods (near `family_uid`, `General.py:112-113`):

```python
    def owns_source_records(self) -> bool:
        return False
```

`Archivist/Scrip.py`, `ScripProfile` — add alongside `family_uid` (`Scrip.py:324-327`):

```python
    def owns_source_records(self) -> bool:
        return False
```

`Archivist/HBCA.py`, `HBCAProfile` — add alongside `family_uid` (`HBCA.py:35-36`):

```python
    def owns_source_records(self) -> bool:
        return False
```

`Archivist/General.py`, `get_volume_sources` (`General.py:1002-1033`) — rename the parameter and use it directly as the source ID (no more per-vol `get_dynamic_source_id` call inside the loop, since the caller now resolves and dedupes it):

```python
def get_volume_sources(sources_used: Dict[str, str], target_software: str) -> list:
    """Generates register-specific source records, one per distinct resolved source ID
    (deduped upstream in build_gedcom_from_general - see the module docstring on why this
    is no longer keyed by raw volume: a single collection, e.g. an LAC MIKAN-identified
    series, can span many volumes, and must produce exactly one SOUR block, not one per
    volume)."""
    loc_full = GENERAL_CONFIG['parish_location']
    sour_lines = []

    for s_id, vol in sorted(sources_used.items()):
        v_clause = f", Volume {vol}" if vol else ""
        v_title = f"{GENERAL_CONFIG['volume_title']}{v_clause}"

        if target_software == "RM":
            block = [f"0 {s_id} SOUR",
                     f"1 ABBR {GENERAL_CONFIG['parish_name']} {v_title}",
                     f"1 REFN {s_id.replace('@S', '').replace('@', '')}",
                     f"1 TITL {GENERAL_CONFIG['parish_name']}, , {GENERAL_CONFIG['register_name']}{v_clause} ; "
                     f"{v_title}, {GENERAL_CONFIG['parish_name']}, {loc_full}.",
                     f"1 _SUBQ {GENERAL_CONFIG['parish_name']} - {loc_full}.",
                     f"1 _BIBL {GENERAL_CONFIG['parish_name']}. {v_title}. "
                     f"{GENERAL_CONFIG['parish_name']}, {loc_full}."]

            block.extend(_ACTIVE_PROFILE.volume_source_detail_fields(v_clause))
            block.extend(Utils.weblink_lines(COLLECTION_URL, COLLECTION_NAME, "RM"))
        else:
            block = [f"0 {s_id} SOUR",
                     f"1 TITL {GENERAL_CONFIG['parish_name']}, {v_title}",
                     f"1 AUTH {GENERAL_CONFIG['parish_name']}",
                     f"1 PUBL {REPOSITORY_LOC}: {REPOSITORY}", f"1 REFN {s_id.replace('@S', '').replace('@', '')}"]
            block.extend(Utils.weblink_lines(COLLECTION_URL, COLLECTION_NAME, "FTM"))

        sour_lines.extend(block)

    return sour_lines
```

`Archivist/General.py`, `build_gedcom_from_general` — replace the `vols_used` collection (`General.py:1065,1071-1072`) and its use (`General.py:1138`):

Replace `printed_indis, printed_media, vols_used = set(), set(), set()` (`General.py:1065`) with:

```python
    printed_indis, printed_media = set(), set()
    sources_used: Dict[str, str] = {}
```

Replace `vol = extract_volume(sheet)` / `vols_used.add(vol)` (`General.py:1071-1072`) with:

```python
        vol = extract_volume(sheet)
        sheet_records = sheet.get('records', [])
        if not sheet_records:
            sources_used.setdefault(get_dynamic_source_id(vol, None), vol)
```

Inside the `for rec in sheet.get('records', []):` loop (`General.py:1091`, right before `fam_recs.extend(build_family(...))` at `General.py:1127`), add:

```python
            sources_used.setdefault(get_dynamic_source_id(vol, rec), vol)

            fam_recs.extend(build_family(rec, vol, media_uid, target_software))
```

(Note: `for rec in sheet.get('records', [])` at `General.py:1091` must now iterate `sheet_records` instead of re-calling `sheet.get('records', [])`, to reuse the value computed above: `for rec in sheet_records:`.)

Replace the call site (`General.py:1138`):

```python
    if not _ACTIVE_PROFILE.owns_source_records():
        ged.extend(get_volume_sources(sources_used, target_software))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Archivist/tests/test_general_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite + golden regression**

Run: `pytest -q` then `pytest Archivist/tests/test_archivist_dispatcher.py -v`
Expected: PASS unchanged. Parish and Scrip golden fixtures have no shared `collection_mikan` across distinct volumes (or none at all), so the dedup produces the same one-block-per-volume output as before.

- [ ] **Step 6: Commit**

```bash
git add Archivist/General.py Archivist/Scrip.py Archivist/HBCA.py Archivist/tests/test_general_smoke.py
git commit -m "fix(archivist): dedupe SOUR blocks by resolved source ID, not raw volume"
```

---

### Task 7: Capture FamilySearch's `cc` (collection code)

**Files:**
- Modify: `Voyageur/Voyageur.js:1590-1600` (accumulate `cc` alongside `item_id`), `Voyageur/FS.py:456-494` (`build_universal_json`), `Voyageur/FS.py:660-670` (census path)
- Test: `Voyageur/tests/test_fs.py`

**Interfaces:**
- Produces: `FS.py`'s citation dict gains `"collection_id"` (the FS `cc` value) alongside the existing `"apid_db"` field.

- [ ] **Step 1: Write the failing test**

Add to `Voyageur/tests/test_fs.py` (read the file first to match its existing `build_universal_json` test fixture shape exactly):

```python
def test_build_universal_json_captures_collection_id():
    items_raw = [{
        "item_id": "MF36-Z6D",
        "cc": "1401638",
        "citation_text": "Some citation text.",
        "catalog_items": [],
        "rows": [{"role": "Claimant"}],
    }]
    raw_data = {"collection_title": "Manitoba Church Records"}

    result = FS.build_universal_json(raw_data, items_raw, {}, "parish")

    assert result["citation"]["collection_id"] == "1401638"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Voyageur/tests/test_fs.py -k collection_id -v`
Expected: FAIL with `KeyError: 'collection_id'`

- [ ] **Step 3: Implement**

`Voyageur/Voyageur.js` — in `runFamilySearchGather()`'s scraping loop, alongside the existing `accumulatedItems.push({item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows});` (`Voyageur.js:1599`), capture `cc` from the current page URL and include it:

```js
const collectionCode = new URLSearchParams(window.location.search).get('cc') || "";
accumulatedItems.push({item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows, cc: collectionCode});
```

(No automated test for this line — `Voyageur.js` has no JS test harness in this project; every other scraping line in this file is likewise untested by `pytest`. Verify manually against a live FamilySearch page after this change, the same way the earlier `cc` discovery in this design was verified.)

`Voyageur/FS.py`, `build_universal_json` (`FS.py:490-493`):

```python
    first_cc = next((it.get("cc", "") for it in items_raw if it.get("cc")), "")
    return {
        "collection_title": collection_title,
        "record_family": record_family,
        "citation": {**citation, "apid_db": "", "collection_id": first_cc, "catalog_items": list(catalog_items.values())},
        "sheets": sheets,
    }
```

`Voyageur/FS.py`, census path (`FS.py:667-668`, inside the per-page dict) — thread the same `cc` value through if available on the raw item; read the surrounding function signature first (`build_census_json`) to confirm whether `items_raw` is in scope at that point before adding `"collection_id": <value>` next to the existing `"apid_db": ""` line, following the same pattern as the general path above.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Voyageur/tests/test_fs.py -k collection_id -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/FS.py Voyageur/tests/test_fs.py
git commit -m "feat(fs): capture FamilySearch collection code (cc) from record page URL"
```

---

### Task 8: Keystone REFD parsing (`HBCA.py`)

**Files:**
- Modify: `Voyageur/HBCA.py:201-248` (`parse_keystone_search_response`, `query_keystone_for_code`)
- Test: `Voyageur/tests/test_hbca_keystone.py`

**Interfaces:**
- Produces: new `parse_keystone_refd(html_text: str) -> Optional[str]`. `query_keystone_for_code()`'s return dict gains a `"refd"` key.

- [ ] **Step 1: Write the failing test**

Add to `Voyageur/tests/test_hbca_keystone.py` (read the file first for its existing fixture-HTML style and mirror it — condensed real markup confirmed live during this design's investigation, for the `B.239/g/13` result page):

```python
def test_parse_keystone_refd_extracts_numeric_id():
    html = """
    <html><body>
    <a href="https://pam.minisisinc.com/SCRIPTS/MWIMAIN.DLL/421746206/DESCRIPTION_WEB_ACCESS/REFD/9295?JUMP">Northern Department abstracts of servants' accounts</a>
    <a href="https://pam.minisisinc.com/SCRIPTS/MWIMAIN.DLL/421746206/DESCRIPTION_WEB/REFD/9295?JUMP">Click here for information about the group of records...</a>
    </body></html>
    """
    assert HBCA.parse_keystone_refd(html) == "9295"


def test_parse_keystone_refd_none_when_absent():
    assert HBCA.parse_keystone_refd("<html><body>No REFD here.</body></html>") is None


def test_query_keystone_for_code_includes_refd(monkeypatch):
    class FakeResp:
        status_code = 200
        text = ('<a href="https://pam.minisisinc.com/SCRIPTS/MWIMAIN.DLL/1/DESCRIPTION_WEB_ACCESS/REFD/14374?JUMP">'
                'Extracts from registers of baptisms</a>')

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            return FakeResp()

    result = HBCA.query_keystone_for_code("E.4/1a", session=FakeSession())

    assert result["refd"] == "14374"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Voyageur/tests/test_hbca_keystone.py -k refd -v`
Expected: FAIL — `AttributeError: module 'HBCA' has no attribute 'parse_keystone_refd'`, then `KeyError: 'refd'`

- [ ] **Step 3: Implement**

`Voyageur/HBCA.py`, add near `parse_keystone_search_response` (`HBCA.py:201-230`):

```python
_REFD_REGEX = re.compile(r"/REFD/(\d+)\?JUMP", re.IGNORECASE)


def parse_keystone_refd(html_text: str) -> Optional[str]:
    """Extracts the numeric REFD identifier for this item's enclosing fonds/series
    description, from the same result page query_keystone_for_code already fetches -
    e.g. ".../REFD/9295?JUMP" -> "9295". Mirrors LAC's hierarchy-breadcrumb MIKAN
    extraction: a stable, purely numeric per-series identifier, not a per-item one."""
    match = _REFD_REGEX.search(html_text)
    return match.group(1) if match else None
```

Update `query_keystone_for_code` (`HBCA.py:233-248`) to include it:

```python
def query_keystone_for_code(
    location_code: str,
    base_url: str = KEYSTONE_BASE_URL,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Queries Keystone database for a given location code."""
    url = build_keystone_search_url(location_code, base_url)
    client = session or requests.Session()
    headers = {"User-Agent": "Scriptorium/1.0 (Genealogy Keystone Resolver)"}
    try:
        resp = client.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            parsed = parse_keystone_search_response(resp.text, base_url)
            parsed["refd"] = parse_keystone_refd(resp.text)
            return parsed
    except Exception as e:
        print(f"[WARN] Failed to query Keystone for {location_code}: {e}")
    return {"record_urls": [url], "media_urls": [], "refd": None}
```

(`parse_keystone_search_response`'s return type annotation, `HBCA.py:201`, changes from `Dict[str, List[str]]` to `Dict[str, Any]` to match — update the import at the top of the file if `Any` isn't already imported; it already is, per `HBCA.py:11`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Voyageur/tests/test_hbca_keystone.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add Voyageur/HBCA.py Voyageur/tests/test_hbca_keystone.py
git commit -m "feat(hbca): parse Keystone REFD collection identifier"
```

---

### Task 9: New `Paleographer/HBCATools.py` — resolve REFDs into `source_documents`

**Files:**
- Create: `Paleographer/HBCATools.py`
- Modify: `Paleographer/Paleographer.py`
- Test: Create `Paleographer/tests/test_hbcatools.py`

**Interfaces:**
- Consumes: `record['type_specific_fields']['hbca_references']` (list of strings, already populated by `HBCA.pmt`'s AI extraction — this task does not touch extraction), `HBCA.query_keystone_for_code()` (Task 8)
- Produces: `enrich_hbca_json_data(data: Dict[str, Any], cookies: Optional[dict] = None) -> Dict[str, Any]`. Populates each record's `source_documents` list with one entry per reference: `{"reference_code": str, "resolved_source_id": Optional[str]}`.

- [ ] **Step 1: Write the failing test**

Create `Paleographer/tests/test_hbcatools.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import HBCATools


def test_enrich_hbca_json_data_populates_source_documents(monkeypatch):
    def fake_query(code, session=None):
        return {"refd": {"B.239/g/13": "9295", "E.4/1a": "14374"}[code]}

    monkeypatch.setattr(HBCATools.voyageur_hbca, "query_keystone_for_code", fake_query)

    data = {
        "sheets": [{
            "document_metadata": {"file_name": "adams_george.pdf"},
            "records": [{
                "record_id": "1",
                "type_specific_fields": {"hbca_references": ["B.239/g/13", "E.4/1a"]},
            }],
        }]
    }

    result = HBCATools.enrich_hbca_json_data(data)

    record = result["sheets"][0]["records"][0]
    assert record["source_documents"] == [
        {"reference_code": "B.239/g/13", "resolved_source_id": "9295"},
        {"reference_code": "E.4/1a", "resolved_source_id": "14374"},
    ]


def test_enrich_hbca_json_data_skips_records_without_references():
    data = {
        "sheets": [{
            "document_metadata": {"file_name": "no_refs.pdf"},
            "records": [{"record_id": "1", "type_specific_fields": {}}],
        }]
    }

    result = HBCATools.enrich_hbca_json_data(data)

    assert "source_documents" not in result["sheets"][0]["records"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Paleographer/tests/test_hbcatools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'HBCATools'`

- [ ] **Step 3: Implement**

Create `Paleographer/HBCATools.py`, mirroring `ScripTools.py`'s import pattern (`ScripTools.py:24-34`):

```python
"""
HBCATools: HBCA-specific document enrichment for Paleographer.

Resolves each AI-extracted HBCA biographical sheet's hbca_references codes (Archives of
Manitoba archival location codes, e.g. "B.239/g/13") to their Keystone REFD - the numeric
identifier of the fonds/series each reference belongs to - and records them as one
source_documents entry per reference, so Archivist can emit one citation and one Source
per reference instead of sharing a single hardcoded Source across every HBCA record. This
runs after Extract.py's AI pass (HBCA.pmt), since hbca_references isn't known until then -
unlike ScripTools' LAC enrichment, which can run against gather-time PIDs directly.

Scriptorium.py launches Paleographer.py (the dispatcher) as a subprocess with
cwd=Paleographer/, so this module imports as a plain sibling.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from Voyageur import HBCA as voyageur_hbca
except (ImportError, ValueError):
    try:
        from . import HBCA as voyageur_hbca
    except (ImportError, ValueError):
        import HBCA as voyageur_hbca


def enrich_hbca_json_data(data: Dict[str, Any], cookies: Optional[dict] = None) -> Dict[str, Any]:
    """Iterates every record's AI-extracted hbca_references and resolves each to a Keystone
    REFD, populating record['source_documents'] with one entry per reference."""
    for sheet in data.get("sheets", []):
        for record in sheet.get("records", []):
            type_fields = record.get("type_specific_fields") or {}
            references = type_fields.get("hbca_references") or []
            if not references:
                continue

            source_documents = []
            for code in references:
                result = voyageur_hbca.query_keystone_for_code(code)
                source_documents.append({
                    "reference_code": code,
                    "resolved_source_id": result.get("refd"),
                })
            record["source_documents"] = source_documents

    return data


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Paleographer: HBCA Keystone REFD enrichment.")
    parser.add_argument("--json", dest="json_path", required=True,
                        help="Path to the HBCA MASTER_DB JSON file to enrich in place.")
    args = parser.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data = enrich_hbca_json_data(data)

    with open(args.json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[System] HBCA Keystone enrichment complete: {args.json_path}")


if __name__ == "__main__":
    main()
```

`Paleographer/Paleographer.py`:

```python
ENRICHMENT_MODES = ("enrich", "crosscheck", "partition", "resolve-names")
HBCA_MODES = ("enrich-hbca",)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ENRICHMENT_MODES:
        import ScripTools
        ScripTools.main()
    elif len(sys.argv) > 1 and sys.argv[1] in HBCA_MODES:
        sys.argv.pop(1)
        import HBCATools
        HBCATools.main()
    else:
        import Extract
        Extract.main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Paleographer/tests/test_hbcatools.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add Paleographer/HBCATools.py Paleographer/Paleographer.py Paleographer/tests/test_hbcatools.py
git commit -m "feat(hbca): add Keystone REFD enrichment pass for HBCA biographical sheets"
```

---

### Task 10: `_build_citation_block` gains `source_id_override`

**Files:**
- Modify: `Archivist/General.py:526-643` (`_build_citation_block`, `build_general_citation`)
- Test: `Archivist/tests/test_general_smoke.py`

**Interfaces:**
- Consumes: `doc['resolved_source_id']` (Task 9)
- Produces: `_build_citation_block(..., source_id_override: Optional[str] = None)`. `build_general_citation`'s existing `source_documents` loop passes it.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_general_smoke.py`:

```python
def test_build_citation_block_uses_source_id_override():
    rec = {"page": "1", "record_id": "R1", "year": "1900",
           "type_specific_fields": {}, "citation_text": "", "citation_details": ""}
    part = {"std_given": "A", "std_surname": "B", "role_semantic": "primary"}

    General.set_active_profile(General.GeneralProfile())
    block = General._build_citation_block(
        rec, part, "EVEN", "1", "M1", "proven", "RM", source_id_override="9295",
    )

    assert "2 SOUR @S9295@" in block


def test_build_general_citation_passes_source_id_override_per_document():
    rec = {
        "page": "1", "record_id": "R1", "year": "1900",
        "type_specific_fields": {}, "citation_text": "", "citation_details": "",
        "source_documents": [
            {"reference_code": "B.239/g/13", "resolved_source_id": "9295"},
            {"reference_code": "E.4/1a", "resolved_source_id": "14374"},
        ],
    }
    part = {"std_given": "A", "std_surname": "B", "role_semantic": "primary"}

    class FakeProfile(General.GeneralProfile):
        def citation_uses_source_documents(self, rec):
            return True

    General.set_active_profile(FakeProfile())
    try:
        blocks = General.build_general_citation(rec, part, "EVEN", "1", "M1")
    finally:
        General.set_active_profile(General.GeneralProfile())

    assert len(blocks) == 2
    assert "2 SOUR @S9295@" in blocks[0]
    assert "2 SOUR @S14374@" in blocks[1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Archivist/tests/test_general_smoke.py -k source_id_override -v`
Expected: FAIL — `TypeError: _build_citation_block() got an unexpected keyword argument 'source_id_override'`

- [ ] **Step 3: Implement**

`Archivist/General.py`, `_build_citation_block` signature and `sour_id` resolution (`General.py:526-539`):

```python
def _build_citation_block(rec: dict, part: dict, tag_name: str, vol: str, media_uid: str,
                           proof_status: str, target_software: str, document_type: Optional[str] = None,
                           page: Optional[str] = None, citation_text: Optional[str] = None,
                           citation_details: Optional[str] = None,
                           doc_media_uid: Optional[str] = None,
                           source_id_override: Optional[str] = None) -> str:
    page = Utils.clean_val(page if page is not None else rec.get('page')) or 'X'
    rec_id = Utils.clean_val(rec.get('record_id')) or 'Unknown'
    year = Utils.clean_val(rec.get('year')) or 'Unknown'

    titl = _ACTIVE_PROFILE.citation_title(rec, part, tag_name, year, document_type)
    page_line = _ACTIVE_PROFILE.citation_page(rec, part, page)

    if source_id_override:
        sour_id = f"@S{source_id_override}@"
    else:
        template_id = _ACTIVE_PROFILE.citation_template_id(rec, vol)
        sour_id = f"@S{template_id}@" if template_id else get_dynamic_source_id(vol, rec)
```

`build_general_citation`'s per-`doc` loop (`General.py:626-642`):

```python
    blocks = []
    for doc in source_documents:
        asset_id = doc.get('lac_asset_id')
        media_path = doc.get('media_path')
        if asset_id:
            doc_media_uid = generate_media_uid_for_lac_asset(asset_id)
        elif media_path:
            doc_media_uid = generate_media_uid_for_path(media_path)
        else:
            doc_media_uid = media_uid
        blocks.append(_build_citation_block(
            rec, part, tag_name, vol, media_uid, proof_status, target_software,
            document_type=doc.get('document_type'), page=doc.get('page'),
            citation_text=doc.get('citation_text'),
            citation_details=doc.get('citation_details'),
            doc_media_uid=doc_media_uid,
            source_id_override=doc.get('resolved_source_id'),
        ))
    return blocks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Archivist/tests/test_general_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite + golden regression**

Run: `pytest -q` then `pytest Archivist/tests/test_archivist_dispatcher.py -v`
Expected: PASS unchanged (no golden fixture record has `resolved_source_id` in its `source_documents`, so `source_id_override` is always `None` there, falling through to the existing `template_id`/`get_dynamic_source_id` path).

- [ ] **Step 6: Commit**

```bash
git add Archivist/General.py Archivist/tests/test_general_smoke.py
git commit -m "feat(archivist): per-document source_id_override for multi-source citations"
```

---

### Task 11: `HBCAProfile.resolve_source_templates` emits one block per REFD

**Files:**
- Modify: `Archivist/HBCA.py:35-36` (`owns_source_records`), `Archivist/HBCA.py:218-244` (`resolve_source_templates`)
- Test: `Archivist/tests/test_hbca_profile.py`

**Interfaces:**
- Consumes: `record['source_documents'][]['resolved_source_id']` (Task 9), `owns_source_records()` (Task 6)
- Produces: `HBCAProfile.resolve_source_templates(json_data, target_software)` emits one `0 @S{refd}@ SOUR` block per distinct REFD found across `json_data`'s records, instead of the single hardcoded `@S10009@` block. `HBCAProfile.owns_source_records()` returns `True`.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_hbca_profile.py`:

```python
def test_hbca_owns_source_records():
    assert HBCA.HBCAProfile().owns_source_records() is True


def test_resolve_source_templates_emits_one_block_per_distinct_refd():
    json_data = {
        "sheets": [{
            "records": [{
                "source_documents": [
                    {"reference_code": "B.239/g/13", "resolved_source_id": "9295"},
                    {"reference_code": "E.4/1a", "resolved_source_id": "14374"},
                ],
            }],
        }],
    }

    blocks = HBCA.HBCAProfile().resolve_source_templates(json_data, "RM")

    assert "0 @S9295@ SOUR" in blocks
    assert "0 @S14374@ SOUR" in blocks
    assert blocks.count("0 @S9295@ SOUR") == 1


def test_resolve_source_templates_falls_back_when_no_references_resolved():
    json_data = {"sheets": [{"records": [{"source_documents": []}]}]}

    blocks = HBCA.HBCAProfile().resolve_source_templates(json_data, "RM")

    assert f"0 @S{HBCA.HBCA_TEMPLATE_ID}@ SOUR" in blocks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Archivist/tests/test_hbca_profile.py -k "owns_source_records or resolve_source_templates" -v`
Expected: FAIL — `owns_source_records` doesn't exist yet; `resolve_source_templates` today always returns the single hardcoded `@S10009@` block regardless of `json_data` content, so the multi-REFD test fails.

- [ ] **Step 3: Implement**

`Archivist/HBCA.py` — set `owns_source_records` to `True` (`HBCA.py:35-36`, added in Task 6 as `False`):

```python
    def owns_source_records(self) -> bool:
        return True
```

Rewrite `resolve_source_templates` (`HBCA.py:218-244`) to collect distinct REFDs and emit one block per REFD, keeping today's single-block shape as the fallback when no reference resolved to a REFD (e.g. `resolve_keystone`/enrichment hasn't run yet for this JSON):

```python
    def resolve_source_templates(self, json_data: dict, target_software: str) -> List[str]:
        repository = "Hudson's Bay Company Archives, Archives of Manitoba"
        pub_loc = "Winnipeg, Manitoba, Canada"

        refds_used = {}
        for sheet in json_data.get('sheets', []):
            for rec in sheet.get('records', []):
                for doc in rec.get('source_documents') or []:
                    refd = doc.get('resolved_source_id')
                    code = doc.get('reference_code')
                    if refd and refd not in refds_used:
                        refds_used[refd] = code

        if not refds_used:
            refds_used = {str(HBCA_TEMPLATE_ID): None}

        block: List[str] = []
        for refd, code in sorted(refds_used.items()):
            display_name = "Hudson's Bay Company Archives: Biographical Sheets"
            abbr = f"HBCA Biographical Sheets{f' - {code}' if code else ''}"
            bibl = f"{repository}. Biographical Sheets. {pub_loc}."

            block.extend([
                f"0 @S{refd}@ SOUR",
                f"1 ABBR {abbr}",
                f"1 REFN {refd}",
                f"1 TITL {display_name}",
                f"1 _BIBL {bibl}",
            ])
            if target_software == "RM":
                block.extend([
                    "1 _TMPLT",
                    f"2 TID {HBCA_TEMPLATE_ID}",
                    "2 FIELD", "3 NAME PrimaryCreator", "3 VALUE Hudson's Bay Company",
                    "2 FIELD", "3 NAME Department", "3 VALUE Archives of Manitoba",
                    "2 FIELD", "3 NAME SourceDescription", "3 VALUE Biographical Sheets",
                    "2 FIELD", "3 NAME Publisher", "3 VALUE Archives of Manitoba",
                    "2 FIELD", "3 NAME PublishLocation", f"3 VALUE {pub_loc}",
                    "2 FIELD", "3 NAME Repository", f"3 VALUE {repository}",
                ])
                block.extend(General.get_source_templates({HBCA_TEMPLATE_ID}))

        return block
```

(`HBCA_TEMPLATE_ID` stays exactly as-is — it's still correct as the RM citation *template* ID passed to `2 TID`; only its former reuse as the source XREF is gone, replaced by real per-REFD XREFs.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Archivist/tests/test_hbca_profile.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest -q`
Expected: PASS. (No golden-file regression check for HBCA — confirmed during Task planning that `Archivist/tests/golden/` only has `parish_*`/`scrip_*` fixtures, no HBCA golden file exists yet.)

- [ ] **Step 6: Commit**

```bash
git add Archivist/HBCA.py Archivist/tests/test_hbca_profile.py
git commit -m "feat(hbca): emit one Source per resolved Keystone REFD instead of one shared constant"
```

---

## Self-Review Notes

- **Spec coverage:** All four "In scope" items from the design spec are covered — Ancestry (already correct, no task needed, confirmed in Background), FS `cc` capture (Task 7), LAC MIKAN (Tasks 1-6), HBCA Keystone REFD + multi-citation (Tasks 8-11). The three "Open questions for the planning phase" (exact FS/LAC field names, HBCA citation code shape, Ancestry/Census scope) are resolved by this plan's concrete choices — except the Ancestry/Census scope question, which remains deliberately unresolved and out of scope per the Global Constraints, since brainstorming didn't reach a decision on it.
- **Type consistency:** `dynamic_source_id`'s new `rec` parameter is threaded identically across `GeneralProfile`, `ScripProfile`, `HBCAProfile`, and every call site (Task 4), verified against the existing `test_profile_parity.py` structural test. `get_volume_sources`' signature change from `set` to `Dict[str, str]` is consistent between its definition (Task 6) and its one call site in `build_gedcom_from_general` (same task).
- **No placeholders:** every step has real, file-verified code. The one deliberately-unautomated step (Task 7's `Voyageur.js` change) is called out explicitly as such, matching this project's existing lack of JS test coverage, not left as a silent gap.
