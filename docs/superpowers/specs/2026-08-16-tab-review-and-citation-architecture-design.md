# Antiquarian UI Tab Review & Citation Architecture

## 1. Overview
Following a detailed review of each tab in the Antiquarian UI, this design focuses on simplifying the Gather process, shifting manual Citation entry to the AI analysis stage where it can inform extraction, and drastically improving the Help window documentation.

## 2. Voyageur (Gather) Tab Consolidation
The Voyageur tab will simplify its inputs by dynamically swapping the backend variables based on the active `VOYAGEUR_SOURCE`.
* **Consolidated Gather Options:** The UI will expose a single `Gather URL` input and a `Collision Policy` dropdown. The backend scripts (`A.py`, `FS.py`, `HBCA.py`) will be updated to read generic `GATHER_URL` instead of provider-specific variants.
* **HBCA-Specific Settings:** `HBCA_LETTER_FILTER`, `HBCA_RESOLVE_KEYSTONE`, and `HBCA_DOWNLOAD_KEYSTONE_MEDIA` will be retained and shown conditionally when HBCA is selected.
* **LAC Abstraction:** `LAC_VOLUME`, `LAC_RECORD_TYPE`, and `VOLUME_TITLE` will be hidden from the UI. The script will be updated to auto-generate or parse these from the downloaded data to reduce manual user burden.

## 3. Paleographer (Analyze) & Citation Data Shift
Because images bypassing Voyageur still need citation metadata, and because the AI context window benefits from Volume/Title context during transcription, we are moving manual citation injection upstream.
* **Citation Migration:** All citation override fields (`PUBLISHER`, `REPOSITORY`, `CALL_NUMBER`, `COLLECTION_URL`, `COLLECTION_NAME`, `PUB_LOC`, `REGISTER_NAME`, `REGISTER_SOURCE_ID`, `CITATION_DETAIL`, `CITATION_TEXT`) will move from the **Archivist** settings schema to the **Paleographer** settings schema.
* **Dynamic Display:** The `.pmt` files (e.g., `Parish.pmt`, `Scrip.pmt`) will be updated to include `Citation Overrides` in their `settings_sections` array, ensuring these fields dynamically appear in the UI only when the corresponding record type is selected.
* **Metadata Injection:** `Extract.py` will be updated to inject these configured citation fields directly into the `document_metadata` or `collection_metadata` block of the generated Master DB JSON.

## 4. Archivist (Create) Tab Simplification
* **Remove Citation Inputs:** With citation data moving upstream to Paleographer, the Archivist tab will be stripped of these manual fields.
* **JSON Dependency:** `General.py` and other GEDCOM compilation scripts will be updated to pull their citation metadata from the ingested JSON file rather than the local `.env` variables.

## 5. Help Documentation Refresh
* **UI Tooltips:** Ensure every field in every `settings_schema.yaml` has a clear, accurate `tooltip` attribute.
* **Help Windows:** Rewrite the `self.help_texts` dictionary in `Antiquarian.py` to match the new dynamic reality of the tabs, explicitly explaining how fields conditionally appear based on the chosen Gather Source or Record Type.
