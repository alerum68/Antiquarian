# Commissioner: Core Domain Models (Pilot)

## What this is

A new shared package, `Commissioner/`, holding strongly-typed data models for the
things every pipeline module works with: a historical record, a person mentioned in
it, and the facts (birth, death, marriage, occupation...) attached to that person.
Today these are passed around as loosely-shaped dicts, translated back and forth
between modules by one-off adapter functions (e.g. `build_census_dataframe_from_unified`
in `Archivist.py`). This pilot replaces that with one typed, validated contract that
every module can eventually import instead of inventing its own shape.

`Commissioner/` used to be a pipeline stage (scrip enrichment/partitioning); that logic
was already folded into `Paleographer`/`Voyageur` in a recent commit, leaving the
folder essentially empty. We're reusing the name and cleaning out the leftover
scaffold (`Commissioner/.env`, empty `Commissioner/tests/`) as part of this work.

## Goals

- Strongly-typed models (Pydantic) for the ingestion shape every AI-transcription
  pipeline (Paleographer/Voyageur) already produces: a `Collection` of `Sheet`s, each
  with `Record`s, each with `Participant`s, each carrying `Fact`s.
- A registry that reads `FactTypes.json` (the ~60 GEDCOM fact types: Birth, Death,
  Marriage, Occupation, etc.) once, so any fact a person/family carries can be
  validated and, later, rendered generically instead of via a hardcoded per-type
  branch.
