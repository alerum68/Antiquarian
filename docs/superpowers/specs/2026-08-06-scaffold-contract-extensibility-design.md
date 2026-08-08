# Scaffold Contract Extensibility (Sub-project 1 of the Voyageur-owns-ingestion rework)

## What this is

The first of several sub-projects implementing a larger redirect: ingestion for
every record type (Parish, Scrip, Census, and future types like HBC records and
Wills & Probates) is moving into `Voyageur`, with `Paleographer` becoming pure
analysis (AI transcription/translation/enrichment) that never constructs the base
JSON structure itself. That larger rework is decomposed into sub-projects; this one
is the foundation the rest depend on.

This sub-project makes the JSON shape every record type produces a fixed,
record-type-agnostic template that never needs to change when a new record type is
added. It closes one specific gap: `Commissioner.record_registry` already scans
every `.pmt` file in `Paleographer/prompts/` and builds, per document type, typed
extra fields and a valid-roles list — but only Parish and Scrip have `.pmt` files
today. Census has no such declaration, so it's invisible to Commissioner's registry
entirely, even though `Voyageur/census_schema.py`'s own gather output
(`normalize_census_pages`) already produces a dict shaped exactly like
`Commissioner.models.Record`/`Participant`.

## Goals

- Every record type — present (Parish, Scrip, Census) and future (HBC, Wills &
  Probates, anything else) — declares its shape through exactly one mechanism: a
  `.pmt` file in `Paleographer/prompts/`, using the same YAML front matter
  (`roles`, `extra_fields`) that `record_registry._build_registry()` already scans.
  Adding a new record type in the future means writing one new `.pmt` file — never
  a code change in `Commissioner`.
- `Commissioner.models`'s `Collection`/`Sheet`/`Record`/`Participant`/`Fact` classes
  stay completely untouched. They are already the fixed, agnostic shape; this
  sub-project proves that claim by extending the declared-type list without ever
  touching them.
- Close the immediate gap: give Census a `.pmt` file so `Census` becomes a
  recognized `document_type` and `parse_collection(raw_json, "Census")` becomes
  callable, the same way it already is for Parish and Scrip.

## Non-goals (explicitly out of scope for this sub-project)

- Not wiring `parse_collection()` into Voyageur's actual Census gather path yet —
  that's a later sub-project. This sub-project only makes the call *possible*.
- Not touching `Paleographer.py`'s ingestion path, `engine.py`, or any AI-prompted
  extraction logic.
- Not changing `Voyageur/census_schema.py`'s behavior. Its `field_maps/*.yaml`
  (raw source column → shared field name) is an orthogonal, upstream concern that
  feeds *into* the shape `Census.pmt` declares — it is not a competing declaration
  of that shape and is not touched here.
- Not changing `Commissioner/models.py`, `Commissioner/fact_registry.py`, or
  `Commissioner/record_registry.py`. The `.pmt`-scanning mechanism already handles
  "any `.pmt` file found in the prompts directory" — no code there needs to change
  for a new type to become visible.
- Not authoring `.pmt` files for HBC or Wills & Probates. Those record types aren't
  built yet (per `ROADMAP.md`); this sub-project only proves the pattern generalizes,
  using Census as the concrete case.

## Architecture

`Commissioner.record_registry` already treats "which document types exist" as
data, not code: it scans `Paleographer/prompts/*.pmt` at load time and builds a
typed extra-fields model and a valid-roles list per file, purely from each file's
YAML front matter. Nothing about that scan assumes the file's prose body is ever
sent to an LLM — it just needs to parse.

That means the fix for Census's invisibility isn't a new code path — it's
authoring one new front-matter block, the same shape as Parish/Scrip's front
matter. Unlike the original assumption, `Census.pmt`'s prose section (below the
`---` front matter) is a real Gemini extraction prompt, not a placeholder: Census
images get analyzed by Paleographer the same way Parish/Scrip images do, so the
AI can fill in or correct data the Ancestry/FamilySearch index didn't capture (a
column the transcriber skipped, a name transcribed differently than what's on the
image, information present on the image but never indexed at all). Census.pmt
becomes a normal AI-prompted `.pmt` file, structurally no different from
Parish/Scrip — there is no "no-AI type" category in this design after all.

This generalizes directly: a future `HBC.pmt` or `Wills.pmt` needs the same two
things — `roles` and `extra_fields` — and record_registry picks it up
automatically the next time it runs, exactly as documented in the original
Commissioner pilot spec's "Example: what generic and extensible actually means"
section.

## Components changed

**New file: `Paleographer/prompts/Census.pmt`**

