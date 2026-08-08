from pathlib import Path

import Scriptorium

BASE_DIR = Path(__file__).resolve().parent.parent


def test_archivist_schema_matches_expected_shape():
    result = Scriptorium._load_tool_schema(BASE_DIR / "Archivist")

    assert result == {
        "Which JSON to Build From": {
            "JSON_FILE": "", "GEDCOM_OUTPUT_NAME": "Family_Register.ged",
            "GEDCOM_OUTPUT_MODE": "Both", "IMAGE_DIR": "",
            "APID_DB": "", "ANCESTRY_IMAGE_BASE_ID": "",
        },
        "Location Overrides": {
            "STATE": "", "COUNTY": "", "TOWNSHIP": "",
            "ENUMERATION_DISTRICT": "", "FILM_NUMBER": "", "ROLL_NUMBER": "",
            "DEFAULT_EVENT_LOCATION": "", "PARISH_NAME": "Parish Name",
            "PARISH_NAME_SHORT": "Parish", "PARISH_CITY": "City",
            "PARISH_STATE": "State", "PARISH_FILE_NAME": "Parish_Export",
        },
        "Family Inference Tuning": {
            "MIN_MARRIAGE_AGE": "12", "MAX_SPOUSE_AGE_GAP": "25",
            "HUSBAND_CHILD_AGE_GAP_MIN": "14", "HUSBAND_CHILD_AGE_GAP_MAX": "60",
            "WIFE_CHILD_AGE_GAP_MIN": "12", "WIFE_CHILD_AGE_GAP_MAX": "50",
        },
        "Citation & Role Vocabulary": {
            "TRANSCRIPTION_HEADER": "Citation Text:", "TRANSLATION_HEADER": "Citation Details:",
            "ROLE_CLERGY": "Priest", "CLERGY_HONORIFIC": "Father", "ROLE_DEFAULT_WITNESS": "Witness",
            "CALL_NUMBER": "", "REPOSITORY": "", "REPOSITORY_LOC": "",
            "COLLECTION_URL": "", "COLLECTION_NAME": "", "PUBLISHER": "",
            "PUB_LOC": "", "REGISTER_NAME": "", "REGISTER_SOURCE_ID": "1",
            "VOLUME_TITLE": "", "VOLUME_NUM": "",
        },
    }


def test_voyageur_schema_matches_expected_shape():
    result = Scriptorium._load_tool_schema(BASE_DIR / "Voyageur")

    assert result == {
        "Gather Settings": {"VOYAGEUR_SOURCE": ""},
        "Ancestry": {"A_URL": ""},
        "FamilySearch": {"FS_URL": ""},
        "LAC": {
            "LAC_URL": "", "LAC_IMAGE_DIR": "LAC",
            "LAC_HARVEST_VOLUME": "", "LAC_ARCHIVAL_NUMBER": "RG15",
            "LAC_COOKIE_FILE": "Working/LAC/lac_cookies.txt",
            "LAC_CHECKPOINT_DIR": "Working/LAC", "LAC_CDP_PORT": "9222", "LAC_MAX_WORKERS": "1",
            "LAC_RECORD_TYPE": "", "LAC_VOLUME": "", "VOLUME_TITLE": "",
        },
    }


