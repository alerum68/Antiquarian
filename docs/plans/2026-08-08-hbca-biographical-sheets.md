# HBCA Biographical Sheets Integration Unified Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode. Follow AI Assistant.md for subagent usage for task.

**Goal:** Implement the 2-pass Voyageur gathering system for HBCA sheets with tiered regex/LLM data extraction and media deduplication.

**Status of prior work:** `Voyageur/HBCA.py`, `Archivist/HBCA.py`, and `Paleographer/prompts/HBCA.pmt` already exist and are wired into settings/CLI dispatch (the original 6-task implementation plan is complete; `HBCRecords/` has already been removed). This plan covers targeted follow-up work only.

---

## 1. Architecture & Design

The Archives of Manitoba hosts an index of approximately **2,906 Biographical Information Sheets** for employees and officers of the Hudson's Bay Company (HBC) and North West Company (NWC). These sheets compile vitals, service career timelines, family connections, and archival location codes.

### Findings from live-data verification

Before writing this revision, the live site (`gov.mb.ca/chc/archives/hbca`) and the live Keystone/MINISIS search database were queried directly to validate the original draft's assumptions. Several things it assumed did not hold:

1. **Header fields and service tables are frequently incomplete.** A sample sheet with an irregular career (`adams_george.pdf`) has blank `PARISH:`, `ENTERED SERVICE:`, and `DATES:` fields and zero rows in its Appointments & Service table — its seven archival citations (`C.1/345`, `B.239/d/188`, etc.) live entirely in numbered footnotes attached to narrative prose. A sample sheet with a full career (`adams_charles.pdf`) has a populated table, but each `HBCA Reference` cell holds a base code plus a comma-separated list of page/folio numbers (`B.239/k/3, p. 334, 356`), the same base code often repeats across consecutive rows, and the column is labelled `Post` on career sheets but `Ship` on voyage/passage sheets. A pure "regex parses the table, LLM only reads family notes" split does not hold up against this variance — see the **tiered extraction** design below.
2. **The Keystone reference-code search is not a stateless GET.** `query_keystone_for_code`'s current URL (`.../144/PAM_LISTINGS?DIRECTSEARCH&KEYWORD_CLUSTER=<code>`) returns HTTP 200 but only the generic search page shell — it never actually searches anything. The real search form POSTs to a **session-scoped action URL** (`/scripts/mwimain.dll/<SESSION_ID>/1/0`) that is only obtainable by first GETting the `DIRECTSEARCH` landing page and reading the session ID out of the returned form's `action` attribute; the location-code field is a `LOCATION_CODE` POST parameter (the generic `KEYWORDS` field returns "No records found" for reference-code lookups). Verified live: POSTing `LOCATION_CODE=B.239/k/3` to the session URL correctly resolves to a single record ("Northern Department minutes of council") with a direct, session-independent PDF link at `https://PAM.MINISISINC.COM/DIGITALOBJECTS/Access/HBCA%20Microfilm/1M814/B239-K-3.pdf` — confirming the `code → PDF filename` mapping is `B.239/k/3` → `B239-K-3.pdf` (periods and slashes become dashes, letter section uppercased). Confirmed with a second, independently-checked code (`B.223/d/105A` → `B223-D-105A.pdf`) that this mapping generalizes. See **Task 3** for the corrected implementation this requires.
3. **The record page's own URL is not stable, but a separate permalink is.** The session-scoped record page (e.g. `/scripts/mwimain.dll/221743522/1/0?SEARCH&ERRMSG=[PAM]listNo.htm`) gets a fresh session ID every search — it cannot be stored and revisited later. The page's "Share Link" control reveals a genuinely stable, cookie-independent permalink instead (verified live with a cookie-less request): `https://pam.minisisinc.com/scripts/mwimain.dll/144/LISTINGS_IMAGES/LISTINGS_DET_IMAGES/SISN%20<N>?sessionsearch`. That page also already carries the full citation-relevant metadata in one load — Item Description (title), Date, Fonds/Series Title, Notes, Location Code, and Microfilm No. — so it must be scraped for citation data, not just the PDF link.
4. **A single location code can span multiple digitized reels, each its own PDF.** The Archives' microfilm digitization is reel-based, so one `HBCA Reference` can resolve to several separate PDF files on the record page rather than one. All of them need to be downloaded and joined into a single combined PDF per location code — `parse_keystone_search_response` already collects every matching media link into a list rather than just the first, so this is a downstream download/merge step rather than a detection gap.

This design integrates HBCA Biographical Sheets into the standard Scriptorium architecture using a **tiered extraction strategy**: deterministic regex handles what it reliably can (alphabet filtering, reference-code discovery for Keystone lookups, well-formed tables), and the LLM is used both for unstructured family notes (always) and as a fallback for structured vitals/service history when Voyageur's regex pass finds the sheet incomplete (conditionally).

### Core Requirements
1. **Alphabet Filter**: Voyageur must correctly respect the alphabet filter (e.g., `--letter A`) to allow targeted gathering.
2. **Media Deduplication & Reel Joining**: Multiple employees often cite the same archival document (e.g., `B.239/k/3`). Voyageur must track downloaded media to ensure Keystone is only queried once per document and the image is only downloaded once, linking it to multiple citations. Where a document spans multiple digitized reels, all reel PDFs must be downloaded and merged into one combined PDF per location code.
3. **Two-Pass Voyageur System**:
   - *Pass 1*: Download the Biographical Sheet PDF.
   - *Pass 2*: Extract data and sources via regex where the sheet is well-formed; query Keystone using the corrected session-based search protocol; download and merge original media; and scaffold Citations and Sources in JSON, flagging any sheet whose header/table data is incomplete for LLM follow-up.
