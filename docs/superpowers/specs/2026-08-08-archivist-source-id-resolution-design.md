# Archivist Source ID Resolution — Design

> **Continuation note:** This document covers only Source ID resolution, the
> first item from a larger Archivist settings-tab review. The remaining
> items — Citation & Role Vocabulary rename/scoping with a record-type
> dropdown, `GEDCOM_OUTPUT_MODE` becoming a dropdown, Location Overrides
> split per record type, Family Inference Tuning gated to Census only, and a
> general settings tab-placement/duplication audit — are deferred to a
> follow-up brainstorming pass once this document's implementation is
> complete.

## Goal

Replace Archivist's current `@Sxxx@`/`REFN` source-numbering schemes —
a persistent sequential registry for Parish/general, a `vol`-digits formula
for Scrip, and a hardcoded constant for HBCA — with resolution based on
each gather platform's own real collection identifier, when one is known.
This eliminates the risk of a generated `@Sxxx@` colliding with an
unrelated, pre-existing source already in the destination RootsMagic/FTM
database, and gives re-imports of the same collection a stable ID to merge
against. Falls back to the existing manual `REGISTER_SOURCE_ID` setting
only when the gather source is unknown (e.g. an ad hoc, unindexed image
source with no platform metadata at all).

## Background

Confirmed by reading the current code (`Archivist/Utils.py`,
`Archivist/Scrip.py`, `Archivist/HBCA.py`, `Archivist/General.py`):

- **Census** — `Utils.PRECODED_SOURCE_IDS`, a fixed table (`Census_1900` →
  `1001`, `Census_Slave_Schedule` → `1020`, etc.). Already stable and
  collision-resistant by construction; not a problem case.
- **Parish / general / manual** — `Utils.resolve_source_id()`, a persistent
  local registry (`Archivist/source_id_registry.json`) assigning
  sequential numbers from 1030 up, keyed on `(record_type_name,
  collection_name)`.
- **Scrip** — `ScripProfile.dynamic_source_id(vol_digits)`: builds
  `@S{vol_digits.zfill(3)}@` directly from the scrip record's own `volume`
  field (e.g. volume `7` → `@S007@`). Small, low numbers — real collision
  risk against sources already present in a destination database.
- **HBCA** — `HBCAProfile.dynamic_source_id()`: hardcoded, always returns
  `@S10009@` for every record regardless of which collection it came from.
  `10009` is actually RootsMagic's own citation *template* ID
  (`HBCA_TEMPLATE_ID`, used for `_TMPLT`/`TID`), reused to double as the
  GEDCOM source XREF — a coincidence, not a real HBCA identifier, and only
  avoids collision by luck (>2000).

Separately, and *not* changed by this design: `APID_DB` (Ancestry's
per-collection `dbid`, used to build `_APID` citation tags and record
links) and `ANCESTRY_IMAGE_BASE_ID` (a Census-only fallback image-filename
stem, used only when a row's own `Image_ID` is missing — confirmed in this
session to still be used and still needed as-is). Both are already correct
for their existing purposes.

## Design principle

Source ID should represent the real-world collection the material was
gathered from, using that platform's own stable identifier:

- **Read directly** when the platform already exposes a per-collection ID
  reachable from gathered data (Ancestry `APID_DB`, FamilySearch `cc`).
