import re
from pathlib import Path

def apply_fixes():
    base_dir = Path(r"C:\Users\Jason Cole\Documents\Genealogy\Scriptorium")

    # Fix test_archivist.py
    f = base_dir / "Archivist" / "tests" / "test_archivist.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("profile = # noinspection PyUnresolvedReferences\n    Archivist.resolve_profile", "profile = Archivist.resolve_profile")
    # Actually, I should just remove the # noinspection there.
    # Let's do regex replace for profile = # ... \n Archivist.resolve_profile
    content = re.sub(r'profile = # noinspection PyUnresolvedReferences\s*\n\s*Archivist\.resolve_profile', r'profile = Archivist.resolve_profile  # type: ignore', content)
    f.write_text(content, encoding="utf-8")

    # Fix test_census_ingestion.py
    f = base_dir / "Archivist" / "tests" / "test_census_ingestion.py"
    content = f.read_text(encoding="utf-8")
    content = content.replace("import Census as Census as arc", "import Census as arc")
    f.write_text(content, encoding="utf-8")

    # Fix test_hbca_profile.py (might have the same issue with Archivist.resolve_profile)
    f = base_dir / "Archivist" / "tests" / "test_hbca_profile.py"
    content = f.read_text(encoding="utf-8")
    content = re.sub(r'profile = # noinspection PyUnresolvedReferences\s*\n\s*Archivist\.resolve_profile', r'profile = Archivist.resolve_profile  # type: ignore', content)
    content = content.replace("import HBCA as HBCA as arc", "import HBCA as arc")
    f.write_text(content, encoding="utf-8")

if __name__ == "__main__":
    apply_fixes()
