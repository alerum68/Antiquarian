# Scriptorium Settings/UI Redesign — Design

## Problem

`Scriptorium.py`'s settings definitions (`GLOBAL_VARS`, `ARCHIVIST_VARS`, `VOYAGEUR_VARS`, `PALEOGRAPHER_VARS`, `REGISTRAR_VARS`, `GAZETTEER_VARS`, `PDFIX_VARS`, plus their `TOOLTIP_DESCRIPTIONS`/`FIELD_WIDGETS`/`PATH_PICKER_FIELDS`/`CUSTOM_LABELS`) were written when the project started and have drifted from what each tool actually reads via `os.getenv`/`os.environ.get`, since each tool has changed substantially (Commissioner domain models, the citation-field rename, the Parish/Scrip profile scaffold, the Voyageur/Paleographer/Archivist structural splits). Centralizing every tool's settings inside `Scriptorium.py` means each tool's own evolution has no natural pressure to keep the GUI in sync — nothing breaks when a tool grows a new setting the GUI never learns about.

## Audit findings (confirmed via direct `os.getenv`/`os.environ.get` grep against each tool's source)

**Archivist** — missing from UI entirely:
- `TRANSCRIPTION_HEADER`, `TRANSLATION_HEADER`, `ROLE_CLERGY`, `CLERGY_HONORIFIC`, `ROLE_DEFAULT_WITNESS` (read by `General.py`)
- `ENUMERATION_DISTRICT`, `FILM_NUMBER`, `ROLL_NUMBER` (sit alongside `STATE`/`COUNTY`/`TOWNSHIP` in code, absent from the "Location Overrides" UI section)
- Also structurally behind Paleographer/Voyageur: has no Record-Type/profile dropdown or per-profile filtered settings, despite the Archivist structural-split plan (`2026-08-07-archivist-structural-split.md`) introducing `PROFILE_REGISTRY`/`resolve_profile`.

**Paleographer** — missing `AGY_CLI_BIN`, `AGY_TIMEOUT_SECONDS` (read by `Extract.py`). Everything else confirmed matching. Help text is also stale: mentions "Enrich Metadata"/"Partition Collections" but not the `crosscheck`/`resolve-names` modes `Paleographer.py`'s `ENRICHMENT_MODES` already dispatches.

**Voyageur/LAC** — one confirmed bug, not just a gap: the UI field is `LAC_HARVEST_ARCHIVAL_NUMBER`, but `LAC.py` reads `LAC_ARCHIVAL_NUMBER` (no "HARVEST"). They have never matched — editing that field in the GUI has always been a no-op; `LAC.py` silently falls back to its own hardcoded `"RG15"` default. Also missing from UI: `LAC_CHECKPOINT_DIR`, `LAC_CDP_PORT`, `LAC_MAX_WORKERS`.

**Registrar** — no missing fields. The six thresholds/colors are all read (via a `_get_env_int()` wrapper, which is why an early literal-pattern grep missed them) and already represented in the UI. `Registrar/schema_ui_map.py` is dead, unimported scaffolding — never referenced anywhere in the codebase — but its `UI_SCHEMA_MAPPINGS` dict carries per-field `description` text that's often better than the current tooltips.

**Gazetteer** — no missing fields; `GAZETTEER_RM_DATABASE`/`GAZETTEER_SHAPEFILE` are read via a multi-line `os.getenv(...)` call an early grep pattern couldn't span.

**PDFix** — no missing fields, confirmed clean.

**Commissioner** — pure domain-model library (`fact_registry.py`, `models.py`, `normalization.py`, `record_registry.py`). Zero `os.getenv` calls, no `SCRIPT_PATHS` entry, never launched standalone. No UI representation needed.

## Design

### 1. Per-tool schema files (YAML)

Each tool folder gets its own `settings_schema.yaml`: `Voyageur/`, `Paleographer/`, `Archivist/`, `Registrar/`, `Gazetteer/`, `PDFix/`. `GLOBAL_VARS` and `SCRIPT_PATHS` stay as Python literals in `Scriptorium.py` — they're cross-cutting (API key, researcher credit, shared directories), not owned by any one tool.

Shape:

```yaml
sections:
  Location Overrides:
    STATE:
      default: ""
      tooltip: "Overrides the state/province Archivist infers from context."
    ENUMERATION_DISTRICT:
      default: ""
      tooltip: "Census-specific enumeration district identifier."
    PALEOGRAPHER_PDF_COMPRESSION_LEVEL:
      default: "1"
      widget: segmented
      options: [["0", "Low"], ["1", "Medium"], ["2", "High"]]
    JSON_DIR:
      default: "Working"
      picker: {kind: directory, base_dir_key: "__PROGRAM_DIR__"}
    label_overrides:
      GEDCOM_CONC: "GEDCOM CONC Tag"
```

`"__PROGRAM_DIR__"` / `"__TOOLBOX_DIR__"` are the string forms of today's `PROGRAM_DIR_SENTINEL`/`TOOLBOX_DIR_SENTINEL`.

