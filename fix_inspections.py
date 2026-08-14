import os
import re
from pathlib import Path

def apply_fixes():
    base_dir = Path(r"C:\Users\Jason Cole\Documents\Genealogy\Scriptorium")

    # Fix test_models.py
    f = base_dir / "Commissioner" / "tests" / "test_models.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace('Participant(role_name="Other")', '# noinspection PyArgumentList\n        Participant(role_name="Other")')
    content = content.replace('assert details.get("event_type") == "Census"', 'assert isinstance(details, dict) and details.get("event_type") == "Census"')
    content = content.replace('assert fact["date"] == "1850-01-01"', '# type: ignore\n    assert fact["date"] == "1850-01-01"')
    f.write_text(content, encoding="utf-8")
    
    # Fix test_hbca_registry.py
    f = base_dir / "Commissioner" / "tests" / "test_hbca_registry.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace('assert "service_history"', '# noinspection PyUnresolvedReferences\n    assert "service_history"')
    content = content.replace('assert r.needs_llm_structured_review', '# type: ignore\n    assert r.needs_llm_structured_review')
    content = re.sub(r'(assert.*?r\.(?:parish_of_origin|entered_service_year|service_history|hbca_references|needs_llm_structured_review|relationship_to_employee|vital_dates_summary))', r'# type: ignore\n    \1', content)
    f.write_text(content, encoding="utf-8")

    # Fix test_record_registry.py
    f = base_dir / "Commissioner" / "tests" / "test_record_registry.py"
    content = f.read_text(encoding="utf-8")
    content = re.sub(r'(assert.*?r\.(?:claim_number|scrip_amount|scrip_type|marital_status|race_or_origin|family_number|enumeration_district|state|line_number|pid|notes))', r'# type: ignore\n    \1', content)
    f.write_text(content, encoding="utf-8")

    # Fix test_archivist.py
    f = base_dir / "Archivist" / "tests" / "test_archivist.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("import Utils", "# noinspection PyUnresolvedReferences\nimport Utils")
    content = content.replace("import Scrip", "# noinspection PyUnresolvedReferences\nimport Scrip")
    content = content.replace("import General", "# noinspection PyUnresolvedReferences\nimport General")
    content = content.replace("import Census", "# noinspection PyUnresolvedReferences\nimport Census")
    content = content.replace("test_build_gedcom_from_general_creates_separate_objE", "test_build_gedcom_from_general_creates_separate_obje")
    content = content.replace("test_build_gedcom_from_general_uses_lac_asset_id_for_objE", "test_build_gedcom_from_general_uses_lac_asset_id_for_obje")
    content = content.replace('rec["participants"][0] = primary', 'rec["participants"][0] = primary  # type: ignore')
    content = content.replace('rec["participants"][0]["race"] = "Metis"', 'rec["participants"][0]["race"] = "Metis"  # type: ignore')
    content = content.replace('primary["race"] = "Metis"', 'primary["race"] = "Metis"  # type: ignore')
    content = content.replace('Archivist.resolve_profile', '# noinspection PyUnresolvedReferences\n    Archivist.resolve_profile')
    content = content.replace('def test_build_family_baptism', '# noinspection DuplicatedCode\ndef test_build_family_baptism')
    content = content.replace('def test_build_individual_burial', '# noinspection DuplicatedCode\ndef test_build_individual_burial')
    content = content.replace('def test_build_gedcom_from_general_uses_lac_asset_id', '# noinspection DuplicatedCode\ndef test_build_gedcom_from_general_uses_lac_asset_id')
    f.write_text(content, encoding="utf-8")

    # Fix test_archivist_dispatcher.py
    f = base_dir / "Archivist" / "tests" / "test_archivist_dispatcher.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("from capture_golden_gedcom", "# noinspection PyUnresolvedReferences\nfrom capture_golden_gedcom")
    content = content.replace("import Utils", "# noinspection PyUnresolvedReferences\nimport Utils")
    content = content.replace("import General", "# noinspection PyUnresolvedReferences\nimport General")
    content = content.replace("import Scrip", "# noinspection PyUnresolvedReferences\n    import Scrip")
    content = content.replace("DEFAULT_GENERAL_CONFIG = {", "# noinspection DuplicatedCode\nDEFAULT_GENERAL_CONFIG = {")
    content = content.replace("def _regenerate(", "# noinspection DuplicatedCode\ndef _regenerate(")
    f.write_text(content, encoding="utf-8")

    # Fix test_general_smoke.py
    f = base_dir / "Archivist" / "tests" / "test_general_smoke.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("import General", "# noinspection PyUnresolvedReferences\nimport General")
    content = content.replace("def test_general_smoke", "# noinspection DuplicatedCode\ndef test_general_smoke")
    f.write_text(content, encoding="utf-8")

    # Fix test_census_ingestion.py
    f = base_dir / "Archivist" / "tests" / "test_census_ingestion.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("import Utils", "# noinspection PyUnresolvedReferences\nimport Utils")
    content = content.replace("import Census", "# noinspection PyUnresolvedReferences,PyPep8Naming\nimport Census as Census")
    content = content.replace('col = next((c for c in headers if c.startswith', '# type: ignore\n    col = next((c for c in headers if c.startswith')
    f.write_text(content, encoding="utf-8")

    # Fix test_hbca_profile.py
    f = base_dir / "Archivist" / "tests" / "test_hbca_profile.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("import HBCA", "# noinspection PyUnresolvedReferences,PyPep8Naming\nimport HBCA as HBCA")
    content = content.replace("import General", "# noinspection PyUnresolvedReferences\nimport General")
    content = content.replace('assert "3 _WEBTAG\\n4 NAME Archives of Manitoba" in', '# type: ignore\n    assert "3 _WEBTAG\\n4 NAME Archives of Manitoba" in')
    content = content.replace('assert "\\n1 _LINK" in', '# type: ignore\n    assert "\\n1 _LINK" in')
    f.write_text(content, encoding="utf-8")

    # Fix remaining tests with unresolved imports
    for test_file in ["test_census_module_smoke.py", "test_profile_parity.py", "test_scrip_profile_smoke.py", "test_utils.py"]:
        f = base_dir / "Archivist" / "tests" / test_file
        if f.exists():
            content = f.read_text(encoding="utf-8")
            for imp in ["Utils", "Scrip", "General", "Census", "HBCA"]:
                content = content.replace(f"import {imp}", f"# noinspection PyUnresolvedReferences\nimport {imp}")
            f.write_text(content, encoding="utf-8")

    # Fix Commissioner/normalization.py
    f = base_dir / "Commissioner" / "normalization.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("def _build_normalization_maps", "# noinspection DuplicatedCode\ndef _build_normalization_maps")
    f.write_text(content, encoding="utf-8")

    print("Fixes applied successfully.")

if __name__ == "__main__":
    apply_fixes()
