"""
Unit tests for DQMA core functions.
Tests all pure functions (no database required).
"""

import pytest
import math
from dqma import (
    compute_confidence, study_confidence, compute_phase,
    bayesian_shrinkage, effective_roi, elastic_quota,
    assign_tiers, should_absorb_oqt, dynamic_segment_weight,
    routing_score, Phase, Params
)


# ── CONFIDENCE TESTS ──────────────────────────────────────────────────────────

class TestComputeConfidence:
    def test_zero_completions_no_norms(self):
        k = compute_confidence(0, 0, 0, 0, 0, 0)
        assert k == 0.0

    def test_zero_completions_with_norms(self):
        k = compute_confidence(0, 0, 0, 0, 0, 3)
        assert k > 0.0
        assert k <= 0.30  # norm boost cap

    def test_grows_with_sample(self):
        k10 = compute_confidence(10, 5, 5, 5, 5, 0)
        k25 = compute_confidence(25, 15, 15, 15, 15, 0)
        k50 = compute_confidence(50, 30, 30, 30, 30, 0)
        assert k10 < k25 < k50

    def test_full_components_higher_than_partial(self):
        k_full    = compute_confidence(30, 25, 20, 25, 15, 0)
        k_partial = compute_confidence(30, 25, 5, 5, 5, 0)
        assert k_full > k_partial

    def test_fewer_than_2_components_penalty(self):
        k_one  = compute_confidence(30, 25, 0, 0, 0, 0)
        k_two  = compute_confidence(30, 25, 20, 0, 0, 0)
        # one component gets 0.5 penalty on coverage
        assert k_one < k_two

    def test_caps_at_1(self):
        k = compute_confidence(200, 200, 200, 200, 200, 10)
        assert k <= 1.0

    def test_norm_boost_caps_at_30pct(self):
        k_many_norms = compute_confidence(0, 0, 0, 0, 0, 100)
        assert k_many_norms <= 0.30


class TestStudyConfidence:
    def test_empty_list(self):
        assert study_confidence([]) == 0.0

    def test_single_value(self):
        assert study_confidence([0.5]) == 0.5

    def test_weighted_toward_weakest(self):
        # With one very low kappa, study confidence should be pulled down
        # Formula: 0.7 * p25 + 0.3 * min
        # p25 of 15×0.8 + 1×0.01 = 0.01 (first quartile)
        # min = 0.01
        # result = 0.7*0.01 + 0.3*0.01 = 0.01... but p25 of sorted list
        # sorted: [0.01, 0.8, 0.8, ...] → index 4 = 0.8
        # 0.7*0.8 + 0.3*0.01 = 0.563 — pulled down but not below 0.5 with 15/16 high
        kappas = [0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8,
                  0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.01]
        k = study_confidence(kappas)
        # Should be meaningfully below the uniform 0.8
        assert k < 0.8
        # And above 0 — weakest link pulls it down but doesn't zero it
        assert k > 0.0

    def test_uniform_returns_that_value(self):
        kappas = [0.5] * 16
        k = study_confidence(kappas)
        assert abs(k - 0.5) < 0.01


# ── PHASE TESTS ───────────────────────────────────────────────────────────────

class TestComputePhase:
    def test_seed(self):
        assert compute_phase(0.10, False) == Phase.SEED

    def test_emerging(self):
        assert compute_phase(0.25, False) == Phase.EMERGING

    def test_responsive_low_kappa(self):
        assert compute_phase(0.55, False) == Phase.RESPONSIVE

    def test_responsive_high_kappa_no_client(self):
        assert compute_phase(0.80, False) == Phase.RESPONSIVE

    def test_committed_requires_both(self):
        assert compute_phase(0.80, True) == Phase.COMMITTED

    def test_boundary_seed_emerging(self):
        assert compute_phase(0.15, False) == Phase.EMERGING

    def test_boundary_emerging_responsive(self):
        assert compute_phase(0.40, False) == Phase.RESPONSIVE


# ── BAYESIAN SHRINKAGE TESTS ──────────────────────────────────────────────────

