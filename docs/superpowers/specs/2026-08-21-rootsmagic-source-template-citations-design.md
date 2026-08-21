# RootsMagic Source Template Citation Wiring — Design

> Branch: `fix/rm-source-template-citation-linking`

## Problem

RootsMagic custom Source Templates (`Archivist/Source Templates/*.rmst`) exist in the
repo and are already loaded and emitted into GEDCOM output, but real imports show every
citation falling back to **Free Form** in RootsMagic instead of picking up the intended
template. Confirmed against a real export
(`Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS-RM.ged`) and a real
RootsMagic-exported reference file the user produced from their live database
(`C:\Users\Jason Cole\Documents\Genealogy\Antiquarian\GEDCOM\test.ged`, referred to
below as `test.ged`).

Two independent classes of bug, plus one content-drift issue and one selection-logic
issue, all found by diffing our current output/code against `test.ged`:

1. **Wrong GEDCOM tag vocabulary.** `_rmst_element_to_gedcom` (duplicated in
   `Census.py` and `General.py`) emits `_SRCTEMPLATE`/`FOOT`/`BIBL`/`DISP`/`DETL`/`LHNT`.
   RootsMagic's real export uses `_STMPLT` (with the name as a separate `1 NAME` line,
   not inline on the tag) and `FOOTNOTE`/`BIBLIO`/`DISPLAY`/`ISDETAIL`/`LONGHINT`. RM's
   importer doesn't recognize the tags we currently emit, so the embedded template
   definition itself is invisible to it.
