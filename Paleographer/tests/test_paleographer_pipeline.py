"""
End-to-end simulation of Paleographer.py's full pipeline: file discovery -> content-part
building -> prompt/schema assembly -> (fake) Gemini call -> post-processing -> master DB
write. No real API call is ever made - google.genai.Client is replaced with a fake that
returns a canned, schema-shaped response - but every other piece (the real Parish.pmt/
Scrip.pmt prompt files, the real FactTypes.json vocabulary, engine.py's schema merging,
postprocess.py's derivation logic, Paleographer.py's own orchestration) runs for real.

This exists because engine.py and postprocess.py already have thorough unit tests for
their own pieces in isolation, but nothing previously exercised Paleographer.py itself or
verified the pieces actually work together end-to-end for either real record type.
"""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image


class FakeCaches:
    def create(self, **_kwargs):
        return SimpleNamespace(name="fake-cache-1")

    def delete(self, **_kwargs):
        pass


class FakeModels:
    """fake_page_data is either one dict (returned for every call, the common case) or a
    list of dicts (consumed one per call, in order - for simulating a multi-file run where
    each image needs its own distinct response, e.g. page-continuation tests)."""
    def __init__(self, fake_page_data):
        self.fake_page_data = fake_page_data
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=500,
                                cached_content_token_count=0, thoughts_token_count=0)
        if isinstance(self.fake_page_data, list):
            response_data = self.fake_page_data[len(self.calls) - 1]
        else:
            response_data = self.fake_page_data
        return SimpleNamespace(
            text=json.dumps(response_data),
            usage_metadata=usage,
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))],
        )


class FakeClient:
    """Stands in for genai.Client so process_one_file_sync's real logic (retry loop,
    JSON parsing, cost tracking, context caching) runs unchanged against a canned
    response instead of a real network call."""
    last_instance = None

    def __init__(self, *args, **kwargs):
        self.caches = FakeCaches()
        self.models = FakeModels(FakeClient.pending_page_data)
        FakeClient.last_instance = self


