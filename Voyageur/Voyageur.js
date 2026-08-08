// ==UserScript==
// @name         Voyageur
// @namespace    https://github.com/alerum68/Scriptorium
// @version      0.3.6
// @description  Gathers pages from supported Repositories. Detects which repository you're on from the URL and runs that repository's own gather logic.
// @author       alerum68
// @match        *://*.ancestry.com/imageviewer*
// @match        *://*.familysearch.org/ark:/*
// @match        *://sg30p0.familysearch.org/*
// @connect      *
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @run-at       document-start
// ==/UserScript==
// noinspection JSUnresolvedReference

(function () {
    'use strict';

    // Shared by both runXGather() functions below. Resolves as soon as checkFn() returns a
    // truthy value, re-testing it on every DOM mutation (React re-rendering a panel, a
    // table's rows updating, a button's disabled attribute flipping) instead of on a fixed
    // timer - so a page that's already ready resolves immediately, and a slow one still
    // only waits as long as it actually takes, up to timeoutMs. Falls back to a plain
    // timeout if nothing mutates before then (e.g. waiting on something that will never
    // appear).
    function waitForCondition(checkFn, {timeoutMs = 15000, target = document.body} = {}) {
        return new Promise((resolve) => {
            const startedAt = performance.now();
            const immediate = checkFn();
            if (immediate) {
                resolve({result: immediate, elapsedMs: 0, timedOut: false});
                return;
            }

            let settled = false;
            const finish = (result, timedOut) => {
                if (settled) return;
                settled = true;
                observer.disconnect();
                clearTimeout(timer);
                resolve({result, elapsedMs: Math.round(performance.now() - startedAt), timedOut});
            };

            const observer = new MutationObserver(() => {
                const result = checkFn();
                if (result) finish(result, false);
            });
            observer.observe(target, {childList: true, subtree: true, attributes: true, characterData: true});

            const timer = setTimeout(() => finish(null, true), timeoutMs);
        });
    }

    // Dispatch by hostname, the same way Voyageur.py's Python side dispatches by an explicit
    // source-code argument - adding a new Major Repository here is a new @match line above
    // plus a new runXGather() function below, nothing else touched.
    const host = window.location.hostname;

    if (host.includes('ancestry.com')) {
        runAncestryGather();
    } else if (host === 'sg30p0.familysearch.org') {
        runFsImageIframeHelper();
    } else if (host.includes('familysearch.org')) {
        runFamilySearchGather();
    }

    // ==========================================
    // FAMILYSEARCH IMAGE HELPER - runs inside the hidden iframe downloadFsImage (below)
    // creates, same-origin relative to the deepzoomcloud image itself. Direct access to
    // this endpoint from the FamilySearch record page's own origin is blocked - confirmed
    // live across three separate mechanisms: GM_xmlhttpRequest hangs to timeout, a plain
    // cross-origin fetch() gets 429 even on a brand-new item_id never requested before,
    // and a plain cross-origin <a download> triggers nothing at all - while a genuine
    // top-level navigation to this exact URL (what the site's own "Print" button does)
    // always works cleanly. Loading it in a hidden iframe gets a real navigation (no
    // popup-blocker issue, unlike window.open(), and the parent page's own state/loop
    // isn't disturbed the way navigating the parent tab itself would be), and this
    // function then runs same-origin inside that iframe, where fetch() is no longer
    // cross-origin and none of the above restrictions apply.
    // ==========================================
    function runFsImageIframeHelper() {
        // Only fetches here and hands the raw bytes back to the parent via postMessage -
        // confirmed live that triggering the actual <a download> click from *inside* this
        // iframe runs the whole fetch+blob chain successfully (postMessage 'done' arrives,
        // the image visibly renders) but never actually saves a file, while the identical
        // click mechanism triggered from the top-level record page (the JSON downloads)
        // always works - browsers commonly restrict download-triggering from a nested
        // iframe even when same-origin. The parent does the actual click instead, in the
        // same top-level context that already reliably downloads the JSON.
        const match = window.location.pathname.match(/\/dz\/v1\/([^/]+)\/\$dist/);
        const itemId = match ? decodeURIComponent(match[1]) : "unknown_item";
        const fileName = `${itemId.replace(/[^a-zA-Z0-9_-]/g, '_')}.jpg`;

        fetch(window.location.href)
            .then(response => {
                if (!response.ok) {
                    window.parent.postMessage({voyageurFsImage: 'error', status: response.status}, '*');
                    return;
                }
                return response.arrayBuffer().then(buffer => {
                    window.parent.postMessage({voyageurFsImage: 'data', buffer, fileName}, '*', [buffer]);
                });
            })
            .catch(e => {
                window.parent.postMessage({voyageurFsImage: 'error', message: String(e)}, '*');
            });
    }

    // ==========================================
    // ANCESTRY (A) - census index + image gather
    // ==========================================
    function runAncestryGather() {
        // GUARD: Check if the extractor has been explicitly triggered for this session or via URL
        if (sessionStorage.getItem('run_census_extractor') !== 'true' && !window.location.href.includes('mgs_auto=1')) {
            return; // Exit immediately, doing nothing
        }

        // Clear the flag so it only runs once per trigger (optional)
        sessionStorage.removeItem('run_census_extractor');

        const DEBUG_MODE = true;
        let isAutoExtracting = false;
        let accumulatedPages = [];
        let batchPageCounter = 1;
        let seenPids = new Set();
        let lastPageSignature = "INITIAL_STATE_NOT_SET";

        const shouldAutoStart = window.location.href.includes('mgs_auto=1');

        function debugLog(msg) {
            if (DEBUG_MODE) {
                console.log(`[MGS DEBUG] ${msg}`);
            }
        }

        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__mgs_intercepted) {
            unsafeWindow.__mgs_intercepted = true;
            unsafeWindow.__mgs_pids = [];

            function extractPidsFromText(text) {
                try {
                    let parsed;
                    try {
                        parsed = JSON.parse(text);
                    } catch (e) {
                        parsed = null;
                    }

                    if (parsed && Array.isArray(parsed.RecordRectangles) && parsed.RecordRectangles.length > 0) {
                        const ids = parsed.RecordRectangles
                            .map(r => (r && r.RecordId != null) ? String(r.RecordId) : null)
                            .filter(id => id !== null);
                        if (ids.length > 0) {
                            unsafeWindow.__mgs_pids = ids;
                            return;
                        }
                    }

                    const matches = [...text.matchAll(/"(?:recordId|pId|clientRecordId)"\s*:\s*"?(\d{5,15})"?/gi)];
                    if (matches.length > 2) {
                        unsafeWindow.__mgs_pids = matches.map(m => m[1]);
                    }
                } catch (e) {
                }
            }

            const origFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const response = await origFetch.apply(this, args);
                try {
                    const clone = response.clone();
                    clone.text().then(text => extractPidsFromText(text)).catch(() => {
                    });
                } catch (e) {
                }
                return response;
            };

            const origOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.addEventListener('load', function () {
                    extractPidsFromText(this.responseText);
                });
                origOpen.apply(this, arguments);
            };
        }

        function initUI() {
            if (document.getElementById('extractor-ui-container')) return;

            const style = document.createElement('style');
            style.innerHTML = `
                #extractor-ui-container { position: fixed; bottom: 20px; right: 20px; background-color: #1a1a1a; color: white; border-radius: 8px; padding: 12px 16px; font-family: sans-serif; z-index: 999999; box-shadow: 0 4px 12px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 10px; align-items: center; border: 1px solid #333; min-width: 180px; }
                #extractor-header { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding-bottom: 4px; border-bottom: 1px solid #333; }
                #extractor-title { font-weight: bold; font-size: 15px; }
                #extractor-status-light { width: 12px; height: 12px; border-radius: 50%; background-color: #22c55e; box-shadow: 0 0 8px #22c55e; transition: all 0.3s ease; }
                #extractor-status-light.running { background-color: #3b82f6; box-shadow: 0 0 10px #3b82f6; animation: pulse-light 1.5s infinite; }
                @keyframes pulse-light { 0% { transform: scale(0.95); opacity: 0.8; } 50% { transform: scale(1.1); opacity: 1; } 100% { transform: scale(0.95); opacity: 0.8; } }
                .extractor-btn { color: white; border: none; border-radius: 6px; padding: 10px 14px; font-size: 14px; font-weight: bold; cursor: pointer; width: 100%; transition: background-color 0.2s; }
                #ext-start-btn { background-color: #2b7a4b; } #ext-start-btn:hover { background-color: #1e5935; }
                #ext-stop-btn { background-color: #991b1b; display: none; }
                #extractor-toast-container { position: fixed; bottom: 140px; right: 20px; z-index: 999999; display: flex; flex-direction: column; gap: 10px; pointer-events: none; }
                .extractor-toast { background-color: #333; color: #fff; padding: 12px 20px; border-radius: 6px; font-size: 14px; opacity: 0; transform: translateY(10px); transition: opacity 0.3s, transform 0.3s; }
                .extractor-toast.show { opacity: 1; transform: translateY(0); }
                .extractor-toast.error { background-color: #b91c1c; } .extractor-toast.success { background-color: #15803d; }
            `;
            document.head.appendChild(style);

            const toastContainer = document.createElement('div');
            toastContainer.id = 'extractor-toast-container';
            document.body.appendChild(toastContainer);

            window.showToast = function (message, type = 'success', duration = 2500) {
                const toast = document.createElement('div');
                toast.className = `extractor-toast ${type}`;
                toast.innerText = message;
                toastContainer.appendChild(toast);
                void toast.offsetWidth;
                toast.classList.add('show');
                setTimeout(() => {
                    toast.classList.remove('show');
                    setTimeout(() => toast.remove(), 300);
                }, duration);
            }

            const controlPanel = document.createElement('div');
            controlPanel.id = 'extractor-ui-container';

            const header = document.createElement('div');
            header.id = 'extractor-header';
            const statusLight = document.createElement('div');
            statusLight.id = 'extractor-status-light';
            const title = document.createElement('span');
            title.id = 'extractor-title';
            title.innerText = 'Voyageur (A)';

            header.appendChild(statusLight);
            header.appendChild(title);
            controlPanel.appendChild(header);

            const startBtn = document.createElement('button');
            startBtn.id = 'ext-start-btn';
            startBtn.className = 'extractor-btn';
            startBtn.innerText = 'Start Auto-Batch';

            const stopBtn = document.createElement('button');
            stopBtn.id = 'ext-stop-btn';
            stopBtn.className = 'extractor-btn';
            stopBtn.innerText = 'Stop & Download JSON';

            controlPanel.appendChild(startBtn);
            controlPanel.appendChild(stopBtn);
            document.body.appendChild(controlPanel);

            startBtn.addEventListener('click', startBatch);
            stopBtn.addEventListener('click', stopBatch);

            window._startBtn = startBtn;
            window._stopBtn = stopBtn;
            window._statusLight = statusLight;
        }

        function getYearAndLocation() {
            let year = "UnknownYear";
            let locationStr = "Unknown_Location";

            if (typeof unsafeWindow !== 'undefined' && unsafeWindow.__PRELOADED_STATE__) {
                try {
                    const state = unsafeWindow.__PRELOADED_STATE__;
                    if (state.viewer) {
                        // collectionInfo lives under viewer.imageInfo, not directly under viewer -
                        // reading the wrong path here silently failed and always fell through to
                        // the document.title regex below.
                        year = state.viewer.imageInfo?.collectionInfo?.publicationYear || year;
                        const path = state.viewer.imageInfo?.browsePath;
                        if (path && path.length > 0) locationStr = path.join(' - ');
                    }
                } catch (err) {
                }
            }
            if (year === "UnknownYear") {
                const yearMatch = document.title.match(/(1[7-9]\d\d|19[0-6]\d)/);
                if (yearMatch) year = yearMatch[0];
            }
            locationStr = locationStr.replace(/[/\\?%*:|"<>]/g, '-').replace(/\s+/g, ' ').trim();
            return {year, locationStr};
        }

        function getBaseImageId() {
            const urlMatch = window.location.href.match(/images\/([^?&/]+)/);
            if (urlMatch) return urlMatch[1].replace(/[^a-zA-Z0-9_-]/g, '');
            return "Unknown_Image";
        }

        function getEnumerationDistrict(pathArr, structureType) {
            // Different collections/years can have different browsePath depths and orders (e.g.
            // some don't have an Enumeration District level at all). Use the collection's own
            // structureType labels from __PRELOADED_STATE__ to find which position actually holds
            // the ED instead of assuming a fixed index. Returns the index too (not just the
            // value) so callers building place_details from the remaining path segments can
            // exclude it, rather than duplicating the ED into both fields (confirmed happening
            // across every 4-segment browsePath year from 1880 on: static-checked all 17 US
            // census years' real browsePath/structureType shapes against this function).
            const keys = Object.keys(structureType || {});
            const namedIndex = keys.findIndex(k => /district/i.test(k));
            if (namedIndex !== -1 && pathArr[namedIndex]) return {value: pathArr[namedIndex], index: namedIndex};
            if (pathArr.length > 3) return {value: pathArr[pathArr.length - 1], index: pathArr.length - 1};
            return {value: "", index: -1};
        }

        function parseFilmRollFromImageId(imageId) {
            // Fallback only, used when the real Source Citation can't be scraped (see
            // scrapeSourceCitation below). Ancestry image IDs for NARA-microfilmed collections
            // sometimes encode the microfilm publication and roll, e.g. "M-T0627-03009-00399"
            // -> NARA publication T627, roll 3009. Not all collections use this scheme (in
            // fact most pre-1940 ones don't), so a non-match just leaves both blank rather
            // than guessing wrong.
            const match = imageId.match(/^[A-Z]-([A-Z])0*(\d+)-0*(\d+)-\d+$/i);
            if (!match) return {film: "", roll: ""};
            const [, letter, filmNum, rollNum] = match;
            return {film: `${letter.toUpperCase()}${filmNum}`, roll: rollNum};
        }

        function findLeafByExactText(text) {
            // Ancestry's CSS class names for the info-panel tab bar aren't stable across
            // deploys, so match by the tab's own visible label instead of a selector.
            const candidates = document.querySelectorAll('button, a, [role="tab"], li, div, span');
            for (const el of candidates) {
                if (el.children.length === 0 && el.textContent.trim() === text) return el;
            }
            return null;
        }

        function parseCitationFields(citationText) {
            const fields = {};
            citationText.split(';').forEach(part => {
                const idx = part.indexOf(':');
                if (idx === -1) return;
                const label = part.slice(0, idx).trim();
                const value = part.slice(idx + 1).trim();
                if (label) fields[label] = value;
            });
            return fields;
        }

        function parseSourceInformation(text) {
            // Ancestry's (and, going by the same convention, FamilySearch's) "Source
            // Information" prose follows a consistent two-sentence template:
            // "<Repository>. <Collection> [database on-line]. <City, ST, USA>: <Repository
            // Entity>, <year>.\n\nOriginal data: <description>. <City, ST/Country>: <Publisher>,
            // <year>. <extra>." Pull every "<Location>: <Entity>, <Year>." pair out of it; the
            // first is always the online-database repository, the last is always the original
            // data's publisher. ("Original data:" itself sometimes false-matches as a pair in
            // between the two real ones, since it's also followed eventually by a ", <year>."
            // - harmless, since only the first and last matches are actually used.)
            const result = {repository: "", repositoryLoc: "", publisher: "", pubLoc: ""};
            if (!text) return result;

            // The repository name is the leading "<Name>. " clause, e.g. "Ancestry.com. " or
            // "FamilySearch.org. " - matched as a dotted domain-like token so it isn't cut
            // short at its own internal period.
            const repoMatch = text.match(/^([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)\.\s/);
            if (repoMatch) result.repository = repoMatch[1].trim();

            // The trailing year is sometimes literally "n.d." (no date) instead of a real
            // year - confirmed live on a real citation ("...National Archives and Records
            // Administration, n.d.") - which silently broke this match entirely, since only
            // the first (Ancestry.com) pair would then be found and get reused for both
            // repository and publisher, defeating the whole point of citing NARA instead.
            // Note: "n.d" (not "n.d.") - the outer \. right after the group supplies the
            // final period, so "n.d." + outer \. would wrongly require two trailing dots.
            const pairs = [...text.matchAll(
                /([A-Z][A-Za-z., ]{2,60}?):\s*([A-Z][A-Za-z., &]{2,80}?),\s*(?:1[6-9]\d{2}|20\d{2}|n\.d)\./g)];
            if (pairs.length > 0) {
                result.repositoryLoc = pairs[0][1].trim().replace(/,\s*USA$/i, '');
            }
            if (pairs.length > 1) {
                const last = pairs[pairs.length - 1];
                result.pubLoc = last[1].trim();
                result.publisher = last[2].trim();
            }
            return result;
        }

        async function scrapeSourceCitation() {
            // The real, authoritative Roll/Film/ED/Year/Repository/Publisher live in the info
            // panel's "Source" tab as rendered text (e.g. "Year: 1940; Census Place: St Thomas,
            // Pembina, North Dakota; Roll: m-t0627-03009; Page: 6A; Enumeration District:
            // 34-33" plus a separate "Source Information" paragraph), not in
            // __PRELOADED_STATE__ or any network response we could otherwise intercept. Must
            // be re-scraped on every page: NARA microfilm rolls don't align with county/ED
            // boundaries, so a roll can change mid-run without any change in
            // County/Township/ED to signal it.
            const sourceTab = findLeafByExactText('Source');

            // aria-controls names the DOM element that actually holds this tab's content.
            // Live testing confirmed this container is mounted in the DOM from the very
            // start (before any clicking) - yet its text never appeared in
            // document.body.innerText no matter how long we waited. innerText respects CSS
            // visibility/layout; textContent doesn't. That means the pane is present but
            // not "visible" by that reckoning (off-screen or zero-height until selected,
            // rather than removed from the DOM) - so read the container's own textContent
            // directly instead of waiting on it to become visible. Since the data is
            // already mounted, this needs no wait at all.
            const sourceContentId = sourceTab ? sourceTab.getAttribute('aria-controls') : null;
            const sourceContentEl = sourceContentId ? document.getElementById(sourceContentId) : null;

            if (sourceTab) sourceTab.click();

            let citationBlock = "", infoBlock = "";

            if (sourceContentEl) {
                const rawText = (sourceContentEl.textContent || "").replace(/\s+/g, ' ').trim();

                if (DEBUG_MODE) {
                    console.log(`[MGS DEBUG] citation: container raw text (first 1000 chars): ${rawText.slice(0, 1000)}`);
                }

                // Loosened from the old \n+-based boundaries (textContent has no layout
                // whitespace to rely on) - anchored on the literal heading words instead,
                // which should still appear verbatim regardless of surrounding markup. No
                // trailing \b: confirmed live that Ancestry concatenates directly with no
                // separator at all ("...803094DescriptionCity: Pembina..."), so the
                // transition from the heading's last letter into the next section's first
                // letter is word-to-word, never a \b boundary - a \b here made the whole
                // match silently fail every time.
                const citeMatch = rawText.match(
                    /Source Citation\s*(.*?)\s*(?:Source Information|Description|Source Description|Person)/);
                if (citeMatch && citeMatch[1].trim()) citationBlock = citeMatch[1].trim();

                const infoMatch = rawText.match(/Source Information\s*(.*?)\s*(?:Source Description|Person)/);
                if (infoMatch && infoMatch[1].trim()) infoBlock = infoMatch[1].trim();

                if (DEBUG_MODE) {
                    console.log(`[MGS DEBUG] citation: parsed citationBlock: "${citationBlock.slice(0, 300)}" | infoBlock: "${infoBlock.slice(0, 300)}"`);
                }
            } else if (DEBUG_MODE) {
                console.log(`[MGS DEBUG] citation: "Source" tab found: ${!!sourceTab} | content container found: false`);
                if (!sourceTab) {
                    // The tab's exact label may have changed - list every short leaf
                    // element's text so the real label (if any) is visible in the console
                    // instead of guessing blind.
                    const candidateLabels = [...new Set(
                        [...document.querySelectorAll('button, a, [role="tab"], li, span')]
                            .filter(el => el.children.length === 0)
                            .map(el => el.textContent.trim())
                            .filter(t => t && t.length <= 30)
                    )].slice(0, 40);
                    console.log(`[MGS DEBUG] citation: no exact "Source" leaf found - candidate short labels on page: ${JSON.stringify(candidateLabels)}`);
                }
            }

            if (!citationBlock) {
                return {
                    roll: "", film: "", ed: "", year: "",
                    repository: "", repositoryLoc: "", publisher: "", pubLoc: ""
                };
            }

            const fields = parseCitationFields(citationBlock);
            const info = parseSourceInformation(infoBlock);

            // Ancestry's own Roll value is formatted "<roll number>_<film number>"
            // (confirmed live, e.g. "M653_94" - "M653" is the roll number, "94" is the film
            // number). Split them into Archivist's separate Roll/Film fields instead of
            // carrying the combined string as "roll" alone - distinct from the separate
            // "Family History Library Film" catalog number (a different, unrelated
            // numbering system - confirmed live: "803094" alongside "M653_94" on the same
            // record), which is only used as a fallback when Roll itself isn't parseable.
            const rollValue = fields['Roll'] || "";
            const rollMatch = rollValue.match(/^(.+?)_(\d+)$/);
            const rollNumber = rollMatch ? rollMatch[1] : rollValue;
            const rollFilmNumber = rollMatch ? rollMatch[2] : "";

            return {
                roll: rollNumber,
                film: rollFilmNumber || fields['Family History Library Film'] || "",
                ed: fields['Enumeration District'] || "",
                year: fields['Year'] || "",
                repository: info.repository,
                repositoryLoc: info.repositoryLoc,
                publisher: info.publisher,
                pubLoc: info.pubLoc
            };
        }

        // Ancestry's own per-person Detail panel surfaces crowdsourced "alternate
        // reading" submissions (bracketed values, each attributable to a specific
        // Ancestry user) for fields like Name and Birth Place, alongside its own
        // primary indexed reading (see ROADMAP.md). Confirmed live: selecting a
        // different person's row triggers zero new network requests - all people's
        // data for this page is already bulk-loaded - so reading this per person only
        // costs UI interaction time, not extra fetches.
        function findDetailTab() {
            return [...document.querySelectorAll('[role="tab"]')].find(t => t.textContent.trim() === 'Detail');
        }

        function findFieldRow(detailContentEl, label) {
            return [...detailContentEl.querySelectorAll('tr')].find(tr => {
                const th = tr.querySelector('th');
                return th && th.textContent.trim() === label;
            });
        }

        async function ensureInfoPanelOpen() {
            // The Detail/Related/Source panel is a separate, independently-toggled
            // panel from the index table (#indexPanel) - confirmed live: the Source
            // tab's own citation content never rendered until this was opened.
            //
            // Its open/closed state is a persisted user preference (confirmed live: a
            // fresh page load can start already open, carried over from a previous
            // browsing session), NOT something that always starts closed - the tab
            // bar/buttons exist in the DOM either way, so checking for the Detail tab's
            // mere presence is not a reliable "is it open" signal and caused a real bug:
            // blindly clicking the toggle closed an already-open panel instead of
            // opening a closed one. `.infopanel`'s own "opened" class is the real
            // indicator.
            const isOpen = () => {
                const panel = document.querySelector('.infopanel');
                return !!panel && panel.classList.contains('opened');
            };
            if (isOpen()) return;

            const infoPanelToggle = [...document.querySelectorAll('button, [role="button"]')]
                .find(el => /information panel/i.test(el.getAttribute('aria-label') || el.title || el.textContent || ''));
            if (infoPanelToggle) {
                infoPanelToggle.click();
                await waitForCondition(isOpen, {timeoutMs: 5000});
            }
        }

        function readAlternateEntries(fieldRow) {
            // Each value in this field is its own <div class="full-row"><button>...
            // </button></div>; when more than one exists, all but the last are
            // crowdsourced alternates (the last is Ancestry's own primary reading,
            // already captured from the index table, so it's not re-scraped here). The
            // bracketed alternate text is already sitting right there on the button -
            // no need to click it open to read the value itself.
            //
            // This deliberately does NOT click through to the "Added by <user>" popup
            // to capture a submitter anymore. That popup has two entirely different
            // rendering variants (a wide "callout" and a narrow "modal") depending on
            // viewport, sometimes takes several seconds to render, and has no reliable
            // close control in either variant (Escape does nothing, its own "Close
            // popup region" button doesn't actually dismiss it, and the modal variant
            // has none at all - only a genuine click outside its bounds works). A slow
            // render meant the code gave up waiting and moved on while the popup was
            // still pending, so it would surface moments later, orphaned, while the
            // script had already moved to a different field/person/page - with nothing
            // left watching to close it. That's confirmed live to be exactly what froze
            // a real gather. Not worth the risk for a "submitted by" note.
            if (!fieldRow) return [];
            const valueButtons = [...fieldRow.querySelectorAll('td .full-row > button.link')];
            if (valueButtons.length <= 1) return [];

            const alternateButtons = valueButtons.slice(0, -1);
            const seen = new Set();
            const entries = [];
            for (const btn of alternateButtons) {
                const cleanValue = btn.textContent.trim().replace(/^\[|\]\s*$/g, '').trim();
                if (!cleanValue) continue;
                const key = cleanValue.toLowerCase();
                if (seen.has(key)) continue;
                seen.add(key);
                entries.push({value: cleanValue});
            }
            return entries;
        }

        async function readPersonAlternates(row, expectedFullName) {
            // Click this person's own row to activate their Detail panel, wait for it
            // to actually reflect them (rather than a blind delay), then read
            // alternates for Name and Birth Place specifically - the two fields that
            // map onto GEDCOM facts (see ROADMAP.md); other fields' alternates aren't
            // captured.
            await ensureInfoPanelOpen();
            // Confirmed live: alternate-settle timeouts start suddenly partway down a page
            // (rows 1-25 fine, 26-30 all timed out) and never recover for the rest of that
            // page - consistent with a virtualized/windowed table only fully rendering rows
            // near the current scroll position, so a row further down may not be genuinely
            // clickable yet even though it's already in `rows`. Scrolling it into view first
            // is a no-op for an already-visible row, so this costs nothing on the common case.
            row.scrollIntoView({block: 'center'});
            row.click();

            const detailTab = findDetailTab();
            if (!detailTab) return {names: [], birthPlaces: [], timedOut: false};

            // scrapeSourceCitation() (called once per page, before this per-row loop
            // starts) leaves the info panel on the "Source" tab, and nothing switches
            // it back - confirmed live: every alternate-button click was landing on a
            // hidden Detail pane, so its tooltip never actually rendered. Reading
            // textContent bypasses visibility fine, but clicking a button to trigger
            // its popover needs the pane to genuinely be the active/displayed one.
            if (detailTab.getAttribute('aria-selected') !== 'true') {
                detailTab.click();
            }

            const settleWait = await waitForCondition(() => {
                const el = document.getElementById(detailTab.getAttribute('aria-controls'));
                const nameRow = el ? findFieldRow(el, 'Name') : null;
                if (!nameRow) return null;
                const valueButtons = [...nameRow.querySelectorAll('td .full-row > button.link')];
                const lastValue = valueButtons.length ? valueButtons[valueButtons.length - 1].textContent.trim() : '';
                return lastValue && expectedFullName && lastValue === expectedFullName ? el : null;
            }, {timeoutMs: 5000});

            if (DEBUG_MODE) {
                console.log(`[MGS DEBUG] alternates: settle for "${expectedFullName}" ${settleWait.timedOut ? 'TIMED OUT' : 'resolved'} after ${settleWait.elapsedMs}ms`);
            }

            // On timeout, settleWait.result is null specifically because the panel never
            // confirmed showing THIS person's name - falling back to "whatever's in the DOM
            // right now" here used to mean reading the panel while it still showed the
            // PREVIOUS row's data, silently attributing their alternate name/place to this
            // person instead (confirmed live: "Gabe" - a real alternate for one specific
            // person - showed up attached to other people too, whenever the panel was slow
            // to swap over). Missing this person's own alternates on a slow render is a far
            // smaller cost than misattributing someone else's, so a timeout now returns
            // nothing rather than guessing from stale DOM state.
            if (!settleWait.result) return {names: [], birthPlaces: [], timedOut: true};
            const detailContentEl = settleWait.result;

            const names = readAlternateEntries(findFieldRow(detailContentEl, 'Name'));
            const birthPlaces = readAlternateEntries(findFieldRow(detailContentEl, 'Birth Place'));

            if (DEBUG_MODE && (names.length || birthPlaces.length)) {
                console.log(`[MGS DEBUG] alternates: "${expectedFullName}" -> names: ${JSON.stringify(names)} | birthPlaces: ${JSON.stringify(birthPlaces)}`);
            }

            return {names, birthPlaces, timedOut: false};
        }

        async function extractCurrentPageData(rows) {
            // Confirmed live: once the alternate-reading settle-wait starts timing out (each
            // one eating its full 5s ceiling), it keeps timing out for every remaining row on
            // that page too - something about the page/panel got stuck, not this one row
            // specifically. Continuing to pay the full ceiling per remaining row for a result
            // we already know will come back empty either way (see readPersonAlternates'
            // timeout handling) is pure wasted time, so this stops attempting it for the rest
            // of the page after a couple of consecutive timeouts. Resets every page.
            let consecutiveAlternateTimeouts = 0;
            const ALTERNATE_TIMEOUT_CIRCUIT_BREAKER = 2;

            let imageId = getBaseImageId();
            let country = "USA", state = "", county = "", city = "", placeDetails = "", enumerationDistrict = "";

            let dbid = "0";
            const dbMatch = window.location.href.match(/collections\/(\d+)/i) || window.location.href.match(/dbid=(\d+)/i) || window.location.href.match(/view\/\d+:(\d+)/i);
            if (dbMatch) dbid = dbMatch[1];

            if (typeof unsafeWindow !== 'undefined' && unsafeWindow.__PRELOADED_STATE__) {
                const info = unsafeWindow.__PRELOADED_STATE__.viewer?.imageInfo;
                const pathArr = info?.browsePath || [];
                state = pathArr[0] || "";
                county = pathArr[1] || "";
                city = pathArr[2] || "";
                const ed = getEnumerationDistrict(pathArr, info?.structureType);
                enumerationDistrict = ed.value;
                placeDetails = pathArr.slice(3).filter((_, i) => (i + 3) !== ed.index).join(" - ") || "";
            }

            const citation = await scrapeSourceCitation();
            const imageIdGuess = parseFilmRollFromImageId(imageId);
            const filmNumber = citation.film || imageIdGuess.film;
            const rollNumber = citation.roll || imageIdGuess.roll;
            // The citation text is what will actually appear in the GEDCOM's own citation, so
            // prefer it over the browsePath-derived guess whenever it's actually available.
            if (citation.ed) enumerationDistrict = citation.ed;
            const repository = citation.repository || "";
            const repositoryLoc = citation.repositoryLoc || "";
            const publisher = citation.publisher || "";
            const pubLoc = citation.pubLoc || "";

            let rowIndex = 0;

            if (DEBUG_MODE) {
                console.log(`[MGS DEBUG] page ${batchPageCounter} | url: ${window.location.href} | cached pids: ${typeof unsafeWindow !== 'undefined' ? unsafeWindow.__mgs_pids.length : 'n/a'}`);
            }

            const pageEntry = {
                page_number: batchPageCounter,
                image_id: imageId,
                country: country, state: state, county: county, city: city, place_details: placeDetails,
                enumeration_district: enumerationDistrict, film_number: filmNumber, roll_number: rollNumber,
                apid_db: dbid !== "0" ? dbid : "",
                repository: repository, repository_loc: repositoryLoc, publisher: publisher, pub_loc: pubLoc,
                people: []
            };
            let columnNames = [];

            for (const row of rows) {
                const isHeader = row.classList.contains('indexPanelHeaderRow') || row.querySelectorAll('th, [role="columnheader"]').length > 0;

                if (isHeader) {
                    if (columnNames.length === 0) {
                        row.querySelectorAll('th, td, .grid-cell, [role="columnheader"], [role="gridcell"]').forEach(col => {
                            let text = (col.innerText || col.textContent).replace(/(\r\n|\n|\r)/gm, " ").trim();
                            columnNames.push(text);
                        });
                    }
                    continue;
                }

                const cols = row.querySelectorAll('td, .grid-cell, [role="gridcell"]');
                if (cols.length === 0) continue;

                let rowPid = "";
                let rowUrl = "";
                let pidSource = "none";
                const link = row.querySelector('a[href*="records/"]');
                if (link) {
                    const match = link.href.match(/records\/(\d+)/);
                    if (match) {
                        rowPid = match[1];
                        pidSource = "anchor href";
                    }
                }

                if (!rowPid) {
                    const domElements = [row, ...row.querySelectorAll('*')];
                    for (let el of domElements) {
                        const reactKey = Object.keys(el).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
                        if (reactKey) {
                            /** @type {any} */
                            let fiber = el[reactKey];
                            let attempts = 0;
                            while (fiber && attempts < 15) {
                                const props = fiber.memoizedProps || {};
                                let recordsToCheck = [props.rowData, props.record, (props.data ? props.data[props.rowIndex] : null)];
                                recordsToCheck.forEach(rec => {
                                    if (rec && typeof rec === 'object') {
                                        let potentialPid = rec.recordId || rec.clientRecordId || rec.id;
                                        if (!rowPid && potentialPid && String(potentialPid).match(/^\d{5,15}$/)) {
                                            rowPid = String(potentialPid);
                                            pidSource = "react fiber";
                                        }
                                    }
                                });
                                fiber = fiber.return;
                                attempts++;
                            }
                        }
                        if (rowPid) break;
                    }
                }

                if (!rowPid && typeof unsafeWindow !== 'undefined' && unsafeWindow.__mgs_pids[rowIndex]) {
                    rowPid = unsafeWindow.__mgs_pids[rowIndex];
                    pidSource = "network cache";
                }
                // No math-based pid fallback here anymore (see CHANGELOG) - it assumed the
                // URL's pId param was this page's own starting pid, but that param actually
                // carries the previous page's last-clicked record forward, so the guess
                // could collide with an already-seen pid and wipe out a whole page (see the
                // rowIndex-freeze fix below). anchor href/react fiber/network cache are
                // reliable enough on their own; Archivist's rec_id fallback covers a person
                // left with no pid at all.
                if (rowPid && dbid && dbid !== "0") {
                    rowUrl = `https://www.ancestry.com/search/collections/${dbid}/records/${rowPid}`;
                }

                // Incremented here - right after rowIndex is done being read for this row's
                // own network-cache lookup, but before any `continue` below - rather than
                // only at the very end of the loop body. Confirmed live: the duplicate-skip
                // continue used to bypass the increment entirely, freezing rowIndex on the
                // first duplicate hit, which then fed the (since-removed) math fallback the
                // same stale value for every remaining row, cascading into "every row on the
                // rest of the page marked duplicate" and silently wiping out an entire page's
                // worth of real people. Still needed now for the network-cache lookup and
                // the synthesized Line Number to track this row's true position on the page.
                rowIndex++;

                if (rowPid && seenPids.has(rowPid)) {
                    if (DEBUG_MODE) {
                        console.log(`[MGS DEBUG] Row ${rowIndex} | PID: ${rowPid} | Source: ${pidSource} | SKIPPED as duplicate`);
                    }
                    continue;
                }
                if (rowPid) {
                    seenPids.add(rowPid);
                }

                const columns = {};
                cols.forEach((col, i) => {
                    columns[columnNames[i] || `Column_${i + 1}`] = (col.innerText || col.textContent).replace(/(\r\n|\n|\r)/gm, " ").trim();
                });

                // Not every census year's index exposes a Line Number column. When it's
                // missing, synthesize one from this row's position on the page (1-based,
                // restarting at 1 on every page) so citations get a real line reference
                // instead of Archivist's "Line: X" filler.
                const hasLineNumber = Object.keys(columns).some(name => /line/i.test(name));
                if (!hasLineNumber) {
                    columns['Line Number'] = String(rowIndex);
                }

                debugLog(`Row ${rowIndex} | PID: ${rowPid} | Source: ${pidSource}`);

                // Alternate name/place capture (see ROADMAP.md): expects the Given
                // Name/Surname column keys the index table already uses. Falls back to
                // no-alternates rather than throwing if a given collection's own
                // Detail panel doesn't match this shape, so a scraping hiccup here
                // never costs the row's own already-scraped index data.
                let alternateNames = [], alternateBirthPlaces = [];
                if (consecutiveAlternateTimeouts < ALTERNATE_TIMEOUT_CIRCUIT_BREAKER) {
                    try {
                        const expectedFullName = `${columns['Given Name'] || ''} ${columns['Surname'] || ''}`.trim();
                        const alts = await readPersonAlternates(row, expectedFullName);
                        alternateNames = alts.names;
                        alternateBirthPlaces = alts.birthPlaces;
                        consecutiveAlternateTimeouts = alts.timedOut ? consecutiveAlternateTimeouts + 1 : 0;
                    } catch (err) {
                        if (DEBUG_MODE) {
                            console.warn(`[MGS DEBUG] Row ${rowIndex}: alternate-reading capture failed: ${err.message || err}`);
                        }
                    }
                } else if (DEBUG_MODE) {
                    console.log(`[MGS DEBUG] Row ${rowIndex}: skipping alternate-reading (${consecutiveAlternateTimeouts} consecutive timeouts already seen on this page).`);
                }

                pageEntry.people.push({
                    columns: columns, pid: rowPid, extracted_url: rowUrl,
                    alternate_names: alternateNames, alternate_birth_places: alternateBirthPlaces
                });
            }

            accumulatedPages.push(pageEntry);
        }

        async function downloadCurrentImage() {
            const startedAt = performance.now();
            return new Promise((resolve) => {
                let highResUrl = "";
                let imgFileName = getBaseImageId() + ".jpg";

                if (typeof unsafeWindow !== 'undefined' && unsafeWindow.__PRELOADED_STATE__) {
                    try {
                        let path = unsafeWindow.__PRELOADED_STATE__.viewer?.imageInfo?.imageDownloadUrl;
                        if (path) {
                            if (path.startsWith('http')) {
                                highResUrl = path;
                            } else {
                                highResUrl = (unsafeWindow.__PRELOADED_STATE__.mainOrigin || "https://www.ancestry.com") + path;
                            }
                        }
                    } catch (err) {
                    }
                }

                if (!highResUrl) {
                    if (window.showToast) window.showToast("Error: Could not find image URL.", "error");
                    resolve();
                    return;
                }

                const finish = () => {
                    if (DEBUG_MODE) {
                        console.log(`[MGS DEBUG] image download for ${imgFileName} finished after ${Math.round(performance.now() - startedAt)}ms`);
                    }
                    resolve();
                };

                GM_xmlhttpRequest({
                    method: "GET",
                    url: highResUrl,
                    responseType: "blob",
                    timeout: 20000,
                    ontimeout: function () {
                        if (window.showToast) window.showToast("Image request timed out, skipping.", 'error');
                        finish();
                    },
                    onload: function (response) {
                        if (response.status === 200) {
                            triggerBlobDownload(response.response, imgFileName, 'A/Images');
                            if (window.showToast) window.showToast(`Image captured: ${imgFileName}`, 'success', 1000);
                        } else {
                            if (window.showToast) window.showToast(`Failed to fetch image. Status: ${response.status}`, 'error');
                        }
                        finish();
                    },
                    onerror: function () {
                        if (window.showToast) window.showToast("Network error fetching image.", 'error');
                        finish();
                    }
                });
            });
        }

        function triggerBlobDownload(blob, jsonFileName, subfolder) {
            // Plain <a download> - GM_download was tried and reverted (see CHANGELOG):
            // its permission grant proved unreliable and reset on every script edit.
            // Chrome replaces "/" in a download attribute with "_" instead of creating
            // subfolders, so the subfolder is baked into the filename as a prefix
            // instead (matching what A.py/FS.py scan the Downloads root for).
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.setAttribute("href", url);
            link.setAttribute("download", `TMP_${subfolder.replace(/\//g, '_')}_${jsonFileName}`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }

        function triggerJsonDownload(jsonString, jsonFileName) {
            triggerBlobDownload(new Blob([jsonString], {type: 'application/json;charset=utf-8;'}), jsonFileName, 'A');
        }

        function downloadFinalJson() {
            if (accumulatedPages.length === 0) {
                if (window.showToast) window.showToast("No data gathered to download.", "error");
                return;
            }
            const {year, locationStr} = getYearAndLocation();
            const payload = {census_year: year, location: locationStr, pages: accumulatedPages};
            triggerJsonDownload(JSON.stringify(payload, null, 2), `${year} - ${locationStr} - ANC.json`);
            if (window.showToast) window.showToast("Success! Master JSON Downloaded.", "success", 5000);
        }

        // A page that dies mid-batch (an Ancestry viewer crash, a network drop, the tab being
        // closed) takes every accumulated page with it, since nothing was persisted until the
        // final Stop & Download - discovered the hard way when Ancestry's own viewer crashed
        // ~55 images into a real run and silently lost all of them. Periodically writing a
        // checkpoint means a crash only costs the pages since the last one.
        const CHECKPOINT_INTERVAL_PAGES = 20;

        function downloadCheckpointJson() {
            if (accumulatedPages.length === 0) return;
            const {year, locationStr} = getYearAndLocation();
            const payload = {census_year: year, location: locationStr, pages: accumulatedPages};
            triggerJsonDownload(
                JSON.stringify(payload, null, 2),
                `${year} - ${locationStr} [checkpoint through page ${batchPageCounter}].json`
            );
            if (window.showToast) window.showToast(`Checkpoint saved (page ${batchPageCounter}).`, "success", 1500);
        }

        function isNextBtnDisabled(btn) {
            return !!btn && (btn.disabled || btn.classList.contains('disabled') || btn.getAttribute('aria-disabled') === 'true' || btn.hasAttribute('disabled'));
        }

        async function runExtractionLoop() {
            while (isAutoExtracting) {

                // Checked up front (rather than only after extraction, as before) because
                // its answer bounds how cautious the blank-page check below needs to be.
                // Confirmed live: the Next button is still printed (just disabled) on a
                // genuinely blank/unindexed page - it's only ever missing/disabled on the
                // true last frame of the whole roll. So a confirmed-absent Next button here
                // means this page's own content, whatever it turns out to be, is the last
                // thing this gather will ever see - there's no "silently skip past a real
                // page in the middle of the roll" risk the way the old fixed ceiling
                // regression had, since there's nowhere left to skip to.
                const nextBtnSelector = 'button[aria-label="Next image"], .pagination.right button.page, .nextButton, button[title="Next image"]';
                const nextBtnWait = await waitForCondition(() => document.querySelector(nextBtnSelector),
                    {timeoutMs: 5000});
                const nextBtn = nextBtnWait.result;
                const isNextDisabled = isNextBtnDisabled(nextBtn);
                const isLastPage = !nextBtn || isNextDisabled;

                if (DEBUG_MODE) {
                    console.log(`[MGS DEBUG] nextBtn found: ${!!nextBtn} (${nextBtnWait.elapsedMs}ms) | disabled: ${!!isNextDisabled} | isLastPage: ${isLastPage}`);
                }

                // Event-driven: resolves the instant the button actually appears/enables
                // rather than on a fixed timer, via waitForCondition's MutationObserver.
                //
                // Ceiling reverted to 15s after a real regression: live testing showed a
                // genuinely indexed page (40 real rows, confirmed by adjacent pages having
                // the identical structure) take 13.3s just to navigate, and a shortened 6s
                // ceiling here wrongly classified it as unindexed and silently skipped its
                // data. A slower blank-page detection is a far smaller cost than silently
                // losing real genealogical data, so this errs long again - except on a
                // confirmed-last page (see isLastPage above), where that risk doesn't
                // apply, so a short ceiling costs nothing but time.
                const toggleWait = await waitForCondition(() => document.getElementById('indexPanelToggle'),
                    {timeoutMs: isLastPage ? 3000 : 15000});
                let toggleBtn = toggleWait.result;

                const isToggleBtnDisabled = () => toggleBtn.disabled || toggleBtn.classList.contains('disabled');

                let enableWait = {elapsedMs: 0, timedOut: false};
                if (toggleBtn) {
                    enableWait = await waitForCondition(() => !isToggleBtnDisabled(), {timeoutMs: 15000});
                }

                // A blank page never renders the toggle button at all, not just a disabled one;
                // treat "never found" the same as "found but disabled" so blank pages skip
                // straight to the download/next-page step instead of burning the row-wait
                // below waiting for a table that will never appear.
                const isUnindexed = !toggleBtn || isToggleBtnDisabled();

                if (DEBUG_MODE) {
                    console.log(`[MGS DEBUG] page ${batchPageCounter} indexing check | toggleBtn found: ${!!toggleBtn} (${toggleWait.elapsedMs}ms) | enable wait: ${enableWait.elapsedMs}ms | isUnindexed: ${isUnindexed}`);
                    if (isUnindexed) {
                        console.warn(`[MGS DEBUG] SKIPPING extraction on page ${batchPageCounter}: treated as unindexed. toggleBtn: ${toggleBtn ? toggleBtn.outerHTML.slice(0, 150) : 'null'}`);
                    }
                }

                if (!isUnindexed) {
                    const indexPanel = document.getElementById('indexPanel');
                    if (indexPanel && indexPanel.classList.contains('noDisplay')) {
                        // Reaching here already proves toggleBtn is truthy (isUnindexed above
                        // is !toggleBtn || toggleBtn.disabled || ...), so no need to re-guard it.
                        toggleBtn.click();
                        // No settle delay needed - the row-wait below is itself event-driven
                        // and will catch the panel's content whenever it actually renders.
                    }

                    const rowWait = await waitForCondition(() => {
                        let currentRows = document.querySelectorAll('table tr, .grid-row, [role="row"]');
                        if (currentRows.length <= 1) return null;

                        let dataRows = Array.from(currentRows).filter(r => !r.classList.contains('indexPanelHeaderRow') && r.querySelectorAll('th, [role="columnheader"]').length === 0);
                        if (dataRows.length === 0) return null;

                        let firstRowText = (dataRows[0].innerText || dataRows[0].textContent).trim();
                        let lastRowText = (dataRows[dataRows.length - 1].innerText || dataRows[dataRows.length - 1].textContent).trim();
                        let currentSignature = firstRowText + " | " + lastRowText;

                        if (currentSignature !== lastPageSignature && currentSignature.length > 5) {
                            lastPageSignature = currentSignature;
                            return currentRows;
                        }
                        return null;
                    }, {timeoutMs: 30000});
                    const rows = rowWait.result;

                    if (DEBUG_MODE) {
                        console.log(`[MGS DEBUG] row wait ${rowWait.timedOut ? 'TIMED OUT' : 'resolved'} after ${rowWait.elapsedMs}ms`);
                    }

                    if (rowWait.timedOut) {
                        debugLog("Timed out waiting for React table to update.");
                    } else if (rows && rows.length > 1) {
                        if (window.showToast) window.showToast(`Transcribing page ${batchPageCounter}...`, "success", 1500);
                        await extractCurrentPageData(rows);
                    }
                }

                // Awaited: letting this run in the background while the loop moved on to
                // the next page navigation let a page's image download overlap with the
                // next page's own fetch/navigation - the version of this script that ran
                // reliably always finished one image fully before moving on. That
                // reliability matters more than the few seconds saved per page.
                await downloadCurrentImage();

                if (batchPageCounter % CHECKPOINT_INTERVAL_PAGES === 0) {
                    downloadCheckpointJson();
                }

                // The top-of-loop check above is only ever a speculative hint for the
                // toggle-wait ceiling - it runs before extraction has given the page any
                // time to render, so a "not found yet" there does NOT mean "confirmed
                // absent". The actual stop-vs-continue decision always re-checks fresh
                // here, at the same point in the page lifecycle the original (pre-restructure)
                // code checked it, so it keeps exactly the same timing/safety margin for
                // telling "no next button yet" apart from "no next button, period" - only
                // reusing the earlier reference when it's still confirmed attached (i.e. we
                // already know the answer and a second wait would just be redundant).
                let finalNextBtn = nextBtn;
                let finalIsNextDisabled = isNextDisabled;
                if (!finalNextBtn || !document.body.contains(finalNextBtn)) {
                    const recheck = await waitForCondition(() => document.querySelector(nextBtnSelector),
                        {timeoutMs: 5000});
                    finalNextBtn = recheck.result;
                    finalIsNextDisabled = isNextBtnDisabled(finalNextBtn);
                }

                if (finalNextBtn && !finalIsNextDisabled) {
                    const prevUrl = window.location.href;
                    if (window.showToast) window.showToast("Advancing to next page...", "success", 1000);

                    if (typeof unsafeWindow !== 'undefined') {
                        unsafeWindow.__mgs_pids = [];
                    }

                    finalNextBtn.click();

                    const navWait = await waitForCondition(() => window.location.href !== prevUrl,
                        {timeoutMs: 15000});

                    if (DEBUG_MODE) {
                        console.log(`[MGS DEBUG] navigation ${navWait.timedOut ? 'TIMED OUT' : 'succeeded'} after ${navWait.elapsedMs}ms | new url: ${window.location.href}`);
                    }

                    if (navWait.timedOut) {
                        if (window.showToast) window.showToast("Navigation timed out. Stopping.", "error");
                        stopBatch();
                        break;
                    }

                    batchPageCounter++;
                } else {
                    if (DEBUG_MODE) {
                        console.log(`[MGS DEBUG] Stopping: nextBtn was ${!finalNextBtn ? 'not found' : 'found but disabled'}.`);
                    }
                    stopBatch();
                    break;
                }
            }
        }

        function startBatch() {
            isAutoExtracting = true;
            accumulatedPages = [];
            seenPids.clear();
            batchPageCounter = 1;
            lastPageSignature = "INITIAL_STATE_NOT_SET";

            if (window._startBtn) window._startBtn.style.display = 'none';
            if (window._stopBtn) window._stopBtn.style.display = 'block';
            if (window._statusLight) window._statusLight.classList.add('running');
            if (window.showToast) window.showToast("Starting Batch Extraction...", "success");
            runExtractionLoop().catch((err) => {
                console.error('[MGS] Extraction loop crashed:', err);
                if (window.showToast) window.showToast(`Extraction stopped: ${err.message || err}`, 'error', 4000);
                stopBatch();
            });
        }

        async function stopBatch() {
            if (!isAutoExtracting) return;
            isAutoExtracting = false;
            if (window._startBtn) window._startBtn.style.display = 'block';
            if (window._stopBtn) window._stopBtn.style.display = 'none';
            if (window._statusLight) window._statusLight.classList.remove('running');
            debugLog("Batch stopped.");
            // Every page's image download is already fully awaited before the loop moves
            // on (see runExtractionLoop), so there's never one still in flight here.
            downloadFinalJson();
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                initUI();
                if (shouldAutoStart && !isAutoExtracting) startBatch();
            });
        } else {
            initUI();
            if (shouldAutoStart && !isAutoExtracting) startBatch();
        }
    }

    // ==========================================
    // FAMILYSEARCH (FS) - church-register index + citation gather
    // ==========================================
    function runFamilySearchGather() {
        // GUARD: only run when explicitly triggered, same convention as Ancestry above.
        if (sessionStorage.getItem('run_fs_gather') !== 'true' && !window.location.href.includes('mgs_auto=1')) {
            return;
        }
        sessionStorage.removeItem('run_fs_gather');

        const DEBUG_MODE = true;
        let isRunning = false;
        let accumulatedItems = [];
        let seenItemIds = new Set();
        let itemsAtLastCheckpoint = 0;

        const shouldAutoStart = window.location.href.includes('mgs_auto=1');

        function debugLog(msg) {
            if (DEBUG_MODE) console.log(`[Voyageur FS] ${msg}`);
        }

        // ==========================================
        // UI (same visual conventions as Ancestry's, separate element ids so both can
        // theoretically be open in different tabs without colliding)
        // ==========================================
        function initUI() {
            if (document.getElementById('fs-ui-container')) return;

            const style = document.createElement('style');
            style.innerHTML = `
                #fs-ui-container { position: fixed; bottom: 20px; right: 20px; background-color: #1a1a1a; color: white; border-radius: 8px; padding: 12px 16px; font-family: sans-serif; z-index: 999999; box-shadow: 0 4px 12px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 10px; align-items: center; border: 1px solid #333; min-width: 180px; }
                #fs-header { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding-bottom: 4px; border-bottom: 1px solid #333; }
                #fs-title { font-weight: bold; font-size: 15px; }
                #fs-status-light { width: 12px; height: 12px; border-radius: 50%; background-color: #22c55e; box-shadow: 0 0 8px #22c55e; transition: all 0.3s ease; }
                #fs-status-light.running { background-color: #3b82f6; box-shadow: 0 0 10px #3b82f6; animation: fs-pulse 1.5s infinite; }
                @keyframes fs-pulse { 0% { transform: scale(0.95); opacity: 0.8; } 50% { transform: scale(1.1); opacity: 1; } 100% { transform: scale(0.95); opacity: 0.8; } }
                .fs-btn { color: white; border: none; border-radius: 6px; padding: 10px 14px; font-size: 14px; font-weight: bold; cursor: pointer; width: 100%; transition: background-color 0.2s; }
                #fs-start-btn { background-color: #2b7a4b; } #fs-start-btn:hover { background-color: #1e5935; }
                #fs-stop-btn { background-color: #991b1b; display: none; }
                #fs-toast-container { position: fixed; bottom: 140px; right: 20px; z-index: 999999; display: flex; flex-direction: column; gap: 10px; pointer-events: none; }
                .fs-toast { background-color: #333; color: #fff; padding: 12px 20px; border-radius: 6px; font-size: 14px; opacity: 0; transform: translateY(10px); transition: opacity 0.3s, transform 0.3s; }
                .fs-toast.show { opacity: 1; transform: translateY(0); }
                .fs-toast.error { background-color: #b91c1c; } .fs-toast.success { background-color: #15803d; }
            `;
            document.head.appendChild(style);

            const toastContainer = document.createElement('div');
            toastContainer.id = 'fs-toast-container';
            document.body.appendChild(toastContainer);

            window.fsShowToast = function (message, type = 'success', duration = 2500) {
                const toast = document.createElement('div');
                toast.className = `fs-toast ${type}`;
                toast.innerText = message;
                toastContainer.appendChild(toast);
                void toast.offsetWidth;
                toast.classList.add('show');
                setTimeout(() => {
                    toast.classList.remove('show');
                    setTimeout(() => toast.remove(), 300);
                }, duration);
            };

            const panel = document.createElement('div');
            panel.id = 'fs-ui-container';

            const header = document.createElement('div');
            header.id = 'fs-header';
            const statusLight = document.createElement('div');
            statusLight.id = 'fs-status-light';
            const title = document.createElement('span');
            title.id = 'fs-title';
            title.innerText = 'Voyageur (FS)';
            header.appendChild(statusLight);
            header.appendChild(title);
            panel.appendChild(header);

            const startBtn = document.createElement('button');
            startBtn.id = 'fs-start-btn';
            startBtn.className = 'fs-btn';
            startBtn.innerText = 'Start Auto-Batch';

            const stopBtn = document.createElement('button');
            stopBtn.id = 'fs-stop-btn';
            stopBtn.className = 'fs-btn';
            stopBtn.innerText = 'Stop & Download JSON';

            panel.appendChild(startBtn);
            panel.appendChild(stopBtn);
            document.body.appendChild(panel);

            startBtn.addEventListener('click', startBatch);
            stopBtn.addEventListener('click', stopBatch);

            window._fsStartBtn = startBtn;
            window._fsStopBtn = stopBtn;
            window._fsStatusLight = statusLight;
        }

        // ==========================================
        // DOM HELPERS
        // ==========================================
        function findByExactText(selector, text) {
            // FamilySearch's own CSS class names aren't a stable target (same reasoning as
            // Ancestry's findLeafByExactText) - match by visible text instead.
            const candidates = document.querySelectorAll(selector);
            for (const el of candidates) {
                if (el.textContent.trim() === text) return el;
            }
            return null;
        }

        async function clickTab(tabText) {
            // Event-driven (see waitForCondition) rather than polling every 100ms for up to
            // 5s. No settle delay after the click either - every caller already waits on its
            // own specific downstream condition (real citation text, an actually-populated
            // table) rather than assuming a fixed delay is enough.
            const tabWait = await waitForCondition(() => findByExactText('[role="tab"], button, a', tabText),
                {timeoutMs: 5000});
            if (!tabWait.result) return false;
            tabWait.result.click();
            return true;
        }

        function getItemId() {
            const match = window.location.pathname.match(/ark:\/61903\/([^/?#]+)/);
            return match ? decodeURIComponent(match[1]) : "";
        }

        // ==========================================
        // SCRAPING
        // ==========================================
        async function scrapeCitationAndCatalog() {
            const ok = await clickTab('Information');
            if (!ok) return {citationText: "", catalogItems: []};

            // FamilySearch renders the "Citation" heading immediately on tab switch but fills in
            // the actual prose a beat later, showing a literal "No citation is available." placeholder
            // in the meantime - waiting only for the heading to exist (rather than for real text to
            // replace the placeholder) meant every image after the first got its citation scraped
            // before it was ready. Event-driven (see waitForCondition) rather than polling every
            // 200ms for up to 10s.
            const citationWait = await waitForCondition(() => {
                const citationHeading = findByExactText('h1, h2, h3, h4, h5, h6', 'Citation');
                if (!citationHeading) return null;
                // The citation prose sits alongside the heading inside the same panel; grab the
                // panel's text and strip the heading/button lines around it rather than assuming
                // a specific sibling structure, since that's the part most likely to shift.
                const panelText = citationHeading.parentElement ? citationHeading.parentElement.innerText : "";
                const match = panelText.match(/Citation\s*\n+([\s\S]*?)(?:\n+COPY CITATION|$)/i);
                const candidateText = match ? match[1].trim() : "";
                return (candidateText && candidateText.toLowerCase() !== 'no citation is available.') ? candidateText : null;
            }, {timeoutMs: 10000});
            const citationText = citationWait.result || "";

            const catalogItems = [];
            const table = document.querySelector('table');
            if (table) {
                const rows = [...table.querySelectorAll('tr')];
                for (const row of rows.slice(1)) {
                    const cells = [...row.querySelectorAll('th, td')];
                    if (cells.length >= 3) {
                        catalogItems.push({
                            label: (cells[0].innerText || '').trim(),
                            item_number: (cells[1].innerText || '').trim(),
                            note: (cells[2].innerText || '').trim()
                        });
                    }
                }
            }

            return {citationText, catalogItems};
        }

        async function parseHouseholdSections() {
            const ok = await clickTab('Names');
            if (!ok) return [];

            // FamilySearch renders the "Names" panel shell immediately but fills in household
            // content a beat later (same skeleton-then-fill race already handled for the old
            // Image Index table and the citation panel) - wait for at least one household
            // heading, or the panel's own "no names" state, before reading anything.
            const namesWait = await waitForCondition(() => {
                if (document.body.innerText.includes('No names have been indexed for this image')) {
                    return {empty: true};
                }
                const heading = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')]
                    .find(h => /\sHousehold$/.test(h.textContent.trim()));
                return heading ? {found: true} : null;
            }, {timeoutMs: 15000});
            if (!namesWait.result || namesWait.result.empty) return [];

            // FamilySearch's own household heading level/tag isn't assumed stable (matches this
            // file's own "don't trust FamilySearch's markup" convention) - collect every heading
            // in document order and hand each one to findHouseholdContainer() by position.
            const headings = getHouseholdHeadings();

            const sections = [];
            for (let i = 0; i < headings.length; i++) {
                const container = findHouseholdContainer(i);
                if (!container) continue;

                const items = [...container.querySelectorAll('[role="listitem"], li')];
                const members = items.map(item => {
                    // The list item's own visible text is "{Name}\n{Role}" (confirmed live: e.g.
                    // "Joseph Rolette\nPrimary | Spouse") - the accessible "Click to view {name}"
                    // button is a second, separately-labeled element inside the same item, not the
                    // one carrying the name/role text itself. Only name/roleHint are kept here -
                    // NOT a reference to the button element itself. Confirmed live: FamilySearch
                    // re-renders this list shortly after it first appears (still settling/loading),
                    // which silently detaches any button reference captured this early - clicking a
                    // detached button does nothing, no error, and every scrapePersonDetail() call
                    // then times out waiting for a panel that never opens. Buttons are instead
                    // re-located fresh at click time by locateMemberButton(), using this same
                    // household-index + item-index addressing.
                    const lines = item.innerText.split('\n').map(s => s.trim()).filter(Boolean);
                    return {name: lines[0] || '', roleHint: lines[1] || ''};
                });

                sections.push({householdLabel: headings[i].textContent.trim(), members});
            }
            return sections;
        }

        // Scope to the Names panel's own <aside> (identified by its own "Names" heading) -
        // confirmed live that document-wide list queries pick up unrelated <ul>s (e.g. the
        // "Manage Indexes" dropdown menu) ahead of the real household lists.
        function getNamesPanel() {
            return [...document.querySelectorAll('aside')]
                .find(a => [...a.querySelectorAll('h1,h2,h3,h4,h5,h6')].some(h => h.textContent.trim() === 'Names'));
        }

        function getHouseholdHeadings() {
            const panel = getNamesPanel();
            if (!panel) return [];
            return [...panel.querySelectorAll('h1, h2, h3, h4, h5, h6')]
                .filter(h => /\sHousehold$/.test(h.textContent.trim()));
        }

        // Re-run fresh every time a household's list container is needed (parsing AND clicking)
        // rather than caching the result, since the panel keeps mutating after it first appears -
        // see parseHouseholdSections()'s own note on why cached button references go stale.
        function findHouseholdContainer(householdIndex) {
            const panel = getNamesPanel();
            if (!panel) return null;
            const headings = getHouseholdHeadings();
            const heading = headings[householdIndex];
            if (!heading) return null;
            const nextHeading = headings[householdIndex + 1] || null;
            const listContainers = [...panel.querySelectorAll('[role="list"], ul, ol')];
            const inRange = (el) => {
                const afterThis = heading.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING;
                // Confirmed live: this must check that `el` PRECEDES nextHeading, not that it
                // FOLLOWS it - the two are easy to invert since both read as "& FOLLOWING" from
                // one comparison direction or the other. Getting this backwards makes every
                // heading grab the *next* household's list instead of its own.
                const beforeNext = !nextHeading
                    || (nextHeading.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING);
                return afterThis && beforeNext;
            };
            return listContainers.find(inRange) || null;
        }

        function locateMemberButton(householdIndex, memberIndex) {
            const container = findHouseholdContainer(householdIndex);
            if (!container) return null;
            const items = [...container.querySelectorAll('[role="listitem"], li')];
            const item = items[memberIndex];
            if (!item) return null;
            return [...item.querySelectorAll('button')].find(b => {
                const label = b.getAttribute('aria-label') || b.textContent || '';
                return label.trim().startsWith('Click to view');
            }) || null;
        }

        function readRecordArkFromOpenPanel() {
            const aside = document.querySelector('aside');
            const headingEl = aside && [...aside.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                .find(h => h.textContent.trim() === 'View Name');
            if (!headingEl) return null;
            const links = [...aside.querySelectorAll('a[href]')]
                .filter(a => headingEl.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING);
            const recordArkLink = links.find(a => /ark:\/61903\/1:1:([A-Z0-9]{4}-[A-Z0-9]{3,4})/.test(a.getAttribute('href')));
            return recordArkLink
                ? recordArkLink.getAttribute('href').match(/ark:\/61903\/1:1:([A-Z0-9]{4}-[A-Z0-9]{3,4})/)[1]
                : null;
        }

        // includeHouseholdRelationships is only meaningful (and only reliable) when called for
        // a household's own head/primary member (raw index 0) - confirmed live that FamilySearch's
        // Household Details, viewed from a NON-head member's own panel, defaults every other
        // member's relationship to "No Relation" instead of computing it (e.g. viewing a child's
        // panel showed their own mother AND sibling both as "No Relation"). The head's panel is
        // the only place this data is actually correct, so it's read once per household and
        // applied by position to every member - see scrapeNamesPanel().
        async function scrapePersonDetail(householdIndex, memberIndex, previousRecordArk, {includeHouseholdRelationships = false} = {}) {
            // Re-located fresh right here rather than accepting a button reference from the
            // caller - see parseHouseholdSections()'s note on why a reference captured earlier
            // goes stale.
            const viewButton = locateMemberButton(householdIndex, memberIndex);
            if (!viewButton) {
                debugLog(`scrapePersonDetail: could not locate household ${householdIndex} member ${memberIndex}`);
                return {recordArk: '', personArk: '', given: '', surname: '', gender: '', age: '',
                        householdRelationships: []};
            }
            viewButton.click();

            // Wait for the record ark to actually CHANGE, not for the target name to appear in
            // the panel - two people in the same household can share a name (confirmed live:
            // this design's own reference record has a "Joseph Rolette" head and a "Joseph
            // Rolette" child), so waiting on name text can resolve instantly against the
            // still-open PREVIOUS person's panel before it re-renders.
            const arkWait = await waitForCondition(() => {
                const ark = readRecordArkFromOpenPanel();
                return (ark && ark !== previousRecordArk) ? ark : null;
            }, {timeoutMs: 10000});
            if (!arkWait.result) {
                debugLog(`scrapePersonDetail: record ark never changed from "${previousRecordArk}"`);
                return {recordArk: '', personArk: '', given: '', surname: '', gender: '', age: '',
                        householdRelationships: []};
            }

            const aside = document.querySelector('aside');
            const headingEl = [...aside.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                .find(h => h.textContent.trim() === 'View Name');
            const fullText = aside.innerText;
            const viewIdx = fullText.indexOf('View Name');
            const panelText = fullText.slice(viewIdx);

            // "VIEW RECORD" always points at this specific indexed entry (record_ark, already
            // captured above via readRecordArkFromOpenPanel) - the Tree Attachment section, when
            // present, points at the real Family Tree person (person_ark == PID) via a DIFFERENT
            // href shape than the old UI used ("/en/tree/person/{PID}", no "/details/" segment -
            // confirmed live, the old "/tree/person/details/{PID}" regex no longer matches
            // anything on this page). Scoped to links after the "View Name" heading so the
            // still-present household list above it can't contribute a stray match.
            const links = [...aside.querySelectorAll('a[href]')]
                .filter(a => headingEl.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING);
            const personArkLink = links.find(a => /\/tree\/person\/([A-Z0-9]{4}-[A-Z0-9]{3,4})(?:$|[/?])/.test(a.getAttribute('href')));
            const personArkMatch = personArkLink
                && personArkLink.getAttribute('href').match(/\/tree\/person\/([A-Z0-9]{4}-[A-Z0-9]{3,4})/);
            const personArk = personArkMatch ? personArkMatch[1] : '';

            // Essential Information/Additional Facts render as "Heading\nLabel: Value\n..." blocks
            // in the panel's own innerText (confirmed live) - parsed the same way
            // scrapeCitationAndCatalog already parses the Citation panel's prose.
            const givenMatch = panelText.match(/Given Name:\s*(.+)/);
            const surnameMatch = panelText.match(/Surname:\s*(.+)/);
            const sexMatch = panelText.match(/Sex:\s*(\w+)/);
            const ageMatch = panelText.match(/Age:\s*(\d+)/);

            let householdRelationships = [];
            if (includeHouseholdRelationships) {
                const householdMatch = panelText.match(/Household Details([\s\S]*?)(?:\n\n|Events\n|$)/);
                if (householdMatch) {
                    // Confirmed live shape: "{Relationship}\n{Name}" pairs, one per household
                    // member INCLUDING the head themselves, whose own pair reads
                    // "Household • Census\n{HeadName}" rather than a real relationship label.
                    const relPairs = [...householdMatch[1].matchAll(
                        /(Household\s*•\s*Census|Spouse|Child|Father|Mother|No Relation)\n(.+)/g)];
                    householdRelationships = relPairs.map(([, label]) =>
                        label.startsWith('Household') ? 'Head' : label);
                }
            }

            return {
                recordArk: arkWait.result, personArk,
                given: givenMatch ? givenMatch[1].trim() : '',
                surname: surnameMatch ? surnameMatch[1].trim() : '',
                gender: sexMatch ? sexMatch[1].trim().toUpperCase() : '',
                age: ageMatch ? ageMatch[1].trim() : '',
                householdRelationships,
            };
        }

        async function scrapeNamesPanel() {
            const sections = await parseHouseholdSections();
            if (sections.length === 0) return [];

            const rows = [];
            let lastRecordArk = null;
            for (let familyNumber = 0; familyNumber < sections.length; familyNumber++) {
                const {members} = sections[familyNumber];
                if (members.length === 0) continue;

                // The head/primary is always the household's first-listed member (confirmed
                // live) - their own Household Details panel is the only reliable source for
                // every other member's relationship-to-head (see scrapePersonDetail's own
                // note), so it's read once per household and applied by position below.
                const headDetail = await scrapePersonDetail(familyNumber, 0, lastRecordArk,
                    {includeHouseholdRelationships: true});
                lastRecordArk = headDetail.recordArk;

                // Confirmed live: a household where FamilySearch never indexed real
                // relationships (every Names-list role reads bare "Primary") reports every
                // member as "No Relation" rather than leaving the field blank - fabricating
                // that as real data would be worse than omitting the column entirely, so the
                // column is only populated when at least one member has an actual
                // Spouse/Child/Father/Mother relationship recorded.
                const rawRelationships = headDetail.householdRelationships;
                const hasRealRelationshipData = rawRelationships.some(r => r !== 'Head' && r !== 'No Relation');
                const relationships = hasRealRelationshipData ? rawRelationships : [];

                // FamilySearch's own index can surface the same person twice within one
                // household (confirmed live: "Josette Cardinal" and "J Baptiste Cardinal" both
                // appeared twice under "J Baptiste Cardinal Household") - build_census_json()
                // has no row-level dedup of its own, so a duplicate scraped here is a duplicate
                // person in the final GEDCOM. Skip a repeat of the same name+role within the
                // same household rather than scraping it a second time - relationship lookup
                // still uses `idx`, the member's ORIGINAL position, since that's what stays
                // aligned with `relationships`.
                const seen = new Set();
                for (let idx = 0; idx < members.length; idx++) {
                    const member = members[idx];
                    const key = `${member.name}|${member.roleHint}`;
                    if (seen.has(key)) continue;
                    seen.add(key);

                    const detail = idx === 0 ? headDetail
                        : await scrapePersonDetail(familyNumber, idx, lastRecordArk);
                    lastRecordArk = detail.recordArk;

                    const columns = {
                        'Given Name': detail.given || member.name.split(' ').slice(0, -1).join(' '),
                        'Surname': detail.surname || member.name.split(' ').slice(-1).join(' '),
                        'Gender': detail.gender,
                        'Age': detail.age,
                        'Family Number': String(familyNumber + 1),
                    };
                    if (relationships[idx]) {
                        columns['Relationship to Head'] = relationships[idx];
                    }

                    rows.push({columns, person_ark: detail.recordArk, attached_fsftid: detail.personArk});
                }
            }
            return rows;
        }

        async function scrapeCurrentImage() {
            const itemId = getItemId();
            if (!itemId || seenItemIds.has(itemId)) return;

            const rows = await scrapeNamesPanel();
            const {citationText, catalogItems} = await scrapeCitationAndCatalog();
            // Awaited before moving on to the next image, same convention as Ancestry's
            // own per-page image download.
            await downloadFsImage(itemId);

            seenItemIds.add(itemId);
            accumulatedItems.push({item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows});

            debugLog(`Scraped item ${itemId}: ${rows.length} index rows.`);
        }

        // ==========================================
        // BATCH LOOP
        // ==========================================
        async function runLoop() {
            while (isRunning) {
                if (window.fsShowToast) window.fsShowToast(`Gathering ${getItemId()}...`, 'success', 1200);
                await scrapeCurrentImage();

                if (accumulatedItems.length - itemsAtLastCheckpoint >= FS_CHECKPOINT_INTERVAL_ITEMS) {
                    downloadCheckpointJson();
                    itemsAtLastCheckpoint = accumulatedItems.length;
                }

                // Event-driven (see waitForCondition) rather than polling every 200ms for up
                // to 5s.
                const nextBtnSelector = 'button[aria-label="Next Image"], button[aria-label="Next image"], '
                    + '.pagination.right button.page, button[title="Next Image"]';
                const nextBtnWait = await waitForCondition(() => document.querySelector(nextBtnSelector),
                    {timeoutMs: 5000});
                const nextBtn = nextBtnWait.result;
                const isDisabled = nextBtn && (nextBtn.disabled || nextBtn.getAttribute('aria-disabled') === 'true');

                if (nextBtn && !isDisabled) {
                    const prevUrl = window.location.href;
                    nextBtn.click();
                    // No post-nav settle delay needed - scrapeCurrentImage's own downstream
                    // waits (scrapeNamesPanel/scrapeCitationAndCatalog) already handle "has the
                    // new page's content rendered yet" on their own terms.
                    const navWait = await waitForCondition(() => window.location.href !== prevUrl,
                        {timeoutMs: 10000});
                    if (navWait.timedOut) {
                        if (window.fsShowToast) window.fsShowToast('Navigation timed out. Stopping.', 'error');
                        stopBatch();
                        break;
                    }
                } else {
                    stopBatch();
                    break;
                }
            }
        }

        function triggerFsJsonDownload(jsonString, jsonFileName) {
            // Same reasoning as the Ancestry side's triggerBlobDownload: GM_download's
            // "downloads" permission grant proved unreliable (resets on every script
            // edit, and even when granted sometimes ignored the requested name). Plain
            // <a download> always honors the exact name given - matching the original
            // CensusExtractor.js. Chrome replaces "/" in the download attribute with "_"
            // rather than creating a subfolder, so the prefix keeps FS.py's Downloads-root
            // scan able to pick this out from unrelated files.
            const blob = new Blob([jsonString], {type: 'application/json;charset=utf-8;'});
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.setAttribute('href', url);
            link.setAttribute('download', `TMP_FS_${jsonFileName}`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }

        function downloadFsImage(itemId) {
            // FamilySearch's own image viewer exposes a "Download" button that fetches the
            // full scanned page (not a tile, not a thumbnail - confirmed against a real
            // record: 3346x4527, full resolution) from its deepzoomcloud storage service,
            // keyed by the same item_id already scraped for citations above.
            //
            // Direct access from this page's own origin is blocked - confirmed live across
            // three separate mechanisms (GM_xmlhttpRequest hangs to timeout; a plain
            // cross-origin fetch() gets 429 even on a brand-new item_id never requested
            // before; a plain cross-origin <a download> triggers nothing). A genuine
            // top-level navigation to the same URL always works (what the site's own
            // "Print" button does) - loading it into a hidden iframe gets that same real
            // navigation without popup-blocker issues (window.open() gets blocked, since
            // this isn't a trusted user gesture) and without disturbing this page's own
            // gather loop state. runFsImageIframeHelper (this script's own top-level
            // dispatch, matched via the sg30p0.familysearch.org @match rule) then runs
            // same-origin inside that iframe and does the actual fetch+download, signaling
            // back via postMessage when done.
            const imageUrl = `https://sg30p0.familysearch.org/service/records/storage/`
                + `deepzoomcloud/dz/v1/${encodeURIComponent(itemId)}/$dist`;
            debugLog(`downloadFsImage loading via hidden iframe: ${imageUrl}`);

            return new Promise((resolve) => {
                let settled = false;
                const finish = () => {
                    if (settled) return;
                    settled = true;
                    window.removeEventListener('message', onMessage);
                    clearTimeout(safetyTimer);
                    if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
                    resolve();
                };

                const onMessage = (event) => {
                    if (!event.data || typeof event.data !== 'object' || !('voyageurFsImage' in event.data)) return;
                    if (event.data.voyageurFsImage === 'data') {
                        // The actual download click happens here, in this top-level
                        // frame's own context - not inside the iframe (see
                        // runFsImageIframeHelper's own comment for why).
                        const blob = new Blob([event.data.buffer], {type: 'image/jpeg'});
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.setAttribute('href', url);
                        link.setAttribute('download', `TMP_FS_Images_${event.data.fileName}`);
                        link.style.visibility = 'hidden';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        URL.revokeObjectURL(url);
                        if (window.fsShowToast) window.fsShowToast(`Image captured: ${event.data.fileName}`, 'success', 1000);
                    } else {
                        debugLog(`downloadFsImage iframe reported error: ${JSON.stringify(event.data)}`);
                        if (window.fsShowToast) window.fsShowToast('Failed to fetch image.', 'error');
                    }
                    finish();
                };
                window.addEventListener('message', onMessage);

                const iframe = document.createElement('iframe');
                iframe.style.display = 'none';
                iframe.src = imageUrl;
                document.body.appendChild(iframe);

                // Safety net in case the iframe never loads or never gets a chance to run
                // (blocked, slow network, etc.) - one image's failure shouldn't hang the
                // whole batch forever.
                const safetyTimer = setTimeout(finish, 15000);
            });
        }

        function downloadFinalJson() {
            if (accumulatedItems.length === 0) {
                if (window.fsShowToast) window.fsShowToast('No data gathered to download.', 'error');
                return;
            }

            const collectionTitle = document.title || 'FamilySearch Gather';
            const payload = {source: 'FS', collection_title: collectionTitle, items: accumulatedItems};
            const safeName = collectionTitle.replace(/[/\\?%*:|"<>]/g, '-').slice(0, 120);
            triggerFsJsonDownload(JSON.stringify(payload, null, 2), `FS - ${safeName}.json`);

            if (window.fsShowToast) window.fsShowToast('Success! Gather JSON downloaded.', 'success', 5000);
        }

        // Same reasoning as the Ancestry side: a mid-batch crash takes every accumulated item
        // with it since nothing is persisted until the final Stop & Download. Periodic
        // checkpoints cap the loss to the items since the last one.
        const FS_CHECKPOINT_INTERVAL_ITEMS = 20;

        function downloadCheckpointJson() {
            if (accumulatedItems.length === 0) return;
            const collectionTitle = document.title || 'FamilySearch Gather';
            const payload = {source: 'FS', collection_title: collectionTitle, items: accumulatedItems};
            const safeName = collectionTitle.replace(/[/\\?%*:|"<>]/g, '-').slice(0, 120);
            triggerFsJsonDownload(
                JSON.stringify(payload, null, 2),
                `FS - ${safeName} [checkpoint ${accumulatedItems.length} items].json`
            );
            if (window.fsShowToast) window.fsShowToast(`Checkpoint saved (${accumulatedItems.length} items).`, 'success', 1500);
        }

        function startBatch() {
            isRunning = true;
            accumulatedItems = [];
            seenItemIds.clear();
            itemsAtLastCheckpoint = 0;
            if (window._fsStartBtn) window._fsStartBtn.style.display = 'none';
            if (window._fsStopBtn) window._fsStopBtn.style.display = 'block';
            if (window._fsStatusLight) window._fsStatusLight.classList.add('running');
            if (window.fsShowToast) window.fsShowToast('Starting Gather...', 'success');
            runLoop().catch((err) => {
                console.error('[Voyageur FS] Loop crashed:', err);
                if (window.fsShowToast) window.fsShowToast(`Gather stopped: ${err.message || err}`, 'error', 4000);
                stopBatch();
            });
        }

        function stopBatch() {
            if (!isRunning) return;
            isRunning = false;
            if (window._fsStartBtn) window._fsStartBtn.style.display = 'block';
            if (window._fsStopBtn) window._fsStopBtn.style.display = 'none';
            if (window._fsStatusLight) window._fsStatusLight.classList.remove('running');
            debugLog('Batch stopped.');
            downloadFinalJson();
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                initUI();
                if (shouldAutoStart && !isRunning) startBatch();
            });
        } else {
            initUI();
            if (shouldAutoStart && !isRunning) startBatch();
        }
    }

})();
