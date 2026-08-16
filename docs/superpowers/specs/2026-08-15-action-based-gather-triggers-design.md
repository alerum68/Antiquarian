# Action-Based Gather Triggers & DOM-Extraction Removal — Design

**Status:** Design settled, ready for implementation planning
**Related:** GitHub issue #13 (replace time-based delays with action-driven triggers, Ancestry-scoped in the title but the audit below covers every provider), issue #25 (eliminate the FS Information-tab click). Sibling/precedent: `docs/superpowers/specs/2026-08-15-ancestry-index-panel-extraction-design.md` (added the Ancestry API path as a fallback pair; this plan removes the DOM side of that pair now that the API path has proven reliable in production), `docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md` (FS's own DOM-to-API migration, precedent for the same move on Ancestry).

## Goal

Two related changes to Voyageur's gather pipeline:

1. Remove the DOM-based data-extraction paths that API-based extraction has superseded — Ancestry's DOM-table-scraper fallback, and FS's remaining Information-tab DOM scrape for citation text — plus the DOM-index-detection reload loop that exists only to compensate for DOM-table flakiness and has no purpose once that table is gone.
2. Replace what those DOM paths covered for reliability (a second chance when the API doesn't fire) with a cheaper, action-based equivalent: one retry pass at the end of a run for any page whose API response never arrived, with a loud, impossible-to-miss warning if a page still comes back empty after that.

An audit of every provider's timing code (below) found the JS-side gather loop already uses action-based waiting (`MutationObserver` + bounded ceiling) everywhere except the two DOM paths this plan removes. The remaining Python-side `time.sleep()` calls are unrelated — Windows file-lock retry backoffs and deliberate server rate-limiting — and are explicitly out of scope.

## Audit: current state per provider

| Provider | Extraction | Timing model |
|---|---|---|
| Ancestry (`A.py`/`Voyageur.js`) | API-first (`index-panel-data`), DOM-table scrape as fallback | `waitForCondition()` (MutationObserver + ceiling) for DOM waits; API wait is a promise resolved by an XHR/fetch interceptor. **DOM fallback + reload-retry loop are this plan's main target.** |
| FamilySearch (`FS.py`/`Voyageur.js`) | Orchestration/Image-Index API only for person data (DOM removed in issue #23) | Same interceptor-promise pattern. Citation text still DOM-scraped (Information tab) for the `names` page type — **this plan's other target (issue #25, partial)**. |
| HBCA (`HBCA.py`) | `requests` for most gathers; optional Playwright for Keystone metadata search | `page.wait_for_load_state("domcontentloaded")` already action-based. No change needed. |
| LAC (`LAC.py`/`lac_client.py`) | Pure `requests`, no browser/DOM at all | N/A — nothing to convert. No change needed. |

No code changes are proposed for HBCA or LAC; the audit result is recorded here so it doesn't need re-investigating later.

## Architecture

### 1. Ancestry: remove the DOM-table-scraper fallback

Delete the `else { for (const row of rows) {...} }` branch inside `extractCurrentPageData()` (`Voyageur.js`, currently ~1236-1420), along with `readPersonAlternates()` and `readAlternateEntries()`, which exist only to feed it. The API path (`waitForAncestryIndexPanelResponse` + `ancestryRowsFromIndexPanelResponse`) becomes the only extraction path.

This is a safe removal, not a feature cut: `ancestryRowsFromIndexPanelResponse()` already hardcodes `alternate_names: []`/`alternate_birth_places: []`, so in the common case (API succeeds) the DOM-only alternate-name capture was already not running — the DOM branch only executed when the API had already failed. Its removal changes nothing about the normal path.

### 2. Ancestry: remove the DOM-index-detection reload loop

Delete the `isUnindexed`/`toggleBtn`/`indexPanel`/`rowWait` block in `runExtractionLoop()` (`Voyageur.js:1537-1630`), including `indexReloadAttempts`/`MAX_INDEX_RELOAD_ATTEMPTS` (currently 3) and the `location.reload()` retry it drives. That whole block exists to give the DOM index panel a second chance to render — a concern that doesn't apply once nothing reads that panel.

Each page becomes: call `extractCurrentPageData()` unconditionally, no `rows` argument, no DOM-readiness gate. Its own API wait (existing 8s ceiling) is the only "does this page have data" signal. A timeout is not retried inline (that's what cost up to ~90 seconds per blank page under the old 3-reload loop); it's queued for the single end-of-run retry pass described below.

### 3. FamilySearch: JSON-sourced citation text (issue #25, partial)

Add `fsBuildCitationTextFromOrchestrationResponse()`, mirroring the existing `fsBuildCitationTextFromImageIndexResponse()`, so the `names` page-type branch gets `citationText` from the orchestration-API JSON instead of `scrapeCitationAndCatalog()`'s DOM read. The `image-index` branch already does this for citation text; only `names` still depends on DOM for it.

Catalog items (the Film/Digital Note table) stay on `scrapeCitationAndCatalog()` for both page types for now. Issue #25 flags this as genuinely unresolved — neither JSON source is confirmed to carry that table. The first implementation task is to check both response shapes for it; if found, extend this plan's scope to drop the Information-tab click entirely; if not, the click stays, scoped to catalog items only, and issue #25 stays open for that half.

### 4. End-of-run retry pass (both providers)

When a page's API wait times out, it's still recorded in the output — citation/location metadata intact, empty people/rows — but flagged `incomplete: true`, and its identifying info (page number, dbid/ark, image id, and the page's own URL) is pushed onto a `pagesNeedingRetry` list held in the same reload-state object each provider already persists across reloads (`RELOAD_STATE_KEY` for Ancestry, `FS_RELOAD_STATE_KEY` for FS).

When the forward pass reaches its normal stop condition, and only if `pagesNeedingRetry` is non-empty, the script enters a short retry pass before finalizing: navigate to each flagged page's saved URL, re-run its extraction with the same timeout as a normal attempt (a fresh page load is the retry's value, not a longer wait), and either backfill the page in place on success or leave it `incomplete` on a second failure. One retry per page, then finalize — not a loop.

Ancestry currently advances within one script execution (no reload between images via the Next-image click). Jumping back to an earlier page's URL for the retry pass is a real navigation, so it needs a small reload-state of its own for this phase — same sessionStorage convention as the existing `indexReloadAttempts` recovery path, scoped to just the retry list and current retry index. FS already reloads per image (`mgs_run`-keyed state), so the retry pass reuses that mechanism directly.

### 5. Noisy warning on incomplete pages

Three layers, so a failed page can't be missed:

- A persistent (non-auto-dismissing) toast naming the exact page numbers still `incomplete` after the retry pass.
- The final JSON gains a top-level `incomplete_pages` array (`[{page_number, image_id}]`, empty when everything succeeded).
- `A.py`/`FS.py` print a bordered terminal banner listing every incomplete page when that field is non-empty, at the point each script processes the downloaded JSON.

## Error handling

No fabricated data. A page that never gets a real API response is never filled with guessed or blank-but-unflagged rows — it's marked `incomplete` and surfaced, matching this project's existing "never silently invent data" convention.

## Testing

For each changed function, a subagent writes and runs tests against the existing fixture-based harnesses before the change is considered done: the Node test harness (`Voyageur/tests/js/*.mjs`) for pure JS functions, pytest for any Python-side change (the `incomplete_pages` banner in `A.py`/`FS.py`). The diff is reviewed and the tests must pass before moving to the next piece. Live-browser gather verification is done by the user directly, not through browser automation, per the project's established timing-fidelity constraint (a Claude-driven background tab inflates JS timers well beyond what real usage sees).

## Out of scope

- Windows file-lock retry backoffs (`move_with_retry`, `_read_text_with_retry`) and HBCA/LAC server-politeness rate-limiting delays — not gather-blocking waits, left untouched.
- HBCA and LAC — already action-based (Playwright's `wait_for_load_state`) or have no DOM step at all (`requests`-only). No code changes.
- Ancestry's `collections/collection-text` citation-JSON endpoint — a separate, already-deferred target (issue #24), not built here.

## Next steps

Ready for an explicit, code-complete implementation plan (`writing-plans` skill).
