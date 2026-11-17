"""Tests for the HTTP API.

These never touch the network and never read the real data/jobs.json. A small
fixture is written to a temp file and api.main.data_path is pointed at it, so
the numbers asserted here cannot drift when a pipeline run changes the real
dataset.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api import main


def iso(days_ago, suffix="Z"):
    """An ISO timestamp N days in the past, in one of the three real shapes."""
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    if suffix == "Z":
        return when.strftime("%Y-%m-%dT%H:%M:%SZ")
    if suffix == "offset":
        # The same instant written with an explicit +05:30 offset, which is
        # what some source feeds send. Sorted as a string this would land in
        # the wrong place, which is exactly what the parsing is for.
        return when.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
    return when.isoformat()  # microseconds + +00:00


def job(job_id, title, company, role, city, days_ago, source="adzuna", suffix="Z"):
    return {
        "id": job_id,
        "title": title,
        "company": company,
        "role": role,
        "city": city,
        "raw_location": f"{city}, India",
        "source": source,
        "url": f"https://example.test/{job_id}",
        "posted_at": iso(days_ago, suffix),
        "description": "D" * 900,
        "is_fresher": True,
    }


FIXTURE = [
    job("a1", "Software Intern", "Acme", "Software Engineering", "Pune", 0),
    job("a2", "SDE Intern", "Acme", "Software Engineering", "Bengaluru", 2, suffix="offset"),
    job("a3", "Data Analyst Trainee", "Borealis", "Data Science", "Bengaluru", 5),
    job("a4", "Marketing Intern", "Cyclo", "Marketing & Growth", "Mumbai", 10, source="lever"),
    job("a5", "Support Associate", "Delta", "Operations & Support", "Pune", 40),
    job("a6", "Design Intern", "Acme", "Design", "Remote", 60, source="greenhouse", suffix="micro"),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient whose API reads FIXTURE instead of the real data files."""
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps(FIXTURE), encoding="utf-8")
    meta_file = tmp_path / "run_meta.json"
    meta_file.write_text(json.dumps({"last_refreshed": "2026-11-17T00:00:00Z"}), encoding="utf-8")

    def fake_data_path(key):
        return {"jobs": jobs_file, "run_meta": meta_file}[key]

    monkeypatch.setattr(main, "data_path", fake_data_path)
    # The cache is module-level and keyed on mtime, so clear it between tests.
    main._cache.update(jobs=[], by_id={}, meta={}, mtime=None, loaded_at=None)
    return TestClient(main.app)


# ---------------------------------------------------------------- basics