Every widget/picker key from today's `FIELD_WIDGETS`/`PATH_PICKER_FIELDS` carries over unchanged, just nested under `widget`/`picker` in the YAML instead of living in a separate top-level dict keyed by field name:

```yaml
    SCRIP_DELAY_SECONDS:
      default: "0.4"
      widget: slider
      min: 0
      max: 5
      step: 0.1
      suffix: "s"
    PALEOGRAPHER_ENABLE_CACHE:
      default: "True"
      widget: toggle
    GEDCOM_OUTPUT_PATH:
      default: ""
      picker: {kind: save, base_dir_key: "__PROGRAM_DIR__", defaultextension: ".ged",
               filetypes: [["GEDCOM files", "*.ged"], ["All files", "*.*"]]}
    ROOT_SOURCE_ID:
      default: ""
      picker: {kind: open, base_dir_key: "__PROGRAM_DIR__", always_absolute: true}
```

**Migration scope is settings-only.** Only the field list, tooltips, widget specs, path pickers, and labels move per-tool. Bespoke tab UI — action buttons, dropdown wiring, help text, button gating (e.g. Paleographer's Scrip-only buttons), the LAC debug-browser launcher — stays hand-written in `Scriptorium.py`'s `_build_tab_*` methods. That logic is workflow behavior, not settings, and forcing it into a generic schema would fight each tab's genuinely different bespoke needs.

**Why YAML over a relocated Python module:** matches the `.pmt` front-matter precedent already in the codebase (Paleographer/Archivist profile files), and directly serves the actual goal (easy hand-editing) better than Python dict literals. The one YAML footgun — implicit typing turning an unquoted `0.4`/`true`/`off` into a non-string — is fully closed by having the loader `str()` every loaded value immediately regardless of YAML's inferred type, so no field needs to be quoted defensively.

### 2. Generic loader + Archivist integration

`Scriptorium.py` gains one function, `_load_tool_schema(tool_dir: Path) -> dict`, returning the same shape `_build_form_ui` already consumes today. `_build_form_ui`, `_build_segmented_field`, `_build_slider_field`, `_browse_for_path` are unchanged — only where their input data comes from changes. `ENV_TARGETS` is now built by the loader (each schema's target subfolder is the tool folder it loaded from) instead of six hand-maintained tuples.

Archivist gets the Record-Type dropdown + filtered-form treatment Paleographer/Voyageur already have (`_on_record_type_change`/`_on_voyageur_source_change`), but driven by `PROFILE_REGISTRY` rather than `.pmt` files: `Scriptorium.py` imports Archivist's profile module directly and reads `PROFILE_REGISTRY.keys()` for the dropdown values. Each `PROFILE_REGISTRY` entry gains an optional `settings_sections: list[str]` attribute (same meaning as `.pmt`'s `settings_sections`) — the Archivist structural-split plan (Task A, not yet implemented) needs this attribute added before this project's Archivist work begins.

### 3. Migration + error handling

All six `*_VARS` dicts are translated into their tool's `settings_schema.yaml` in one atomic change, carrying over current defaults/sections/tooltips/widgets/pickers/labels plus the confirmed debt fixes above (new fields, the `LAC_ARCHIVAL_NUMBER` rename, Registrar's `schema_ui_map.py` descriptions harvested as tooltips and the file then deleted). `Scriptorium.py`'s old module-level `*_VARS`/`TOOLTIP_DESCRIPTIONS`/`FIELD_WIDGETS`/`PATH_PICKER_FIELDS`/`CUSTOM_LABELS` dicts are deleted in the same change — no transition period where both a hardcoded dict and a YAML file claim the same tool.

This is a single-user local desktop tool: a malformed or missing `settings_schema.yaml` fails loudly at startup with a message naming the file and the parse error, rather than silently rendering an empty or partial form.

### 4. Testing

**Loader unit tests** — pure-function tests against small YAML fixtures: correct section/field shapes, `str()` coercion of YAML-typed values, path-picker sentinel resolution, and a clear error on malformed YAML.

**Schema-completeness regression test** — for each tool, grep its source for every env-var read (the same technique used for this audit) and assert every key exists in that tool's `settings_schema.yaml` (excluding the `GLOBAL_VARS` keys). This is the test that would have caught every gap in this audit, and it fails the next time a tool grows a setting the GUI doesn't know about — turning "settings silently drift" from a manual audit into an automated check.

No GUI-automated tests (CustomTkinter widget rendering isn't practically testable here); manual click-through per tab covers rendering/save/reload behavior, same as today.

## Out of scope

- Sidebar/tab grouping changes beyond the Archivist dropdown addition — the current pipeline-then-Utilities grouping already matches the actual workflow.
- Moving help text, tab titles/descriptions, or action-button definitions into the schema files (considered and rejected — see Migration scope above).
- Any change to Commissioner (no UI needed).
