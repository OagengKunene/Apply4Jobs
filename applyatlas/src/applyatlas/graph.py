from __future__ import annotations

import sqlite3
import threading
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .intelligence import Planner, critique, match, render_packet
from .models import digest
from .policy import context_hash, gate
from .store import EncryptedSerde


class State(TypedDict, total=False):
    app_id: str
    fit: dict
    attempts: int
    gate: str
    reasons: list[str]
    approved_hash: str
    decision: bool


class Engine:
    def __init__(self, store, executor, planner=None):
        self.store, self.executor = store, executor
        self.planner = planner or Planner()
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(store.root / "checkpoints.db", check_same_thread=False)
        saver = SqliteSaver(self.connection, serde=EncryptedSerde(store.cipher))
        graph = StateGraph(State)
        graph.add_node("match", self._match)
        graph.add_node("compose", self._compose)
        graph.add_node("critic", self._critic)
        graph.add_node("policy", self._policy)
        graph.add_node("review", self._review)
        graph.add_node("execute", self._execute)
        graph.add_edge(START, "match")
        graph.add_edge("match", "compose")
        graph.add_edge("compose", "critic")
        graph.add_conditional_edges("critic", self._after_critic, {"repair": "compose", "next": "policy"})
        graph.add_conditional_edges("policy", lambda s: s["gate"],
                                    {"review": "review", "autopilot": "execute", "skip": END, "blocked": END})
        graph.add_conditional_edges("review", lambda s: "yes" if s["decision"] else "no",
                                    {"yes": "execute", "no": END})
        graph.add_edge("execute", END)
        self.graph = graph.compile(checkpointer=saver)

    def close(self):
        self.connection.close()

    def records(self, state):
        app = self.store.application(state["app_id"])
        return app, self.store.candidate(app["candidate_id"]), self.store.job(app["job_id"])

    def _match(self, state):
        app, candidate, job = self.records(state)
        fit = match(candidate, job)
        self.store.update(app["id"], status="running")
        self.store.event(app["id"], "match", f"Score {fit['score']}; supported skills {len(fit['supported_skills'])}")
        return {"fit": fit, "attempts": 0}

    def _compose(self, state):
        app, candidate, job = self.records(state)
        repair = state.get("attempts", 0) > 0
        try:
            selection, engine = self.planner.select(candidate, job, state["fit"], repair=repair)
        except Exception as exc:
            self.store.event(app["id"], "planner", f"Provider unavailable ({type(exc).__name__}); deterministic fallback")
            selection, engine = Planner().select(candidate, job, state["fit"], repair=True)
        packet = render_packet(candidate, job, state["fit"], selection, engine)
        self.store.update(app["id"], packet=packet, context_hash=context_hash(candidate, job))
        self.store.event(app["id"], "compose", f"Selected {len(packet['claims'])} verified facts; engine {engine}")
        return {"attempts": state.get("attempts", 0) + 1}

    def _critic(self, state):
        app, candidate, _ = self.records(state)
        packet = app["packet"]
        packet["critic"] = critique(candidate, packet)
        self.store.update(app["id"], packet=packet, packet_hash=digest(packet))
        self.store.event(app["id"], "critic", "Evidence passed" if packet["critic"]["passed"] else "Repair requested")
        return {}

    def _after_critic(self, state):
        packet = self.store.application(state["app_id"])["packet"]
        return "repair" if not packet["critic"]["passed"] and state["attempts"] < 2 else "next"

    def _policy(self, state):
        app, candidate, job = self.records(state)
        route, reasons = gate(candidate, job, app["packet"])
        status = {"review": "review", "autopilot": "approved", "blocked": "needs_attention", "skip": "skipped"}[route]
        self.store.update(app["id"], status=status)
        self.store.event(app["id"], "policy", "; ".join(reasons))
        return {"gate": route, "reasons": reasons,
                "approved_hash": app["packet_hash"] if route == "autopilot" else ""}

    def _review(self, state):
        app = self.store.application(state["app_id"])
        # All work before interrupt is read-only: this node is re-entered on resume.
        decision = interrupt({"app_id": app["id"], "packet_hash": app["packet_hash"], "reasons": state["reasons"]})
        if not isinstance(decision, dict) or decision.get("packet_hash") != app["packet_hash"]:
            raise ValueError("The document changed; review its current hash")
        approved = decision.get("approve") is True
        self.store.update(app["id"], status="approved" if approved else "rejected")
        self.store.event(app["id"], "review", "Client approved document hash" if approved else "Client rejected")
        return {"decision": approved, "approved_hash": app["packet_hash"] if approved else ""}

    def _execute(self, state):
        app, candidate, job = self.records(state)
        if app["status"] == "submitted":
            return {}
        if app["packet_hash"] != state.get("approved_hash") or app["context_hash"] != context_hash(candidate, job):
            self.store.update(app["id"], status="needs_attention", receipt={"reason": "Profile, job or policy changed since approval"})
            self.store.event(app["id"], "execute", "Stale approval rejected")
            return {}
        # Re-evaluate the mandate immediately before performing external side effects.
        if state["gate"] == "autopilot" and gate(candidate, job, app["packet"])[0] != "autopilot":
            self.store.update(app["id"], status="needs_attention", receipt={"reason": "Mandate no longer valid"})
            return {}
        claimed, reason = self.store.claim_submission(app["id"], candidate.id, candidate.policy.daily_limit)
        if not claimed:
            self.store.update(app["id"], status="needs_attention", receipt={"reason": reason})
            return {}
        self.store.event(app["id"], "execute", "Submission intent reserved")
        receipt = self.executor.execute(job, candidate, app["packet"], app["id"])
        self.store.update(app["id"], status=receipt["status"], receipt=receipt)
        self.store.event(app["id"], "receipt", receipt["status"])
        return {}

    def run(self, candidate_id, job_id):
        with self.lock:
            self.store.candidate(candidate_id)
            self.store.job(job_id)
            identifier = self.store.create_application(candidate_id, job_id)
            app = self.store.application(identifier)
            config = {"configurable": {"thread_id": identifier}}
            if app["status"] == "queued":
                self.graph.invoke({"app_id": identifier}, config)
            elif app["status"] == "running":
                self.graph.invoke(None, config)
            # Reviewing, completed or uncertain attempts are never silently restarted.
            return self.store.application(identifier)

    def approve(self, identifier, decision):
        with self.lock:
            app = self.store.application(identifier)
            if app["status"] != "review":
                raise ValueError("Application is not awaiting review")
            if decision.packet_hash != app["packet_hash"]:
                raise ValueError("Document hash does not match current draft")
            config = {"configurable": {"thread_id": identifier}}
            self.graph.invoke(Command(resume=decision.model_dump()), config)
            return self.store.application(identifier)
