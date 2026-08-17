# Voyageur & Paleographer Fixes — Design Document

**Date:** 2026-08-16
**Status:** Approved

---

## Summary

Three targeted fixes to the Antiquarian GUI and settings schemas, to be implemented on a
feature branch and merged via PR. No new tools, no new pipeline stages.

---

## Change 1 — Voyageur: Expose Overwrite/Skip for Keystone Archives & LAC

### Problem

`_voyageur_visible_sections()` in `Antiquarian.py` (line ~1771) strips `GATHER_ON_COLLISION`
from every source except Ancestry and FamilySearch. The HBCA and LAC scripts never read the
env var, so the UI correctly hid it — but users now want the option available for those
sources too.

### Decision

- Remove the Ancestry/FamilySearch guard so `GATHER_ON_COLLISION` is shown for **all four**
  sources (Ancestry, FamilySearch, LAC, Keystone Archives).
- Wire `GATHER_ON_COLLISION` into `HBCA.py` and `LAC.py`: where each script writes a file
  that already exists, read the env var and either overwrite or skip accordingly.
- Use the **shared `GATHER_ON_COLLISION` key** (no new per-source env keys) — one setting,
  uniform UI, consistent behavior.
- `Voyageur/settings_schema.yaml` already defines the widget correctly; no schema changes.

---

## Change 2 — Voyageur: Three Action Buttons (Gather / Gather & Build / Gather, Transcribe & Build)

### Problem

The current two-button layout (`Gather from {source}`, `Gather and Send to Archivist`) is
missing a third path: Gather → Paleographer → Archivist for raw-image collections that need
AI transcription before a GEDCOM can be built.

### Decision

Replace the two buttons with three, in this order:

| # | Label | Color | Chain |
|---|---|---|---|
| 1 | `Gather from {source}` | Blue `#3B8ED0` | Voyageur only |
| 2 | `Gather & Build` | Green `#2b7a4b` | Voyageur → Archivist |
| 3 | `Gather, Transcribe & Build` | Purple `#7c5cbf` | Voyageur → Paleographer → Archivist |

Button 3's chain nests two `on_success` callbacks:
```
execute_script("VOYAGEUR_SCRIPT", code,
    on_success=lambda: execute_script("PALEOGRAPHER_SCRIPT", "extract",
        on_success=lambda: execute_script("ARCHIVIST_SCRIPT", "gedcom_auto")))
```

The `_on_voyageur_source_change()` method is updated to configure all three buttons whenever
the source dropdown changes.

---

## Change 3 — Paleographer: Multi-Tier Prompt Discovery

### Problem

`_list_record_types()`, `_read_pmt_front_matter()`, and `_get_pmt_settings_sections()` all
hardcode `Paleographer/prompts` relative to `__file__`. At runtime, `engine.py` uses a
three-tier search:
1. `GENEALOGY_DIR/Prompts` — user's own per-installation overrides (highest priority)
2. `PROGRAM_DIR/Prompts` — app's bundled defaults
3. `Paleographer/prompts/` sibling folder — dev-mode fallback

In a portable build where `PROGRAM_DIR` points to a different folder, the GUI dropdown and
the runtime can show different record types, explaining why the dropdown only shows `Parish`.

### Decision

- Add a `_prompt_search_dirs()` helper to `Antiquarian.py` that mirrors
  `engine.py`'s `_prompt_search_dirs()` exactly, reading `GENEALOGY_DIR` and `PROGRAM_DIR`
  from `self.string_vars` (already loaded at startup).
- Rewrite `_list_record_types()` to scan all three tiers in the same order, with earlier
  tiers (GENEALOGY_DIR) shadowing the same filename in later tiers — matching engine.py's
  dedup logic.
- Rewrite `_read_pmt_front_matter()` to resolve the .pmt path through the same multi-tier
  scan rather than a hardcoded sibling path.
- `_get_pmt_settings_sections()` calls `_read_pmt_front_matter()`, so it inherits the fix
  automatically.
- `PROMPTS_DIR` remains an internal/exempt env key (consistent with
  `tests/test_settings_schema_completeness.py` line 17 `INTERNAL_KEYS`).
- No `settings_schema.yaml` changes required.

---

## Constraints

- Branch off `Unify`; merge back via PR (no direct push to `Unify` or `main`).
- Lint: zero pycodestyle violations at `--max-line-length=120`.
- All tests must pass: `python -m pytest` from repo root.
- Schema-completeness tests must pass: every new env key read by `HBCA.py` / `LAC.py`
  must be declared in `Voyageur/settings_schema.yaml` (or be in `INTERNAL_KEYS`).
- No golden-file regeneration (`capture_golden_gedcom.py`) — this change doesn't touch
  GEDCOM output logic.
