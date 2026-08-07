# Scriptorium Program Documentation Design Specification

**Date:** 2026-08-06  
**Status:** Approved  
**Scope:** Dual-Stream Documentation (GitHub User Wiki + In-Repo Developer Documentation)

---

## 1. Overview & Goals

Scriptorium is a desktop genealogy toolkit that automates historical record retrieval, AI-assisted transcription, schema normalization, and GEDCOM tree generation.

This project delivers comprehensive, human-written documentation across two distinct destinations:
1. **User Documentation (GitHub Wiki)**: Stored in the `Scriptorium-Docs` repository (`https://github.com/alerum68/Scriptorium.wiki.git`), focused on practical setup, step-by-step workflows, and operational guides for genealogists and researchers.
2. **Developer Documentation (`docs/developer/`)**: Stored in the core `Scriptorium` repository, detailing the system architecture, domain models, schema contracts, `.pmt` prompt specifications, and contributor workflows.

---

## 2. Voice and Style Standards

All documentation must read naturally, clearly, and pragmatically. It must avoid common AI writing tells:

- **Banned Phrasing & Structures**:
  - No "Whether you're..." constructions.
  - No "Not only... but also..." phrasing.
  - No repetitive three-item lists or forced triads.
  - No artificial closing summaries or inspirational sign-offs at the end of sections.
  - No long, exhaustive catalogs of hypothetical examples.
  - No symmetrical, rigidly templated paragraphs.
  - Do not explain every internal mechanism before explaining how to perform the core action.
- **Tone**: Direct, practical, concise, and technically precise. Explain what the tool does, how to use it, what parameters mean, and how to recover when something breaks.
- **Attribution**: No AI attribution, "Co-Authored-By", or Claude/Gemini tags anywhere in prose, comments, or commit messages.

---

## 3. User Documentation Specification (GitHub Wiki — `Scriptorium-Docs/`)

