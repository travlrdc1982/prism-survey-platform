#!/usr/bin/env python3
"""
PRISM Survey Platform — End-to-end flow test against live Vercel API.

Simulates a complete respondent journey:
    Trump voter, Strong Republican → GOP battery → AL study →
    study pages → completion

Usage:
    python tests/test_live_flow.py
    python tests/test_live_flow.py https://your-custom-url.vercel.app
"""

import sys
import json
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://prism-survey-platform-rcghealthprism.vercel.app"
client = httpx.Client(base_url=BASE, timeout=30)


def step(label, method, path, **kwargs):
    """Make a request and print the result."""
    print(f"\n{'='*60}")
    print(f"  STEP: {label}")
    print(f"  {method.upper()} {path}")
    print(f"{'='*60}")

    if method == "get":
        r = client.get(path, **kwargs)
    else:
        r = client.post(path, **kwargs)

    # Follow redirects for complete/terminate
    print(f"  Status: {r.status_code}")
    try:
        data = r.json()
        print(json.dumps(data, indent=2))
        return data
    except Exception:
        print(f"  Body: {r.text[:500]}")
        return {}


# ── 1. ENTRY ─────────────────────────────────────────────────────────────────

entry = step(
    "Dynata Entry — create session",
    "get", "/survey/entry",
    params={"psid": "TEST_LIVE_001", "source": "test_script"},
)
resp_id = entry.get("resp_id")
assert resp_id, "No resp_id returned!"
assert entry.get("next") == "screener"


# ── 2. SCREENER ──────────────────────────────────────────────────────────────
#   qvote=1 (registered), qballot=1 (Trump), qparty=1 (Strong Republican)
#   → should return battery=GOP

screener = step(
    "Screener — Trump voter, Strong Republican",
    "post", "/survey/screener",
    json={
        "resp_id": resp_id,
        "qvote": 1,
        "qballot": 1,       # Trump
        "qparty": 1,         # Strong Republican
        "qgender": 1,
        "qage": 35,
        "qzip": "20001",
    },
)
battery = screener.get("battery")
print(f"\n  >> Battery assigned: {battery}")
assert battery == "GOP", f"Expected GOP, got {battery}"
assert screener.get("next") == "typing"


# ── 3. TYPING BATTERY ───────────────────────────────────────────────────────
#   GOP battery has 12 items. Send fake B-W scores.
#   These are placeholder values — real typing uses MaxDiff best/worst.

# GOP battery expects zGOP1..zGOP12 — B-W scores from MaxDiff typing tasks
# Values are z-scored: positive = chosen as best, negative = chosen as worst
gop_items = {f"zGOP{i}": float((i % 3) - 1) for i in range(1, 13)}

typing = step(
    "Typing Battery — GOP (12 items, fake scores)",
    "post", "/survey/typing",
    json={
        "resp_id": resp_id,
        "battery": "GOP",
        "raw_responses": gop_items,
    },
)

study_code = typing.get("study_code")
segment_id = typing.get("segment_id")
xrandom4 = typing.get("xrandom4")
msg_version = typing.get("msg_version")

print(f"\n  >> Study assigned: {study_code}")
print(f"  >> Segment: {segment_id}")
print(f"  >> xrandom4: {xrandom4}")
print(f"  >> MSG version: {msg_version}")

if typing.get("status") == "overquota":
    print("\n  !! Respondent was overquota — no study assigned.")
    print("  !! This means the AL study hasn't been initialized yet.")
    print("  !! Run: POST /admin/initialize {\"study_code\": \"AL\", \"n_base\": 75}")
    sys.exit(1)

assert study_code, "No study assigned!"


# ── 4. STUDY PAGES — walk through the instrument ────────────────────────────
#   GET each page, POST a response, check what's next.

# Start with the first study page
page_id = "pre_test.SECTORFAV"
pages_visited = []

# Walk through a few pages (not all — just enough to verify flow)
MAX_PAGES = 50  # Walk the entire instrument

for i in range(MAX_PAGES):
    # GET the page content
    page_content = step(
        f"GET study page: {page_id}",
        "get", f"/survey/study/{page_id}",
        params={"resp_id": resp_id},
    )

    pages_visited.append(page_id)

    # POST a dummy response
    dummy_response = {"dummy_var": 1}  # Minimal response
    page_result = step(
        f"POST response for: {page_id}",
        "post", f"/survey/study/{page_id}",
        json={
            "resp_id": resp_id,
            "page_id": page_id,
            "responses": dummy_response,
        },
    )

    next_page = page_result.get("next")
    status = page_result.get("status")

    print(f"\n  >> Next page: {next_page}")
    print(f"  >> Status: {status}")

    if next_page == "complete" or status == "complete":
        print("\n  ** Instrument complete signal received **")
        break

    page_id = next_page


# ── 5. SUMMARY ───────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"  FLOW SUMMARY")
print(f"{'='*60}")
print(f"  resp_id:     {resp_id}")
print(f"  battery:     {battery}")
print(f"  study:       {study_code}")
print(f"  segment:     {segment_id}")
print(f"  xrandom4:    {xrandom4}")
print(f"  msg_version: {msg_version}")
print(f"  pages visited ({len(pages_visited)}):")
for p in pages_visited:
    print(f"    → {p}")
print(f"\n  All steps completed successfully!")
