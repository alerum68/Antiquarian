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


def test_general_rmst_element_to_gedcom_uses_stmplt_tag_vocabulary():
    import lxml.etree as etree
    xml = etree.fromstring("""
    <Template Id="88888">
      <Name>!Test Template</Name>
      <Description>Paragraph one.

Paragraph two.</Description>
      <Category>Test Category</Category>
      <Footnote>Footnote text.</Footnote>
      <ShortFootnote>Short text.</ShortFootnote>
      <Bibliography>Bibliography text.</Bibliography>
      <Field>
        <Type>Name</Type>
        <Name>TestField</Name>
        <Display>Test Field</Display>
        <Hint>a hint</Hint>
        <Detail>False</Detail>
        <LongHint/>
      </Field>
    </Template>
    """)
    lines = General._rmst_element_to_gedcom(xml)
    joined = "\n".join(lines)
    assert "0 _STMPLT" in joined
    assert "_SRCTEMPLATE" not in joined
    assert "1 NAME !Test Template" in joined
    assert "1 DESC Paragraph one." in joined
    assert "2 CONT " in joined
    assert "2 CONT Paragraph two." in joined
    assert "1 FOOTNOTE Footnote text." in joined
    assert "1 BIBLIO Bibliography text." in joined
    assert "2 DISPLAY Test Field" in joined
    assert "2 TYPE NAME" in joined
    assert "2 ISDETAIL N" in joined
