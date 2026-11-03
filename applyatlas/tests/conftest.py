import pytest

from applyatlas.demo import seed
from applyatlas.graph import Engine
from applyatlas.store import Store


class RecordingExecutor:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"status": "submitted", "confirmation": "Application received", "demo": True}

    def execute(self, job, candidate, packet, app_id):
        self.calls.append(app_id)
        return self.result


@pytest.fixture(autouse=True)
def no_external_model(monkeypatch):
    monkeypatch.delenv("APPLYATLAS_LLM_API_KEY", raising=False)
    monkeypatch.delenv("APPLYATLAS_LLM_MODEL", raising=False)
    monkeypatch.delenv("APPLYATLAS_API_TOKEN", raising=False)
    monkeypatch.setenv("APPLYATLAS_LIVE_SUBMIT", "false")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    seed(s)
    return s


@pytest.fixture
def good_job(store):
    return next(j["id"] for j in store.jobs() if j["title"] == "Data Engineer")


@pytest.fixture
def executor():
    return RecordingExecutor()


@pytest.fixture
def engine(store, executor):
    e = Engine(store, executor)
    yield e
    e.close()
