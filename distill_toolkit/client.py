"""Thin cached client for the Distill Markets API.

Every response is cached on disk so analyses reproduce and re-runs do not spend
quota. A 404 and a 400 are cached too: an uncovered issuer is a stable fact
about the request, and a probe that re-issues one on every restart spends a
budget proving the same thing repeatedly. Every network hit is timed and
appended to ``<cache>/latency.jsonl``.

Configuration, from the environment or the nearest ``.env`` found walking up
from the working directory (so scripts and notebooks anywhere inside the
repository share one cache):

    DISTILL_API_KEY    required for any call
    DISTILL_API_BASE   default https://api.distillmarkets.com
    DISTILL_CACHE_DIR  default ``cache`` next to that .env, else ./cache

The cache holds licensed API responses. It is for your own use for the duration
of your subscription and must never be committed or redistributed. See NOTICE.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import warnings
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

import httpx

from . import __version__

USER_AGENT = f"agentic-stock-research/{__version__}"

# Politeness gap between uncached requests, in seconds. The published per-minute
# cap is 60, so a little over one second keeps a tight loop under it.
REQUEST_GAP = 1.05

# Statuses that are a fact about the request rather than a transient, so the
# answer is worth keeping: an uncovered issuer 404s identically forever.
NEGATIVE_CACHE_STATUSES = (400, 404)

# Key under which a cached error is stored. No API response carries it, so a
# cache file written before negative caching existed still reads as a success.
ERROR_KEY = "__distill_error__"

# Pause before the single retry after a transport reset, in seconds.
RESET_BACKOFF = 2.0

_last_request_at = 0.0
_session: httpx.Client | None = None
_offline = False


class OfflineError(RuntimeError):
    """An uncached call was attempted while the client was offline."""


def is_offline() -> bool:
    """True when uncached calls are refused: inside ``offline()`` or ``DISTILL_OFFLINE=1``."""
    env = os.environ.get("DISTILL_OFFLINE", "")
    return _offline or env.strip().lower() not in ("", "0", "false", "no")


@contextmanager
def offline(enabled: bool = True):
    """Refuse any call that is not already on disk, for the duration of the block.

    A study's reproduction claim is that one script rebuilds every number from
    files already held, and the only way to know that is to make a network call
    impossible and watch it pass. Monkeypatching the transport tests the mock;
    this tests the study. ``DISTILL_OFFLINE=1`` in the environment does the same
    for a whole run, which is how a verifier runs someone else's script without
    editing it.

    Cached responses still serve, negative-cached 400s and 404s still re-raise
    as themselves, and an uncached request raises ``OfflineError`` naming the
    path it wanted. ``offline(False)`` re-enables calls inside a block, which is
    for the one fetch a mostly-offline script is allowed.
    """
    global _offline
    prev = _offline
    _offline = enabled
    try:
        yield
    finally:
        _offline = prev


def _find_env_file() -> Path | None:
    for d in (Path.cwd(), *Path.cwd().parents):
        if (d / ".env").exists():
            return d / ".env"
    return None


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = _find_env_file()
    if env_file is not None:
        env["_ENV_DIR"] = str(env_file.parent)
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.split("#")[0].strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("DISTILL_")})
    return env


_ENV = _load_env()
BASE = _ENV.get("DISTILL_API_BASE", "https://api.distillmarkets.com")
KEY = _ENV.get("DISTILL_API_KEY", "")
_ANCHOR = Path(_ENV.get("_ENV_DIR", Path.cwd()))
CACHE_DIR = (_ANCHOR / Path(_ENV.get("DISTILL_CACHE_DIR", "cache")).expanduser()).resolve()
LATENCY_LOG = CACHE_DIR / "latency.jsonl"


def session() -> httpx.Client:
    """The shared HTTP session. Created on first use so importing needs no key."""
    global _session
    if _session is None:
        if not KEY:
            raise RuntimeError(
                "DISTILL_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _session = httpx.Client(
            base_url=BASE,
            headers={"X-Api-Key": KEY, "User-Agent": USER_AGENT},
            timeout=60.0,
        )
    return _session


def _cache_key(method: str, path: str, params: dict | None, body: dict | None) -> Path:
    payload = json.dumps({"m": method, "p": path, "q": params, "b": body}, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
    slug = path.strip("/").replace("/", "_")[:80]
    return CACHE_DIR / f"{slug}.{digest}.json"


def log_latency(method: str, path: str, params: dict | None, status: int, ms: float) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "method": method,
        "path": path,
        "params": params or {},
        "status": status,
        "ms": round(ms, 1),
    }
    with LATENCY_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _wait_for_gap() -> None:
    gap = REQUEST_GAP - (time.monotonic() - _last_request_at)
    if gap > 0:
        time.sleep(gap)


def _raise_cached_error(method: str, path: str, params: dict | None, err: dict) -> None:
    """Re-raise a cached error as the ``httpx.HTTPStatusError`` the live call raised.

    A cached failure has to fail the same way the network one did, or a caller's
    ``except httpx.HTTPStatusError`` works on the first run and not on the second.
    """
    req = httpx.Request(method, httpx.URL(BASE).join(path), params=params)
    body, text = err.get("body"), err.get("text") or ""
    resp = (httpx.Response(err["status"], request=req, json=body) if body is not None
            else httpx.Response(err["status"], request=req, text=text))
    resp.raise_for_status()


def _send(method: str, path: str, params: dict | None, body: dict | None) -> httpx.Response:
    """One request, retried once on a transport reset.

    Long sweeps can see a connection reset; retried once. That is the socket,
    not the request: the same call succeeds on a fresh connection. Retried once
    only, so a genuinely broken endpoint still surfaces instead of looping.
    """
    try:
        return session().request(method, path, params=params, json=body)
    except (httpx.RemoteProtocolError, httpx.ReadError):
        time.sleep(RESET_BACKOFF)
        return session().request(method, path, params=params, json=body)


def request(
    method: str,
    path: str,
    params: dict | None = None,
    body: dict | None = None,
    force: bool = False,
) -> dict | list:
    """Cached JSON request. Raises for HTTP errors; the error status is still latency-logged.

    A 429 is retried after the server's ``retryAfter`` hint, up to three times,
    and a transport reset is retried once. A 400 or a 404 is cached and re-raised
    from cache on every later call for the same request, so a restarted probe
    does not re-issue calls it has already spent. ``force=True`` re-issues the
    call and overwrites whichever kind of cache entry is there.
    """
    global _last_request_at
    cache_file = _cache_key(method, path, params, body)
    if cache_file.exists() and not force:
        cached = json.loads(cache_file.read_text())
        if isinstance(cached, dict) and ERROR_KEY in cached:
            _raise_cached_error(method, path, params, cached[ERROR_KEY])
        return cached
    if is_offline():
        raise OfflineError(
            f"offline: {method} {path} with params {params} is not in {CACHE_DIR}. "
            "Fetch it in a run that is allowed to call, or drop the row from the study.")

    _wait_for_gap()
    for _attempt in range(4):
        t0 = time.perf_counter()
        resp = _send(method, path, params, body)
        ms = (time.perf_counter() - t0) * 1000
        _last_request_at = time.monotonic()
        log_latency(method, path, params, resp.status_code, ms)
        if resp.status_code != 429:
            break
        if _attempt == 3:
            break
        try:
            payload = resp.json()
            retry_after = int(payload.get("retryAfter", 15)) + 1 if isinstance(payload, dict) else 16
        except ValueError:
            retry_after = 16
        time.sleep(retry_after)

    if resp.status_code in NEGATIVE_CACHE_STATUSES:
        try:
            err_body = resp.json()
        except ValueError:
            err_body = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(
            {ERROR_KEY: {"status": resp.status_code, "body": err_body, "text": resp.text}},
            indent=1))
    resp.raise_for_status()
    data = resp.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, indent=1))
    return data


def get(path: str, **params) -> dict | list:
    return request("GET", path, params=params or None)


def post(path: str, body: dict, **params) -> dict | list:
    return request("POST", path, params=params or None, body=body)


def is_cached(path: str, **params) -> bool:
    """True when this exact GET is already on disk, error entries included.

    Price a sweep before running it: the difference between a network call and
    one that costs nothing is knowable in advance, and a study with a call
    budget should spend it on what it has not asked yet.
    """
    return _cache_key("GET", path, params or None, None).exists()


def get_paged(path: str, limit: int = 500, **params):
    """Yield successive pages of a paged endpoint, following ``nextOffset``.

    The server caps ``limit`` at 500 however much is asked for, so a large
    window is several pages and a single call returns only the first. Each page
    is cached under its own offset, so a re-run costs nothing and an interrupted
    sweep resumes. Iteration stops when a page carries no ``nextOffset`` or one
    that does not advance, so an offset echoed back unchanged ends the loop
    rather than repeating it forever.

    Yields whole page dicts: the item list has a different key per endpoint, and
    the summary fields that sit beside it are usually wanted too.
    """
    offset = int(params.pop("offset", 0))
    while True:
        page = get(path, limit=limit, offset=offset, **params)
        yield page
        nxt = page.get("nextOffset") if isinstance(page, dict) else None
        if not nxt or int(nxt) <= offset:
            return
        offset = int(nxt)


def manifest() -> list[tuple[Path, int, float]]:
    """Every cached response as ``(path, bytes, mtime)``, sorted by path.

    A study's denominators move when the cache is filled underneath it by
    something else. Pin the inputs by recording this at the start of a run and
    comparing at the end: a file that
    appeared, grew, or changed its mtime between the two is an input the study
    did not have when it computed its first number.
    """
    if not CACHE_DIR.exists():
        return []
    return sorted(
        ((p, p.stat().st_size, p.stat().st_mtime) for p in CACHE_DIR.glob("*.json")),
        key=lambda row: str(row[0]),
    )


PANEL_FILES = ("panel.csv", "pit-sample.csv.gz")


def panel_path() -> Path:
    """The point-in-time panel on disk: the full export if it is there, else
    the published 200-firm sample. Raises ``FileNotFoundError`` naming both
    when neither is; the README's Install section says how to get either."""
    for name in PANEL_FILES:
        p = CACHE_DIR / name
        if p.exists():
            return p
    raise FileNotFoundError(
        f"no panel in {CACHE_DIR}: run examples/fetch_panel.py for {PANEL_FILES[0]} "
        f"or download {PANEL_FILES[1]} from the release page (README, Install)")


