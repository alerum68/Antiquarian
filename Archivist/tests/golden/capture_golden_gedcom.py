"""Golden-file capture: runs build_gedcom_from_general on today's unmodified
Archivist.py against a Scrip fixture and a Parish fixture, for both target
software flavors, and writes the four outputs as committed .ged fixtures.
Task 6's regression test rebuilds the same fixtures through the post-split
modules and diffs byte-for-byte against these files - run this script again,
by hand, ONLY if a real (intentional) behavior change is made after the split;
never re-run it to make a failing regression test pass."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import Archivist as arc

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


def main() -> None:
    arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
    (GOLDEN_DIR / "scrip_rm.ged").write_text(
        arc.build_gedcom_from_general(SCRIP_FIXTURE, "RM"), encoding="utf-8")
    (GOLDEN_DIR / "scrip_ftm.ged").write_text(
        arc.build_gedcom_from_general(SCRIP_FIXTURE, "FTM"), encoding="utf-8")

    arc.GENERAL_CONFIG['omit_source_id_prefix'] = False
    (GOLDEN_DIR / "parish_rm.ged").write_text(
        arc.build_gedcom_from_general(PARISH_FIXTURE, "RM"), encoding="utf-8")
    (GOLDEN_DIR / "parish_ftm.ged").write_text(
        arc.build_gedcom_from_general(PARISH_FIXTURE, "FTM"), encoding="utf-8")
    print(f"Wrote 4 golden files to {GOLDEN_DIR}")


if __name__ == "__main__":
    main()
