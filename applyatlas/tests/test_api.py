from fastapi.testclient import TestClient

from applyatlas.api import create_app
from applyatlas.models import Job


def test_owner_auth_and_origin_boundary(tmp_path, executor):
    app = create_app(tmp_path, executor=executor)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/candidates").status_code == 401
        assert client.post("/api/demo").status_code == 401
        headers = {"Authorization": "Bearer " + (tmp_path / "owner-token.txt").read_text()}
        assert client.post("/api/demo", headers={**headers, "Origin": "https://malicious.invalid"}).status_code == 403
        assert client.post("/api/demo", headers=headers).status_code == 200
        assert client.get("/api/candidates", headers=headers).json()[0]["name"] == "Alex Morgan"
        assert client.get("/api/candidates", headers=headers).headers["cache-control"] == "no-store"


def test_complete_api_review_flow(tmp_path, executor):
    app = create_app(tmp_path, executor=executor)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + (tmp_path / "owner-token.txt").read_text()}
        client.post("/api/demo", headers=headers)
        jobs = client.get("/api/jobs?candidate_id=demo-client", headers=headers).json()
        job = next(j for j in jobs if j["title"] == "Data Engineer")
        result = client.post("/api/run", json={"candidate_id": "demo-client", "job_ids": [job["id"]]}, headers=headers)
        assert result.status_code == 202
        identifier = result.json()["application_ids"][0]
        packet = client.get("/api/applications/" + identifier, headers=headers).json()
        assert packet["status"] == "review"
        assert client.get(f"/api/applications/{identifier}/resume.pdf", headers=headers).content.startswith(b"%PDF")
        submitted = client.post(f"/api/applications/{identifier}/review", headers=headers,
                                json={"packet_hash": packet["packet_hash"], "approve": True})
        assert submitted.json()["status"] == "submitted"
        assert client.post(f"/api/applications/{identifier}/outcome", headers=headers,
                           json={"stage": "interview"}).status_code == 200
        overview = client.get("/api/overview", headers=headers).json()
        assert overview["insights"][0]["smoothed_response_rate"] == 0.667


def test_demo_source_cannot_be_forged_by_job_import(tmp_path, executor, store, good_job):
    app = create_app(tmp_path / "separate", executor=executor)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + (tmp_path / "separate" / "owner-token.txt").read_text()}
        result = client.post("/api/jobs", json=store.job(good_job).model_dump(mode="json"), headers=headers)
        assert result.status_code == 400


def test_discovery_api_uses_adapter_and_dedupes(tmp_path, executor, monkeypatch):
    job = Job(title="Python Engineer", company="Example", location="Remote", description="Build Python services.",
              url="https://jobs.lever.co/example/role", source="lever", required_skills=["Python"])
    monkeypatch.setattr("applyatlas.api.discover", lambda request: [job, job])
    app = create_app(tmp_path, executor=executor)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + (tmp_path / "owner-token.txt").read_text()}
        result = client.post("/api/discover", json={"source": "lever", "board": "example"}, headers=headers).json()
        assert result == {"found": 2, "new": 1}