4. **Tiered Paleographer (LLM)**: The LLM always extracts unstructured narrative notes (family members and relationships). For sheets Voyageur flags as incomplete, it *additionally* extracts header vitals and service history from prose/footnotes.
5. **Non-destructive merge**: Whichever pass runs second (currently Paleographer, after Voyageur's scaffold) must not silently overwrite fields the other pass already populated.

### Media Directory Structure
All media is stored under a central `Media/HBCA/` directory:
- `Media/HBCA/Bio Sheets/<Letter>/` — Contains the downloaded biographical PDFs, sorted alphabetically.
- `Media/HBCA/Archives/` — Contains the actual archival images/microfilm downloaded from Keystone.

---

## 2. Implementation Tasks

**Tech Stack:** Python 3.11+, Pydantic v2, BeautifulSoup4, pdfplumber, pypdf, pytest, `re`, `requests`.

### Task 1: Voyageur Pass 1 - Fix Alphabet Filter Regex

**Context for Engineer:**
The current `parse_biographical_index_html` function in `Voyageur/HBCA.py` tries to extract the alphabetical letter from the URL using the regex `r"biographical/([a-z0-9])/([^/]+\.pdf)$"`. Because the links on the Archives site are relative (verified live: `<a href="../../_assets/docs/hbca/biographical/a/adams_george.pdf">`), the regex fails to find `biographical/` immediately before the letter segment in some link forms and falls back to parsing the first letter of the filename, which breaks the `--letter` filter. Fix the regex to match the alphabetical directory segment directly, relying on the server's known alphabetical organization rather than requiring the literal string `biographical/` to precede it.

**Files:**
- Modify: `Voyageur/HBCA.py`
- Modify/Create: `Voyageur/tests/test_hbca_gather.py`

**Step 1: Write the failing test**
*Direction: Create a test for `parse_biographical_index_html` supplying a raw HTML string with relative links like `<a href="a/adams.pdf">`. Assert that the resulting `BioSheetEntry.letter` is strictly based on the directory (`a`), not the filename fallback.*

```python
import pytest
from Voyageur.HBCA import parse_biographical_index_html

def test_parse_biographical_index_html_extracts_letter():
    mock_html = '<html><body><a href="a/adams.pdf">Adams</a><a href="b/b-weird_name.pdf">B-Weird</a></body></html>'
    entries = parse_biographical_index_html(mock_html, base_url="https://fake.url/")

    assert len(entries) == 2
    assert entries[0].letter == "a"
    assert entries[1].letter == "b"
```

**Step 2: Run test to verify it fails**
Run: `pytest Voyageur/tests/test_hbca_gather.py::test_parse_biographical_index_html_extracts_letter -v`
Expected: FAIL (because the current regex requires `biographical/` in the string).

**Step 3: Write implementation**
*Direction: Update the regex inside `parse_biographical_index_html` to `r"([a-z0-9])/([^/]+\.pdf)$"`.*

```python
# In Voyageur/HBCA.py
# Change:
# match = re.search(r"biographical/([a-z0-9])/([^/]+\.pdf)$", href, re.IGNORECASE)
# To:
match = re.search(r"([a-z0-9])/([^/]+\.pdf)$", href, re.IGNORECASE)
```

**Step 4: Run test to verify it passes**
Run: `pytest Voyageur/tests/test_hbca_gather.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add Voyageur/tests/test_hbca_gather.py Voyageur/HBCA.py
git commit -m "fix(voyageur): correct regex to parse alphabetical subdirectories for HBCA filtering"
```

---

### Task 2: Voyageur Pass 2 - Tiered Header & Service History Extraction

**Context for Engineer:**
Add a new `parse_bio_sheet_text` function that extracts what regex reliably can, using field names that match the schema already validated in `Commissioner/tests/test_hbca_registry.py` and already consumed by `Archivist/HBCA.py` (`parish_of_origin`, `entered_service_year`, `service_years_range`, `highest_position`, `service_history` list with `outfit_years`/`position`/`post`/`district`/`hbca_ref` keys) — do not invent new field names, as `Archivist/HBCA.py`'s `citation_detail_fields` already reads `tf.get('parish_of_origin')`, `tf.get('birth_date_extracted')`, and `tf.get('death_date_extracted')`.

Because live sheets show header fields (`PARISH:`, `ENTERED SERVICE:`, `DATES:`) are frequently blank, and floruit dates instead often appear only in the PDF's `Filename:` metadata footer (e.g. `Adams, Charles (fl. 1866-1882). JHB/ek May/85`), also regex-extract that fallback and split any captured "DATES" text into `birth_date_extracted` / `death_date_extracted` where `b.`/`d.` prefixes are present.

Because the Appointments & Service table is sometimes entirely empty (all citations instead embedded in footnoted prose) and sometimes has multi-value reference cells (`B.239/k/4, fo. 33d, 42d, 58, 71, 83`), the row regex should capture the base `HBCA Reference` code per row (via the existing `extract_hbca_location_codes`, which already correctly isolates base codes like `B.239/k/3` from trailing page/folio lists) rather than attempting to also capture the folio list.

Compute and store a boolean `needs_llm_structured_review` in `type_specific_fields`: `True` when `parish_of_origin`, `entered_service_year`, and vital dates are all blank AND `service_history` is empty after the regex pass. This flag drives Task 4's conditional Paleographer prompt.

`extract_hbca_location_codes` already runs over the *entire* raw text (not just table rows) and is confirmed live to correctly pull codes out of footnoted prose regardless of table completeness — no change needed there; Keystone/media lookups are not gated on the table-extraction tier succeeding.

**Files:**
- Modify: `Voyageur/HBCA.py`
- Modify/Create: `Voyageur/tests/test_hbca_regex.py`

**Step 1: Write the failing tests**
*Direction: Cover both tiers seen in live data — a sheet with a populated table and blank header fields (mirrors `adams_charles.pdf`), and a sheet with blank header fields and an empty table whose only data is in footnoted prose (mirrors `adams_george.pdf`).*

```python
import pytest
from Voyageur.HBCA import parse_bio_sheet_text

def test_parse_bio_sheet_populated_table():
    sample_text = """
    NAME: ADAMS, Charles PARISH: ENTERED SERVICE: DATES:
    Appointments & Service
    Outfit Year* Position Post District HBCA Reference
    1866-1868 Postmaster The Pas Cumberland B.239/k/3, p. 334, 356
    1868-1871 Clerk in charge Rapid River English River B.239/k/3, p. 377, 407, 433
    1874-1875 Clerk in charge Lake St. Anns Upper Saskatchewan B.239/k/4, fo. 2d
    Filename: Adams, Charles (fl. 1866-1882). JHB/ek May/85
    """
    data = parse_bio_sheet_text(sample_text)

    assert data["parish_of_origin"] == ""
    assert len(data["service_history"]) == 3
    assert data["service_history"][0]["hbca_ref"] == "B.239/k/3"
    assert data["service_history"][0]["post"] == "The Pas"
    assert data["service_history"][2]["hbca_ref"] == "B.239/k/4"
    assert data["needs_llm_structured_review"] is False
    # No structured DATES field, so the Filename footer's floruit range is the fallback
    assert "1866-1882" in data["service_years_range"] or "1866-1882" in (data.get("vital_dates_summary") or "")

def test_parse_bio_sheet_blank_header_and_empty_table_flags_for_llm_review():
    sample_text = """
    NAME: ADAMS, George PARISH: ENTERED SERVICE: DATES:
    Appointments & Service
    Outfit Year* Position Ship District HBCA Reference
    George Adams is listed as one of seven passengers boarding the chartered vessel Hadlow...
    In summer 1816 Adams apparently joined the employ of the Hudson's Bay Company...3
    Filename: Adams, George (fl. 1815-1823) JHB October 1998
    """
    data = parse_bio_sheet_text(sample_text)

    assert data["parish_of_origin"] == ""
    assert data["service_history"] == []
    assert data["needs_llm_structured_review"] is True
```

**Step 2: Run test to verify it fails**
Run: `pytest Voyageur/tests/test_hbca_regex.py -v`
Expected: FAIL (function missing).

**Step 3: Write implementation**
*Direction: Add `parse_bio_sheet_text` to `Voyageur/HBCA.py`, matching the canonical `Commissioner`/`Archivist` field names. Update `build_hbca_scaffold_sheet` to call it and merge the results into the first record's `type_specific_fields` (alongside the existing `hbca_references`/`keystone_urls` it already sets).*

```python
# In Voyageur/HBCA.py
_FILENAME_FOOTER_REGEX = re.compile(
    r"Filename:.*?\((?:fl\.|b\.|d\.)\s*([^)]+)\)", re.IGNORECASE
)

def parse_bio_sheet_text(text: str) -> dict:
    data = {
        "parish_of_origin": "", "entered_service_year": "", "service_years_range": "",
        "vital_dates_summary": "", "birth_date_extracted": "", "death_date_extracted": "",
        "service_history": [],
    }

    parish_match = re.search(r'PARISH:\s*(.*?)(?:\s*ENTERED SERVICE:|\s*DATES:|\n)', text)
    if parish_match:
        data["parish_of_origin"] = parish_match.group(1).strip()

    service_match = re.search(r'ENTERED SERVICE:\s*(.*?)(?:\s*DATES:|\n)', text)
    if service_match:
        data["entered_service_year"] = service_match.group(1).strip()

    dates_match = re.search(r'DATES:\s*(.*?)(?:Appointments & Service|Outfit Year|Filename:|$)', text, re.DOTALL)
    if dates_match:
        data["vital_dates_summary"] = dates_match.group(1).strip()
    b_match = re.search(r'\bb\.\s*([^,;\n]+)', data["vital_dates_summary"])
    if b_match:
        data["birth_date_extracted"] = b_match.group(1).strip()
    d_match = re.search(r'\bd\.\s*([^,;\n]+)', data["vital_dates_summary"])
    if d_match:
        data["death_date_extracted"] = d_match.group(1).strip()

    # Fallback: floruit/vital range from the Filename metadata footer, e.g.
    # "Filename: Adams, Charles (fl. 1866-1882)."
    if not data["vital_dates_summary"]:
        footer_match = _FILENAME_FOOTER_REGEX.search(text)
        if footer_match:
            data["service_years_range"] = data["service_years_range"] or footer_match.group(1).strip()
            data["vital_dates_summary"] = footer_match.group(0).strip()

    row_pattern = r'^(\d{4}(?:-\d{4})?)\s+(.+?)\s+([A-Z][.\w/]+(?:/\d+[a-z]?)?)(?:,.*)?$'
    for oy, middle_text, _ in re.findall(row_pattern, text, re.MULTILINE):
        codes = extract_hbca_location_codes(middle_text + " " + _)
        ref = codes[0] if codes else None
        if not ref:
            continue
        parts = middle_text.split()
        data["service_history"].append({
            "outfit_years": oy.strip(),
            "position": " ".join(parts[:2]) if len(parts) >= 2 else middle_text.strip(),
            "post": " ".join(parts[2:]) if len(parts) > 2 else "",
            "district": "",
            "hbca_ref": ref,
        })

    data["needs_llm_structured_review"] = not any([
        data["parish_of_origin"], data["entered_service_year"],
        data["vital_dates_summary"], data["service_history"],
    ])
    return data


# In build_hbca_scaffold_sheet, merge the parsed vitals into the first record's type_specific_fields:
# parsed = parse_bio_sheet_text(raw_text)
# scaffold["records"][0]["type_specific_fields"].update(parsed)
```

*Note: the row regex above is a starting point, not a guaranteed fit for every table layout — during implementation, validate it against several real downloaded sheets (not just the two fixtures above) and adjust capture groups for `post`/`district` splitting, which pdfplumber's column-flattening will not always separate cleanly. Where the split is ambiguous, prefer leaving `district` empty over guessing wrong — `needs_llm_structured_review` should NOT be set purely because of an imperfect post/district split; only set it when the header fields and table are both genuinely empty.*

**Step 4: Run test to verify it passes**
Run: `pytest Voyageur/tests/test_hbca_regex.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add Voyageur/tests/test_hbca_regex.py Voyageur/HBCA.py
git commit -m "feat(voyageur): tiered regex extraction of vitals and service history with LLM-review flag"
```

---

### Task 3: Voyageur Pass 2 - Correct Keystone Search Protocol, Source Metadata & Reel-Merged Media Cache

**Context for Engineer:**
**The current `query_keystone_for_code`/`build_keystone_search_url` do not work against the live site.** Verified directly against `pam.minisisinc.com`: the `KEYWORD_CLUSTER` GET parameter is not read by the real search form at all — submitting it returns the generic search page shell with no results. The real flow, confirmed live end-to-end for `B.239/k/3`:

1. `GET https://pam.minisisinc.com/scripts/mwimain.dll/144/PAM_LISTINGS?DIRECTSEARCH` — establishes a MINISIS session and returns a page whose search `<form>` has `method="post"` and an `action` attribute of the form `/scripts/mwimain.dll/<SESSION_ID>/1/0` (the session ID is assigned per-request and must be scraped out of this response, not hardcoded or guessed).
2. `POST` to that exact session-scoped action URL with form field `LOCATION_CODE=<code>` (the generic `KEYWORDS` field searches free-text descriptions and returns "No records found" for reference-code lookups — it is the wrong field).
3. The response is the record detail page. It contains everything needed for a citation, laid out under labelled headings — `Item Description` (title), `Date`, `Fonds/Series Title`, `Notes`, `Location Code`, `Microfilm No.` — plus one or more `Click here for PDF File` links, each linking directly to `https://PAM.MINISISINC.COM/DIGITALOBJECTS/Access/HBCA%20Microfilm/<MicrofilmNo>/<CODE-with-dashes-uppercase>.pdf` (e.g. `B.239/k/3` → `B239-K-3.pdf`; confirmed live with a second code too, `B.223/d/105A` → `B223-D-105A.pdf`). These PDF URLs are stable/session-independent and can be downloaded directly with a plain GET.
4. **The record page's own URL is not reusable** — it is scoped to that one search session (e.g. `.../221743522/1/0?SEARCH&ERRMSG=...`) and a fresh search gets a different session ID every time. For a storable citation URL, use the page's "Share Link" value instead: verified live to be a distinct, cookie-independent permalink of the form `https://pam.minisisinc.com/scripts/mwimain.dll/144/LISTINGS_IMAGES/LISTINGS_DET_IMAGES/SISN%20<N>?sessionsearch`, which resolves identically with no prior session (confirmed with a cookie-less request). This is what should be stored as the citation source URL; the session-scoped record page URL should not be persisted anywhere.
5. **A location code can resolve to more than one PDF link** — the Archives' microfilm digitization is reel-based, so a single document is sometimes split across multiple digitized reel-part PDFs, all listed on the same record page. `parse_keystone_search_response` should keep collecting every matching media link (it already does, into a list) rather than assuming the first is the only one; `download_keystone_media` must download all of them per code and merge them into a single combined PDF before the result is treated as "the" media file for that location code.

Rewrite `query_keystone_for_code` to perform steps 1–2 with a `requests.Session` (so cookies persist across the GET and POST), and `parse_keystone_search_response` to extract both the structured metadata fields and every PDF link from the resulting record page (falling back to whatever "No records found" / multi-result-list handling is appropriate — flag ambiguous multi-result pages for manual review rather than guessing which result is correct).

Then add the dedup cache on top of the corrected implementation: multiple employees cite the same document (e.g. `B.239/k/3`), so a shared `keystone_cache.json` should store the resolved `{"record_urls": [<share link permalink>], "media_urls": [...], "metadata": {...}}` per location code and skip the session/search round-trip, the media re-download, and the re-merge when a code is already cached.

Finally, thread the per-code result into the JSON scaffold: `build_hbca_scaffold_sheet` should store a `keystone_records` dict keyed by location code (each value being that code's `metadata`/`record_urls`/merged media path) into `type_specific_fields`, alongside the existing `hbca_references`/`keystone_urls`. `Archivist/HBCA.py::citation_detail_fields` currently builds `Page`/`RefNumber`/`URL` from other fields and has no knowledge of this Keystone-scraped metadata — wiring it in there is a natural next task, but is scoped out of this one; note it as follow-up work rather than silently leaving the scraped metadata unused once it exists.

**Files:**
- Modify: `Voyageur/HBCA.py`
- Modify/Create: `Voyageur/tests/test_hbca_keystone.py`
- Modify: `requirements.txt` (or equivalent) — add `pypdf` for merging reel PDFs

**Step 1: Write the failing tests**
*Direction: Mock `requests.Session` to return (a) the DIRECTSEARCH landing page containing a form action with a session ID, then (b) a record detail page carrying the metadata block, the Share Link permalink, and two reel PDF links. Assert the session ID is round-tripped correctly, the metadata and permalink are extracted, and both PDF links are captured. Separately, assert two downloaded reel PDFs get merged into one file, and that a second `query_keystone_for_code` call for the same code hits the cache instead of the network.*

```python
import pytest
from Voyageur.HBCA import query_keystone_for_code, parse_keystone_search_response, download_and_merge_keystone_media

LANDING_PAGE_HTML = """
<html><body>
<form name="frmSearchListings" method="post" action="/scripts/mwimain.dll/521745500/1/0?SEARCH">
  <input type="text" name="LOCATION_CODE">
</form>
</body></html>
"""

RECORD_PAGE_HTML = """
<html><body>
<h1>Northern Department minutes of council</h1>
<div>Item Description</div><div>Northern Department minutes of council</div>
<div>Date</div><div>1851-1870</div>
<div>Fonds/Series Title</div><div>Northern Department minutes of council</div>
<div>Notes</div><div>The microfilm of this record has been digitized.</div>
<div>Location Code</div><div>H2-24-1 ( B.239/k/3 )</div>
<div>Microfilm No.</div><div>1M814</div>
<textarea id="share_link_url">https://pam.minisisinc.com/scripts/mwimain.dll/144/LISTINGS_IMAGES/LISTINGS_DET_IMAGES/SISN%205154?sessionsearch</textarea>
<a href="https://PAM.MINISISINC.COM/DIGITALOBJECTS/Access/HBCA%20Microfilm/1M814/B239-K-3-Reel1.pdf">Click here for PDF File</a>
<a href="https://PAM.MINISISINC.COM/DIGITALOBJECTS/Access/HBCA%20Microfilm/1M814/B239-K-3-Reel2.pdf">Click here for PDF File</a>
</body></html>
"""

def test_query_keystone_for_code_extracts_metadata_permalink_and_all_reel_pdfs(requests_mock):
    requests_mock.get(
        "https://pam.minisisinc.com/scripts/mwimain.dll/144/PAM_LISTINGS?DIRECTSEARCH",
        text=LANDING_PAGE_HTML,
    )
    requests_mock.post(
        "https://pam.minisisinc.com/scripts/mwimain.dll/521745500/1/0",
        text=RECORD_PAGE_HTML,
    )
    result = query_keystone_for_code("B.239/k/3")
    assert len(result["media_urls"]) == 2
    assert "SISN%205154" in result["record_urls"][0]
    assert result["metadata"]["item_description"] == "Northern Department minutes of council"
    assert result["metadata"]["microfilm_no"] == "1M814"

def test_download_and_merge_keystone_media_combines_reels(tmp_path, requests_mock):
    requests_mock.get("https://example.com/reel1.pdf", content=b"%PDF-1.4 reel1")
    requests_mock.get("https://example.com/reel2.pdf", content=b"%PDF-1.4 reel2")
    merged_path = download_and_merge_keystone_media(
        ["https://example.com/reel1.pdf", "https://example.com/reel2.pdf"],
        target_dir=tmp_path,
        output_name="B239-K-3.pdf",
    )
    assert merged_path.exists()

def test_keystone_query_is_cached(tmp_path, requests_mock):
    cache_file = tmp_path / "keystone_cache.json"
    requests_mock.get(
        "https://pam.minisisinc.com/scripts/mwimain.dll/144/PAM_LISTINGS?DIRECTSEARCH",
        text=LANDING_PAGE_HTML,
    )
    requests_mock.post(
        "https://pam.minisisinc.com/scripts/mwimain.dll/521745500/1/0",
        text=RECORD_PAGE_HTML,
    )
    res1 = query_keystone_for_code("B.239/k/3", cache_file=str(cache_file))
    res2 = query_keystone_for_code("B.239/k/3", cache_file=str(cache_file))
    assert requests_mock.call_count == 2  # one GET + one POST, only on the first call
    assert res1 == res2
```

**Step 2: Run test to verify it fails**
Run: `pytest Voyageur/tests/test_hbca_keystone.py -v`
Expected: FAIL

**Step 3: Write implementation**
*Direction: Rewrite `query_keystone_for_code` to GET the DIRECTSEARCH URL, parse the form action's session-scoped path via BeautifulSoup, POST `LOCATION_CODE` to it, and hand the result to an updated `parse_keystone_search_response` that pulls out the labelled metadata fields, the `#share_link_url` permalink, and every PDF link. Add `download_and_merge_keystone_media`, downloading each reel URL and combining them with `pypdf.PdfWriter`. Add the `cache_file` load/check/save wrapper around the whole lookup.*

```python
# In Voyageur/HBCA.py
from pypdf import PdfWriter

def parse_keystone_search_response(html_text: str, base_url: str = KEYSTONE_BASE_URL) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    media_urls: List[str] = []
    seen_media: Set[str] = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if href.lower().endswith(".pdf"):
            full_url = urljoin(base_url, href)
            if full_url not in seen_media:
                seen_media.add(full_url)
                media_urls.append(full_url)

    record_urls: List[str] = []
    share_el = soup.find(id="share_link_url")
    if share_el:
        permalink_match = re.search(r"https?://\S+SISN%20\d+\S*", share_el.get_text())
        if permalink_match:
            record_urls.append(permalink_match.group(0))

    metadata = _extract_keystone_metadata_fields(soup)
    return {"record_urls": record_urls, "media_urls": media_urls, "metadata": metadata}


def _extract_keystone_metadata_fields(soup: BeautifulSoup) -> Dict[str, str]:
    labels = {
        "Item Description": "item_description", "Date": "date",
        "Fonds/Series Title": "fonds_series_title", "Notes": "notes",
        "Location Code": "location_code", "Microfilm No.": "microfilm_no",
    }
    metadata: Dict[str, str] = {}
    for label_text, key in labels.items():
        label_el = soup.find(string=lambda s: s and s.strip() == label_text)
        if label_el:
            value_el = label_el.find_next(string=True)
            if value_el:
                metadata[key] = value_el.strip()
    return metadata


def download_and_merge_keystone_media(
    media_urls: List[str], target_dir: Path, output_name: str,
    session: Optional[requests.Session] = None,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    headers = {"User-Agent": "Scriptorium/1.0 (Genealogy Keystone Media Downloader)"}
    reel_paths: List[Path] = []
    for i, url in enumerate(media_urls):
        reel_path = target_dir / f"_reel_{i}_{output_name}"
        resp = client.get(url, headers=headers, timeout=30)
        reel_path.write_bytes(resp.content)
        reel_paths.append(reel_path)

    output_path = target_dir / output_name
    if len(reel_paths) == 1:
        reel_paths[0].rename(output_path)
        return output_path

    writer = PdfWriter()
    for reel_path in reel_paths:
        writer.append(str(reel_path))
    with open(output_path, "wb") as f:
        writer.write(f)
    for reel_path in reel_paths:
        reel_path.unlink()
    return output_path


def query_keystone_for_code(
    location_code: str,
    base_url: str = KEYSTONE_BASE_URL,
    session: Optional[requests.Session] = None,
    cache_file: Optional[str] = None,
) -> Dict[str, Any]:
    if cache_file:
        cache = _load_keystone_cache(cache_file)
        if location_code in cache:
            return cache[location_code]

    client = session or requests.Session()
    headers = {"User-Agent": "Scriptorium/1.0 (Genealogy Keystone Resolver)"}
    landing_url = f"{base_url}/144/PAM_LISTINGS?DIRECTSEARCH"
    result = {"record_urls": [], "media_urls": [], "metadata": {}}
    try:
        landing_resp = client.get(landing_url, headers=headers, timeout=20)
        soup = BeautifulSoup(landing_resp.text, "html.parser")
        form = soup.find("form", attrs={"name": "frmSearchListings"}) or soup.find(
            "form", attrs={"method": lambda v: v and v.lower() == "post"}
        )
        if form and form.get("action"):
            search_url = urljoin(landing_url, form["action"])
            record_resp = client.post(
                search_url, data={"LOCATION_CODE": location_code}, headers=headers, timeout=20
            )
            if record_resp.status_code == 200:
                result = parse_keystone_search_response(record_resp.text, base_url)
    except Exception as e:
        print(f"[WARN] Failed to query Keystone for {location_code}: {e}")

    if cache_file:
        cache = _load_keystone_cache(cache_file)
        cache[location_code] = result
        _save_keystone_cache(cache_file, cache)
    return result
```

*Note: `_extract_keystone_metadata_fields`'s label-matching approach is a starting point — verify field-label text and DOM structure against a live fetch during implementation, since MINISIS templates can vary field ordering/wording slightly between record types (textual records vs. photographs vs. maps use different templates per the "Choose a format" filter on the search form).*

**Step 4: Run test to verify it passes**
Run: `pytest Voyageur/tests/test_hbca_keystone.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add Voyageur/tests/test_hbca_keystone.py Voyageur/HBCA.py requirements.txt
git commit -m "fix(voyageur): real Keystone search protocol, source metadata capture, and reel-merged media cache"
```

---

### Task 4: Paleographer Prompt - Conditional Structured Fallback

**Context for Engineer:**
Because Task 2 established that a full "regex does all structured data, LLM only does family notes" split does not survive contact with real sheets, **do not** strip `service_history`/`highest_position`/etc. out of `HBCA.pmt`'s `extra_fields` — Voyageur still populates them via regex for the sheets where that works, and Commissioner's registry validation must keep accepting them (removing them would make Commissioner reject Voyageur's own scaffolded data).

Instead, make the LLM's job conditional using the existing per-file dynamic-prompt mechanism (`Paleographer/engine.py`'s `get_dynamic_prompt`, which already injects a per-file `Metadata Context` block — filename, page, etc. — into the prompt sent for each sheet). Have Voyageur's scaffold carry `needs_llm_structured_review` from Task 2 through into the file metadata passed to `get_dynamic_prompt`, and update the `HBCA.pmt` prompt body so the LLM:
- **Always** extracts family/relationship notes into `participants`.
- **Only when** `Metadata Context` indicates `needs_llm_structured_review: true`, *also* reads the narrative prose and footnotes to fill `parish_of_origin`, `entered_service_year`, vital dates, and `service_history` — the same fields Voyageur already regex-extracts for the well-formed sheets, so the schema doesn't change, only which sheets the LLM is asked to fill them in for.

**Files:**
- Modify: `Paleographer/prompts/HBCA.pmt`
- Modify: `Paleographer/Extract.py` (or wherever the per-file metadata dict passed to `get_dynamic_prompt` is assembled, to thread `needs_llm_structured_review` through)
- Modify: `Commissioner/tests/test_hbca_registry.py` (only if field expectations changed — they should not need to, since fields are being kept, not removed)

**Step 1: Write the failing test**
*Direction: Assert the registry still validates records with `service_history`/`highest_position` present (i.e. no removal happened) and add a check that `needs_llm_structured_review` is an accepted `type_specific_fields` key.*

```python
# In Commissioner/tests/test_hbca_registry.py
# Extend test_hbca_record_extra_fields' input dict with "needs_llm_structured_review": False
# and assert extra.needs_llm_structured_review is False.
```

**Step 2: Run test to verify it fails**
Run: `pytest Commissioner/tests/test_hbca_registry.py -v`
Expected: FAIL (field not yet declared in `HBCA.pmt`'s `extra_fields`)

**Step 3: Write implementation**
*Direction: Add `needs_llm_structured_review` (type boolean) to `HBCA.pmt`'s record-level `extra_fields`. Rewrite the prompt body's EXTRACTION RULES section to state the conditional instruction above, keyed off `Metadata Context`. Thread the flag from Voyageur's scaffold into whatever builds the per-file metadata dict for `get_dynamic_prompt`.*

```yaml
# In Paleographer/prompts/HBCA.pmt extra_fields.record, add:
    - {name: needs_llm_structured_review, type: boolean}
```

**Step 4: Run test to verify it passes**
Run: `pytest Commissioner/tests/test_hbca_registry.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add Paleographer/prompts/HBCA.pmt Paleographer/Extract.py Commissioner/tests/test_hbca_registry.py
git commit -m "feat(paleographer): conditional structured-field fallback for sheets regex couldn't parse"
```

---

### Task 5: Preserve Voyageur's Extracted Fields When Paleographer Replaces the Placeholder Sheet

**Context for Engineer:**
`Paleographer/Extract.py::merge_sheets` currently does a **wholesale replacement** of a Voyageur-written placeholder sheet with Paleographer's output (`master_sheets[existing_idx] = new_sheet`), not a field-level merge. This is safe for other document types (their placeholders carry no pre-filled data), but for HBCA, Voyageur's Pass 2 populates `type_specific_fields` (parish, service history, reference codes, Keystone URLs) into the placeholder *before* Paleographer runs on it. If Paleographer's response doesn't happen to echo every one of those fields back — which Task 4 explicitly does not require it to, for sheets where Voyageur's extraction already succeeded — a wholesale replacement will silently erase Voyageur's work.

The codebase already has the right merge semantics for this elsewhere: `_merge_record_into` (used by `merge_same_claim_records`) merges `type_specific_fields` key-by-key, keeping the existing value whenever the incoming value is falsy. Apply the same preserve-if-incoming-empty semantics inside `merge_sheets` when it replaces a placeholder, instead of a flat dict replacement. This is a general fix (harmless no-op for document types with nothing pre-filled), not an HBCA-specific branch.

**Files:**
- Modify: `Paleographer/Extract.py`
- Modify/Create: `Paleographer/tests/test_master_db_merge.py`

**Step 1: Write the failing test**
*Direction: Build a placeholder sheet with Voyageur-populated `type_specific_fields` (as HBCA Pass 2 would produce) and a "real" Paleographer sheet for the same filename whose `type_specific_fields` only carries participant-derived data. Assert that after `merge_sheets`, the resulting sheet has both Voyageur's original fields intact AND Paleographer's participants.*

```python
def test_merge_sheets_preserves_voyageur_fields_on_placeholder_replacement(minimal_paleographer_env):
    module = minimal_paleographer_env
    placeholder = {
        "page_id": "adams_charles.pdf",
        "document_metadata": {"file_name": "adams_charles.pdf"},
        "records": [{
            "event_type": "Employment",
            "participants": [],
            "type_specific_fields": {
                "parish_of_origin": "",
                "service_history": [{"outfit_years": "1866-1868", "hbca_ref": "B.239/k/3"}],
                "hbca_references": ["B.239/k/3"],
            },
        }],
    }
    real_sheet = {
        "page_id": "adams_charles.pdf",
        "document_metadata": {"file_name": "adams_charles.pdf"},
        "records": [{
            "event_type": "Employment",
            "participants": [{"role_name": "Employee", "std_given": "Charles", "std_surname": "Adams"}],
            "type_specific_fields": {},
        }],
    }
    master_data = {"sheets": [placeholder]}
    module.merge_sheets(master_data, [real_sheet])

    merged = master_data["sheets"][0]["records"][0]
    assert merged["participants"][0]["std_given"] == "Charles"
    assert merged["type_specific_fields"]["service_history"][0]["hbca_ref"] == "B.239/k/3"
    assert merged["type_specific_fields"]["hbca_references"] == ["B.239/k/3"]
```

**Step 2: Run test to verify it fails**
Run: `pytest Paleographer/tests/test_master_db_merge.py -v`
Expected: FAIL (wholesale replacement drops `service_history`/`hbca_references`)

**Step 3: Write implementation**
*Direction: In `merge_sheets`, when replacing a placeholder, merge each record's `type_specific_fields` (and `participants`, reusing `_merge_record_into`'s participant-merge logic) instead of assigning the new sheet outright.*

```python
# In Paleographer/Extract.py

def merge_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None:
    master_sheets = master_data.get("sheets")
    if not isinstance(master_sheets, list):
        master_data["sheets"] = new_sheets
        return

    by_file_name = {
        sheet.get("document_metadata", {}).get("file_name"): idx
        for idx, sheet in enumerate(master_sheets)
    }

    for new_sheet in new_sheets:
        file_name = new_sheet.get("document_metadata", {}).get("file_name")
        existing_idx = by_file_name.get(file_name) if file_name is not None else None
        if existing_idx is not None and _sheet_is_placeholder(master_sheets[existing_idx]):
            placeholder_sheet = master_sheets[existing_idx]
            for old_rec, new_rec in zip(placeholder_sheet.get("records", []), new_sheet.get("records", [])):
                _merge_record_into(old_rec, new_rec)
                new_rec.update(old_rec)
            master_sheets[existing_idx] = new_sheet
            continue
        master_sheets.append(new_sheet)
```

*Note: `_merge_record_into` also appends a `source_documents` entry each call — verify during implementation that this side effect is acceptable for the placeholder-replacement path (it may need a narrower helper that only merges `type_specific_fields`/`participants` without the `source_documents` bookkeeping, which was designed for the different same-claim-merge scenario).*

**Step 4: Run test to verify it passes**
Run: `pytest Paleographer/tests/test_master_db_merge.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add Paleographer/Extract.py Paleographer/tests/test_master_db_merge.py
git commit -m "fix(paleographer): preserve Voyageur-extracted fields when replacing placeholder sheets"
```

---

### Task 6: Archivist - Consume Keystone Source Metadata in Citations

**Context for Engineer:**
Task 3 has Voyageur scrape and cache real archival metadata per location code — `item_description` (title), `date`, `fonds_series_title`, `notes`, `microfilm_no`, and the stable `SISN` permalink — into a `keystone_records` dict in `type_specific_fields`, keyed by location code. `Archivist/HBCA.py::citation_detail_fields` currently has no knowledge of any of this: `RefNumber` is built only from the bare `hbca_references` code list (`f"HBCA: {'; '.join(hbca_refs)}"`), and `URL` only ever points at the biographical sheet PDF (`tf.get('pdf_url')`), never at the underlying archival record itself. Without this task, the metadata Task 3 goes to the trouble of scraping never reaches the GEDCOM output.

Enrich `citation_detail_fields` (and `citation_text_block`, which builds the narrative citation text) to fold in `keystone_records` when present:
- `RefNumber` should include the microfilm number alongside the location code(s), e.g. `HBCA: B.239/k/3 (Microfilm 1M814)`.
- The citation's narrative text should incorporate the Keystone item description/date/fonds-series title where available, e.g. `Northern Department minutes of council, 1851-1870 (Archives of Manitoba, HBCA B.239/k/3, Microfilm 1M814)`, so the citation reads as a real archival reference rather than just a bare code.
- The stable `SISN` permalink from `record_urls` should be surfaced as its own field (not overwrite the existing biographical-sheet `URL` field, which serves a different purpose) — add an `ArchivalRecordURL` field when a permalink is available.
- All of this must degrade gracefully when `keystone_records` is absent or a given code has no cached entry (e.g. the Keystone lookup failed or hasn't run yet) — citations must keep working exactly as they do today in that case.

**Files:**
- Modify: `Archivist/HBCA.py`
- Modify/Create: `Archivist/tests/test_hbca_profile.py`

**Step 1: Write the failing test**
*Direction: Build a record whose `type_specific_fields` carries both `hbca_references` and a matching `keystone_records` entry, and assert the enriched `RefNumber`/`ArchivalRecordURL` fields appear, then assert a record with `hbca_references` but no `keystone_records` entry still produces the old, simpler `RefNumber` without erroring.*

```python
from Archivist.HBCA import HBCAProfile

def test_citation_detail_fields_include_keystone_metadata_when_present():
    profile = HBCAProfile()
    rec = {
        "type_specific_fields": {
            "employee_name": "Charles Adams",
            "hbca_references": ["B.239/k/3"],
            "keystone_records": {
                "B.239/k/3": {
                    "metadata": {
                        "item_description": "Northern Department minutes of council",
                        "date": "1851-1870",
                        "microfilm_no": "1M814",
                    },
                    "record_urls": [
                        "https://pam.minisisinc.com/scripts/mwimain.dll/144/LISTINGS_IMAGES/LISTINGS_DET_IMAGES/SISN%205154?sessionsearch"
                    ],
                },
            },
        },
    }
    part = {"std_given": "Charles", "std_surname": "Adams"}
    lines = profile.citation_detail_fields(rec, part, page="adams_charles.pdf", vol="", target_software="RM")
    joined = "\n".join(lines)
    assert "1M814" in joined
    assert "SISN%205154" in joined

def test_citation_detail_fields_degrade_gracefully_without_keystone_records():
    profile = HBCAProfile()
    rec = {"type_specific_fields": {"employee_name": "Charles Adams", "hbca_references": ["B.239/k/3"]}}
    part = {"std_given": "Charles", "std_surname": "Adams"}
    lines = profile.citation_detail_fields(rec, part, page="adams_charles.pdf", vol="", target_software="RM")
    assert any("B.239/k/3" in line for line in lines)
```

**Step 2: Run test to verify it fails**
Run: `pytest Archivist/tests/test_hbca_profile.py -v`
Expected: FAIL (no `ArchivalRecordURL` field, `RefNumber` doesn't include the microfilm number)

**Step 3: Write implementation**
*Direction: In `citation_detail_fields`, after computing `ref_val` from `hbca_refs`, look up each code in `tf.get('keystone_records', {})` and, when present, append the microfilm number to `ref_val` and add an `ArchivalRecordURL` entry from the first available permalink.*

```python
# In Archivist/HBCA.py, inside citation_detail_fields, after ref_val is computed:
keystone_records = tf.get('keystone_records') or {}
microfilm_nos = []
archival_urls = []
for code in (hbca_refs if isinstance(hbca_refs, list) else [hbca_refs]):
    entry = keystone_records.get(code)
    if not entry:
        continue
    meta = entry.get('metadata') or {}
    if meta.get('microfilm_no'):
        microfilm_nos.append(meta['microfilm_no'])
    archival_urls.extend(entry.get('record_urls') or [])

if microfilm_nos:
    ref_val = f"{ref_val} (Microfilm {', '.join(dict.fromkeys(microfilm_nos))})"

detail_fields = [
    ("Page", page_val),
    ("SourceDetailPerson", person_name),
    ("Location", location_val),
    ("Repository", repo_val),
    ("URL", url_val),
    ("Accessed", accessed_val),
    ("RefNumber", ref_val),
]
if archival_urls:
    detail_fields.append(("ArchivalRecordURL", archival_urls[0]))
```

**Step 4: Run test to verify it passes**
Run: `pytest Archivist/tests/test_hbca_profile.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add Archivist/HBCA.py Archivist/tests/test_hbca_profile.py
git commit -m "feat(archivist): surface Keystone-scraped microfilm number and archival record permalink in citations"
```

---

## 3. Verification Plan

1. Run Voyageur Pass 1 with `--letter A`. Verify PDFs download to `Media/HBCA/Bio Sheets/A/`.
2. Run Voyageur Pass 2 against a small real batch spanning both tiers seen live (a sheet with a populated table and blank header fields, and a sheet with an empty table and footnoted prose). Verify `needs_llm_structured_review` is set correctly in each case, and that `hbca_references`/`keystone_urls` are populated for both regardless of tier.
3. Verify Keystone resolution end-to-end for at least one real code (e.g. `B.239/k/3`): confirm the session GET+POST flow resolves to the correct record, that the scraped metadata (title, date, fonds/series, notes, location code, microfilm number) matches the live page, and that the stored `record_urls` entry is the stable `SISN`-based Share Link permalink — never the session-scoped record page URL.
4. Verify media download/merge for at least one location code known to span multiple reels: confirm all reel PDFs download and are combined into a single output PDF, that a second lookup for the same code hits `keystone_cache.json` instead of repeating the network round-trip and re-merge, and that a single-reel code still produces a correctly-named PDF without unnecessary merging.
5. Run Paleographer on the same batch. Verify family/participant notes are always populated, and that structured header/service-history fields are only attempted by the LLM on sheets flagged `needs_llm_structured_review: true`.
6. Verify `merge_sheets` preserves Voyageur's `type_specific_fields` after Paleographer's output replaces the placeholder sheet, on both tiers.
7. Run Archivist export end-to-end. Verify the shared Master Source, per-record citations (including multi-folio references, the `RefNumber` microfilm-number enrichment, and the `ArchivalRecordURL` permalink field Task 6 adds), media `1 OBJE` links, and `_PROOF`/`QUAY` ratings render correctly in the GEDCOM output — and that a record with no cached `keystone_records` entry still exports a valid citation.
8. Run the full repository regression suite (`pytest -v`) to confirm no other document type's Paleographer merge behavior (Task 5) or Archivist citation behavior (Task 6) regressed.
