# HBCA Biographical Sheets Integration & Pipeline Design

**Date:** 2026-08-08  
**Topic:** Hudson's Bay Company Archives (HBCA / Archives of Manitoba) Biographical Sheets  
**Status:** Approved  

---

## 1. Executive Summary & Goals

The Archives of Manitoba hosts an index of approximately **2,906 Biographical Information Sheets** for employees and officers of the Hudson's Bay Company (HBC) and North West Company (NWC). These sheets compile vitals, service career timelines across trading posts and districts, family/marriage connections (European, Indigenous, and Métis), and archival location codes (e.g., `B.239/g/13`, `A.32/21`, `E.4/1a`).

This design integrates HBCA Biographical Sheets directly into the standard 3-stage Scriptorium architecture (**Voyageur** Gather $\rightarrow$ **Paleographer** Analyze $\rightarrow$ **Archivist** Export), replacing the legacy standalone script `HBCRecords/HBCRecords.py`.

### Core Requirements
1. **New Prompt Template (`Paleographer/prompts/HBCA.pmt`)**: Formal schema definition and LLM prompt body for extracting header vitals, tabular service career history, family relationships, and archival references into `MasterDB_HBCA.json`.
2. **Voyageur Gatherer (`Voyageur/HBCA.py`)**: Crawls `https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html` to discover and download all 2,906 employee PDFs with resumable checkpoints, text prefetch, and optional letter/surname filters.
3. **Keystone Search & Media Gatherer**: Queries Archives of Manitoba's Keystone database for cited location codes to discover and download associated digitized microfilm images/PDFs.
4. **Single Shared Master Source & Simplified Citations**: Adheres to RootsMagic Simplified Citations (`10009` Non-traditional Archives / `10006` Master Template), emitting a single shared Master Source (`0 @S<id>@ SOUR`) with granular per-record citation details (`2 SOUR @S<id>@`).
5. **Evidence Quality & Proof Status Rules**:
   - Facts derived solely from the Biographical Sheet are marked as `2 _PROOF proposed` with derivative source quality (`3 QUAY 1` / `4 _SOUR D` / `4 _INFO S` / `4 _EVID I`).
   - Facts linked to actual primary archival sources (e.g., digitized microfilm or parish registers) are upgraded to `2 _PROOF proven` with primary quality (`3 QUAY 3` / `4 _SOUR O` / `4 _INFO P` / `4 _EVID D`).
6. **Legacy Code Cleanup**: Deletes `HBCRecords/HBCRecords.py` and its directory.

---

## 2. Architecture & Data Contracts

### 2.1 Prompt Template (`Paleographer/prompts/HBCA.pmt`)

```yaml
---
document_type: HBCA
roles:
  "1": {name: "Employee", semantic: primary, context: "The HBC servant, officer, or laborer who is the subject of the biographical sheet."}
  "2": {name: "Spouse", semantic: spouse, context: "Wife or country-marriage partner (European, Indigenous, or Métis)."}
  "3": {name: "Child", semantic: child, context: "Child of the employee, with baptism, birth, or marriage notes."}
  "4": {name: "Father", semantic: father, context: "Father of the employee."}
  "5": {name: "Mother", semantic: mother, context: "Mother of the employee."}
  "0": {name: "Other", context: "Other mentioned associates, relatives, or executors."}
role_validation: closed
defaults:
  record:
    event_type: "Employment"
extra_fields:
  record:
    - {name: parish_of_origin, type: string}
    - {name: entered_service_year, type: string}
    - {name: service_years_range, type: string}
    - {name: highest_position, type: string}
    - {name: service_history, type: list}
    - {name: search_file_reference, type: string}
    - {name: hbca_references, type: list}
    - {name: keystone_urls, type: list}
  participant:
    - {name: relationship_to_employee, type: string}
    - {name: vital_dates_summary, type: string}
    - {name: citations_text, type: string}
metadata_fields:
  Collection: "${HBCA_COLLECTION_NAME}"
  Repository: "${HBCA_REPOSITORY}"
settings_sections:
  - "Antigravity CLI"
  - "HBCA Information"
field_remap:
  HBCA_IMAGE_DIR: IMAGE_DIR
  HBCA_MASTER_DB_NAME: MASTER_DB_NAME
  HBCA_COLLECTION_NAME: COLLECTION_NAME
  HBCA_GEDCOM_NAME: GEDCOM_OUTPUT_NAME
---

# HBCA Biographical Sheet Extraction Instructions
Extract all individuals, dates, places, service career entries, and relationships from the document image or text...
```

