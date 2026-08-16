from pathlib import Path

import Antiquarian

BASE_DIR = Path(__file__).resolve().parent.parent


def test_archivist_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Archivist")

    assert result == {
        "Which JSON to Build From": {
            "JSON_FILE": "", "GEDCOM_OUTPUT_NAME": "Family_Register.ged",
            "GEDCOM_OUTPUT_MODE": "Both", "APID_DB": "", "ANCESTRY_IMAGE_BASE_ID": "",
        },
        "Citation Overrides": {
            "CITATION_TEXT": "", "CITATION_DETAIL": "",
            "CALL_NUMBER": "", "REPOSITORY": "", "REPOSITORY_LOC": "",
            "COLLECTION_URL": "", "COLLECTION_NAME": "", "PUBLISHER": "",
            "PUB_LOC": "", "REGISTER_NAME": "", "REGISTER_SOURCE_ID": "1",
            "VOLUME_TITLE": "", "VOLUME_NUM": "",
        },
    }


def test_voyageur_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Voyageur")

    assert result == {
        "Gather Settings": {"VOYAGEUR_SOURCE": "", "GATHER_URL": "", "GATHER_ON_COLLISION": "overwrite"},
        "HBCA / Manitoba Archives": {
            "HBCA_LETTER_FILTER": "",
            "HBCA_RESOLVE_KEYSTONE": "false",
            "HBCA_DOWNLOAD_KEYSTONE_MEDIA": "true",
        },
    }


def test_paleographer_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Paleographer")

    assert result == {
        "Antigravity CLI": {"AGY_CLI_BIN": "agy"},
        "Data & Directories": {
            "PALEOGRAPHER_RECORD_TYPE": "",
            "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "2",
        },
        "Parish Information": {
            "CHURCH_MASTER_DB_NAME": "parish_register.json",
            "PARISH_NAME": "St. Generic Catholic Church",
            "PARISH_NAME_SHORT": "St. Generic Parish, Anytown, ST",
            "PARISH_CITY": "Anytown", "PARISH_STATE": "State",
            "DEFAULT_EVENT_LOCATION": "Anytown, Any County, State, USA",
        },
        "Register Information": {
            "VOLUME_TITLE": "Volume 1", "VOLUME_NUM": "1",
        },
        "Scrip Information": {
            "SCRIP_MASTER_DB_NAME": "scrip_records.json",
            "SCRIP_COLLECTION_NAME": "Library and Archives Canada, RG15 Scrip Records",
            "SCRIP_DISTRICT": "",
        },
    }


def test_paleographer_help_text_mentions_resolve_names():
    import tkinter
    if getattr(tkinter, "_default_root", None) is not None and hasattr(tkinter._default_root, "help_texts"):
        assert "Resolve Names" in tkinter._default_root.help_texts["Paleographer"]
    else:
        root = Antiquarian.Antiquarian()
        try:
            assert "Resolve Names" in root.help_texts["Paleographer"]
        finally:
            root.withdraw()


def test_registrar_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "Registrar")

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
    result = Antiquarian._load_tool_schema(BASE_DIR / "Gazetteer")

    assert result == {
        "File Paths": {
            "GAZETTEER_RM_DATABASE": "Your Tree.rmtree",
            "GAZETTEER_SHAPEFILE": "Antiquarian/Gazetteer/Reference/US_AtlasHCB_Counties/"
            "US_HistCounties_Shapefile/US_HistCounties.shp",
            "GAZETTEER_CA_SHAPEFILE_DIR": "Antiquarian/Gazetteer/CA_UNICEN_Counties",
        },
    }


def test_pdfix_schema_matches_expected_shape():
    result = Antiquarian._load_tool_schema(BASE_DIR / "PDFix")

    assert result == {
        "Scan Settings": {
            "PDFIX_TARGET_DIR": ".", "PDFIX_COMPRESSION_LEVEL": "2",
        },
        "Safety": {"PDFIX_CREATE_BACKUP": "True", "PDFIX_REPAIR_MODE": "False"},
    }


def test_batch_set_env_updates_existing_and_preserves_comments(tmp_path):
    from dotenv import dotenv_values
    env_file = tmp_path / ".env"
    env_file.write_text("# Initial comment\nFOO='old'\nBAR='keep'\n", encoding="utf-8")

    Antiquarian.batch_set_env(env_file, {"FOO": "new", "BAZ": "created", "EMPTY": ""})

    vals = dotenv_values(env_file)
    assert vals == {"FOO": "new", "BAR": "keep", "BAZ": "created", "EMPTY": ""}
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Initial comment"
    assert "FOO='new'" in lines
    assert "BAR='keep'" in lines
    assert "BAZ='created'" in lines
    assert "EMPTY=''" in lines
