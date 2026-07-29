# Roadmap

Ideas and planned work that aren't scheduled for the current phase. Nothing here is a
commitment or a deadline, just a place to keep track of what's next so it isn't lost.

## Major Repository support

The toolbox is organized around three pipeline stages now, not "indexed vs. unindexed":
**Voyageur (Gather)** talks to a repository's website - images, plus any index/metadata the
site already provides; **Paleographer (Analysis)** runs AI transcription/translation on
gathered images, doing as little of that as an index already made unnecessary;
**Archivist (Create)** builds the GEDCOM from whatever finished JSON it's handed, auto-
detecting the record family so there's never a per-source button to pick.

Voyageur is a hub: each Major Repository gets its own Python sub-script (`Voyageur/<code>.py`).
Any repository that needs a live logged-in browser session also gets a `runXGather()` function
inside the single `Voyageur/Voyageur.js` Tampermonkey script - one file to install, dispatching
by URL - so adding a new one never touches the shared Python dispatcher or requires installing
a second userscript. Per repository:

### Ancestry (`A`)

- Gather: done (`Voyageur/A.py` + `runAncestryGather()` in `Voyageur.js`, ported from the old
  Archivist scraper this pass).
- Analysis: not needed - Ancestry's own index is already the finished structured data for
  census records.
- The only Major Repository with a paid subscription right now, so the only one that can
  be tested end-to-end today.
- Captures Ancestry's own crowdsourced "alternate reading" submissions (bracketed values
  in each person's Detail panel, each attributable to a specific Ancestry user) for Name
  and Birth Place, merged into the GEDCOM as additional facts alongside the primary
  reading. FamilySearch may expose an equivalent feature (its own attached-tree/user
  corrections) - not yet investigated, deferred as a follow-up.

### FamilySearch (`FS`)

