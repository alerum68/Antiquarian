# HBCA Biographical Sheets Integration Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode. Follow gemini.md for rules regarding subagents during execution of this plan.

**Goal:** Implement full pipeline integration for Hudson's Bay Company Archives (HBCA / Archives of Manitoba) Biographical Sheets in Scriptorium, replacing the standalone `HBCRecords.py` with `HBCA.pmt`, `Voyageur/HBCA.py`, Keystone media gatherer, and Archivist Simplified Citations export with proof quality ratings.

**Architecture:** A native 3-stage Scriptorium flow: (1) `Voyageur/HBCA.py` crawls the Manitoba Archives index of 2,906 employee PDFs, prefetches text, discovers/downloads associated digitized microfilm media via Keystone, and scaffolds `MasterDB_HBCA.json`; (2) `Paleographer/prompts/HBCA.pmt` extracts vitals, service history, and family trees; (3) `Archivist/HBCA.py` emits a single shared Master Source (`10009` Non-traditional Simplified Citation) with granular per-record citations, default `_PROOF proposed` with derivative source quality (`QUAY 1`), upgraded `_PROOF proven` (`QUAY 3`) when primary records are linked, and `1 OBJE` media attachments.

**Tech Stack:** Python 3.11+, Pydantic v2, BeautifulSoup4, pdfplumber / pypdf, pytest, RootsMagic Simplified Citation templates (`.rmst`).

---

### Task 1: Prompt Template Definition (`Paleographer/prompts/HBCA.pmt`) & Commissioner Registry Validation

**Files:**
- Create: `Paleographer/prompts/HBCA.pmt`
- Test: `Commissioner/tests/test_hbca_registry.py`

**Step 1: Write the failing test**
Create `Commissioner/tests/test_hbca_registry.py`:
```python
from Commissioner.record_registry import get_registry, validate_record_dict

def test_hbca_pmt_registered():
    registry = get_registry()
    assert "HBCA" in registry
    type_info = registry["HBCA"]
    assert type_info.document_type == "HBCA"
    assert "Employee" in type_info.role_names
    assert "Spouse" in type_info.role_names
    assert "Child" in type_info.role_names
    assert type_info.role_validation == "closed"

def test_hbca_record_validation():
    valid_record = {
        "record_id": 1,
        "event_type": "Employment",
        "event_date": "1821-1854",
        "event_place": "York Factory",
        "type_specific_fields": {
            "parish_of_origin": "Birsay, Orkney",
            "entered_service_year": "1821",
            "service_years_range": "1821-1854",
            "highest_position": "Steersman",
            "service_history": [
                {"outfit_years": "1821-1825", "position": "Laborer", "post": "York Factory", "district": "York", "hbca_ref": "B.239/g/1"}
            ],
            "search_file_reference": "Search File: 'ADAMS, GEORGE'",
            "hbca_references": ["B.239/g/1", "A.32/21"],
            "keystone_urls": ["https://pam.minisisinc.com/scripts/mwimain.dll/..."]
        },
        "participants": [
            {
                "participant_id": 1,
                "name": "George Adams",
                "role": "Employee",
                "type_specific_fields": {
                    "relationship_to_employee": "Self",
                    "vital_dates_summary": "b. ca. 1796, d. 1864",
                    "citations_text": "Search file; B.239/g/1"
                }
            }
        ]
    }
    validated = validate_record_dict("HBCA", valid_record)
    assert validated.event_type == "Employment"
    assert validated.type_specific_fields["parish_of_origin"] == "Birsay, Orkney"
```

**Step 2: Run test to verify it fails**
Run: `pytest Commissioner/tests/test_hbca_registry.py -v`  
Expected: FAIL (HBCA not in registry)

**Step 3: Implement `Paleographer/prompts/HBCA.pmt`**
Create `Paleographer/prompts/HBCA.pmt` with complete YAML front matter and prompt transcription instructions.

**Step 4: Run test to verify it passes**
Run: `pytest Commissioner/tests/test_hbca_registry.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add Paleographer/prompts/HBCA.pmt Commissioner/tests/test_hbca_registry.py
git commit -m "feat(paleographer): add HBCA.pmt prompt template and validation tests"
```

---

### Task 2: Voyageur HBCA Gatherer & Index Crawler (`Voyageur/HBCA.py`)

**Files:**
- Create: `Voyageur/HBCA.py`
- Test: `Voyageur/tests/test_hbca_gather.py`

