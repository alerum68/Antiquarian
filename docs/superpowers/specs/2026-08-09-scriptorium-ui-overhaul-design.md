# Antiquarian UI & Settings Overhaul Design

## 1. Overview
The goal of this overhaul is to drastically simplify the Antiquarian interface by removing "developer-centric" settings, hardcoding them as sensible defaults, and upgrading remaining inputs to proper UI widgets (checkboxes, dropdowns) to prevent option overload for genealogists. We will also integrate a seamless "Sign in to Google" button for AGY (`agy`), deprecating raw AI Assistant API inputs.

## 2. AGY OAuth Integration
- **Remove API Variables:** Remove all direct AI Assistant API variables from `Global Settings` (`EXTRACTION_ENGINE`, `AI_API_KEY`, `API_BUDGET`, `MODEL_NAME`, `COST_PER_1M_INPUT`, `COST_PER_1M_OUTPUT`, `CACHE_DISCOUNT_MULTIPLIER`).
- **Remove API Logic:** Purge legacy API backend fallback code across the app, ensuring the app relies solely on `agy`.
- **UI Addition:** Add a prominent "Sign in to Google" button on the Global Settings tab. When clicked, it will shell out to `agy login`, triggering the OAuth flow in the user's browser. The UI will poll `agy login --status` and update to show the connected user email upon success.

## 3. Setting Removals (Hardcoded Constants)
These settings will be removed from the UI (YAML schemas and `GLOBAL_VARS`) and hardcoded directly into their respective scripts:

### Global Settings
- `SOFTWARE_NAME`, `SOFTWARE_VERS`, `COPYRIGHT_START`, `GEDCOM_NOTE`, `GEDCOM_CONC`
- `REVIEW_COLOR` (Hardcode to 1, or rely strictly on RootMagic task defaults)

### Archivist
- `MIN_MARRIAGE_AGE`, `MAX_SPOUSE_AGE_GAP`
- `HUSBAND_CHILD_AGE_GAP_MIN`, `HUSBAND_CHILD_AGE_GAP_MAX`
- `WIFE_CHILD_AGE_GAP_MIN`, `WIFE_CHILD_AGE_GAP_MAX`

### Paleographer
- `AGY_CLI_BIN`, `AGY_TIMEOUT_SECONDS` (Timeout fixed to 240s)
- `MASTER_DB`, `OUTPUT_DIR` (Fully automate path resolution)
- `SCRIP_DELAY_SECONDS` (Fixed to 0.4s), `SCRIP_ENRICH_LIMIT`, `SCRIP_PARTITION_OUTPUT_DIR`

### Voyageur
- `LAC_COOKIE_FILE`, `LAC_CHECKPOINT_DIR`, `LAC_CDP_PORT`
- `HBCA_CHECKPOINT_DIR`
- `LAC_MAX_WORKERS`, `HBCA_MAX_WORKERS` (Both hardcoded to `8` as the standard for all headless gathering tasks)

## 4. UI Widget Upgrades
Replace basic text string inputs with rich UI widgets in the YAML schemas:

### Checkboxes (Booleans)
- **Voyageur:** `HBCA_RESOLVE_KEYSTONE`
- **Voyageur:** `HBCA_DOWNLOAD_KEYSTONE_MEDIA`

### Dropdowns
- **Paleographer:** `PALEOGRAPHER_RECORD_TYPE` (Dynamically populated by listing the `.pmt` files in the `Paleographer/prompts` directory).
- **Voyageur:** `VOYAGEUR_SOURCE` (Formalized to ensure it uses a dropdown instead of text).
