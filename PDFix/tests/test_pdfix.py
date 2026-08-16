import fitz

from PDFix import PDFix


def _make_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Test page {i}")
    doc.save(str(path))
    doc.close()


# ==========================================
# page_by_page_recovery
# ==========================================
def test_page_by_page_recovery_returns_document_when_no_output_path(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(pdf_path)

    doc = PDFix.page_by_page_recovery(str(pdf_path))

    assert doc is not None
    assert doc.page_count == 2
    doc.close()


def test_page_by_page_recovery_writes_to_output_path_without_mutating_original(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    output_path = tmp_path / "repaired.pdf"
    _make_pdf(pdf_path)
    original_bytes = pdf_path.read_bytes()

    result = PDFix.page_by_page_recovery(str(pdf_path), str(output_path))

    assert result is True
    assert output_path.exists()
    assert pdf_path.read_bytes() == original_bytes


# ==========================================
# optimize_pdf (regression test for the page_by_page_recovery arg-count bug)
# ==========================================
def test_optimize_pdf_repair_mode_uses_page_by_page_fallback_without_typeerror(tmp_path, monkeypatch):
    """Regression test: optimize_pdf's repair fallback used to call
    page_by_page_recovery(pdf_path, temp_optimized_pdf_path) - 2 positional args -
    against a signature that only accepted 1, raising TypeError instead of repairing."""
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(pdf_path, pages=2)

    real_save = fitz.Document.save

    def selective_fail_save(self, *args, **kwargs):
        # Only the two direct optimize_pdf() save attempts pass "garbage"; letting
        # page_by_page_recovery's own plain new_doc.save(temp_file.name) through
        # unpatched is what actually forces this exact fallback path to run.
        if "garbage" in kwargs:
            raise RuntimeError("simulated save failure")
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Document, "save", selective_fail_save)

    result = PDFix.optimize_pdf(str(pdf_path), PDFix.COMPRESSION_PARAMS[1], repair_mode=True)

    assert result["success"] is True
    assert result["repaired"] is True
    assert result["error"] is None
