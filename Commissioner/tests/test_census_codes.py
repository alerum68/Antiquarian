from Commissioner import census_codes


def test_decode_occupation_code():
    assert census_codes.decode(1950, "Item_C_Occupation", "100") == "Farmers (owners and tenants)"


def test_decode_industry_code():
    assert census_codes.decode(1950, "Item_C_Industry", "105") == "Agriculture"


def test_decode_class_of_worker_code():
    assert census_codes.decode(1950, "Item_C_Class_Of_Worker", "3") == "In own business"


def test_decode_education_code():
    assert census_codes.decode(1950, "Education", "S8") == "8th grade"


def test_decode_race_code():
    assert census_codes.decode(1950, "Race", "W") == "White"


def test_decode_returns_none_for_unknown_code():
    assert census_codes.decode(1950, "Item_C_Occupation", "999999") is None


def test_decode_returns_none_for_unknown_item():
    assert census_codes.decode(1950, "NotARealItem", "100") is None


def test_decode_returns_none_for_unknown_year():
    assert census_codes.decode(1899, "Item_C_Occupation", "100") is None


def test_decode_returns_none_for_falsy_code():
    assert census_codes.decode(1950, "Item_C_Occupation", "") is None
    assert census_codes.decode(1950, "Item_C_Occupation", None) is None


def test_decode_birthplace_us_code_resolves_directly():
    place, is_foreign = census_codes.decode_birthplace(1950, "091")
    assert place == "Washington"
    assert is_foreign is False


def test_decode_birthplace_foreign_code_strips_citizenship_prefix():
    place, is_foreign = census_codes.decode_birthplace(1950, "161")
    assert place == "Canada -- English"
    assert is_foreign is True


def test_decode_birthplace_foreign_code_with_unspecified_citizenship_prefix():
    place, is_foreign = census_codes.decode_birthplace(1950, "V39")
    assert place == "Iceland"
    assert is_foreign is True


def test_decode_birthplace_unresolvable_code_returns_none_not_foreign():
    place, is_foreign = census_codes.decode_birthplace(1950, "999")
    assert place is None
    assert is_foreign is False


def test_decode_birthplace_falsy_code():
    place, is_foreign = census_codes.decode_birthplace(1950, "")
    assert place is None
    assert is_foreign is False
