"""Golden-file capture: runs build_gedcom_from_general on today's unmodified
Archivist.py against a Scrip fixture and a Parish fixture, for both target
software flavors, and writes the four outputs as committed .ged fixtures.
Task 6's regression test rebuilds the same fixtures through the post-split
modules and diffs byte-for-byte against these files - run this script again,
by hand, ONLY if a real (intentional) behavior change is made after the split;
never re-run it to make a failing regression test pass."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import General as arc
import Scrip

GOLDEN_DIR = Path(__file__).resolve().parent

SCRIP_FIXTURE = {
    "collection_title": "Test Scrip Collection", "record_type_name": "Scrip",
    "sheets": [{
        "document_metadata": {"file_name": "BAC-LAC_fonandcol_1502188.pdf", "pages": "1", "file_type": "pdf"},
        "records": [{
            "event_type": "Scrip", "page": "1", "record_id": "SCRIP-5473", "year": "1880",
            "event_place": "Winnipeg",
            "type_specific_fields": {
                "claim_number": "3126", "affidavit_number": "5473",
                "scrip_number": "12761", "scrip_amount": "$160", "claim_basis": "Half-breed Head",
            },
            "source_documents": [
                {"document_type": "Scrip Certificate",
                 "media_path": "C:/Media/Commissioner/1502999/e099999999.pdf"},
            ],
            "participants": [
                {"role_semantic": "primary", "role_name": "Claimant", "role_number": "0",
                 "sex": "M", "std_given": "Roger", "std_surname": "Letendre",
                 "is_priest": False, "age": "35"},
                {"role_semantic": "witness", "role_name": "Witness", "role_number": "1",
                 "sex": "M", "std_given": "Baptiste", "std_surname": "Sabiston",
                 "is_priest": False, "age": ""},
            ],
        }],
    }],
}

PARISH_FIXTURE = {
    "collection_title": "St. Boniface Parish Register", "record_type_name": "Parish",
    "sheets": [{
        "document_metadata": {"file_name": "st_boniface_vol3_p12.pdf", "pages": "12",
                               "file_type": "pdf", "source_name": "St. Boniface"},
        "records": [{
            "event_type": "Baptism", "page": "12", "record_id": "REC-1", "year": "1875",
            "event_place": "St. Boniface, Manitoba", "vol": "3",
            "type_specific_fields": {"document_type": "Baptism Register"},
            "citation_text": "Le douze mars mil huit cent soixante-quinze...",
            "citation_details": "On the twelfth of March, eighteen seventy-five...",
            "participants": [
                {"role_semantic": "primary", "role_name": "Child", "role_number": "0",
                 "sex": "F", "std_given": "Marie", "std_surname": "Gagnon",
                 "is_priest": False, "age": ""},
                {"role_semantic": "father", "role_name": "Father", "role_number": "1",
                 "sex": "M", "std_given": "Jean", "std_surname": "Gagnon",
                 "is_priest": False, "age": ""},
                {"role_semantic": "mother", "role_name": "Mother", "role_number": "2",
                 "sex": "F", "std_given": "Josephte", "std_surname": "Nolin",
                 "is_priest": False, "age": ""},
                {"role_semantic": "witness", "role_name": "Priest", "role_number": "3",
                 "sex": "M", "std_given": "Georges", "std_surname": "Dugas",
                 "is_priest": True, "age": ""},
            ],
        }],
    }],
}


def _normalize(text: str) -> str:
    return re.sub(r"1 DATE .*\r?\n2 TIME .*", "1 DATE 07 AUG 2026\n2 TIME 14:11:32", text)


DEFAULT_GENERAL_CONFIG = {
    'volume_num': '',
    'register_source_id': '1',
    'register_name': '',
    'parish_name': '',
    'parish_name_short': '',
    'parish_location': '',
    'volume_title': '',
    'date_range_str': '',
    'diocese': '',
    'collection_url': '',
    'collection_name': '',
    'parish_file_name': '',
    'default_location': '',
    'citation_detail': '',
    'citation_text': '',
    'role_clergy': 'Priest',
    'role_default_witness': 'Witness',
    'clergy_honorific': 'Father',
}


def _regenerate(fixture: dict, target_software: str, profile) -> str:
    arc.set_active_profile(profile)
    arc.CALL_NUMBER = ""
    arc.COLLECTION_URL = ""
    arc.COLLECTION_NAME = ""
    arc.REPOSITORY = ""
    arc.REPOSITORY_LOC = ""
    arc.GENERAL_CONFIG.clear()
    arc.GENERAL_CONFIG.update(DEFAULT_GENERAL_CONFIG)
    raw = arc.build_gedcom_from_general(fixture, target_software)
    return _normalize(raw)


def main() -> None:
    (GOLDEN_DIR / "scrip_rm.ged").write_text(
        _regenerate(SCRIP_FIXTURE, "RM", Scrip.ScripProfile()), encoding="utf-8")
    (GOLDEN_DIR / "scrip_ftm.ged").write_text(
        _regenerate(SCRIP_FIXTURE, "FTM", Scrip.ScripProfile()), encoding="utf-8")

    (GOLDEN_DIR / "parish_rm.ged").write_text(
        _regenerate(PARISH_FIXTURE, "RM", arc.GeneralProfile()), encoding="utf-8")
    (GOLDEN_DIR / "parish_ftm.ged").write_text(
        _regenerate(PARISH_FIXTURE, "FTM", arc.GeneralProfile()), encoding="utf-8")
    print(f"Wrote 4 golden files to {GOLDEN_DIR}")


if __name__ == "__main__":
    main()
