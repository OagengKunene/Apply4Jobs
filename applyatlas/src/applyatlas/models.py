from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Use an ordinary HTTPS URL without credentials or custom ports")
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith("utm_") and k not in {"source", "ref"}]
    return urlunsplit(("https", p.hostname.lower(), p.path.rstrip("/"), urlencode(sorted(query)), ""))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    text: str = Field(min_length=10, max_length=1500)
    skills: list[str] = Field(min_length=1, max_length=20)


class Policy(StrictModel):
    mode: Literal["review", "autopilot"] = "review"
    min_score: int = Field(default=75, ge=0, le=100)
    daily_limit: int = Field(default=5, ge=1, le=25)
    allowed_companies: list[str] = Field(default_factory=list, max_length=100)
    allowed_hosts: list[str] = Field(default_factory=list, max_length=20)
    mandate_until: datetime | None = None

    @model_validator(mode="after")
    def explicit_autopilot(self):
        if self.mode == "autopilot":
            if not self.allowed_companies or not self.allowed_hosts or not self.mandate_until:
                raise ValueError("Autopilot requires company and host allowlists and an expiry")
            if self.mandate_until.tzinfo is None:
                raise ValueError("Mandate expiry must include a timezone")
        return self


class Candidate(StrictModel):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    phone: str = Field(default="", max_length=40)
    location: str = Field(min_length=2, max_length=150)
    years_experience: float = Field(ge=0, le=60)
    desired_titles: list[str] = Field(min_length=1, max_length=20)
    preferred_locations: list[str] = Field(min_length=1, max_length=20)
    evidence: list[Evidence] = Field(min_length=1, max_length=100)
    policy: Policy = Field(default_factory=Policy)

    @field_validator("evidence")
    @classmethod
    def unique_evidence(cls, value):
        if len({e.id for e in value}) != len(value):
            raise ValueError("Evidence IDs must be unique")
        return value


class Job(StrictModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(min_length=2, max_length=150)
    location: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20, max_length=50000)
    url: str
    source: Literal["demo", "greenhouse", "lever", "manual", "jobspy"] = "manual"
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    min_years: float = Field(default=0, ge=0, le=60)
    discovered_at: str = Field(default_factory=now)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return canonical_url(value)

    @property
    def id(self) -> str:
        # A mirror on another board should not create a second application.
        identity = [re.sub(r"\W+", " ", x.casefold()).strip() for x in (self.company, self.title, self.location)]
        return digest(identity)[:24]


class Selection(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    strategy: Literal["direct_match", "transferable_skills", "stretch_role"]


class RunRequest(StrictModel):
    candidate_id: str
    job_ids: list[str] = Field(min_length=1, max_length=30)


class Approval(StrictModel):
    packet_hash: str
    approve: bool


class DiscoveryRequest(StrictModel):
    source: Literal["greenhouse", "lever", "jobspy"]
    board: str = Field(default="", pattern=r"^[a-zA-Z0-9_-]{0,100}$")
    query: str = Field(default="software engineer", max_length=100)
    location: str = Field(default="South Africa", max_length=100)
    limit: int = Field(default=20, ge=1, le=50)