def download(path: str, out: Path, params: dict | None = None, timeout: float = 300.0) -> Path:
    """Stream a large response (for example ``/sec/screen/export``) to a file.

    Not cached through the JSON cache; the file itself is the artifact. Latency
    is logged like any other call.
    """
    global _last_request_at
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if is_offline():
        raise OfflineError(f"offline: refusing to stream {path} to {out}")
    _wait_for_gap()
    t0 = time.perf_counter()
    with session().stream("GET", path, params=params, timeout=timeout) as resp:
        status = resp.status_code
        if status >= 400:
            resp.read()
            log_latency("GET", path, params, status, (time.perf_counter() - t0) * 1000)
            resp.raise_for_status()
        with out.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    _last_request_at = time.monotonic()
    log_latency("GET", path, params, status, (time.perf_counter() - t0) * 1000)
    return out


def _slug_of(cache_file: Path) -> str:
    """The request slug a cache filename was built from, without the digest."""
    return cache_file.name.rsplit(".", 2)[0]


def cached_for(tickers: Sequence[str]) -> dict[str, list[Path]]:
    """``{ticker: [cache file, ...]}`` for the responses already on disk per ticker.

    Matched on the request slug, which is the path with its slashes turned into
    underscores, so ``/sec/fundamentals/AAPL/history`` is found under ``AAPL``.
    A bulk response covering many tickers carries no ticker in its path and
    appears under none of them.
    """
    out: dict[str, list[Path]] = {}
    if not CACHE_DIR.exists():
        return {t: [] for t in tickers}
    files = [(p, f"_{_slug_of(p).upper()}_") for p in CACHE_DIR.glob("*.json")]
    for t in tickers:
        needle = f"_{str(t).upper()}_"
        out[t] = sorted(p for p, slug in files if needle in slug)
    return out


