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

### Keystone (`KS`, Archives of Manitoba)

- First check whether LAC's own search portal actually surfaces Keystone material
  adequately for our purposes - if so, no separate sub-script is needed. Confirm this
  rather than assuming it either way.
- If not, build `Voyageur/KS.py`. HBCRecords.py already has a working (if
  narrow, HBC-specific) Keystone scraper to use as prior art.

### NARA (National Archives, US)

- Gather: not started. No site research done yet.

### BAnQ (`BANQ`, Bibliothèque et Archives nationales du Québec)

- Gather: not started. No site research done yet.

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

## Wills & Probates record type

Another record type Paleographer will need a `.pmt` file for. Structurally closer to
Scrip Records than to Parish registers (multi-document case files rather than a single
sacramental entry), and will likely need the same Batch API / OCR-heavy handling Scrip
uses rather than the single-page synchronous path Parish uses.
