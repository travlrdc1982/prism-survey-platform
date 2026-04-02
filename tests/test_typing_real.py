#!/usr/bin/env python3
"""
PRISM Typing Tool — Real Data Path Test

Generates realistic MaxDiff task responses (best/worst picks) from the
GOP BIBD design in prism_norms.db, reconstructs B-W scores using the
same logic as export.py, feeds those to /survey/typing, and verifies
the assigned segment is consistent with the simulated choice pattern.

No hand-crafted raw values. The full data path is exercised:
    BIBD tasks → best/worst picks → B-W reconstruction → z-scoring → D² → softmax → segment

Usage:
    python tests/test_typing_real.py
"""

import sys
import os
import sqlite3
import json
import math
import httpx
import time

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://prism-survey-platform-rcghealthprism.vercel.app"

# ── Load typing data from prism_norms.db ─────────────────────────────────────

NORMS_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prism_norms.db")
conn = sqlite3.connect(NORMS_DB)
conn.row_factory = sqlite3.Row

# GOP BIBD: task_num → [item_num, ...]
bibd_rows = conn.execute(
    "SELECT task_num, position, item_num FROM typing_bibd_gop ORDER BY task_num, position"
).fetchall()
BIBD_TASKS = {}
for r in bibd_rows:
    t = r["task_num"]
    if t not in BIBD_TASKS:
        BIBD_TASKS[t] = []
    BIBD_TASKS[t].append(r["item_num"])

# item_num → item_id mapping (item_order = item_num in the BIBD)
item_rows = conn.execute(
    "SELECT item_id, item_order, mu, sigma FROM typing_items WHERE battery = 'GOP' ORDER BY item_order"
).fetchall()
ITEM_MAP = {}  # item_num → item_id
ITEM_PARAMS = {}  # item_id → {mu, sigma}
for r in item_rows:
    ITEM_MAP[r["item_order"]] = r["item_id"]
    ITEM_PARAMS[r["item_id"]] = {"mu": r["mu"], "sigma": r["sigma"]}

N_ITEMS = len(ITEM_MAP)

# Centroids: segment_id → {item_id: centroid_value}
centroid_rows = conn.execute(
    "SELECT segment_id, item_id, centroid FROM typing_centroids "
    "WHERE item_id LIKE 'zGOP%' ORDER BY segment_id, item_id"
).fetchall()
CENTROIDS = {}
for r in centroid_rows:
    seg = r["segment_id"]
    if seg not in CENTROIDS:
        CENTROIDS[seg] = {}
    CENTROIDS[seg][r["item_id"]] = r["centroid"]

# Segment names
seg_rows = conn.execute(
    "SELECT segment_id, abbreviation, full_name FROM segments ORDER BY segment_id"
).fetchall()
SEG_NAMES = {r["segment_id"]: f"{r['abbreviation']} ({r['full_name']})" for r in seg_rows}

conn.close()


# ── B-W score reconstruction (same logic as export.py) ───────────────────────

def reconstruct_bw_scores(task_responses: dict, bibd_tasks: dict, n_items: int) -> dict:
    """
    Reconstruct item-level B-W scores from task-level best/worst picks.

    task_responses: {task_num: {"best": item_num, "worst": item_num}}
    bibd_tasks:     {task_num: [item_num, ...]}
    n_items:        total number of items

    Returns: {item_num: bw_score} where bw_score = (times_best - times_worst)
    """
    scores = {i: 0 for i in range(1, n_items + 1)}
    for task_num, response in task_responses.items():
        best = response["best"]
        worst = response["worst"]
        scores[best] += 1
        scores[worst] -= 1
    return scores


# ── Simulate a respondent with a target segment profile ──────────────────────

def simulate_respondent_choices(target_segment_id: int, bibd_tasks: dict, centroids: dict) -> dict:
    """
    Simulate MaxDiff best/worst choices for a respondent whose preferences
    align with a target segment's centroid.

    For each task, pick BEST = item closest to centroid (highest centroid value)
    and WORST = item furthest from centroid (lowest centroid value).

    This is deterministic and produces the strongest possible signal for the
    target segment — a real respondent would be noisier.
    """
    target_centroid = centroids[target_segment_id]
    task_responses = {}

    for task_num, item_nums in bibd_tasks.items():
        # Map item_nums to their centroid values for the target segment
        item_centroids = {}
        for inum in item_nums:
            item_id = ITEM_MAP[inum]
            item_centroids[inum] = target_centroid.get(item_id, 0.0)

        # Best = highest centroid value (most aligned with segment)
        best = max(item_centroids, key=item_centroids.get)
        # Worst = lowest centroid value (least aligned with segment)
        worst = min(item_centroids, key=item_centroids.get)

        task_responses[task_num] = {"best": best, "worst": worst}

    return task_responses


def bw_scores_to_raw_responses(bw_scores: dict, item_map: dict, item_params: dict) -> dict:
    """
    Convert integer B-W scores to the raw_responses format expected by
    /survey/typing. The typing tool expects {item_id: raw_value} where
    raw_value is in the item's scale range (scale_min to scale_max, i.e. -4 to +4).

    B-W scores from 12 tasks with 4 items each range from -4 to +4 (each item
    appears in exactly 4 tasks). These map directly to the scale.
    """
    raw = {}
    for item_num, bw in bw_scores.items():
        item_id = item_map[item_num]
        raw[item_id] = float(bw)
    return raw


# ── Run the test ─────────────────────────────────────────────────────────────