The wiki files reside in `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium-Docs\` and synchronize directly with the GitHub Wiki.

### 3.1 Page Hierarchy & Contents

1. **`Home.md`**:
   - Introduction to Scriptorium's role in processing large archival collections.
   - The core pipeline: **Voyageur** (Gather) → **Paleographer** (Analyze) → **Archivist** (Create GEDCOM).
   - Navigation links to all wiki topics.

2. **`_Sidebar.md` & `_Footer.md`**:
   - Sticky GitHub Wiki navigation bar categorizing pages into: *Overview*, *Getting Started*, *Pipeline Modules*, *Maintenance Tools*, and *Reference*.

3. **`Getting-Started.md`**:
   - System requirements (Windows 10/11, Python 3.12+).
   - Installing dependencies via `requirements.txt`.
   - Installing the `Voyageur.js` TamperMonkey browser extension.
   - Launching Scriptorium (`python Scriptorium.py`).
   - First-run checklist.

4. **`Configuration-&-Settings.md`**:
   - Using the Global Settings tab in the application.
   - API key management (OpenAI, Anthropic, Gemini, local LLM servers).
   - Working directories, raw download folders, and output destinations.
   - The `.env` file configuration reference.

5. **`Voyageur-User-Guide.md`**:
   - Purpose: Gathering images and index records from online repositories.
   - **Ancestry**: Gathering indexed census pages and automated image downloads.
   - **FamilySearch**: Extracting church register index tables, citation metadata, and duplicate person linking.
   - **Library and Archives Canada (LAC) / Canadiana**: Automated multi-worker image downloads from microfilm reels and volume bundles.
   - Managing rate limits, cookies, and network retries.

6. **`Paleographer-User-Guide.md`**:
   - Purpose: Transcribing historical document images into structured JSON using AI models.
   - Selecting record types (Parish registers, Metis Scrip, Census).
   - Single-sheet live extraction vs. background batch job execution.
   - Reviewing, editing, and saving the master database JSON.
   - Handling unrecognized handwriting, abbreviations, and low-confidence readings.

7. **`Archivist-User-Guide.md`**:
   - Purpose: Generating standards-compliant GEDCOM 5.5.1 files from normalized master databases.
   - Automatic record type detection.
   - Household reconstruction heuristics.
   - Linking primary individuals, spouses, parents, witnesses, and godparents.
   - Importing the output GEDCOM into RootsMagic and Family Tree Maker.

8. **`Registrar-&-Gazetteer.md`**:
   - **Safety First**: Closing RootsMagic and backing up tree files before running database maintenance.
   - **Registrar**: Scanning RootsMagic trees for duplicate individuals with configurable fuzzy name and date thresholds.
   - **Gazetteer**: Normalizing historical county and territory boundary names using the Newberry Atlas dataset.

9. **`PDFix-Utility.md`**:
   - Repairing corrupted or non-standard PDF files.
   - Extracting page images at native resolutions for Paleographer input.

10. **`Troubleshooting-&-FAQ.md`**:
    - Resolving TamperMonkey communication issues.
    - Handling API quota limits and timeouts.
    - Fixing database file lock errors.
    - Recovering from interrupted batch downloads.

---

## 4. Developer Documentation Specification (`docs/developer/`)

These files reside in `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium\docs\developer\`.

### 4.1 Document Structure & Contents

1. **`docs/developer/architecture-overview.md`**:
   - Top-level architectural diagram (UI layer, pipeline stages, shared validation kernel).
   - Directory structure and responsibilities of core modules (`Scriptorium.py`, `Voyageur/`, `Paleographer/`, `Archivist/`, `Commissioner/`, `Registrar/`, `Gazetteer/`, `PDFix/`).
   - Execution lifecycle of a typical record batch.

2. **`docs/developer/commissioner-domain-models.md`**:
   - Purpose of the `Commissioner` domain validation layer.
   - Pydantic v2 core models: `Collection`, `Sheet`, `Record`, `Participant`, `Fact`, `Citation`.
   - Soft-fail validation contract: `validate_soft(data, document_type, label)`.
   - Role validation modes: `closed` (strict whitelist) vs `open` (extensible).
   - Extra fields validation against typed definitions.

3. **`docs/developer/pmt-specification.md`**:
   - The `.pmt` (Prompt Template) file specification.
   - YAML front matter schema: `roles`, `role_validation`, `extra_fields` (record and participant level).
   - Markdown prompt body conventions for LLM instructions.
   - Adding a new document type without modifying core Python code.

4. **`docs/developer/scaffold-data-contract.md`**:
   - The Master DB JSON contract shared between Voyageur and Paleographer.
   - Scaffold sheet format (`page_id`, `document_metadata`, empty `records`).
   - Merge semantics: replacing placeholder scaffold sheets with real extracted data while preserving ordering.
   - Checkpoint format and download progress tracking.

5. **`docs/developer/development-workflow.md`**:
   - Virtual environment setup and dependency installation.
   - Running the test suite (`pytest` conventions, fixture design, mocking network dependencies).
   - Code style enforcement (`pycodestyle --max-line-length=120`, zero lint policy).
   - Commit standards and release verification checklist.

---

## 5. Main Repo README Cross-Linking

Update `README.md` in the root repository to provide direct markdown links:
- User Guide links pointing to GitHub Wiki pages (`https://github.com/alerum68/Scriptorium/wiki/...`).
- Developer Architecture links pointing to local `docs/developer/` files.

---

## 6. Implementation & Delivery Plan

1. **Task 1: User Documentation (GitHub Wiki in `Scriptorium-Docs`)**
   - Create and populate all 10 wiki markdown files in `Scriptorium-Docs`.
   - Verify formatting and navigation.
   - Commit and push to `origin/master` (or main branch) on `Scriptorium.wiki.git`.
2. **Task 2: Developer Documentation (`docs/developer/`)**
   - Create `docs/developer/` directory.
   - Author all 5 technical specification documents.
   - Ensure diagrams and code examples match the current codebase.
3. **Task 3: Root README Update & Verification**
   - Update `README.md` with links to wiki and developer docs.
   - Verify all file paths and external URLs.
   - Run pycodestyle / pytest to guarantee repo health.
   - Commit and push to `origin/Unify`.
