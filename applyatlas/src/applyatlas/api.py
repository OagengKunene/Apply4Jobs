from __future__ import annotations

import hmac
import os
import secrets
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .browser import BrowserExecutor
from .connectors import discover
from .demo import seed
from .documents import resume_pdf
from .graph import Engine
from .intelligence import match
from .models import Approval, Candidate, DiscoveryRequest, Job, RunRequest
from .store import Store


class Outcome(BaseModel):
    stage: Literal["pending", "interview", "offer", "rejected", "withdrawn"]


def owner_token(root):
    if token := os.getenv("APPLYATLAS_API_TOKEN"):
        if len(token) < 24:
            raise ValueError("Use an API token of at least 24 characters")
        return token
    path = root / "owner-token.txt"
    if not path.exists():
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    return path.read_text().strip()


def create_app(data_dir=None, executor=None, planner=None):
    root = Path(data_dir or os.getenv("APPLYATLAS_DATA_DIR", "./data"))
    store = Store(root)
    token = owner_token(root)
    base = f"http://127.0.0.1:{os.getenv('APPLYATLAS_PORT', '8000')}"
    executor = executor or BrowserExecutor(root, sandbox_base=base)
    engine = Engine(store, executor, planner=planner)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.close()

    app = FastAPI(title="ApplyAtlas", version=__version__, lifespan=lifespan,
                  description="Local operator API. Use Authorization: Bearer <owner token>.")
    app.state.store, app.state.engine = store, engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver", "[::1]"])

    @app.middleware("http")
    async def access_control(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not hmac.compare_digest(bearer, token):
                return JSONResponse({"detail": "Owner token required"}, status_code=401)
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
                return JSONResponse({"detail": "Cross-origin API access rejected"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/overview")
    def overview():
        apps = store.applications()
        return {"jobs": len(store.jobs()), "clients": len(store.candidates()),
                "applications": len(apps), "review": sum(a["status"] == "review" for a in apps),
                "submitted": sum(a["status"] == "submitted" for a in apps),
                "audit_valid": store.verify_chain(), "insights": store.insights(),
                "llm_enabled": engine.planner.enabled,
                "live_submit": os.getenv("APPLYATLAS_LIVE_SUBMIT", "false").lower() == "true"}

    @app.post("/api/demo")
    def demo():
        return {"candidate_id": seed(store)}

    @app.get("/api/candidates")
    def candidates():
        return store.candidates()

    @app.post("/api/candidates")
    def save_candidate(candidate: Candidate):
        store.save_candidate(candidate)
        return candidate

    @app.get("/api/jobs")
    def jobs(candidate_id: str | None = None):
        result = store.jobs()
        if candidate_id:
            candidate = store.candidate(candidate_id)
            for job in result:
                job["match"] = match(candidate, Job.model_validate({k: v for k, v in job.items() if k != "id"}))
            result.sort(key=lambda j: j["match"]["score"], reverse=True)
        return result

    @app.post("/api/jobs")
    def add_job(job: Job):
        # Demo source can only be seeded by the explicit fictional dataset endpoint.
        if job.source == "demo":
            raise HTTPException(400, "Use the demo endpoint for fictional jobs")
        store.save_job(job)
        return {"id": job.id}

    @app.post("/api/discover")
    def discovery(request: DiscoveryRequest):
        try:
            jobs = discover(request)
        except ValueError:
            raise
        except Exception as exc:
            raise HTTPException(502, f"Source unavailable ({type(exc).__name__}); verify board identifier") from exc
        inserted = sum(store.save_job(j) for j in jobs)
        store.event(None, "discovery", f"{request.source}: {len(jobs)} found, {inserted} new")
        return {"found": len(jobs), "new": inserted}

    def process(candidate_id, identifiers):
        for identifier in identifiers:
            try:
                engine.run(candidate_id, identifier)
            except Exception as exc:
                application_id = store.create_application(candidate_id, identifier)
                store.update(application_id, status="needs_attention", receipt={"reason": type(exc).__name__})
                store.event(application_id, "error", type(exc).__name__)

    @app.post("/api/run", status_code=202)
    def run(request: RunRequest, background: BackgroundTasks):
        store.candidate(request.candidate_id)
        for identifier in request.job_ids:
            store.job(identifier)
        ids = [store.create_application(request.candidate_id, identifier) for identifier in request.job_ids]
        background.add_task(process, request.candidate_id, request.job_ids)
        return {"application_ids": ids}

    @app.get("/api/applications")
    def applications():
        return store.applications()

    @app.get("/api/applications/{identifier}")
    def application(identifier: str):
        return store.application(identifier)

    @app.post("/api/applications/{identifier}/review")
    def review(identifier: str, approval: Approval):
        return engine.approve(identifier, approval)

    @app.get("/api/applications/{identifier}/resume.pdf")
    def resume(identifier: str):
        packet = store.application(identifier)["packet"]
        if not packet:
            raise HTTPException(409, "Packet not generated")
        return Response(resume_pdf(packet), media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="resume.pdf"'})

    @app.post("/api/applications/{identifier}/outcome")
    def outcome(identifier: str, result: Outcome):
        store.application(identifier)
        store.outcome(identifier, result.stage)
        store.event(identifier, "outcome", result.stage)
        return {"saved": True}

    @app.get("/api/events")
    def events():
        rows = store.events()
        return {"valid": store.verify_chain(), "events": rows[-100:]}

    def sandbox_app(identifier):
        record = store.application(identifier)
        if store.job(record["job_id"]).source != "demo" or record["status"] != "submitting":
            raise HTTPException(404)
        return record

    @app.get("/sandbox/apply/{identifier}", response_class=HTMLResponse)
    def sandbox_form(identifier: str):
        sandbox_app(identifier)
        return f"""<!doctype html><html lang='en'><head><title>Fictional employer sandbox</title>
        <link rel='stylesheet' href='/static/style.css'></head><body><main class='sandbox'>
        <span class='eyebrow'>APPLYATLAS TEST EMPLOYER</span><h1>Application sandbox</h1>
        <p>This form never contacts an employer.</p><form action='/sandbox/apply/{escape(identifier)}' method='post'>
        <label>Full name<input name='name' required></label>
        <label>Email<input type='email' name='email' required></label>
        <label>Phone<input name='phone'></label>
        <label>Cover letter<textarea name='letter' required></textarea></label>
        <button type='submit'>Submit application</button></form></main></body></html>"""

    @app.post("/sandbox/apply/{identifier}", response_class=HTMLResponse)
    def sandbox_submit(identifier: str, name: str = Form(), email: str = Form(), letter: str = Form()):
        sandbox_app(identifier)
        # Do not store PII a second time; only the workflow receipt persists.
        return "<!doctype html><html><body><h1>Application received</h1><p>Fictional sandbox only.</p></body></html>"

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (static / "index.html").read_text()

    return app
