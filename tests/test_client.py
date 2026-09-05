"""Tests for distill_toolkit.client against a stub transport. Every response
here is synthetic: invented payloads in the shape the API returns, and no call
leaves the machine."""

import json

import httpx
import pytest

from distill_toolkit import client


class StubSession:
    """Hands back queued responses (or raises queued exceptions) and counts calls."""

    def __init__(self, queue):
        self.queue = list(queue)
        self.calls = []

    def request(self, method, path, params=None, json=None):
        self.calls.append((method, path, params))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _resp(status, payload=None):
    req = httpx.Request("GET", "https://example.invalid/api/v1/thing")
    return httpx.Response(status, request=req, json=payload if payload is not None else {})


@pytest.fixture
def stub(tmp_path, monkeypatch):
    """Client wired to a temp cache and a stub session, with the politeness gap off."""
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(client, "LATENCY_LOG", tmp_path / "latency.jsonl")
    monkeypatch.setattr(client, "REQUEST_GAP", 0.0)
    monkeypatch.setattr(client, "RESET_BACKOFF", 0.0)

    def install(queue):
        session = StubSession(queue)
        monkeypatch.setattr(client, "session", lambda: session)
        return session

    return install


def test_success_is_cached_and_not_re_issued(stub):
    session = stub([_resp(200, {"ok": 1})])
    assert client.get("/api/v1/thing") == {"ok": 1}
    assert client.get("/api/v1/thing") == {"ok": 1}
    assert len(session.calls) == 1


def test_a_404_is_cached_and_raises_the_same_error_from_disk(stub):
    session = stub([_resp(404, {"error": "not covered"})])
    with pytest.raises(httpx.HTTPStatusError) as first:
        client.get("/api/v1/thing", ticker="NOPE")
    with pytest.raises(httpx.HTTPStatusError) as second:
        client.get("/api/v1/thing", ticker="NOPE")
    assert len(session.calls) == 1  # the restart does not re-spend the call
    assert first.value.response.status_code == second.value.response.status_code == 404
    assert second.value.response.json() == {"error": "not covered"}


def test_the_cached_error_file_records_the_status(stub, tmp_path):
    stub([_resp(400, {"error": "bad param"})])
    with pytest.raises(httpx.HTTPStatusError):
        client.get("/api/v1/thing", quarters="many")
    written = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert written[client.ERROR_KEY]["status"] == 400


def test_a_500_is_not_cached(stub):
    session = stub([_resp(500), _resp(200, {"ok": 1})])
    with pytest.raises(httpx.HTTPStatusError):
        client.get("/api/v1/thing")
    assert client.get("/api/v1/thing") == {"ok": 1}
    assert len(session.calls) == 2


def test_is_cached_sees_both_kinds_of_entry(stub):
    stub([_resp(200, {"ok": 1}), _resp(404, {})])
    assert not client.is_cached("/api/v1/thing", a=1)
    client.get("/api/v1/thing", a=1)
    assert client.is_cached("/api/v1/thing", a=1)
    with pytest.raises(httpx.HTTPStatusError):
        client.get("/api/v1/thing", a=2)
    assert client.is_cached("/api/v1/thing", a=2)


def test_get_paged_follows_next_offset(stub):
    session = stub([
        _resp(200, {"transactions": [1, 2], "nextOffset": 2}),
        _resp(200, {"transactions": [3], "nextOffset": None}),
    ])
    pages = list(client.get_paged("/api/v1/insider/X", limit=2))
    assert [p["transactions"] for p in pages] == [[1, 2], [3]]
    assert [c[2]["offset"] for c in session.calls] == [0, 2]


def test_get_paged_stops_when_the_offset_does_not_advance(stub):
    stub([_resp(200, {"rows": [1], "nextOffset": 0})])
    assert len(list(client.get_paged("/api/v1/insider/X"))) == 1


def test_a_transport_reset_is_retried_once(stub):
    session = stub([httpx.RemoteProtocolError("server disconnected"), _resp(200, {"ok": 1})])
    assert client.get("/api/v1/thing") == {"ok": 1}
    assert len(session.calls) == 2


def test_a_second_reset_is_not_retried(stub):
    stub([httpx.ReadError("reset"), httpx.ReadError("reset")])
    with pytest.raises(httpx.ReadError):
        client.get("/api/v1/thing")


