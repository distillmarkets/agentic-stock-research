"""Sweep every documented endpoint: status, latency, response shape.

Tickers chosen to spread the shapes a response can take, not to sit at the
median: IBM, MSFT, CRWV, GOOGL (multi-class), AAPL, PLPC (a thin small-cap),
and ZZZZZ (a nonexistent ticker).
"""

import httpx

from distill_toolkit import client

TICKERS = ["AAPL", "IBM", "MSFT", "GOOGL", "CRWV", "PLPC", "ZZZZZ"]

GET_ENDPOINTS = [
    "/api/v1/sec/fundamentals/{t}",
    "/api/v1/sec/profile/{t}",
    "/api/v1/sec/valuation/{t}",
    "/api/v1/sec/filings/{t}",
    "/api/v1/sec/insider/{t}",
    "/api/v1/sec/facts/{t}",
    "/api/v1/sec/ownership/{t}",
    "/api/v1/sec/ownership/{t}/history",
    "/api/v1/sec/ownership/{t}/managers",
    "/api/v1/sec/fundamentals/{t}/history",
    "/api/v1/sec/fundamentals/{t}/as-of/2024-06-30",
    "/api/v1/sec/versions/{t}",
    "/api/v1/sec/revisions/{t}",
    "/api/v1/sec/capex-cycles/ticker/{t}",
    "/api/v1/sec/financial-health/{t}",
    "/api/v1/sec/earnings/{t}",
    "/api/v1/sec/quality-score/{t}",
]

GLOBAL_GETS = [
    ("/api/v1/macro", {}),
    ("/api/v1/sec/managers", {}),
    ("/api/v1/sec/capex-cycles", {}),
    ("/api/v1/sec/buyback-cycles", {}),
    ("/api/v1/sec/financial-health", {}),
    ("/api/v1/sec/upcoming-earnings", {}),
    ("/api/v1/market/tickers/search", {"q": "apple"}),
]


def shape(data) -> str:
    if isinstance(data, list):
        return f"list[{len(data)}]"
    if isinstance(data, dict):
        keys = list(data.keys())
        parts = []
        for k in keys[:12]:
            v = data[k]
            parts.append(f"{k}:list[{len(v)}]" if isinstance(v, list) else k)
        return "{" + ", ".join(parts) + ("…" if len(keys) > 12 else "") + "}"
    return type(data).__name__


def run(label: str, method: str, path: str, params=None, body=None):
    try:
        data = client.request(method, path, params=params, body=body)
        print(f"OK   {label}  {shape(data)}")
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:160].replace("\n", " ")
        print(f"HTTP {e.response.status_code}  {label}  {detail}")
    except Exception as e:
        print(f"ERR  {label}  {type(e).__name__}: {e}")


def main():
    for path, params in GLOBAL_GETS:
        run(path, "GET", path, params=params)

    for tmpl in GET_ENDPOINTS:
        for t in TICKERS:
            path = tmpl.replace("{t}", t)
            run(path, "GET", path)

    # Screen: latest + PIT as-of (Pro scope)
    run("screen latest", "POST", "/api/v1/sec/screen", body={"limit": 50})
    run(
        "screen as-of 2024-06-30",
        "POST",
        "/api/v1/sec/screen",
        body={"limit": 50, "asOf": "2024-06-30"},
    )


if __name__ == "__main__":
    main()