**Step 1: Write the failing test**
Create `Voyageur/tests/test_hbca_gather.py`:
```python
import pytest
from Voyageur.HBCA import parse_biographical_index_html, BioSheetEntry, build_hbca_scaffold_sheet

SAMPLE_INDEX_HTML = """
<html>
<body>
  <a href="../../_assets/docs/hbca/biographical/a/adams_george.pdf">Adams, George</a>
  <a href="../../_assets/docs/hbca/biographical/b/ballenden_john.pdf">Ballenden, John</a>
</body>
</html>
"""

def test_parse_biographical_index_html():
    entries = parse_biographical_index_html(SAMPLE_INDEX_HTML, base_url="https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html")
    assert len(entries) == 2
    assert entries[0].employee_name == "Adams, George"
    assert entries[0].file_name == "adams_george.pdf"
    assert entries[0].letter == "A"
    assert "adams_george.pdf" in entries[0].pdf_url

def test_build_hbca_scaffold_sheet():
    entry = BioSheetEntry(
        employee_name="Adams, George",
        file_name="adams_george.pdf",
        letter="A",
        pdf_url="https://www.gov.mb.ca/chc/archives/_assets/docs/hbca/biographical/a/adams_george.pdf"
    )
    sheet = build_hbca_scaffold_sheet(entry, raw_text="NAME: ADAMS, George\nDATES: b. ca. 1796")
    assert sheet["document_metadata"]["file_name"] == "adams_george.pdf"
    assert sheet["document_metadata"]["document_type"] == "HBCA"
    assert sheet["document_metadata"]["employee_name"] == "Adams, George"
    assert "NAME: ADAMS" in sheet["document_metadata"]["raw_text"]
    assert len(sheet["records"]) == 0
```

**Step 2: Run test to verify it fails**
Run: `pytest Voyageur/tests/test_hbca_gather.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'Voyageur.HBCA'`

**Step 3: Implement `Voyageur/HBCA.py`**
Implement index parsing, download logic, text extraction prefetch, checkpoint tracking, and scaffold creation.

**Step 4: Run test to verify it passes**
Run: `pytest Voyageur/tests/test_hbca_gather.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add Voyageur/HBCA.py Voyageur/tests/test_hbca_gather.py
git commit -m "feat(voyageur): add HBCA index scraper, scaffold generator, and gatherer"
```

---

### Task 3: Keystone Search Resolver & Media Downloader in `Voyageur/HBCA.py`

**Files:**
- Modify: `Voyageur/HBCA.py`
- Test: `Voyageur/tests/test_hbca_keystone.py`

**Step 1: Write the failing test**
Create `Voyageur/tests/test_hbca_keystone.py`:
```python
from Voyageur.HBCA import extract_hbca_location_codes, parse_keystone_search_response

def test_extract_hbca_location_codes():
    text = "HBC References: B.239/g/13; A.32/21; E.4/1a fo. 45; Search File: ADAMS, GEORGE"
    codes = extract_hbca_location_codes(text)
    assert "B.239/g/13" in codes
    assert "A.32/21" in codes
    assert "E.4/1a" in codes

def test_parse_keystone_search_response():
    html_response = """
    <html>
      <a href="https://pam.minisisinc.com/scripts/mwimain.dll/144/PAM_LISTINGS/1234?RECORD">Post Journal B.239/a/1</a>
      <a href="https://pam.minisisinc.com/assets/media/B_239_a_1.pdf">Digitized Copy (PDF)</a>
    </html>
    """
    media_links = parse_keystone_search_response(html_response)
    assert len(media_links) >= 1
    assert any("B_239_a_1.pdf" in link["url"] for link in media_links)
```

**Step 2: Run test to verify it fails**
Run: `pytest Voyageur/tests/test_hbca_keystone.py -v`  
Expected: FAIL (functions not defined)

**Step 3: Implement Keystone search resolver & media downloader**
Add location code regex extractor, Keystone MINISIS query client, response parser, and media downloader in `Voyageur/HBCA.py`.

**Step 4: Run test to verify it passes**
Run: `pytest Voyageur/tests/test_hbca_keystone.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add Voyageur/HBCA.py Voyageur/tests/test_hbca_keystone.py
git commit -m "feat(voyageur): add Keystone location code resolver and media downloader"
```

---

### Task 4: Scriptorium Settings, GUI & CLI Dispatch Integration

**Files:**
- Modify: `Voyageur/settings_schema.yaml`
- Modify: `Voyageur/Voyageur.py`
- Modify: `Scriptorium.py`
- Test: `tests/test_hbca_dispatch.py`

**Step 1: Write the failing test**
Create `tests/test_hbca_dispatch.py`:
```python
import yaml
from pathlib import Path
from Voyageur.Voyageur import SOURCES

def test_hbca_in_voyageur_sources():
    assert "HBCA" in SOURCES

def test_hbca_in_settings_schema():
    schema_path = Path("Voyageur/settings_schema.yaml")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    section_names = [s["name"] for s in schema.get("sections", [])]
    assert "HBCA / Manitoba Archives" in section_names
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_hbca_dispatch.py -v`  
Expected: FAIL

