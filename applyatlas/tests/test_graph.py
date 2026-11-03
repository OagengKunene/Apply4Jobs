from datetime import datetime, timedelta, timezone

import pytest

from applyatlas.graph import Engine
from applyatlas.models import Approval, Policy, Selection


def approve(app):
    return Approval(packet_hash=app["packet_hash"], approve=True)


def test_durable_review_survives_restart(store, executor, good_job):
    first = Engine(store, executor)
    app = first.run("demo-client", good_job)
    assert app["status"] == "review"
    assert not executor.calls
    first.close()
    second = Engine(store, executor)
    try:
        result = second.approve(app["id"], approve(app))
        assert result["status"] == "submitted"
        assert executor.calls == [app["id"]]
        assert store.verify_chain()
    finally:
        second.close()


def test_duplicate_run_and_double_approval_do_not_submit_twice(engine, executor, good_job):
    app = engine.run("demo-client", good_job)
    engine.approve(app["id"], approve(app))
    repeated = engine.run("demo-client", good_job)
    assert repeated["id"] == app["id"]
    assert len(executor.calls) == 1
    with pytest.raises(ValueError):
        engine.approve(app["id"], approve(app))


def test_stale_document_hash_rejected(engine, good_job):
    app = engine.run("demo-client", good_job)
    with pytest.raises(ValueError, match="hash"):
        engine.approve(app["id"], Approval(packet_hash="old", approve=True))


def test_profile_edit_invalidates_approval(store, engine, executor, good_job):
    app = engine.run("demo-client", good_job)
    candidate = store.candidate("demo-client")
    candidate.phone = "+27 changed"
    store.save_candidate(candidate)
    result = engine.approve(app["id"], approve(app))
    assert result["status"] == "needs_attention"
    assert "changed" in result["receipt"]["reason"]
    assert not executor.calls


def test_job_edit_invalidates_approval(store, engine, executor, good_job):
    app = engine.run("demo-client", good_job)
    job = store.job(good_job)
    job.description += " Job description changed."
    store.save_job(job)
    result = engine.approve(app["id"], approve(app))
    assert result["status"] == "needs_attention"
    assert not executor.calls


def test_rejection_never_calls_browser(engine, executor, good_job):
    app = engine.run("demo-client", good_job)
    result = engine.approve(app["id"], Approval(packet_hash=app["packet_hash"], approve=False))
    assert result["status"] == "rejected"
    assert not executor.calls


def test_low_fit_is_skipped(store, engine, executor):
    job_id = next(j["id"] for j in store.jobs() if j["title"] == "Senior Platform Engineer")
    result = engine.run("demo-client", job_id)
    assert result["status"] == "skipped"
    assert not executor.calls


def set_autopilot(store, good_job, expired=False):
    candidate = store.candidate("demo-client")
    job = store.job(good_job)
    candidate.policy = Policy(mode="autopilot", min_score=75, daily_limit=2,
                              allowed_companies=[job.company], allowed_hosts=["demo.applyatlas.invalid"],
                              mandate_until=datetime.now(timezone.utc) + timedelta(days=-1 if expired else 1))
    store.save_candidate(candidate)


def test_scoped_autopilot_submits_without_per_job_review(store, engine, executor, good_job):
    set_autopilot(store, good_job)
    app = engine.run("demo-client", good_job)
    assert app["status"] == "submitted"
    assert len(executor.calls) == 1


def test_expired_mandate_routes_to_review(store, engine, executor, good_job):
    set_autopilot(store, good_job, expired=True)
    app = engine.run("demo-client", good_job)
    assert app["status"] == "review"
    assert not executor.calls


def test_wrong_employer_routes_to_review(store, engine, executor, good_job):
    set_autopilot(store, good_job)
    candidate = store.candidate("demo-client")
    candidate.policy.allowed_companies = ["Different employer"]
    store.save_candidate(candidate)
    assert engine.run("demo-client", good_job)["status"] == "review"
    assert not executor.calls


def test_evidence_critic_repairs_unknown_planner_ids(store, executor, good_job):
    class BadPlanner:
        enabled = True

        def select(self, candidate, job, fit, repair=False):
            if repair:
                return Selection(evidence_ids=[candidate.evidence[0].id], strategy="direct_match"), "repair"
            return Selection(evidence_ids=["fabricated-degree"], strategy="direct_match"), "llm"

    engine = Engine(store, executor, BadPlanner())
    try:
        app = engine.run("demo-client", good_job)
        assert app["status"] == "review"
        assert app["packet"]["critic"]["passed"]
        assert app["packet"]["engine"] == "repair"
        assert "fabricated-degree" not in app["packet"]["cover_letter"]
    finally:
        engine.close()


def test_uncertain_result_never_retries(store, executor, engine, good_job):
    executor.result = {"status": "needs_attention", "uncertain": True, "reason": "No receipt"}
    app = engine.run("demo-client", good_job)
    engine.approve(app["id"], approve(app))
    result = engine.run("demo-client", good_job)
    assert result["status"] == "needs_attention"
    assert len(executor.calls) == 1