class TestBayesianShrinkage:
    def test_zero_obs_returns_zero(self):
        assert bayesian_shrinkage(0, 0.3) == 0.0

    def test_grows_with_sample(self):
        lam10 = bayesian_shrinkage(10, 0.3)
        lam50 = bayesian_shrinkage(50, 0.3)
        lam200 = bayesian_shrinkage(200, 0.3)
        assert lam10 < lam50 < lam200

    def test_caps_at_1(self):
        assert bayesian_shrinkage(10000, 0.3) <= 1.0

    def test_wider_prior_more_trust_in_obs(self):
        # Wide prior (high norm_std) → trust observed data more
        lam_wide   = bayesian_shrinkage(30, 0.8)
        lam_narrow = bayesian_shrinkage(30, 0.1)
        assert lam_wide > lam_narrow


# ── EFFECTIVE ROI TESTS ───────────────────────────────────────────────────────

class TestEffectiveROI:
    def test_no_data_returns_1(self):
        roi = effective_roi(0, None, 0, 0, 0, 0, 0.0, 1.0, 0.3, 0)
        assert roi == 1.0

    def test_norms_only_returns_norm(self):
        roi = effective_roi(0, None, 0, 0, 0, 0, 0.05, 1.3, 0.3, 3)
        assert roi == 1.3

    def test_full_obs_blends_with_norm(self):
        # Full components, decent sample — should blend toward observed
        roi = effective_roi(50, 1.5, 30, 25, 30, 20, 0.8, 1.0, 0.3, 5)
        assert 1.0 < roi < 1.5  # between norm and observed

    def test_partial_leans_more_on_norm(self):
        # Partial components, low kappa
        roi_partial = effective_roi(20, 1.5, 20, 0, 0, 0, 0.2, 1.0, 0.3, 3)
        roi_full    = effective_roi(50, 1.5, 30, 25, 30, 20, 0.8, 1.0, 0.3, 3)
        # Partial should be closer to norm (1.0) than full
        assert abs(roi_partial - 1.0) < abs(roi_full - 1.0)


# ── ELASTIC QUOTA TESTS ───────────────────────────────────────────────────────

class TestElasticQuota:
    def test_seed_phase_returns_n_base(self):
        Q = elastic_quota(1.0, 0.0, Phase.SEED, 75, 0, 2, 1200)
        assert Q == 75  # No elasticity in SEED

    def test_high_roi_increases_quota(self):
        Q_high = elastic_quota(1.5, 0.7, Phase.RESPONSIVE, 75, 0, 1, 1200)
        Q_avg  = elastic_quota(1.0, 0.7, Phase.RESPONSIVE, 75, 0, 2, 1200)
        assert Q_high > Q_avg

    def test_low_roi_decreases_quota(self):
        Q_low = elastic_quota(0.5, 0.7, Phase.RESPONSIVE, 75, 0, 3, 1200)
        Q_avg = elastic_quota(1.0, 0.7, Phase.RESPONSIVE, 75, 0, 2, 1200)
        assert Q_low < Q_avg

    def test_never_below_completions(self):
        Q = elastic_quota(0.1, 1.0, Phase.COMMITTED, 75, 100, 3, 1200)
        assert Q >= 100

    def test_never_negative(self):
        Q = elastic_quota(0.0, 0.0, Phase.SCORING, 75, 0, 3, 1200)
        assert Q >= 0

    def test_committed_phase_full_roi_weight(self):
        # In COMMITTED, kappa=1: pure ROI-weighted allocation
        Q_t1 = elastic_quota(1.5, 1.0, Phase.COMMITTED, 75, 0, 1, 1200)
        Q_t3 = elastic_quota(0.7, 1.0, Phase.COMMITTED, 75, 0, 3, 1200)
        assert Q_t1 > Q_t3


# ── TIER ASSIGNMENT TESTS ─────────────────────────────────────────────────────