def pin(tickers: Sequence[str], path) -> dict:
    """Record which cached responses back a study's ticker set, and detect drift later.

    A shared cache is filled by other work while a study runs, and a denominator
    moves underneath the study when it is: the event set the first table counted
    is not the set the fifth table counted. Call this
    before the first call of a run and again at the end. The first call writes
    the record; a later call reads it back, compares, and reports what moved
    without overwriting it.

    A file that appeared, vanished, or changed size between the two is an input
    the study did not have when it computed its first number. Returns the pinned
    record with a ``changed`` list of ``(ticker, filename, what)``, and raises a
    ``RuntimeWarning`` when that list is not empty, so a run that drifted says so
    in its own output rather than in nobody's.

    ``manifest`` is the whole-cache version of the same idea; this one is scoped
    to the tickers a study named, which is what belongs in a write-up.
    """
    path = Path(path)
    now = {t: {p.name: p.stat().st_size for p in files}
           for t, files in cached_for(tickers).items()}
    record = {"recorded": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "cache_dir": str(CACHE_DIR), "tickers": now}
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, sort_keys=True))
        return {**record, "changed": []}
    pinned = json.loads(path.read_text())
    was = pinned.get("tickers", {})
    changed = []
    for t in sorted(set(was) | set(now)):
        a, b = was.get(t, {}), now.get(t, {})
        for name in sorted(set(a) | set(b)):
            if name not in a:
                changed.append((t, name, "appeared"))
            elif name not in b:
                changed.append((t, name, "vanished"))
            elif a[name] != b[name]:
                changed.append((t, name, f"resized {a[name]} to {b[name]}"))
    if changed:
        warnings.warn(
            f"pin: {len(changed)} cached response(s) moved since {pinned.get('recorded')}; "
            "the study's inputs are not the ones it started with",
            RuntimeWarning, stacklevel=2)
    return {**pinned, "changed": changed}
