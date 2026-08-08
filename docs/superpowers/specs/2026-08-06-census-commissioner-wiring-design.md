# Wire Voyageur's Census Gather to Commissioner Validation (Sub-project 2 of the Voyageur-owns-ingestion rework)

## What this is

Sub-project 1 ("Scaffold Contract Extensibility") gave Census a `.pmt` file so
`Commissioner.record_registry.parse_collection(raw_json, "Census")` became
callable, but nothing in production code calls it — it's exercised only by
Commissioner's own tests. This sub-project wires that call into Voyageur's real
Census gather path (`A.py` for Ancestry, `FS.py` for FamilySearch) and resolves
the two gaps sub-project 1's final review deferred:

1. Census.pmt's role vocabulary was a hard allow-list with no fallback for
   Voyageur's index-sourced `role_name` values (raw source-column text like
   "Roomer", "Grandson", "Stepson" that a fixed list can never fully anticipate).
2. The `unmapped` dict-shaped `type_specific_fields` catch-all was excluded from
   Census.pmt's declared fields because Commissioner's `_PRIMITIVE_TYPE_MAP` had
   no dict/object type.

## Goals

- `parse_collection()` runs against every real Census gather (Ancestry and
  FamilySearch), as a validation/visibility check on the shape
  `normalize_census_pages()` produces.
- Family-relationship roles (Head, Wife, Husband, Son, Daughter, Father, Mother,
  Father-In-Law, Mother-In-Law — the set with real semantics in Archivist's
  family-linking vocabulary) stay a small, validated, closed set. Every other
  role_name the source records (Boarder, Servant, Roomer, Grandson, Aunt, Uncle,
  Cousin, Stepson, anything) is accepted exactly as recorded, with no validation
  error and no family-linking semantic — association-only, never a GEDCOM family
  edge.
- The `unmapped` catch-all validates as a real, inspectable, typed field instead
  of being excluded from Census.pmt's declared shape.
- A validation failure on one Census gather never crashes or blocks that gather
  — this is Commissioner validation's first production call site anywhere in the
  codebase, and hard-failing real genealogical data collection over a
  first-rollout schema gap is a bad trade.

## Non-goals (explicitly out of scope for this sub-project)

- No `role_name` → `role_semantic` derivation for Voyageur-sourced Census data.
  Commissioner's role list (open or closed) only validates that a name is
  accepted — it doesn't, by itself, produce the `role_semantic` value Archivist's
  family-linking logic consumes. That derivation currently only runs inside
  Paleographer's own AI-extraction pipeline (`Paleographer.py:1517-1518`), which
  Voyageur's index-sourced path never touches. Making Census family-linking
  actually functional is deferred to a later sub-project (when Census
  participates in Archivist linking).
- No changes to `Voyageur.py`. Confirmed dead code: nothing imports it as a
  module, nothing calls its `main()`; it's a pre-split monolith (comment at
  line 65: "CENSUS SCHEMA (folded from census_schema.py)") left behind when
  `census_schema.py`/`A.py`/`FS.py` were split out. Its own
  `normalize_census_pages()` call sites (lines 540, 1212) are not wired to
  Commissioner validation. Deleting it is a cleanup candidate for a separate,
  unrelated task — not touched here.
