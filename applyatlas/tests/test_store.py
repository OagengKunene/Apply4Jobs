from concurrent.futures import ThreadPoolExecutor

from applyatlas.store import EncryptedSerde, Store


def test_atomic_daily_budget_across_connections(store, tmp_path):
    def reserve(i):
        return Store(tmp_path).claim_submission("attempt-" + str(i), "demo-client", 3)[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(20)))
    assert sum(results) == 3


def test_application_lease_is_unique(store):
    assert store.claim_submission("app-one", "client", 5)[0]
    assert not store.claim_submission("app-one", "client", 5)[0]


def test_profiles_encrypted_at_rest(store):
    with store.db() as db:
        raw = db.execute("SELECT payload FROM profiles").fetchone()[0]
    assert "alex@example.com" not in raw
    assert "Alex Morgan" not in raw
    assert store.candidate("demo-client").email == "alex@example.com"


def test_checkpoint_serializer_encrypts_payloads(store):
    serializer = EncryptedSerde(store.cipher)
    blob = serializer.dumps_typed({"name": "Private Client", "steps": [1, 2]})
    assert b"Private Client" not in blob[1]
    assert serializer.loads_typed(blob) == {"name": "Private Client", "steps": [1, 2]}


def test_event_tampering_is_detected(store):
    store.event(None, "test", "first")
    store.event(None, "test", "second")
    assert store.verify_chain()
    with store.db() as db:
        db.execute("UPDATE events SET detail='edited' WHERE seq=1")
    assert not store.verify_chain()


def test_mirrored_jobs_dedupe_without_replacing_canonical_source(store, good_job):
    mirrored = store.job(good_job)
    mirrored.source = "manual"
    mirrored.url = "https://jobs.example.com/same-position"
    assert not store.save_job(mirrored)
    assert store.job(good_job).source == "demo"