- **Resolved structurally** when the platform exposes collection membership
  through a hierarchy/breadcrumb rather than a flat ID (LAC's MIKAN number,
  Keystone's REFD number) — parsed from a page the gather step already
  fetches, not a new bulk-scraping pass.
- **Manual fallback** (`REGISTER_SOURCE_ID`) only when none of the above
  resolves.

## Per-source-type mechanism

### Ancestry Gather — `APID_DB`

Already correctly captured (`Voyageur/A.py` parses `dbid` from the gather
URL; threaded through to `Census.py`'s `APID_DB` / per-row `apid_db`
field). No new capture work needed. The change is on the consuming side:
Source ID resolution uses `APID_DB` as the `@Sxxx@` value directly when
present for the record's gather source, instead of the sequential registry.

### FamilySearch Gather — `cc` (collection code)

New capture. Confirmed live: an FS record page's own URL carries
`cc=<number>` (e.g.
`https://www.familysearch.org/ark:/61903/3:1:S3HY-67N2-GZ?view=index&cc=1401638&lang=en`)
— FamilySearch's own collection code, the platform's equivalent of
Ancestry's `dbid`. `Voyageur.js`'s `runFamilySearchGather()` (specifically
alongside its existing `getItemId()`, which already parses the `ark:`
portion of `window.location.pathname`) needs to also read
`new URLSearchParams(window.location.search).get('cc')` and thread it into
the citation dict `FS.py` builds — currently a hardcoded blank
`"apid_db": ""` placeholder (`FS.py:493`, `FS.py:667`) stands where this
value belongs.

### Scrip (LAC) — MIKAN

Confirmed live against a real record (PID `1502188`, "Scrip affidavit for
Letendre, Roger..."). LAC's record page renders a hierarchy breadcrumb
(`#jq-context-ul-hierarchycontext-fonandcol{pid}`, nested inside the
accordion body `lac_client.py` already touches for other fields but doesn't
currently parse this element) as an ordered `<li>` list from the root fonds
down to the item itself. Each level has a real link,
`<a href="https://central.bac-lac.gc.ca/.redirect?app=FonAndCol&id={MIKAN}&lang=eng">{label}</a>`,
plus a second, textless "bilingual equivalent" `<a>` per level that must be
filtered out by requiring non-empty link text.

For PID 1502188: "Department of the Interior fonds" (id=30) → "Dominion
Lands Branch" (id=134031) → "Métis and Original White Settlers affidavits"
(id=134034) → the item itself (id=1502188, matches the PID). The
**second-to-last** entry — the item's immediate parent — is the collection:
MIKAN `134034` in this example.

**Mechanism:** extend `lac_client.RecordMetadata` (currently `pid`,
`title`, `digital_object_count`, `reel_numbers`, `series_code`) with a new
`collection_mikan: Optional[str]` field, parsed from the same `soup`
`get_record_metadata()` already fetches — no extra HTTP request. Walk the
hierarchy `<li>` elements in DOM order, take each level's first `<a>` with
non-empty text and an `id=(\d+)` in its `href`, and take the
second-to-last `(id, label)` pair as `collection_mikan`. If the hierarchy
has fewer than 2 levels, leave it `None` (falls back to
`REGISTER_SOURCE_ID`).

This is structural — relative to the leaf item, not a fixed absolute depth
— so it holds regardless of how many fonds/branch levels sit above a given
item, and generalizes automatically to Parish or any future LAC-gathered
record type, not just Scrip (per explicit requirement: "the script itself
will need to identify the collection MIKAN number for the record... when
other record types from LAC are captured").

**Superseded:** the `vol_digits`-based `@S{vol}@` formula in
`ScripProfile.dynamic_source_id()`.

### HBCA — Keystone REFD

Confirmed live against two real HBCA location codes via Archives of
Manitoba's Keystone/MINISIS database:

- `B.239/g/13` → "Northern Department abstracts of servants' accounts" →
  `.../DESCRIPTION_WEB_ACCESS/REFD/9295?JUMP`
- `E.4/1a` → "Extracts from registers of baptisms, marriages and burials in
  Rupert's Land sent to the Governor and Committee" →
  `.../DESCRIPTION_WEB_ACCESS/REFD/14374?JUMP`

This confirms REFD is a real, stable, purely numeric identifier, distinct
per fonds/series, discoverable by searching Keystone for a given
`hbca_references` code (`build_keystone_search_url`, already implemented in
`Voyageur/HBCA.py`) and parsing the resulting item page's
`.../REFD/(\d+)?JUMP` link.

**Mechanism:** revive/extend the existing but currently-disabled-by-default
`resolve_keystone`/`HBCA_RESOLVE_KEYSTONE` gather-time path
(`query_keystone_for_code` etc.) to also capture each reference's REFD, not
just its record/media URLs. Note: `hbca_references` extraction itself has
already moved to `HBCA.pmt`'s AI extraction, superseding the old
regex-based `extract_hbca_location_codes` in `HBCA.py` (confirmed with the
user during this session) — the Keystone resolution step needs to read from
the pmt-extracted `type_specific_fields.hbca_references` list, not
re-derive references from raw PDF text itself.

**Structural change:** because a single biographical sheet can carry
multiple `hbca_references` codes belonging to different series (confirmed
live above — the two test codes resolve to two different REFDs), each
reference gets its own citation pointing at its own REFD-resolved Source —
not today's single-citation-per-record, single-shared-`@S10009@`
model. `HBCAProfile`'s citation-building methods
(`citation_title`, `citation_page`, `citation_template_id`, etc.) and
`General._build_citation_block`'s call site need to move from "one
citation per record" to "one citation per reference," for HBCA
specifically. The exact code shape (a loop inside `_build_citation_block`,
vs. `HBCAProfile` returning a list of citation blocks) is a planning-phase
decision, not fixed by this design.

**Superseded:** the hardcoded `@S10009@` as the source ID. Note:
`HBCA_TEMPLATE_ID = 10009` likely still has a legitimate, separate life as
the RM citation *template* ID (`2 TID {HBCA_TEMPLATE_ID}` in
`resolve_source_templates`) — that usage is unrelated to source *identity*
and stays as-is; only its reuse as the `@Sxxx@` XREF is being replaced.

### Unknown/manual source — `REGISTER_SOURCE_ID`

Unchanged. The existing manual setting (default `"1"`) is used only when no
platform-derived collection ID resolves: LAC's hierarchy is too shallow, an
HBCA reference doesn't resolve via Keystone, or the images came from an ad
hoc/unindexed source with no gather-source metadata at all.

## Scope

### In scope (this document)

- `FS.py` / `Voyageur.js`: capture `cc` from the FS record page URL,
  replacing the blank `apid_db` placeholder in the citation dict.
- `lac_client.py`: extend `RecordMetadata` with `collection_mikan`, parsed
  from the existing hierarchy breadcrumb already present in the fetched
  record page.
- `Voyageur/HBCA.py`: extend Keystone resolution to capture REFD per
  `hbca_references` code, reading references from the pmt-extracted
  `type_specific_fields.hbca_references` list.
- `Archivist/General.py` / `HBCAProfile`: support one citation + one
  resolved Source per HBCA reference, instead of one shared Source per
  record.
- Archivist Source ID resolution logic: prefer the platform-derived ID
  (`APID_DB` / `cc` / `collection_mikan` / REFD) for the active gather
  source when present; fall back to `REGISTER_SOURCE_ID` only when none
  resolves.
- `ScripProfile.dynamic_source_id`: replaced by `collection_mikan`-based
  resolution.

### Explicitly out of scope (deferred to the follow-up pass)

- Citation & Role Vocabulary section rename/scoping to true
  manual-fallback-only fields, gated by a record-type dropdown.
- `GEDCOM_OUTPUT_MODE` becoming a dropdown (RM/FTM/Both) instead of free
  text.
- Location Overrides split per record type.
- Family Inference Tuning gated to Census only.
- General settings-tab correctness audit (each setting defined once, in
  the correct tab).
- `ANCESTRY_IMAGE_BASE_ID`: confirmed in this session to be used
  (Census-only fallback image-filename stem when a row's own `Image_ID` is
  missing) and still needed as-is — no design change; noted here only so
  the finding isn't lost before the follow-up pass.

## Testing

Following the existing project convention (golden-file regression tests
already established for the Archivist structural split):

- Unit tests for the LAC hierarchy-breadcrumb parser, against fixture HTML
  captured during this session's live investigation (the two real claim
  pages fetched above make good fixtures).
- Unit tests for the Keystone REFD parser, against fixture HTML from the
  two real Keystone item pages fetched above.
- Unit tests for FS's `cc` capture, against a fixture URL.
- Unit tests for `HBCAProfile`'s new per-reference citation building.
- Full `pytest` suite stays green throughout.

## Open questions for the planning phase

- Exact JSON field names for FS's `cc` and LAC's `collection_mikan` (this
  design specifies the source and mechanism, not the final schema key
  names).
- Exact code shape for `HBCAProfile`'s per-reference citation building
  (loop inside `_build_citation_block` vs. a list-returning profile
  method).
- Whether Ancestry-gathered Census records should also switch to
  `APID_DB`-based resolution, or keep `PRECODED_SOURCE_IDS` as-is. Census's
  existing scheme already has no collision problem; this design's
  motivating cases (Scrip, HBCA) don't include Census, and the user's
  original ask ("Source ID should be the same as the Ancestry APID when
  Ancestry Gather") wasn't scoped record-type-by-record-type during this
  session — confirm intent before implementation begins rather than
  silently overriding a scheme that already works.
