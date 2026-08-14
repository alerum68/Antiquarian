from Commissioner.record_registry import (
    get_document_types,
    get_valid_roles,
    get_field_remap,
    parse_collection,
    validate_participant_extra_fields,
    validate_record_extra_fields,
)


def test_hbca_pmt_registered():
    doc_types = get_document_types()
    assert "HBCA" in doc_types


def test_hbca_valid_roles():
    roles = get_valid_roles("HBCA")
    assert "Employee" in roles
    assert "Spouse" in roles
    assert "Child" in roles
    assert "Father" in roles
    assert "Mother" in roles


def test_hbca_field_remap():
    remap = get_field_remap("HBCA")
    assert remap.get("HBCA_MASTER_DB_NAME") == "MASTER_DB_NAME"
    # Image dirs are auto-resolved as Media/<Prompt_Name>, not remapped.
    assert "HBCA_IMAGE_DIR" not in remap


def test_hbca_record_extra_fields():
    extra = validate_record_extra_fields(
        "HBCA",
        {
            "parish_of_origin": "Birsay, Orkney",
            "entered_service_year": "1821",
            "service_years_range": "1821-1854",
            "highest_position": "Steersman",
            "service_history": [
                {
                    "outfit_years": "1821-1825",
                    "position": "Laborer",
                    "post": "York Factory",
                    "district": "York",
                    "hbca_ref": "B.239/g/1",
                }
            ],
            "search_file_reference": "Search File: 'ADAMS, GEORGE'",
            "hbca_references": ["B.239/g/1", "A.32/21"],
            "keystone_urls": ["https://pam.minisisinc.com/scripts/mwimain.dll/..."],
            "needs_llm_structured_review": False,
        },
    )
    assert extra.parish_of_origin == "Birsay, Orkney"
    assert extra.entered_service_year == "1821"
    assert len(extra.service_history) == 1
    assert len(extra.hbca_references) == 2
    assert extra.needs_llm_structured_review is False


def test_hbca_participant_extra_fields():
    extra = validate_participant_extra_fields(
        "HBCA",
        {
            "relationship_to_employee": "Self",
            "vital_dates_summary": "b. ca. 1796, d. 1864",
            "citations_text": "Search file; B.239/g/1",
        },
    )
    assert extra.relationship_to_employee == "Self"
    assert extra.vital_dates_summary == "b. ca. 1796, d. 1864"


def test_hbca_parse_collection_end_to_end():
    payload = {
        "collection_title": "Hudson's Bay Company Biographical Sheets",
        "sheets": [
            {
                "page_id": "adams_george.pdf",
                "document_metadata": {
                    "file_name": "adams_george.pdf",
                    "source_name": "Hudson's Bay Company Archives: Biographical Sheets",
                    "source_location": "Archives of Manitoba, Winnipeg, Manitoba, Canada",
                },
                "records": [
                    {
                        "page": "adams_george.pdf",
                        "record_number": "1",
                        "event_type": "Employment",
                        "year": "1821",
                        "event_date": "1821-1854",
                        "event_place": "York Factory",
                        "citation_details": "Search File: 'ADAMS, GEORGE'",
                        "citation_text": "B.239/g/1",
                        "review": False,
                        "continues_on_next_image": False,
                        "continues_from_previous_image": False,
                        "type_specific_fields": {
                            "parish_of_origin": "Birsay, Orkney",
                            "entered_service_year": "1821",
                            "service_years_range": "1821-1854",
                            "highest_position": "Steersman",
                            "service_history": [
                                {
                                    "outfit_years": "1821-1825",
                                    "position": "Laborer",
                                    "post": "York Factory",
                                    "district": "York",
                                    "hbca_ref": "B.239/g/1",
                                }
                            ],
                            "search_file_reference": "Search File: 'ADAMS, GEORGE'",
                            "hbca_references": ["B.239/g/1", "A.32/21"],
                            "keystone_urls": ["https://pam.minisisinc.com/..."],
                        },
                        "participants": [
                            {
                                "role_name": "Employee",
                                "std_given": "George",
                                "std_surname": "Adams",
                                "is_priest": False,
                                "sex": "M",
                                "review": False,
                                "type_specific_fields": {
                                    "relationship_to_employee": "Self",
                                    "vital_dates_summary": "b. ca. 1796, d. 1864",
                                    "citations_text": "Search file; B.239/g/1",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    collection = parse_collection(payload, document_type="HBCA")
    assert len(collection.sheets) == 1
    assert collection.sheets[0].records[0].type_specific_fields["highest_position"] == "Steersman"
