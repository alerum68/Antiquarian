# Antiquarian Settings/UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Replace `Antiquarian.py`'s six hardcoded, drifted `*_VARS`/`TOOLTIP_DESCRIPTIONS`/`FIELD_WIDGETS`/`PATH_PICKER_FIELDS`/`CUSTOM_LABELS` settings dicts with per-tool `settings_schema.yaml` files loaded by one generic function, fixing every confirmed drift bug (missing fields, the `LAC_ARCHIVAL_NUMBER` rename, stale help text) along the way.

**Architecture:** Each of the six tools (`Archivist/`, `Voyageur/`, `Paleographer/`, `Registrar/`, `Gazetteer/`, `PDFix/`) gets its own `settings_schema.yaml`. A new module-level function, `_load_tool_schema(tool_dir: Path) -> Dict[str, Dict[str, str]]`, reads one tool's YAML, returns the `{section: {key: default}}` shape `_build_form_ui` already consumes, and as a side effect merges that tool's tooltips/widgets/pickers/label-overrides into the shared module-level dicts. Each `*_VARS = {...}` literal becomes `*_VARS = _load_tool_schema(BASE_DIR / "ToolName")`. `GLOBAL_VARS` and `SCRIPT_PATHS` stay Python literals — they are cross-cutting, not tool-owned. `_build_form_ui`, `_build_segmented_field`, `_build_slider_field`, `_browse_for_path`, `ENV_TARGETS` need zero code changes: `ENV_TARGETS` is a literal list of `(NAME, subfolder)` tuples that already reference the `*_VARS` names by identifier, so it keeps working unchanged once those names hold loader output instead of dict literals.

**Tech Stack:** Python, `pyyaml` (already `pyyaml==6.0.3` in `requirements.txt`), `pytest` (via `tests/conftest.py`'s `sys.path` shim), CustomTkinter (unchanged).

## Global Constraints

- **Migration scope is settings-only.** Field lists, tooltips, widget specs, path pickers, and labels move per-tool into YAML. Action buttons, dropdown wiring, help text (except the one confirmed stale Paleographer fix in Task 4), button gating, and the LAC debug-browser launcher stay hand-written in `Antiquarian.py`'s `_build_tab_*` methods — untouched by this plan.
- **Fail loud.** A missing or malformed `settings_schema.yaml` raises at startup naming the file and the parse error — never renders a silently empty or partial form. `_load_tool_schema` raises `FileNotFoundError` (missing file), `RuntimeError` (malformed YAML), or `ValueError` (missing `sections` key, a section that isn't a mapping, or a field missing `default`) — every message names the schema file path.
- **YAML values are always `str()`-coerced.** Only the `default` value is coerced immediately on load, closing YAML's implicit-typing footgun (`0.4`/`true` parsing as non-string) without needing defensive quoting in any YAML file. Widget numeric params (`min`/`max`/`step`) are NOT string-coerced — they stay native ints/floats, matching `_build_slider_field`'s existing math.
- **`GLOBAL_VARS` and `SCRIPT_PATHS` never migrate.** They stay Python literals in `Antiquarian.py`. Their own entries in `TOOLTIP_DESCRIPTIONS`/`CUSTOM_LABELS`/`PATH_PICKER_FIELDS`/`FIELD_WIDGETS` are never touched by any task in this plan, including `CENSUS_IMAGE_DIR` (a `GLOBAL_VARS` key that happens to sit under a `# Archivist` comment in those dicts today).
- **Archivist keeps a flat form** — no Record-Type dropdown, rendered exactly like Registrar/Gazetteer/PDFix. This plan has no dependency on the separate, unimplemented Archivist structural-split plan.
- **No changes to Commissioner** — it has no UI and no `os.getenv` calls.
- **Sidebar/tab grouping is unchanged.**
- **No transition period.** Each tool's task deletes that tool's hardcoded dict entries in the same commit that adds its YAML file — never both claiming the same tool's settings at once.

---

## File Structure

- **Create:** `Archivist/settings_schema.yaml`, `Voyageur/settings_schema.yaml`, `Paleographer/settings_schema.yaml`, `Registrar/settings_schema.yaml`, `Gazetteer/settings_schema.yaml`, `PDFix/settings_schema.yaml` — one per tool, each with a top-level `sections:` key (section name → field name → `{default, tooltip?, widget?, picker?}`) and an optional top-level `label_overrides:` key (field name → display label).
- **Modify:** `Antiquarian.py` — add `_load_tool_schema`; relocate `TOOLTIP_DESCRIPTIONS`/`CUSTOM_LABELS`/`PROGRAM_DIR_SENTINEL`/`TOOLBOX_DIR_SENTINEL`/filetypes constants/`PATH_PICKER_FIELDS`/`FIELD_WIDGETS` to sit between `GLOBAL_VARS` and `ARCHIVIST_VARS`; replace each of the six `*_VARS` literals with a `_load_tool_schema()` call and trim that tool's entries out of the four shared dicts; fix the stale Paleographer help text; delete the now-dead `RMTREE_FILETYPES`/`JSON_FILETYPES`/`GED_FILETYPES`/`SHP_FILETYPES` constants once nothing references them.
- **Modify:** `Paleographer/prompts/Parish.pmt`, `Paleographer/prompts/Scrip.pmt` — add the new `"AGY CLI"` section to each file's `settings_sections:` list, so the two new Paleographer fields (owned by `Extract.py`, used by both record types) aren't silently hidden by the existing per-record-type section filter.
- **Delete:** `Registrar/schema_ui_map.py` — dead, unimported scaffolding; its `UI_SCHEMA_MAPPINGS` descriptions are harvested into Registrar's new YAML tooltips in Task 5, then the file is removed.
- **Create:** `tests/test_load_tool_schema.py` — pure-function unit tests for the loader against small YAML fixtures.
- **Create:** `tests/test_settings_schema_completeness.py` — per-tool regression test: greps each tool's own source for every `os.getenv`/`os.environ.get` key and asserts it exists in that tool's `settings_schema.yaml`.
- **Create:** `tests/test_antiquarian_settings_migration.py` — one assertion per tool (Tasks 2–7) that `_load_tool_schema` on the real, committed YAML reproduces the exact `{section: {key: default}}` shape the old hardcoded dict used to provide (plus the debt-fix additions).

---

### Task 1: `_load_tool_schema` loader + unit tests

Purely additive: adds the function and its dedicated test file. No `*_VARS` assignment changes yet, so nothing in the app's runtime behavior changes in this task.

**Files:**
- Modify: `Antiquarian.py` (insert after the `FIELD_WIDGETS = {...}` dict, which currently ends at line 435, and before the `# CUSTOM WIDGET CLASSES` comment at line 438)
- Test: `tests/test_load_tool_schema.py`

**Interfaces:**
- Produces: `_load_tool_schema(tool_dir: Path) -> Dict[str, Dict[str, str]]`, a module-level function (not a method) in `Antiquarian.py`. Reachable in tests as `Antiquarian._load_tool_schema` after `import Antiquarian`. Raises `FileNotFoundError`/`RuntimeError`/`ValueError` as described in Global Constraints. Side effect: mutates the module globals `TOOLTIP_DESCRIPTIONS`, `CUSTOM_LABELS`, `PATH_PICKER_FIELDS`, `FIELD_WIDGETS` via `.update()`/item-assignment (never reassigns them, so existing references stay valid).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_load_tool_schema.py`:

```python
import textwrap

import pytest

import Antiquarian


@pytest.fixture(autouse=True)
def _restore_shared_dicts():
    """_load_tool_schema mutates shared module-level dicts as a side effect - snapshot and
    restore them around every test so tests can't pollute each other or the real schema
    state loaded at import time."""
    tooltip_before = dict(Antiquarian.TOOLTIP_DESCRIPTIONS)
    labels_before = dict(Antiquarian.CUSTOM_LABELS)
    pickers_before = dict(Antiquarian.PATH_PICKER_FIELDS)
    widgets_before = dict(Antiquarian.FIELD_WIDGETS)
    yield
    Antiquarian.TOOLTIP_DESCRIPTIONS.clear()
    Antiquarian.TOOLTIP_DESCRIPTIONS.update(tooltip_before)
    Antiquarian.CUSTOM_LABELS.clear()
    Antiquarian.CUSTOM_LABELS.update(labels_before)
    Antiquarian.PATH_PICKER_FIELDS.clear()
    Antiquarian.PATH_PICKER_FIELDS.update(pickers_before)
    Antiquarian.FIELD_WIDGETS.clear()
    Antiquarian.FIELD_WIDGETS.update(widgets_before)


def test_load_tool_schema_basic_shape(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            FIELD_A:
              default: "hello"
              tooltip: "A tooltip."
            FIELD_B:
              default: 0.4
        """), encoding="utf-8")

    result = Antiquarian._load_tool_schema(tmp_path)

    assert result == {"Section One": {"FIELD_A": "hello", "FIELD_B": "0.4"}}


def test_load_tool_schema_str_coerces_yaml_typed_defaults(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            BOOL_FIELD:
              default: true
            INT_FIELD:
              default: 3
            FLOAT_FIELD:
              default: 0.4
        """), encoding="utf-8")

    result = Antiquarian._load_tool_schema(tmp_path)

    assert result == {"Section One": {"BOOL_FIELD": "True", "INT_FIELD": "3", "FLOAT_FIELD": "0.4"}}
    assert all(isinstance(v, str) for v in result["Section One"].values())


def test_load_tool_schema_merges_tooltip_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            FIELD_A:
              default: ""
              tooltip: "Explains FIELD_A."
        """), encoding="utf-8")

    Antiquarian._load_tool_schema(tmp_path)

    assert Antiquarian.TOOLTIP_DESCRIPTIONS["FIELD_A"] == "Explains FIELD_A."


def test_load_tool_schema_merges_widget_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            LEVEL:
              default: "1"
              widget: segmented
              options: [["0", "Low"], ["1", "Medium"], ["2", "High"]]
            AMOUNT:
              default: "0.4"
              widget: slider
              min: 0
              max: 5
              step: 0.1
              suffix: "s"
        """), encoding="utf-8")

    Antiquarian._load_tool_schema(tmp_path)

    assert Antiquarian.FIELD_WIDGETS["LEVEL"] == {
        "type": "segmented",
        "options": [("0", "Low"), ("1", "Medium"), ("2", "High")],
    }
    assert Antiquarian.FIELD_WIDGETS["AMOUNT"] == {
        "type": "slider", "min": 0, "max": 5, "step": 0.1, "suffix": "s",
    }
    assert isinstance(Antiquarian.FIELD_WIDGETS["AMOUNT"]["min"], int)
    assert isinstance(Antiquarian.FIELD_WIDGETS["AMOUNT"]["step"], float)


def test_load_tool_schema_merges_picker_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            OUT_FILE:
              default: ""
              picker:
                kind: save
                base_dir_key: "__PROGRAM_DIR__"
                defaultextension: ".ged"
                filetypes: [["GEDCOM files", "*.ged"], ["All files", "*.*"]]
        """), encoding="utf-8")

    Antiquarian._load_tool_schema(tmp_path)

    assert Antiquarian.PATH_PICKER_FIELDS["OUT_FILE"] == {
        "kind": "save",
        "base_dir_key": "__PROGRAM_DIR__",
        "defaultextension": ".ged",
        "filetypes": [("GEDCOM files", "*.ged"), ("All files", "*.*")],
    }


def test_load_tool_schema_merges_label_overrides_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            SOME_FIELD:
              default: ""
        label_overrides:
          SOME_FIELD: "A Nicer Label"
        """), encoding="utf-8")

    Antiquarian._load_tool_schema(tmp_path)

    assert Antiquarian.CUSTOM_LABELS["SOME_FIELD"] == "A Nicer Label"


def test_load_tool_schema_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        Antiquarian._load_tool_schema(tmp_path)


def test_load_tool_schema_malformed_yaml_raises_runtime_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text("sections: [this is not: valid: yaml", encoding="utf-8")

    with pytest.raises(RuntimeError):
        Antiquarian._load_tool_schema(tmp_path)


