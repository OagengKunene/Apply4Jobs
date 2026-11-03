from datetime import datetime, timezone
from urllib.parse import urlsplit

from .models import digest

SUPPORTED_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.eu.lever.co"}


def context_hash(candidate, job):
    # Discover timestamps do not invalidate a review; job content changes do.
    data = job.model_dump(mode="json", exclude={"discovered_at"})
    return digest([candidate.model_dump(mode="json"), data])


def gate(candidate, job, packet):
    if not packet["critic"]["passed"]:
        return "blocked", ["Evidence critic failed"]
    if packet["match"]["score"] < candidate.policy.min_score:
        return "skip", ["Match below client minimum"]
    if job.source != "demo" and urlsplit(job.url).hostname not in SUPPORTED_HOSTS:
        return "blocked", ["Application host has no supported adapter; export packet for manual application"]
    p = candidate.policy
    reasons = list(packet["match"]["warnings"])
    if p.mode != "autopilot":
        reasons.append("Client chose per-application review")
    if p.mode == "autopilot":
        if not p.mandate_until or p.mandate_until <= datetime.now(timezone.utc):
            reasons.append("Client mandate expired")
        if job.company.casefold() not in {c.casefold() for c in p.allowed_companies}:
            reasons.append("Company outside client mandate")
        if urlsplit(job.url).hostname not in p.allowed_hosts:
            reasons.append("Domain outside client mandate")
        if packet["match"]["gaps"]:
            reasons.append("Evidence gaps need client review")
    return ("review", reasons) if reasons else ("autopilot", ["Within current client mandate"])
