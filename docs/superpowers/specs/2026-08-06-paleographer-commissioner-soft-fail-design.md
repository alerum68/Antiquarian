# Wire Paleographer's Own MASTER_DB Write to Commissioner Validation (Sub-project 4 of the Voyageur-owns-ingestion rework)

## What this is

Sub-project 2 wired soft-fail Commissioner validation into Voyageur's Census
gather (`A.py`/`FS.py`), and the just-shipped Voyageur Parish/Scrip scaffold
work extended the same soft-fail pattern to `FS.py`'s Parish/Scrip gather and
to `LAC.py`'s scaffold-sheet MASTER_DB writes. Three call sites now exist, each
with its own copy-pasted `try: from Commissioner.record_registry import
parse_collection; parse_collection(data, document_type); except Exception as
e: print(f"[WARN] ...")` block. Paleographer — the tool that actually
AI-fills those records and writes the final content into MASTER_DB — has no
Commissioner validation at all. This sub-project closes that gap and
deduplicates the three existing copies at the same time.

## Goals

- Every MASTER_DB write Paleographer performs (`save_master_db()`, all ~6 call
  sites) runs through the same soft-fail Commissioner check Voyageur already
  has, with no call site able to forget it — validation lives inside
  `save_master_db()` itself, not repeated at each caller.
- The repeated try/except/log-WARN shape currently copy-pasted three times
  (`census_schema.py`, `FS.py`, `LAC.py`) collapses into one shared
  `Commissioner.record_registry.validate_soft()` function all four sites
  (the three existing plus the new Paleographer one) call.
- A Commissioner schema mismatch on a Paleographer write behaves exactly like
  a Voyageur one: logged, swallowed, never blocks the write or crashes the
  run.

## Non-goals (explicitly out of scope for this sub-project)

- No hard-fail/blocking validation mode anywhere. This soft-fail rollout is
  still untested against real data (per the user: "untested. I think we need
  to have Paleographer conform to what the commissioner says, like Voyageur,
  before we do any other steps") — deciding whether/when to make any of the
  four sites hard-fail is deferred until the now-four-site rollout has
  actually run and surfaced real shape gaps to react to.
- No change to Paleographer's own JSON-construction responsibility (it still
  builds sheets/records itself, AI-derived). That's Sub-project 6.
- No broader structural rebuild of `Paleographer.py` (the folded-together
  `engine.py`/`agy_engine.py`/`postprocess.py`/Scrip-DEV file, legacy
  wrappers and shims). Explicitly folded into Sub-project 6 instead, per
  user direction, rather than attempted here — this sub-project touches
  `save_master_db()` and its immediate neighbors only.
- No change to `Commissioner.models` or the validation rules themselves
  (`parse_collection`'s behavior is unchanged; only how many places call it
  changes).

## Architecture

`Commissioner/record_registry.py` gains one new function:
`validate_soft(data: dict, document_type: str, label: str) -> None`. It
wraps `parse_collection(data, document_type)` in the same try/except the
three existing call sites already hand-roll, logging
`[WARN] Commissioner validation failed for {label!r}: {e}"` and never
raising. Because it lives inside `record_registry.py`, it calls
`parse_collection` as a plain sibling-function call (no import needed
inside it) — the import that must stay guarded is `record_registry` itself,
which callers already wrap in `try/except` per the existing "never at module
scope" rule (importing it triggers `_build_registry()`, which parses every
`.pmt` file and could itself raise).

The three existing Voyageur wrappers (`census_schema.validate_against_commissioner`,
`FS.validate_against_commissioner`, `LAC.validate_master_db_against_commissioner`)
keep their own document-type resolution logic (hardcoded `"Census"`, the
`record_family` → document-type mapping with its early-return for unmapped
families like `"wills"`, or a direct passthrough respectively) but replace
their internal `parse_collection` call with a call to `validate_collection_softly`,
inside the same `try/except` shape they already have (this guards the
`validate_collection_softly` import itself; `validate_collection_softly`'s own internal catch handles
everything after that import succeeds, so there is no double-logging in the
normal case).

Paleographer's `save_master_db(master_data)` gets no new parameter. It reads
`document_type` off `master_data["record_type_name"]` (already present at
call time — set at `load_master_db()` or the default-shape construction) and
calls `validate_soft(master_data, master_data.get("record_type_name",
TYPE_CFG.name), COLLECTION_TITLE)` once, before the `json.dump` write. Every
one of its ~6 existing call sites is covered automatically with zero
per-site changes.

## Components changed

**`Commissioner/record_registry.py`**
- New: `validate_soft(data: dict, document_type: str, label: str) -> None` —
  calls `parse_collection(data, document_type)` inside `try/except
  Exception`, logging `[WARN] Commissioner validation failed for {label!r}:
  {e}` on failure, never raising.