def test_load_tool_schema_missing_sections_key_raises_value_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text("foo: bar\n", encoding="utf-8")

    with pytest.raises(ValueError):
        Antiquarian._load_tool_schema(tmp_path)


def test_load_tool_schema_section_not_a_mapping_raises_value_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One: ["not", "a", "mapping"]
        """), encoding="utf-8")

    with pytest.raises(ValueError):
        Antiquarian._load_tool_schema(tmp_path)


def test_load_tool_schema_field_missing_default_raises_value_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            FIELD_A:
              tooltip: "no default here"
        """), encoding="utf-8")

    with pytest.raises(ValueError):
        Antiquarian._load_tool_schema(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_load_tool_schema.py -v`
Expected: every test FAILs with `AttributeError: module 'Antiquarian' has no attribute '_load_tool_schema'`.

- [ ] **Step 3: Add `_load_tool_schema` to `Antiquarian.py`**

Insert this immediately after the `FIELD_WIDGETS = {...}` dict's closing `}` (currently line 435), before the `# ==========================================` / `# CUSTOM WIDGET CLASSES` comment block (currently line 438):

```python

# ==========================================
# PER-TOOL SETTINGS SCHEMA LOADER
# ==========================================
def _load_tool_schema(tool_dir: Path) -> Dict[str, Dict[str, str]]:
    """Loads one tool's settings_schema.yaml, returning the same {section: {key: default}}
    shape the hardcoded *_VARS dict literals used to provide directly. As a side effect,
    merges this tool's tooltips/widgets/pickers/label-overrides into the shared
    module-level dicts _build_form_ui already reads from - so nothing downstream of this
    call needs to know settings moved from a Python literal to a YAML file. Fails loudly:
    this is a single-user desktop tool, so a missing or malformed schema should stop
    startup with a message naming the file, not silently render an empty or partial form."""
    schema_path = tool_dir / "settings_schema.yaml"
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing settings schema: {schema_path}")

    try:
        raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise RuntimeError(f"Malformed YAML in {schema_path}: {e}") from e

    if not isinstance(raw, dict) or "sections" not in raw:
        raise ValueError(f"{schema_path} is missing its top-level 'sections' key")

    result: Dict[str, Dict[str, str]] = {}
    for section, fields in raw["sections"].items():
        if not isinstance(fields, dict):
            raise ValueError(f"{schema_path}: section '{section}' is not a mapping")
        result[section] = {}
        for field, spec in fields.items():
            if not isinstance(spec, dict) or "default" not in spec:
                raise ValueError(f"{schema_path}: field '{section}.{field}' is missing a 'default'")
            result[section][field] = str(spec["default"])

            if "tooltip" in spec:
                TOOLTIP_DESCRIPTIONS[field] = spec["tooltip"]

            if "widget" in spec:
                widget_spec = {"type": spec["widget"]}
                if "options" in spec:
                    widget_spec["options"] = [tuple(opt) for opt in spec["options"]]
                for extra_key in ("min", "max", "step", "suffix"):
                    if extra_key in spec:
                        widget_spec[extra_key] = spec[extra_key]
                FIELD_WIDGETS[field] = widget_spec

            if "picker" in spec:
                picker_spec = dict(spec["picker"])
                if "filetypes" in picker_spec:
                    picker_spec["filetypes"] = [tuple(ft) for ft in picker_spec["filetypes"]]
                PATH_PICKER_FIELDS[field] = picker_spec

    for field, label in (raw.get("label_overrides") or {}).items():
        CUSTOM_LABELS[field] = label

    return result

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_load_tool_schema.py -v`
Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add Antiquarian.py tests/test_load_tool_schema.py
git commit -m "Add generic per-tool settings schema loader"
```

---

### Task 2: Migrate Archivist to `settings_schema.yaml`

This is the first tool migrated, so it also performs the one-time relocation this architecture requires: `TOOLTIP_DESCRIPTIONS`/`CUSTOM_LABELS`/the sentinel and filetypes constants/`PATH_PICKER_FIELDS`/`FIELD_WIDGETS`/`_load_tool_schema` must sit BEFORE `ARCHIVIST_VARS` in the file, since `_load_tool_schema` mutates those dicts as a side effect the moment `ARCHIVIST_VARS = _load_tool_schema(...)` runs — and Python resolves a function body's global names at call time, not def time, so those globals must already exist by then. Also fixes the confirmed Archivist audit gaps: `TRANSCRIPTION_HEADER`, `TRANSLATION_HEADER`, `ROLE_CLERGY`, `CLERGY_HONORIFIC`, `ROLE_DEFAULT_WITNESS` (read by `Archivist.py` lines 252-256, defaults `"Citation Text:"`/`"Citation Details:"`/`"Priest"`/`"Father"`/`"Witness"`) and `ENUMERATION_DISTRICT`, `FILM_NUMBER`, `ROLL_NUMBER` (read by `Archivist.py` lines 197-199, all default `""`) were missing from the UI entirely.

**Files:**
- Create: `Archivist/settings_schema.yaml`
- Modify: `Antiquarian.py`
- Test: `tests/test_antiquarian_settings_migration.py` (new file, this task adds its first test)

**Interfaces:**
- Consumes: `_load_tool_schema(tool_dir: Path) -> Dict[str, Dict[str, str]]` from Task 1.
- Produces: `ARCHIVIST_VARS` module-level name now holds `_load_tool_schema(BASE_DIR / "Archivist")`'s return value instead of a literal — same shape, same consumers (`_build_tab_archivist` reads it via `_build_form_ui(frame, ARCHIVIST_VARS)`, no changes needed there).

- [ ] **Step 1: Write the failing migration test**

Create `tests/test_antiquarian_settings_migration.py`:

```python
from pathlib import Path

import Antiquarian

BASE_DIR = Path(__file__).resolve().parent.parent


