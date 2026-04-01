"""
PRISM Typing Tool — Layer 1 hardcoded platform component.

Implements the segment classification algorithm:
    1. Collect B-W responses from the typing MaxDiff battery
    2. Z-score each item: z = (raw - μ) / σ
    3. Compute squared Euclidean distance to each segment centroid:
       D²_j = Σ (z_i - centroid_{i,j})²
    4. Softmax over negative distances:
       P_j = exp(-D²_j / 2) / Σ exp(-D²_k / 2)
    5. Assign to segment with highest P_j within party block

Party routing:
    GOP battery (12 items) → segments 1-10
    DEM battery (10 items + 2 attitude vectors) → segments 11-16

Loads parameters from prism_norms.db (Layer 3).
"""

import math
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from config import get_norms_db


# ── DATA CLASSES ──────────────────────────────────────────────────────────────

@dataclass
class TypingResult:
    segment_id:     int           # 1-16
    party_block:    str           # GOP or DEM
    seg_probability: float        # P for assigned segment (0-1)
    seg_gap:        float         # P_best - P_second (confidence spread)
    seg_entropy:    float         # -Σ P_j log P_j (classification certainty)
    all_probs:      dict          # {segment_id: probability} for party block
    d2_values:      dict          # {segment_id: D² distance}


# ── NORMS LOADING ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_typing_params() -> dict:
    """
    Load typing tool parameters from prism_norms.db.
    Cached after first load — parameters are fixed.
    Returns:
        {
          'items': {item_id: {battery, mu, sigma, scale_min, scale_max, item_order}},
          'centroids': {item_id: {segment_id: centroid_value}},
          'segments': {segment_id: {party_block, abbreviation}},
        }
    """
    conn = get_norms_db()

    items = {}
    for row in conn.execute(
        "SELECT item_id, battery, item_type, item_order, mu, sigma, "
        "scale_min, scale_max FROM typing_items ORDER BY battery, item_order"
    ):
        items[row[0]] = {
            "battery":    row[1],
            "item_type":  row[2],
            "item_order": row[3],
            "mu":         row[4],
            "sigma":      row[5],
            "scale_min":  row[6],
            "scale_max":  row[7],
        }

    centroids = {}
    for row in conn.execute(
        "SELECT item_id, segment_id, centroid FROM typing_centroids"
    ):
        if row[0] not in centroids:
            centroids[row[0]] = {}
        centroids[row[0]][row[1]] = row[2]

    segments = {}
    for row in conn.execute(
        "SELECT segment_id, abbreviation, party_block FROM segments"
    ):
        segments[row[0]] = {
            "abbreviation": row[1],
            "party_block":  row[2],
        }

    conn.close()
    return {"items": items, "centroids": centroids, "segments": segments}


def _get_battery_items(battery: str) -> list[str]:
    """Return ordered list of item_ids for a given battery (GOP or DEM)."""
    params = _load_typing_params()
    return sorted(
        [iid for iid, info in params["items"].items() if info["battery"] == battery],
        key=lambda iid: params["items"][iid]["item_order"]
    )


def _get_battery_segments(battery: str) -> list[int]:
    """Return segment IDs for a given battery (GOP → 1-10, DEM → 11-16)."""
    params = _load_typing_params()
    return sorted(
        [sid for sid, info in params["segments"].items() if info["party_block"] == battery]
    )


# ── CORE ALGORITHM ────────────────────────────────────────────────────────────

def z_score(raw: float, mu: float, sigma: float) -> float:
    """Normalize a raw response to Z-score."""
    if sigma == 0:
        return 0.0
    return (raw - mu) / sigma


def compute_d2(
    z_scores: dict[str, float],
    centroids: dict[str, dict[int, float]],
    segment_id: int,
) -> float:
    """
    Squared Euclidean distance from respondent's Z-scores to a segment centroid.
    D²_j = Σ (z_i - centroid_{i,j})²
    """
    d2 = 0.0
    for item_id, z in z_scores.items():
        centroid = centroids.get(item_id, {}).get(segment_id, 0.0)
        d2 += (z - centroid) ** 2
    return d2


def softmax_probs(d2_values: dict[int, float]) -> dict[int, float]:
    """
    Softmax over negative D² values.
    P_j = exp(-D²_j / 2) / Σ exp(-D²_k / 2)
    """
    exp_vals = {sid: math.exp(-d2 / 2) for sid, d2 in d2_values.items()}
    total = sum(exp_vals.values())
    return {sid: v / total for sid, v in exp_vals.items()}


def compute_entropy(probs: dict[int, float]) -> float:
    """Shannon entropy of probability distribution. Higher = more uncertain."""
    return -sum(p * math.log(p) for p in probs.values() if p > 0)


# ── MAIN TYPING FUNCTION ──────────────────────────────────────────────────────

