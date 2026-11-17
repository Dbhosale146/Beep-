"""Tests for normalisation: text cleaning, city aliases, the India check."""

from pipeline.normalise import (
    canonical_city,
    clean_text,
    is_india,
    make_id,
    normalise,
    normalise_one,
)


# ---- text cleaning -------------------------------------------------------

def test_clean_text_handles_greenhouse_double_escaping():
    # Greenhouse returns HTML that is itself HTML-escaped.
    assert clean_text("&lt;p&gt;Join  us&lt;/p&gt;") == "Join us"


def test_clean_text_strips_tags_and_collapses_whitespace():
    assert clean_text("<div>a</div>\n\n  <span>b</span>") == "a b"


def test_clean_text_on_empty_values():
    assert clean_text(None) == ""
    assert clean_text("") == ""


# ---- city aliases --------------------------------------------------------

def test_common_aliases_map_to_canonical_names():
    assert canonical_city("Bangalore, Karnataka, India") == "Bengaluru"
    assert canonical_city("Gurgaon") == "Gurugram"
    assert canonical_city("Bombay") == "Mumbai"
    assert canonical_city("Trivandrum") == "Thiruvananthapuram"


def test_longer_alias_wins_over_shorter_one():
    # "Navi Mumbai" must be tested before "Mumbai", and both map to Mumbai.
    assert canonical_city("Navi Mumbai") == "Mumbai"
    # "Greater Noida" must not be mistaken for something else.
    assert canonical_city("Greater Noida") == "Noida"


def test_unknown_location_returns_none():
    assert canonical_city("Reykjavik") is None
    assert canonical_city(None) is None


def test_city_match_uses_word_boundaries():
    # "Goa" must not match inside another word.
    assert canonical_city("Goalpara District") is None


# ---- India check ---------------------------------------------------------

def test_explicit_country_code_is_trusted():
    assert is_india({"country": "IN"}, None) is True
    assert is_india({"country": "India"}, None) is True


def test_explicit_foreign_country_wins_over_a_city_match():
    # A Lever job in Dubai also lists Indian offices; country must decide.
    assert is_india({"country": "AE", "raw_location": "Dubai | Mumbai"}, "Mumbai") is False


def test_falls_back_to_location_text_when_country_missing():
    # Greenhouse gives no country field at all.
    assert is_india({"raw_location": "Bengaluru, India"}, "Bengaluru") is True
    assert is_india({"raw_location": "London"}, None) is False


def test_remote_alone_is_not_enough_to_claim_india():
    assert is_india({"raw_location": "Work from home"}, "Remote") is False


# ---- ids and the full pass ----------------------------------------------

def test_id_is_stable_and_source_scoped():
    assert make_id("greenhouse", "123") == make_id("greenhouse", "123")
    assert make_id("greenhouse", "123") != make_id("lever", "123")


def test_normalise_one_produces_the_agreed_schema():
    row = {
        "source": "lever",
        "source_id": "abc",
        "company": "Paytm",
        "title": "  SDE   Intern ",
        "raw_location": "Noida, Uttar Pradesh",
        "description": "<p>Work with us</p>",
        "url": "https://jobs.lever.co/paytm/abc",
        "posted_at": "2026-11-10T00:00:00+00:00",
        "fetched_at": "2026-11-16T00:00:00+00:00",
        "departments": ["Engineering"],
    }
    out = normalise_one(row)
    assert out["title"] == "SDE Intern"
    assert out["city_guess"] == "Noida"
    assert out["description"] == "Work with us"
    assert out["department"] == "Engineering"
    assert set(out) == {
        "id", "source", "source_id", "title", "company", "raw_location",
        "city_guess", "department", "employment_type", "description", "url",
        "posted_at", "fetched_at",
    }


def test_normalise_drops_non_india_and_unlinkable_rows():
    rows = [
        {"source": "x", "source_id": "1", "title": "Intern", "url": "u1",
         "raw_location": "Pune, India"},
        {"source": "x", "source_id": "2", "title": "Intern", "url": "u2",
         "raw_location": "Berlin, Germany"},
        {"source": "x", "source_id": "3", "title": None, "url": "u3",
         "raw_location": "Pune"},
        {"source": "x", "source_id": "4", "title": "Intern", "url": None,
         "raw_location": "Pune"},
    ]
    kept, counts = normalise(rows)
    assert counts == {"input": 4, "no_title_or_url": 2, "not_india": 1, "kept": 1}
    assert kept[0]["city_guess"] == "Pune"