- No hard-fail/blocking validation mode. Deferred to sub-project 5 ("wiring
  Commissioner validation at both the Voyageur and Paleographer boundaries"),
  once the vocabulary and shape gaps this sub-project targets are proven out
  against real gather runs.
- No changes to `Commissioner.models` or `Commissioner.fact_registry`.

## Architecture

`Commissioner/record_registry.py` gains one new, fully generic mechanism: an
opt-in role-validation mode per document type, declared in `.pmt` front matter
alongside the existing `roles`/`extra_fields` blocks. This is not a
Census-specific carve-out — any `.pmt` file can set it — but every currently
existing `.pmt` file (Parish, Scrip, Census) declares it explicitly, so the
mode is always visible in the file that matters rather than relying on a silent
default a future author might not know exists.

`_DocumentTypeSchema` gains `role_validation_mode: "closed" | "open"`, read from
a new front-matter key `role_validation`. `validate_role_name()` becomes a
no-op when the mode is `"open"` — it never raises `InvalidRoleError` for that
document type, regardless of what `role_name` value arrives. Declared roles
still populate `valid_roles` and remain meaningful metadata (documenting which
names carry family semantics elsewhere), but membership is no longer enforced.

Separately, `_PRIMITIVE_TYPE_MAP` gains a `"dict"` entry mapped to
`Dict[str, Any]`, so a `.pmt` file can declare a field as an open-shaped object
instead of only string/int/float/bool/date/enum. This has no interaction with
role validation — it's a second, independent extension to the same
`_PRIMITIVE_TYPE_MAP` that sub-project 1 already established as the file to
extend when a new field shape is needed.

At the call site, Voyageur wraps its existing `normalize_census_pages()` output
in a `parse_collection()` check immediately after normalization, before the
result is written to disk. A validation failure is logged as a warning and the
gather proceeds unchanged — Commissioner validation is observational in this
sub-project, not a gate.

## Components changed

**`Commissioner/record_registry.py`**
- `_DocumentTypeSchema.__init__` gains `role_validation_mode: str` parameter.
- `_build_registry()` reads `front_matter.get("role_validation", "closed")` and
  passes it through. Missing key still defaults to `"closed"` in code (a safety
  net for any future `.pmt` file that forgets to declare it), but every
  currently existing file declares it explicitly per the Goals above.
- `validate_role_name()`: returns immediately (no-op) when
  `role_validation_mode == "open"`, before the `frozenset` membership check.
- `_PRIMITIVE_TYPE_MAP` gains `"dict": Dict[str, Any]`.

**`Paleographer/prompts/Parish.pmt`, `Paleographer/prompts/Scrip.pmt`**
- Front matter gains `role_validation: closed` (one line each). No behavior
  change — this is the explicit spelling of what was previously an implicit
  default.

**`Paleographer/prompts/Census.pmt`**
- Front matter gains `role_validation: open`.
- `roles` shrinks from the 20-entry list authored in sub-project 1 to the 9
  names with real semantics in Archivist's `FAMILY_SEMANTICS` vocabulary: Head,
  Wife, Husband, Son, Daughter, Father, Mother, Father-In-Law, Mother-In-Law.
  Extended-family terms (Grandson, Granddaughter, Nephew, Niece, Cousin,
  Brother, Sister) and non-family terms (Boarder, Servant, Lodger, Roomer,
  Other) are removed from the declared list — they now fall through to open
  validation like any other source-recorded text, since Archivist has no
  semantic category for them today.
- `extra_fields.participant` gains `unmapped: {type: dict}`.

**`Voyageur/A.py`** (~line 163) and **`Voyageur/FS.py`** (~line 898)
- Immediately after each file's `normalize_census_pages()` call, wrap a call to
  `Commissioner.record_registry.parse_collection(normalized, "Census")` in
  `try/except Exception`. On any exception, log a warning including the
  collection title and the exception text. The normalized dict is written to
  disk exactly as today in both the success and failure case — this call is a
  side-effecting check only, never a mutation or a gate.

## Data flow

Before: `normalize_census_pages()` output is written straight to JSON with zero
validation. `role_name` values pass through as raw source-column text with no
constraint. The `unmapped` bucket exists in the output but was invisible to
Commissioner's declared shape.

After: the same output additionally passes through `parse_collection()`. Family
roles are checked against the 9-name closed set; every other `role_name` value
is accepted unconditionally. `unmapped`'s dict contents validate as a real
declared field. On success, nothing about the written output changes. On
failure (e.g. a genuinely new record-level field `census_schema.py` starts
producing that Census.pmt hasn't declared), a warning is logged and the file is
still written — validation gaps surface as something to fix, not lost data or a
crashed gather run.

## Error handling

No new exception types. `InvalidRoleError` can no longer fire for Census (open
mode) — it remains reachable only for Parish/Scrip, unchanged from today.
`UnknownFieldTypeError` and Pydantic `ValidationError` remain reachable for
Census (e.g. an `unmapped` value that isn't dict-shaped, or an entirely new
undeclared field) — caught at the `A.py`/`FS.py` call sites per the soft-fail
policy above, never propagated to crash the gather or reach the caller.

## Testing

- `Commissioner/tests/test_record_registry.py`:
  - New test: a document type with `role_validation: open` in its front matter
    accepts an undeclared `role_name` (e.g. `"Roomer"`) without raising.
  - New test: the same open-mode document type still accepts a declared role
    name (e.g. `"Head"`) without raising — open mode doesn't remove roles from
    `valid_roles`, it only stops enforcing membership.
  - New test: a document type with `role_validation: closed` (or the key
    absent) still raises `InvalidRoleError` for an undeclared role — proves the
    default is unchanged from sub-project 1's behavior.
  - New test: a field declared `type: dict` accepts a nested dict value via
    `validate_participant_extra_fields`/`validate_record_extra_fields`.
  - Existing Parish/Scrip tests continue to pass unmodified — proves adding
    `role_validation: closed` to those `.pmt` files is behavior-neutral.
- `Voyageur/tests/`: a test on the post-`normalize_census_pages()` step in
  `A.py` (or a shared helper if the try/except is factored out to avoid
  duplicating it between `A.py` and `FS.py`) confirming a `parse_collection()`
  exception is caught and logged, and the gather's return value / written file
  is unaffected either way.

## What comes after this sub-project (not part of it)

- Sub-project 3: Voyageur building the Commissioner-shaped scaffold (images +
  empty-content records) for Parish and Scrip. Done.
- Sub-project 4: wiring soft-fail Commissioner validation into Paleographer's
  own MASTER_DB write boundary (`save_master_db`), matching the pattern
  Voyageur already has at `census_schema.py`/`FS.py`/`LAC.py`, plus
  deduplicating that repeated try/except-log-WARN shape into one shared
  `Commissioner.record_registry.validate_soft()` helper all four sites call.
  Untested in production so far — a hard-fail/blocking mode for Census (and
  everything else) stays explicitly deferred until the now-four-site soft-fail
  rollout has actually surfaced real-world shape gaps to react to.
- Sub-project 5: cross-script invocation (Paleographer/Voyageur calling into
  each other's real functions when one needs what the other gathers).
- Sub-project 6: reworking Paleographer to consume the Sub-project 3 scaffold
  as pure analysis, never constructing the base JSON structure itself — and,
  folded into the same sub-project per explicit user direction, the broader
  structural rebuild `Paleographer.py` (2142 lines) needs: it's still four
  historically separate files (`engine.py`, `agy_engine.py`, `postprocess.py`,
  a Commissioner/DEV Scrip-enrichment block) stitched together behind banner
  comments rather than re-architected into real module boundaries, with
  legacy wrappers/shims kept "for test-suite compatibility." Moved to last in
  the sequence (was Sub-project 4) per explicit reprioritization.
- Census family-linking: a `role_name` → `role_semantic` derivation path for
  Voyageur-sourced data, and/or extending Archivist's `FAMILY_SEMANTICS`
  vocabulary to cover extended-family relationships (grandchild, sibling,
  aunt/uncle, cousin) if that's ever wanted. Neither is scoped to any
  currently-planned sub-project; would need its own brainstorm.