**Step 3: Update `settings_schema.yaml`, `Voyageur.py`, and `Scriptorium.py`**
- Add `HBCA` section to `settings_schema.yaml` (`HBCA_INDEX_URL`, `HBCA_IMAGE_DIR`, `HBCA_LETTER_FILTER`, `HBCA_RESOLVE_KEYSTONE`, `HBCA_MASTER_DB_NAME`).
- Register `HBCA` in `Voyageur/Voyageur.py` dispatcher.
- Register `("HBCA", "HBCA")` in `Scriptorium.py` `VOYAGEUR_SOURCES`.

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_hbca_dispatch.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add Voyageur/settings_schema.yaml Voyageur/Voyageur.py Scriptorium.py tests/test_hbca_dispatch.py
git commit -m "feat(core): integrate HBCA into Voyageur settings schema, CLI dispatcher, and UI"
```

---

### Task 5: Archivist Simplified Citations Profile & Proof / Source Quality Rules

**Files:**
- Create: `Archivist/HBCA.py`
- Modify: `Archivist/General.py` / `Archivist/Utils.py`
- Test: `Archivist/tests/test_hbca_archivist.py`

**Step 1: Write the failing test**
Create `Archivist/tests/test_hbca_archivist.py`:
```python
from Archivist.HBCA import HBCAProfile
from Archivist.models import Person, Fact, Citation

def test_hbca_single_master_source():
    profile = HBCAProfile()
    master_source = profile.get_master_source()
    assert master_source.title == "Hudson's Bay Company Archives: Biographical Sheets"
    assert master_source.template_id == 10009
    assert master_source.template_fields["PrimaryCreator"] == "Hudson's Bay Company"
    assert master_source.template_fields["Repository"] == "Archives of Manitoba"

def test_hbca_citation_proof_proposed_by_default():
    profile = HBCAProfile()
    # Fact with only bio sheet citation
    proof_status, quay, qual = profile.evaluate_citation_quality(is_primary_linked=False)
    assert proof_status == "proposed"
    assert quay == "1"
    assert qual == {"_SOUR": "D", "_INFO": "S", "_EVID": "I"}

def test_hbca_citation_proof_proven_when_primary_linked():
    profile = HBCAProfile()
    # Fact linked to primary microfilm/register
    proof_status, quay, qual = profile.evaluate_citation_quality(is_primary_linked=True)
    assert proof_status == "proven"
    assert quay == "3"
    assert qual == {"_SOUR": "O", "_INFO": "P", "_EVID": "D"}

def test_hbca_citation_detail_fields():
    profile = HBCAProfile()
    fields = profile.build_citation_detail_fields(
        person_name="George Adams",
        page="Biographical Sheet: ADAMS, George",
        url="https://www.gov.mb.ca/chc/archives/.../adams_george.pdf",
        ref_number="B.239/g/13; Search File: ADAMS, GEORGE",
        location="York Factory"
    )
    assert fields["SourceDetailPerson"] == "George Adams"
    assert fields["Page"] == "Biographical Sheet: ADAMS, George"
    assert fields["RefNumber"] == "B.239/g/13; Search File: ADAMS, GEORGE"
```

**Step 2: Run test to verify it fails**
Run: `pytest Archivist/tests/test_hbca_archivist.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'Archivist.HBCA'`

**Step 3: Implement `Archivist/HBCA.py`**
Implement `HBCAProfile` adhering to Simplified Citations `10009` specification, master source sharing, citation detail generation, `_PROOF proposed` / `_PROOF proven` switching, `QUAY`/`_QUAL` ratings, and `1 OBJE` media linking.

**Step 4: Run test to verify it passes**
Run: `pytest Archivist/tests/test_hbca_archivist.py -v`  
Expected: PASS

**Step 5: Commit**
```bash
git add Archivist/HBCA.py Archivist/tests/test_hbca_archivist.py
git commit -m "feat(archivist): add HBCA Simplified Citations profile with proof quality ratings"
```

---

### Task 6: Legacy Code Cleanup & End-to-End Regression Verification

**Files:**
- Delete: `HBCRecords/HBCRecords.py` (and directory `HBCRecords/`)
- Test: Full repository test suite

**Step 1: Delete `HBCRecords/`**
Remove `HBCRecords/` folder and any leftover standalone scripts.

**Step 2: Run full regression test suite**
Run: `pytest -v`  
Expected: All tests PASS across Commissioner, Voyageur, Paleographer, and Archivist.

**Step 3: Commit**
```bash
git add -A
git commit -m "refactor: remove legacy HBCRecords.py in favor of standard Scriptorium pipeline"
```
