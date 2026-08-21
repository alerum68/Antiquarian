# Roadmap

Ideas and planned work that aren't scheduled for the current phase. Nothing here is a
commitment or a deadline, just a place to keep track of what's next so it isn't lost.

## Major Repository support

Voyageur is a hub: each Major Repository gets its own Python sub-script (`Voyageur/<code>.py`).
Any repository that needs a live logged-in browser session also gets a `runXGather()` function
inside the single `Voyageur/Voyageur.js` Tampermonkey script - one file to install, dispatching
by URL - so adding a new one never touches the shared Python dispatcher or requires installing
a second userscript. Per repository:

### LAC (`LAC`)

- Indexed search of LAC's own website (rather than only reading scanned files cold) is
  still open - some Scrip records are already partially transcribed there, with key
  information (and sometimes UIDs) displayed on the page itself.

### Keystone / HBCA (`HBCA`, Archives of Manitoba)

- **Started and working.** Keystone is the digitized search portal for the Hudson's Bay
  Company Archives (HBCA), housed at the Archives of Manitoba. The HBCA gather is
  implemented in `Voyageur/HBCA.py`: biographical index parsing, HBCA reference/location
  code extraction, Keystone POST search with a Playwright headless fallback, and PDF
  media download with multi-reel merging into Commissioner-compliant scaffold sheets.
  Tested by `Voyageur/tests/test_hbca_*.py` and dispatched as source `HBCA` from
  `Voyageur/Voyageur.py`.
- Remaining: more live testing against real HBCA/Keystone sessions to configure properly -
  verify search-form matching, media-type coverage, and permalink fidelity; tighten as
  gaps surface.

### NARA (National Archives, US)

- Gather: in planning (2026-08-09). Design spec + implementation plan under way - see
  `docs/superpowers/specs/2026-08-09-nara-gather-design.md` and
  `docs/superpowers/plans/2026-08-09-nara-gather.md`.

### BAnQ (`BANQ`, Bibliothèque et Archives nationales du Québec)

- Gather: not started. No site research done yet.

## Whole-town census gather (multi-URL, merged GEDCOM)

Today a Voyageur census gather covers one already-open record/collection at a time -
whatever page the browser is sitting on. Extend this so a whole town's census records can
be gathered into a single GEDCOM in one pass: the user supplies a plain text file listing
every record URL they want (one per line - e.g. every page of a town's enumeration
district(s)), Voyageur works through the list producing one raw JSON per URL exactly as it
does today, then a new combine step merges all of those JSONs into one document before
Archivist builds the GEDCOM.

Two genuinely separate pieces of work:

- **Driving the URL list.** Voyageur.js's existing `mgs_auto`/`mgs_run` reload-and-resume
  pattern (see `runFamilySearchGather()`'s own notes on why "Next Image" re-runs the whole
  script from scratch on every navigation) already solves "keep going across many page
  reloads without losing state" for one collection - the natural extension is a persisted
  queue of *starting* URLs instead of just "next image within this collection," so a crash
  partway through only costs the current URL, not the whole run. Per-URL output stays one
  standalone JSON each, unchanged.
- **Merging person records across the combined JSONs.** This is the hard part, and splits
  into two cases:
  - *Same real person, shared Tree attachment*: solved by the `pid`/`person_ark` hashing
    work (`Voyageur/FS.py`'s `pid_from_identifier()`, 2026-08-21) - the same real person
    attached across multiple gathered records already collapses to the same `pid`, so
    matching on it is enough.
  - *Same real person, no Tree attachment* (the common case - most historical census
    personas were never attached): needs real fuzzy matching - name, age/birth year,
    birthplace, household role. `Voyageur/MergedCensus.py` (deleted in commit `b913aa6`,
    "archive merge concept") solved a related but distinct problem - merging FamilySearch +
    Ancestry readings of the *same* page/sheet - via locator-normalized sheet matching and
    per-field conflict resolution that records disagreement as a review reason rather than
    silently picking a winner; its conflict-handling approach (never drop data, flag
    uncertainty) is worth reviving even though its sheet-matching logic doesn't apply here
    (this is the same source across *different* pages, not two sources on one page).
    `Archivist/Census.py`'s existing household-parsing heuristics
    (`evaluate_spouse_match`/`evaluate_child_match`, confidence-scored against
    `REVIEW_THRESHOLD`) are the closest existing precedent for a confidence-scored,
    flag-rather-than-guess matching policy at person granularity.
  - Related and higher-stakes at town scale: cross-page/cross-ED duplicate detection (the
    same household enumerated once but appearing to span overlapping page/ED ranges) and
    the already-open ED-boundary-crossing detection task from
    `docs/plans/2026-08-20-familysearch-viewer-rebuild.md` both become much more likely to
    matter once adjacent pages/EDs across a whole town are being combined, not just one
    collection.
- Once merged, the combined dataset should be able to feed `Archivist/Census.py`'s existing
  `build_gedcom_from_census()` unchanged - it already groups a DataFrame by household - as
  long as merging/deduplication happens upstream of that call, not inside it.

## Reunion (Mac) GEDCOM output support

Low priority. A third `target_software` output flavor in Archivist.py (alongside RootsMagic
and Family Tree Maker) for Reunion, the long-standing Mac-only genealogy app from Leister
Productions. Feasible to build the same way the FTM branch was - research Reunion's known
GEDCOM import behavior/quirks, then write a `target_software == "Reunion"` branch in the
citation/task builders - but with a real gap the RM/FTM work didn't have: neither this
project nor its maintainer currently has a Mac or a copy of Reunion to test against, so
anything built would ship unverified against a real import (unlike FTM, where at least the
maintainer can test empirically) until that access exists. Worth doing once that testing
gap closes, not before.

## Mac (.dmg) and Linux (.deb) packaging

CI (`.github/workflows/build.yml`) only builds Windows today: a single `runs-on:
windows-latest` job producing the Inno Setup installer and `Antiquarian_Portable.zip`.
The original packaging design (`docs/superpowers/specs/2026-08-15-packaging-architecture-design.md`,
Section 4) planned a full 3-OS matrix, but the Mac and Linux legs were never implemented.

Needs real platform-specific work, not just adding runners:
- A macOS job: PyInstaller `--onedir` build, then wrap in a `.dmg` (e.g. `create-dmg`).
- A Linux job: PyInstaller `--onedir` build, then package via `fpm` or `dpkg-deb`.
- CustomTkinter, Tampermonkey, and AGY-CLI dependency handling all need verifying on
  both platforms - untested there today.
- The installer's Node.js/AGY-CLI auto-install logic is Windows-specific PowerShell
  (`installer.iss`) and has no Mac/Linux equivalent yet.

## Wills & Probates record type

Another record type Paleographer will need a `.pmt` file for. Structurally closer to
Scrip Records than to Parish registers (multi-document case files rather than a single
sacramental entry), and will likely need the same Batch API / OCR-heavy handling Scrip
uses rather than the single-page synchronous path Parish uses.