def type_respondent(
    battery: str,
    raw_responses: dict[str, float],
) -> TypingResult:
    """
    Assign a respondent to a PRISM segment.

    Args:
        battery:       'GOP', 'DEM', or 'BOTH'
                       Determined by determine_batteries() from screener.
        raw_responses: {item_id: raw_score} for all items in the battery/batteries.
                       B-W items: -4 to +4. Attitude vectors: 1 to 7.

    Returns:
        TypingResult with segment assignment, probabilities, and diagnostics.
        For BOTH: argmax P across all 16 segments.

    Raises:
        ValueError if battery is invalid or required items are missing.
    """
    if battery not in ("GOP", "DEM", "BOTH"):
        raise ValueError(f"battery must be 'GOP', 'DEM', or 'BOTH', got '{battery}'")

    params    = _load_typing_params()
    items     = params["items"]
    centroids = params["centroids"]

    if battery == "BOTH":
        # Run both batteries, combine probability vectors across all 16 segments
        gop_result = _run_battery("GOP", raw_responses, items, centroids)
        dem_result = _run_battery("DEM", raw_responses, items, centroids)

        # Merge probability dicts — each covers its own party block
        all_probs = {**gop_result["probs"], **dem_result["probs"]}
        all_d2    = {**gop_result["d2"],    **dem_result["d2"]}

        # Normalize combined probabilities so they sum to 1
        total     = sum(all_probs.values())
        all_probs = {k: round(v / total, 6) for k, v in all_probs.items()}

        best_seg  = max(all_probs, key=all_probs.get)
        sorted_p  = sorted(all_probs.values(), reverse=True)
        gap       = round(sorted_p[0] - sorted_p[1], 6)
        entropy   = round(compute_entropy(all_probs), 6)
        party     = "GOP" if best_seg <= 10 else "DEM"

        return TypingResult(
            segment_id      = best_seg,
            party_block     = party,
            seg_probability = all_probs[best_seg],
            seg_gap         = gap,
            seg_entropy     = entropy,
            all_probs       = all_probs,
            d2_values       = {k: round(v, 4) for k, v in all_d2.items()},
        )

    else:
        # Single battery
        result   = _run_battery(battery, raw_responses, items, centroids)
        probs    = result["probs"]
        d2       = result["d2"]
        best_seg = max(probs, key=probs.get)
        sorted_p = sorted(probs.values(), reverse=True)
        gap      = round(sorted_p[0] - sorted_p[1], 6) if len(sorted_p) > 1 else sorted_p[0]
        entropy  = round(compute_entropy(probs), 6)

        return TypingResult(
            segment_id      = best_seg,
            party_block     = battery,
            seg_probability = round(probs[best_seg], 6),
            seg_gap         = gap,
            seg_entropy     = entropy,
            all_probs       = {k: round(v, 6) for k, v in probs.items()},
            d2_values       = {k: round(v, 4) for k, v in d2.items()},
        )


def _run_battery(
    battery:   str,
    raw_responses: dict[str, float],
    items:     dict,
    centroids: dict,
) -> dict:
    """
    Run a single battery (GOP or DEM) and return probs and d2 values.
    Raises ValueError if required items are missing.
    """
    battery_items    = _get_battery_items(battery)
    battery_segments = _get_battery_segments(battery)

    missing = [iid for iid in battery_items if iid not in raw_responses]
    if missing:
        raise ValueError(f"{battery} battery missing responses for: {missing}")

    # Z-score all items in this battery
    z_scores = {}
    for item_id in battery_items:
        raw  = raw_responses[item_id]
        info = items[item_id]
        raw  = max(info["scale_min"], min(info["scale_max"], float(raw)))
        z_scores[item_id] = z_score(raw, info["mu"], info["sigma"])

    # D² to each segment centroid
    d2_values = {
        seg_id: compute_d2(z_scores, centroids, seg_id)
        for seg_id in battery_segments
    }

    return {
        "probs": softmax_probs(d2_values),
        "d2":    d2_values,
    }


# ── PARTY ROUTING FROM SCREENER ───────────────────────────────────────────────
# Source: Routing & Termination sheet (PRISM_Master_Specs_03_29_26.xlsx)
# Primary branch on QBALLOT (2024 presidential vote), secondary on QPARTY.
#
# QPARTY codes:
#   1=Strong Republican  2=Not-so-strong Republican  3=Lean Republican
#   4=Independent/Other
#   5=Lean Democrat      6=Not-so-strong Democrat    7=Strong Democrat
#
# QBALLOT codes:
#   1=Trump  2=Harris  3=Someone else  (did not vote → already terminated in screener)
#
# Returns: 'GOP', 'DEM', 'BOTH', or 'TERMINATE'
#   GOP       → run GOP battery only  (segments 1-10)
#   DEM       → run DEM battery only  (segments 11-16)
#   BOTH      → run both batteries, assign to argmax P across all 16 segments
#   TERMINATE → true independent, do not proceed to typing

def determine_batteries(qballot: int, qparty: int) -> str:
    """
    Determine which typing battery/batteries to administer.

    Args:
        qballot: 2024 presidential vote (1=Trump, 2=Harris, 3=Other)
        qparty:  Party identification (1-7, see codes above)

    Returns:
        'GOP', 'DEM', 'BOTH', or 'TERMINATE'
    """
    if qballot == 1:          # Voted Trump
        if qparty <= 4:       # Strong R → Independent
            return "GOP"
        else:                 # Lean D → Strong D (cross-pressured)
            return "BOTH"

    elif qballot == 2:        # Voted Harris
        if qparty <= 3:       # Strong R → Lean R (cross-pressured)
            return "BOTH"
        else:                 # Independent → Strong D
            return "DEM"

    elif qballot == 3:        # Voted Other
        if qparty <= 2:       # Strong R, Not-so-strong R
            return "GOP"
        elif qparty == 3:     # Lean R (cross-pressured third-party voter)
            return "BOTH"
        elif qparty == 4:     # True independent / neither lean
            return "TERMINATE"
        else:                 # Lean D → Strong D
            return "DEM"

    # Fallback — should not be reached if screener terminates non-voters
    return "TERMINATE"