def test_archivist_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Archivist")

    assert result == {
        "Which JSON to Build From": {"JSON_FILE": ""},
        "Location Overrides": {
            "STATE": "", "COUNTY": "", "TOWNSHIP": "",
            "ENUMERATION_DISTRICT": "", "FILM_NUMBER": "", "ROLL_NUMBER": "",
        },
        "Family Inference Tuning": {
            "MIN_MARRIAGE_AGE": "12", "MAX_SPOUSE_AGE_GAP": "25",
            "HUSBAND_CHILD_AGE_GAP_MIN": "14", "HUSBAND_CHILD_AGE_GAP_MAX": "60",
            "WIFE_CHILD_AGE_GAP_MIN": "12", "WIFE_CHILD_AGE_GAP_MAX": "50",
        },
        "Citation & Role Vocabulary": {
            "TRANSCRIPTION_HEADER": "Citation Text:", "TRANSLATION_HEADER": "Citation Details:",
            "ROLE_CLERGY": "Priest", "CLERGY_HONORIFIC": "Father", "ROLE_DEFAULT_WITNESS": "Witness",
        },
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_antiquarian_settings_migration.py -v`
Expected: FAIL with `FileNotFoundError` (no `Archivist/settings_schema.yaml` yet).

- [ ] **Step 3: Create `Archivist/settings_schema.yaml`**

```yaml
sections:
  Which JSON to Build From:
    JSON_FILE:
      default: ""
      tooltip: "Only needed to build from a specific JSON file Voyageur already gathered. Leave blank to automatically use the most recently created JSON file in your JSON folder."
      picker:
        kind: open
        base_dir_key: "JSON_DIR"
        filetypes: [["JSON files", "*.json"], ["All files", "*.*"]]
  Location Overrides:
    STATE:
      default: ""
      tooltip: "Leave blank to use the State Voyageur already gathered per-page from the JSON file. Only fill this in to force the same State on every record."
    COUNTY:
      default: ""
      tooltip: "Leave blank to use the County Voyageur already gathered per-page from the JSON file. Only fill this in to force the same County on every record."
    TOWNSHIP:
      default: ""
      tooltip: "Leave blank to use the Township/City Voyageur already gathered per-page from the JSON file. Only fill this in to force the same Township on every record."
    ENUMERATION_DISTRICT:
      default: ""
      tooltip: "Census-specific enumeration district identifier. Only fill this in to force the same district on every record; otherwise Archivist reads it per-record from the JSON."
    FILM_NUMBER:
      default: ""
      tooltip: "Microfilm/FHL film number to force on every record's citation, overriding whatever the source data provides per-record."
    ROLL_NUMBER:
      default: ""
      tooltip: "NARA roll number to force on every record's citation, overriding whatever the source data provides per-record."
  Family Inference Tuning:
    MIN_MARRIAGE_AGE:
      default: "12"
      tooltip: "The youngest plausible age someone could be married (used to group families correctly)."
      widget: slider
      min: 0
      max: 30
      step: 1
    MAX_SPOUSE_AGE_GAP:
      default: "25"
      tooltip: "The largest age gap allowed between a husband and wife before the AI assumes they are not married."
      widget: slider
      min: 0
      max: 50
      step: 1
    HUSBAND_CHILD_AGE_GAP_MIN:
      default: "14"
      tooltip: "The minimum plausible age difference between a father and his child."
      widget: slider
      min: 0
      max: 30
      step: 1
    HUSBAND_CHILD_AGE_GAP_MAX:
      default: "60"
      tooltip: "The maximum plausible age difference between a father and his child."
      widget: slider
      min: 30
      max: 90
      step: 1
    WIFE_CHILD_AGE_GAP_MIN:
      default: "12"
      tooltip: "The minimum plausible age difference between a mother and her child."
      widget: slider
      min: 0
      max: 30
      step: 1
    WIFE_CHILD_AGE_GAP_MAX:
      default: "50"
      tooltip: "The maximum plausible age difference between a mother and her child."
      widget: slider
      min: 20
      max: 70
      step: 1
  Citation & Role Vocabulary:
    TRANSCRIPTION_HEADER:
      default: "Citation Text:"
      tooltip: "The label prefixed to the transcribed original-language text inside generated source citations."
    TRANSLATION_HEADER:
      default: "Citation Details:"
      tooltip: "The label prefixed to the English translation/details text inside generated source citations."
    ROLE_CLERGY:
      default: "Priest"
      tooltip: "The role label used for the officiating clergy member in generated records."
    CLERGY_HONORIFIC:
      default: "Father"
      tooltip: "The honorific prefixed to a clergy member's name (e.g., 'Father')."
    ROLE_DEFAULT_WITNESS:
      default: "Witness"
      tooltip: "The role label used for a witness when no more specific role is given."
label_overrides:
  JSON_FILE: "Downloaded JSON File Name"
```

- [ ] **Step 4: Relocate the four shared dicts (and their supporting constants) to sit before `ARCHIVIST_VARS`, trimmed of Archivist's own entries**

In `Antiquarian.py`, cut the entire block starting at `# ==========================================` / `# TOOLTIP DESCRIPTIONS` (currently line 172) through the end of the `_load_tool_schema` function added in Task 1 (the blank line right after its closing `return result`) — this is everything currently between `ENV_TARGETS = [...]` and the `# ==========================================` / `# CUSTOM WIDGET CLASSES` comment. Delete it from that location.

Paste it back in, trimmed of Archivist's own keys, immediately after `GLOBAL_VARS = {...}`'s closing `}` (currently line 90) and before `ARCHIVIST_VARS = {...}` (currently line 92):

```python

# ==========================================
# TOOLTIP DESCRIPTIONS
# ==========================================
TOOLTIP_DESCRIPTIONS = {  # Global Settings
    "PROGRAM_DIR": "Your single base Genealogy folder. Everything else, including the Antiquarian code, your "
                   "Roots Magic / Family Tree Maker databases, Media, and GEDCOM output, lives directly inside "
                   "this one folder.",
    "EXTRACTION_ENGINE": "Which backend performs the AI extraction. 'AGY CLI' shells out to the agy CLI - "
                         "covered by a Google account subscription, no per-token API cost, but needs agy installed, "
                         "on PATH, and signed in (use Test Agy Connection below). 'AI Assistant API' uses your "
                         "AI_API_KEY directly, billed per token.",
    "AGY_MODEL_NAME": "The exact AGY CLI model ID (e.g. gemini-3.1-pro-high) - always passed explicitly on "
                      "every call. agy's own default is a flash-tier model with noticeably lower OCR quality, and "
                      "shorthand values like 'pro' or 'flash' are not valid - only exact IDs from `agy models` work.",
    "AI_API_KEY": "Your personal API key from Google AI Studio. Used to read and transcribe handwritten images.",
    "MEDIA_DIR": "The base folder where your genealogy media is stored.",
    "API_BUDGET": "A safety limit for your AI costs (e.g., '20' means $20). The script stops if it spends this much.",
    "MODEL_NAME": "The AI model version you want to use (usually AI Assistant-3.1-pro-preview or AI Assistant-2.5-pro).",
    "RM_DIR": "The folder where your RootsMagic files live, relative to the Program Dir.",
    "JSON_DIR": "The folder where downloaded JSON data files are kept.",
    "GEDCOM_OUTPUT_PATH": "The folder where the finished, ready-to-import GEDCOM files will be saved.",
    "RESEARCHER": "Your name. This will be added to the GEDCOM file to give you credit as the transcriber.",
    "COST_PER_1M_INPUT": "The price Google charges per 1 million input tokens (text/images sent to the AI).",
    "COST_PER_1M_OUTPUT": "The price Google charges per 1 million output tokens (JSON/text generated by the AI).",
    "CACHE_DISCOUNT_MULTIPLIER": "The fractional discount applied to tokens loaded from context caching (e.g., 0.10 "
                                 "means 10% of standard cost).",
    "ORG_NAME": "The name of your Historical Society, Library, or personal organization to include in GEDCOM headers.",
    "ROOT_SOURCE_ID": "The master SOUR (Source) ID used in RootsMagic for the researcher credit (e.g., @S1@).",
    "REVIEW_COLOR": "The numeric RootsMagic color code to paint people who have been flagged for manual review.",

    # Archivist (Create step - Census) - CENSUS_IMAGE_DIR is a GLOBAL_VARS key despite the
    # grouping comment; it stays here forever, never migrates to Archivist/settings_schema.yaml.
    "CENSUS_IMAGE_DIR": "The subfolder name (e.g., 'Census') inside your Base Media Directory. Can also be an "
                         "absolute path."}

# ==========================================
# CUSTOM UI LABELS OVERRIDE
# ==========================================
# Add keys here if you want them to display differently than standard Title Case.
CUSTOM_LABELS = {
    "AI_API_KEY": "Google AI API Key",
    "PROGRAM_DIR": "Genealogy Root Directory",
    "RM_DIR": "RootsMagic Folder",
    "FTM_DIR": "Family Tree Maker Folder",
    "MEDIA_DIR": "Base Media Directory",
    "JSON_DIR": "JSON Download Folder",
    "CENSUS_IMAGE_DIR": "Census Image Save Folder"}

# ==========================================
# PATH & FILE PICKER FIELDS
# ==========================================
# Keys that get a "Browse..." button next to their entry, opening a native dialog instead of
# requiring the value to be typed by hand. "kind" picks the dialog: "directory" for folder
# fields, "open" for picking an existing file, "save" for naming a new/output file (lets you
# type a name that doesn't exist yet). "base_dir_key" says which folder the dialog should
# start in: another field's key (resolved against PROGRAM_DIR, same as execute_script does),
# or one of the two sentinels below.
PROGRAM_DIR_SENTINEL = "__PROGRAM_DIR__"  # Distinct from the real "PROGRAM_DIR" settings key
TOOLBOX_DIR_SENTINEL = "__TOOLBOX_DIR__"  # The Antiquarian code folder itself (BASE_DIR).

PATH_PICKER_FIELDS = {
    # Global: Directories (folders, relative to PROGRAM_DIR unless absolute)
    "PROGRAM_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL, "always_absolute": True},
    "RM_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "FTM_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "MEDIA_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "JSON_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "GEDCOM_OUTPUT_PATH": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},

    # Archivist - CENSUS_IMAGE_DIR is a GLOBAL_VARS key, stays here forever (see above).
    "CENSUS_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
}

# ==========================================
# RICHER FIELD WIDGETS (toggles/segments/sliders instead of plain text entries)
# ==========================================
# Keyed by settings key; any key not listed here keeps the default plain CTkEntry behavior.
FIELD_WIDGETS = {
    "EXTRACTION_ENGINE": {
        "type": "segmented",
        "options": [
            ("agy", "AGY CLI (subscription)"),
            ("api", "AI Assistant API (pay-per-token)"),
        ],
    },

    # Bounded numeric tuning knobs.
    "API_BUDGET": {"type": "slider", "min": 0, "max": 200, "step": 5, "suffix": "$"},
    "CACHE_DISCOUNT_MULTIPLIER": {"type": "slider", "min": 0, "max": 1, "step": 0.05},
}


# ==========================================
# PER-TOOL SETTINGS SCHEMA LOADER
# ==========================================
def _load_tool_schema(tool_dir: Path) -> Dict[str, Dict[str, str]]:
    """Loads one tool's settings_schema.yaml, returning the same {section: {key: default}}
    shape the hardcoded *_VARS dict literals used to provide directly. As a side effect,
    merges this tool's tooltips/widgets/pickers/label-overrides into the shared
    module-level dicts _build_form_ui already reads from - so nothing downstream of this
    call needs to know settings moved from a Python literal to a YAML file. Fails loudly:
    this is a single-user desktop tool, so a missing or malformed schema should stop
    startup with a message naming the file, not silently render an empty or partial form."""
    schema_path = tool_dir / "settings_schema.yaml"
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing settings schema: {schema_path}")

    try:
        raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise RuntimeError(f"Malformed YAML in {schema_path}: {e}") from e

    if not isinstance(raw, dict) or "sections" not in raw:
        raise ValueError(f"{schema_path} is missing its top-level 'sections' key")

    result: Dict[str, Dict[str, str]] = {}
    for section, fields in raw["sections"].items():
        if not isinstance(fields, dict):
            raise ValueError(f"{schema_path}: section '{section}' is not a mapping")
        result[section] = {}
        for field, spec in fields.items():
            if not isinstance(spec, dict) or "default" not in spec:
                raise ValueError(f"{schema_path}: field '{section}.{field}' is missing a 'default'")
            result[section][field] = str(spec["default"])

            if "tooltip" in spec:
                TOOLTIP_DESCRIPTIONS[field] = spec["tooltip"]

            if "widget" in spec:
                widget_spec = {"type": spec["widget"]}
                if "options" in spec:
                    widget_spec["options"] = [tuple(opt) for opt in spec["options"]]
                for extra_key in ("min", "max", "step", "suffix"):
                    if extra_key in spec:
                        widget_spec[extra_key] = spec[extra_key]
                FIELD_WIDGETS[field] = widget_spec

            if "picker" in spec:
                picker_spec = dict(spec["picker"])
                if "filetypes" in picker_spec:
                    picker_spec["filetypes"] = [tuple(ft) for ft in picker_spec["filetypes"]]
                PATH_PICKER_FIELDS[field] = picker_spec

    for field, label in (raw.get("label_overrides") or {}).items():
        CUSTOM_LABELS[field] = label

    return result

```

Note what was deliberately dropped from this relocated block versus the original: every Archivist-owned key (`JSON_FILE`, `STATE`, `COUNTY`, `TOWNSHIP`, `MIN_MARRIAGE_AGE`, `MAX_SPOUSE_AGE_GAP`, `HUSBAND_CHILD_AGE_GAP_MIN`, `HUSBAND_CHILD_AGE_GAP_MAX`, `WIFE_CHILD_AGE_GAP_MIN`, `WIFE_CHILD_AGE_GAP_MAX`) is gone from `TOOLTIP_DESCRIPTIONS`/`FIELD_WIDGETS`; `JSON_FILE` is gone from `CUSTOM_LABELS`/`PATH_PICKER_FIELDS`. Every other tool's entries (Voyageur, Paleographer, Registrar, Gazetteer, PDFix) are carried over unchanged for now — they're trimmed in their own tasks (3-7). `RMTREE_FILETYPES`/`JSON_FILETYPES`/`GED_FILETYPES`/`SHP_FILETYPES` are also carried over unchanged (still referenced by other tools' still-hardcoded `PATH_PICKER_FIELDS` entries) — do NOT paste them into this new location; leave them exactly where they currently are (lines 353-356), since Archivist's own picker no longer needs them (its `JSON_FILE` picker's `filetypes` now lives inline in the YAML).

- [ ] **Step 5: Replace the `ARCHIVIST_VARS` literal with a loader call**

Old (now sitting right after the relocated block from Step 4):

```python
ARCHIVIST_VARS = {"Which JSON to Build From": {"JSON_FILE": ""},
                  "Location Overrides": {"STATE": "", "COUNTY": "", "TOWNSHIP": ""},
                  "Family Inference Tuning": {"MIN_MARRIAGE_AGE": "12", "MAX_SPOUSE_AGE_GAP": "25",
                                              "HUSBAND_CHILD_AGE_GAP_MIN": "14", "HUSBAND_CHILD_AGE_GAP_MAX": "60",
                                              "WIFE_CHILD_AGE_GAP_MIN": "12", "WIFE_CHILD_AGE_GAP_MAX": "50"}}
```

New:

```python
ARCHIVIST_VARS = _load_tool_schema(BASE_DIR / "Archivist")
```

- [ ] **Step 6: Delete the now-empty original location's leftover comment header**

Where the `# TOOLTIP DESCRIPTIONS` block used to sit (originally right after `ENV_TARGETS`), only the `# ==========================================` / `# CUSTOM WIDGET CLASSES` comment (originally line 438) and the `class ToolTip` definition that follows it should remain — confirm no orphaned blank block or duplicate comment header is left behind between `ENV_TARGETS = [...]` and that class.

- [ ] **Step 7: Run the app's existing test to confirm nothing broke**

Run: `pytest tests/test_antiquarian_paleographer_gating.py -v`
Expected: both tests still PASS (Paleographer isn't migrated yet in this task, so this is a regression check on the reorder itself — if `Antiquarian.py` fails to import, both tests error immediately).

- [ ] **Step 8: Run the migration test to verify it passes**

Run: `pytest tests/test_antiquarian_settings_migration.py -v`
Expected: `test_archivist_schema_matches_expected_shape` PASSES.

- [ ] **Step 9: Manual click-through**

Launch `python Antiquarian.py`, open the Archivist tab, confirm all four sections render (including the new "Citation & Role Vocabulary" section with its five fields), confirm the age-gap sliders still work, confirm "Downloaded JSON File Name" still shows as `JSON_FILE`'s label with its Browse button, save, and confirm `Archivist/.env` gets the new keys with their defaults.

- [ ] **Step 10: Commit**

```bash
git add Antiquarian.py Archivist/settings_schema.yaml tests/test_antiquarian_settings_migration.py
git commit -m "Migrate Archivist settings to settings_schema.yaml, add missing citation/location fields"
```

---

### Task 3: Migrate Voyageur to `settings_schema.yaml`

Fixes the confirmed `LAC_HARVEST_ARCHIVAL_NUMBER` bug — `LAC.py` line 50 actually reads `LAC_ARCHIVAL_NUMBER` (no "HARVEST"), so the old UI field was a permanent no-op. Adds `LAC_CHECKPOINT_DIR` (`LAC.py` line 48, default `"Working/LAC"`), `LAC_CDP_PORT` (`LAC.py` line 51, default `"9222"`, matching `lac_client.DEFAULT_CDP_PORT`), and `LAC_MAX_WORKERS` (`LAC.py` line 649, default `"1"`).

**Files:**
- Create: `Voyageur/settings_schema.yaml`
- Modify: `Antiquarian.py`
- Modify: `tests/test_antiquarian_settings_migration.py`

**Interfaces:**
- Consumes: `_load_tool_schema` (Task 1).
- Produces: `VOYAGEUR_VARS` now holds loader output.

- [ ] **Step 1: Write the failing migration test**

Append to `tests/test_antiquarian_settings_migration.py`:

```python
def test_voyageur_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Voyageur")

    assert result == {
        "Gather Settings": {"VOYAGEUR_SOURCE": ""},
        "Ancestry": {"A_URL": ""},
        "FamilySearch": {"FS_URL": ""},
        "LAC": {
            "LAC_URL": "", "LAC_IMAGE_DIR": "LAC",
            "LAC_HARVEST_VOLUME": "", "LAC_ARCHIVAL_NUMBER": "RG15",
            "LAC_COOKIE_FILE": "Working/LAC/lac_cookies.txt",
            "LAC_CHECKPOINT_DIR": "Working/LAC", "LAC_CDP_PORT": "9222", "LAC_MAX_WORKERS": "1",
        },
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_antiquarian_settings_migration.py::test_voyageur_schema_matches_expected_shape -v`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Create `Voyageur/settings_schema.yaml`**

```yaml
sections:
  Gather Settings:
    VOYAGEUR_SOURCE:
      default: ""
      tooltip: "Which repository to gather from. Adding a new one is a new Voyageur sub-script, nothing else changes here."
      label_override: "Gather From"
  Ancestry:
    A_URL:
      default: ""
      tooltip: "The web address (URL) of the specific Ancestry.com census page you want to gather."
  FamilySearch:
    FS_URL:
      default: ""
      tooltip: "The web address (URL) of the specific FamilySearch record page you want to gather."
  LAC:
    LAC_URL:
      default: ""
      tooltip: "Paste the complete Heritage Canadiana link (e.g., https://heritage.canadiana.ca/iiif/oocihm.lac_reel_c2170/)."
    LAC_IMAGE_DIR:
      default: "LAC"
      tooltip: "The subfolder name (e.g., 'LAC') inside your Base Media Directory. A subfolder per roll number is created automatically inside it. Can also be an absolute path."
      picker:
        kind: directory
        base_dir_key: "MEDIA_DIR"
    LAC_HARVEST_VOLUME:
      default: ""
      tooltip: "Volume number at Library and Archives Canada to harvest (e.g. '1320' or '1325-1330')."
    LAC_ARCHIVAL_NUMBER:
      default: "RG15"
      tooltip: "Archival series prefix used when harvesting an LAC volume (default 'RG15')."
    LAC_COOKIE_FILE:
      default: "Working/LAC/lac_cookies.txt"
      tooltip: "Fallback text file for LAC search session cookies."
    LAC_CHECKPOINT_DIR:
      default: "Working/LAC"
      tooltip: "Folder where LAC harvest progress checkpoints are saved, so an interrupted harvest can resume without re-downloading."
    LAC_CDP_PORT:
      default: "9222"
      tooltip: "Chrome DevTools Protocol port LAC connects to when loading browser session cookies (default 9222)."
    LAC_MAX_WORKERS:
      default: "1"
      tooltip: "Number of concurrent download workers used when harvesting an LAC volume (default 1)."
```

Note: `label_override` (singular, per-field) is not a key this plan's loader reads — remove it, this was a drafting slip. Use the top-level `label_overrides:` block instead, matching every other tool's YAML in this plan:

```yaml
sections:
  Gather Settings:
    VOYAGEUR_SOURCE:
      default: ""
      tooltip: "Which repository to gather from. Adding a new one is a new Voyageur sub-script, nothing else changes here."
  Ancestry:
    A_URL:
      default: ""
      tooltip: "The web address (URL) of the specific Ancestry.com census page you want to gather."
  FamilySearch:
    FS_URL:
      default: ""
      tooltip: "The web address (URL) of the specific FamilySearch record page you want to gather."
  LAC:
    LAC_URL:
      default: ""
      tooltip: "Paste the complete Heritage Canadiana link (e.g., https://heritage.canadiana.ca/iiif/oocihm.lac_reel_c2170/)."
    LAC_IMAGE_DIR:
      default: "LAC"
      tooltip: "The subfolder name (e.g., 'LAC') inside your Base Media Directory. A subfolder per roll number is created automatically inside it. Can also be an absolute path."
      picker:
        kind: directory
        base_dir_key: "MEDIA_DIR"
    LAC_HARVEST_VOLUME:
      default: ""
      tooltip: "Volume number at Library and Archives Canada to harvest (e.g. '1320' or '1325-1330')."
    LAC_ARCHIVAL_NUMBER:
      default: "RG15"
      tooltip: "Archival series prefix used when harvesting an LAC volume (default 'RG15')."
    LAC_COOKIE_FILE:
      default: "Working/LAC/lac_cookies.txt"
      tooltip: "Fallback text file for LAC search session cookies."
    LAC_CHECKPOINT_DIR:
      default: "Working/LAC"
      tooltip: "Folder where LAC harvest progress checkpoints are saved, so an interrupted harvest can resume without re-downloading."
    LAC_CDP_PORT:
      default: "9222"
      tooltip: "Chrome DevTools Protocol port LAC connects to when loading browser session cookies (default 9222)."
    LAC_MAX_WORKERS:
      default: "1"
      tooltip: "Number of concurrent download workers used when harvesting an LAC volume (default 1)."
label_overrides:
  VOYAGEUR_SOURCE: "Gather From"
  A_URL: "Ancestry Census URL"
  LAC_URL: "Heritage Canadiana URL"
  FS_URL: "FamilySearch Record URL"
```

- [ ] **Step 4: Trim Voyageur's entries out of the four shared dicts in `Antiquarian.py`**

In `TOOLTIP_DESCRIPTIONS`, delete these entries (the `# LAC & Scrip Enrichment` group's LAC-only lines, plus the `# Voyageur (Gather step)` group):

```python
    # LAC & Scrip Enrichment
    "LAC_HARVEST_VOLUME": "Volume number at Library and Archives Canada to harvest (e.g. '1320' or '1325-1330').",
    "LAC_HARVEST_ARCHIVAL_NUMBER": "Archival series prefix used when harvesting an LAC volume (default 'RG15').",
    "LAC_COOKIE_FILE": "Fallback text file for LAC search session cookies.",
```

and:

```python
    # Voyageur (Gather step)
    "VOYAGEUR_SOURCE": "Which repository to gather from. Adding a new one is a new Voyageur sub-script, nothing "
                       "else changes here.",
    "A_URL": "The web address (URL) of the specific Ancestry.com census page you want to gather.",
    "FS_URL": "The web address (URL) of the specific FamilySearch record page you want to gather.",
    "LAC_URL": "Paste the complete Heritage Canadiana link (e.g., "
                "https://heritage.canadiana.ca/iiif/oocihm.lac_reel_c2170/).",
    "LAC_IMAGE_DIR": "The subfolder name (e.g., 'LAC') inside your Base Media Directory. A subfolder per roll number "
                      "is created automatically inside it. Can also be an absolute path.",
```

(Leave the `# LAC & Scrip Enrichment` group's Scrip-only lines — `SCRIP_DELAY_SECONDS`, `SCRIP_ENRICH_LIMIT`, `SCRIP_PARTITION_OUTPUT_DIR` — in place; they're Paleographer-owned and trimmed in Task 4.)

In `CUSTOM_LABELS`, delete:

```python
    "A_URL": "Ancestry Census URL",
    "LAC_URL": "Heritage Canadiana URL",
    "FS_URL": "FamilySearch Record URL",
    "VOYAGEUR_SOURCE": "Gather From",
```

In `PATH_PICKER_FIELDS`, delete:

```python
    # Voyageur
    "LAC_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},

```

`FIELD_WIDGETS` has no Voyageur-owned entries — no change needed there.

- [ ] **Step 5: Replace the `VOYAGEUR_VARS` literal with a loader call**

Old:

```python
VOYAGEUR_VARS = {"Gather Settings": {"VOYAGEUR_SOURCE": ""},
                 "Ancestry": {"A_URL": ""},
                 "FamilySearch": {"FS_URL": ""},
                 "LAC": {"LAC_URL": "", "LAC_IMAGE_DIR": "LAC",
                         "LAC_HARVEST_VOLUME": "", "LAC_HARVEST_ARCHIVAL_NUMBER": "RG15",
                         "LAC_COOKIE_FILE": "Working/LAC/lac_cookies.txt"}}
```

New:

```python
VOYAGEUR_VARS = _load_tool_schema(BASE_DIR / "Voyageur")
```

(`VOYAGEUR_SOURCES = [("A", "Ancestry"), ("FS", "FamilySearch"), ("LAC", "LAC")]`, the line immediately above, is unrelated dropdown-population data — leave it exactly as-is.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_antiquarian_settings_migration.py tests/test_antiquarian_paleographer_gating.py -v`
Expected: all PASS.

- [ ] **Step 7: Manual click-through**

Launch `python Antiquarian.py`, open the Voyageur tab, confirm the LAC section shows all 8 fields including the 3 new ones, save, and confirm `Voyageur/.env` now has `LAC_ARCHIVAL_NUMBER` (not `LAC_HARVEST_ARCHIVAL_NUMBER`) plus the three new keys.

- [ ] **Step 8: Commit**

```bash
git add Antiquarian.py Voyageur/settings_schema.yaml tests/test_antiquarian_settings_migration.py
git commit -m "Migrate Voyageur settings to settings_schema.yaml, fix LAC_ARCHIVAL_NUMBER rename bug"
```

---

### Task 4: Migrate Paleographer to `settings_schema.yaml` + fix stale help text

Fixes the confirmed gap — `AGY_CLI_BIN` (`Extract.py` line 272, default `"agy"`, matching `agy_client.DEFAULT_CLI_BIN`) and `AGY_TIMEOUT_SECONDS` (`Extract.py` line 273, default `"240"`, matching `agy_client.DEFAULT_TIMEOUT_SECONDS`) were missing from the UI. These are read by the shared `Extract.py` module used by BOTH the Parish and Scrip record-type flows, so the new "AGY CLI" section must be visible for both — meaning `Parish.pmt` and `Scrip.pmt`'s own `settings_sections:` front-matter lists (which `_get_pmt_settings_sections` uses to filter which `PALEOGRAPHER_VARS` sections show per record type) both need the new section name added, or the fields would be silently invisible in the GUI for every record type. Also fixes the confirmed stale help text: it currently only mentions "Enrich Metadata"/"Partition Collections" but the tab has a third button, "Resolve Names" (`Antiquarian.py` line 1584-1587), that the help text never mentions.

**Files:**
- Create: `Paleographer/settings_schema.yaml`
- Modify: `Antiquarian.py` (settings migration + help text fix)
- Modify: `Paleographer/prompts/Parish.pmt`, `Paleographer/prompts/Scrip.pmt`
- Modify: `tests/test_antiquarian_settings_migration.py`

**Interfaces:**
- Consumes: `_load_tool_schema` (Task 1).
- Produces: `PALEOGRAPHER_VARS` now holds loader output.

- [ ] **Step 1: Write the failing migration test**

Append to `tests/test_antiquarian_settings_migration.py`:

```python
def test_paleographer_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Paleographer")

    assert result == {
        "AGY CLI": {"AGY_CLI_BIN": "agy", "AGY_TIMEOUT_SECONDS": "240"},
        "Data & Directories": {
            "PALEOGRAPHER_RECORD_TYPE": "", "CHURCH_IMAGE_DIR": "Parish",
            "CHURCH_GEDCOM_NAME": "Parish.ged", "CHURCH_MASTER_DB_NAME": "parish_register.json",
            "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "2",
        },
        "Parish Information": {
            "PARISH_NAME": "St. Generic Catholic Church",
            "PARISH_NAME_SHORT": "St. Generic Parish, Anytown, ST",
            "PARISH_CITY": "Anytown", "PARISH_STATE": "State",
            "PARISH_FILE_NAME": "Parish_Anytown",
            "DEFAULT_EVENT_LOCATION": "Anytown, Any County, State, USA",
        },
        "Register Information": {
            "REGISTER_SOURCE_ID": "1",
            "REGISTER_NAME": "Baptisms, marriages and burials, 1850-1900",
            "VOLUME_TITLE": "Volume 1", "VOLUME_NUM": "1",
        },
        "Church Citation (Source)": {
            "CHURCH_CALL_NUMBER": "Call #1234567",
            "CHURCH_COLLECTION_URL": "https://www.familysearch.org/search/collection",
            "CHURCH_COLLECTION_NAME": "Generic Historical Collection",
            "CHURCH_REPOSITORY": "FamilySearch.org", "CHURCH_REPOSITORY_LOC": "Granite Mountain, UT",
        },
        "Scrip Information": {
            "SCRIP_IMAGE_DIR": "Scrip", "SCRIP_MASTER_DB_NAME": "scrip_records.json",
            "SCRIP_COLLECTION_NAME": "Library and Archives Canada, RG15 Scrip Records",
            "SCRIP_DISTRICT": "", "SCRIP_DELAY_SECONDS": "0.4",
            "SCRIP_ENRICH_LIMIT": "", "SCRIP_PARTITION_OUTPUT_DIR": "",
        },
    }


def test_paleographer_help_text_mentions_resolve_names():
    assert "Resolve Names" in Antiquarian.Antiquarian.__dict__ or True  # placeholder removed below
```

Remove that last placeholder test immediately — it isn't real. Replace it with an actual assertion against the constructed app's `help_texts` dict:

```python
def test_paleographer_help_text_mentions_resolve_names():
    import customtkinter as ctk
    root = Antiquarian.Antiquarian()
    try:
        assert "Resolve Names" in root.help_texts["Paleographer"]
    finally:
        root.destroy()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_antiquarian_settings_migration.py::test_paleographer_schema_matches_expected_shape tests/test_antiquarian_settings_migration.py::test_paleographer_help_text_mentions_resolve_names -v`
Expected: the schema test FAILs with `FileNotFoundError`; the help-text test FAILs with `AssertionError` (current text only mentions "Enrich Metadata"/"Partition Collections").

- [ ] **Step 3: Create `Paleographer/settings_schema.yaml`**

```yaml
sections:
  AGY CLI:
    AGY_CLI_BIN:
      default: "agy"
      tooltip: "The command/path used to invoke the AGY CLI (agy). Leave as 'agy' unless it's not on your PATH."
    AGY_TIMEOUT_SECONDS:
      default: "240"
      tooltip: "How many seconds to wait for a single agy transcription call before giving up (default 240)."
  Data & Directories:
    PALEOGRAPHER_RECORD_TYPE:
      default: ""
      tooltip: "Which record type (from Paleographer/prompts) to transcribe. Leave blank to use the default, Parish.pmt."
    CHURCH_IMAGE_DIR:
      default: "Parish"
      tooltip: "The subfolder name (e.g., 'Parish') inside your Base Media Directory. Can also be an absolute path."
      picker:
        kind: directory
        base_dir_key: "MEDIA_DIR"
    CHURCH_GEDCOM_NAME:
      default: "Parish.ged"
      tooltip: "The filename for the generated GEDCOM file."
      picker:
        kind: save
        base_dir_key: "GEDCOM_OUTPUT_PATH"
        filetypes: [["GEDCOM files", "*.ged"], ["All files", "*.*"]]
        defaultextension: ".ged"
    CHURCH_MASTER_DB_NAME:
      default: "parish_register.json"
      tooltip: "The filename for the JSON database storing the extracted records."
      picker:
        kind: save
        base_dir_key: "JSON_DIR"
        filetypes: [["JSON files", "*.json"], ["All files", "*.*"]]
        defaultextension: ".json"
    PALEOGRAPHER_PDF_COMPRESSION_LEVEL:
      default: "2"
      tooltip: "How aggressively PDFix's lossless structural optimization (garbage collection + stream deflate) runs on a scanned PDF before it's uploaded to the AI: 0=low, 1=medium, 2=high (recommended). This never touches embedded image resolution/DPI, so transcription quality is unaffected at any level."
      widget: segmented
      options: [["0", "Low"], ["1", "Medium"], ["2", "High"]]
  Parish Information:
    PARISH_NAME:
      default: "St. Generic Catholic Church"
      tooltip: "The full historical name of the church (e.g., St. Joseph Catholic Church)."
    PARISH_NAME_SHORT:
      default: "St. Generic Parish, Anytown, ST"
      tooltip: "A shortened name for the parish, used in file titles."
    PARISH_CITY:
      default: "Anytown"
      tooltip: "The city where the parish is located."
    PARISH_STATE:
      default: "State"
      tooltip: "The state or province where the parish is located."
    PARISH_FILE_NAME:
      default: "Parish_Anytown"
      tooltip: "The base filename used for parish exports."
    DEFAULT_EVENT_LOCATION:
      default: "Anytown, Any County, State, USA"
      tooltip: "The default location assigned to events if none is specified."
  Register Information:
    REGISTER_SOURCE_ID:
      default: "1"
      tooltip: "The source ID assigned to this specific register volume."
    REGISTER_NAME:
      default: "Baptisms, marriages and burials, 1850-1900"
      tooltip: "What this register contains and covers (e.g., 'Baptisms, marriages and burials, 1850-1900'). Used throughout the generated source citations, distinct from Volume Title."
    VOLUME_TITLE:
      default: "Volume 1"
      tooltip: "This specific volume/book's own title or label (e.g., 'Volume 1'). Used alongside Register Name in the generated source citations."
    VOLUME_NUM:
      default: "1"
      tooltip: "The volume number of the register."
  Church Citation (Source):
    CHURCH_CALL_NUMBER:
      default: "Call #1234567"
      tooltip: "The call number for the church register collection."
    CHURCH_COLLECTION_URL:
      default: "https://www.familysearch.org/search/collection"
      tooltip: "A link back to FamilySearch or Ancestry where you found these images."
    CHURCH_COLLECTION_NAME:
      default: "Generic Historical Collection"
      tooltip: "The name of the specific collection these images belong to (e.g., 'Quebec, Catholic Parish Registers'). Do not include the repository/website name here, that's set separately below."
    CHURCH_REPOSITORY:
      default: "FamilySearch.org"
      tooltip: "The archive or website hosting this collection (e.g., FamilySearch.org, Library and Archives Canada, Ancestry.com)."
    CHURCH_REPOSITORY_LOC:
      default: "Granite Mountain, UT"
      tooltip: "The physical location or address of that repository, used in the citation (e.g., 'Granite Mountain, UT' for FamilySearch, 'Ottawa, ON' for LAC)."
  Scrip Information:
    SCRIP_IMAGE_DIR:
      default: "Scrip"
      tooltip: "The subfolder name (e.g., 'Scrip') inside your Base Media Directory. Can also be an absolute path."
      picker:
        kind: directory
        base_dir_key: "MEDIA_DIR"
    SCRIP_MASTER_DB_NAME:
      default: "scrip_records.json"
      tooltip: "The filename for the JSON database storing the extracted scrip records."
      picker:
        kind: save
        base_dir_key: "JSON_DIR"
        filetypes: [["JSON files", "*.json"], ["All files", "*.*"]]
        defaultextension: ".json"
    SCRIP_COLLECTION_NAME:
      default: "Library and Archives Canada, RG15 Scrip Records"
      tooltip: "The name of the archival collection these scrip files came from."
    SCRIP_DISTRICT:
      default: ""
      tooltip: "The scrip district or region this batch of applications belongs to, if known."
    SCRIP_DELAY_SECONDS:
      default: "0.4"
      tooltip: "Pacing delay in seconds between LAC API requests during metadata enrichment (default: 0.4s)."
      widget: slider
      min: 0
      max: 5
      step: 0.1
      suffix: "s"
    SCRIP_ENRICH_LIMIT:
      default: ""
      tooltip: "Optional maximum number of records to process during enrichment (blank for all)."
    SCRIP_PARTITION_OUTPUT_DIR:
      default: ""
      tooltip: "Directory where partitioned collection JSON files are saved (default: 'partitioned' subfolder)."
      picker:
        kind: directory
        base_dir_key: "JSON_DIR"
```

- [ ] **Step 4: Add "AGY CLI" to both `.pmt` files' `settings_sections:` lists**

In `Paleographer/prompts/Parish.pmt`, change:

```yaml
settings_sections:
  - "Data & Directories"
  - "Parish Information"
  - "Register Information"
  - "Church Citation (Source)"
```

to:

```yaml
settings_sections:
  - "AGY CLI"
  - "Data & Directories"
  - "Parish Information"
  - "Register Information"
  - "Church Citation (Source)"
```

In `Paleographer/prompts/Scrip.pmt`, change:

```yaml
settings_sections:
  - "Scrip Information"
```

to:

```yaml
settings_sections:
  - "AGY CLI"
  - "Scrip Information"
```

- [ ] **Step 5: Trim Paleographer's entries out of the four shared dicts in `Antiquarian.py`**

In `TOOLTIP_DESCRIPTIONS`, delete the Scrip-only lines from the `# LAC & Scrip Enrichment` group:

```python
    "SCRIP_DELAY_SECONDS": (
        "Pacing delay in seconds between LAC API requests during metadata enrichment (default: 0.4s)."
    ),
    "SCRIP_ENRICH_LIMIT": "Optional maximum number of records to process during enrichment (blank for all).",
    "SCRIP_PARTITION_OUTPUT_DIR": (
        "Directory where partitioned collection JSON files are saved (default: 'partitioned' subfolder)."
    ),
```

(The `# LAC & Scrip Enrichment` comment header itself is now dead — delete it too, since Task 3 already removed the LAC-only lines beneath it.)

Delete the entire `# Paleographer` group:

```python
    # Paleographer
    "PALEOGRAPHER_RECORD_TYPE": "Which record type (from Paleographer/prompts) to transcribe. Leave blank to use the "
    "default, Parish.pmt.",
    "CHURCH_IMAGE_DIR": "The subfolder name (e.g., 'Parish') inside your Base Media Directory. Can also be an "
                         "absolute path.",
    "CHURCH_GEDCOM_NAME": "The filename for the generated GEDCOM file.",
    "CHURCH_MASTER_DB_NAME": "The filename for the JSON database storing the extracted records.",
    "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "How aggressively PDFix's lossless structural optimization (garbage "
                                          "collection + stream deflate) runs on a scanned PDF before it's uploaded "
                                          "to the AI: 0=low, 1=medium, 2=high (recommended). This never touches "
                                          "embedded image resolution/DPI, so transcription quality is unaffected "
                                          "at any level.",
    "PARISH_NAME": "The full historical name of the church (e.g., St. Joseph Catholic Church).",
    "PARISH_NAME_SHORT": "A shortened name for the parish, used in file titles.",
    "PARISH_CITY": "The city where the parish is located.",
    "PARISH_STATE": "The state or province where the parish is located.",
    "PARISH_FILE_NAME": "The base filename used for parish exports.",
    "DEFAULT_EVENT_LOCATION": "The default location assigned to events if none is specified.",
    "REGISTER_SOURCE_ID": "The source ID assigned to this specific register volume.",
    "REGISTER_NAME": "What this register contains and covers (e.g., 'Baptisms, marriages and burials, "
                     "1850-1900'). Used throughout the generated source citations, distinct from Volume Title.",
    "VOLUME_TITLE": "This specific volume/book's own title or label (e.g., 'Volume 1'). Used alongside "
                    "Register Name in the generated source citations.",
    "VOLUME_NUM": "The volume number of the register.",
    "CHURCH_CALL_NUMBER": "The call number for the church register collection.",
    "CHURCH_COLLECTION_URL": "A link back to FamilySearch or Ancestry where you found these images.",
    "CHURCH_COLLECTION_NAME": "The name of the specific collection these images belong to (e.g., 'Quebec, Catholic "
                              "Parish Registers'). Do not include the repository/website name here, that's set "
                              "separately below.",
    "CHURCH_REPOSITORY": "The archive or website hosting this collection (e.g., FamilySearch.org, Library and "
                         "Archives Canada, Ancestry.com).",
    "CHURCH_REPOSITORY_LOC": "The physical location or address of that repository, used in the citation (e.g., "
                             "'Granite Mountain, UT' for FamilySearch, 'Ottawa, ON' for LAC).",
    "SCRIP_IMAGE_DIR": "The subfolder name (e.g., 'Scrip') inside your Base Media Directory. Can also be an "
                       "absolute path.",
    "SCRIP_MASTER_DB_NAME": "The filename for the JSON database storing the extracted scrip records.",
    "SCRIP_COLLECTION_NAME": "The name of the archival collection these scrip files came from.",
    "SCRIP_DISTRICT": "The scrip district or region this batch of applications belongs to, if known.",

```

`CUSTOM_LABELS` has no Paleographer-owned entries — no change needed there.

In `PATH_PICKER_FIELDS`, delete:

```python
    # Paleographer
    "CHURCH_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
    "CHURCH_GEDCOM_NAME": {"kind": "save", "base_dir_key": "GEDCOM_OUTPUT_PATH", "filetypes": GED_FILETYPES,
                           "defaultextension": ".ged"},
    "CHURCH_MASTER_DB_NAME": {"kind": "save", "base_dir_key": "JSON_DIR", "filetypes": JSON_FILETYPES,
                              "defaultextension": ".json"},
    "SCRIP_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
    "SCRIP_MASTER_DB_NAME": {"kind": "save", "base_dir_key": "JSON_DIR", "filetypes": JSON_FILETYPES,
                             "defaultextension": ".json"},

```

and:

```python
    # Scrip Partition Output
    "SCRIP_PARTITION_OUTPUT_DIR": {"kind": "directory", "base_dir_key": "JSON_DIR"},
```

In `FIELD_WIDGETS`, delete:

```python
    "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": {"type": "segmented",
                                           "options": [("0", "Low"), ("1", "Medium"), ("2", "High")]},
```

and:

```python
    "SCRIP_DELAY_SECONDS": {"type": "slider", "min": 0, "max": 5, "step": 0.1, "suffix": "s"},
```

Note: `SCRIP_DELAY_SECONDS` doesn't actually appear in `FIELD_WIDGETS` today (confirmed absent from the original dict — it was rendered as a plain text entry despite having a natural slider shape). This task adds it as a real slider for the first time, via the YAML `widget: slider` spec in Step 3 — there is nothing to delete for it here; only skip this deletion sub-step.

- [ ] **Step 6: Replace the `PALEOGRAPHER_VARS` literal with a loader call**

Old (the full 6-section literal at what is currently lines 112-134):

```python
PALEOGRAPHER_VARS = {"Data & Directories": {"PALEOGRAPHER_RECORD_TYPE": "", "CHURCH_IMAGE_DIR": "Parish",
                                            "CHURCH_GEDCOM_NAME": "Parish.ged",
                                            "CHURCH_MASTER_DB_NAME": "parish_register.json",
                                            "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "2"},
                     "Parish Information": {"PARISH_NAME": "St. Generic Catholic Church",
                                            "PARISH_NAME_SHORT": "St. Generic Parish, Anytown, ST",
                                            "PARISH_CITY": "Anytown", "PARISH_STATE": "State",
                                            "PARISH_FILE_NAME": "Parish_Anytown",
                                            "DEFAULT_EVENT_LOCATION": "Anytown, Any County, State, USA"},
                     "Register Information": {"REGISTER_SOURCE_ID": "1",
                                              "REGISTER_NAME": "Baptisms, marriages and burials, 1850-1900",
                                              "VOLUME_TITLE": "Volume 1",
                                              "VOLUME_NUM": "1"},
                     "Church Citation (Source)": {"CHURCH_CALL_NUMBER": "Call #1234567",
                                                  "CHURCH_COLLECTION_URL":
                                                  "https://www.familysearch.org/search/collection",
                                                  "CHURCH_COLLECTION_NAME": "Generic Historical Collection",
                                                  "CHURCH_REPOSITORY": "FamilySearch.org",
                                                  "CHURCH_REPOSITORY_LOC": "Granite Mountain, UT"},
                     "Scrip Information": {"SCRIP_IMAGE_DIR": "Scrip", "SCRIP_MASTER_DB_NAME": "scrip_records.json",
                                           "SCRIP_COLLECTION_NAME": "Library and Archives Canada, RG15 Scrip Records",
                                           "SCRIP_DISTRICT": "", "SCRIP_DELAY_SECONDS": "0.4",
                                           "SCRIP_ENRICH_LIMIT": "", "SCRIP_PARTITION_OUTPUT_DIR": ""}}
```

New:

```python
PALEOGRAPHER_VARS = _load_tool_schema(BASE_DIR / "Paleographer")
```

- [ ] **Step 7: Fix the stale Paleographer help text**

In `self.help_texts`'s `"Paleographer"` entry (currently lines 689-704), change:

```python
                           "4. Click 'Run Analysis (API)' to transcribe. For Scrip records, use 'Enrich Metadata' "
                           "to fetch live LAC catalog metadata or 'Partition Collections' to split records into "
                           "official LAC archival series files.\n\n"
```

to:

```python
                           "4. Click 'Run Analysis (API)' to transcribe. For Scrip records, use 'Enrich Metadata' "
                           "to fetch live LAC catalog metadata, 'Partition Collections' to split records into "
                           "official LAC archival series files, or 'Resolve Names' to cross-reference and "
                           "deduplicate participant names across records.\n\n"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_antiquarian_settings_migration.py tests/test_antiquarian_paleographer_gating.py -v`
Expected: all PASS, including the two new Paleographer tests from Step 1.

- [ ] **Step 9: Manual click-through**

Launch `python Antiquarian.py`, open the Paleographer tab, switch the Record Type dropdown between `Parish.pmt` and `Scrip.pmt`, and for each confirm the "AGY CLI" section now appears alongside that type's usual sections. Click the ⓘ help icon and confirm the updated text mentions Resolve Names.

- [ ] **Step 10: Commit**

```bash
git add Antiquarian.py Paleographer/settings_schema.yaml Paleographer/prompts/Parish.pmt Paleographer/prompts/Scrip.pmt tests/test_antiquarian_settings_migration.py
git commit -m "Migrate Paleographer settings to settings_schema.yaml, add AGY_CLI_BIN/AGY_TIMEOUT_SECONDS, fix stale help text"
```

---

### Task 5: Migrate Registrar to `settings_schema.yaml`, delete dead `schema_ui_map.py`

No missing fields (all 8 already represented), but harvests `Registrar/schema_ui_map.py`'s `UI_SCHEMA_MAPPINGS` `description` text as the new tooltips (more specific than the current generic ones), then deletes that dead, unimported file.

**Files:**
- Create: `Registrar/settings_schema.yaml`
- Modify: `Antiquarian.py`
- Delete: `Registrar/schema_ui_map.py`
- Modify: `tests/test_antiquarian_settings_migration.py`

**Interfaces:**
- Consumes: `_load_tool_schema` (Task 1).
- Produces: `REGISTRAR_VARS` now holds loader output.

- [ ] **Step 1: Write the failing migration test**

Append to `tests/test_antiquarian_settings_migration.py`:

```python
def test_registrar_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Registrar")

    assert result == {
        "File Paths (Relative to RootsMagic Dir)": {"REGISTRAR_RM_DATABASE": "Your Tree.rmtree"},
        "Matching Thresholds": {
            "REGISTRAR_FUZZY_THRESHOLD": "82", "REGISTRAR_MAX_AGE_GAP": "5",
            "REGISTRAR_FUZZY_THRESHOLD_STRICT": "95", "REGISTRAR_FAMILY_MATCH_THRESHOLD": "75",
        },
        "RootsMagic UI Settings": {
            "REGISTRAR_FOLDER_NAME": "!Duplicate Review",
            "REGISTRAR_COLOR_SET": "1", "REGISTRAR_COLOR_VALUE": "27",
        },
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_antiquarian_settings_migration.py::test_registrar_schema_matches_expected_shape -v`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Create `Registrar/settings_schema.yaml`**

```yaml
sections:
  File Paths (Relative to RootsMagic Dir):
    REGISTRAR_RM_DATABASE:
      default: "Your Tree.rmtree"
      tooltip: "Path to the RootsMagic .rmtree SQLite database file"
      picker:
        kind: open
        base_dir_key: "RM_DIR"
        filetypes: [["RootsMagic files", "*.rmtree"], ["All files", "*.*"]]
  Matching Thresholds:
    REGISTRAR_FUZZY_THRESHOLD:
      default: "82"
      tooltip: "Name token set ratio cutoff score for Pass 1 matching"
      widget: slider
      min: 0
      max: 100
      step: 1
    REGISTRAR_MAX_AGE_GAP:
      default: "5"
      tooltip: "Maximum allowed birth year difference for Pass 1 matching"
      widget: slider
      min: 0
      max: 20
      step: 1
    REGISTRAR_FUZZY_THRESHOLD_STRICT:
      default: "95"
      tooltip: "Strict name token set ratio cutoff score for Pass 2 (missing birth year)"
      widget: slider
      min: 0
      max: 100
      step: 1
    REGISTRAR_FAMILY_MATCH_THRESHOLD:
      default: "75"
      tooltip: "Name similarity threshold for verifying linked relative names"
      widget: slider
      min: 0
      max: 100
      step: 1
  RootsMagic UI Settings:
    REGISTRAR_FOLDER_NAME:
      default: "!Duplicate Review"
      tooltip: "Name of the RootsMagic task folder (TagType=1) where duplicate tasks are grouped"
    REGISTRAR_COLOR_SET:
      default: "1"
      tooltip: "RootsMagic color set index (1-based index determining PersonTable.Color{N} column)"
    REGISTRAR_COLOR_VALUE:
      default: "27"
      tooltip: "Color ID assigned to flagged individuals in PersonTable (e.g. 27 = Slate)"
label_overrides:
  REGISTRAR_RM_DATABASE: "RootsMagic Database Path"
```

- [ ] **Step 4: Trim Registrar's entries out of the four shared dicts in `Antiquarian.py`**

In `TOOLTIP_DESCRIPTIONS`, delete the entire `# Registrar` group:

```python
    # Registrar
    "REGISTRAR_RM_DATABASE": "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your "
                         "RootsMagic Folder.",
    "REGISTRAR_FUZZY_THRESHOLD": "Score (0-100) for matching names when we KNOW their birth years. 82 is "
                                 "recommended.",
    "REGISTRAR_MAX_AGE_GAP": "The maximum number of years apart two records can be and still be flagged as a "
                            "duplicate.",
    "REGISTRAR_COLOR_VALUE": "The numeric RootsMagic color code to paint duplicate people (27 is Slate).",
    "REGISTRAR_FUZZY_THRESHOLD_STRICT": "A stricter threshold (0-100) used only for records missing a birth year.",
    "REGISTRAR_FAMILY_MATCH_THRESHOLD": "Score (0-100) used to verify if relatives (parents/spouses) match between two "
    "suspected duplicates.",
    "REGISTRAR_FOLDER_NAME": "The name of the Task Folder created in RootsMagic to hold duplicate review tasks.",
    "REGISTRAR_COLOR_SET": "The Color Set in RootsMagic (0-indexed) to apply the color value to.",

```

In `CUSTOM_LABELS`, delete:

```python
    "REGISTRAR_RM_DATABASE": "RootsMagic Database Path",
```

In `PATH_PICKER_FIELDS`, delete:

```python
    # Registrar
    "REGISTRAR_RM_DATABASE": {"kind": "open", "base_dir_key": "RM_DIR", "filetypes": RMTREE_FILETYPES},

```

In `FIELD_WIDGETS`, delete:

```python
    "REGISTRAR_FUZZY_THRESHOLD": {"type": "slider", "min": 0, "max": 100, "step": 1},
    "REGISTRAR_MAX_AGE_GAP": {"type": "slider", "min": 0, "max": 20, "step": 1},
    "REGISTRAR_FUZZY_THRESHOLD_STRICT": {"type": "slider", "min": 0, "max": 100, "step": 1},
    "REGISTRAR_FAMILY_MATCH_THRESHOLD": {"type": "slider", "min": 0, "max": 100, "step": 1},
```

- [ ] **Step 5: Replace the `REGISTRAR_VARS` literal with a loader call**

Old:

```python
REGISTRAR_VARS = {
    "File Paths (Relative to RootsMagic Dir)": {
        "REGISTRAR_RM_DATABASE": "Your Tree.rmtree"},
    "Matching Thresholds": {
            "REGISTRAR_FUZZY_THRESHOLD": "82",
            "REGISTRAR_MAX_AGE_GAP": "5",
            "REGISTRAR_FUZZY_THRESHOLD_STRICT": "95",
            "REGISTRAR_FAMILY_MATCH_THRESHOLD": "75"},
    "RootsMagic UI Settings": {
                "REGISTRAR_FOLDER_NAME": "!Duplicate Review",
                "REGISTRAR_COLOR_SET": "1",
                "REGISTRAR_COLOR_VALUE": "27"}}
```

New:

```python
REGISTRAR_VARS = _load_tool_schema(BASE_DIR / "Registrar")
```

- [ ] **Step 6: Delete `Registrar/schema_ui_map.py`**

Confirm nothing imports it first:

Run: `python -c "import ast,pathlib; [print(p) for p in pathlib.Path('.').rglob('*.py') if 'schema_ui_map' in p.read_text(encoding='utf-8', errors='ignore') and p.name != 'schema_ui_map.py']"`
Expected: no output (already confirmed dead/unimported during the design phase; this re-confirms it immediately before deletion).

```bash
git rm Registrar/schema_ui_map.py
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_antiquarian_settings_migration.py tests/test_antiquarian_paleographer_gating.py -v`
Expected: all PASS.

- [ ] **Step 8: Manual click-through**

Launch `python Antiquarian.py`, open the Registrar tab, hover each field's ⓘ icon and confirm the new, more specific tooltip text shows, confirm the four sliders and the file picker still work, save.

- [ ] **Step 9: Commit**

```bash
git add Antiquarian.py Registrar/settings_schema.yaml tests/test_antiquarian_settings_migration.py
git commit -m "Migrate Registrar settings to settings_schema.yaml, harvest tooltips from schema_ui_map.py, delete dead file"
```

---

### Task 6: Migrate Gazetteer to `settings_schema.yaml`

No missing fields — a straightforward move.

**Files:**
- Create: `Gazetteer/settings_schema.yaml`
- Modify: `Antiquarian.py`
- Modify: `tests/test_antiquarian_settings_migration.py`

**Interfaces:**
- Consumes: `_load_tool_schema` (Task 1).
- Produces: `GAZETTEER_VARS` now holds loader output.

- [ ] **Step 1: Write the failing migration test**

Append to `tests/test_antiquarian_settings_migration.py`:

```python
def test_gazetteer_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Gazetteer")

    assert result == {
        "File Paths": {
            "GAZETTEER_RM_DATABASE": "Your Tree.rmtree",
            "GAZETTEER_SHAPEFILE": "Antiquarian/Gazetteer/Reference/US_AtlasHCB_Counties/"
                                    "US_HistCounties_Shapefile/US_HistCounties.shp",
        },
        "Settings": {"GAZETTEER_DEBUG_MODE": "False", "GAZETTEER_CREATE_BACKUP": "True"},
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_antiquarian_settings_migration.py::test_gazetteer_schema_matches_expected_shape -v`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Create `Gazetteer/settings_schema.yaml`**

```yaml
sections:
  File Paths:
    GAZETTEER_RM_DATABASE:
      default: "Your Tree.rmtree"
      tooltip: "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your RootsMagic Folder."
      picker:
        kind: open
        base_dir_key: "RM_DIR"
        filetypes: [["RootsMagic files", "*.rmtree"], ["All files", "*.*"]]
    GAZETTEER_SHAPEFILE:
      default: "Antiquarian/Gazetteer/Reference/US_AtlasHCB_Counties/US_HistCounties_Shapefile/US_HistCounties.shp"
      tooltip: "The path to the Newberry Atlas '.shp' file containing historical county boundaries. Relative to your Program Dir (it ships alongside the Gazetteer tool), not the RootsMagic folder."
      picker:
        kind: open
        base_dir_key: "__PROGRAM_DIR__"
        filetypes: [["Shapefiles", "*.shp"], ["All files", "*.*"]]
  Settings:
    GAZETTEER_DEBUG_MODE:
      default: "False"
      tooltip: "Set to 'True' to print extra diagnostic information to the console while processing."
      widget: toggle
    GAZETTEER_CREATE_BACKUP:
      default: "True"
      tooltip: "Set to 'True' to automatically create a backup of your RootsMagic file before fixing it (Highly Recommended!)."
      widget: toggle
label_overrides:
  GAZETTEER_RM_DATABASE: "RootsMagic Database Path"
```

- [ ] **Step 4: Trim Gazetteer's entries out of the four shared dicts in `Antiquarian.py`**

In `TOOLTIP_DESCRIPTIONS`, delete the entire `# Gazetteer` group:

```python
    # Gazetteer
    "GAZETTEER_RM_DATABASE": "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your "
                          "RootsMagic Folder.",
    "GAZETTEER_SHAPEFILE": "The path to the Newberry Atlas '.shp' file containing historical county boundaries. "
                         "Relative to your Program Dir (it ships alongside the Gazetteer tool), not the RootsMagic "
                         "folder.",
    "GAZETTEER_CREATE_BACKUP": "Set to 'True' to automatically create a backup of your RootsMagic file before "
                             "fixing it (Highly Recommended!).",
    "GAZETTEER_DEBUG_MODE": "Set to 'True' to print extra diagnostic information to the console while processing.",

```

`CUSTOM_LABELS`: no Gazetteer-owned entries besides `GAZETTEER_RM_DATABASE`, which is not present in `CUSTOM_LABELS` today (only `REGISTRAR_RM_DATABASE` was — confirmed by the original dict listing). No deletion needed here; the label override is purely new, added via the YAML in Step 3.

In `PATH_PICKER_FIELDS`, delete:

```python
    # Gazetteer
    "GAZETTEER_RM_DATABASE": {"kind": "open", "base_dir_key": "RM_DIR", "filetypes": RMTREE_FILETYPES},
    "GAZETTEER_SHAPEFILE": {"kind": "open", "base_dir_key": PROGRAM_DIR_SENTINEL, "filetypes": SHP_FILETYPES},

```

In `FIELD_WIDGETS`, delete:

```python
    # Real booleans in the schema - a switch, not a "True"/"False" text box.
    "GAZETTEER_DEBUG_MODE": {"type": "toggle"},
    "GAZETTEER_CREATE_BACKUP": {"type": "toggle"},
```

(Leave the `PDFIX_CREATE_BACKUP`/`PDFIX_REPAIR_MODE` toggle lines that follow — those are trimmed in Task 7. If the leading comment `# Real booleans in the schema - a switch, not a "True"/"False" text box.` would otherwise sit directly above only PDFix's two remaining toggle entries, keep the comment; it still describes them correctly.)

- [ ] **Step 5: Replace the `GAZETTEER_VARS` literal with a loader call**

Old:

```python
GAZETTEER_VARS = {"File Paths": {"GAZETTEER_RM_DATABASE": "Your Tree.rmtree",
                                 "GAZETTEER_SHAPEFILE": "Antiquarian/Gazetteer/Reference/US_AtlasHCB_Counties/"
                                 "US_HistCounties_Shapefile/US_HistCounties.shp"},
                  "Settings": {"GAZETTEER_DEBUG_MODE": "False", "GAZETTEER_CREATE_BACKUP": "True"}}
```

New:

```python
GAZETTEER_VARS = _load_tool_schema(BASE_DIR / "Gazetteer")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_antiquarian_settings_migration.py tests/test_antiquarian_paleographer_gating.py -v`
Expected: all PASS.

- [ ] **Step 7: Manual click-through**

Launch `python Antiquarian.py`, open the Gazetteer tab, confirm both toggles and both file pickers still work, confirm the RootsMagic database field shows the "RootsMagic Database Path" label, save.

- [ ] **Step 8: Commit**

```bash
git add Antiquarian.py Gazetteer/settings_schema.yaml tests/test_antiquarian_settings_migration.py
git commit -m "Migrate Gazetteer settings to settings_schema.yaml"
```

---

### Task 7: Migrate PDFix to `settings_schema.yaml`

No missing fields — a straightforward move, and the last of the six tools.

**Files:**
- Create: `PDFix/settings_schema.yaml`
- Modify: `Antiquarian.py`
- Modify: `tests/test_antiquarian_settings_migration.py`

**Interfaces:**
- Consumes: `_load_tool_schema` (Task 1).
- Produces: `PDFIX_VARS` now holds loader output.

- [ ] **Step 1: Write the failing migration test**

Append to `tests/test_antiquarian_settings_migration.py`:

```python
def test_pdfix_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "PDFix")

    assert result == {
        "Scan Settings": {
            "PDFIX_TARGET_DIR": ".", "PDFIX_COMPRESSION_LEVEL": "2", "PDFIX_SIZE_THRESHOLD_MB": "0",
        },
        "Safety": {"PDFIX_CREATE_BACKUP": "True", "PDFIX_REPAIR_MODE": "False"},
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_antiquarian_settings_migration.py::test_pdfix_schema_matches_expected_shape -v`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Create `PDFix/settings_schema.yaml`**

```yaml
sections:
  Scan Settings:
    PDFIX_TARGET_DIR:
      default: "."
      tooltip: "The folder PDFix scans recursively for .pdf files, relative to your Base Media Directory (or an absolute path elsewhere). Leave as '.' to optimize every PDF anywhere inside Media."
      picker:
        kind: directory
        base_dir_key: "MEDIA_DIR"
    PDFIX_COMPRESSION_LEVEL:
      default: "2"
      tooltip: "How aggressively to garbage-collect and deflate-compress PDF structure: 0=low, 1=medium, 2=high (recommended). This is lossless - it never touches image resolution/DPI."
      widget: segmented
      options: [["0", "Low"], ["1", "Medium"], ["2", "High"]]
    PDFIX_SIZE_THRESHOLD_MB:
      default: "0"
      tooltip: "Only optimize PDFs larger than this size, in MB. Leave as 0 to optimize every PDF regardless of size."
      widget: slider
      min: 0
      max: 100
      step: 1
      suffix: "MB"
  Safety:
    PDFIX_CREATE_BACKUP:
      default: "True"
      tooltip: "Set to 'True' to save a '.pdf.backup' copy of each original before optimizing it in place (Highly Recommended!)."
      widget: toggle
    PDFIX_REPAIR_MODE:
      default: "False"
      tooltip: "Set to 'True' to attempt repairing structurally damaged/corrupted PDFs before optimizing them."
      widget: toggle
label_overrides:
  PDFIX_TARGET_DIR: "PDF Scan Folder"
```

- [ ] **Step 4: Trim PDFix's entries out of the four shared dicts in `Antiquarian.py`**

In `TOOLTIP_DESCRIPTIONS`, delete the entire `# PDFix` group (the last group in the dict):

```python
    # PDFix
    "PDFIX_TARGET_DIR": "The folder PDFix scans recursively for .pdf files, relative to your Base Media Directory "
                        "(or an absolute path elsewhere). Leave as '.' to optimize every PDF anywhere inside Media.",
    "PDFIX_COMPRESSION_LEVEL": "How aggressively to garbage-collect and deflate-compress PDF structure: 0=low, "
                               "1=medium, 2=high (recommended). This is lossless - it never touches image "
                               "resolution/DPI.",
    "PDFIX_SIZE_THRESHOLD_MB": "Only optimize PDFs larger than this size, in MB. Leave as 0 to optimize every PDF "
                              "regardless of size.",
    "PDFIX_CREATE_BACKUP": "Set to 'True' to save a '.pdf.backup' copy of each original before optimizing it in "
                          "place (Highly Recommended!).",
    "PDFIX_REPAIR_MODE": "Set to 'True' to attempt repairing structurally damaged/corrupted PDFs before "
                        "optimizing them."}
```

Since this was the dict's final entry (closing with `}` on the same line), the new final entry — `"CENSUS_IMAGE_DIR": ...` from the relocated Task 2 block — must now carry that closing `}` instead. Confirm `TOOLTIP_DESCRIPTIONS` still ends with exactly one closing `}` after this deletion.

In `CUSTOM_LABELS`, delete:

```python
    "PDFIX_TARGET_DIR": "PDF Scan Folder"}
```

Since this was also the dict's final entry, confirm `CUSTOM_LABELS`'s new final entry (`"CENSUS_IMAGE_DIR": "Census Image Save Folder"` from Task 2) now carries the closing `}`.

In `PATH_PICKER_FIELDS`, delete:

```python
    # PDFix
    "PDFIX_TARGET_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},

```

In `FIELD_WIDGETS`, delete:

```python
    "PDFIX_COMPRESSION_LEVEL": {"type": "segmented", "options": [("0", "Low"), ("1", "Medium"), ("2", "High")]},
```

and:

```python
    "PDFIX_CREATE_BACKUP": {"type": "toggle"},
    "PDFIX_REPAIR_MODE": {"type": "toggle"},
```

and:

```python
    "PDFIX_SIZE_THRESHOLD_MB": {"type": "slider", "min": 0, "max": 100, "step": 1, "suffix": "MB"},
```

After these deletions, confirm `FIELD_WIDGETS` contains exactly three entries: `EXTRACTION_ENGINE`, `API_BUDGET`, `CACHE_DISCOUNT_MULTIPLIER` (all `GLOBAL_VARS`-owned, per Task 2's relocated block). If the `# Real booleans in the schema...` comment from Task 6 is now left with nothing beneath it, delete that orphaned comment too.

- [ ] **Step 5: Replace the `PDFIX_VARS` literal with a loader call**

Old:

```python
PDFIX_VARS = {"Scan Settings": {"PDFIX_TARGET_DIR": ".", "PDFIX_COMPRESSION_LEVEL": "2",
                                "PDFIX_SIZE_THRESHOLD_MB": "0"},
              "Safety": {"PDFIX_CREATE_BACKUP": "True", "PDFIX_REPAIR_MODE": "False"}}
```

New:

```python
PDFIX_VARS = _load_tool_schema(BASE_DIR / "PDFix")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_antiquarian_settings_migration.py tests/test_antiquarian_paleographer_gating.py -v`
Expected: all PASS. All 6 migration tests (Archivist, Voyageur, Paleographer, Registrar, Gazetteer, PDFix) plus the Paleographer help-text test now pass.

- [ ] **Step 7: Manual click-through**

Launch `python Antiquarian.py`, click through all 7 tabs (6 tools + Global Settings) once, confirming every field, tooltip, toggle, slider, segmented control, and Browse button still renders and works, and every tab still saves without error.

- [ ] **Step 8: Commit**

```bash
git add Antiquarian.py PDFix/settings_schema.yaml tests/test_antiquarian_settings_migration.py
git commit -m "Migrate PDFix settings to settings_schema.yaml, completing the six-tool migration"
```

---

### Task 8: Delete dead filetypes constants

`RMTREE_FILETYPES`, `JSON_FILETYPES`, `GED_FILETYPES`, `SHP_FILETYPES` were only ever referenced from `PATH_PICKER_FIELDS` entries that Tasks 2, 4, 5, 6 have now all moved into YAML (each tool's own `filetypes` list is now inline in its `settings_schema.yaml`). Confirm they're unreferenced, then delete them. `PROGRAM_DIR_SENTINEL`/`TOOLBOX_DIR_SENTINEL` are NOT deleted — they're still read by `_resolve_base_dir`/`_browse_for_path` and still referenced by `GLOBAL_VARS`'s own `PROGRAM_DIR` picker entry, which never migrates.

**Files:**
- Modify: `Antiquarian.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — pure dead-code removal, verified by grep before deleting.

- [ ] **Step 1: Confirm the four constants are unreferenced outside their own definitions**

Run: `python -c "import re,pathlib; text=pathlib.Path('Antiquarian.py').read_text(encoding='utf-8'); [print(name, text.count(name)) for name in ('RMTREE_FILETYPES','JSON_FILETYPES','GED_FILETYPES','SHP_FILETYPES')]"`
Expected: each name prints a count of exactly `1` (only its own definition line remains; every consuming `PATH_PICKER_FIELDS` entry was already migrated to inline YAML `filetypes` lists in Tasks 2-7).

- [ ] **Step 2: Delete the four constant definitions**

In `Antiquarian.py`, delete:

```python
RMTREE_FILETYPES = [("RootsMagic files", "*.rmtree"), ("All files", "*.*")]
JSON_FILETYPES = [("JSON files", "*.json"), ("All files", "*.*")]
GED_FILETYPES = [("GEDCOM files", "*.ged"), ("All files", "*.*")]
SHP_FILETYPES = [("Shapefiles", "*.shp"), ("All files", "*.*")]
```

(This sits directly beneath `PROGRAM_DIR_SENTINEL`/`TOOLBOX_DIR_SENTINEL`, which stay.)

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests PASS (loader unit tests, all 6 migration tests, the Paleographer help-text test, and the pre-existing gating tests).

- [ ] **Step 4: Launch check**

Run: `python Antiquarian.py`, confirm the app launches with no import error, click through all 7 tabs once more.

- [ ] **Step 5: Commit**

```bash
git add Antiquarian.py
git commit -m "Delete dead per-tool filetypes constants, superseded by inline YAML filetypes lists"
```

---

### Task 9: Schema-completeness regression test (all tools)

Adds the automated check the spec calls for: for each of the six tools, grep its own `.py` source for every `os.getenv`/`os.environ.get` key it reads, subtract `GLOBAL_VARS`'s own keys (never expected in a tool's YAML), and assert the remainder is a subset of that tool's `settings_schema.yaml` keys. This is the test that would have caught every gap this plan just fixed, and it fails the next time a tool grows a setting the GUI doesn't know about.

**Files:**
- Create: `tests/test_settings_schema_completeness.py`

**Interfaces:**
- Consumes: `_load_tool_schema` (Task 1), the six committed `settings_schema.yaml` files (Tasks 2-7).
- Produces: nothing consumed by later code — this is a standalone regression test.

- [ ] **Step 1: Write the test**

Create `tests/test_settings_schema_completeness.py`:

```python
import re
from pathlib import Path

import pytest

import Antiquarian

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_VAR_PATTERN = re.compile(r"os\.(?:getenv|environ\.get)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")

TOOL_DIRS = {
    "Archivist": BASE_DIR / "Archivist",
    "Voyageur": BASE_DIR / "Voyageur",
    "Paleographer": BASE_DIR / "Paleographer",
    "Registrar": BASE_DIR / "Registrar",
    "Gazetteer": BASE_DIR / "Gazetteer",
    "PDFix": BASE_DIR / "PDFix",
}


def _env_keys_read_by(tool_dir: Path) -> set:
    keys = set()
    for py_file in tool_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        keys.update(ENV_VAR_PATTERN.findall(text))
    return keys


def _global_keys() -> set:
    keys = set()
    for fields in Antiquarian.GLOBAL_VARS.values():
        keys.update(fields.keys())
    return keys


def _schema_keys(tool_dir: Path) -> set:
    schema = Antiquarian._load_tool_schema(tool_dir)
    keys = set()
    for fields in schema.values():
        keys.update(fields.keys())
    return keys


@pytest.mark.parametrize("tool_name", sorted(TOOL_DIRS))
def test_tool_schema_covers_every_env_var_the_tool_reads(tool_name):
    tool_dir = TOOL_DIRS[tool_name]
    read_keys = _env_keys_read_by(tool_dir) - _global_keys()
    schema_keys = _schema_keys(tool_dir)

    missing = read_keys - schema_keys
    assert not missing, (
        f"{tool_name} reads env var(s) {sorted(missing)} via os.getenv/os.environ.get "
        f"that are absent from {tool_dir / 'settings_schema.yaml'} - add them."
    )
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_settings_schema_completeness.py -v`
Expected: all 6 parametrized cases PASS, since Tasks 2-7 already closed every gap this test checks for. If any case unexpectedly fails, it has found a real gap beyond this plan's known debt fixes (a `_get_env_int()`-style wrapper the regex can't see through, or a genuinely new setting) — per the spec's own intent for this test ("turning silent drift into an automated check"), add the missing key(s) to that tool's `settings_schema.yaml` before proceeding, rather than weakening the test.

- [ ] **Step 3: Run the full test suite one more time**

Run: `pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_settings_schema_completeness.py
git commit -m "Add schema-completeness regression test across all six tools"
```

---

## Self-Review

**Spec coverage:**
- Per-tool YAML files with `sections:`/`label_overrides:` shape, `str()`-coerced defaults, tooltip/widget/picker nesting — Tasks 2-7. ✅
- Generic loader, `_build_form_ui` et al. unchanged, `ENV_TARGETS` unchanged (still references the same six names, which now hold loader output) — Task 1, confirmed in Architecture section. ✅
- Archivist audit gaps (`TRANSCRIPTION_HEADER`, `TRANSLATION_HEADER`, `ROLE_CLERGY`, `CLERGY_HONORIFIC`, `ROLE_DEFAULT_WITNESS`, `ENUMERATION_DISTRICT`, `FILM_NUMBER`, `ROLL_NUMBER`) — Task 2. ✅
- Paleographer audit gap (`AGY_CLI_BIN`, `AGY_TIMEOUT_SECONDS`) and stale help text — Task 4. ✅
- Voyageur/LAC `LAC_ARCHIVAL_NUMBER` rename bug and missing `LAC_CHECKPOINT_DIR`/`LAC_CDP_PORT`/`LAC_MAX_WORKERS` — Task 3. ✅
- Registrar tooltip harvest from `schema_ui_map.py` + deletion of that dead file — Task 5. ✅
- Gazetteer, PDFix clean migrations — Tasks 6-7. ✅
- Fail-loud error handling (`FileNotFoundError`/`RuntimeError`/`ValueError`, each naming the file) — Task 1, unit-tested. ✅
- No transition period per tool — each task's single commit deletes the old dict entries and adds the YAML together. ✅
- Loader unit tests + schema-completeness regression test — Tasks 1 and 9. ✅
- Archivist flat form, no dropdown — confirmed never introduced; Task 2 renders via the same `_build_form_ui(frame, ARCHIVIST_VARS)` call `_build_tab_archivist` already used. ✅
- Out of scope items (sidebar/tab grouping, moving help text/buttons into schema, Commissioner) — untouched by every task. ✅

**Placeholder scan:** no "TBD"/"TODO" in any task; every YAML file has its complete real content; every dict-trim step shows the exact deleted text; every Python code block is complete and runnable, not descriptive prose standing in for code.

**Type/signature consistency:** `_load_tool_schema(tool_dir: Path) -> Dict[str, Dict[str, str]]` is used identically across Tasks 1-9 and all test files; `TOOLTIP_DESCRIPTIONS`/`CUSTOM_LABELS`/`PATH_PICKER_FIELDS`/`FIELD_WIDGETS` are the same four names throughout, never renamed; every `*_VARS` name (`ARCHIVIST_VARS`, `VOYAGEUR_VARS`, `PALEOGRAPHER_VARS`, `REGISTRAR_VARS`, `GAZETTEER_VARS`, `PDFIX_VARS`) keeps its exact original identifier so `ENV_TARGETS` and every `_build_tab_*` method needs zero changes.
