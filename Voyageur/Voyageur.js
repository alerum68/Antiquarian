// ==UserScript==
// @name         Voyageur
// @namespace    https://github.com/alerum68/Scriptorium
// @version      0.3.27
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

    // Shared by any gather's town/place-boundary stop condition (see runExtractionLoop
    // below): true only when every one of these fields matches exactly. enumeration_district
    // is included alongside city because some collections leave city blank/"Not Stated" for
    // an entire roll - ED is the finer-grained boundary those records actually expose.
    function placesMatch(a, b) {
        return a.state === b.state && a.county === b.county && a.city === b.city
            && a.enumeration_district === b.enumeration_district;
    }

    // Persists in-flight batch progress across a `location.reload()` triggered by the
    // index-not-loaded retry (see runExtractionLoop). Tampermonkey re-runs this entire
    // script from scratch on reload - without this, startBatch()'s reset of
    // accumulatedPages/batchPageCounter/seenPids would silently discard every page
    // gathered so far. sessionStorage (not GM_setValue) is deliberate: this only needs to
    // survive a same-tab reload, not a browser restart, and needs no new script permissions.
    const RELOAD_STATE_KEY = 'voyageur_a_reload_state';

    function saveReloadState(state) {
        sessionStorage.setItem(RELOAD_STATE_KEY, JSON.stringify({
            pageUrl: window.location.href,
            accumulatedPages: state.accumulatedPages,
            batchPageCounter: state.batchPageCounter,
            seenPids: Array.from(state.seenPids),
            firstPagePlace: state.firstPagePlace,
            indexReloadAttempts: state.indexReloadAttempts,
        }));
    }

    // Returns null (rather than restoring) whenever the saved state doesn't obviously
    // belong to the page we're now on - a real reload keeps the URL identical, so any
    // mismatch means this is a different navigation, not the reload we saved this for.
    function loadReloadState() {
        const raw = sessionStorage.getItem(RELOAD_STATE_KEY);
        if (!raw) return null;
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            return null;
        }
        if (parsed.pageUrl !== window.location.href) return null;
        return {
            accumulatedPages: parsed.accumulatedPages || [],
            batchPageCounter: parsed.batchPageCounter || 1,
            seenPids: new Set(parsed.seenPids || []),
            firstPagePlace: parsed.firstPagePlace || null,
            indexReloadAttempts: parsed.indexReloadAttempts || 0,
        };
    }

    function clearReloadState() {
        sessionStorage.removeItem(RELOAD_STATE_KEY);
    }

    // Same sessionStorage-survives-a-reload convention as RELOAD_STATE_KEY above, but keyed
    // by runId (the gather's own mgs_run URL param, stable across every image in one run)
    // rather than the exact page URL. Confirmed live, and unexpected at first: clicking
    // FamilySearch's own "Next Image" button is a REAL page navigation, not client-side
    // routing, so Tampermonkey re-injects this entire script from scratch on every single
    // image. Keying by exact pageUrl (as originally written) never matched after such a
    // navigation, since the URL legitimately changes to the next image's own ark. Without
    // this fix, accumulatedItems silently reset to empty on every image after the first, and
    // only the LAST scraped item ever survived to the final JSON - confirmed live: a real
    // 3-image gather run's downloaded JSON contained exactly 1 item, not 3.
    const FS_RELOAD_STATE_KEY = 'voyageur_fs_reload_state';

    function saveFsReloadState(runId, state) {
        sessionStorage.setItem(FS_RELOAD_STATE_KEY, JSON.stringify({
            runId,
            accumulatedItems: state.accumulatedItems,
            seenItemIds: Array.from(state.seenItemIds),
            itemsAtLastCheckpoint: state.itemsAtLastCheckpoint,
        }));
    }

    function loadFsReloadState(runId) {
        const raw = sessionStorage.getItem(FS_RELOAD_STATE_KEY);
        if (!raw) return null;
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            return null;
        }
        if (parsed.runId !== runId) return null;
        return {
            accumulatedItems: parsed.accumulatedItems || [],
            seenItemIds: new Set(parsed.seenItemIds || []),
            itemsAtLastCheckpoint: parsed.itemsAtLastCheckpoint || 0,
        };
    }

    function clearFsReloadState() {
        sessionStorage.removeItem(FS_RELOAD_STATE_KEY);
    }

    // FamilySearch orchestration-API graph traversal - confirmed live (see
    // docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md) that
    // FamilySearch's own client fires GET .../orchestration/sls/image/{ark} automatically on
    // page load, returning a flat `elements` array cross-referenced by UUID/ark via
    // subElements/superElements - not a nested tree. These are pure, DOM-free functions:
    // build the {id: element} index once per response, then walk it.
    function buildFsElementIndex(apiResponse) {
        const byId = {};
        (apiResponse.elements || []).forEach((e) => { byId[e.id] = e; });
        return byId;
    }

    function fsFieldText(fieldElement) {
        const fv = fieldElement && fieldElement.fieldValues && fieldElement.fieldValues[0];
        if (!fv) return '';
        if (fv.normalizedValues && fv.normalizedValues[0]) return fv.normalizedValues[0].text || '';
        if (fv.origValue) return fv.origValue.text || '';
        return '';
    }

    function fsFindChild(byId, subElements, elementType) {
        if (!subElements) return null;
        for (const ref of subElements) {
            const el = byId[ref.id];
            if (el && el.elementType === elementType) return el;
        }
        return null;
    }

    // Direct indirection: PERSON -> FIELD (matching fieldType) -> text. Confirmed live for
    // RELATIONSHIP_TO_HEAD, MARITAL_STATUS, OCCUPATION, RACE_OR_COLOR, FTHR_BIR_PLACE,
    // MTHR_BIR_PLACE, SEX_CODE, SOURCE_HOUSEHOLD_ID, FS_HOUSEHOLD_ID, SOURCE_HOUSE_NBR - these
    // FIELD elements are direct children of PERSON, no wrapper element in between. Returns ''
    // when the field is genuinely absent (the 1850-1870 era case - not an error, just no such
    // question on that year's questionnaire).
    function fsPersonFieldText(byId, person, fieldType) {
        if (!person || !person.subElements) return '';
        for (const ref of person.subElements) {
            const el = byId[ref.id];
            if (el && el.elementType === 'FIELD' && el.fieldType === fieldType) return fsFieldText(el);
        }
        return '';
    }

    // Two-level indirection: PERSON -> {wrapperElementType, e.g. AGE} -> FIELD -> text.
    // Confirmed live for AGE - unlike the direct fields above, AGE is its own wrapping
    // element type, not a bare FIELD child of PERSON.
    function fsWrappedFieldText(byId, person, wrapperElementType) {
        const wrapper = fsFindChild(byId, person && person.subElements, wrapperElementType);
        if (!wrapper) return '';
        const field = fsFindChild(byId, wrapper.subElements, 'FIELD');
        return field ? fsFieldText(field) : '';
    }

    // Three-level indirection: PERSON -> NAME -> NAME_GIVEN/NAME_SURNAME -> FIELD -> text.
    // A person can have more than one NAME (multiple indexed variants, confirmed live: 101
    // NAME elements for 42 PERSON elements on one 1850 image) - prefers the one marked
    // primary, same convention already used for PERSON itself in this file, falling back to
    // the first NAME found when none is marked primary.
    function fsPersonName(byId, person) {
        const names = (person && person.subElements || [])
            .map((ref) => byId[ref.id])
            .filter((el) => el && el.elementType === 'NAME');
        const nameEl = names.find((n) => n.primary) || names[0];
        if (!nameEl) return {given: '', surname: ''};
        const givenEl = fsFindChild(byId, nameEl.subElements, 'NAME_GIVEN');
        const surnameEl = fsFindChild(byId, nameEl.subElements, 'NAME_SURNAME');
        const givenField = givenEl ? fsFindChild(byId, givenEl.subElements, 'FIELD') : null;
        const surnameField = surnameEl ? fsFindChild(byId, surnameEl.subElements, 'FIELD') : null;
        return {
            given: givenField ? fsFieldText(givenField) : '',
            surname: surnameField ? fsFieldText(surnameField) : '',
        };
    }

    // PERSON -> EVENT(eventType=BIRTH) -> PLACE -> FIELD -> text. Confirmed live: the CENSUS
    // event's PLACE is residence, not birthplace - only the BIRTH-type event's PLACE is
    // birthplace, and it's absent entirely when FamilySearch's indexing didn't derive one.
    function fsPersonBirthPlace(byId, person) {
        const events = (person && person.subElements || [])
            .map((ref) => byId[ref.id])
            .filter((el) => el && el.elementType === 'EVENT');
        const birthEvent = events.find((e) => e.eventType === 'BIRTH');
        if (!birthEvent) return '';
        const placeEl = fsFindChild(byId, birthEvent.subElements, 'PLACE');
        if (!placeEl) return '';
        const field = fsFindChild(byId, placeEl.subElements, 'FIELD');
        return field ? fsFieldText(field) : '';
    }

    // RECORD.subElements directly lists the household's PERSON arks - confirmed live, no
    // separate id-matching needed the way the old UI-scraper had to reconstruct household
    // membership from DOM position.
    function fsHouseholds(apiResponse, byId) {
        return (apiResponse.elements || [])
            .filter((e) => e.elementType === 'RECORD')
            .map((record) => ({
                recordId: record.id,
                personIds: (record.subElements || [])
                    .map((ref) => ref.id)
                    .filter((id) => byId[id] && byId[id].elementType === 'PERSON'),
            }));
    }

    // Reduces one orchestration-API PERSON down to the canonical field map shared with the
    // Image-Index parser (fsCanonicalFieldsFromImageIndexPerson) - fsColumnsFromCanonicalFields
    // below builds the final `columns` object from either source's canonical map the same way.
    function fsCanonicalFieldsFromApiPerson(byId, person) {
        const {given, surname} = fsPersonName(byId, person);
        const sex = fsPersonFieldText(byId, person, 'SEX_CODE');
        return {
            givenName: given,
            surname: surname,
            sex: sex ? sex.toUpperCase() : '',
            age: fsWrappedFieldText(byId, person, 'AGE'),
            birthplace: fsPersonBirthPlace(byId, person),
            householdIdSource: fsPersonFieldText(byId, person, 'SOURCE_HOUSEHOLD_ID'),
            householdIdFs: fsPersonFieldText(byId, person, 'FS_HOUSEHOLD_ID'),
            relationshipToHead: fsPersonFieldText(byId, person, 'RELATIONSHIP_TO_HEAD'),
            maritalStatus: fsPersonFieldText(byId, person, 'MARITAL_STATUS'),
            occupation: fsPersonFieldText(byId, person, 'OCCUPATION'),
            race: fsPersonFieldText(byId, person, 'RACE_OR_COLOR'),
            fatherBirthplace: fsPersonFieldText(byId, person, 'FTHR_BIR_PLACE'),
            motherBirthplace: fsPersonFieldText(byId, person, 'MTHR_BIR_PLACE'),
        };
    }

    // Shared by both fsBuildRowsFromApiResponse (orchestration API) and
    // fsBuildRowsFromImageIndexResponse (filmdatainfo/image-data) - both sources reduce a
    // person down to the same canonical field shape above this function, so the household-ID
    // precedence and era-appropriate omission logic exists exactly once. householdIdSource
    // (SOURCE_HOUSEHOLD_ID) is the sheet-printed family number, preferred over
    // householdIdFs (FS_HOUSEHOLD_ID, FamilySearch's own system-generated id) - confirmed
    // live on the orchestration API these two are exact complements on a real image (35 + 7 =
    // 42 of 42 persons), and the same two-key relationship was independently confirmed live
    // again on the Image-Index endpoint (1860 sample used FS_HOUSEHOLD_ID, 1880 used
    // SOURCE_HOUSEHOLD_ID). Falls back to a sequential per-household counter only if neither
    // exists at all.
    function fsColumnsFromCanonicalFields(canonicalFields, sequenceFallback) {
        const columns = {
            'Given Name': canonicalFields.givenName || '',
            'Surname': canonicalFields.surname || '',
            'Gender': canonicalFields.sex || '',
            'Age': canonicalFields.age || '',
            'Family Number': canonicalFields.householdIdSource
                || canonicalFields.householdIdFs
                || String(sequenceFallback),
        };
        // Omitted entirely (not set to '') when absent - matches the old UI-scraper's own
        // "don't fabricate data" convention, and is how the pre-1880 era boundary is handled:
        // no special-case branching, just field-absence. maritalStatus/occupation/race/
        // fatherBirthplace/motherBirthplace/birthplace are captured in canonicalFields but
        // deliberately not added here - see this plan's Global Constraints.
        if (canonicalFields.relationshipToHead) columns['Relationship to Head'] = canonicalFields.relationshipToHead;
        return columns;
    }

    function fsBuildRowsFromApiResponse(apiResponse) {
        const byId = buildFsElementIndex(apiResponse);
        const rows = [];
        let householdIndex = 0;
        for (const household of fsHouseholds(apiResponse, byId)) {
            householdIndex++;
            for (const personId of household.personIds) {
                const person = byId[personId];
                if (!person) continue;

                const canonicalFields = fsCanonicalFieldsFromApiPerson(byId, person);
                const columns = fsColumnsFromCanonicalFields(canonicalFields, householdIndex);
                rows.push({columns, person_ark: person.id, attached_fsftid: ''});
            }
        }
        return rows;
    }

    // filmdatainfo/image-data parsing (the "Image Index" page's own data source, reached via
    // Image Browser/township navigation - confirmed live to be a completely different
    // endpoint from the orchestration API, never firing on the same page as it). Confirmed
    // live against two real captures: records[] is one entry PER HOUSEHOLD, each holding
    // {fields[] (record/citation-level admin data), persons[]}. Each person mixes two shapes:
    // facts[] entries carry a convenience .value alongside their fuller .fields[].values[]
    // backing data; fields[] entries (relationship, household id, parents' birthplace) have
    // no .value shortcut and must be read via .values[], preferring Interpreted over Original.

    // Prefers the FIRST Interpreted value when multiple exist - confirmed live this is
    // correct, not an arbitrary choice: the head-of-household's own RelationshipToHead field
    // carries a correction trail (Original "Self", then two Interpreted entries "Head" then
    // "Self") where the first Interpreted entry is the right one.
    function fsImageIndexFieldText(fieldOrFact) {
        if (!fieldOrFact) return '';
        if (typeof fieldOrFact.value === 'string') return fieldOrFact.value;
        const values = fieldOrFact.values || [];
        const interpreted = values.find((v) => v.type === 'http://gedcomx.org/Interpreted');
        if (interpreted) return interpreted.text || '';
        const original = values.find((v) => v.type === 'http://gedcomx.org/Original');
        return original ? (original.text || '') : '';
    }

    function fsImageIndexFindByType(list, type) {
        return (list || []).find((item) => item.type === type) || null;
    }

    function fsCanonicalFieldsFromImageIndexPerson(person) {
        const facts = (person && person.facts) || [];
        const fields = (person && person.fields) || [];

        const nameForm = person && person.names && person.names[0] && person.names[0].nameForms && person.names[0].nameForms[0];
        const parts = (nameForm && nameForm.parts) || [];
        const surnamePart = fsImageIndexFindByType(parts, 'http://gedcomx.org/Surname');
        const givenPart = fsImageIndexFindByType(parts, 'http://gedcomx.org/Given');

        const genderType = person && person.gender && person.gender.type;
        const sex = genderType === 'http://gedcomx.org/Male' ? 'M'
            : genderType === 'http://gedcomx.org/Female' ? 'F' : '';

        const birthFact = fsImageIndexFindByType(facts, 'http://gedcomx.org/Birth');
        const birthPlaceField = birthFact && birthFact.place
            ? fsImageIndexFindByType(birthFact.place.fields, 'http://gedcomx.org/Place') : null;

        return {
            givenName: givenPart ? (givenPart.value || '') : '',
            surname: surnamePart ? (surnamePart.value || '') : '',
            sex,
            age: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://gedcomx.org/Age')),
            birthplace: fsImageIndexFieldText(birthPlaceField),
            // SourceHouseholdId and HouseholdId are confirmed distinct type URIs backing
            // SOURCE_HOUSEHOLD_ID and FS_HOUSEHOLD_ID respectively - same precedence
            // relationship as the orchestration API (see fsColumnsFromCanonicalFields).
            householdIdSource: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/SourceHouseholdId')),
            householdIdFs: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/HouseholdId')),
            relationshipToHead: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://gedcomx.org/RelationshipToHead')),
            maritalStatus: fsImageIndexFieldText(fsImageIndexFindByType(facts, 'http://gedcomx.org/MaritalStatus')),
            occupation: fsImageIndexFieldText(fsImageIndexFindByType(facts, 'http://gedcomx.org/Occupation')),
            race: fsImageIndexFieldText(fsImageIndexFindByType(facts, 'http://gedcomx.org/Race')),
            fatherBirthplace: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/FatherBirthPlace')),
            motherBirthplace: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/MotherBirthPlace')),
        };
    }

    function fsBuildRowsFromImageIndexResponse(apiResponse) {
        const rows = [];
        const records = (apiResponse && apiResponse.records) || [];
        records.forEach((record, recordIndex) => {
            (record.persons || []).forEach((person) => {
                const canonicalFields = fsCanonicalFieldsFromImageIndexPerson(person);
                const columns = fsColumnsFromCanonicalFields(canonicalFields, recordIndex + 1);

                // identifiers[...][0] is a full URL (.../ark:/61903/1:1:XXXX-XXX) - extract
                // just the "1:1:XXXX-XXX" segment to match the orchestration-API path's own
                // person_ark convention (a bare ark, not a full URL).
                const identifierUrl = (person.identifiers
                    && person.identifiers['http://gedcomx.org/Persistent']
                    && person.identifiers['http://gedcomx.org/Persistent'][0]) || '';
                const arkMatch = identifierUrl.match(/(1:1:[A-Z0-9-]+)/);

                // Tree-attachment link shape not yet confirmed against a real tree-attached
                // person (see this plan's Task 2 notes) - left empty rather than guessed,
                // same "don't fabricate" convention as everywhere else in this file.
                rows.push({columns, person_ark: arkMatch ? arkMatch[1] : '', attached_fsftid: ''});
            });
        });
        return rows;
    }

    // Prefers Township (the more common modern label) but falls back to MinorCivilDivision -
    // confirmed live these are the same third-level-locality concept under two different type
    // URIs depending on era/collection (1880 sample used Township, 1860 sample used
    // MinorCivilDivision for an identically-shaped place). Matches FS.py's own
    // parse_census_browse_path(), which reads browse-path segments positionally, not by an
    // explicit state/county/township prefix - so segment ORDER here (state, county, township,
    // then "ED n" appended last) must stay exactly this order.
    function fsImageIndexBrowsePathSegments(censusFact) {
        const placeFields = (censusFact && censusFact.place && censusFact.place.fields) || [];
        const state = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/State'));
        const county = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/County'));
        const township = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/Township'))
            || fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/MinorCivilDivision'));
        const district = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/District'));
        const segments = [state, county, township].filter(Boolean);
        if (district) segments.push(district);
        return segments;
    }

    // Builds the same prose citation_text string FS.py's parse_citation()/
    // parse_nara_citing_clause() already regex-parse (Voyageur/FS.py CITATION_RE/
    // NARA_CITING_RE) - entirely from JSON fields, so the Image-Index extraction path never
    // depends on scrapeCitationAndCatalog()'s UI read. imageNumber/imageTotal come from the
    // caller (the one remaining UI fallback in this whole plan - no JSON source for the total
    // image count was found in this endpoint's response).
    function fsBuildCitationTextFromImageIndexResponse(apiResponse, {imageNumber, imageTotal} = {}) {
        const record = ((apiResponse && apiResponse.records) || [])[0];
        if (!record) return '';
        const headPerson = (record.persons || [])[0];
        const recordFields = record.fields || [];
        const personFields = headPerson ? (headPerson.fields || []) : [];

        const collectionName = ((apiResponse.collections || [])[0]
            && apiResponse.collections[0].collections
            && apiResponse.collections[0].collections[0]
            && apiResponse.collections[0].collections[0].title) || '';
        const url = apiResponse.imageURL || '';
        const date = new Date().toLocaleDateString('en-US', {day: 'numeric', month: 'long', year: 'numeric'});

        const censusFact = headPerson ? fsImageIndexFindByType(headPerson.facts || [], 'http://gedcomx.org/Census') : null;
        const browsePath = fsImageIndexBrowsePathSegments(censusFact);
        if (imageNumber && imageTotal) browsePath.push(`image ${imageNumber} of ${imageTotal}`);

        const publication = fsImageIndexFieldText(fsImageIndexFindByType(recordFields, 'http://familysearch.org/types/fields/FilmNbr'))
            || fsImageIndexFieldText(fsImageIndexFindByType(recordFields, 'http://familysearch.org/types/fields/DigitalFilmNbr'));
        const rawRepoName = fsImageIndexFieldText(fsImageIndexFindByType(personFields, 'http://familysearch.org/types/fields/ExtRepositoryName'));
        // Confirmed live: the real value carries a trailing "(NARA)" that would otherwise
        // break NARA_CITING_RE's repo_name group ([^,()]+ - excludes parentheses).
        const repoName = rawRepoName.replace(/\s*\([^)]*\)\s*$/, '').trim();
        // NARA repository location - no matching JSON field found in either captured sample
        // (see design spec's "Not yet verified" list). Hardcoded: every US census NARA
        // microfilm citation this project has observed cites this same physical archive
        // location regardless of the specific record.
        const repoLoc = 'Washington D.C.';

        let text = `"${collectionName}," database with images, FamilySearch (${url} : ${date}), ${browsePath.join(' > ')}`;
        if (publication && repoName) {
            text += `; citing NARA microfilm publication ${publication} (${repoLoc}: ${repoName}, n.d.).`;
        } else {
            text += '.';
        }
        return text;
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
        let firstPagePlace = null;
        let indexReloadAttempts = 0;
        const MAX_INDEX_RELOAD_ATTEMPTS = 3;

        // A location.reload() triggered by the index-not-loaded retry (see
        // runExtractionLoop) re-runs this whole script from scratch. Restore whatever was
        // saved right before that reload so the batch resumes instead of startBatch()
        // silently wiping every page gathered so far.
        let resumingFromReload = false;
        const resumedState = loadReloadState();
        if (resumedState) {
            accumulatedPages = resumedState.accumulatedPages;
            batchPageCounter = resumedState.batchPageCounter;
            seenPids = resumedState.seenPids;
            firstPagePlace = resumedState.firstPagePlace;
            indexReloadAttempts = resumedState.indexReloadAttempts;
            resumingFromReload = true;
            clearReloadState();
        }

        const shouldAutoStart = window.location.href.includes('mgs_auto=1');
        const runId = new URLSearchParams(window.location.search).get('mgs_run') || 'norun';

        function debugLog(msg) {
            if (DEBUG_MODE) {
                console.log(`[MGS DEBUG] ${msg}`);
            }
        }

        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__mgs_intercepted) {
            unsafeWindow.__mgs_intercepted = true;
            unsafeWindow.__mgs_pids = [];
            // State for the index-panel-data interceptor below - separate from __mgs_pids
            // since this captures the FULL per-person field response, not just a PID list.
            unsafeWindow.__voyageurAncestryIndexPanelResponses = {};
            // Per-"dbId:imageId" resolver callbacks for waitForAncestryIndexPanelResponse()
            // below - same waiter-map pattern as FS's __voyageurFsApiWaiters elsewhere in
            // this file. Storing a response sets a plain object property, not a DOM node -
            // waitForCondition()'s MutationObserver would never see it, so waiters are
            // notified directly here instead.
            unsafeWindow.__voyageurAncestryIndexPanelWaiters = {};

            const ANCESTRY_INDEX_PANEL_TARGET = '/imageviewer/api/record/index-panel-data';

            function ancestryIndexPanelKeyFromUrl(url) {
                const dbMatch = url.match(/[?&]dbId=([^&]+)/);
                const imgMatch = url.match(/[?&]imageId=([^&]+)/);
                if (!dbMatch || !imgMatch) return null;
                return `${decodeURIComponent(dbMatch[1])}:${decodeURIComponent(imgMatch[1])}`;
            }

            function storeAncestryIndexPanelResponse(url, bodyText) {
                const key = ancestryIndexPanelKeyFromUrl(url);
                if (!key) return;
                try {
                    const parsed = JSON.parse(bodyText);
                    unsafeWindow.__voyageurAncestryIndexPanelResponses[key] = parsed;
                    const waiter = unsafeWindow.__voyageurAncestryIndexPanelWaiters[key];
                    if (waiter) waiter(parsed);
                } catch (e) {
                    // Leave unset - waitForAncestryIndexPanelResponse() below times out the
                    // same as "never arrived", the correct behavior for an unparseable body.
                }
            }

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
                const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
                const response = await origFetch.apply(this, args);
                try {
                    const clone = response.clone();
                    clone.text().then(text => {
                        extractPidsFromText(text);
                        if (url.includes(ANCESTRY_INDEX_PANEL_TARGET)) {
                            storeAncestryIndexPanelResponse(url, text);
                        }
                    }).catch(() => {
                    });
                } catch (e) {
                }
                return response;
            };

            const origOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.addEventListener('load', function () {
                    extractPidsFromText(this.responseText);
                    if (url && url.includes(ANCESTRY_INDEX_PANEL_TARGET)) {
                        storeAncestryIndexPanelResponse(url, this.responseText);
                    }
                });
                origOpen.apply(this, arguments);
            };
        }

        // Instant resolution if the response already arrived before this was called (the
        // API call fires on page load, same as the DOM table's own data source - by the
        // time extractCurrentPageData's caller has already confirmed the DOM table
        // populated, this response has almost always already arrived too). Falls back to a
        // bounded timer only when the API genuinely never fires for this collection/page.
        async function waitForAncestryIndexPanelResponse(dbId, imageId, {timeoutMs = 8000} = {}) {
            const key = `${dbId}:${imageId}`;
            const startedAt = performance.now();
            const existing = (unsafeWindow.__voyageurAncestryIndexPanelResponses || {})[key];
            if (existing) {
                return {result: existing, elapsedMs: 0, timedOut: false};
            }
            return new Promise((resolve) => {
                let settled = false;
                const timer = setTimeout(() => {
                    if (settled) return;
                    settled = true;
                    delete unsafeWindow.__voyageurAncestryIndexPanelWaiters[key];
                    resolve({result: null, elapsedMs: Math.round(performance.now() - startedAt), timedOut: true});
                }, timeoutMs);
                unsafeWindow.__voyageurAncestryIndexPanelWaiters[key] = (result) => {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    delete unsafeWindow.__voyageurAncestryIndexPanelWaiters[key];
                    resolve({result, elapsedMs: Math.round(performance.now() - startedAt), timedOut: false});
                };
            });
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

            // Try the index-panel-data API first (Task 1/2) - if it already fired for this
            // exact image (the common case: it's the same page load that populated the DOM
            // table extractCurrentPageData's caller already confirmed), this resolves
            // instantly. Only pays the bounded timeout when the API genuinely never fires
            // for this collection/page, in which case the DOM-table loop below (completely
            // unmodified) is the fallback. dbid/imageId were both already computed above in
            // this same function.
            const dbIdForApi = (dbid && dbid !== "0") ? dbid : null;
            let apiSourcedPeople = null;
            if (dbIdForApi && imageId) {
                const apiWait = await waitForAncestryIndexPanelResponse(dbIdForApi, imageId, {timeoutMs: 8000});
                if (!apiWait.timedOut && apiWait.result && Array.isArray(apiWait.result.records) && apiWait.result.records.length > 0) {
                    apiSourcedPeople = ancestryRowsFromIndexPanelResponse(apiWait.result).filter((p) => {
                        if (p.pid && seenPids.has(p.pid)) return false;
                        if (p.pid) seenPids.add(p.pid);
                        return true;
                    });
                    debugLog(`Ancestry index-panel-data API: ${apiSourcedPeople.length} people (of ${apiWait.result.records.length} total, ${apiWait.elapsedMs}ms) - using API data, skipping DOM table scrape for this page.`);
                } else {
                    debugLog(`Ancestry index-panel-data API ${apiWait.timedOut ? 'timed out' : 'returned no records'} after ${apiWait.elapsedMs}ms - falling back to DOM table scrape.`);
                }
            }

            if (apiSourcedPeople) {
                pageEntry.people.push(...apiSourcedPeople);
            } else {
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
            }

            const thisPlace = {
                state: pageEntry.state, county: pageEntry.county,
                city: pageEntry.city, enumeration_district: pageEntry.enumeration_district,
            };
            if (firstPagePlace === null) {
                firstPagePlace = thisPlace;
            } else if (!placesMatch(thisPlace, firstPagePlace)) {
                // Crossed into a new town/ED - this page belongs to the next town, not the
                // one this gather is for. Discard it entirely (the caller also skips this
                // page's image download) and signal the loop to stop here.
                return {placeBoundaryCrossed: true};
            }

            accumulatedPages.push(pageEntry);
            return {placeBoundaryCrossed: false};
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
                            triggerBlobDownload(response.response, imgFileName, `A_${runId}/Images`);
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
            triggerBlobDownload(new Blob([jsonString], {type: 'application/json;charset=utf-8;'}), jsonFileName, `A_${runId}`);
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

                // Ancestry sometimes fails to render the index on a genuinely indexed page
                // while the script is running (confirmed live) - indistinguishable from a
                // truly blank page by the toggleBtn check above. A reload recovers the
                // former; a real blank page still shows unindexed after reloading too, so
                // this can't tell the two apart on a single attempt - it can only bound how
                // many times it's willing to guess "transient" before accepting "blank".
                if (isUnindexed && indexReloadAttempts < MAX_INDEX_RELOAD_ATTEMPTS) {
                    indexReloadAttempts++;
                    if (window.showToast) {
                        window.showToast(`No index detected - reloading (attempt ${indexReloadAttempts}/${MAX_INDEX_RELOAD_ATTEMPTS})...`, 'error', 2000);
                    }
                    saveReloadState({accumulatedPages, batchPageCounter, seenPids, firstPagePlace, indexReloadAttempts});
                    location.reload();
                    return;
                }
                // Either the index loaded, or every reload attempt still came back
                // unindexed - the retry ceiling has been reached, so this page is now
                // treated as genuinely blank. Reset for whichever page comes next.
                indexReloadAttempts = 0;

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
                        const extractResult = await extractCurrentPageData(rows);
                        if (extractResult && extractResult.placeBoundaryCrossed) {
                            // This page belongs to the next town, not the one this gather
                            // started on - it's already been excluded from accumulatedPages
                            // by extractCurrentPageData. Don't download its image either,
                            // and stop here rather than advancing past it.
                            debugLog(`Place boundary crossed at page ${batchPageCounter}. Stopping and discarding this page.`);
                            if (window.showToast) window.showToast("New town detected - stopping batch.", "error", 3000);
                            stopBatch();
                            break;
                        }
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
            if (!resumingFromReload) {
                accumulatedPages = [];
                seenPids.clear();
                batchPageCounter = 1;
                firstPagePlace = null;
                indexReloadAttempts = 0;
                lastPageSignature = "INITIAL_STATE_NOT_SET";
            }
            resumingFromReload = false;

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

        function stopBatch() {
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
        const runId = new URLSearchParams(window.location.search).get('mgs_run') || 'norun';

        // A genuine FamilySearch page navigation from clicking "Next Image" (see
        // goToNextImage/FS_RELOAD_STATE_KEY's own note) re-runs this whole script from
        // scratch - restore whatever was saved right before so the batch resumes instead of
        // silently discarding every item gathered so far. Same convention as
        // runAncestryGather's own resumedState handling. isResumingFsState is read by
        // startBatch() below to skip its own unconditional reset, the same way
        // runAncestryGather's resumingFromReload guards startBatch() there.
        let isResumingFsState = false;
        const resumedFsState = loadFsReloadState(runId);
        if (resumedFsState) {
            accumulatedItems = resumedFsState.accumulatedItems;
            seenItemIds = resumedFsState.seenItemIds;
            itemsAtLastCheckpoint = resumedFsState.itemsAtLastCheckpoint;
            isResumingFsState = true;
            clearFsReloadState();
        }

        function debugLog(msg) {
            if (DEBUG_MODE) console.log(`[Voyageur FS] ${msg}`);
        }

        // Confirmed live: FamilySearch's own client requests this endpoint automatically on
        // every image's page load, no UI interaction required - installed here, as early as
        // possible inside this function (before any async work), mirroring
        // runAncestryGather's own __mgs_intercepted pattern (same fetch/XHR patch technique,
        // different target URL/response shape). __voyageurFsApiResponses is keyed by ark so
        // multiple in-flight requests (if FamilySearch ever prefetches adjacent images) don't
        // collide with each other.
        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__voyageurFsApiIntercepted) {
            unsafeWindow.__voyageurFsApiIntercepted = true;
            unsafeWindow.__voyageurFsApiResponses = {};
            // Per-ark resolver callbacks for waitForFsApiResponse() below. Storing a response
            // sets a plain object property, not a DOM node - waitForCondition()'s
            // MutationObserver would never see it, so waiters are notified directly here
            // instead of relying on that helper's DOM-mutation-driven re-checks.
            unsafeWindow.__voyageurFsApiWaiters = {};

            const FS_API_TARGET = '/service/records/volunteer/orchestration/sls/image/';

            function fsApiArkFromUrl(url) {
                const match = url.match(/\/image\/([^/?#]+)/);
                return match ? decodeURIComponent(match[1]) : null;
            }

            function storeFsApiResponse(url, bodyText) {
                const ark = fsApiArkFromUrl(url);
                if (!ark) return;
                try {
                    const parsed = JSON.parse(bodyText);
                    unsafeWindow.__voyageurFsApiResponses[ark] = parsed;
                    const waiter = unsafeWindow.__voyageurFsApiWaiters[ark];
                    if (waiter) waiter(parsed);
                } catch (e) {
                    // Leave unset - waitForFsApiResponse() below times out the same as "never
                    // arrived", which is the correct behavior for an unparseable response.
                }
            }

            const origFsXhrOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.__voyageurFsApiUrl = url;
                this.addEventListener('load', function () {
                    if (this.__voyageurFsApiUrl && this.__voyageurFsApiUrl.includes(FS_API_TARGET)) {
                        storeFsApiResponse(this.__voyageurFsApiUrl, this.responseText);
                    }
                });
                return origFsXhrOpen.apply(this, arguments);
            };

            const origFsFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
                const resp = await origFsFetch.apply(this, args);
                if (url.includes(FS_API_TARGET)) {
                    resp.clone().text().then((t) => storeFsApiResponse(url, t));
                }
                return resp;
            };
        }

        // Instant resolution if the response already arrived before this was called (the API
        // call fires on page load, which can beat the gather loop reaching this image).
        // Deliberately does NOT go through waitForCondition() - that helper only re-checks its
        // condition on MutationObserver-observed DOM mutations, and storeFsApiResponse() above
        // sets a plain object property that never touches the DOM, so it would never reliably
        // trigger a re-check. Instead, storeFsApiResponse() resolves the matching waiter
        // directly by ark; this only falls back to a timer if the response never arrives.
        async function waitForFsApiResponse(ark, {timeoutMs = 15000} = {}) {
            const startedAt = performance.now();
            const existing = (unsafeWindow.__voyageurFsApiResponses || {})[ark];
            if (existing) {
                return {result: existing, elapsedMs: 0, timedOut: false};
            }
            return new Promise((resolve) => {
                let settled = false;
                const timer = setTimeout(() => {
                    if (settled) return;
                    settled = true;
                    delete unsafeWindow.__voyageurFsApiWaiters[ark];
                    resolve({result: null, elapsedMs: Math.round(performance.now() - startedAt), timedOut: true});
                }, timeoutMs);
                unsafeWindow.__voyageurFsApiWaiters[ark] = (result) => {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    delete unsafeWindow.__voyageurFsApiWaiters[ark];
                    resolve({result, elapsedMs: Math.round(performance.now() - startedAt), timedOut: false});
                };
            });
        }

        // Same technique as the orchestration-API interceptor just above, targeting
        // filmdatainfo/image-data instead - confirmed live this endpoint's request URL is
        // identical for every image ("/search/filmdatainfo/image-data", no per-image query
        // param), so responses can't be keyed by URL the way the orchestration API's can.
        // Keyed by the response BODY's own arkId field instead.
        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__voyageurFsImageIndexIntercepted) {
            unsafeWindow.__voyageurFsImageIndexIntercepted = true;
            unsafeWindow.__voyageurFsImageIndexResponses = {};
            unsafeWindow.__voyageurFsImageIndexWaiters = {};

            const FS_IMAGE_INDEX_TARGET = '/search/filmdatainfo/image-data';

            function storeFsImageIndexResponse(bodyText) {
                let parsed;
                try {
                    parsed = JSON.parse(bodyText);
                } catch (e) {
                    // Leave unset - waitForFsImageIndexResponse() below times out the same as
                    // "never arrived", the correct behavior for an unparseable response.
                    return;
                }
                const ark = parsed && parsed.arkId;
                if (!ark) return;
                unsafeWindow.__voyageurFsImageIndexResponses[ark] = parsed;
                const waiter = unsafeWindow.__voyageurFsImageIndexWaiters[ark];
                if (waiter) waiter(parsed);
            }

            const origImageIndexXhrOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.__voyageurFsImageIndexUrl = url;
                this.addEventListener('load', function () {
                    if (this.__voyageurFsImageIndexUrl && this.__voyageurFsImageIndexUrl.includes(FS_IMAGE_INDEX_TARGET)) {
                        storeFsImageIndexResponse(this.responseText);
                    }
                });
                return origImageIndexXhrOpen.apply(this, arguments);
            };

            const origImageIndexFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
                const resp = await origImageIndexFetch.apply(this, args);
                if (url.includes(FS_IMAGE_INDEX_TARGET)) {
                    resp.clone().text().then((t) => storeFsImageIndexResponse(t));
                }
                return resp;
            };
        }

        // Same event-driven-with-timeout-fallback shape as waitForFsApiResponse above.
        async function waitForFsImageIndexResponse(ark, {timeoutMs = 15000} = {}) {
            const startedAt = performance.now();
            const existing = (unsafeWindow.__voyageurFsImageIndexResponses || {})[ark];
            if (existing) {
                return {result: existing, elapsedMs: 0, timedOut: false};
            }
            return new Promise((resolve) => {
                let settled = false;
                const timer = setTimeout(() => {
                    if (settled) return;
                    settled = true;
                    delete unsafeWindow.__voyageurFsImageIndexWaiters[ark];
                    resolve({result: null, elapsedMs: Math.round(performance.now() - startedAt), timedOut: true});
                }, timeoutMs);
                unsafeWindow.__voyageurFsImageIndexWaiters[ark] = (result) => {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    delete unsafeWindow.__voyageurFsImageIndexWaiters[ark];
                    resolve({result, elapsedMs: Math.round(performance.now() - startedAt), timedOut: false});
                };
            });
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

        // Runs once per image, before either data source is awaited. Names/Image Index tab
        // presence is the ground truth of which page actually rendered - confirmed live this
        // is a navigation-method split (Search -> Names panel, Image Browser -> Image Index),
        // not something inferable from the URL. Event-driven via the existing
        // waitForCondition convention, same as clickTab() above.
        async function detectFsPageType({timeoutMs = 15000} = {}) {
            const wait = await waitForCondition(() => {
                if (findByExactText('[role="tab"], button, a', 'Names')) return 'names';
                if (findByExactText('[role="tab"], button, a', 'Image Index')) return 'image-index';
                return null;
            }, {timeoutMs});
            return wait.result;
        }

        async function scrapeCurrentImage() {
            const itemId = getItemId();
            if (!itemId || seenItemIds.has(itemId)) return;

            const pageType = await detectFsPageType();
            let rows = [];
            let citationText = '';
            let catalogItems = [];

            if (pageType === 'image-index') {
                const apiWait = await waitForFsImageIndexResponse(itemId);
                if (apiWait.result) {
                    rows = fsBuildRowsFromImageIndexResponse(apiWait.result);
                    // The one UI read left in this whole plan: no JSON source for the total
                    // image count was found on this endpoint (see the design spec's "Not yet
                    // verified" list) - the page already renders it plainly ("Image 1 of 3").
                    const imageMatch = document.body.innerText.match(/Image\s+(\d+)\s+of\s+(\d+)/i);
                    citationText = fsBuildCitationTextFromImageIndexResponse(apiWait.result, {
                        imageNumber: imageMatch ? imageMatch[1] : undefined,
                        imageTotal: imageMatch ? imageMatch[2] : undefined,
                    });
                } else {
                    debugLog(`No Image-Index response arrived for item ${itemId} after `
                        + `${apiWait.elapsedMs}ms - continuing with no household data for this image.`);
                    if (window.fsShowToast) {
                        window.fsShowToast('No index data received for this image - skipping.', 'error', 4000);
                    }
                }
                // Still used for catalogItems (the Film/Digital Note table) - its own
                // citationText is discarded in favor of the JSON-built one above; both page
                // types share the same "Information" tab UI shell this function reads.
                const catalog = await scrapeCitationAndCatalog();
                catalogItems = catalog.catalogItems;
            } else if (pageType === 'names') {
                const apiWait = await waitForFsApiResponse(itemId);
                if (apiWait.result) {
                    rows = fsBuildRowsFromApiResponse(apiWait.result);
                } else {
                    debugLog(`No orchestration-API response arrived for item ${itemId} after `
                        + `${apiWait.elapsedMs}ms - continuing with no household data for this image.`);
                    if (window.fsShowToast) {
                        window.fsShowToast('No index data received for this image - skipping.', 'error', 4000);
                    }
                }
                const citation = await scrapeCitationAndCatalog();
                citationText = citation.citationText;
                catalogItems = citation.catalogItems;
            } else {
                debugLog(`Neither Names nor Image Index tab found for item ${itemId} - `
                    + 'unrecognized page shape, continuing with no data.');
                if (window.fsShowToast) {
                    window.fsShowToast('Unrecognized page - skipping.', 'error', 4000);
                }
            }

            // Awaited before moving on to the next image, same convention as Ancestry's
            // own per-page image download.
            await downloadFsImage(itemId);

            seenItemIds.add(itemId);
            accumulatedItems.push({item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows});

            debugLog(`Scraped item ${itemId}: ${rows.length} index rows.`);
        }

        // FamilySearch's account-level "explore" record view (reached, confirmed live, via
        // some FamilySearch navigation paths) drops the dedicated Next Image button entirely
        // - without this fallback, the batch silently stopped after exactly one image
        // whenever that view was reached.
        //
        // The "Enter Image number" input looked like an equivalent second control but is
        // NOT real navigation - confirmed live, extensively: typing a new value and
        // submitting it (even via a genuine trusted OS-level keypress, not just a synthetic
        // dispatch()) updates the displayed number cosmetically while
        // window.location.pathname never changes. scrapeCurrentImage() would then silently
        // skip every subsequent image forever, since getItemId() parses the ark from that
        // same unchanged pathname and seenItemIds already has it.
        //
        // The filmstrip's own "Go to image N" thumbnail buttons are genuine navigation -
        // confirmed live that clicking one changes the ark (e.g. "...9YBZ-XVG" ->
        // "...9YBZ-F86" on the same record). In the classic "index" view, the
        // currently-viewed image's own neighbor is reliably already rendered in the
        // (virtualized) filmstrip. In "explore" mode specifically, the filmstrip is often
        // empty outright and this fallback can't reach it - see the KNOWN LIMITATION note
        // inside advanceViaFilmstripThumbnail() below.
        async function advanceViaFilmstripThumbnail() {
            // KNOWN LIMITATION (not fully solved): in the "explore" view specifically, this
            // filmstrip is a virtualized list that's frequently empty and never renders any
            // "Go to image N" buttons at all - confirmed live across repeated attempts. A
            // window resize event is a plausible nudge for this general class of
            // virtualized-list bug (many such lists use a ResizeObserver), but it did NOT
            // reliably fix this specific case in live testing - neither did toggling
            // FamilySearch's own "View Grid" control. Left in as a cheap, harmless attempt
            // rather than removed, since it's free and may help on some page states even
            // though it isn't a confirmed fix. When this path exhausts its wait, the batch
            // stops after the current image exactly like it did before this whole fallback
            // existed - no worse than the prior behavior, just not the full fix. See
            // GitHub issue tracking FamilySearch "explore" view multi-page continuation for
            // follow-up.
            let currentWait = await waitForCondition(() => [...document.querySelectorAll('button')]
                .find(b => /^Go to image \d+, viewed$/.test(b.getAttribute('aria-label') || '')) || null,
                {timeoutMs: 3000});
            if (!currentWait.result) {
                window.dispatchEvent(new Event('resize'));
                currentWait = await waitForCondition(() => [...document.querySelectorAll('button')]
                    .find(b => /^Go to image \d+, viewed$/.test(b.getAttribute('aria-label') || '')) || null,
                    {timeoutMs: 10000});
            }
            const currentBtn = currentWait.result;
            if (!currentBtn) {
                debugLog(`advanceViaFilmstripThumbnail: no currently-viewed thumbnail found (${currentWait.elapsedMs}ms)`);
                return {advanced: false, timedOut: false};
            }
            const current = parseInt(currentBtn.getAttribute('aria-label').match(/^Go to image (\d+)/)[1], 10);

            const nextLabel = `Go to image ${current + 1}`;
            const nextWait = await waitForCondition(() => [...document.querySelectorAll('button')]
                .find(b => b.getAttribute('aria-label') === nextLabel) || null, {timeoutMs: 10000});
            const nextThumb = nextWait.result;
            if (!nextThumb) {
                debugLog(`advanceViaFilmstripThumbnail: "${nextLabel}" thumbnail never found (${nextWait.elapsedMs}ms) `
                    + '- likely the last image');
                return {advanced: false, timedOut: false};
            }

            const prevUrl = window.location.href;
            nextThumb.click();
            const navWait = await waitForCondition(() => window.location.href !== prevUrl, {timeoutMs: 10000});
            return {advanced: !navWait.timedOut, timedOut: navWait.timedOut};
        }

        // FamilySearch's own "Next Image" button (aria-label exactly "Next Image", matching
        // nextBtnSelector below all along) genuinely exists in BOTH the classic "index" view
        // and the "explore" view - it was never missing. It simply never mounts into the DOM
        // until the mouse hovers over the image viewer, confirmed live via screen-share: a
        // real hover made it visible where every automated DOM query had found nothing.
        // Dispatching synthetic mouse hover events on the viewer's own wrapper element
        // reliably mounts it without an actual OS-level mouse move - confirmed live
        // (before: false, after: true on the same page, same session).
        function triggerNextButtonHoverMount() {
            const wrapper = document.querySelector('[class*="wrapperCss"]') || document.body;
            ['mouseover', 'mouseenter', 'mousemove'].forEach(type => {
                wrapper.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, clientX: 900, clientY: 300}));
            });
        }

        async function goToNextImage() {
            triggerNextButtonHoverMount();

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
                // waits (waitForFsApiResponse/scrapeCitationAndCatalog) already handle "has
                // the new page's content rendered yet" on their own terms.
                const navWait = await waitForCondition(() => window.location.href !== prevUrl,
                    {timeoutMs: 10000});
                return {advanced: !navWait.timedOut, timedOut: navWait.timedOut};
            }
            return advanceViaFilmstripThumbnail();
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

                // Saved before every advance attempt - see FS_RELOAD_STATE_KEY's own note:
                // clicking "Next Image" is a real page navigation on FamilySearch, so this
                // script re-runs from scratch on every single image regardless of whether
                // goToNextImage() itself ever called location.reload(). Without this,
                // accumulatedItems reset to empty on the next injection and only the LAST
                // scraped item ever reached the final JSON - confirmed live.
                saveFsReloadState(runId, {accumulatedItems, seenItemIds, itemsAtLastCheckpoint});

                const {advanced, timedOut} = await goToNextImage();
                if (!advanced) {
                    if (timedOut && window.fsShowToast) window.fsShowToast('Navigation timed out. Stopping.', 'error');
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
            link.setAttribute('download', `TMP_FS_${runId}_${jsonFileName}`);
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
                        link.setAttribute('download', `TMP_FS_${runId}_Images_${event.data.fileName}`);
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
            // Skipped when resuming (see isResumingFsState above) - the whole point of
            // restoring saved state is to carry accumulatedItems across this exact reset,
            // the same way runAncestryGather's resumingFromReload guards its own startBatch.
            if (!isResumingFsState) {
                accumulatedItems = [];
                seenItemIds.clear();
                itemsAtLastCheckpoint = 0;
            }
            isResumingFsState = false;
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
            clearFsReloadState();
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

    // Test-only: exposes pure, DOM-free helpers for the Node test harness (see
    // tests/js/harness.js). `module` is undefined under Tampermonkey, so this never runs
    // there - the guard is load-bearing, not defensive boilerplate.
// Ancestry's imageviewer/api/record/index-panel-data endpoint uses a stable, self-
// describing fieldName vocabulary that does NOT change across census years (only which
// fields are present varies) - confirmed live against real 1850, 1860, 1880, and 1920
// Ancestry census data (Pembina, ND / Minnesota Territory / Dakota Territory), see
// docs/superpowers/specs/2026-08-15-ancestry-index-panel-extraction-design.md for the
// full real field tables this was built from. Maps each known fieldName to the SAME
// column header text the existing DOM-table scraper already produces (e.g. "Given
// Name", "Surname") so field_maps/ancestry_census.yaml needs no changes for any field
// already listed here - this is a drop-in second producer of the exact same `columns`
// shape, not a new schema.
const ANCESTRY_INDEX_FIELD_TO_COLUMN = {
    LineNumber: 'Line Number',
    SourceDwellingNumber: 'Dwelling Number',
    HouseNumber: 'Dwelling Number', // 1920's fieldName for the same concept as SourceDwellingNumber - confirmed the two never co-occur on the same collection/year
    Famnum: 'Family Number',
    SelfGivenName: 'Given Name',
    SelfSurname: 'Surname',
    SelfResidenceAge: 'Age',
    SelfBirthYear: 'Birth Year',
    SelfBirthMonth: 'Birth Month',
    SelfGender: 'Gender',
    SelfRace: 'Race',
    SelfResidenceOccupation: 'Occupation',
    SelfResidenceIndustry: 'Industry',
    SelfResidenceRealEstateValue: 'Real Estate Value',
    SelfResidencePersonalEstateValue: 'Personal Estate Value',
    SelfBirthPlace: 'Birth Place',
    SelfResidenceMarriedWithinYear: 'Married within Year',
    SelfResidenceAttendedSchool: 'Attended School',
    SelfResidenceCannotRead: 'Cannot Read, Write',
    SelfResidenceCannotWrite: 'Cannot Read, Write',
    SelfResidenceCanRead: 'Cannot Read, Write',
    SelfResidenceCanWrite: 'Cannot Read, Write',
    SelfResidenceDisabilityCondition: 'Disability Condition',
    SelfResidenceIsMaimed: 'Disability Condition',
    SelfResidenceIsSick: 'Disability Condition',
    SelfResidenceIsBlind: 'Disability Condition',
    SelfResidenceIsDeafDumb: 'Deaf Dumb Blind Insane',
    SelfResidenceIsInsane: 'Deaf Dumb Blind Insane',
    SelfResidenceIsIdiotic: 'Idiotic Pauper Convict',
    SelfResidenceStreetAddress: 'Street',
    SelfRelationToHead: 'Relationship to Head',
    SelfMaritalStatus: 'Marital Status',
    FatherBirthPlace: 'Father Foreign Born',
    MotherBirthPlace: 'Mother Foreign Born',
    SelfResidenceMonthsUnEmployedPastYear: 'Months Not Employed',
    SelfResidenceHomeOwnership: 'Home Ownership',
    SelfResidenceHomeMortgaged: 'Home Mortgaged',
    SelfArrivalYear: 'Immigration Year',
    SelfResidenceNaturalizationStatus: 'Naturalization Status',
    SelfNaturalizationYear: 'Year of Naturalization',
    SelfResidenceLanguageSpoken: 'Native Tongue',
    SelfResidenceAbleToSpeakEnglish: 'Speaks English',
    SelfResidenceIsEmployed: 'Employment Field',
};

// Converts one index-panel-data record (one person) into the same {columnHeader:
// value} shape the DOM-table scraper produces. Empty-string values are skipped
// entirely (never fabricate a blank column, matching how downstream unmapped-column
// detection already treats blank values as absent). When two different API fieldNames
// map to the SAME target column (e.g. 1880's SelfResidenceIsSick and
// SelfResidenceIsBlind both feed "Disability Condition"), their values are combined
// with "; " rather than the second silently overwriting the first - confirmed live
// this collision is real (1880 exposes 6 separate boolean disability flags, this
// project's existing schema only has one combined "Disability Condition" column). An
// unrecognized fieldName (a field this map hasn't been extended to cover yet) is
// passed through under its own human-readable label (from fieldLabelsByName) when
// available, or its raw fieldName otherwise - never dropped. This exact case (a new,
// not-yet-mapped fieldName) is expected to happen on census years beyond the 4
// confirmed here; downstream census_schema.py already flags any unrecognized column
// as "unmapped" for manual review - no new review-flagging logic is needed in this
// function, it just needs to not lose the data.
function ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByName) {
    const columns = {};
    (record.recordFields || []).forEach((f) => {
        const value = (f.value == null ? '' : String(f.value)).trim();
        if (!value) return;
        const target = ANCESTRY_INDEX_FIELD_TO_COLUMN[f.fieldName] || fieldLabelsByName[f.fieldName] || f.fieldName;
        columns[target] = columns[target] ? `${columns[target]}; ${value}` : value;
    });
    return columns;
}

