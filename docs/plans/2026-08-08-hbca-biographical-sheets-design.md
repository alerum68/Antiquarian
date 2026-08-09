# HBCA Biographical Sheets Integration & Pipeline Design

**Date:** 2026-08-08  
**Topic:** Hudson's Bay Company Archives (HBCA / Archives of Manitoba) Biographical Sheets  
**Status:** Approved (Updated Design)

---

## 1. Executive Summary & Goals

The Archives of Manitoba hosts an index of approximately **2,906 Biographical Information Sheets** for employees and officers of the Hudson's Bay Company (HBC) and North West Company (NWC). These sheets compile vitals, service career timelines, family connections, and archival location codes.

This design integrates HBCA Biographical Sheets into the standard Scriptorium architecture, but heavily leans on **deterministic Regex extraction** for the bulk of the data, reserving the LLM for unstructured notes.

### Core Requirements
1. **Alphabet Filter**: Voyageur must correctly respect the alphabet filter (e.g., `--letter A`) to allow targeted gathering.
2. **Media Deduplication**: Multiple employees often cite the same archival document (e.g., `B.239/g/43`). Voyageur must track downloaded media to ensure an image is only downloaded once and linked to multiple citations.
3. **Two-Pass Voyageur System**: 
   - *Pass 1*: Download the Biographical Sheet PDF.
   - *Pass 2*: Extract data and sources deterministically via Regex; query Keystone; download original media; and scaffold fully formed Citations and Sources in JSON.
4. **Focused Paleographer (LLM)**: The LLM is only used to parse the highly variable, unstructured narrative notes at the bottom of the sheets (to find family members and relationships).

---

## 2. Architecture & Data Contracts

### 2.1 Media Directory Structure
All media is stored under a central `Media/HBCA/` directory:
- `Media/HBCA/Bio Sheets/<Letter>/` — Contains the downloaded biographical PDFs (e.g., `adams_charles.pdf`), sorted alphabetically.
- `Media/HBCA/Originals/` — Contains the actual archival images/microfilm downloaded from Keystone.

### 2.2 Voyageur Gatherer (`Voyageur/HBCA.py`)
Voyageur executes a two-pass gathering strategy.

#### Pass 1: Bio Sheet Gathering
- Scrapes the HTML index page for the specified letter filter.
- Downloads the employee PDFs into `Media/HBCA/Bio Sheets/<Letter>/`.

#### Pass 2: Regex Extraction & Media Gathering
Using `biographical_sheet_revealed.pdf` as a rigid blueprint, Voyageur parses the raw PDF text deterministically:
1. **Header Vitals**: Extracts Name, Parish, Entered Service, and Dates (b., d., fl., ca.) via Regex.
2. **Service History**: Uses a regex state machine to parse the "Appointments & Service" table, capturing Outfit Year, Position, Post, District, and HBCA Reference.
3. **Keystone Resolution**: For each unique HBCA Reference extracted, Voyageur queries Keystone to find the digitized media URL.
4. **Deduplication Cache**: Voyageur maintains a registry of downloaded media in `Working/HBCA/media_cache.json`. If a reference is already cached, it reuses the local path; otherwise, it downloads it to `Media/HBCA/Originals/`.
5. **Scaffold Builder**: Voyageur populates `MasterDB_HBCA.json` with the extracted header vitals, the service history, and fully formed citation/source objects containing the media links.

### 2.3 Paleographer Prompt (`Paleographer/prompts/HBCA.pmt`)
Since Voyageur handles all structured data, the LLM prompt focuses solely on the unstructured notes section of the PDF.
- **Goal**: Identify family members (Spouse, Child, Parents) and executors.
- **Output**: Populates the `participants` array in the JSON schema with relationship details and vital dates.

### 2.4 Archivist Export (`Archivist/HBCA.py`)
- Emits a single shared Master Source (`10009` Non-traditional Archives).
- Consumes the fully formed citation and media objects scaffolded by Voyageur, directly writing `2 SOUR @S_HBCA@` details and `1 OBJE` links into the GEDCOM without further processing.

---

## 3. Verification Plan
1. Run Voyageur Pass 1 with `--letter A`. Verify PDFs download to `Media/HBCA/Bio Sheets/A/`.
2. Run Voyageur Pass 2. Verify JSON is populated with header vitals and service history arrays. Verify media is downloaded to `Media/HBCA/Originals/` and deduplicated.
3. Run Paleographer pass on the JSON scaffold to verify family members are extracted.
4. Run Archivist export to verify the Master Source, citations, and media links are correctly generated in the GEDCOM.
