from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from .models import Candidate, Job, digest, now, uid


class EncryptedSerde:
    """Encrypt every LangGraph checkpoint value, including intermediate writes."""

    def __init__(self, cipher: Fernet):
        self.cipher = cipher
        self.inner = JsonPlusSerializer()

    def dumps_typed(self, obj):
        kind, value = self.inner.dumps_typed(obj)
        return "fernet", self.cipher.encrypt(kind.encode() + b"\0" + value)

    def loads_typed(self, data):
        kind, payload = data
        if kind != "fernet":
            raise ValueError("Unencrypted checkpoint rejected")
        inner_kind, value = self.cipher.decrypt(payload).split(b"\0", 1)
        return self.inner.loads_typed((inner_kind.decode(), value))


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        key_path = root / "vault.key"
        if not key_path.exists():
            try:
                fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(Fernet.generate_key())
            except FileExistsError:
                pass
        self.cipher = Fernet(key_path.read_bytes())
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS applications(
                  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, job_id TEXT NOT NULL,
                  status TEXT NOT NULL, packet TEXT, packet_hash TEXT, context_hash TEXT,
                  receipt TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  UNIQUE(candidate_id, job_id));
                CREATE TABLE IF NOT EXISTS events(
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, at TEXT NOT NULL,
                  node TEXT NOT NULL, detail TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(
                  app_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, day TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outcomes(app_id TEXT PRIMARY KEY, stage TEXT NOT NULL);
            """)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.root / "atlas.db", timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def seal(self, value) -> str:
        return self.cipher.encrypt(json.dumps(value, sort_keys=True).encode()).decode()

    def unseal(self, value: str):
        return json.loads(self.cipher.decrypt(value.encode()))

    def save_candidate(self, candidate: Candidate):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO profiles VALUES (?,?)",
                       (candidate.id, self.seal(candidate.model_dump(mode="json"))))

    def candidate(self, identifier: str) -> Candidate:
        with self.db() as db:
            row = db.execute("SELECT payload FROM profiles WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise KeyError(identifier)
        return Candidate.model_validate(self.unseal(row[0]))

    def candidates(self):
        with self.db() as db:
            rows = db.execute("SELECT payload FROM profiles").fetchall()
        return [self.unseal(r[0]) for r in rows]

    def save_job(self, job: Job):
        with self.db() as db:
            existing = db.execute("SELECT payload FROM jobs WHERE id=?", (job.id,)).fetchone()
            if existing:
                old = Job.model_validate_json(existing[0])
                if old.source != job.source:
                    return False  # Preserve canonical board details when a mirror arrives.
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job.id, job.model_dump_json()))
        return existing is None

    def job(self, identifier: str) -> Job:
        with self.db() as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise KeyError(identifier)
        return Job.model_validate_json(row[0])

    def jobs(self):
        with self.db() as db:
            return [{"id": r[0], **json.loads(r[1])} for r in db.execute("SELECT id,payload FROM jobs")]

    def create_application(self, candidate_id, job_id):
        with self.db() as db:
            identifier = uid()
            db.execute("INSERT OR IGNORE INTO applications(id,candidate_id,job_id,status,created_at,updated_at) "
                       "VALUES (?,?,?,'queued',?,?)", (identifier, candidate_id, job_id, now(), now()))
            row = db.execute("SELECT id FROM applications WHERE candidate_id=? AND job_id=?",
                             (candidate_id, job_id)).fetchone()
        return row[0]

    def application(self, identifier):
        with self.db() as db:
            row = db.execute("SELECT * FROM applications WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise KeyError(identifier)
        result = dict(row)
        result["packet"] = self.unseal(result["packet"]) if result["packet"] else None
        result["receipt"] = self.unseal(result["receipt"]) if result["receipt"] else None
        return result

    def applications(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM applications ORDER BY created_at DESC")]
        return [self.application(i) for i in ids]

    def update(self, identifier, **values):
        allowed = {"status", "packet", "packet_hash", "context_hash", "receipt"}
        if not values.keys() <= allowed:
            raise ValueError("Unknown application field")
        for key in ("packet", "receipt"):
            if key in values:
                values[key] = self.seal(values[key])
        values["updated_at"] = now()
        with self.db() as db:
            db.execute(f"UPDATE applications SET {','.join(k + '=?' for k in values)} WHERE id=?",
                       [*values.values(), identifier])

    def claim_submission(self, app_id, candidate_id, daily_limit):
        """Reserve quota and the side-effect lease atomically across processes.

        A crash after claiming requires reconciliation, never a blind retry.
        """
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            day = now()[:10]
            count = db.execute("SELECT COUNT(*) FROM attempts WHERE candidate_id=? AND day=?",
                               (candidate_id, day)).fetchone()[0]
            if count >= daily_limit:
                return False, "daily_limit"
            if db.execute("SELECT 1 FROM attempts WHERE app_id=?", (app_id,)).fetchone():
                return False, "already_attempted"
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (app_id, candidate_id, day))
            db.execute("UPDATE applications SET status='submitting',updated_at=? WHERE id=?", (now(), app_id))
        return True, "reserved"

    def event(self, app_id, node, detail):
        # Details must be operational metadata; no profile/contact/cover-letter payloads.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            previous = row[0] if row else "0" * 64
            timestamp = now()
            hashed = digest([app_id, timestamp, node, detail, previous])
            db.execute("INSERT INTO events(app_id,at,node,detail,previous_hash,hash) VALUES (?,?,?,?,?,?)",
                       (app_id, timestamp, node, detail, previous, hashed))

    def events(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY seq")]

    def verify_chain(self):
        previous = "0" * 64
        for row in self.events():
            if row["previous_hash"] != previous or row["hash"] != digest(
                [row["app_id"], row["at"], row["node"], row["detail"], previous]
            ):
                return False
            previous = row["hash"]
        return True

    def outcome(self, app_id, stage):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?)", (app_id, stage))

    def insights(self):
        with self.db() as db:
            rows = db.execute("SELECT a.job_id,o.stage FROM outcomes o JOIN applications a ON a.id=o.app_id")
            items = list(rows)
        groups = {}
        for row in items:
            source = self.job(row["job_id"]).source
            group = groups.setdefault(source, {"source": source, "observed": 0, "positive": 0})
            group["observed"] += 1
            group["positive"] += row["stage"] in {"interview", "offer"}
        for group in groups.values():
            group["smoothed_response_rate"] = round((group["positive"] + 1) / (group["observed"] + 2), 3)
        return list(groups.values())
