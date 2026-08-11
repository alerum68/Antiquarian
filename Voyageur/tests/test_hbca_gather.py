import importlib.util
import json
from pathlib import Path
import pytest

_hbca_path = Path(__file__).resolve().parents[1] / "HBCA.py"
_spec = importlib.util.spec_from_file_location("voyageur_hbca", _hbca_path)
_hbca_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hbca_mod)


BioSheetEntry = _hbca_mod.BioSheetEntry
build_hbca_scaffold_sheet = _hbca_mod.build_hbca_scaffold_sheet
filter_entries_by_letter = _hbca_mod.filter_entries_by_letter
load_checkpoint = _hbca_mod.load_checkpoint
parse_biographical_index_html = _hbca_mod.parse_biographical_index_html
save_checkpoint = _hbca_mod.save_checkpoint


SAMPLE_INDEX_HTML = """
<!DOCTYPE html>
<html>
<body>
  <div class="content">
    <ul>
      <li><a href="../../_assets/docs/hbca/biographical/a/adams_george.pdf">Adams, George (b. ca. 1796-d. 1864) (fl. 1821-1854)</a></li>  # noqa: E501
      <li><a href="../../_assets/docs/hbca/biographical/a/adams_joseph.pdf">Adams, Joseph (fl. 1730-1737)</a></li>
      <li><a href="../../_assets/docs/hbca/biographical/b/ballenden_john.pdf">Ballenden, John (1810-1856) (fl. 1829-1856)</a></li>  # noqa: E501
      <li><a href="../../_assets/docs/hbca/biographical/c/connolly_william.pdf">Connolly, William (1786-1849) (fl. 1801-1831)</a></li>  # noqa: E501
    </ul>
  </div>
</body>
</html>
"""


def test_parse_biographical_index_html():
    entries = parse_biographical_index_html(
        SAMPLE_INDEX_HTML,
        base_url="https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html",
    )
    assert len(entries) == 4

    first = entries[0]
    assert first.employee_name == "Adams, George (b. ca. 1796-d. 1864) (fl. 1821-1854)"
    assert first.file_name == "adams_george.pdf"
    assert first.letter == "a"
    assert (
        first.pdf_url
        == "https://www.gov.mb.ca/chc/archives/_assets/docs/hbca/biographical/a/adams_george.pdf"
    )

    ballenden = entries[2]
    assert ballenden.file_name == "ballenden_john.pdf"
    assert ballenden.letter == "b"


def test_filter_entries_by_letter():
    entries = parse_biographical_index_html(
        SAMPLE_INDEX_HTML,
        base_url="https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html",
    )

    filtered_a = filter_entries_by_letter(entries, letters=["A"])
    assert len(filtered_a) == 2
    assert all(e.letter == "a" for e in filtered_a)

    filtered_ab = filter_entries_by_letter(entries, letters=["A", "B"])
    assert len(filtered_ab) == 3

    filtered_z = filter_entries_by_letter(entries, letters=["Z"])
    assert len(filtered_z) == 0


def test_build_hbca_scaffold_sheet():
    entry = BioSheetEntry(
        employee_name="Adams, George",
        file_name="adams_george.pdf",
        letter="a",
        pdf_url="https://www.gov.mb.ca/chc/archives/_assets/docs/hbca/biographical/a/adams_george.pdf",
    )
    raw_text = "NAME: ADAMS, George\nDATES: b. ca. 1796 d. 1864\nAppointments & Service: 1821-1854"
    sheet = build_hbca_scaffold_sheet(entry, raw_text=raw_text)

    assert sheet["page_id"] == "adams_george.pdf"
    assert sheet["document_metadata"]["file_name"] == "adams_george.pdf"
    assert sheet["document_metadata"]["document_type"] == "HBCA"
    assert (
        sheet["document_metadata"]["source_name"]
        == "Hudson's Bay Company Archives: Biographical Sheets"
    )
    assert (
        sheet["document_metadata"]["source_location"]
        == "Archives of Manitoba, Winnipeg, Manitoba, Canada"
    )
    assert sheet["document_metadata"]["employee_name"] == "Adams, George"
    assert sheet["document_metadata"]["raw_text"] == raw_text
    assert len(sheet["records"]) == 1
    assert sheet["records"][0]["participants"] == []


def test_checkpoint_roundtrip(tmp_path):
    cp_file = tmp_path / "hbca_checkpoint.json"
    downloaded = {"adams_george.pdf", "ballenden_john.pdf"}

    save_checkpoint(cp_file, downloaded_files=downloaded)
    assert cp_file.exists()

    loaded = load_checkpoint(cp_file)
    assert loaded == downloaded


def test_parse_biographical_index_html_extracts_letter():
    mock_html = '<html><body><a href="a/zebra.pdf">Zebra</a><a href="b/x-weird_name.pdf">X-Weird</a></body></html>'
    entries = parse_biographical_index_html(mock_html, base_url="https://fake.url/")

    assert len(entries) == 2
    assert entries[0].letter == "a"
    assert entries[1].letter == "b"
