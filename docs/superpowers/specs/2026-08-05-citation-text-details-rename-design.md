# Rename original_transcription/english_translation to citation_text/citation_details

## What this is

A project-wide field rename: `original_transcription` becomes `citation_text`, and
`english_translation` becomes `citation_details`. These are the two fields every
record (Parish, Scrip, Census) carries for "the text that goes in the citation" and
"a details/synopsis of that text" respectively.

This isn't inventing new names — `citation_text`/`citation_details` are RootsMagic's
own field names, and `Archivist.py` already has a partial fix in place: its citation
builder accepts `citation_text`/`citation_details` as override parameters, falling
back to `original_transcription`/`english_translation` when absent. The same
`citation_text` name is already used, unrelated, in `Voyageur.py`/`FS.py` for
FamilySearch/Ancestry's own raw bibliographic citation strings - confirmed
intentional reuse, not a naming collision, since both concepts describe the same
underlying idea (text belonging in a citation) even though they arrive through
different pipelines.

This is a pure rename. Per this session's standing rule, there is no compatibility
shim: once a location is renamed, the old name is deleted there, not kept as a
fallback. Parish's actual behavior does not change - it still produces a full,
literal English translation; it's just stored under the new field name. Scrip's
synopsis behavior is likewise unchanged.

This is deliberately scoped to the rename only. A related, separate feature -
per-`.pmt` citation headers (Parish showing "Original Transcription:"/"English
Translation:" labels, other types showing none) - is out of scope here and will be
its own spec once this rename ships.

## Non-goals

- No change to Parish's or Scrip's actual prompt behavior/content quality - only the
  field name each writes to.
- No per-document-type header feature (separate spec, follows this one).
- No change to `FactTypes.json`, `Commissioner/fact_registry.py`, or
  `Commissioner/record_registry.py` - unrelated to this rename.
- No change to `Voyageur.py`/`FS.py`'s own `citation_text` (bibliographic citation
  string) usage for census sources - that is a different field entirely and is not
  touched by this rename.

## Files touched

**Source of truth (rename here first):**
- `Paleographer/schema.json` - rename the two Record-level properties. Neither
  carries a `description` today, so this is a pure key rename with nothing else to
  update in this file.
- `Paleographer/prompts/Parish.pmt` - section "9. TRANSCRIPTION & TRANSLATION"
  currently reads "english_translation = full English translation... original_
  transcription = exact original French/Latin... Use original_transcription just in
  the citation block." Rename both field references; the surrounding instructions
  (produce a full literal translation, preserve diacritics in the original, etc.)
  are unchanged.
- `Paleographer/prompts/Scrip.pmt` - the "COMMISSIONER'S REVIEW (english_translation
  field)" section header and its prose rename to reference `citation_details`.

**Commissioner (must stay in sync - guardrail tests enforce this):**
- `Commissioner/models.py` - rename `Record.original_transcription` /
  `Record.english_translation` to `Record.citation_text` / `Record.citation_details`.
- `Commissioner/tests/test_models.py` - update `EXPECTED_FIELDS` (the schema.json
  field-name guardrail) and the full-collection round-trip test to use the new names.

**Live consumers:**
- `Paleographer/engine.py` - the source-document dict builder (~line 256-257) and
  the multi-image continuation-prompt template (~line 934-935, the "transcription so
  far" / "translation so far" lines shown back to the model).
- `Paleographer/Paleographer.py` - the same two patterns, duplicated from engine.py
  (confirmed by the existing `build_merged_schema` duplication between these files).
- `Paleographer/postprocess.py` - the `source_documents` dict builder (~line 215-227)
  used when merging multi-document Scrip claims.
- `Voyageur/census_schema.py` - the empty-string placeholders (~line 240) Census
  records set for these fields (Census doesn't transcribe/translate, so both are
  always `""`, but the keys still need to match the shared schema).
- `Voyageur/Voyageur.py` - two separate occurrences of the same empty-string
  placeholder pattern (~line 228, an Ancestry-source builder; ~line 815, a
  FamilySearch-via-Voyageur builder).
- `Voyageur/FS.py` - one occurrence of the same pattern (~line 364-365).
- `Archivist/Archivist.py` - `_build_citation_block` and `build_general_citation`:
  delete the `original_transcription`/`english_translation` parameters and their
  fallback branches entirely (lines ~2643-2644, ~2649-2651, ~2734-2743, ~2846-2847).
  Only `citation_text`/`citation_details` remain, matching the override names that
  already exist there today - this file ends up simpler than it is now, not more
  complex.

**Tests to update:**
- `Archivist/tests/test_archivist.py`
- `Archivist/tests/test_census_ingestion.py`
- `Paleographer/tests/test_paleographer_pipeline.py`
- `Paleographer/tests/test_postprocess.py`
- `Paleographer/tests/test_engine.py`
- `Paleographer/tests/test_schema.py`

## Error handling

None beyond what already exists. This introduces no new validation or failure
modes - it changes which key names carry the same data through the same code paths.
If a test currently asserts on the old key name, it needs updating to the new one;
that's the only new "failure" this change should ever produce (a stale assertion),
and the point of running the full suite throughout is to catch every one.

## Testing

No new test categories. The existing suite (253 tests as of the Commissioner merge)
gets its fixtures and assertions updated to the new field names, and must stay green
throughout - including Commissioner's two guardrail tests, which are the direct
proof that `Commissioner/models.py` didn't drift from the renamed `schema.json`.
Given the number of files involved, the implementation plan should sequence this
so the suite is run and green after each logical group of files, not just once at
the very end - a rename this wide is exactly the kind of change where a mistake in
one file (a typo, a missed occurrence) is easy to miss if verification is deferred
to the end.