def test_manifest_lists_every_cached_response_sorted(stub, tmp_path):
    stub([_resp(200, {"ok": 1}), _resp(200, {"ok": 2})])
    client.get("/api/v1/thing", a=1)
    client.get("/api/v1/other", a=1)
    rows = client.manifest()
    assert len(rows) == 2
    assert [str(p) for p, _s, _m in rows] == sorted(str(p) for p, _s, _m in rows)
    assert all(size > 0 and mtime > 0 for _p, size, mtime in rows)


# ---- the offline guard and the cache pin ----------------------------------
@pytest.fixture
def cache(tmp_path, monkeypatch):
    """The client pointed at an empty temporary cache, with no session available."""
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(client, "LATENCY_LOG", tmp_path / "latency.jsonl")
    monkeypatch.setattr(client, "REQUEST_GAP", 0.0)
    monkeypatch.delenv("DISTILL_OFFLINE", raising=False)
    return tmp_path


def _write_cached(cache_dir, path, payload, params=None):
    f = client._cache_key("GET", path, params, None)
    f.write_text(json.dumps(payload))
    return f


def test_offline_serves_the_cache_and_refuses_everything_else(cache):
    _write_cached(cache, "/api/v1/thing", {"ok": 1})
    with client.offline():
        assert client.get("/api/v1/thing") == {"ok": 1}
        with pytest.raises(client.OfflineError, match="not in"):
            client.get("/api/v1/other")


def test_offline_still_re_raises_a_negative_cached_error(cache):
    f = client._cache_key("GET", "/api/v1/gone", None, None)
    f.write_text(json.dumps({client.ERROR_KEY: {"status": 404, "body": {"detail": "no"}}}))
    with client.offline():
        with pytest.raises(httpx.HTTPStatusError):
            client.get("/api/v1/gone")


def test_offline_restores_the_previous_state_and_nests(cache):
    assert not client.is_offline()
    with client.offline():
        assert client.is_offline()
        with client.offline(False):
            assert not client.is_offline()
        assert client.is_offline()
    assert not client.is_offline()


def test_the_environment_variable_turns_it_on_for_a_whole_run(cache, monkeypatch):
    monkeypatch.setenv("DISTILL_OFFLINE", "1")
    assert client.is_offline()
    with pytest.raises(client.OfflineError):
        client.get("/api/v1/thing")
    monkeypatch.setenv("DISTILL_OFFLINE", "0")
    assert not client.is_offline()


def test_download_refuses_to_stream_while_offline(cache):
    with client.offline():
        with pytest.raises(client.OfflineError, match="stream"):
            client.download("/api/v1/sec/screen/export", cache / "panel.csv")


def test_cached_for_finds_the_responses_belonging_to_a_ticker(cache):
    _write_cached(cache, "/api/v1/sec/fundamentals/AAA/history", {"years": []})
    _write_cached(cache, "/api/v1/sec/revisions/AAA", {"revisions": []})
    _write_cached(cache, "/api/v1/sec/fundamentals/BBB/history", {"years": []})
    found = client.cached_for(["AAA", "BBB", "CCC"])
    assert len(found["AAA"]) == 2 and len(found["BBB"]) == 1 and found["CCC"] == []


def test_pin_writes_the_record_then_reports_what_moved(cache, tmp_path):
    _write_cached(cache, "/api/v1/sec/fundamentals/AAA/history", {"years": [1]})
    pin_file = tmp_path / "pin.json"
    first = client.pin(["AAA"], pin_file)
    assert first["changed"] == [] and pin_file.exists()

    # A second study fills the cache underneath this one.
    _write_cached(cache, "/api/v1/sec/revisions/AAA", {"revisions": []})
    with pytest.warns(RuntimeWarning, match="moved since"):
        again = client.pin(["AAA"], pin_file)
    assert [c[2] for c in again["changed"]] == ["appeared"]
    # The record itself is not overwritten, so the drift stays visible.
    assert json.loads(pin_file.read_text())["tickers"]["AAA"].keys() == \
        first["tickers"]["AAA"].keys()


def test_pin_notices_a_response_that_grew(cache, tmp_path):
    f = _write_cached(cache, "/api/v1/sec/fundamentals/AAA/history", {"years": [1]})
    pin_file = tmp_path / "pin.json"
    client.pin(["AAA"], pin_file)
    f.write_text(json.dumps({"years": [1, 2, 3, 4, 5, 6, 7, 8, 9]}))
    with pytest.warns(RuntimeWarning):
        out = client.pin(["AAA"], pin_file)
    assert out["changed"][0][2].startswith("resized")