def _import_paleographer_fresh(monkeypatch, tmp_path, env_overrides, fake_page_data, argv=None,
                               image_filenames=("TestFile_00001.jpg",)):
    program_dir = tmp_path / "program"
    image_dir_name = "Images"
    json_dir_name = "JSON"
    (program_dir / image_dir_name).mkdir(parents=True)
    (program_dir / json_dir_name).mkdir(parents=True)

    for name in image_filenames:
        Image.new("RGB", (10, 10), color="white").save(program_dir / image_dir_name / name)

    env = {
        "PROGRAM_DIR": str(program_dir),
        "IMAGE_DIR": image_dir_name,
        "JSON_DIR": json_dir_name,
        "MASTER_DB_NAME": "master.json",
        "MODEL_NAME": "gemini-test-model",
        "GEMINI_API_KEY": "fake-key-not-used",
        "API_BUDGET": "5.00",
        "COST_PER_1M_INPUT": "0.075",
        "COST_PER_1M_OUTPUT": "0.30",
        "CACHE_DISCOUNT_MULTIPLIER": "0.10",
        "VOLUME_TITLE": "Test Volume",
        "VOLUME_NUM": "1",
    }
    env.update(env_overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    # Paleographer.py's own load_dotenv(..., override=True) calls would otherwise
    # overwrite the env set above with whatever's in the real project .env files.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    # DEBUG_FILE reads sys.argv[1] at import time - pytest's own argv would otherwise be
    # misread as a debug filename and divert the whole run down the debug-mode path.
    monkeypatch.setattr(sys, "argv", argv or ["Paleographer.py"])

    FakeClient.pending_page_data = fake_page_data
    monkeypatch.setattr("google.genai.Client", FakeClient)

    sys.modules.pop("Paleographer", None)
    module = importlib.import_module("Paleographer")
    return module, program_dir / json_dir_name / "master.json"


PARISH_FAKE_RESPONSE = {
    "collection_title": "Test Baptisms",
    "sheets": [{
        "page_id": "p1",
        "document_metadata": {},
        "records": [{
            "record_id": None,
            "page": "12",
            "record_number": "45",
            "event_type": "Baptism",
            "year": "1850",
            "event_date": "December 12, 1850",
            "event_place": None,
            "english_translation": "On December 12, 1850, I baptized Jean, son of Jean Gagne and Marie Notre-Dame.",
            "original_transcription": "Le 12 decembre 1850, j'ai baptise Jean, fils de Jean Gagne et Marie Notre-Dame.",
            "review": False,
            "review_reason": None,
            "type_specific_fields": {},
            "participants": [
                {
                    "role_number": None, "role_name": "Primary",
                    "std_given": "Jean", "std_surname": "Gagné",
                    "raw_given": "Jean", "raw_surname": "Gagné",
                    "dit_name": None, "prefix": None, "suffix": None,
                    "sex": "M", "is_priest": False, "age": None,
                    "occupation": None, "race": None, "religion": None, "residence": None,
                    "birth_date": "December 10, 1850", "birth_place": None,
                    "death_date": None, "death_place": None,
                    "review": False, "review_reason": None, "type_specific_fields": {},
                },
                {
                    "role_number": None, "role_name": "Father",
                    "std_given": "Jean", "std_surname": "Gagné",
                    "raw_given": "Jean", "raw_surname": "Gagné",
                    "dit_name": None, "prefix": None, "suffix": None,
                    "sex": "M", "is_priest": False, "age": "30",
                    "occupation": "Farmer", "race": None, "religion": None, "residence": None,
                    "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
                    "review": False, "review_reason": None, "type_specific_fields": {},
                },
                {
                    "role_number": None, "role_name": "Mother",
                    "std_given": "Marie", "std_surname": "Nôtre-Dame",
                    "raw_given": "Marie", "raw_surname": "Nôtre-Dame",
                    "dit_name": None, "prefix": None, "suffix": None,
                    "sex": "F", "is_priest": False, "age": "28",
                    "occupation": None, "race": None, "religion": None, "residence": None,
                    "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
                    "review": False, "review_reason": None, "type_specific_fields": {},
                },
                {
                    "role_number": None, "role_name": "Officiant",
                    "std_given": "Alexandre", "std_surname": "Tache",
                    "raw_given": "Alexandre", "raw_surname": "Tache",
                    "dit_name": None, "prefix": None, "suffix": None,
                    "sex": "M", "is_priest": True, "age": None,
                    "occupation": None, "race": None, "religion": None, "residence": None,
                    "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
                    "review": False, "review_reason": None, "type_specific_fields": {},
                },
            ],
        }],
    }],
}


def test_parish_pipeline_end_to_end(tmp_path, monkeypatch):
    module, master_db_path = _import_paleographer_fresh(
        monkeypatch, tmp_path,
        env_overrides={
            "PALEOGRAPHER_RECORD_TYPE": "Parish.pmt",
            "PARISH_NAME": "St. Test Parish", "PARISH_CITY": "Testville", "PARISH_STATE": "TS",
            "DEFAULT_EVENT_LOCATION": "Testville, TS, USA",
        },
        fake_page_data=PARISH_FAKE_RESPONSE,
    )

    module.main()

    assert master_db_path.exists(), "main() should have written the master DB"
    saved = json.loads(master_db_path.read_text(encoding="utf-8"))

    assert saved["total_pages_processed"] == 1
    assert saved["total_spent"] > 0

    sheet = saved["sheets"][0]
    assert sheet["document_metadata"]["file_name"] == "TestFile_00001.jpg"
    assert sheet["document_metadata"]["file_type"] == "JPEG"
    assert sheet["document_metadata"]["volume"] == "1"

    record = sheet["records"][0]
    # Derived from event_type via the real FactTypes.json vocabulary (Baptism -> BAPM).
    assert record["record_id"] == "BAPM-45"
    # LLM's English-language date reading converted to ISO by postprocess.parse_to_iso.
    assert record["event_date"] == "1850-12-12"
    # Parish.pmt's record-level default (event_place was left null by the fake response).
    assert record["event_place"] == "Testville, TS, USA"

    primary, father, mother, officiant = record["participants"]
    assert primary["role_number"] == "1"
    assert father["role_number"] == "2"
    assert mother["role_number"] == "3"
    # New "Officiant" role (added so is_priest has somewhere to attach to) resolves to its
    # own role_number - proving Parish.pmt's roles table and derive_role_numbers agree.
    assert officiant["role_number"] == "9"
    assert officiant["is_priest"] is True
    assert primary["is_priest"] is False

    # Diacritics stripped from std_* fields only - raw_* must stay untouched.
    assert primary["std_surname"] == "Gagne"
    assert primary["raw_surname"] == "Gagné"
    assert mother["std_surname"] == "Notre-Dame"

    assert primary["birth_date"] == "1850-12-10"

    # Primary and Father share the same standardized name -> Jr/Sr suffix derivation.
    assert primary["suffix"] == "Jr"
    assert father["suffix"] == "Sr"

    # Parish.pmt's participant-level default, applied since the fake response left it null.
    assert primary["religion"] == "Roman Catholic"
    assert father["religion"] == "Roman Catholic"
    assert mother["religion"] == "Roman Catholic"


SCRIP_FAKE_RESPONSE = {
    "collection_title": "Test Scrip",
    "sheets": [{
        "page_id": "p1",
        "document_metadata": {},
        "records": [{
            "record_id": None,
            "page": "1",
            "record_number": "7",
            "event_type": "Residence (family)",
            "year": "1876",
            "event_date": "March 3, 1876",
            "event_place": "Manitoba",
            "english_translation": "Scrip application of Louis Riel.",
            "original_transcription": "Scrip application of Louis Riel.",
            "review": False,
            "review_reason": None,
            "type_specific_fields": {
                "scrip_number": "1234", "scrip_amount": "$160",
                "claim_basis": "Half-breed", "application_date": "March 3, 1876",
            },
            "participants": [
                {
                    "role_number": None, "role_name": "Claimant",
                    "std_given": "Louis", "std_surname": "Riel",
                    "raw_given": "Louis", "raw_surname": "Riel",
                    "dit_name": None, "prefix": None, "suffix": None,
                    "sex": "M", "is_priest": False, "age": "31",
                    "occupation": None, "race": None, "religion": None, "residence": None,
                    "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
                    "review": False, "review_reason": None,
                    "type_specific_fields": {"marital_status": "Married", "relationship_to_claimant": "Self"},
                },
            ],
        }],
    }],
}


def test_scrip_pipeline_end_to_end(tmp_path, monkeypatch):
    module, master_db_path = _import_paleographer_fresh(
        monkeypatch, tmp_path,
        env_overrides={
            "PALEOGRAPHER_RECORD_TYPE": "Scrip.pmt",
            "SCRIP_COLLECTION_NAME": "Test Scrip Collection", "SCRIP_DISTRICT": "Test District",
        },
        fake_page_data=SCRIP_FAKE_RESPONSE,
    )

    module.main()

    saved = json.loads(master_db_path.read_text(encoding="utf-8"))
    record = saved["sheets"][0]["records"][0]

    # Scrip.pmt's extra_fields (record + participant level) must survive the schema
    # merge/round-trip intact, proving build_merged_schema's injected fields actually
    # thread through Paleographer.py's real pipeline rather than only in isolation.
    assert record["type_specific_fields"]["scrip_number"] == "1234"
    assert record["type_specific_fields"]["scrip_amount"] == "$160"
    assert record["type_specific_fields"]["claim_basis"] == "Half-breed"

    claimant = record["participants"][0]
    assert claimant["role_number"] == "1"
    assert claimant["type_specific_fields"]["marital_status"] == "Married"
    assert claimant["type_specific_fields"]["relationship_to_claimant"] == "Self"


def test_debug_mode_does_not_write_master_db(tmp_path, monkeypatch):
    """DEBUG_FILE mode (the Toolbox's 'Run Analysis (API)' with a specific file picked)
    must print the extracted JSON without ever touching the master DB on disk."""
    module, master_db_path = _import_paleographer_fresh(
        monkeypatch, tmp_path,
        env_overrides={
            "PALEOGRAPHER_RECORD_TYPE": "Parish.pmt",
            "PARISH_NAME": "St. Test Parish", "PARISH_CITY": "Testville", "PARISH_STATE": "TS",
            "DEFAULT_EVENT_LOCATION": "Testville, TS, USA",
        },
        fake_page_data=PARISH_FAKE_RESPONSE,
        argv=["Paleographer.py", "TestFile_00001.jpg"],
    )

    module.main()

    assert not master_db_path.exists(), "DEBUG_FILE mode must never write the master DB"


def _minimal_record(**overrides):
    base = {
        "record_id": None, "page": "1", "record_number": "1",
        "event_type": "Baptism", "year": "1850", "event_date": "December 12, 1850", "event_place": None,
        "english_translation": "On December 12, 1850, I baptized Jean.",
        "original_transcription": "Le 12 decembre 1850, j'ai baptise Jean.",
        "review": False, "review_reason": None, "continues_on_next_image": False,
        "continues_from_previous_image": False, "type_specific_fields": {},
        "participants": [{
            "role_number": None, "role_name": "Primary", "std_given": "Jean", "std_surname": "Gagne",
            "raw_given": "Jean", "raw_surname": "Gagne", "dit_name": None, "prefix": None, "suffix": None,
            "sex": "M", "is_priest": False, "age": None, "occupation": None, "race": None, "religion": None,
            "residence": None, "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
            "review": False, "review_reason": None, "type_specific_fields": {},
        }],
    }
    base.update(overrides)
    return base


def test_page_continuation_merges_across_images_without_duplication(tmp_path, monkeypatch):
    """A record cut off at the bottom of one image and completed at the top of the next
    must end up as ONE record in the master DB, not two - see UNIVERSAL_PROMPT_SUFFIX's
    PAGE CONTINUITY rule, engine.build_continuation_context, and Paleographer.py's
    pop_trailing_cutoff_record/consumed_leading_continuation/reattach_leftover_record."""
    page_1_response = {
        "collection_title": "Test Baptisms",
        "sheets": [{"page_id": "p1", "document_metadata": {}, "records": [
            _minimal_record(record_number="44", original_transcription="Le 12 decembre, j'ai baptise",
                            continues_on_next_image=True, review=True, review_reason="Cut off at page end"),
        ]}],
    }
    page_2_response = {
        "collection_title": "Test Baptisms",
        "sheets": [{"page_id": "p2", "document_metadata": {}, "records": [
            _minimal_record(record_number="44",
                            original_transcription="Le 12 decembre, j'ai baptise Jean, fils de...",
                            continues_from_previous_image=True),
            _minimal_record(record_number="45"),
        ]}],
    }

    module, master_db_path = _import_paleographer_fresh(
        monkeypatch, tmp_path,
        env_overrides={
            "PALEOGRAPHER_RECORD_TYPE": "Parish.pmt",
            "PARISH_NAME": "St. Test Parish", "PARISH_CITY": "Testville", "PARISH_STATE": "TS",
            "DEFAULT_EVENT_LOCATION": "Testville, TS, USA",
        },
        fake_page_data=[page_1_response, page_2_response],
        image_filenames=("TestFile_00001.jpg", "TestFile_00002.jpg"),
    )

    module.main()

    saved = json.loads(master_db_path.read_text(encoding="utf-8"))
    all_records = [r for sheet in saved["sheets"] for r in sheet["records"]]

    assert len(all_records) == 2, f"expected 2 records total (one merged, one new), got {len(all_records)}"
    record_44 = next(r for r in all_records if r["record_number"] == "44")
    assert record_44["original_transcription"] == "Le 12 decembre, j'ai baptise Jean, fils de..."
    assert record_44["continues_from_previous_image"] is True


def test_page_continuation_saves_leftover_when_nothing_continues_it(tmp_path, monkeypatch):
    """If the next image's response doesn't claim to continue the pending record, it must
    still be saved (exactly as flagged as before this feature existed), not silently
    dropped."""
    page_1_response = {
        "collection_title": "Test Baptisms",
        "sheets": [{"page_id": "p1", "document_metadata": {}, "records": [
            _minimal_record(record_number="44", continues_on_next_image=True,
                            review=True, review_reason="Cut off at page end"),
        ]}],
    }
    page_2_response = {
        "collection_title": "Test Baptisms",
        "sheets": [{"page_id": "p2", "document_metadata": {}, "records": [
            _minimal_record(record_number="45"),
        ]}],
    }

    module, master_db_path = _import_paleographer_fresh(
        monkeypatch, tmp_path,
        env_overrides={
            "PALEOGRAPHER_RECORD_TYPE": "Parish.pmt",
            "PARISH_NAME": "St. Test Parish", "PARISH_CITY": "Testville", "PARISH_STATE": "TS",
            "DEFAULT_EVENT_LOCATION": "Testville, TS, USA",
        },
        fake_page_data=[page_1_response, page_2_response],
        image_filenames=("TestFile_00001.jpg", "TestFile_00002.jpg"),
    )

    module.main()

    saved = json.loads(master_db_path.read_text(encoding="utf-8"))
    record_numbers = sorted(r["record_number"] for sheet in saved["sheets"] for r in sheet["records"])
    assert record_numbers == ["44", "45"], "the cut-off record must still be saved, not dropped"
