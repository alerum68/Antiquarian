# noinspection PyUnresolvedReferences
import General
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_general_module_imports_and_default_profile_is_general():
    assert isinstance(General._ACTIVE_PROFILE, General.GeneralProfile)


def test_get_dynamic_source_id_keeps_prefix_by_default():
    General.set_active_profile(General.GeneralProfile())
    orig = General.GENERAL_CONFIG.get('register_source_id')
    try:
        General.GENERAL_CONFIG['register_source_id'] = '1042'
        assert General.get_dynamic_source_id("3") == "@S1042003@"
    finally:
        if orig is not None:
            General.GENERAL_CONFIG['register_source_id'] = orig
        else:
            General.GENERAL_CONFIG.pop('register_source_id', None)
