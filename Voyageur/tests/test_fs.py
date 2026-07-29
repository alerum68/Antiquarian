import FS

ROLES = {
    "1": {"name": "Primary", "semantic": "primary"},
    "2": {"name": "Father", "semantic": "father"},
    "7": {"name": "Godfather/Witness 1"},
}


def test_derive_role_semantic_matches_by_role_number():
    assert FS.derive_role_semantic("1", ROLES) == "primary"
    assert FS.derive_role_semantic("2", ROLES) == "father"


def test_derive_role_semantic_none_for_role_without_semantic():
    assert FS.derive_role_semantic("7", ROLES) is None


def test_derive_role_semantic_none_for_missing_role_number():
    assert FS.derive_role_semantic(None, ROLES) is None