- A registry that reads every `.pmt` file in `Paleographer/prompts/` (currently
  `Parish.pmt` and `Scrip.pmt`) and builds, per document type:
  - its extra fields (e.g. Scrip's `claim_number`, `scrip_amount`...) as real typed
    fields, not an untyped dict
  - its valid participant roles (e.g. Scrip's `Claimant, Spouse, Child, Father,
    Mother, Heir, Witness, Commissioner, Other`), so a role name that isn't on the
    list is rejected instead of silently accepted
  - **Both are read generically from whatever's in the `.pmt` file.** Adding a new
    `.pmt` for a new document type in the future needs zero code changes here — the
    registry picks it up automatically the next time it runs.

## Non-goals (explicitly out of scope for this pilot)

- Not touching the Census pipeline, `Archivist.py`, or any other legacy code.
- Not wiring `Commissioner` into Paleographer's actual ingestion calls yet.
- Not retiring `Paleographer/schema.json` yet — Paleographer keeps using it exactly
  as it does today. (Longer-term, once Paleographer adopts `Commissioner`,
  `schema.json` could be generated on the fly from the Pydantic models instead of
  hand-maintained — but that's a later phase, not this one.)
- Not building the emission/GEDCOM-writing side. This pilot builds the typed data and
  proves it can be validated; using it to write output is future work.

## Package layout

```
Commissioner/
    models.py           # Collection, Sheet, Record, Participant, Fact (Pydantic)
    fact_registry.py     # loads FactTypes.json -> FactDefinition lookup
    record_registry.py   # scans Paleographer/prompts/*.pmt -> per-doc-type models + role lists
    __init__.py           # public API
    tests/
```

## How the pieces fit together

**`models.py`** is the one authored source of truth for what a `Collection` /
`Sheet` / `Record` / `Participant` / `Fact` looks like. It's written by hand as
Pydantic classes, with each field's guidance text (currently living in
`schema.json`'s `description` properties, e.g. *"Leave null. Derived downstream from
event_type..."*) carried over as Pydantic `Field(description=...)`. Because Pydantic
can export a model back out as JSON Schema, nothing is lost by keeping the
descriptions in Python instead of the JSON file.

To make sure `models.py` doesn't quietly drift from what Paleographer is actually
sending the AI today, the test suite includes one guardrail: it checks that
`Collection.model_json_schema()` still matches the real `Paleographer/schema.json`
on disk. If someone changes `models.py` in a way that no longer matches what
Paleographer expects, this test fails loudly, immediately — not months later as a
mystery bug.

**`fact_registry.py`** loads `FactTypes.json` once and builds a lookup of fact name
-> its rendering rule (GEDCOM tag, whether it uses a value/date/place, whether it's a
person-level or family-level fact). Any `Fact.fact_type` gets checked against this
list; an unrecognized name is rejected immediately, naming the bad value.

**`record_registry.py`** scans every `.pmt` file once and, per document type
(`Parish`, `Scrip`, and whatever gets added later), builds two things from that
file's front matter:

1. Its **extra fields** — from the `.pmt`'s `extra_fields.record` /
   `extra_fields.participant` lists. Each field has a declared type from a fixed set:
   `string`, `int`, `float`, `bool`, `date`, or `enum` (a fixed set of choices, e.g.
   `Cash`/`Land`). An unrecognized type name in a `.pmt` fails immediately when
   `Commissioner` loads — not the first time someone tries to use that document type.
   A `.pmt` with no extra fields at all (Parish's `extra_fields: {}`) is a normal,
   valid case — it just means that document type adds nothing beyond the base
   fields everyone shares.
2. Its **valid roles** — from the `.pmt`'s `roles` list (e.g. Parish's roles are
   Primary/Father/Mother/Spouse/.../Other; Scrip's are a completely different list:
   Claimant/Spouse/Child/Father/Mother/Heir/Witness/Commissioner/Other). A
   participant's `role_name` is checked against whichever document type produced it.

Both checks happen at the same moment, driven by "which document type is this,"
so `Record` and `Participant` stay single, stable classes matching the real
ingestion shape — there's no separate `ScripParticipant`/`ParishParticipant` class
tree to maintain.

**Note for implementation**: `Scrip.pmt`'s current `scrip_amount` field conflates two
things — a dollar figure ("$160") or a land description ("240 acres") in one string.
Splitting it into `scrip_amount` (the number) and a new `scrip_type` field
(`enum`, choices `Cash`/`Land`) is part of this pilot's implementation work — editing
`Scrip.pmt` itself is a task for the implementation plan, not done during this
design phase.

## Example: what "generic and extensible" actually means

Today, `Scrip.pmt` declares 15 record-level extra fields and 5 participant-level
ones, all typed `string`. If someone writes a new `Census.pmt` next month with its
own extra fields and its own role list, nothing in `Commissioner` needs to change —
`record_registry` reads whatever's in the new file the same way it reads the
existing two. The only case that requires a code change is a genuinely new *type*
of value the type map doesn't understand yet (something beyond string/int/float/
bool/date/enum) — and that fails loudly and immediately rather than silently
guessing.

## Error handling

Every failure case below raises immediately and names the specific problem, rather
than silently coercing, dropping data, or failing somewhere else downstream:

- Unknown `fact_type` (not in `FactTypes.json`)
- Unknown `document_type` (no matching `.pmt`)
- Unknown `type:` token in a `.pmt`'s extra fields (outside string/int/float/bool/
  date/enum) — caught when `Commissioner` loads, before any data flows through it
- A value that doesn't match its declared type (e.g. a `.pmt` says `scrip_amount` is
  a number but the AI output isn't numeric)
- An invalid `role_name` for that document type (e.g. `"Coordinator"` isn't a real
  role in Scrip's list)

Not an error: a document type with no extra fields at all (Parish today).

## Testing

Tested against the real files (`FactTypes.json`, `Parish.pmt`, `Scrip.pmt`), not
mocks, matching how `Archivist/tests` is already written:

- `fact_registry`: known fact names resolve correctly, person/family scope is
  respected, an unknown name raises.
- `record_registry`: Parish yields empty extra-field models; Scrip yields exactly
  its (updated) record/participant fields with correct types, including the new
  `scrip_type` enum; an unsupported type token in a test fixture `.pmt` raises at
  load time; an invalid role name for a given document type raises.
- A round-trip test: a small, realistic Scrip-shaped payload parses into a fully
  typed object graph with correct values.
- The `models.py` <-> `schema.json` guardrail test described above.
- Negative tests for every error case listed above.

## What comes after this pilot (not part of it)

- Wiring `Commissioner` into Paleographer/Voyageur's actual ingestion path.
- Using `fact_registry` to drive generic GEDCOM emission (no more per-fact-type
  branches).
- Retiring `schema.json` as a hand-maintained file once Paleographer no longer needs
  it maintained separately from `models.py`.
- Migrating the Census pipeline (`Archivist.py`'s `build_census_dataframe_from_unified`
  and friends) onto these models, removing that shim entirely.
