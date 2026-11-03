import httpx

from applyatlas.connectors import discover
from applyatlas.models import DiscoveryRequest


def test_greenhouse_payload_mapping(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            assert url == "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
            return httpx.Response(200, request=httpx.Request("GET", url), json={"jobs": [{
                "id": 1, "title": "Data Engineer", "location": {"name": "Remote"},
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
                "content": "<p>Build Python and SQL pipelines. 3 years of experience.</p>"}]})
    monkeypatch.setattr("applyatlas.connectors.httpx.Client", Client)
    jobs = discover(DiscoveryRequest(source="greenhouse", board="example", query="data"))
    assert jobs[0].min_years == 3
    assert jobs[0].required_skills == ["python", "sql"]
    assert "<p>" not in jobs[0].description


def test_lever_payload_mapping(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request("GET", url), json=[{
                "text": "Python Developer", "categories": {"location": "Remote"},
                "descriptionPlain": "Build production services with Python.",
                "lists": [{"content": "<li>Docker and SQL experience</li>"}],
                "applyUrl": "https://jobs.lever.co/example/role/apply"}])
    monkeypatch.setattr("applyatlas.connectors.httpx.Client", Client)
    jobs = discover(DiscoveryRequest(source="lever", board="example", query="python"))
    assert jobs[0].source == "lever"
    assert set(jobs[0].required_skills) == {"python", "docker", "sql"}
