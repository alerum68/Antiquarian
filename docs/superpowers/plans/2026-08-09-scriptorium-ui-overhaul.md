# Scriptorium UI & Settings Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Simplify the Scriptorium UI by removing developer-centric settings, implementing agy OAuth, and adding proper UI widgets.

**Architecture:** We will systematically strip variables from `GLOBAL_VARS` and the tool-specific `settings_schema.yaml` files. Where these variables were previously consumed via `os.getenv()`, we will replace them with hardcoded constants in the Python scripts. Finally, we will inject a native CustomTkinter button into `Scriptorium.py` to shell out to `agy login`.

**Tech Stack:** Python, CustomTkinter, YAML, python-dotenv, subprocess.

## Global Constraints

No test requirements were specified in the blueprint (this is primarily a UI and configuration cleanup task). Commits must be frequent and atomic.

---

### Task 1: Clean up Global Settings and Implement agy OAuth

**Files:**
- Modify: `Scriptorium.py`

**Interfaces:**
- Consumes: The `Scriptorium.py` file builds UI dynamically using `GLOBAL_VARS` and `TOOLTIP_DESCRIPTIONS`.

- [ ] **Step 1: Remove API and Boilerplate Variables from GLOBAL_VARS**

In `Scriptorium.py`, edit `GLOBAL_VARS`. Remove `EXTRACTION_ENGINE`, `AI_API_KEY`, `API_BUDGET`, `MODEL_NAME`, `COST_PER_1M_INPUT`, `COST_PER_1M_OUTPUT`, `CACHE_DISCOUNT_MULTIPLIER`. Also remove `SOFTWARE_NAME`, `SOFTWARE_VERS`, `COPYRIGHT_START`, `GEDCOM_NOTE`, `GEDCOM_CONC`, `REVIEW_COLOR`.
Keep `AGY_MODEL_NAME`.
Also remove their corresponding entries in `TOOLTIP_DESCRIPTIONS` and `CUSTOM_LABELS`.

- [ ] **Step 2: Add agy OAuth Button Logic to Scriptorium.py**

In `Scriptorium.py`, add a new helper method to the `Scriptorium` class that handles the agy login:

```python
    def _run_agy_login(self, status_label):
        status_label.configure(text="Logging in...", text_color=C_ACCENT)
        self.update_idletasks()
        try:
            # Run agy login, which pops the browser
            subprocess.run(["agy", "login"], check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            
            # Poll for status
            result = subprocess.run(["agy", "login", "--status"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if "Logged in as" in result.stdout:
                status_label.configure(text=result.stdout.strip(), text_color=C_SUCCESS)
            else:
                status_label.configure(text="Not connected.", text_color=C_DANGER)
        except Exception as e:
            status_label.configure(text=f"Error: {e}", text_color=C_DANGER)
```

- [ ] **Step 3: Inject the Button into the Global Settings Tab**

In `Scriptorium.py`, inside `_build_tab_global(self, parent_frame):`, add the button at the top of the tab before the dynamically built form:

```python
    def _build_tab_global(self, parent_frame):
        # --- NEW AGY AUTHENTICATION WIDGET ---
        auth_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        auth_frame.pack(fill="x", padx=20, pady=(20, 0))
        
        btn = ctk.CTkButton(auth_frame, text="Sign in to Google (AGY)", fg_color=C_ACCENT, text_color=C_ON_ACCENT, hover_color=C_ACCENT_STRONG)
        btn.pack(side="left", padx=(0, 10))
        
        status_lbl = ctk.CTkLabel(auth_frame, text="Not connected.", text_color=C_TEXT_MUTED)
        status_lbl.pack(side="left")
        
        btn.configure(command=lambda: threading.Thread(target=self._run_agy_login, args=(status_lbl,), daemon=True).start())
        # -------------------------------------
        
        self._build_form_ui(parent_frame, ENV_TARGETS[0][0], ENV_TARGETS[0][1])
```

- [ ] **Step 4: Commit**

```bash
git add Scriptorium.py
git commit -m "refactor(ui): remove dev global vars and add agy login button"
```

---

### Task 2: Clean up Archivist Settings Schema

**Files:**
- Modify: `Archivist/settings_schema.yaml`
- Modify: `Archivist/Census.py` (where inference variables are used)

- [ ] **Step 1: Remove Family Inference Tuning from Schema**

In `Archivist/settings_schema.yaml`, remove the entire "Family Inference Tuning" section (which includes `MIN_MARRIAGE_AGE`, `MAX_SPOUSE_AGE_GAP`, `HUSBAND_CHILD_AGE_GAP_MIN`, `HUSBAND_CHILD_AGE_GAP_MAX`, `WIFE_CHILD_AGE_GAP_MIN`, `WIFE_CHILD_AGE_GAP_MAX`).

