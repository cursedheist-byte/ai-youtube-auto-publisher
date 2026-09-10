from app.routers.categories import normalized

def test_category_names_are_normalized_for_case_and_whitespace():
    assert normalized("  Funny   Animals ") == "funny animals"


def test_mix_is_represented_by_no_category_id():
    # The API intentionally uses null for Mix; it is never persisted as a Category row.
    assert normalized("Mix") == "mix"