// Converts a full index-panel-data API response into the same row-array shape
// extractCurrentPageData()'s DOM-table loop already produces for pageEntry.people:
// [{columns, pid, extracted_url, alternate_names, alternate_birth_places}], plus a new
// household_id field census_schema.py's _group_household() will prefer when present
// (see Task 4). record.pid is Ancestry's own real, stable numeric person ID -
// confirmed live this is the exact same identifier this project's DOM-scraper already
// extracts from an <a href="...records/{pid}"> link, just delivered directly instead
// of scraped. Synthesizes "Line Number" from array position (1-based) when the API
// response doesn't expose that field at all - confirmed live 1860 exposes no
// LineNumber field, matching the DOM-scraper's own existing "not every census year's
// index exposes a Line Number column" fallback for the same reason.
function ancestryRowsFromIndexPanelResponse(apiResponse) {
    const fieldLabelsByName = {};
    (apiResponse.fieldLabels || []).forEach((fl) => {
        fieldLabelsByName[fl.fieldName] = fl.labelText;
    });
    return (apiResponse.records || []).map((record, idx) => {
        const columns = ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByName);
        if (!columns['Line Number']) {
            columns['Line Number'] = String(idx + 1);
        }
        return {
            columns: columns,
            pid: record.pid != null ? String(record.pid) : '',
            household_id: record.householdId ? String(record.householdId) : '',
            extracted_url: '',
            alternate_names: [],
            alternate_birth_places: [],
        };
    });
}

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            placesMatch, saveReloadState, loadReloadState, clearReloadState,
            buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
            fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
            fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields,
            fsImageIndexFieldText, fsImageIndexFindByType,
            fsCanonicalFieldsFromImageIndexPerson, fsBuildRowsFromImageIndexResponse,
            fsImageIndexBrowsePathSegments, fsBuildCitationTextFromImageIndexResponse,
            ancestryColumnsFromIndexPanelRecord, ancestryRowsFromIndexPanelResponse,
        };
    }

})();