def run_test(target_seg: int, label: str):
    """Run a full typing test for a target segment."""
    print(f"\n{'='*70}")
    print(f"  TYPING TEST: {label}")
    print(f"  Target segment: {target_seg} — {SEG_NAMES.get(target_seg, '?')}")
    print(f"{'='*70}")

    # Step 1: Simulate MaxDiff task responses
    task_responses = simulate_respondent_choices(target_seg, BIBD_TASKS, CENTROIDS)
    print(f"\n  STEP 1: Simulated MaxDiff task responses ({len(task_responses)} tasks)")
    for task_num in sorted(task_responses):
        resp = task_responses[task_num]
        items_in_task = BIBD_TASKS[task_num]
        best_id = ITEM_MAP[resp["best"]]
        worst_id = ITEM_MAP[resp["worst"]]
        print(f"    Task {task_num:>2d}: items {items_in_task} → "
              f"BEST={resp['best']} ({best_id}), WORST={resp['worst']} ({worst_id})")

    # Step 2: Reconstruct B-W scores
    bw_scores = reconstruct_bw_scores(task_responses, BIBD_TASKS, N_ITEMS)
    print(f"\n  STEP 2: Reconstructed B-W scores")
    for item_num in sorted(bw_scores):
        item_id = ITEM_MAP[item_num]
        bw = bw_scores[item_num]
        centroid_val = CENTROIDS[target_seg].get(item_id, 0)
        bar_pos = "+" * max(0, bw)
        bar_neg = "-" * max(0, -bw)
        print(f"    {item_id:8s} (item {item_num:>2d}): BW={bw:+2d}  "
              f"centroid={centroid_val:+.3f}  {bar_neg}{bar_pos}")

    # Step 3: Convert to raw responses
    raw_responses = bw_scores_to_raw_responses(bw_scores, ITEM_MAP, ITEM_PARAMS)
    print(f"\n  STEP 3: Raw responses for /survey/typing")
    for item_id in sorted(raw_responses):
        print(f"    {item_id:8s} = {raw_responses[item_id]:+.1f}")

    # Step 4: Hit the live API
    print(f"\n  STEP 4: API call chain")
    client = httpx.Client(base_url=BASE, timeout=30)

    # Entry
    r = client.get("/survey/entry", params={"psid": f"TYPING_REAL_{target_seg}_{time.time()}"}).json()
    rid = r["resp_id"]
    print(f"    Entry: resp_id={rid}")

    # Screener (Strong Republican, Trump voter)
    client.post("/survey/screener", json={
        "resp_id": rid, "qvote": 1, "qballot": 1, "qparty": 1,
        "qgender": 1, "qage": 40, "qzip": "20001",
    })
    print(f"    Screener: GOP battery assigned")

    # Typing
    t = client.post("/survey/typing", json={
        "resp_id": rid,
        "battery": "GOP",
        "raw_responses": raw_responses,
    }).json()

    if "segment_id" not in t:
        print(f"    Typing FAILED: {json.dumps(t)[:300]}")
        return False

    assigned = t["segment_id"]
    prob = t.get("seg_probability", 0)
    gap = t.get("seg_gap", 0)
    entropy = t.get("seg_entropy", 0)
    all_probs = t.get("all_probs", {})

    print(f"\n  STEP 5: Results")
    print(f"    Assigned segment:  {assigned} — {SEG_NAMES.get(assigned, '?')}")
    print(f"    Target segment:    {target_seg} — {SEG_NAMES.get(target_seg, '?')}")
    print(f"    seg_probability:   {prob:.4f}")
    print(f"    seg_gap:           {gap:.4f}")
    print(f"    seg_entropy:       {entropy:.4f}")

    if all_probs:
        print(f"\n    Softmax distribution:")
        for seg_id in sorted(all_probs.keys(), key=lambda x: int(x)):
            p = all_probs[seg_id]
            bar = "█" * int(p * 50)
            markers = []
            if int(seg_id) == assigned:
                markers.append("ASSIGNED")
            if int(seg_id) == target_seg and int(seg_id) != assigned:
                markers.append("TARGET")
            marker = f" ← {', '.join(markers)}" if markers else ""
            print(f"      Seg {seg_id:>2s}: {p:.4f} {bar}{marker}")

    # Verify
    match = assigned == target_seg
    print(f"\n  VERDICT: {'PASS' if match else 'FAIL'} — "
          f"{'target segment assigned' if match else f'expected seg {target_seg}, got seg {assigned}'}"
          f" (P={prob:.4f})")

    return match


# ── Main ─────────────────────────────────────────────────────────────────────

print("=" * 70)
print("  PRISM TYPING TOOL — REAL DATA PATH VERIFICATION")
print("  BIBD tasks → best/worst → B-W reconstruction → typing API → segment")
print("=" * 70)
print(f"\n  prism_norms.db: {NORMS_DB}")
print(f"  GOP BIBD: {len(BIBD_TASKS)} tasks × {len(BIBD_TASKS[1])} items")
print(f"  GOP items: {N_ITEMS}")
print(f"  Segments with centroids: {sorted(CENTROIDS.keys())}")

results = {}

# Test multiple target segments across the GOP block
for target_seg, label in [
    (10, "Vaccine Skeptics — anti-vax, anti-mandate items high"),
    (1,  "Trust-the-Science Pragmatists — trust institutions, defer to experts"),
    (7,  "Paleo Freedom Fighters — meat-heavy diet, reject government nutrition advice"),
    (6,  "Wellness Evangelists — my body my choice, natural health"),
]:
    results[target_seg] = run_test(target_seg, label)

print(f"\n{'='*70}")
print(f"  SUMMARY")
print(f"{'='*70}")
for seg, passed in results.items():
    status = "PASS" if passed else "FAIL"
    print(f"  Seg {seg:>2d} ({SEG_NAMES.get(seg, '?'):40s}): {status}")
total_pass = sum(results.values())
print(f"\n  {total_pass}/{len(results)} passed")