def test_health_reports_the_loaded_count(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["jobs"] == 6


def test_default_listing_returns_everything_on_one_page(client):
    body = client.get("/api/jobs").json()
    assert body["total"] == 6
    assert body["total_unfiltered"] == 6
    assert body["pages"] == 1
    assert len(body["jobs"]) == 6


def test_internal_fields_never_reach_the_client(client):
    body = client.get("/api/jobs").json()
    for row in body["jobs"]:
        assert not [k for k in row if k.startswith("_")], row


def test_list_sends_a_snippet_and_detail_sends_the_full_description(client):
    listed = client.get("/api/jobs").json()["jobs"][0]
    assert len(listed["description"]) <= main.SNIPPET_CHARS + 3
    assert listed["truncated"] is True

    full = client.get(f"/api/jobs/{listed['id']}").json()
    assert len(full["description"]) == 900
    assert "truncated" not in full


# ---------------------------------------------------------------- filtering

def test_role_filter_is_exact(client):
    body = client.get("/api/jobs", params={"role": "Software Engineering"}).json()
    assert body["total"] == 2
    assert {j["id"] for j in body["jobs"]} == {"a1", "a2"}


def test_city_filter_is_exact(client):
    body = client.get("/api/jobs", params={"city": "Pune"}).json()
    assert {j["id"] for j in body["jobs"]} == {"a1", "a5"}


def test_role_and_city_combine(client):
    body = client.get(
        "/api/jobs", params={"role": "Software Engineering", "city": "Bengaluru"}
    ).json()
    assert body["total"] == 1
    assert body["jobs"][0]["id"] == "a2"


def test_source_filter(client):
    body = client.get("/api/jobs", params={"source": "lever"}).json()
    assert body["total"] == 1
    assert body["jobs"][0]["id"] == "a4"


def test_search_words_match_in_any_order(client):
    forward = client.get("/api/jobs", params={"q": "intern acme"}).json()
    reverse = client.get("/api/jobs", params={"q": "acme intern"}).json()
    assert {j["id"] for j in forward["jobs"]} == {"a1", "a2", "a6"}
    assert forward["total"] == reverse["total"]


def test_search_covers_location_but_not_description(client):
    assert client.get("/api/jobs", params={"q": "mumbai"}).json()["total"] == 1
    # Every fixture description is a wall of "D". If descriptions were
    # searched, this would match all six instead of none.
    assert client.get("/api/jobs", params={"q": "DDDDDDDD"}).json()["total"] == 0


def test_search_that_matches_nothing_returns_an_empty_page_not_an_error(client):
    body = client.get("/api/jobs", params={"q": "quantum blacksmith"}).json()
    assert body["total"] == 0
    assert body["jobs"] == []
    assert body["pages"] == 1


# ---------------------------------------------------------------- freshness

def test_posted_within_days_filters_by_real_dates(client):
    assert client.get("/api/jobs", params={"posted_within_days": 1}).json()["total"] == 1
    assert client.get("/api/jobs", params={"posted_within_days": 7}).json()["total"] == 3
    assert client.get("/api/jobs", params={"posted_within_days": 30}).json()["total"] == 4
    assert client.get("/api/jobs", params={"posted_within_days": 0}).json()["total"] == 6


# ---------------------------------------------------------------- sorting

def test_sort_recent_is_newest_first_across_mixed_timestamp_formats(client):
    ids = [j["id"] for j in client.get("/api/jobs", params={"sort": "recent"}).json()["jobs"]]
    assert ids == ["a1", "a2", "a3", "a4", "a5", "a6"]


def test_sort_oldest_is_the_reverse(client):
    ids = [j["id"] for j in client.get("/api/jobs", params={"sort": "oldest"}).json()["jobs"]]
    assert ids == ["a6", "a5", "a4", "a3", "a2", "a1"]


def test_sort_company_is_alphabetical(client):
    companies = [
        j["company"] for j in client.get("/api/jobs", params={"sort": "company"}).json()["jobs"]
    ]
    assert companies == sorted(companies)


def test_an_unknown_sort_is_rejected(client):
    assert client.get("/api/jobs", params={"sort": "banana"}).status_code == 422


# ---------------------------------------------------------------- paging

def test_pages_do_not_overlap_and_cover_everything(client):
    seen = []
    for page in (1, 2, 3):
        body = client.get("/api/jobs", params={"page": page, "page_size": 2}).json()
        assert body["pages"] == 3
        seen += [j["id"] for j in body["jobs"]]
    assert sorted(seen) == ["a1", "a2", "a3", "a4", "a5", "a6"]


def test_a_page_past_the_end_is_empty_rather_than_an_error(client):
    body = client.get("/api/jobs", params={"page": 99}).json()
    assert body["jobs"] == []
    assert body["total"] == 6


def test_page_zero_is_rejected(client):
    assert client.get("/api/jobs", params={"page": 0}).status_code == 422


# ---------------------------------------------------------------- facets

def test_facets_ignore_their_own_dimension(client):
    """Picking a city must not collapse the city menu to one option.

    This is the behaviour that makes the filters usable: the city counts are
    computed as if no city were selected, so you can still see -- and switch
    to -- the other cities.
    """
    body = client.get("/api/jobs", params={"city": "Pune"}).json()
    assert body["total"] == 2
    # Cities menu still offers all four, because it ignores the city filter.
    assert set(body["facets"]["cities"]) == {"Pune", "Bengaluru", "Mumbai", "Remote"}
    # Roles menu does respect the city filter, so it shows only Pune's roles.
    assert set(body["facets"]["roles"]) == {"Software Engineering", "Operations & Support"}


def test_facet_counts_respect_the_text_search(client):
    body = client.get("/api/jobs", params={"q": "acme"}).json()
    assert body["facets"]["cities"] == {"Bengaluru": 1, "Pune": 1, "Remote": 1}


def test_facets_are_ordered_biggest_first(client):
    counts = list(client.get("/api/jobs").json()["facets"]["cities"].values())
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------- errors

def test_unknown_job_id_is_404(client):
    response = client.get("/api/jobs/nope")
    assert response.status_code == 404
    assert "no job" in response.json()["detail"]


def test_missing_data_file_explains_what_to_run(tmp_path, monkeypatch):
    missing = tmp_path / "gone.json"
    monkeypatch.setattr(main, "data_path", lambda key: missing)
    main._cache.update(jobs=[], by_id={}, meta={}, mtime=None, loaded_at=None)

    response = TestClient(main.app, raise_server_exceptions=False).get("/api/jobs")
    assert response.status_code == 503
    assert "pipeline.run" in response.json()["detail"]


def test_a_broken_run_meta_does_not_take_the_api_down(tmp_path, monkeypatch):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps(FIXTURE), encoding="utf-8")
    meta_file = tmp_path / "run_meta.json"
    meta_file.write_text("{not json", encoding="utf-8")

    monkeypatch.setattr(
        main, "data_path", lambda key: {"jobs": jobs_file, "run_meta": meta_file}[key]
    )
    main._cache.update(jobs=[], by_id={}, meta={}, mtime=None, loaded_at=None)

    client = TestClient(main.app)
    assert client.get("/api/jobs").json()["total"] == 6
    assert client.get("/api/meta").json() == {}


def test_source_facet_ignores_its_own_dimension(client):
    """Selecting a source must not collapse the source menu to that one value.

    Same rule as role and city: without this you could pick "lever" and then
    have no way to switch to another source from the menu.
    """
    body = client.get("/api/jobs", params={"source": "lever"}).json()
    assert body["total"] == 1
    assert set(body["facets"]["sources"]) == {"adzuna", "lever", "greenhouse"}