2. **Wrong citation-level `_TMPLT` structure.** Every citation builder (`Census.py`'s
   `build_census_citation`, `Scrip.py`'s `get_scrip_citation_fields`, `General.py`'s
   `GeneralProfile.citation_detail_fields`, `HBCA.py`'s `citation_detail_fields`) emits
   bare `3 FIELD`/`4 NAME`/`4 VALUE` lines directly under the citation's `2 SOUR`
   pointer, with no `_TMPLT` wrapper at all. RM only recognizes citation-level Detail
   field data as belonging to a template when it's nested under a `_TMPLT` tag. Per
   `test.ged`, that citation-level `_TMPLT` carries **no `TID`** (the TID lives once, on
   the master `SOUR` record) and sits **after** `PAGE`/`_TITL`, not before.
3. **Scrip template content has drifted from the user's live RootsMagic database.**
   `Metis Scrip.rmst` and `Scrip.py`'s `_SIMPLIFIED_CITATION_TEMPLATES` dict describe an
   older "Simplified Citations" design (6 master fields, `Accessed`/`RefNumber` detail
   fields, `* Simple Citations: ...` naming) that no longer matches the templates
   actually installed in the user's RootsMagic 11 database, which `test.ged` proves use
   a simplified field set, `!`-prefixed names, and different footnote/bibliography text.
4. **Scrip template *selection* is separately broken.** `resolve_scrip_template_id`
   reads `document_type` from `type_specific_fields`, but real Voyageur/Commissioner
   data puts it under `source_documents[].document_type` instead — so the
   certificate/receipt shortcut never fires. The Certificate (20004) and Land Grant
   (20005) templates also have an empty `date_range` list, so the year-based fallback
   can never select them either. Fixing the GEDCOM structure is moot if no template ID
   is ever resolved for a record in the first place.

## Non-goals

- Census, Parish/Non-traditional, Traditional, and Master Template TIDs (`10008`,
  `10009`, `10010`, `10006`) are **not** renumbered — no evidence they're wrong.
- FindAGrave (previously `10001`, now colliding with the real North-West Scrip TID) is
  dropped entirely, not reassigned a new TID. Not building for it currently; can be
  revisited later.
- No change to the `.rmst` XML schema itself (`<Template>`/`<Field>` structure) — it
  already carries everything needed (`Type`, `Name`, `Display`, `Hint`, `Detail`,
  `LongHint`). Only the GEDCOM it's translated *into* is wrong.
- No change to how `load_source_template_lines` locates `.rmst` files (directory search
  order untouched).

## Design

### 1. Tag-vocabulary rewrite (`_rmst_element_to_gedcom`, duplicated in `Census.py` and `General.py`)

Rewrite to emit, in this order:

```
0 _STMPLT
1 TID <id>
1 NAME <name>
1 DESC <description>            (wrapped, see below)
1 CAT <category>
1 FOOTNOTE <footnote>           (wrapped)
1 SHORT <short footnote>        (wrapped)
1 BIBLIO <bibliography>         (wrapped)
1 FIELD
2 NAME <field name>
2 DISPLAY <display>             (wrapped, if present)
2 HINT <hint>                   (wrapped, if present)
2 LONGHINT <longhint>           (wrapped, if present)
2 TYPE <TYPE UPPERCASED>
2 ISDETAIL <Y/N>
```

Confirmed field sub-tag order against `test.ged`: `NAME`, `DISPLAY`, `HINT`,
`LONGHINT` (when present), `TYPE`, `ISDETAIL`.

`TYPE` values in the `.rmst` XML are title-case (`Text`, `Name`, `Place`, `Date`) but
must be emitted upper-case (`TEXT`, `NAME`, `PLACE`, `DATE`) to match `test.ged`.

**Line-wrapping fix.** The existing `_gedcom_text_lines` helper only splits on literal
`\n` in the source text (via `CONT`), which is correct for genuine paragraph breaks
(e.g. `DESC`'s multi-paragraph text) but does **not** enforce GEDCOM 5.5.1's 255-byte
line limit within a paragraph — `FOOTNOTE`/`BIBLIO`/long `HINT`/`LONGHINT` text can
exceed that today, emitted as one long line. `test.ged` confirms RM's own export
wraps long single-paragraph text using `CONC` continuation lines (one level deeper,
mid-word breaks are fine — RM doesn't preserve word boundaries when wrapping).
Replace `_gedcom_text_lines` with a helper that:
- Splits on `\n` first (paragraph boundaries) → `CONT` for each new paragraph.
- Within each paragraph, if it exceeds a safe threshold (~200 chars), further splits
  and continues with `CONC` at the same level+1.

Apply this new helper to `DESC`, `FOOTNOTE`, `SHORT`, `BIBLIO`, `HINT`, and `LONGHINT`
wherever multi-line output is possible today.

### 2. Citation-level `_TMPLT` structure (4 call sites)

In each of the four citation builders, wrap the citation's Detail-field lines as:

```
3 _TMPLT
4 FIELD
5 NAME <field>
5 VALUE <value>
...
```

(No `4 TID` line.) Placed in the citation block **after** `_TITL`/`PAGE` and **before**
`DATA`, matching the existing tag order otherwise. Applies uniformly to Census, Scrip,
General/Parish, and HBCA citation builders — this is a citation-level GEDCOM mechanic,
independent of which specific template a citation uses.

Master-source-level `_TMPLT`/`TID`/`FIELD` structure (`1 _TMPLT`/`2 TID`/`2 FIELD`/
`3 NAME`/`3 VALUE`) is already correct today (confirmed both by `test.ged`'s master
`@S1@ SOUR` example and by our existing `get_census_sources`/`get_scrip_template_sources`/
`volume_source_detail_fields` code) — **no change** needed there.

### 3. Scrip template content rebuild

`Metis Scrip.rmst` and `Scrip.py`'s `_SIMPLIFIED_CITATION_TEMPLATES` (TIDs `20001`–`20005`,
unchanged numbering) are rebuilt field-for-field from `test.ged`'s `_STMPLT` blocks:

| TID | Template | Master fields | Detail fields (dropped: `Accessed`, `RefNumber`) |
|---|---|---|---|
| 20001 | Métis Scrip: Manitoba (1870–1876) | Commission, Collection, Repository | ClaimantName, AffidavitNumber, Parish, ScripType, Volume, Microfilm, URL |
| 20002 | Métis Scrip: North-West (1885 & 1900-1901) | Commission, Collection, Repository | ClaimantName, ClaimNumber, ScripNumber, IssueDate, Location, Volume, Microfilm, URL |
| 20003 | Métis Scrip: Treaty 8 (1899-1908) | Commission, Collection, Repository | ClaimantName, ClaimNumber, ScripAmount, ScripNoteNumber, DeliveryDate, DeliveryPlace, Volume, URL |
| 20004 | Métis Scrip: Certificate | Commission, Collection, Repository | ClaimantName, ScripType, CertificateNumber, Amount, IssueDate, Volume, Microfilm, URL |
| 20005 | Land Records: Dominion Land Grant Patent | Collection, Repository (no Commission) | GranteeName, OriginalClaimant, LandDescription, IssueDate, Liber, Folio, Microfilm, URL |

Names get the `!` prefix (dropping the "Simple Citations:" phrasing entirely, per
`test.ged`'s exact wording — e.g. `!Métis Scrip: Manitoba (1870–1876)`, not
`!Simple Citations: Métis Scrip...`). Category becomes `Canadian Records`. Footnote,
ShortFootnote, and Bibliography text transcribed verbatim from `test.ged`.

Every field name in the new design already has a working value source in
`_scrip_template_field_value` or the template dict's own static values — no new field
mappings need inventing.

`get_scrip_template_sources` (master `SOUR` builder) simplifies from
6 possible master `FIELD` entries down to 2–3 (`Commission` when present, `Collection`,
`Repository`), dropping the `PrimaryCreator`/`Department`/`Date`/`SourceDescription`
computation entirely.

FindAGrave's dict entry (`10001`) is deleted outright (dead code, unused elsewhere,
now numerically colliding with the real North-West Scrip TID).

### 4. Census / Parish / Traditional / Master Template — mechanical fixes only, plus field-list reconciliation

These four keep their current TIDs (`10008`, `10009`, `10010`, `10006`), field content,
and `"* Simple Citations: ..."` naming pattern — only the `*` → `!` prefix swap and the
two universal mechanics (Sections 1–2) apply. Reading each `.rmst` file directly (per
the user's direction — the `.rmst` files are themselves the authoritative field-usage
reference) surfaced real deltas between the `.rmst` definitions and the current Python
dict that should be reconciled while this code is already being touched:

- **Census (10008):** `.rmst` defines a `PersonalID` detail field (never referenced in
  Footnote/Bibliography — it's a personal cataloging field, "use whatever numbering
  method you like") that's missing from `_SIMPLIFIED_CITATION_TEMPLATES[10008]`. Add it
  to `detail_fields`; it's fine to leave unpopulated (our data model has no such value)
  since the existing `if f_val:` skip-when-empty pattern already handles that.
- **Non-traditional (10009):** the dict's `master_fields` wrongly includes `Publisher`
  and `PublishLocation` — **not present** in the real `.rmst` at all. Remove them. Also
  missing `PersonalID` from `detail_fields` (same treatment as Census).
- **Traditional (10010):** dict is missing `Title` from `master_fields` and `PersonalID`
  from `detail_fields`.
- **Master Template (10006):** dict is missing `Author`, `Role`, `BookTitle`,
  `Subtitle`, `Title` from `master_fields`, and `PersonalID` from `detail_fields`.

`10006` (Master Template) and `10010` (Traditional) are confirmed **not currently wired
to any citation path** (`citation_template_id`/`resolve_source_templates` never
resolves either TID today) — fixing their field lists is hygiene with zero behavioral
impact right now, but low-cost since this code is already being rewritten.

### 5. Scrip template-selection bugs (`resolve_scrip_template_id` / `select_scrip_template_id`)

- `select_scrip_template_id`'s `document_type` check (`"certificate" in doc_l or
  "receipt" in doc_l`) currently only inspects `rec['type_specific_fields']
  ['document_type']`. Real data carries this under
  `rec['source_documents'][*]['document_type']` instead. Check both locations.
- `_SIMPLIFIED_CITATION_TEMPLATES[20004]` (Certificate) and `[20005]` (Land Grant) have
  `'date_range': []` — the year-fallback loop (`any(lo <= year <= hi for lo, hi in
  tpl['date_range'])`) can never match an empty list, so a record that should fall
  through to one of these two templates by year alone never does. Populate reasonable
  ranges: Certificate `1870–1906` (matches its existing `date_range_str`), Land Grant
  `1870–1930` (same).

### 6. Verification

- Trace `Footnote`/`ShortFootnote`/`Bibliography` for all 5 rebuilt Scrip templates
  (plus Census and Parish, which already have real fixture data in the test suite)
  against representative real field values, evaluating RM's template mini-language
  (`[Field]` substitution, `<...>` optional clauses, `<?[Field]|A|B>` conditionals,
  `:Caps`/`:Surname` modifiers) by hand to confirm each produces a grammatically
  correct citation sentence with no dangling punctuation when optional fields are
  empty.
- Golden-file regression tests (`Archivist/tests/golden/*.ged`) regenerated via
  `capture_golden_gedcom.py` only where the diff is exactly the intentional structural
  change (per `AGENTS.md`'s golden-file discipline — never to paper over an
  unintentional regression).
- Full `Archivist/tests/` suite green.
- Real output regenerated (`Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS-RM.ged`
  or equivalent) and inspected by hand for the corrected `_TMPLT` structure before
  calling this done; actual RootsMagic import verification is on the user, since no RM
  instance is available to this agent.

## Files touched

- `Archivist/Census.py` — tag-vocabulary rewrite, citation `_TMPLT` fix.
- `Archivist/General.py` — tag-vocabulary rewrite, citation `_TMPLT` fix (Parish),
  field-list reconciliation for 10006/10009/10010's dict entries lives in `Scrip.py`
  but their citation-detail-field builders live here — verify field lists used match
  the corrected dict.
- `Archivist/Scrip.py` — `_SIMPLIFIED_CITATION_TEMPLATES` rebuild (20001–20005 content,
  10006/10008/10009/10010 field-list reconciliation, 10001 FindAGrave removal),
  `get_scrip_template_sources` simplification, `get_scrip_citation_fields` `_TMPLT` fix,
  `select_scrip_template_id`/`resolve_scrip_template_id` selection-logic fixes.
- `Archivist/HBCA.py` — citation `_TMPLT` fix.
- `Archivist/Source Templates/Metis Scrip.rmst` — content rebuild per Section 3.
- `Archivist/tests/test_archivist.py`, `Archivist/tests/test_census_ingestion.py` —
  assertion updates for the new nesting level/structure.
- `Archivist/tests/golden/*.ged` — regenerated where the diff is the intentional
  structural change only.
