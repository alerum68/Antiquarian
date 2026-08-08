import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ScripProfile


def test_scrip_profile_dynamic_source_id_has_no_register_prefix():
    profile = ScripProfile.ScripProfile()
    assert profile.dynamic_source_id("3") == "@S003@"


def test_scrip_profile_participant_uid_uses_identity_directly_for_primary():
    profile = ScripProfile.ScripProfile()
    assert profile.participant_uid("SCRIP-5473", "0", 0) == "SCRIP-5473"


def test_scrip_profile_repository_defaults_to_lac():
    profile = ScripProfile.ScripProfile()
    assert profile.repository_defaults() == ("Library and Archives Canada", "Ottawa, ON")