class TestAssignTiers:
    def test_returns_all_16_segments(self):
        roi_vals = {s: 1.0 for s in range(1, 17)}
        tiers = assign_tiers(roi_vals)
        assert len(tiers) == 16

    def test_max_4_tier_1(self):
        # Give many segments high ROI
        roi_vals = {s: 1.5 + s * 0.1 for s in range(1, 17)}
        tiers = assign_tiers(roi_vals)
        assert sum(1 for t in tiers.values() if t == 1) <= 4

    def test_max_3_tier_2(self):
        roi_vals = {s: 1.2 for s in range(1, 17)}
        tiers = assign_tiers(roi_vals)
        assert sum(1 for t in tiers.values() if t == 2) <= 3

    def test_high_roi_gets_tier_1(self):
        roi_vals = {s: 1.0 for s in range(1, 17)}
        roi_vals[5] = 2.0  # One standout
        tiers = assign_tiers(roi_vals)
        assert tiers[5] == 1

    def test_low_roi_gets_tier_3(self):
        roi_vals = {s: 1.0 for s in range(1, 17)}
        roi_vals[3] = 0.3  # One very low
        tiers = assign_tiers(roi_vals)
        assert tiers[3] == 3

    def test_empty_returns_all_tier_3(self):
        tiers = assign_tiers({})
        assert all(t == 3 for t in tiers.values())

    def test_uniform_roi_all_tier_2_or_3(self):
        # At exactly 1.0, tau_1 > 1.0 so nothing is Tier 1
        roi_vals = {s: 1.0 for s in range(1, 17)}
        tiers = assign_tiers(roi_vals)
        assert all(t in (2, 3) for t in tiers.values())


# ── OQT ABSORPTION TESTS ──────────────────────────────────────────────────────

class TestShouldAbsorbOqt:
    def test_seed_absorbs_under_cap(self):
        assert should_absorb_oqt(0.5, 0.1, Phase.SEED, 5, 50)

    def test_seed_rejects_over_cap(self):
        assert not should_absorb_oqt(0.5, 0.1, Phase.SEED, 25, 50)

    def test_oqt_flood_low_roi_terminates(self):
        # OQT > 20% of C and low ROI → terminate
        assert not should_absorb_oqt(0.85, 0.8, Phase.RESPONSIVE, 25, 100)

    def test_high_roi_absorbs(self):
        # High ROI, high kappa: threshold = 1.0 - 0.2*0.8 = 0.84
        assert should_absorb_oqt(1.2, 0.8, Phase.RESPONSIVE, 5, 100)

    def test_below_threshold_terminates(self):
        # Low ROI below threshold
        assert not should_absorb_oqt(0.70, 0.8, Phase.RESPONSIVE, 5, 100)

    def test_low_kappa_wider_threshold(self):
        # Low kappa: threshold = 1.0 - 0.2*0.1 = 0.98 → must be very close to avg
        # ROI=0.97 should be absorbed (below threshold of 0.98)
        # Actually threshold 0.98 means we need roi >= 0.98, so 0.97 is rejected
        assert not should_absorb_oqt(0.97, 0.1, Phase.EMERGING, 5, 100)


# ── DYNAMIC SEGMENT WEIGHT TESTS ──────────────────────────────────────────────

class TestDynamicSegmentWeight:
    def test_no_completions_uses_population_estimate(self):
        w = dynamic_segment_weight(75, 0, 0.5, 0.065)
        assert w > 0

    def test_at_target_returns_near_1(self):
        # Q = C = 75 → raw = 1.0
        w = dynamic_segment_weight(75, 75, 1.0, 0.065)
        assert abs(w - 1.0) < 0.01

    def test_underfilled_returns_above_1(self):
        # Q=75, C=25 → raw=3.0
        w = dynamic_segment_weight(75, 25, 0.8, 0.065)
        assert w > 1.0

    def test_low_kappa_dampens_extreme_weight(self):
        w_low_k  = dynamic_segment_weight(75, 10, 0.1, 0.065)
        w_high_k = dynamic_segment_weight(75, 10, 0.9, 0.065)
        # High kappa should amplify the imbalance more
        assert w_high_k > w_low_k

    def test_clamp_max(self):
        w = dynamic_segment_weight(1000, 1, 1.0, 0.065)
        assert w <= Params.WEIGHT_CLAMP_MAX

    def test_clamp_min(self):
        w = dynamic_segment_weight(1, 1000, 1.0, 0.065)
        assert w >= Params.WEIGHT_CLAMP_MIN