### 2.2 Voyageur Gatherer (`Voyageur/HBCA.py`)

- **Crawler**: Scrapes the HTML index page to extract all 2,906 employee PDF links.
- **Filters**: Supports `--letter` (e.g. `A`, `M`, or `ALL`) and `--filter` (glob match on surname).
- **Checkpoints**: Maintains `Working/HBCA/hbca_checkpoint.json` with `{completed_slugs: [...], failed_slugs: [...]}`.
- **Scaffold Builder**: Emits valid `Commissioner.models.Sheet` instances into `MasterDB_HBCA.json` with empty `records: []` and populated `document_metadata` (including prefetched text).
- **Keystone Resolver & Media Downloader**: Queries Keystone (`pam.minisisinc.com/scripts/mwimain.dll?UNIONSEARCH...`) for cited location codes and downloads discovered media to `Media/HBCA_Media/<location_code>/`.

### 2.3 Archivist Simplified Citations & Proof Rules

#### Master Source (`0 @S<id>@ SOUR`)
- Emitted once at the top level of the GEDCOM output:
  - `1 TITL Hudson's Bay Company Archives: Biographical Sheets`
  - `1 AUTH Hudson's Bay Company`
  - `1 PUBL Archives of Manitoba, Winnipeg, MB`
  - `1 _TMPLT` (TID `10009` Non-traditional)
    - `PrimaryCreator`: `Hudson's Bay Company`
    - `Department`: `Hudson's Bay Company Archives (HBCA)`
    - `Date`: `ca. 1700–1920`
    - `SourceDescription`: `Biographical Information Sheets`
    - `Repository`: `Archives of Manitoba`
    - `PublishLocation`: `Winnipeg, Manitoba`

#### Citation Detail (`2 SOUR @S<id>@`)
- Attached under individual facts:
  - `3 PAGE Biographical Sheet: <SURNAME>, <Given Name>`
  - `3 FIELD / NAME SourceDetailPerson: <Full Name>`
  - `3 FIELD / NAME Location: <Parish / District / Post>`
  - `3 FIELD / NAME Repository: Archives of Manitoba`
  - `3 FIELD / NAME URL: <PDF URL>`
  - `3 FIELD / NAME RefNumber: <Location Codes, Search File, Keystone URLs>`
  - `3 DATA / 4 TEXT: <Verbatim / Career Notes>`

#### Proof & Source Quality Rules
| Fact Origin | GEDCOM `_PROOF` | `QUAY` | `_SOUR` | `_INFO` | `_EVID` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bio Sheet Only** (Derivative) | `2 _PROOF proposed` | `3 QUAY 1` | `4 _SOUR D` | `4 _INFO S` | `4 _EVID I` |
| **Primary Archival Source** (Found/Linked) | `2 _PROOF proven` | `3 QUAY 3` | `4 _SOUR O` | `4 _INFO P` | `4 _EVID D` |

#### Media Linking (`1 OBJE`)
- `1 OBJE` blocks point to local downloaded files (`Media/HBCA_Bios/<file>.pdf` and `Media/HBCA_Media/<file>`).

---

## 3. UI & Dispatch Integration

- **`Voyageur/Voyageur.py`**: Add `HBCA` to `SOURCES = ("A", "FS", "LAC", "HBCA")`.
- **`Scriptorium.py`**: Add `("HBCA", "HBCA")` to `VOYAGEUR_SOURCES`.
- **`Voyageur/settings_schema.yaml`**: Add settings block for `HBCA / Manitoba Archives`.

---

## 4. Verification Plan

1. **Unit & Contract Tests**:
   - `tests/test_hbca_pmt.py`: Validate `HBCA.pmt` front matter and Pydantic record validation via `Commissioner.record_registry`.
   - `tests/test_hbca_gather.py`: Test HTML index scraping, link extraction, and checkpoint logic with mock responses.
   - `tests/test_hbca_archivist.py`: Test GEDCOM generation, single Master Source reuse, Simplified Citation detail fields, `_PROOF proposed` default, and `1 OBJE` media records.
2. **End-to-End Test**:
   - Run gather on sample letter (e.g. `A`), verify scaffold generation in `MasterDB_HBCA.json`.
   - Run mock extraction pass and verify GEDCOM export against RootsMagic/FTM parser tests.
