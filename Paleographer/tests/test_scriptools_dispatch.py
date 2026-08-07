import ScripTools


def test_scriptools_module_has_main():
    assert callable(ScripTools.main)


def test_build_claim_search_query_reads_type_specific_fields():
    record = {"type_specific_fields": {"claim_number": "123"}}
    assert ScripTools.build_claim_search_query(record) == "claim: 123"


def test_build_claim_search_query_top_level_fields_are_ignored():
    record = {"claim_number": "123"}
    assert ScripTools.build_claim_search_query(record) is None