def test_paleographer_schema_matches_expected_shape():
    result = Scriptorium._load_tool_schema(BASE_DIR / "Paleographer")

    assert result == {
        "Antigravity CLI": {"AGY_CLI_BIN": "agy", "AGY_TIMEOUT_SECONDS": "240"},
        "Data & Directories": {
            "PALEOGRAPHER_RECORD_TYPE": "", "CHURCH_IMAGE_DIR": "Parish",
            "CHURCH_GEDCOM_NAME": "Parish.ged", "CHURCH_MASTER_DB_NAME": "parish_register.json",
            "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "2", "MASTER_DB": "", "OUTPUT_DIR": "",
        },
        "Parish Information": {
            "PARISH_NAME": "St. Generic Catholic Church",
            "PARISH_NAME_SHORT": "St. Generic Parish, Anytown, ST",
            "PARISH_CITY": "Anytown", "PARISH_STATE": "State",
            "PARISH_FILE_NAME": "Parish_Anytown",
            "DEFAULT_EVENT_LOCATION": "Anytown, Any County, State, USA",
        },
        "Register Information": {
            "REGISTER_SOURCE_ID": "1",
            "REGISTER_NAME": "Baptisms, marriages and burials, 1850-1900",
            "VOLUME_TITLE": "Volume 1", "VOLUME_NUM": "1",
        },
        "Church Citation (Source)": {
            "CHURCH_CALL_NUMBER": "Call #1234567",
            "CHURCH_COLLECTION_URL": "https://www.familysearch.org/search/collection",
            "CHURCH_COLLECTION_NAME": "Generic Historical Collection",
            "CHURCH_REPOSITORY": "FamilySearch.org", "CHURCH_REPOSITORY_LOC": "Granite Mountain, UT",
        },
        "Scrip Information": {
            "SCRIP_IMAGE_DIR": "Scrip", "SCRIP_MASTER_DB_NAME": "scrip_records.json",
            "SCRIP_COLLECTION_NAME": "Library and Archives Canada, RG15 Scrip Records",
            "SCRIP_DISTRICT": "", "SCRIP_DELAY_SECONDS": "0.4",
            "SCRIP_ENRICH_LIMIT": "", "SCRIP_PARTITION_OUTPUT_DIR": "",
        },
    }


def test_paleographer_help_text_mentions_resolve_names():
    import tkinter
    if getattr(tkinter, "_default_root", None) is not None and hasattr(tkinter._default_root, "help_texts"):
        assert "Resolve Names" in tkinter._default_root.help_texts["Paleographer"]
    else:
        root = Scriptorium.Scriptorium()
        try:
            assert "Resolve Names" in root.help_texts["Paleographer"]
        finally:
            root.withdraw()


def test_registrar_schema_matches_expected_shape():
    result = Scriptorium._load_tool_schema(BASE_DIR / "Registrar")

    assert result == {
        "File Paths (Relative to RootsMagic Dir)": {"REGISTRAR_RM_DATABASE": "Your Tree.rmtree"},
        "Matching Thresholds": {
            "REGISTRAR_FUZZY_THRESHOLD": "82", "REGISTRAR_MAX_AGE_GAP": "5",
            "REGISTRAR_FUZZY_THRESHOLD_STRICT": "95", "REGISTRAR_FAMILY_MATCH_THRESHOLD": "75",
        },
        "RootsMagic UI Settings": {
            "REGISTRAR_FOLDER_NAME": "!Duplicate Review",
            "REGISTRAR_COLOR_SET": "1", "REGISTRAR_COLOR_VALUE": "27",
        },
    }
def test_gazetteer_schema_matches_expected_shape():
    result = Scriptorium._load_tool_schema(BASE_DIR / "Gazetteer")

    assert result == {
        "File Paths": {
            "GAZETTEER_RM_DATABASE": "Your Tree.rmtree",
            "GAZETTEER_SHAPEFILE": "Scriptorium/Gazetteer/Reference/US_AtlasHCB_Counties/"
                                    "US_HistCounties_Shapefile/US_HistCounties.shp",
            "GAZETTEER_CA_SHAPEFILE_DIR": "Scriptorium/Gazetteer/CA_UNICEN_Counties",
        },
        "Settings": {"GAZETTEER_DEBUG_MODE": "False", "GAZETTEER_CREATE_BACKUP": "True"},
    }


def test_pdfix_schema_matches_expected_shape():
    result = Scriptorium._load_tool_schema(BASE_DIR / "PDFix")

    assert result == {
        "Scan Settings": {
            "PDFIX_TARGET_DIR": ".", "PDFIX_COMPRESSION_LEVEL": "2", "PDFIX_SIZE_THRESHOLD_MB": "0",
        },
        "Safety": {"PDFIX_CREATE_BACKUP": "True", "PDFIX_REPAIR_MODE": "False"},
    }

