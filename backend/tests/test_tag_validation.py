"""Tests for tag validation, the schema, the cache key, and the fresher rules.

No network: validate() and build_schema() are pure, which is why they are
separate functions rather than inlined into the API call.
"""

from pipeline.fresher import looks_fresher, min_years_required
from pipeline.tag import build_schema, cache_key, validate

ROLES = ["Software Engineering", "Design (UI/UX)", "Other"]
CITIES = ["Bengaluru", "Mumbai", "Pan India", "Remote", "Multiple"]


def ok(index=0, role="Software Engineering", city="Bengaluru", fresher=True):
    return {"i": index, "r": role, "c": city, "f": fresher}


# ---- the schema we send -------------------------------------------------

def test_schema_pins_roles_and_cities_as_enums():
    schema = build_schema(ROLES, CITIES)
    item = schema["properties"]["tags"]["items"]
    assert item["properties"]["r"]["enum"] == ROLES
    assert item["properties"]["c"]["enum"] == CITIES
    assert item["required"] == ["i", "r", "c", "f"]


# ---- happy path ---------------------------------------------------------

def test_valid_response_passes_with_no_problems():
    valid, problems = validate({"tags": [ok(0), ok(1, city="Mumbai")]}, 2, ROLES, CITIES)
    assert problems == []
    assert valid[0] == {"role": "Software Engineering", "city": "Bengaluru", "is_fresher": True}
    assert valid[1]["city"] == "Mumbai"


# ---- rejections ---------------------------------------------------------

def test_role_outside_the_taxonomy_is_rejected():
    valid, problems = validate({"tags": [ok(role="Astronaut")]}, 1, ROLES, CITIES)
    assert valid == {}
    assert any("role not in taxonomy" in p for p in problems)


def test_city_outside_the_taxonomy_is_rejected():
    # The model answering "Bangalore" instead of the canonical "Bengaluru"
    # is exactly the failure this catches.
    valid, problems = validate({"tags": [ok(city="Bangalore")]}, 1, ROLES, CITIES)
    assert valid == {}
    assert any("city not in taxonomy" in p for p in problems)


def test_non_boolean_is_fresher_is_rejected():
    valid, problems = validate({"tags": [ok(fresher="yes")]}, 1, ROLES, CITIES)
    assert valid == {}
    assert any("is_fresher not a bool" in p for p in problems)


def test_index_out_of_range_is_rejected():
    valid, problems = validate({"tags": [ok(index=7)]}, 2, ROLES, CITIES)
    assert valid == {}
    assert any("index out of range" in p for p in problems)


def test_missing_post_is_reported():
    valid, problems = validate({"tags": [ok(0)]}, 3, ROLES, CITIES)
    assert set(valid) == {0}
    assert any("missing indexes: [1, 2]" in p for p in problems)


def test_garbage_shapes_do_not_raise():
    for payload in ({}, {"tags": "nope"}, [], None, {"tags": ["x"]}):
        valid, problems = validate(payload, 1, ROLES, CITIES)
        assert valid == {}
        assert problems


def test_good_rows_are_kept_even_when_a_sibling_is_bad():
    # A partially valid batch should not throw away the valid answers.
    payload = {"tags": [ok(0), ok(1, role="Astronaut")]}
    valid, problems = validate(payload, 2, ROLES, CITIES)
    assert set(valid) == {0}
    assert problems


# ---- cache key ----------------------------------------------------------

def test_cache_key_is_stable_for_identical_content():
    post = {"title": "SDE Intern", "company": "Acme", "raw_location": "Pune",
            "description": "work"}
    assert cache_key(post) == cache_key(dict(post))


def test_cache_key_changes_when_content_changes():
    base = {"title": "SDE Intern", "company": "Acme", "raw_location": "Pune",
            "description": "work"}
    changed = dict(base, raw_location="Mumbai")
    assert cache_key(base) != cache_key(changed)


# ---- fresher rules ------------------------------------------------------

def test_substring_intern_does_not_leak_a_senior_role():
    # The phase-1 bug: "intern" is a substring of "Internal".
    keep, reason = looks_fresher({"title": "Senior Internal Auditor"})
    assert keep is False
    assert reason == "title_negative:senior"


def test_internal_audit_without_senior_is_still_not_an_internship():
    keep, _ = looks_fresher({"title": "Internal Audit Associate", "description": ""})
    assert keep is False


def test_real_internship_is_kept():
    keep, reason = looks_fresher({"title": "Software Engineer Intern"})
    assert keep is True
    assert reason == "title_positive:intern"


def test_explicit_employment_type_beats_a_vague_title():
    keep, reason = looks_fresher({"title": "Analyst", "employment_type": "Intern"})
    assert keep is True
    assert reason == "employment_type:intern"


def test_zero_to_one_years_in_the_description_is_kept():
    keep, reason = looks_fresher({"title": "Analyst", "description": "0-1 years experience"})
    assert keep is True
    assert reason.startswith("years<=1")


def test_three_plus_years_is_dropped():
    keep, reason = looks_fresher({"title": "Analyst", "description": "3+ years required"})
    assert keep is False
    assert reason == "years_too_high:3"


def test_lowest_stated_year_count_wins():
    assert min_years_required("1 to 3 years, 5 years preferred") == 1
    assert min_years_required("minimum 2 years") == 2
    assert min_years_required("no numbers here") is None
