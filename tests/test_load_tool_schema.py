import textwrap

import pytest

import Scriptorium


@pytest.fixture(autouse=True)
def _restore_shared_dicts():
    """_load_tool_schema mutates shared module-level dicts as a side effect - snapshot and
    restore them around every test so tests can't pollute each other or the real schema
    state loaded at import time."""
    tooltip_before = dict(Scriptorium.TOOLTIP_DESCRIPTIONS)
    labels_before = dict(Scriptorium.CUSTOM_LABELS)
    pickers_before = dict(Scriptorium.PATH_PICKER_FIELDS)
    widgets_before = dict(Scriptorium.FIELD_WIDGETS)
    yield
    Scriptorium.TOOLTIP_DESCRIPTIONS.clear()
    Scriptorium.TOOLTIP_DESCRIPTIONS.update(tooltip_before)
    Scriptorium.CUSTOM_LABELS.clear()
    Scriptorium.CUSTOM_LABELS.update(labels_before)
    Scriptorium.PATH_PICKER_FIELDS.clear()
    Scriptorium.PATH_PICKER_FIELDS.update(pickers_before)
    Scriptorium.FIELD_WIDGETS.clear()
    Scriptorium.FIELD_WIDGETS.update(widgets_before)


def test_load_tool_schema_basic_shape(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            FIELD_A:
              default: "hello"
              tooltip: "A tooltip."
            FIELD_B:
              default: 0.4
        """), encoding="utf-8")

    result = Scriptorium._load_tool_schema(tmp_path)

    assert result == {"Section One": {"FIELD_A": "hello", "FIELD_B": "0.4"}}


def test_load_tool_schema_str_coerces_yaml_typed_defaults(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            BOOL_FIELD:
              default: true
            INT_FIELD:
              default: 3
            FLOAT_FIELD:
              default: 0.4
        """), encoding="utf-8")

    result = Scriptorium._load_tool_schema(tmp_path)

    assert result == {"Section One": {"BOOL_FIELD": "True", "INT_FIELD": "3", "FLOAT_FIELD": "0.4"}}
    assert all(isinstance(v, str) for v in result["Section One"].values())


def test_load_tool_schema_merges_tooltip_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            FIELD_A:
              default: ""
              tooltip: "Explains FIELD_A."
        """), encoding="utf-8")

    Scriptorium._load_tool_schema(tmp_path)

    assert Scriptorium.TOOLTIP_DESCRIPTIONS["FIELD_A"] == "Explains FIELD_A."


def test_load_tool_schema_merges_widget_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            LEVEL:
              default: "1"
              widget: segmented
              options: [["0", "Low"], ["1", "Medium"], ["2", "High"]]
            AMOUNT:
              default: "0.4"
              widget: slider
              min: 0
              max: 5
              step: 0.1
              suffix: "s"
        """), encoding="utf-8")

    Scriptorium._load_tool_schema(tmp_path)

    assert Scriptorium.FIELD_WIDGETS["LEVEL"] == {
        "type": "segmented",
        "options": [("0", "Low"), ("1", "Medium"), ("2", "High")],
    }
    assert Scriptorium.FIELD_WIDGETS["AMOUNT"] == {
        "type": "slider", "min": 0, "max": 5, "step": 0.1, "suffix": "s",
    }
    assert isinstance(Scriptorium.FIELD_WIDGETS["AMOUNT"]["min"], int)
    assert isinstance(Scriptorium.FIELD_WIDGETS["AMOUNT"]["step"], float)


def test_load_tool_schema_merges_picker_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            OUT_FILE:
              default: ""
              picker:
                kind: save
                base_dir_key: "__PROGRAM_DIR__"
                defaultextension: ".ged"
                filetypes: [["GEDCOM files", "*.ged"], ["All files", "*.*"]]
        """), encoding="utf-8")

    Scriptorium._load_tool_schema(tmp_path)

    assert Scriptorium.PATH_PICKER_FIELDS["OUT_FILE"] == {
        "kind": "save",
        "base_dir_key": "__PROGRAM_DIR__",
        "defaultextension": ".ged",
        "filetypes": [("GEDCOM files", "*.ged"), ("All files", "*.*")],
    }


def test_load_tool_schema_merges_label_overrides_into_shared_dict(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            SOME_FIELD:
              default: ""
        label_overrides:
          SOME_FIELD: "A Nicer Label"
        """), encoding="utf-8")

    Scriptorium._load_tool_schema(tmp_path)

    assert Scriptorium.CUSTOM_LABELS["SOME_FIELD"] == "A Nicer Label"


def test_load_tool_schema_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        Scriptorium._load_tool_schema(tmp_path)


def test_load_tool_schema_malformed_yaml_raises_runtime_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text("sections: [this is not: valid: yaml", encoding="utf-8")

    with pytest.raises(RuntimeError):
        Scriptorium._load_tool_schema(tmp_path)


def test_load_tool_schema_missing_sections_key_raises_value_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text("foo: bar\n", encoding="utf-8")

    with pytest.raises(ValueError):
        Scriptorium._load_tool_schema(tmp_path)


def test_load_tool_schema_section_not_a_mapping_raises_value_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One: ["not", "a", "mapping"]
        """), encoding="utf-8")

    with pytest.raises(ValueError):
        Scriptorium._load_tool_schema(tmp_path)


def test_load_tool_schema_field_missing_default_raises_value_error(tmp_path):
    (tmp_path / "settings_schema.yaml").write_text(textwrap.dedent("""\
        sections:
          Section One:
            FIELD_A:
              tooltip: "no default here"
        """), encoding="utf-8")

    with pytest.raises(ValueError):
        Scriptorium._load_tool_schema(tmp_path)
