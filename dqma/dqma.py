"""
PRISM Dynamic Quota Management Algorithm (DQMA) v2.0
Implements the continuous ROI-responsive quota engine from the DQMA spec.

Three entry points for the survey platform:
    route_respondent(conn, resp_id, segment_id, seg_probability, study_registry)
    record_exit(conn, resp_id, study_code, segment_id, exit_type)
    rebalance(conn, study_code)
"""

import math
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class Phase(str, Enum):
    SEED       = "SEED"
    EMERGING   = "EMERGING"
    RESPONSIVE = "RESPONSIVE"
    COMMITTED  = "COMMITTED"
    SCORING    = "SCORING"

class ExitType(str, Enum):
    COMPLETE   = "complete"
    TERMINATE  = "terminate"
    OVERQUOTA  = "overquota"


# ── PARAMETERS ────────────────────────────────────────────────────────────────

class Params:
    """All tunable DQMA parameters in one place."""

    # Phase confidence thresholds
    KAPPA_SEED_MAX       = 0.15
    KAPPA_EMERGING_MAX   = 0.40
    KAPPA_RESPONSIVE_MAX = 0.70

    # Phase elasticity (fraction of n_base that quota can flex)
    ELASTICITY = {
        Phase.SEED:       0.00,
        Phase.EMERGING:   0.30,
        Phase.RESPONSIVE: 0.60,
        Phase.COMMITTED:  1.00,
        Phase.SCORING:    1.00,
    }

    # Minimum quota as fraction of n_base
    PHASE_MIN_FRACTION = {
        Phase.SEED:       1.00,
        Phase.EMERGING:   0.70,
        Phase.RESPONSIVE: 0.50,
        Phase.COMMITTED:  0.33,
        Phase.SCORING:    0.00,
    }

    # Tier allocation budget (fraction of N_j)
    TIER_BUDGET = {1: 0.45, 2: 0.30, 3: 0.25}

    # Tier sample ceilings per segment
    TIER_CEILING = {1: 400, 2: 200, 3: None}  # None = n_base

    # Tier sample floors per segment
    TIER_FLOOR = {1: 250, 2: 125, 3: None}

    # Tier cardinality constraints
    TIER_MAX_COUNT = {1: 4, 2: 3}

    # Minimum n per segment before ROI components are readable
    ROI_MIN_N = {
        "persuasion": 25,
        "coalition":  20,
        "activation": 25,
        "influence":  15,
    }

    # OQT
    OQT_SEED_CAP            = 20    # Max OQT per segment during SEED
    OQT_ABSORPTION_BASE     = 1.0   # Base threshold
    OQT_ABSORPTION_KAPPA_WT = 0.2   # How much kappa tightens the threshold

    # Confidence calculation
    NORM_BOOST_PER_STUDY    = 0.10
    NORM_BOOST_MAX          = 0.30
    NORM_MIN_STUDIES        = 2

    # Rebalance trigger
    REBALANCE_EVERY_N       = 50    # Completions
    REBALANCE_EVERY_HOURS   = 6

    # ROI weights (client-adjustable)
    ROI_WEIGHTS = {
        "persuasion": 0.30,
        "coalition":  0.25,
        "activation": 0.25,
        "influence":  0.20,
    }

    # Feasibility
    INCIDENCE_CAP           = 10.0
    SUPPLY_CRITICAL         = 0.80
    SUPPLY_TIGHT            = 1.50

    # Dynamic segment weight
    WEIGHT_CLAMP_MIN = 0.1
    WEIGHT_CLAMP_MAX = 20.0


# ── CONFIDENCE ────────────────────────────────────────────────────────────────

def compute_confidence(
    C: int,
    persuasion_n: int,
    coalition_n: int,
    activation_n: int,
    influence_n: int,
    n_norm_studies: int,
) -> float:
    """
    Compute kappa (confidence index, 0-1) for a single segment × study cell.
    Spec Section 3.2.
    """
    # Sample size factor: rises steeply to ~25, slowly to ~75
    sample_factor = 1.0 - math.exp(-C / 36.0) if C > 0 else 0.0

    # Component coverage
    component_ns = {
        "persuasion": persuasion_n,
        "coalition":  coalition_n,
        "activation": activation_n,
        "influence":  influence_n,
    }
    n_available = sum(
        1 for key, n in component_ns.items()
        if n >= Params.ROI_MIN_N[key]
    )
    coverage_factor = n_available / 4.0
    if n_available < 2:
        coverage_factor *= 0.5

    # Normative boost
    norm_factor = 0.0
    if n_norm_studies >= Params.NORM_MIN_STUDIES:
        norm_factor = min(
            Params.NORM_BOOST_MAX,
            Params.NORM_BOOST_PER_STUDY * n_norm_studies
        )

    kappa = min(1.0, sample_factor * coverage_factor + norm_factor)
    return round(kappa, 4)