Front matter to declare:
- `roles` — the household-role vocabulary implied by Census participants today
  (Head, Spouse, Child, Other — to be confirmed against what
  `census_schema.py`/`field_maps/*.yaml` actually produce for `role_name`, since
  Census's roles come from source column data, not a fixed AI-facing list the way
  Scrip's do).
- `extra_fields.record` — the `type_specific_fields` keys `normalize_census_pages()`
  already writes at the record level: `family_number`, `enumeration_district`,
  `roll_number`, `film_number`, `state`, `county`, `city`, `country`, `apid_db`.
- `extra_fields.participant` — the `type_specific_fields` keys already written at
  the participant level: passthrough identifiers (`pid`, `extracted_url`,
  `fsftid`, `person_ark`, `familysearch_url`) and the `unmapped` catch-all bucket.

**No changes to `Voyageur/census_schema.py`.** It keeps producing the same dict
shape it does today. This sub-project only makes that shape *validatable*; wiring
the actual `parse_collection()` call into `census_schema.py` or `Voyageur.py` is a
later sub-project.

**No changes to `Commissioner/` package code.**

**Census.pmt's prompt content itself** (what to tell the model about reading a
census image, how to reconcile it against index-sourced data already in the
scaffold) is prompt-engineering work, not a shape decision — out of scope for this
sub-project's design in the same way Parish.pmt's/Scrip.pmt's actual prose was
never part of the Commissioner pilot's own design doc. This sub-project's job is
only to establish that the file exists and its front matter is what Commissioner
reads; the prompt body is implementation-plan-level work.

## Data flow

Before: `record_registry.get_document_types()` returns `["Parish", "Scrip"]`.
`parse_collection(raw_json, "Census")` raises "unknown document_type."

After: `get_document_types()` returns `["Census", "Parish", "Scrip"]`.
`parse_collection(raw_json, "Census")` validates a Census-shaped dict against the
same `Collection`/`Sheet`/`Record`/`Participant` models Parish and Scrip already
use, with Census's own extra-fields model and role list applied. Nothing calls
this yet in production code — it's exercised only by this sub-project's own tests
— but the capability now exists for sub-project 2 to wire in.

## Note for implementation

Census's `type_specific_fields` aren't a fixed set per record the way Scrip's
extra fields are — some keys (`family_number`, `enumeration_district`, etc.) are
conditionally present depending on what the source page actually supplied (see
`normalize_census_pages()`'s `if page.get(...)` guards), and the passthrough
identifiers are conditionally present per participant depending on source
(FamilySearch vs. Ancestry). Whoever implements `Census.pmt` needs to decide:
declare every field as optional (matching how Scrip's fields already work), or
determine Census needs different validation strictness than
`ConfigDict(extra="forbid")`. This mirrors the precedent already set in the
Commissioner pilot spec, which flagged `Scrip.pmt`'s `scrip_amount` field-splitting
as an implementation-time decision rather than a design-time one.

A second, separate decision this sub-project does not resolve: when Census.pmt's
AI pass extracts a value from the image that conflicts with what Voyageur already
put in the scaffold from the index (e.g. the index says one surname spelling, the
image shows another), which value wins. That's a merge-precedence rule that
applies to Parish/Scrip's own image-fills-scaffold behavior too (per the
already-agreed pattern where Voyageur populates the scaffold with whatever the
gather incidentally supplies, e.g. FamilySearch Image Index data), so it belongs
in the sub-project that wires Paleographer's analysis pass against the scaffold,
not here.

## Error handling

No new error paths. Same rules that already apply to Parish/Scrip: an
unrecognized `type:` token in `extra_fields` fails at Commissioner load time; a
value that doesn't match its declared type, or a `role_name` not on the type's
role list, fails at `parse_collection()` time.

## Testing

- `record_registry.get_document_types()` includes `"Census"` after `Census.pmt` is
  added.
- Round-trip test: a real (or representative fixture) `normalize_census_pages()`
  output parses cleanly through `parse_collection(raw_json, "Census")`.
- Negative test: a Census-shaped dict with an invalid `role_name` raises, matching
  the existing Scrip negative-test pattern.

## What comes after this sub-project (not part of it)

- Sub-project 2: wiring Voyageur's Census gather path to actually call
  `parse_collection()` against the now-declared Census shape.
- Sub-project 3: Voyageur building the Commissioner-shaped scaffold (images +
  empty-content records, filled in with whatever real data the gather incidentally
  supplies) for Parish and Scrip.
- Sub-project 4: reworking Paleographer to consume that scaffold as pure analysis,
  never constructing the base JSON structure itself. Merge precedence (decided
  during this sub-project's brainstorming, recorded here so it isn't lost):
  index-sourced fields already present in the scaffold are trusted by default and
  are not re-sent to the AI for review, to avoid spending tokens re-verifying data
  Voyageur already gathered — Paleographer's default pass only fills fields the
  scaffold left empty. A user-facing setting can switch a given run to full-image
  review, where the AI re-examines the whole document and is allowed to overwrite
  already-present indexed values.
- Sub-project 5: wiring Commissioner validation at both the Voyageur and
  Paleographer boundaries.
- Sub-project 6: cross-script invocation (Paleographer/Voyageur calling into each
  other's real functions when one needs what the other gathers, per the
  no-duplicate-code requirement).
