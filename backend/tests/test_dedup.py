"""Tests for the three dedup layers, including which layer catches what."""

from pipeline.dedup import dedup, layer1_exact, layer2_hash, layer3_fuzzy


def post(**kwargs):
    base = {
        "source": "adzuna",
        "source_id": "1",
        "company": "Acme",
        "title": "SDE Intern",
        "city_guess": "Bengaluru",
        "url": "https://example.com/1",
    }
    base.update(kwargs)
    return base


# ---- layer 1: exact ------------------------------------------------------

def test_layer1_removes_repeat_of_same_source_id():
    # One Adzuna job returned by several of our search queries.
    out = layer1_exact([post(), post()])
    assert len(out) == 1


def test_layer1_removes_same_url_with_different_id():
    out = layer1_exact([post(source_id="1"), post(source_id="2")])
    assert len(out) == 1


def test_layer1_ignores_query_strings_and_trailing_slashes():
    a = post(source_id="1", url="https://example.com/job/5")
    b = post(source_id="2", url="https://example.com/job/5/?utm_source=api")
    assert len(layer1_exact([a, b])) == 1


def test_layer1_keeps_genuinely_different_jobs():
    a = post(source_id="1", url="https://example.com/1")
    b = post(source_id="2", url="https://example.com/2", title="QA Intern")
    assert len(layer1_exact([a, b])) == 2


# ---- layer 2: hash ------------------------------------------------------

def test_layer2_catches_same_job_from_two_sources():
    # Same role on the company's own board and in the Adzuna index: different
    # ids, different urls, so layer 1 cannot see it.
    a = post(source="greenhouse", source_id="g1", url="https://boards/x")
    b = post(source="adzuna", source_id="a1", url="https://adzuna/y")
    assert len(layer2_hash([a, b])) == 1


def test_layer2_normalises_punctuation_and_case():
    a = post(source_id="1", url="u1", company="Acme Pvt. Ltd")
    b = post(source_id="2", url="u2", company="ACME PVT LTD")
    assert len(layer2_hash([a, b])) == 1


def test_layer2_keeps_same_title_in_different_cities():
    a = post(source_id="1", url="u1", city_guess="Bengaluru")
    b = post(source_id="2", url="u2", city_guess="Pune")
    assert len(layer2_hash([a, b])) == 2


# ---- layer 3: fuzzy ------------------------------------------------------

def test_layer3_catches_near_identical_titles_at_one_company():
    a = post(source_id="1", url="u1", title="SDE Intern")
    b = post(source_id="2", url="u2", title="SDE Intern (2027 Batch)")
    assert len(layer3_fuzzy([a, b])) == 1


def test_layer3_does_not_merge_across_companies():
    a = post(source_id="1", url="u1", company="Acme", title="Backend Intern")
    b = post(source_id="2", url="u2", company="Globex", title="Backend Intern")
    assert len(layer3_fuzzy([a, b])) == 2


def test_layer3_will_not_let_a_bare_intern_posting_swallow_the_list():
    # "Intern" is a token-subset of every intern title, so without the
    # minimum-token guard this one row would absorb the whole company.
    rows = [
        post(source_id="1", url="u1", title="Intern"),
        post(source_id="2", url="u2", title="Backend Engineering Intern"),
        post(source_id="3", url="u3", title="Marketing Intern"),
    ]
    assert len(layer3_fuzzy(rows)) == 3


def test_layer3_ignores_word_order():
    a = post(source_id="1", url="u1", title="Software Engineer Intern")
    b = post(source_id="2", url="u2", title="Intern Software Engineer")
    assert len(layer3_fuzzy([a, b])) == 1


def test_layer3_keeps_clearly_different_roles():
    a = post(source_id="1", url="u1", title="Backend Engineering Intern")
    b = post(source_id="2", url="u2", title="Marketing Intern")
    assert len(layer3_fuzzy([a, b])) == 2


# ---- all three together -------------------------------------------------

def test_dedup_reports_what_each_layer_removed():
    posts = [
        post(source_id="1", url="u1"),                      # kept
        post(source_id="1", url="u1"),                      # layer 1
        post(source_id="2", url="u2"),                      # layer 2 (same co/title/city)
        post(source_id="3", url="u3", title="SDE Intern 2027"),  # layer 3 (fuzzy)
        post(source_id="4", url="u4", title="Design Intern"),    # kept
    ]
    kept, counts = dedup(posts)
    assert counts["input"] == 5
    assert counts["removed_layer1_exact"] == 1
    assert counts["removed_layer2_hash"] == 1
    assert counts["removed_layer3_fuzzy"] == 1
    assert counts["kept"] == 2
    assert len(kept) == 2


def test_first_row_wins_and_order_is_preserved():
    posts = [
        post(source_id="1", url="u1", title="Alpha Intern"),
        post(source_id="2", url="u2", title="Beta Intern"),
        post(source_id="1", url="u1", title="Alpha Intern"),
    ]
    kept, _ = dedup(posts)
    assert [p["title"] for p in kept] == ["Alpha Intern", "Beta Intern"]