def study_confidence(kappas: list[float]) -> float:
    """
    Aggregate cell-level kappas to study-level confidence.
    Weighted toward the weakest link. Spec Section 3.2.
    """
    if not kappas:
        return 0.0
    sorted_k = sorted(kappas)
    p25 = sorted_k[max(0, len(sorted_k) // 4)]
    k_min = sorted_k[0]
    return round(0.7 * p25 + 0.3 * k_min, 4)


# ── PHASE ─────────────────────────────────────────────────────────────────────

def compute_phase(kappa_j: float, client_tiers_approved: bool) -> Phase:
    """Determine study phase from confidence and client approval. Spec 3.3."""
    if kappa_j < Params.KAPPA_SEED_MAX:
        return Phase.SEED
    elif kappa_j < Params.KAPPA_EMERGING_MAX:
        return Phase.EMERGING
    elif kappa_j < Params.KAPPA_RESPONSIVE_MAX or not client_tiers_approved:
        return Phase.RESPONSIVE
    else:
        return Phase.COMMITTED


# ── EFFECTIVE ROI ─────────────────────────────────────────────────────────────

def bayesian_shrinkage(n_obs: int, norm_std: float) -> float:
    """
    Shrinkage factor lambda: 0 = trust norms, 1 = trust observed.
    Spec Section 9.2.
    """
    if n_obs <= 0:
        return 0.0
    tau_sq = norm_std ** 2
    sigma_sq = 0.5 / max(1, n_obs)
    lam = tau_sq / (tau_sq + sigma_sq)
    return min(1.0, max(0.0, lam))


def effective_roi(
    C: int,
    roi_mean: Optional[float],
    persuasion_n: int,
    coalition_n: int,
    activation_n: int,
    influence_n: int,
    kappa: float,
    norm_roi: float,
    norm_std: float,
    norm_n_studies: int,
) -> float:
    """
    Blend observed, partial, and normative ROI. Spec Section 4.3.
    Returns mean-anchored ROI index (1.0 = average).
    """
    component_counts = {
        "persuasion": persuasion_n,
        "coalition":  coalition_n,
        "activation": activation_n,
        "influence":  influence_n,
    }
    n_components = sum(
        1 for key, n in component_counts.items()
        if n >= Params.ROI_MIN_N[key]
    )

    # Full ROI available
    if n_components == 4 and C >= 30 and roi_mean is not None:
        lam = bayesian_shrinkage(C, norm_std)
        return round(lam * roi_mean + (1.0 - lam) * norm_roi, 4)

    # Partial ROI available
    if n_components >= 1 and C >= 15 and roi_mean is not None:
        partial_weight = kappa * (n_components / 4.0)
        return round(partial_weight * roi_mean + (1.0 - partial_weight) * norm_roi, 4)

    # Norms only
    if norm_n_studies >= Params.NORM_MIN_STUDIES:
        return round(norm_roi, 4)

    # No signal
    return 1.0


# ── ELASTIC QUOTA ─────────────────────────────────────────────────────────────

def elastic_quota(
    roi_eff: float,
    kappa: float,
    phase: Phase,
    n_base: int,
    C: int,
    algo_tier: int,
    N_j: int,
) -> int:
    """
    Compute current elastic quota for a segment × study cell. Spec Section 4.1.
    """
    q_equal = N_j / 16.0

    # ROI-weighted target from algorithmic tier
    q_roi = roi_weighted_target(roi_eff, algo_tier, N_j)

    # Blend equal and ROI-weighted by confidence
    q_elastic = (1.0 - kappa) * q_equal + kappa * q_roi

    # Phase elasticity bounds (asymmetric ceiling)
    elasticity = Params.ELASTICITY[phase]
    q_floor   = q_equal * (1.0 - elasticity)
    q_ceiling = q_equal * (1.0 + elasticity * 3.0)
    q_bounded = max(q_floor, min(q_ceiling, q_elastic))

    # Absolute minimum for estimation
    min_fraction = Params.PHASE_MIN_FRACTION[phase]
    q_min = n_base * min_fraction

    result = max(q_bounded, q_min)

    # Never go below current completions
    result = max(result, C)

    return max(0, round(result))


def roi_weighted_target(roi_eff: float, algo_tier: int, N_j: int) -> float:
    """
    Target allocation if we had perfect ROI information. Spec Section 4.2.
    Note: Full implementation requires all-segment ROI values for normalization.
    This computes the tier-budget share — caller normalizes across segments.
    """
    budget = N_j * Params.TIER_BUDGET.get(algo_tier, 0.25)
    floor  = Params.TIER_FLOOR.get(algo_tier)
    ceil_  = Params.TIER_CEILING.get(algo_tier)

    # Single-segment estimate — will be normalized across tier peers in rebalance
    target = budget / max(1, {1: 3, 2: 2, 3: 10}.get(algo_tier, 10))

    if floor is not None:
        target = max(target, floor)
    if ceil_ is not None:
        target = min(target, ceil_)

    return target


# ── ALGORITHMIC TIER ASSIGNMENT ───────────────────────────────────────────────

def assign_tiers(roi_values: dict[int, float]) -> dict[int, int]:
    """
    Assign algorithmic tiers to all 16 segments based on effective ROI.
    Enforces cardinality constraints: max 4 T1, max 3 T2.
    Spec Section 4.4.

    Args:
        roi_values: {segment_id: roi_effective}
    Returns:
        {segment_id: tier}
    """
    if not roi_values:
        return {s: 3 for s in range(1, 17)}

    values = list(roi_values.values())
    sigma  = (sum((v - 1.0)**2 for v in values) / max(1, len(values))) ** 0.5
    tau_1  = max(1.10, 1.0 + 0.5 * sigma)
    tau_2  = 1.0

    # Raw tier assignments
    raw = {}
    for seg_id, roi in roi_values.items():
        if roi >= tau_1:
            raw[seg_id] = 1
        elif roi >= tau_2:
            raw[seg_id] = 2
        else:
            raw[seg_id] = 3

    # Enforce cardinality: max 4 T1
    t1_segs = sorted(
        [s for s, t in raw.items() if t == 1],
        key=lambda s: -roi_values[s]
    )
    if len(t1_segs) > Params.TIER_MAX_COUNT[1]:
        for s in t1_segs[Params.TIER_MAX_COUNT[1]:]:
            raw[s] = 2

    # Enforce cardinality: max 3 T2
    t2_segs = sorted(
        [s for s, t in raw.items() if t == 2],
        key=lambda s: -roi_values[s]
    )
    if len(t2_segs) > Params.TIER_MAX_COUNT[2]:
        for s in t2_segs[Params.TIER_MAX_COUNT[2]:]:
            raw[s] = 3

    return raw


# ── OQT ABSORPTION POLICY ─────────────────────────────────────────────────────

def should_absorb_oqt(
    roi_eff: float,
    kappa: float,
    phase: Phase,
    oqt_count: int,
    C: int,
) -> bool:
    """
    Decide whether to absorb an over-quota respondent. Spec Section 5.2.
    """
    # SEED phase: absorb everything up to cap
    if phase == Phase.SEED:
        return oqt_count < Params.OQT_SEED_CAP

    # OQT flood check: if OQT > 20% of completions and ROI is low, terminate
    if oqt_count > 0.20 * max(1, C) and roi_eff < 0.90:
        return False

    # ROI-gated absorption threshold tightens with confidence
    threshold = Params.OQT_ABSORPTION_BASE - (Params.OQT_ABSORPTION_KAPPA_WT * kappa)
    return roi_eff >= threshold


# ── DYNAMIC SEGMENT WEIGHT ────────────────────────────────────────────────────

def dynamic_segment_weight(
    Q: int,
    C: int,
    kappa: float,
    pop_share: float,
    base_rate: float = 0.05,
) -> float:
    """
    Compute routing weight for segment × study cell. Spec Section 6.3.
    """
    if C == 0:
        # No data — use population estimate
        raw = min(
            Params.WEIGHT_CLAMP_MAX,
            Q / max(1.0, pop_share * base_rate * 1000)
        )
    else:
        raw = Q / C

    # Dampen extreme weights at low confidence
    damping  = 0.5 + 0.5 * kappa
    dampened = 1.0 + (raw - 1.0) * damping

    return max(Params.WEIGHT_CLAMP_MIN, min(Params.WEIGHT_CLAMP_MAX, dampened))


# ── ROUTING SCORE ─────────────────────────────────────────────────────────────

def compute_quota_balance_factor(
    study_code: str,
    screener_data: dict,
    quota_targets: list[dict],
    quota_state: dict,
) -> float:
    """
    Compute routing score multiplier from soft quota targets.
    Returns 1.0 if all cells within tolerance or no soft quotas defined.
    Returns penalty_floor if respondent's cell is over tolerance.
    Never returns 0 — soft quotas never hard-exclude.

    quota_state: {quota_id: {cell_value: C}} — current counts per cell
    Spec: quota_targets section of study config.
    """
    if not quota_targets:
        return 1.0

    factor = 1.0

    for qt in quota_targets:
        if qt.get('enforcement') != 'soft':
            continue

        var          = qt['var']
        quota_id     = qt['quota_id']
        penalty_floor = qt.get('penalty_floor', 0.75)
        cells        = qt.get('cells', [])

        # Get respondent's value for this quota variable
        resp_val = screener_data.get(var)
        if resp_val is None:
            continue

        # Find the matching cell definition
        cell_def = next((c for c in cells if c['value'] == resp_val), None)
        if cell_def is None:
            continue

        target_share = cell_def.get('target_share', 0.0)
        tolerance    = cell_def.get('tolerance', 0.10)

        # Get current counts from quota_state
        cell_counts  = quota_state.get(quota_id, {})
        total_n      = sum(cell_counts.values())
        cell_n       = cell_counts.get(str(resp_val), 0)

        if total_n == 0:
            continue

        actual_share = cell_n / total_n
        overage      = actual_share - (target_share + tolerance)

        if overage > 0:
            # Cell is over tolerance — apply progressive penalty
            # At tolerance boundary: factor = 1.0
            # As overage grows: factor approaches penalty_floor
            penalty = 1.0 - (overage / (1.0 - target_share)) * (1.0 - penalty_floor)
            cell_factor = max(penalty_floor, penalty)
            factor = min(factor, cell_factor)

    return round(max(0.01, factor), 4)


def check_hard_quota_caps(
    study_code: str,
    screener_data: dict,
    quota_targets: list[dict],
    quota_state: dict,
) -> bool:
    """
    Check whether any hard quota caps are reached for this respondent.
    Returns True if respondent should be excluded (any hard cap reached).
    Returns False if all clear.

    When a hard cap is reached, the platform should also update
    study_registry.eligibility_rules to inject a result=0 rule
    for that cell, so future respondents are excluded at the
    eligibility evaluation stage without hitting this function.
    Spec: quota_targets hard_cohort enforcement.
    """
    for qt in quota_targets:
        if qt.get('enforcement') != 'hard':
            continue

        var      = qt['var']
        quota_id = qt['quota_id']
        cells    = qt.get('cells', [])

        resp_val = screener_data.get(var)
        if resp_val is None:
            continue

        cell_def = next((c for c in cells if c['value'] == resp_val), None)
        if cell_def is None:
            continue

        target_n   = cell_def.get('target_n')
        if target_n is None:
            continue

        cell_counts = quota_state.get(quota_id, {})
        cell_n      = cell_counts.get(str(resp_val), 0)

        if cell_n >= target_n:
            logger.info(
                f"Hard quota cap reached: study={study_code} "
                f"quota={quota_id} cell={resp_val} n={cell_n}/{target_n}"
            )
            return True

    return False


def routing_score(
    segment_id: int,
    study_code: str,
    Q: int,
    C: int,
    OQT: int,
    kappa: float,
    roi_eff: float,
    phase: Phase,
    study_weight: float,
    seg_probability: float,
    pop_share: float,
    can_absorb_oqt: bool,
    quota_balance_factor: float = 1.0,
) -> float:
    """
    Composite routing score for one segment × study pair. Spec Section 6.2.
    Returns 0 if quota is full and OQT absorption is not eligible.

    quota_balance_factor: 0.0-1.0 multiplier from soft quota targets.
    Computed by compute_quota_balance_factor() before this call.
    Never reduces score to 0 — soft quotas nudge, not hard-exclude.
    """
    remaining = max(0, Q - C)

    # Hard zero if quota full and OQT not eligible
    if remaining == 0 and not can_absorb_oqt:
        return 0.0

    # For OQT absorption case, use a small positive urgency
    urgency = remaining / max(1, Q) if remaining > 0 else 0.05

    w_seg = dynamic_segment_weight(Q, C, kappa, pop_share)

    # Boost study weight in RESPONSIVE+ for above-average ROI segments
    adj_study_weight = study_weight
    if phase in (Phase.RESPONSIVE, Phase.COMMITTED):
        adj_study_weight = study_weight * (1.0 + 0.5 * (roi_eff - 1.0))

    score = adj_study_weight * urgency * w_seg * roi_eff * seg_probability
    score = score * quota_balance_factor
    return max(0.0, score)


# ── MAIN ENTRY POINTS ─────────────────────────────────────────────────────────

def evaluate_eligibility(screener_data: dict, eligibility_rules: list[dict]) -> float:
    """
    Evaluate study eligibility rules against respondent screener responses.
    Returns φ_j — the study router weight for this respondent:
        0   = NOT_ELIGIBLE (hard exclude)
        2   = SECONDARY_MATCH
        3   = PRIMARY_MATCH
        4   = STRONG_PRIMARY_MATCH

    eligibility_rules is a list of rule dicts from study_registry.eligibility_rules,
    evaluated in order. First matching rule wins.

    Rule format:
        {"var": "INS1", "op": "eq", "value": 2,   "result": 0}   # hard exclude
        {"var": "INS2", "op": "in", "value": [1,2,3], "result": 3}  # primary
        {"var": "*",    "op": "default",            "result": 2}   # catch-all

    Spec Section 6.4.
    """
    for rule in eligibility_rules:
        var = rule['var']
        op  = rule['op']

        if op == 'default':
            return float(rule['result'])

        val = screener_data.get(var)
        if val is None:
            continue

        match = False
        if op == 'eq':
            match = (val == rule['value'])
        elif op == 'ne':
            match = (val != rule['value'])
        elif op == 'in':
            match = (val in rule['value'])
        elif op == 'not_in':
            match = (val not in rule['value'])
        elif op == 'gte':
            match = (val >= rule['value'])
        elif op == 'lte':
            match = (val <= rule['value'])

        if match:
            return float(rule['result'])

    # No rule matched and no default — treat as secondary match
    return 2.0


def route_respondent(
    conn,
    resp_id: str,
    segment_id: int,
    seg_probability: float,
    screener_data: dict,
) -> Optional[str]:
    """
    Route a typed respondent to the best active study.
    Returns study_code or None if no study can accept this respondent.

    Loads all active studies internally, evaluates φ_j(r) per study
    from eligibility rules, computes routing scores, and assigns to
    the highest-scoring study.

    Uses SELECT FOR UPDATE to lock the quota row before incrementing C.

    Spec Sections 6.2, 6.4, 11.2.
    """
    import psycopg2.extras
    import random
    import json

    scores = {}
    states = {}

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

        # Load all active non-closed studies with their eligibility rules
        cur.execute("""
            SELECT study_code, router_weight, n_base, n_total_target,
                   eligibility_rules, phase
            FROM study_registry
            WHERE active = TRUE AND phase != 'CLOSED'
        """)
        active_studies = cur.fetchall()

        for study_row in active_studies:
            study_code = study_row['study_code']

            # ── Evaluate φ_j(r) from eligibility rules ────────────────────────
            rules_raw = study_row['eligibility_rules']
            if rules_raw:
                rules = json.loads(rules_raw) if isinstance(rules_raw, str) else rules_raw
            else:
                rules = [{"var": "*", "op": "default", "result": 3}]

            phi_j = evaluate_eligibility(screener_data, rules)

            # Hard exclude — study gets score = 0, skip entirely
            if phi_j == 0:
                continue

            # Load segment × study quota state
            cur.execute("""
                SELECT
                    ds.Q, ds.C, ds.OQT, ds.TERM,
                    ds.phase, ds.kappa, ds.roi_effective, ds.algo_tier,
                    sn.pop_share
                FROM dqma_state ds
                JOIN segment_norms sn ON sn.segment_id = ds.segment_id
                WHERE ds.study_code = %s AND ds.segment_id = %s
            """, (study_code, segment_id))
            row = cur.fetchone()
            if row is None:
                continue

            phase   = Phase(row['phase'])
            kappa   = row['kappa']
            Q       = row['Q']
            C       = row['C']
            OQT     = row['OQT']
            roi_eff = row['roi_effective'] or 1.0

            can_oqt = should_absorb_oqt(roi_eff, kappa, phase, OQT, C)

            # φ_j is the base study_weight in the routing score formula
            score = routing_score(
                segment_id    = segment_id,
                study_code    = study_code,
                Q=Q, C=C, OQT=OQT,
                kappa         = kappa,
                roi_eff       = roi_eff,
                phase         = phase,
                study_weight  = phi_j,    # ← eligibility weight drives score
                seg_probability = seg_probability,
                pop_share     = row['pop_share'],
                can_absorb_oqt = can_oqt,
            )

            scores[study_code] = score
            state = dict(row)
            state['phi_j']        = phi_j
            state['can_oqt']      = can_oqt
            state['router_weight'] = phi_j
            states[study_code]    = state

    if not scores or max(scores.values()) == 0.0:
        logger.info(f"No eligible study for resp={resp_id} seg={segment_id}")
        return None

    # Best study by score — random tiebreak
    max_score = max(scores.values())
    candidates = [s for s, v in scores.items() if v == max_score]
    best = random.choice(candidates)

    # ── Lock and increment ─────────────────────────────────────────────────────
    state = states[best]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT Q, C, OQT FROM dqma_state
            WHERE study_code = %s AND segment_id = %s
            FOR UPDATE
        """, (best, segment_id))
        locked = cur.fetchone()
        if locked is None:
            conn.rollback()
            return None

        Q_now, C_now, OQT_now = locked

        if C_now < Q_now:
            cur.execute("""
                UPDATE dqma_state SET C = C + 1, updated_at = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (best, segment_id))
            cur.execute("""
                UPDATE respondents
                SET study_code = %s, status = 'active'
                WHERE resp_id = %s
            """, (best, resp_id))
            conn.commit()
            logger.info(f"Routed resp={resp_id} seg={segment_id} → {best} φ={state['phi_j']}")
            return best

        elif state['can_oqt'] and should_absorb_oqt(
            state['roi_effective'] or 1.0,
            state['kappa'], Phase(state['phase']), OQT_now, C_now
        ):
            cur.execute("""
                UPDATE dqma_state
                SET OQT = OQT + 1,
                    Q   = GREATEST(Q, C + OQT + 1),
                    updated_at = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (best, segment_id))
            cur.execute("""
                UPDATE respondents
                SET study_code = %s, status = 'active'
                WHERE resp_id = %s
            """, (best, resp_id))
            conn.commit()
            logger.info(f"OQT absorbed resp={resp_id} seg={segment_id} → {best}")
            return best

        else:
            # Quota filled between scoring and locking — remove and retry
            conn.rollback()
            remaining_scores = {s: v for s, v in scores.items() if s != best}
            if not remaining_scores:
                return None
            # Rebuild screener_data pass-through for retry
            return _route_from_scores(
                conn, resp_id, segment_id, remaining_scores, states
            )


def _route_from_scores(
    conn,
    resp_id: str,
    segment_id: int,
    scores: dict,
    states: dict,
) -> Optional[str]:
    """
    Retry routing from a pre-computed scores dict (used after quota collision).
    Avoids re-querying the database for scores we already have.
    """
    import random

    if not scores or max(scores.values()) == 0.0:
        return None

    max_score = max(scores.values())
    candidates = [s for s, v in scores.items() if v == max_score]
    best = random.choice(candidates)
    state = states[best]

    with conn.cursor() as cur:
        cur.execute("""
            SELECT Q, C, OQT FROM dqma_state
            WHERE study_code = %s AND segment_id = %s
            FOR UPDATE
        """, (best, segment_id))
        locked = cur.fetchone()
        if locked is None:
            conn.rollback()
            return None

        Q_now, C_now, OQT_now = locked

        if C_now < Q_now:
            cur.execute("""
                UPDATE dqma_state SET C = C + 1, updated_at = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (best, segment_id))
            cur.execute("""
                UPDATE respondents SET study_code = %s, status = 'active'
                WHERE resp_id = %s
            """, (best, resp_id))
            conn.commit()
            return best

        elif state['can_oqt'] and should_absorb_oqt(
            state['roi_effective'] or 1.0,
            state['kappa'], Phase(state['phase']), OQT_now, C_now
        ):
            cur.execute("""
                UPDATE dqma_state
                SET OQT = OQT + 1,
                    Q   = GREATEST(Q, C + OQT + 1),
                    updated_at = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (best, segment_id))
            cur.execute("""
                UPDATE respondents SET study_code = %s, status = 'active'
                WHERE resp_id = %s
            """, (best, resp_id))
            conn.commit()
            return best

        else:
            conn.rollback()
            remaining = {s: v for s, v in scores.items() if s != best}
            return _route_from_scores(conn, resp_id, segment_id, remaining, states)


def record_exit(
    conn,
    resp_id: str,
    study_code: str,
    segment_id: int,
    exit_type: ExitType,
) -> None:
    """
    Record a respondent exit. Updates respondents status and dqma_state counters.
    Called by survey platform on complete / terminate / overquota.
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE respondents
            SET status = %s, complete_ts = NOW()
            WHERE resp_id = %s
        """, (exit_type.value, resp_id))

        if exit_type == ExitType.TERMINATE:
            cur.execute("""
                UPDATE dqma_state
                SET TERM = TERM + 1, updated_at = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (study_code, segment_id))

    conn.commit()
    logger.info(f"Exit recorded: resp={resp_id} study={study_code} seg={segment_id} type={exit_type}")


# ── REBALANCE CYCLE ───────────────────────────────────────────────────────────

def rebalance(conn, study_code: str) -> dict:
    """
    Full rebalancing cycle for one study. Spec Section 7.1.
    Reads current state, recomputes confidence / ROI / tiers / quotas,
    writes updated state back to dqma_state.

    Returns summary dict for logging / admin dashboard.
    """
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

        # Load study parameters
        cur.execute("""
            SELECT n_base, n_total_target, router_weight, client_tiers_approved
            FROM study_registry WHERE study_code = %s
        """, (study_code,))
        study = cur.fetchone()
        if study is None:
            raise ValueError(f"Study {study_code} not found in registry")

        n_base    = study['n_base']
        N_j       = study['n_total_target'] or n_base * 16
        client_approved = study['client_tiers_approved']

        # Load all 16 segment states + norms
        cur.execute("""
            SELECT
                ds.segment_id,
                ds.Q, ds.C, ds.OQT, ds.TERM,
                ds.phase, ds.kappa, ds.roi_mean, ds.roi_se, ds.roi_effective,
                ds.persuasion_n, ds.coalition_n, ds.activation_n, ds.influence_n,
                ds.algo_tier, ds.client_tier, ds.tier_locked,
                sn.pop_share, sn.roi_mean AS norm_roi,
                sn.roi_std AS norm_std, sn.n_studies AS norm_n_studies
            FROM dqma_state ds
            JOIN segment_norms sn ON sn.segment_id = ds.segment_id
            WHERE ds.study_code = %s
            ORDER BY ds.segment_id
        """, (study_code,))
        rows = {r['segment_id']: dict(r) for r in cur.fetchall()}

        if not rows:
            logger.warning(f"No dqma_state rows for study {study_code}")
            return {}

        # ── Step 1: Update ROI aggregates from respondent_roi ──────────────
        cur.execute("""
            SELECT
                segment_id,
                COUNT(*)                                        AS n,
                AVG(roi_total)                                  AS roi_mean,
                STDDEV(roi_total) / NULLIF(SQRT(COUNT(*)),0)    AS roi_se,
                SUM(has_movement::int)                          AS movement_n,
                SUM(has_position::int)                          AS position_n,
                SUM(has_activation::int)                        AS activation_n,
                SUM(has_influence::int)                         AS influence_n
            FROM respondent_roi
            WHERE study_code = %s
            GROUP BY segment_id
        """, (study_code,))
        roi_agg = {r['segment_id']: dict(r) for r in cur.fetchall()}

        # ── Step 2: Compute confidence (kappa) per cell ────────────────────
        kappas = {}
        for seg_id, row in rows.items():
            agg = roi_agg.get(seg_id, {})
            k = compute_confidence(
                C             = row['C'],
                persuasion_n  = agg.get('movement_n',  0) or 0,
                coalition_n   = agg.get('position_n',  0) or 0,
                activation_n  = agg.get('activation_n',0) or 0,
                influence_n   = agg.get('influence_n', 0) or 0,
                n_norm_studies= row['norm_n_studies'],
            )
            kappas[seg_id] = k
            rows[seg_id]['kappa_new'] = k

        # ── Step 3: Study-level confidence → phase ─────────────────────────
        kappa_j = study_confidence(list(kappas.values()))
        phase_j = compute_phase(kappa_j, client_approved)

        # ── Step 4: Effective ROI per cell ─────────────────────────────────
        roi_effs = {}
        for seg_id, row in rows.items():
            agg = roi_agg.get(seg_id, {})
            roi_effs[seg_id] = effective_roi(
                C             = row['C'],
                roi_mean      = agg.get('roi_mean'),
                persuasion_n  = agg.get('movement_n',  0) or 0,
                coalition_n   = agg.get('position_n',  0) or 0,
                activation_n  = agg.get('activation_n', 0) or 0,
                influence_n   = agg.get('influence_n',  0) or 0,
                kappa         = kappas[seg_id],
                norm_roi      = row['norm_roi'],
                norm_std      = row['norm_std'],
                norm_n_studies= row['norm_n_studies'],
            )

        # ── Step 5: Algorithmic tier assignment ────────────────────────────
        tiers = assign_tiers(roi_effs)

        # ── Step 6: Elastic quotas ─────────────────────────────────────────
        new_quotas = {}
        for seg_id, row in rows.items():
            # If client tiers are locked, respect them
            if row['tier_locked'] and row['client_tier'] is not None:
                effective_tier = row['client_tier']
            else:
                effective_tier = tiers[seg_id]

            Q_new = elastic_quota(
                roi_eff   = roi_effs[seg_id],
                kappa     = kappas[seg_id],
                phase     = phase_j,
                n_base    = n_base,
                C         = row['C'],
                algo_tier = effective_tier,
                N_j       = N_j,
            )
            new_quotas[seg_id] = Q_new

        # ── Step 7: Anomaly detection ──────────────────────────────────────
        flags = _detect_anomalies(rows, roi_effs, roi_agg)

        # ── Step 8: Write updated state ────────────────────────────────────
        for seg_id, row in rows.items():
            agg = roi_agg.get(seg_id, {})
            cur.execute("""
                UPDATE dqma_state SET
                    Q               = %s,
                    phase           = %s,
                    kappa           = %s,
                    roi_mean        = %s,
                    roi_se          = %s,
                    roi_effective   = %s,
                    movement_n      = %s,
                    position_n      = %s,
                    activation_n    = %s,
                    influence_n     = %s,
                    algo_tier       = %s,
                    oqt_flood_flag  = %s,
                    roi_anomaly_flag= %s,
                    updated_at      = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (
                new_quotas[seg_id],
                phase_j.value,
                kappas[seg_id],
                agg.get('roi_mean'),
                agg.get('roi_se'),
                roi_effs[seg_id],
                agg.get('movement_n',  0) or 0,
                agg.get('position_n',  0) or 0,
                agg.get('activation_n',0) or 0,
                agg.get('influence_n', 0) or 0,
                tiers[seg_id],
                flags.get(seg_id, {}).get('oqt_flood',    False),
                flags.get(seg_id, {}).get('roi_anomaly',  False),
                study_code, seg_id,
            ))

        # Update study-level phase in registry
        cur.execute("""
            UPDATE study_registry
            SET phase = %s, kappa = %s, updated_at = NOW()
            WHERE study_code = %s
        """, (phase_j.value, kappa_j, study_code))

    conn.commit()

    # Surface tier recommendations if entering RESPONSIVE for first time
    if phase_j == Phase.RESPONSIVE:
        _check_surface_recommendations(study_code, rows, tiers, roi_effs, kappas)

    summary = {
        "study_code": study_code,
        "phase": phase_j.value,
        "kappa_j": kappa_j,
        "quotas": new_quotas,
        "tiers": tiers,
        "roi_effective": roi_effs,
        "flags": flags,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"Rebalance complete: {study_code} phase={phase_j.value} kappa={kappa_j:.3f}")
    return summary


# ── CLIENT TIER LOCK ──────────────────────────────────────────────────────────

def client_tier_lock(conn, study_code: str, client_tiers: dict[int, int]) -> None:
    """
    Apply client-approved tier assignments and transition to COMMITTED.
    Spec Section 8.2.

    Args:
        client_tiers: {segment_id: tier} for all 16 segments
    """
    with conn.cursor() as cur:
        for seg_id, tier in client_tiers.items():
            cur.execute("""
                UPDATE dqma_state
                SET client_tier = %s, tier_locked = TRUE, updated_at = NOW()
                WHERE study_code = %s AND segment_id = %s
            """, (tier, study_code, seg_id))

        cur.execute("""
            UPDATE study_registry
            SET client_tiers_approved = TRUE, updated_at = NOW()
            WHERE study_code = %s
        """, (study_code,))

    conn.commit()

    # Immediate rebalance to apply locked tiers
    rebalance(conn, study_code)
    logger.info(f"Client tiers locked for {study_code}. Transitioned to COMMITTED.")


# ── INITIALIZATION ────────────────────────────────────────────────────────────

def initialize_study(conn, study_code: str, n_base: int = 75) -> None:
    """
    Initialize dqma_state for all 16 segments for a new study.
    Checks for normative maturity and seeds accordingly. Spec Section 11.1.
    """
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

        # Check normative maturity
        cur.execute("SELECT MIN(n_studies) AS min_studies FROM segment_norms")
        min_studies = cur.fetchone()['min_studies'] or 0
        norm_mature = min_studies >= 9  # Phase 3: 9+ studies

        cur.execute("SELECT segment_id, roi_mean, pop_share FROM segment_norms")
        norms = {r['segment_id']: dict(r) for r in cur.fetchall()}

        # Compute seed quotas
        N_j = n_base * 16
        seed_quotas = {}

        if norm_mature:
            # Norm-adjusted seeding
            n_min      = max(25, round(n_base * 0.40))
            n_flexible = N_j - 16 * n_min
            total_weight = sum(max(0.5, n['roi_mean']) for n in norms.values())
            for seg_id, norm in norms.items():
                weight = max(0.5, norm['roi_mean'])
                share  = weight / total_weight
                seed_quotas[seg_id] = n_min + round(n_flexible * share)
        else:
            # Equal allocation
            for seg_id in range(1, 17):
                seed_quotas[seg_id] = n_base

        # Compute initial kappa from norms
        for seg_id in range(1, 17):
            norm = norms.get(seg_id, {})
            n_studies = norm.get('n_studies', 0) if isinstance(norm, dict) else 0
            if n_studies == 0:
                kappa_init = 0.0
            else:
                kappa_init = min(
                    Params.NORM_BOOST_MAX,
                    Params.NORM_BOOST_PER_STUDY * n_studies
                )

            cur.execute("""
                INSERT INTO dqma_state
                    (study_code, segment_id, Q, C, OQT, TERM,
                     phase, kappa, roi_effective)
                VALUES (%s, %s, %s, 0, 0, 0, 'SEED', %s, 1.0)
                ON CONFLICT (study_code, segment_id) DO NOTHING
            """, (study_code, seg_id, seed_quotas[seg_id], kappa_init))

        # Register study
        eligibility_rules = json.dumps(
            study_config.get('eligibility', {}).get('rules', [
                {"var": "*", "op": "default", "result": 3}
            ])
        )
        cur.execute("""
            INSERT INTO study_registry
                (study_code, n_base, n_total_target, phase, kappa,
                 roi_model, eligibility_rules)
            VALUES (%s, %s, %s, 'SEED', 0.0, %s, %s)
            ON CONFLICT (study_code) DO NOTHING
        """, (
            study_code, n_base, N_j,
            study_config.get('roi_config', {}).get('roi_model', 'advocacy'),
            eligibility_rules,
        ))

    conn.commit()
    logger.info(
        f"Study {study_code} initialized. "
        f"n_base={n_base}, norm_mature={norm_mature}, "
        f"seed_quotas={seed_quotas}"
    )


# ── INTERNAL HELPERS ──────────────────────────────────────────────────────────

def _detect_anomalies(
    rows: dict,
    roi_effs: dict,
    roi_agg: dict,
) -> dict:
    """Detect OQT flooding and ROI anomalies. Spec Section 7.3."""
    flags = {}
    for seg_id, row in rows.items():
        seg_flags = {}
        C   = row['C']
        OQT = row['OQT']

        # OQT flood
        if C > 0 and OQT > 0.20 * C:
            seg_flags['oqt_flood'] = True
            logger.warning(f"OQT flood: seg={seg_id} C={C} OQT={OQT}")

        # ROI anomaly vs normative prior
        norm_studies = row.get('norm_n_studies', 0)
        if norm_studies >= 3 and roi_agg.get(seg_id, {}).get('roi_mean') is not None:
            norm_mean = row['norm_roi']
            norm_std  = row['norm_std'] or 0.3
            observed  = roi_agg[seg_id]['roi_mean']
            if abs(observed - norm_mean) > 2 * norm_std:
                seg_flags['roi_anomaly'] = True
                logger.info(
                    f"ROI anomaly: seg={seg_id} "
                    f"observed={observed:.3f} norm={norm_mean:.3f}±{norm_std:.3f}"
                )

        if seg_flags:
            flags[seg_id] = seg_flags

    return flags


def _check_surface_recommendations(
    study_code: str,
    rows: dict,
    tiers: dict,
    roi_effs: dict,
    kappas: dict,
) -> None:
    """Log tier recommendations when entering RESPONSIVE. Spec Section 8.1."""
    logger.info(f"=== TIER RECOMMENDATIONS: {study_code} ===")
    for seg_id in sorted(tiers.keys()):
        logger.info(
            f"  Segment {seg_id:2d}: "
            f"T{tiers[seg_id]} | "
            f"ROI_eff={roi_effs[seg_id]:.3f} | "
            f"kappa={kappas[seg_id]:.3f} | "
            f"C={rows[seg_id]['C']}"
        )