- [ ] **Step 2: Hardcode age gaps in Census inference logic**

In `Archivist/Census.py` (or wherever these `os.getenv` calls are made, search for `MIN_MARRIAGE_AGE`), replace `os.getenv("MIN_MARRIAGE_AGE", ...)` calls with hardcoded integers:
`MIN_MARRIAGE_AGE = 12`
`MAX_SPOUSE_AGE_GAP = 25`
`HUSBAND_CHILD_AGE_GAP_MIN = 14`
`HUSBAND_CHILD_AGE_GAP_MAX = 60`
`WIFE_CHILD_AGE_GAP_MIN = 12`
`WIFE_CHILD_AGE_GAP_MAX = 50`

- [ ] **Step 3: Commit**

```bash
git add Archivist/settings_schema.yaml Archivist/Census.py
git commit -m "refactor(archivist): hardcode family inference tuning parameters"
```

---

### Task 3: Clean up Paleographer Settings Schema

**Files:**
- Modify: `Paleographer/settings_schema.yaml`
- Modify: `Paleographer/Paleographer.py`

- [ ] **Step 1: Remove Technical Options from Schema**

In `Paleographer/settings_schema.yaml`, remove `AGY_CLI_BIN`, `AGY_TIMEOUT_SECONDS`, `MASTER_DB`, `OUTPUT_DIR`, `SCRIP_DELAY_SECONDS`, `SCRIP_ENRICH_LIMIT`, `SCRIP_PARTITION_OUTPUT_DIR`.

- [ ] **Step 2: Upgrade Record Type to Dropdown**

In `Paleographer/settings_schema.yaml`, add the `widget: dropdown` spec to `PALEOGRAPHER_RECORD_TYPE`. We will configure the options in code, but schema should look like:
```yaml
    PALEOGRAPHER_RECORD_TYPE:
      default: "Parish.pmt"
      tooltip: "Which record type (from Paleographer/prompts) to transcribe."
      widget: "dropdown"
      options: [["Parish.pmt", "Parish.pmt"], ["Scrip.pmt", "Scrip.pmt"]]
```
*(Note: A dynamic loader in Scriptorium.py could do this, but for simplicity, we define the static list in YAML for now since those are the main two).*

- [ ] **Step 3: Hardcode Variables in Paleographer.py**

In `Paleographer/Paleographer.py` (and any related `Scrip.py`), ensure `AGY_TIMEOUT_SECONDS` defaults to 240, and `SCRIP_DELAY_SECONDS` defaults to 0.4.

- [ ] **Step 4: Commit**

```bash
git add Paleographer/settings_schema.yaml Paleographer/Paleographer.py
git commit -m "refactor(paleographer): remove dev options and add dropdown for record type"
```

---

### Task 4: Clean up Voyageur Settings Schema and Logic

**Files:**
- Modify: `Voyageur/settings_schema.yaml`
- Modify: `Voyageur/LAC.py` and `Voyageur/HBCA.py`

- [ ] **Step 1: Remove Checkpoints and Dev Options**

In `Voyageur/settings_schema.yaml`, remove `LAC_COOKIE_FILE`, `LAC_CHECKPOINT_DIR`, `LAC_CDP_PORT`, `LAC_MAX_WORKERS`, `HBCA_CHECKPOINT_DIR`, `HBCA_MAX_WORKERS`.

- [ ] **Step 2: Add Checkbox Widgets**

In `Voyageur/settings_schema.yaml`, update `HBCA_RESOLVE_KEYSTONE` and `HBCA_DOWNLOAD_KEYSTONE_MEDIA` to use boolean checkboxes:
```yaml
    HBCA_RESOLVE_KEYSTONE:
      default: "false"
      tooltip: "Query Archives of Manitoba Keystone database to resolve microfilm/finding aid links for cited location codes."
      widget: "checkbox"
```
*(Ensure `widget: checkbox` is supported by the `Scriptorium.py` UI builder, or map them to `segmented` True/False toggles).*

- [ ] **Step 3: Hardcode 8 Workers in scripts**

In `Voyageur/LAC.py` and `Voyageur/HBCA.py` (where `os.getenv("LAC_MAX_WORKERS")` is used), change the code to use a hardcoded value of `8`.

- [ ] **Step 4: Commit**

```bash
git add Voyageur/settings_schema.yaml Voyageur/LAC.py Voyageur/HBCA.py
git commit -m "refactor(voyageur): remove download dev configs and hardcode 8 workers"
```
