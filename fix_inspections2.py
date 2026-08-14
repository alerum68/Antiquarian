import re
from pathlib import Path

def apply_fixes():
    base_dir = Path(r"C:\Users\Jason Cole\Documents\Genealogy\Scriptorium")

    # Fix test_record_registry.py
    f = base_dir / "Commissioner" / "tests" / "test_record_registry.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace('expected = expected_parts[0]', 'expected = expected_parts[0]  # type: ignore')
    content = content.replace('rec["participants"][0] = primary', 'rec["participants"][0] = primary  # type: ignore')
    content = content.replace('assert r.participants[0]["role_name"] ==', '# type: ignore\n    assert r.participants[0]["role_name"] ==')
    content = content.replace('assert r.participants[1]["role_name"] ==', '# type: ignore\n    assert r.participants[1]["role_name"] ==')
    content = content.replace('assert r.participants[0]["type_specific_fields"]["line_number"] ==', '# type: ignore\n    assert r.participants[0]["type_specific_fields"]["line_number"] ==')
    content = content.replace('assert sheet["document_metadata"]["file_name"] ==', '# type: ignore\n    assert sheet["document_metadata"]["file_name"] ==')
    content = content.replace('assert sheet["document_metadata"]["source_name"] ==', '# type: ignore\n    assert sheet["document_metadata"]["source_name"] ==')
    content = content.replace('assert data["sheets"][0]["document_metadata"] ==', '# type: ignore\n    assert data["sheets"][0]["document_metadata"] ==')
    f.write_text(content, encoding="utf-8")

    # Fix test_hbca_profile.py
    f = base_dir / "Archivist" / "tests" / "test_hbca_profile.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace('assert "3 _WEBTAG" in cit', '# type: ignore\n    assert "3 _WEBTAG" in cit')
    content = content.replace('Archivist.resolve_profile', '# noinspection PyUnresolvedReferences\n    Archivist.resolve_profile')
    content = content.replace('assert "\\n1 _LINK" in cit', '# type: ignore\n    assert "\\n1 _LINK" in cit')
    f.write_text(content, encoding="utf-8")

if __name__ == "__main__":
    apply_fixes()