# ── ROUTING SCORE TESTS ───────────────────────────────────────────────────────

class TestRoutingScore:
    def test_full_quota_no_oqt_returns_zero(self):
        score = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=75, OQT=0,
            kappa=0.8, roi_eff=1.2,
            phase=Phase.RESPONSIVE,
            study_weight=1.0, seg_probability=0.85,
            pop_share=0.065, can_absorb_oqt=False
        )
        assert score == 0.0

    def test_full_quota_with_oqt_returns_positive(self):
        score = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=75, OQT=5,
            kappa=0.8, roi_eff=1.2,
            phase=Phase.RESPONSIVE,
            study_weight=1.0, seg_probability=0.85,
            pop_share=0.065, can_absorb_oqt=True
        )
        assert score > 0.0

    def test_higher_roi_scores_higher(self):
        base_kwargs = dict(
            segment_id=1, study_code='AL',
            Q=75, C=50, OQT=0,
            kappa=0.8, phase=Phase.RESPONSIVE,
            study_weight=1.0, seg_probability=0.85,
            pop_share=0.065, can_absorb_oqt=False
        )
        score_high = routing_score(roi_eff=1.5, **base_kwargs)
        score_low  = routing_score(roi_eff=0.7, **base_kwargs)
        assert score_high > score_low

    def test_responsive_phase_boosts_high_roi(self):
        base = dict(
            segment_id=1, study_code='AL',
            Q=75, C=50, OQT=0,
            kappa=0.8, roi_eff=1.5,
            study_weight=1.0, seg_probability=0.85,
            pop_share=0.065, can_absorb_oqt=False
        )
        score_responsive = routing_score(phase=Phase.RESPONSIVE, **base)
        score_seed       = routing_score(phase=Phase.SEED, **base)
        assert score_responsive > score_seed

    def test_urgency_affects_score(self):
        # Low remaining slots → lower urgency
        score_urgent  = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=10, OQT=0,  # 65 remaining → urgency=0.87
            kappa=0.8, roi_eff=1.0, phase=Phase.RESPONSIVE,
            study_weight=1.0, seg_probability=0.85,
            pop_share=0.065, can_absorb_oqt=False
        )
        score_less = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=70, OQT=0,  # 5 remaining → urgency=0.07
            kappa=0.8, roi_eff=1.0, phase=Phase.RESPONSIVE,
            study_weight=1.0, seg_probability=0.85,
            pop_share=0.065, can_absorb_oqt=False
        )
        assert score_urgent > score_less


# ── INTEGRATION SCENARIO TESTS ────────────────────────────────────────────────

