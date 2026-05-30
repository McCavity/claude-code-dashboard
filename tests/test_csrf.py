"""CSRF origin-guard: unit + middleware-integration tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts._csrf import csrf_origin_guard, origin_allowed, origin_is_local


def _client() -> TestClient:
    app = FastAPI()
    app.middleware("http")(csrf_origin_guard)

    @app.post("/mutate")
    def mutate() -> dict:
        return {"ok": True}

    @app.get("/read")
    def read() -> dict:
        return {"ok": True}

    return TestClient(app)


# --- pure-function policy ---------------------------------------------------


def test_no_origin_allowed():
    # Non-browser clients (OTEL exporter, curl) send no Origin header.
    assert origin_allowed(None) is True
    assert origin_allowed("") is True


def test_localhost_origins_allowed():
    assert origin_allowed("http://127.0.0.1:8766") is True
    assert origin_allowed("http://localhost:5173") is True
    assert origin_allowed("http://[::1]:8766") is True


def test_foreign_origins_blocked():
    assert origin_allowed("https://evil.example") is False
    assert origin_allowed("http://attacker.test:8766") is False
    # Look-alike that merely *contains* localhost is still foreign.
    assert origin_allowed("http://localhost.evil.example") is False


def test_origin_is_local_helper():
    assert origin_is_local("http://localhost") is True
    assert origin_is_local("https://example.com") is False


# --- middleware integration -------------------------------------------------


def test_post_foreign_origin_blocked():
    r = _client().post("/mutate", headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_post_localhost_origin_allowed():
    r = _client().post("/mutate", headers={"origin": "http://127.0.0.1:8766"})
    assert r.status_code == 200


def test_post_no_origin_allowed():
    # Simulates the OTEL exporter / curl path: no Origin header.
    r = _client().post("/mutate")
    assert r.status_code == 200


def test_get_with_foreign_origin_allowed():
    # GET is a safe method and is never guarded.
    r = _client().get("/read", headers={"origin": "https://evil.example"})
    assert r.status_code == 200


def test_delete_foreign_origin_blocked():
    # DELETE is state-changing -> guarded like POST.
    app = FastAPI()
    app.middleware("http")(csrf_origin_guard)

    @app.delete("/thing")
    def thing() -> dict:
        return {"deleted": True}

    r = TestClient(app).delete("/thing", headers={"origin": "https://evil.example"})
    assert r.status_code == 403
