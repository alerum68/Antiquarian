# FamilySearch Household-View Gather — Design

## Goal

FamilySearch replaced the classic "Image Index" tab (a single `<table>` with
dynamic per-role columns — `Name`, `Father's Name`, `Mother's Name`, ...) with
a "Names" side panel that groups every person on the current image into
explicit household sections, each with its own relationship labels and a
per-person detail view. `Voyageur.js`'s `scrapeIndexRows()` (the DOM scraper
behind `Voyageur/FS.py`'s gather) targets the old table and no longer finds
one. This design replaces it with a scraper for the new panel, confirmed live
against a real record (Minnesota, 1850 federal census, Joseph Rolette
household, `familysearch.org/ark:/61903/3:1:S3HY-67NL-ZP`).

`downloadFsImage()` (the separate image-download path) was also live-tested
against the same record and needs no change — see Background.

## Background

### What changed, confirmed live

- Clicking "Names" (replacing the old "Image Index" tab) opens a panel
  listing every household visible on the current image as a heading
  (`"{Primary Name} Household"`) + subtitle (`"{record type} | {year} |
  {place}"`) + a list of member buttons, each showing name and a role label
  ("Primary", "Primary | Spouse", "Primary | Child").
- **Role labels are not always real relationship data.** On the same image,
  the Rolette household had correct compound labels; three neighboring
  households (Cardinal, Matwein, Dejarlais) showed *every* member as bare
  "Primary" — an artifact of older per-person census indexing that predates
  relationship capture, now just visually clustered into a "household" with
  no real relationship metadata. Any design here must tolerate a household
  with no relationship data at all, same as the old table did when a
  Relationship-to-Head column was absent.
- **Duplicate entries exist within one household's list** (e.g. "Josette
  Cardinal" appeared twice) — multiple indexing passes surfacing together.
- Clicking a member's "Click to view {name}" button opens a "View Name" panel
  with labeled sections: Tree Attachment (if attached), Essential Information
  (Given Name, Surname, Sex), Household Details (the same roster again, keyed
  by relationship-to-primary: Spouse/Child/"No Relation"/etc.), Events (e.g.
  "Census • Primary Event": Date/Country/County/Place/Township/State; Birth:
  State/Place), Additional Facts (Age, Source Schedule Type, Race). Field
  *sets* vary per record type/collection — this is not a fixed schema.
- Two distinct ark-shaped identifiers, easily confused (this document's own
  earlier draft got them backwards once):
  - **record_ark** (e.g. `MZ2Z-WM4`) — identifies this specific indexed
    entry, from the "VIEW RECORD" link's href
    (`/ark:/61903/1:1:{record_ark}?lang=en`). Always present. Safe for a
    citation web link. This is what the old code's `person_ark` variable
    already held — the variable name was simply wrong.
  - **person_ark == PID** (e.g. `9CJG-851`) — the real Family Tree person
    identity, only present when the record is attached in Family Tree, from
    the Tree Attachment section's link. **The href pattern changed**: old UI
    used `/tree/person/details/{PID}`; new UI uses `/en/tree/person/{PID}`
    (no `/details/` segment) — `Voyageur.js:1401`'s regex
    (`tree\/person\/details\/(...)`) no longer matches and must be updated
    regardless of anything else in this design.
- The private `platform/records/collections/{id}?arkName=...` API (which
  would have let the whole panel be read as one JSON response instead of N
  DOM reads) returned 401 even called from the authenticated page's own JS
  context — it needs a bearer token this design does not attempt to extract
  (out of scope: token extraction borders on credential handling). Scraping
  stays DOM-based.

### Image download — unaffected, no change needed