class TestScenarios:
    """Higher-level behavioral tests."""

    def test_concurrent_quota_fill(self):
        """
        Core correctness guarantee: with Q=1 and many simultaneous requestors,
        exactly one should win. This tests the pure-function layer;
        the database locking test requires a real connection.
        """
        # All segments at 74/75 — one slot left
        # Multiple routing scores computed — scores should be positive
        scores = []
        for _ in range(50):
            score = routing_score(
                segment_id=5, study_code='AL',
                Q=75, C=74, OQT=0,
                kappa=0.6, roi_eff=1.1,
                phase=Phase.RESPONSIVE,
                study_weight=1.0, seg_probability=0.8,
                pop_share=0.065, can_absorb_oqt=False
            )
            scores.append(score)
        # All see the same score — database lock determines winner
        assert all(s > 0 for s in scores)

    def test_phase_progression(self):
        """Verify phases progress in the right direction as kappa grows."""
        thresholds = [
            (0.05, Phase.SEED),
            (0.20, Phase.EMERGING),
            (0.55, Phase.RESPONSIVE),
            (0.55, Phase.RESPONSIVE),   # still RESPONSIVE without client approval
            (0.80, Phase.COMMITTED),    # needs client approval
        ]
        client_approved = [False, False, False, False, True]
        for (kappa, expected), approved in zip(thresholds, client_approved):
            phase = compute_phase(kappa, approved)
            assert phase == expected, f"kappa={kappa} approved={approved}: expected {expected} got {phase}"

    def test_tier_assignment_ma_scenario(self):
        """
        Reproduce the MA Wave 1 scenario from the spec (Section 5.3).
        Progressives should be T1, Abundance T3.
        """
        # Approximate early ROI signals from spec
        roi_map = {
            11: 1.30,  # Progressives (segment 12 in DEM = seg 12 overall)
            1:  1.10,  # CEC
            12: 1.05,  # Idealists
            16: 1.05,  # Institutionalists
            14: 0.75,  # Abundance
            6:  1.07,  # WE
            9:  0.92,  # MFL
            3:  0.45,  # TC
        }
        # Fill remaining with average
        for s in range(1, 17):
            if s not in roi_map:
                roi_map[s] = 1.0

        tiers = assign_tiers(roi_map)

        # Progressives (11) should be T1
        assert tiers[11] == 1
        # Abundance (14) should be T3
        assert tiers[14] == 3
        # TC (3) with very low ROI should be T3
        assert tiers[3] == 3
        # Max T1 constraint
        assert sum(1 for t in tiers.values() if t == 1) <= 4

    def test_oqt_flood_scenario(self):
        """High-ROI segment flooding with OQT should be absorbed, low-ROI terminated."""
        # High ROI segment: absorb
        assert should_absorb_oqt(
            roi_eff=1.30, kappa=0.35,
            phase=Phase.EMERGING,
            oqt_count=10, C=75
        )

        # Low ROI segment with OQT flood: terminate
        # OQT/C = 15/50 = 30% > 20% AND roi < 0.90
        assert not should_absorb_oqt(
            roi_eff=0.45, kappa=0.35,
            phase=Phase.EMERGING,
            oqt_count=15, C=50
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── ELIGIBILITY EVALUATION TESTS ──────────────────────────────────────────────

class TestEvaluateEligibility:
    def test_default_rule_returns_value(self):
        from dqma import evaluate_eligibility
        rules = [{"var": "*", "op": "default", "result": 3}]
        assert evaluate_eligibility({}, rules) == 3.0

    def test_hard_exclude(self):
        from dqma import evaluate_eligibility
        # INS1=2 → not eligible (ESI/MA pattern)
        rules = [
            {"var": "INS1", "op": "eq", "value": 2, "result": 0},
            {"var": "INS2", "op": "in", "value": [1,2,3], "result": 3},
            {"var": "*", "op": "default", "result": 2},
        ]
        assert evaluate_eligibility({"INS1": 2}, rules) == 0.0

    def test_primary_match(self):
        from dqma import evaluate_eligibility
        rules = [
            {"var": "INS1", "op": "eq", "value": 2, "result": 0},
            {"var": "INS2", "op": "in", "value": [1,2,3], "result": 3},
            {"var": "*", "op": "default", "result": 2},
        ]
        assert evaluate_eligibility({"INS1": 1, "INS2": 2}, rules) == 3.0

    def test_secondary_match_catchall(self):
        from dqma import evaluate_eligibility
        rules = [
            {"var": "INS1", "op": "eq", "value": 2, "result": 0},
            {"var": "INS2", "op": "in", "value": [1,2,3], "result": 3},
            {"var": "*", "op": "default", "result": 2},
        ]
        # Neither INS1=2 nor INS2 in [1,2,3] — falls to default
        assert evaluate_eligibility({"INS1": 1, "INS2": 5}, rules) == 2.0

    def test_preg_strong_primary(self):
        from dqma import evaluate_eligibility
        # PREG: PR1=1 → strong primary, PR1=2-3 → primary, else → not eligible
        rules = [
            {"var": "PR1", "op": "eq",     "value": 1,     "result": 4},
            {"var": "PR1", "op": "in",     "value": [2,3], "result": 3},
            {"var": "*",   "op": "default",                 "result": 0},
        ]
        assert evaluate_eligibility({"PR1": 1}, rules) == 4.0
        assert evaluate_eligibility({"PR1": 2}, rules) == 3.0
        assert evaluate_eligibility({"PR1": 4}, rules) == 0.0

    def test_al_all_eligible(self):
        from dqma import evaluate_eligibility
        # AL: no hard screen — everyone is primary match
        rules = [{"var": "*", "op": "default", "result": 3}]
        assert evaluate_eligibility({"INS1": 1, "PR1": 4, "anything": 99}, rules) == 3.0

    def test_missing_var_skips_rule(self):
        from dqma import evaluate_eligibility
        rules = [
            {"var": "INS1", "op": "eq", "value": 2, "result": 0},
            {"var": "*", "op": "default", "result": 3},
        ]
        # INS1 not in screener data — rule skipped, falls to default
        assert evaluate_eligibility({}, rules) == 3.0

    def test_first_match_wins(self):
        from dqma import evaluate_eligibility
        rules = [
            {"var": "X", "op": "eq", "value": 1, "result": 4},
            {"var": "X", "op": "eq", "value": 1, "result": 2},  # never reached
            {"var": "*", "op": "default", "result": 3},
        ]
        assert evaluate_eligibility({"X": 1}, rules) == 4.0


# ── QUOTA BALANCE FACTOR TESTS ────────────────────────────────────────────────

class TestComputeQuotaBalanceFactor:
    def test_no_targets_returns_1(self):
        from dqma import compute_quota_balance_factor
        f = compute_quota_balance_factor('AL', {}, [], {})
        assert f == 1.0

    def test_within_tolerance_returns_1(self):
        from dqma import compute_quota_balance_factor
        targets = [{
            "quota_id": "QGENDER", "var": "qgender",
            "enforcement": "soft", "penalty_floor": 0.75,
            "cells": [
                {"value": 1, "target_share": 0.48, "tolerance": 0.08},
                {"value": 2, "target_share": 0.50, "tolerance": 0.08},
            ]
        }]
        # Cell 1: 48/100 = 0.48 actual vs 0.48 target — within tolerance
        quota_state = {"QGENDER": {"1": 48, "2": 52}}
        screener = {"qgender": 1}
        f = compute_quota_balance_factor('AL', screener, targets, quota_state)
        assert f == 1.0

    def test_over_tolerance_applies_penalty(self):
        from dqma import compute_quota_balance_factor
        targets = [{
            "quota_id": "QGENDER", "var": "qgender",
            "enforcement": "soft", "penalty_floor": 0.75,
            "cells": [
                {"value": 1, "target_share": 0.48, "tolerance": 0.05},
                {"value": 2, "target_share": 0.52, "tolerance": 0.05},
            ]
        }]
        # Cell 1: 70/100 = 0.70 actual vs 0.48 target+0.05 tolerance=0.53 — over
        quota_state = {"QGENDER": {"1": 70, "2": 30}}
        screener = {"qgender": 1}
        f = compute_quota_balance_factor('AL', screener, targets, quota_state)
        assert f < 1.0
        assert f >= 0.75  # never below penalty_floor

    def test_never_below_floor(self):
        from dqma import compute_quota_balance_factor
        targets = [{
            "quota_id": "QGENDER", "var": "qgender",
            "enforcement": "soft", "penalty_floor": 0.80,
            "cells": [
                {"value": 1, "target_share": 0.10, "tolerance": 0.02},
            ]
        }]
        # Cell 1: 95/100 — massively over target
        quota_state = {"QGENDER": {"1": 95, "2": 5}}
        screener = {"qgender": 1}
        f = compute_quota_balance_factor('AL', screener, targets, quota_state)
        assert f >= 0.80

    def test_hard_enforcement_ignored(self):
        from dqma import compute_quota_balance_factor
        # Hard quotas don't affect balance factor — they affect eligibility
        targets = [{
            "quota_id": "QDISEASE", "var": "disease",
            "enforcement": "hard",
            "cells": [{"value": 1, "target_n": 100}]
        }]
        quota_state = {"QDISEASE": {"1": 150}}
        screener = {"disease": 1}
        f = compute_quota_balance_factor('AL', screener, targets, quota_state)
        assert f == 1.0

    def test_missing_screener_var_skipped(self):
        from dqma import compute_quota_balance_factor
        targets = [{
            "quota_id": "QGENDER", "var": "qgender",
            "enforcement": "soft", "penalty_floor": 0.75,
            "cells": [{"value": 1, "target_share": 0.48, "tolerance": 0.05}]
        }]
        # qgender not in screener_data
        f = compute_quota_balance_factor('AL', {}, targets, {})
        assert f == 1.0


class TestCheckHardQuotaCaps:
    def test_cap_not_reached_returns_false(self):
        from dqma import check_hard_quota_caps
        targets = [{
            "quota_id": "QDISEASE", "var": "disease",
            "enforcement": "hard",
            "cells": [{"value": 1, "target_n": 100}]
        }]
        quota_state = {"QDISEASE": {"1": 50}}
        assert check_hard_quota_caps('AL', {"disease": 1}, targets, quota_state) == False

    def test_cap_reached_returns_true(self):
        from dqma import check_hard_quota_caps
        targets = [{
            "quota_id": "QDISEASE", "var": "disease",
            "enforcement": "hard",
            "cells": [{"value": 1, "target_n": 100}]
        }]
        quota_state = {"QDISEASE": {"1": 100}}
        assert check_hard_quota_caps('AL', {"disease": 1}, targets, quota_state) == True

    def test_different_cell_not_capped(self):
        from dqma import check_hard_quota_caps
        targets = [{
            "quota_id": "QDISEASE", "var": "disease",
            "enforcement": "hard",
            "cells": [
                {"value": 1, "target_n": 100},
                {"value": 2, "target_n": 150},
            ]
        }]
        # Cell 1 capped, cell 2 not — respondent in cell 2 is fine
        quota_state = {"QDISEASE": {"1": 100, "2": 50}}
        assert check_hard_quota_caps('AL', {"disease": 2}, targets, quota_state) == False

    def test_soft_enforcement_ignored(self):
        from dqma import check_hard_quota_caps
        targets = [{
            "quota_id": "QGENDER", "var": "qgender",
            "enforcement": "soft", "penalty_floor": 0.75,
            "cells": [{"value": 1, "target_share": 0.48, "tolerance": 0.05}]
        }]
        # Soft quota massively over — but check_hard_quota_caps ignores soft
        quota_state = {"QGENDER": {"1": 999}}
        assert check_hard_quota_caps('AL', {"qgender": 1}, targets, quota_state) == False

    def test_empty_targets_returns_false(self):
        from dqma import check_hard_quota_caps
        assert check_hard_quota_caps('AL', {"x": 1}, [], {}) == False


class TestRoutingScoreWithQuota:
    def test_quota_factor_1_unchanged(self):
        from dqma import routing_score, Phase
        base = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=50, OQT=0, kappa=0.6, roi_eff=1.1,
            phase=Phase.RESPONSIVE, study_weight=3.0,
            seg_probability=0.8, pop_share=0.065,
            can_absorb_oqt=False, quota_balance_factor=1.0
        )
        penalized = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=50, OQT=0, kappa=0.6, roi_eff=1.1,
            phase=Phase.RESPONSIVE, study_weight=3.0,
            seg_probability=0.8, pop_share=0.065,
            can_absorb_oqt=False, quota_balance_factor=0.80
        )
        assert abs(base * 0.80 - penalized) < 0.001

    def test_quota_factor_default_is_1(self):
        from dqma import routing_score, Phase
        score_explicit = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=50, OQT=0, kappa=0.6, roi_eff=1.1,
            phase=Phase.EMERGING, study_weight=3.0,
            seg_probability=0.8, pop_share=0.065,
            can_absorb_oqt=False, quota_balance_factor=1.0
        )
        score_default = routing_score(
            segment_id=1, study_code='AL',
            Q=75, C=50, OQT=0, kappa=0.6, roi_eff=1.1,
            phase=Phase.EMERGING, study_weight=3.0,
            seg_probability=0.8, pop_share=0.065,
            can_absorb_oqt=False
        )
        assert score_explicit == score_default