- Gather: done and tested live (`Voyageur/FS.py` + `runFamilySearchGather()` in
  `Voyageur.js`). Scrapes the Image Index table and citation/catalog text; same-person
  matching (`link_id`) handles collections with overlapping duplicate registers (confirmed
  on a real Manitoba parish-register collection - Catholic Mission de Brochet, 65 images,
  Items 1-3 all traced to the same physical film). Image fetch deliberately deferred -
  FamilySearch serves deep-zoom tiles, not a single downloadable file, so tile-stitching is
  its own follow-up item. When that's built, it must fetch every page's image, not just
  indexed ones - an unindexed page (FamilySearch shows "No indexes are available for this
  image") isn't necessarily blank, it just means volunteer indexing hasn't reached it yet;
  the real content still needs an image for Paleographer to transcribe later. The gather
  already preserves this signal (every item_id is recorded even with `rows: []`), so the
  future downloader just needs to not skip on that basis. Name each stitched image file
  after its own FamilySearch ark (the existing `item_id`, e.g. `3:1:3QS7-8994-WPFM.jpg`)
  rather than a
  generated/sanitized name - keep the archive's own identifier, not a rename.
- A live Tampermonkey run against that 65-image register caught and fixed a real race
  condition: the gather only waited for the index table/citation heading to *exist* after
  paging to a new image, not for their content to finish loading, so every image past the
  first captured an empty stub instead of real data. Now waits for real content and passed a
  full re-run clean (65/65 images, 1509 rows, zero placeholder citations). Also fixed the
  Catalog Record table being scraped but silently discarded (now attached to the shared
  `citation` object) and a citation URL-parsing bug that truncated FamilySearch ark URLs at
  their first internal colon.
- `FS.py`'s output now conforms to `Paleographer/schema.json` exactly (was a bespoke flat
  structure Archivist.py couldn't actually read), using a new shared `FactTypes.json`
  (RootsMagic's own FactTypeTable, both built-in facts and this project's customs like
  "dit Name" and "Scrip" - built from real `.rmtree` databases) for event vocabulary and
  `Parish.pmt`'s roles table for participant vocabulary. Verified by generating a sample
  GEDCOM from a live gather and diffing it against the existing, working Assumption Parish
  pipeline (`DEV/Assumption_Parish.ged` / `Assumption Parish.rmtree`) - caught a real,
  serious bug in the process: Archivist's `generate_uid`/`generate_fam_uid` hash on
  `(vol, page, record_id, role)` alone, and FamilySearch's Image Index frequently lacks
  both page and record locators (~85% of rows in the real register tested), which
  collapsed hundreds of genuinely different people onto identical UIDs. Fixed in `FS.py`
  with a item_id/position-based fallback rather than changing Archivist's hashing scheme.
- Fixed a citation-accuracy bug: the "Attach to Tree" table cell holds two separate links
  (a "View record" link - that row's own per-record ark, always present - and the actual
  attach action), and the scraper was grabbing whichever came first regardless of real
  attachment status, mislabeling the record's own ark as a Family Tree person ID. Confirmed
  live (attached vs. unattached rows, real 1880 census collection) that genuine attachment
  only ever shows via a distinct `/tree/person/details/` link. Now scrapes `person_ark`
  (always present, wired into the citation as a web tag linking straight to that
  FamilySearch record) and `fsftid` (only when actually attached) separately.
- Surveyed all 17 US census years (1790-1950) live for Image Index UI compatibility. All 17
  render the table-based Image Index our scraper reads (1790-1840 are Name + Page Number
  only; 1850 onward adds many more columns, peaking at 17 for 1880). A card-list "Names"
  panel (no `<table>` at all) also turned up during testing and was initially mis-attributed
  to specific films/years - traced it down: it's neither. It's a URL-format thing.
  `?view=index&action=view` (what a search result's "View Original Document" link produces
  - a person-detail deep-link) renders the Names panel; the standard image-browsing URL
  (`...&wc=...&i=0&groupId=...`, produced by waypoint navigation and Next Image, which is
  all `runFamilySearchGather()` ever uses) renders the normal table - confirmed on the
  *exact same film* under both URL forms. Since the gather never navigates via search
  results, it never organically hits the Names-panel form - no scraper fix actually needed.
  Still confirmed the attached Family Tree ID (fsftid) is extractable from the Names panel
  too if this is ever revisited, via the same `/tree/person/details/XXXX-XXXX` link pattern
  already used in the table view. Peaked at 18 columns for 1950 - one genuine wrinkle
  there: its waypoint browsing is organized by Film Number rather than the usual
  State/County/Township/ED chain, and its own "Browse All Images" link doesn't work the
  same way (errors out) - a real user would need to reach an image via search + "View the
  image" instead. The Image Index table itself, once on a clean image URL, is the same
  compatible format regardless.
- Analysis: still needed for the actual transcription/translation text (the index gives
  vitals, not the handwritten record's content) - exact mechanics deferred to Paleographer's
  second-pass redesign, below.

### LAC (`LAC`)

- Gather: done, pre-existing (`Voyageur/LAC.py`, the Heritage Canadiana IIIF downloader) -
  images only, no index scraping yet.
- Indexed search of LAC's own website (rather than only reading scanned files cold) is
  still open - some Scrip records are already partially transcribed there, with key
  information (and sometimes UIDs) displayed on the page itself.

### Keystone (`KS`, Archives of Manitoba)

- First check whether LAC's own search portal actually surfaces Keystone material
  adequately for our purposes - if so, no separate sub-script is needed. Confirm this
  rather than assuming it either way.
- If not, build `Voyageur/KS.py` the same way. HBCRecords.py already has a working (if
  narrow, HBC-specific) Keystone scraper to use as prior art.

### NARA (National Archives, US - no short code assigned yet)

- Gather: not started. No site research done yet.

### BAnQ (`BANQ`, Bibliothèque et Archives nationales du Québec)

- Gather: not started. No site research done yet.

## Cross-source merge (Ancestry + FamilySearch)

Merge logic is built: `FS.py` now has a census-shaped output path (`build_census_json`,
parallel to the church-flavor `build_universal_json`, auto-selected via
`detect_record_family`), a new `Voyageur/MergedCensus.py` merges two already-gathered
Ancestry + FamilySearch JSON files into one, and `Archivist.py`'s census citation builder
emits a single citation for a merged person - both `_APID` and `_FSFTID`, both web links,
and NARA (not Ancestry.com/FamilySearch.org) as the cited repository. Verified against
synthetic fixtures built from a real FamilySearch citation (see below); not yet verified
against a real dual-source live gather.

Matching by fuzzy name+date across two *independent* indexing efforts is risky - a
same-named household, or a name transcribed differently on the two sides, can silently
attach the wrong FamilySearch link to the wrong Ancestry person. The safer key is a
locator both sides reference: **Roll/ED/Page + Line Number**. Ancestry's index reliably
has (or already synthesizes) Line Number; FamilySearch's doesn't expose one directly on
any year checked, so `FS.py` synthesizes its own from each row's position on the page, the
same way Ancestry's side already does. Page matching itself only requires ED + page
number to agree - film/roll is checked as a tie-breaker when both sides have one, but
isn't required, since two independent gathers won't always format it identically.

FamilySearch's roll number isn't on the Image Index table itself, but it is recoverable:
the citation's own "citing NARA microfilm publication `<ID>`" clause plus the Catalog
Record table's Film/Digital Note ("NARA Series `<ID>`, Roll `<N>`") together give an
`<ID>_<N>` string matching Ancestry's own Roll-field convention (e.g. `M653_1`) - `FS.py`
now parses both. That same citation tail also broke the general-purpose `parse_citation()`
regex for census specifically: it still technically matches (doesn't error), but silently
captures garbage into `publisher`/`pub_loc` instead of the real NARA holder, since census
citations end in a longer, differently-shaped clause than the simple "Publisher, Loc."
ending church-register citations use. `FS.py` now parses that clause separately
(`parse_nara_citing_clause`) rather than patching the shared regex, to avoid risking the
already-working church-flavor path.

The convenience layer is built too: Voyageur's Gather tab has a new "Merged (Ancestry +
FamilySearch)" source showing both URL fields at once; picking it and clicking Gather runs
`Voyageur/Merged.py`, which calls `A.py`'s gather, then `FS.py`'s, then
`MergedCensus.merge_census`, writing one merged JSON ready for Archivist. Still open: live
verification against a real Ancestry + FamilySearch dual gather of the same physical page
(synthetic-fixture verification only so far).

## Paleographer: second-pass redesign

Deferred deliberately (see the implementation plan from this session): now that Voyageur
(Gather) and Archivist (Create) exist concretely, redesign Paleographer's actual analysis
logic against their real input/output shapes rather than speculating. Known requirements
going in:
- Operate only on already-complete Gather JSON (own folder-scanning/classification removed;
  Voyageur is responsible for wrapping even a plain manual local-image case).
- Limit AI usage to what an index hasn't already supplied - via schema *omission*
  (a genuinely smaller `response_schema`/prompt), not requesting-then-nulling fields, since
  Gemini's structured output still spends tokens on nulled fields and unrelated prompt
  instructions.
- Auto-detect which `.pmt` template applies (or fall back to a flexible event+note shape,
  matching how census already handles unfamiliar structure) instead of a required manual
  per-run pick.

## Wills & Probates record type

Another record type Paleographer will need a `.pmt` file for. Structurally closer to
Scrip Records than to Parish registers (multi-document case files rather than a single
sacramental entry), and will likely need the same Batch API / OCR-heavy handling Scrip
uses rather than the single-page synchronous path Parish uses.