Live-clicking the image viewer's "Download" button (selecting "JPG Only")
hit `https://sg30p0.familysearch.org/service/records/storage/deepzoomcloud/dz/v1/apid:{item_id}/$dist`
and returned 200. This is character-for-character the same URL
`downloadFsImage()` (`Voyageur.js:1509-1510`) already fetches via a hidden
same-origin iframe (a deliberate workaround for cross-origin blocking on a
direct fetch, per that function's own comments). The visible "Download"
button is a different, human-facing code path from what the automation
actually uses; automation was never at risk here. **No change.**

### Why this is a smaller change than it first looked: the census path already tolerates this

`Voyageur/FS.py` has two independent output paths, chosen by
`detect_record_family_from_raw()`:

- `build_universal_json()` → `row_to_record()`, which reads
  `ROLE_COLUMN_MAP`/`SEX_COLUMN_MAP` (Parish-shaped columns: `Name`,
  `Father's Name`, `Mother's Name`, ...) and feeds `Archivist/General.py`'s
  explicit-role pipeline. Used for parish/church-register gathers.
- `build_census_json()` → the *same* `{census_year, location, pages: [...]}`
  shape `Voyageur/A.py`'s Ancestry gather already produces, deliberately
  (see that function's own docstring: "census data has no sacramental roles,
  it needs dwelling/family numbers and relationship-to-head, which
  Archivist's existing census-flavor pipeline already knows how to handle").
  This feeds `Archivist/Census.py`, which infers households from a
  `Relationship to Head`-shaped column
  (`Census.py:448`'s `RELATIONSHIP_COLUMN_CANDIDATES`, matched via
  `find_relationship_column`/`is_relationship_column` — any column name
  containing both "relation" and "head") and a `Family Number`/`Dwelling
  Number`-shaped column (`Census.py:1065`'s candidate list), tolerating
  either being fully absent (a known, already-handled real-world condition —
  see `row_to_record`'s own docstring on ~85% of rows lacking locators).

Given this, **`build_census_json()` and `Census.py` need no code changes.**
The new UI's household grouping is *more reliable* than what the old table
gave Census.py to infer from — each household section on the page is a
ready-made dwelling/family group, and `normalize_relationship()`
(`Census.py:464`) already recognizes plain-English values FamilySearch's own
Household Details panel uses verbatim (`REL_SPOUSE` = {wife, husband,
spouse}, `REL_CHILD` = {son, daughter, child, ...}). The only work is making
`Voyageur.js`'s scraper produce a `row.columns` dict shaped the way it always
did — `Relationship to Head`, `Family Number`, `Given Name`/`Surname` (or
`Name`), `Sex`, `Age`, plus whatever else a given collection's Additional
Facts/Events sections expose — just sourced from the new panel's structured
fields instead of table cells.

This design is scoped to the **census case**, the one confirmed live. Whether
FamilySearch's parish/church-register collections have *also* moved to this
new panel is unconfirmed — the existing `row_to_record()`/`ROLE_COLUMN_MAP`
path is untouched by this design and should be spot-checked against a live
parish collection before or during implementation; if it has also changed,
it needs the equivalent scraper rewrite feeding its own (already-existing)
column shape instead.

## Architecture

- **`Voyageur.js`**: replace `scrapeIndexRows()` with a new
  `scrapeNamesPanel()`:
  1. Click "Names" (`findByExactText`, same convention as today's
     `clickTab('Image Index')`) instead of "Image Index".
  2. Wait for either a household heading to render or the panel's own empty
     state (mirroring the existing `tableWait`/"No indexes are available"
     race-condition guard, event-driven via `waitForCondition`).
  3. Walk every household section in the panel (there can be several per
     image — confirmed live: Rolette, Cardinal, two Matwein households,
     Dejarlais, Lasert all appeared on one image). For each, capture the
     household heading text and, for each member `listitem`, the name and
     role-label text directly from the list (no click needed for this part —
     it's already fully rendered).
  4. Assign each household section a synthetic sequential `Family Number`
     (1, 2, 3... per image) — this replaces heuristic inference with the
     page's own explicit grouping.
  5. **Deduplicate exact name+role repeats within the same household list**
     at scrape time (confirmed live: FamilySearch surfaces genuine duplicate
     entries, e.g. "Josette Cardinal" twice) — `build_census_json()` has no
     row-level dedup of its own (unlike the Parish path's
     `match_and_link_records()`), so a duplicate scraped here is a duplicate
     person in the output.
  6. For each (deduplicated) person, click their "Click to view {name}"
     button, wait for the View Name panel to render *for that person*
     (name-match guard, same race-condition pattern already used for the
     citation panel), then scrape:
     - `record_ark` from the "VIEW RECORD" link (`ark:\/61903\/1:1:(...)`,
       unchanged regex).
     - `person_ark`/PID from the Tree Attachment link, **using the corrected
       `/en/tree/person/(...)` pattern** (see Background).
     - Essential Information (Given Name, Surname, Sex).
     - Household Details' relationship label for *this* person, when
       present, as the authoritative `Relationship to Head` value — falling
       back to the household-list's own role-label text when Household
       Details is degenerate, and to nothing when both are (the bare-Primary
       case).
     - Events and Additional Facts sections, read as flat label→value pairs
       tolerant of the field set varying by collection (mirroring
       `Census.py`'s own tolerant `get_row_val` candidate-list philosophy —
       no fixed schema assumed).
  7. Assemble each person into the same `{columns: {...}, person_ark,
     attached_fsftid}` row shape `scrapeIndexRows()` already produced, so
     `FS.py`'s `build_census_json()`/`build_universal_json()` need no changes
     to consume it.
- **`Voyageur.js`, line ~1401**: fix the `attached_fsftid` regex
  (`tree\/person\/details\/` → `tree\/person\/`) regardless of the rest of
  this design — it's already broken against the new UI.
- **`Voyageur/FS.py`**: no changes anticipated for the census path. If the
  parish-collection spot-check (see Background) finds the same panel
  replacing the old table there too, `row_to_record()`'s consumption is
  unaffected either way, since it also just reads `row.columns`/`person_ark`/
  `attached_fsftid` — only the JS producing that shape would need parity
  changes, symmetric to the census case.
- **`downloadFsImage()`**: no change (confirmed live, see Background).

## Scope

### In scope

- `scrapeIndexRows()` → `scrapeNamesPanel()` rewrite in `Voyageur.js`,
  targeting the census case confirmed live.
- The `attached_fsftid` href-pattern fix.
- Same-household duplicate-entry dedup at scrape time.
- Synthetic per-household `Family Number` assignment.

### Explicitly out of scope

- Extracting or replaying an auth bearer token to use the private
  `platform/records/*` JSON API instead of DOM scraping — stays DOM-based.
- Any change to `Archivist/Census.py`, `build_census_json()`, or
  `build_universal_json()` — confirmed tolerant of the new scraper's output
  shape as-is.
- Any change to `downloadFsImage()` — confirmed still working.
- Verifying/updating the parish/church-register path (`row_to_record()`'s
  consumption is fine either way, but whether FamilySearch's parish UI also
  changed is unconfirmed) — flagged as a pre-implementation spot-check, not
  designed against here, since no live evidence exists either way.
- Reconciling `record_family` vs. `record_type_name` labeling
  (`FS.py:834`'s own comment already tracks this separately).

## Testing

`Voyageur.js` is a browser userscript with no existing unit-test harness —
verification is live, against the page. Before considering this done:

- Re-run against the Rolette household (this design's reference fixture) and
  confirm the scraped rows match what was read manually in this session:
  4 Rolette members with correct compound role labels, `record_ark`
  `MZ2Z-WM4` for Joseph Rolette, `person_ark`/PID `9CJG-851` via the
  corrected Tree Attachment regex.
- Run against a bare-Primary household (e.g. Cardinal) and confirm it
  degrades gracefully — people scraped, no fabricated relationship data.
- Confirm the duplicate "Josette Cardinal"-style entry collapses to one row.
- Feed a captured raw scrape through `FS.py`'s existing
  `build_census_json()`/`Census.py` pipeline unmodified and confirm a
  sensible household/dwelling grouping comes out, as the no-Python-changes
  claim in this design depends on.