**`Voyageur/census_schema.py`** (`validate_against_commissioner`, ~line 296)
- Internal body changes from importing/calling `parse_collection` directly
  to importing/calling `validate_soft(normalized, "Census", collection_title)`.
  Signature and external behavior unchanged.

**`Voyageur/FS.py`** (`validate_against_commissioner`, ~line 433)
- Keeps its `RECORD_FAMILY_TO_DOCUMENT_TYPE` lookup and early-return for
  unmapped families. The `parse_collection` call at the end becomes a call to
  `validate_soft(final_data, document_type, collection_title)`. Signature and
  external behavior unchanged.

**`Voyageur/LAC.py`** (`validate_master_db_against_commissioner`, in the
building-blocks section added by the scaffold plan)
- Internal body changes from `parse_collection` to
  `validate_soft(master_data, document_type, collection_title)`. Signature
  and external behavior unchanged.

**`Paleographer/Paleographer.py`** (`save_master_db`, ~line 1422)
- Gains one line before the `json.dump` write: a guarded call to
  `validate_soft(master_data, master_data.get("record_type_name",
  TYPE_CFG.name), COLLECTION_TITLE)`. No signature change. All ~6 existing
  call sites (live-extraction loop, batch-job merge loop, quota-exhaustion
  fallback, batch-job submission) are covered without being touched.

## Data flow

Before: Paleographer writes `master_data` to `MASTER_DB` with zero schema
validation, at every one of its ~6 write points. Before this sub-project,
Voyageur's three sites already validate their own output the same soft-fail
way, each with an independent copy of the try/except/log-WARN logic.

After: every MASTER_DB write from any of Paleographer's ~6 call sites passes
through the same `parse_collection` check Voyageur already runs, via the
shared `validate_collection_softly` helper. On success, nothing about the written output
changes. On failure (e.g. an AI-filled sheet with a shape Commissioner
doesn't recognize), a `[WARN]` is logged and the file is still written
exactly as before — this sub-project adds visibility, not a gate. The four
call sites (`census_schema.py`, `FS.py`, `LAC.py`, `Paleographer.py`) now
share one implementation of the actual validation-and-logging step instead
of four independent copies.

## Error handling

No new exception types. `validate_collection_softly` never raises once its own import has
succeeded — it catches `Exception` broadly, matching the existing
soft-fail policy's scope (a Pydantic `ValidationError`, an
`UnknownFieldTypeError`, or any other failure inside `parse_collection` are
all logged and swallowed identically). The remaining, pre-existing risk —
`from Commissioner.record_registry import validate_soft` itself raising if
the module's own `_build_registry()` blows up on a malformed `.pmt` file at
first import — is guarded the same way it already is at every current call
site: the import stays inside the caller's own `try/except`, which logs the
same `[WARN]` format on that (rare, first-import-only) failure too.

## Testing

- `Commissioner/tests/test_record_registry.py`:
  - New test: `validate_collection_softly` with a valid collection and a known
    `document_type` produces no output (no `[WARN]` printed).
  - New test: `validate_collection_softly` with a malformed collection logs `[WARN]
    Commissioner validation failed for {label!r}: ...` and does not raise.
  - New test: `validate_collection_softly` with an unknown `document_type` also logs
    `[WARN]` and does not raise (covers `UnknownDocumentTypeError` the same
    way as any other `parse_collection` failure).
- `Voyageur/tests/test_census_schema.py`, `Voyageur/tests/test_fs.py`,
  `Voyageur/tests/test_lac.py`: existing tests continue to pass unmodified —
  proves the `validate_collection_softly` delegation is behavior-neutral for all three
  existing call sites.
- `Paleographer/tests/test_master_db_merge.py`:
  - New test: `save_master_db` on a MASTER_DB shape Commissioner accepts
    writes the file and prints no `[WARN]`.
  - New test: `save_master_db` on a MASTER_DB shape Commissioner rejects
    still writes the file (soft-fail — the write is not blocked) and prints
    `[WARN] Commissioner validation failed for ...`.

## What comes after this sub-project (not part of it)

- Sub-project 5: cross-script invocation (Paleographer/Voyageur calling into
  each other's real functions when one needs what the other gathers).
- Sub-project 6: reworking Paleographer to consume the Sub-project 3 scaffold
  as pure analysis, never constructing the base JSON structure itself — and,
  folded into the same sub-project per explicit user direction, the broader
  structural rebuild `Paleographer.py` (2142 lines) needs: it's still four
  historically separate files (`engine.py`, `agy_engine.py`, `postprocess.py`,
  a Commissioner/DEV Scrip-enrichment block) stitched together behind banner
  comments rather than re-architected into real module boundaries, with
  legacy wrappers/shims kept "for test-suite compatibility."
- Hard-fail/blocking Commissioner validation mode for any of the four sites,
  once this sub-project's soft-fail rollout has run against real data and
  surfaced whatever shape gaps exist.
- Census family-linking and extended-family vocabulary work — unchanged from
  the sub-project 2 spec, still unscoped to any currently-planned sub-project.
