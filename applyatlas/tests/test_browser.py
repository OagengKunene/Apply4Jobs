import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from applyatlas.browser import BrowserExecutor, field_key, public_host
from applyatlas.intelligence import Planner, match, render_packet


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        sock.close()


def packet_for(store, good_job):
    candidate, job = store.candidate("demo-client"), store.job(good_job)
    fit = match(candidate, job)
    selection, label = Planner().select(candidate, job, fit)
    return candidate, job, render_packet(candidate, job, fit, selection, label)


def test_real_chromium_autofills_submits_and_reads_receipt(store, good_job, tmp_path):
    app = FastAPI()
    submitted = []

    @app.get("/sandbox/apply/{identifier}", response_class=HTMLResponse)
    def form(identifier: str):
        return """<form method='post'><label>Full name<input name='name' required></label>
        <label>Email<input type='email' name='email' required></label>
        <label>Cover letter<textarea name='letter' required></textarea></label>
        <button type='submit'>Submit application</button></form>"""

    @app.post("/sandbox/apply/{identifier}", response_class=HTMLResponse)
    async def receive(identifier: str):
        submitted.append(identifier)
        return "<h1>Application received</h1>"

    candidate, job, packet = packet_for(store, good_job)
    with serve(app) as base:
        receipt = BrowserExecutor(tmp_path, sandbox_base=base).execute(job, candidate, packet, "test")
    assert receipt["status"] == "submitted", receipt
    assert receipt["demo"] is True
    assert receipt["fields_filled"] == 3
    assert submitted == ["test"]


@pytest.mark.parametrize("extra", [
    "<label>Government identity number<input name='identity' required></label>",
    "<label>Agree to terms<input type='checkbox' required></label>",
    "<label>Work authorisation<select required><option></option><option>Yes</option></select></label>",
])
def test_unknown_required_fields_stop_before_submission(store, good_job, tmp_path, extra):
    app = FastAPI()
    submitted = []

    @app.get("/sandbox/apply/{identifier}", response_class=HTMLResponse)
    def form(identifier: str):
        return "<form method='post'><label>Email<input name='email' required></label>" + extra + \
            "<button type='submit'>Submit</button></form>"

    @app.post("/sandbox/apply/{identifier}")
    def receive(identifier: str):
        submitted.append(identifier)

    candidate, job, packet = packet_for(store, good_job)
    with serve(app) as base:
        receipt = BrowserExecutor(tmp_path, sandbox_base=base).execute(job, candidate, packet, "test")
    assert receipt["status"] == "needs_attention", receipt
    assert "unanswered_fields" in receipt
    assert not submitted


def test_live_submission_default_is_off(store, good_job, tmp_path):
    candidate, job, packet = packet_for(store, good_job)
    job.source = "lever"
    job.url = "https://jobs.lever.co/example/role/apply"
    receipt = BrowserExecutor(tmp_path).execute(job, candidate, packet, "test")
    assert receipt["status"] == "needs_attention"
    assert "disabled" in receipt["reason"]


def test_field_mapping_does_not_guess_salary_or_identity():
    assert field_key("First name *") == "first_name"
    assert field_key("Resume / CV") == "resume"
    assert field_key("Desired salary") is None
    assert field_key("Government identity number") is None


def test_loopback_and_private_networks_rejected():
    assert not public_host("127.0.0.1")
    assert not public_host("localhost")
    assert not public_host("10.0.0.1")
