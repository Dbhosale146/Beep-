"""No-network test for the Greenhouse record shaping."""

from pipeline.sources.greenhouse import to_raw

# Trimmed from a real boards-api.greenhouse.io response (databricks, 2026-11-16).
SAMPLE = {
    "id": 7891234,
    "internal_job_id": 123,
    "title": "Software Engineer Intern (2027)",
    "updated_at": "2026-11-10T09:12:00-05:00",
    "requisition_id": "R-4321",
    "location": {"name": "Bengaluru, India"},
    "absolute_url": "https://boards.greenhouse.io/databricks/jobs/7891234",
    "content": "&lt;p&gt;Join us&lt;/p&gt;",
    "departments": [{"id": 1, "name": "Engineering"}],
    "offices": [{"id": 2, "name": "Bengaluru"}],
}


def test_maps_every_common_field():
    row = to_raw(SAMPLE, "Databricks", "2026-11-16T00:00:00+00:00")
    assert row["source"] == "greenhouse"
    assert row["source_id"] == "7891234"        # always a string
    assert row["company"] == "Databricks"       # display name, not the token
    assert row["title"] == "Software Engineer Intern (2027)"
    assert row["raw_location"] == "Bengaluru, India"
    assert row["url"].endswith("/7891234")
    assert row["posted_at"] == "2026-11-10T09:12:00-05:00"
    assert row["fetched_at"] == "2026-11-16T00:00:00+00:00"
    assert row["departments"] == ["Engineering"]
    assert row["offices"] == ["Bengaluru"]


def test_missing_fields_become_none_not_crash():
    row = to_raw({"id": 5}, "Acme", "now")
    assert row["source_id"] == "5"
    assert row["title"] is None
    assert row["raw_location"] is None          # location object absent
    assert row["departments"] == []             # None -> empty list
    assert row["offices"] == []
