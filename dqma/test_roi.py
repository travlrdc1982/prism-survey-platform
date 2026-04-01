"""
Unit tests for PRISM ROI algorithm — advocacy and brand models.
All pure function tests — no database required.
"""

import pytest
from roi import (
    RoiBase, AdvocacyRoi, BrandRoi, RoiResult,
    RoiModelType, FunnelStage, compute_roi
)


# ── BCS TESTS ─────────────────────────────────────────────────────────────────

class TestBcs:
    def test_zero_influence_returns_low(self):
        bcs = RoiBase.compute_bcs(0, 0.5, False)
        assert bcs == 0.0

    def test_high_influence_returns_high(self):
        bcs = RoiBase.compute_bcs(3, 0.8, False)
        assert bcs > 0.7

    def test_overclaim_penalty(self):
        bcs_clean     = RoiBase.compute_bcs(2, 0.5, False)
        bcs_overclaim = RoiBase.compute_bcs(2, 0.5, True)
        assert bcs_overclaim < bcs_clean

    def test_clamps_at_1(self):
        bcs = RoiBase.compute_bcs(3, 1.0, False)
        assert bcs <= 1.0

    def test_clamps_at_0(self):
        bcs = RoiBase.compute_bcs(0, 0.0, True)
        assert bcs >= 0.0

    def test_social_influence_modifier(self):
        bcs_high_social = RoiBase.compute_bcs(2, 0.9, False)
        bcs_low_social  = RoiBase.compute_bcs(2, 0.1, False)
        assert bcs_high_social > bcs_low_social


class TestDestMult:
    def test_max_post_align_returns_1(self):
        assert RoiBase.compute_dest_mult(7.0, 7) == 1.0

    def test_min_post_align_returns_low(self):
        dm = RoiBase.compute_dest_mult(1.0, 7)
        assert abs(dm - 1/7) < 0.001

    def test_midpoint(self):
        dm = RoiBase.compute_dest_mult(4.0, 7)
        assert abs(dm - 4/7) < 0.001


class TestActivation:
    def test_none_inputs_returns_zero_false(self):
        act, has = RoiBase.compute_activation(None, None, None, 0.5)
        assert act == 0.0
        assert has == False

    def test_all_definitely_would_returns_high(self):
        # P1=4 (definitely would), P2=5 (much more), P2n=4 (definitely would)
        act, has = RoiBase.compute_activation(4, 5, 4, 0.8)
        assert has == True
        assert act > 20.0

    def test_all_definitely_would_not_returns_zero(self):
        act, has = RoiBase.compute_activation(1, 1, 1, 0.5)
        assert has == True
        assert act == 0.0

    def test_not_sure_scored_as_033(self):
        # P1=5 (not sure), P2=3 (about same), P2n=5 (not sure)
        act_ns, _ = RoiBase.compute_activation(5, 3, 5, 0.5)
        # P1n=0.33, P2n=0.5, P2pn=0.33 → ARS=0.40*0.33+0.30*0.5+0.30*0.33=0.382
        assert 5.0 < act_ns < 20.0

    def test_high_bcs_boosts_score(self):
        act_high, _ = RoiBase.compute_activation(3, 4, 3, 0.9)
        act_low,  _ = RoiBase.compute_activation(3, 4, 3, 0.2)
        assert act_high > act_low

    def test_max_points_param(self):
        act, _ = RoiBase.compute_activation(4, 5, 4, 1.0, max_points=50.0)
        assert act <= 50.0


# ── ADVOCACY ROI TESTS ────────────────────────────────────────────────────────

def make_items(values, weights=None, reversed_flags=None, transforms=None):
    """Helper to build item lists."""
    n = len(values)
    weights       = weights       or [33] * n
    reversed_flags = reversed_flags or [False] * n
    transforms    = transforms    or ['none'] * n
    return [
        {'var': f'item_{i}', 'value': v, 'weight': w, 'reversed': r, 'transform': t}
        for i, (v, w, r, t) in enumerate(zip(values, weights, reversed_flags, transforms))
    ]


class TestAdvocacyRoi:
    def test_no_movement_zero_persuasion(self):
        pre  = make_items([4.0, 4.0, 3.0])
        post = make_items([4.0, 4.0, 3.0])
        r = AdvocacyRoi.compute(pre, post, 7, 3, 3, 3, 1, 0.5, False)
        assert r.movement_score == 0.0
        assert r.has_movement == True

    def test_full_movement_full_persuasion(self):
        # Move from 3 to 7 on all items = +4 shift → well above 0.8 divisor
        pre  = make_items([3.0, 3.0, 3.0])
        post = make_items([7.0, 7.0, 7.0])
        r = AdvocacyRoi.compute(pre, post, 7, 4, 5, 4, 2, 0.7, False)
        assert r.movement_score == pytest.approx(40.0)

    def test_negative_movement_zero_persuasion(self):
        pre  = make_items([6.0, 6.0])
        post = make_items([3.0, 3.0])
        r = AdvocacyRoi.compute(pre, post, 7, 2, 2, 2, 0, 0.3, False)
        assert r.movement_score == 0.0

    def test_high_post_align_high_coalition(self):
        pre  = make_items([4.0])
        post = make_items([6.5])
        r = AdvocacyRoi.compute(pre, post, 7, 3, 3, 3, 1, 0.5, False)
        assert r.position_score > 20.0

    def test_reversed_item_scored_correctly(self):
        # Reversed item: moving from 6→3 should register as positive movement
        pre  = make_items([6.0], reversed_flags=[True])
        post = make_items([3.0], reversed_flags=[True])
        # After reversal: pre_scaled = 8-6=2, post_scaled = 8-3=5 → move = +3
        r = AdvocacyRoi.compute(pre, post, 7, None, None, None, 0, 0.5, False)
        assert r.align_move > 0

    def test_rank_to_7pt_transform(self):
        # Rank 5 (most important) should map to ~7.0 on 7pt scale
        items = make_items([5.0], transforms=['rank_to_7pt'])
        for item in items:
            item['transform_params'] = {'rank_min': 1, 'rank_max': 5}
        val = AdvocacyRoi._compute_index(items, 7)
        assert abs(val - 7.0) < 0.01

    def test_rank_to_7pt_min(self):
        # Rank 1 (least important) should map to ~1.0
        items = make_items([1.0], transforms=['rank_to_7pt'])
        for item in items:
            item['transform_params'] = {'rank_min': 1, 'rank_max': 5}
        val = AdvocacyRoi._compute_index(items, 7)
        assert abs(val - 1.0) < 0.01

    def test_no_activation_rescales_to_100(self):
        pre  = make_items([4.0])
        post = make_items([5.5])
        r = AdvocacyRoi.compute(pre, post, 7, None, None, None, 1, 0.5, False)
        assert not r.has_activation
        assert r.roi_total == pytest.approx((r.movement_score + r.position_score) * (100/70), abs=0.01)

    def test_roi_total_range(self):
        pre  = make_items([2.0, 2.0])
        post = make_items([7.0, 7.0])
        r = AdvocacyRoi.compute(pre, post, 7, 4, 5, 4, 3, 0.9, False)
        assert 0.0 <= r.roi_total <= 100.0

    def test_missing_value_returns_incomplete(self):
        pre  = make_items([None, 4.0])
        post = make_items([5.0, 4.0])
        r = AdvocacyRoi.compute(pre, post, 7, None, None, None, 0, 0.5, False)
        assert r.align_pre is None
        assert r.roi_total == 0.0

    def test_weighted_items(self):
        # Item 1 weight=90, item 2 weight=10
        # Pre: [3, 3], Post: [7, 3] — only item 1 moved
        pre  = make_items([3.0, 3.0], weights=[90, 10])
        post = make_items([7.0, 3.0], weights=[90, 10])
        r_weighted = AdvocacyRoi.compute(pre, post, 7, None, None, None, 0, 0.5, False)

        # Equal weights
        pre2  = make_items([3.0, 3.0], weights=[50, 50])
        post2 = make_items([7.0, 3.0], weights=[50, 50])
        r_equal = AdvocacyRoi.compute(pre2, post2, 7, None, None, None, 0, 0.5, False)

        # Weighted toward item 1 should show more movement
        assert r_weighted.align_move > r_equal.align_move

    def test_influence_component(self):
        pre  = make_items([4.0])
        post = make_items([5.0])
        r = AdvocacyRoi.compute(pre, post, 7, None, None, None, 3, 0.9, False, include_influence=True)
        assert r.has_influence == True
        assert r.influence_score > 0.0

    def test_no_influence_when_excluded(self):
        pre  = make_items([4.0])
        post = make_items([5.0])
        r = AdvocacyRoi.compute(pre, post, 7, None, None, None, 3, 0.9, False, include_influence=False)
        assert r.has_influence == False
        assert r.influence_score == 0.0


# ── BRAND ROI TESTS ───────────────────────────────────────────────────────────

class TestBrandRoi:
    def test_stage_advancement_scores_positive(self):
        r = BrandRoi.compute(
            pre_stage_raw=1, post_stage_raw=3,   # Aware → Preferring (2 stages)
            stage_var='BRAND_STAGE',
            pre_scale_items=[], post_scale_items=[],
            funnel_weight=0.45, scale_weight=0.00, activation_weight=0.20,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=1, social_inf_score=0.5, overclaim_flag=False,
        )
        assert r.movement_score > 0.0
        assert r.roi_total > 0.0
        assert r.stage_delta == 2

    def test_stage_regression_penalized(self):
        r = BrandRoi.compute(
            pre_stage_raw=3, post_stage_raw=1,   # Preferring → Aware (regression)
            stage_var='BRAND_STAGE',
            pre_scale_items=[], post_scale_items=[],
            funnel_weight=1.0, scale_weight=0.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
        )
        assert r.stage_delta == -2
        assert r.movement_score >= 0.0  # Clamped at 0

    def test_later_transitions_worth_more(self):
        # 1→2 (Aware→Considering) vs 3→4 (Preferring→Intent)
        r_early = BrandRoi.compute(
            pre_stage_raw=1, post_stage_raw=2,
            stage_var='STAGE', pre_scale_items=[], post_scale_items=[],
            funnel_weight=1.0, scale_weight=0.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
        )
        r_late = BrandRoi.compute(
            pre_stage_raw=3, post_stage_raw=4,
            stage_var='STAGE', pre_scale_items=[], post_scale_items=[],
            funnel_weight=1.0, scale_weight=0.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
        )
        assert r_late.movement_score > r_early.movement_score

    def test_scale_only_mode(self):
        pre  = make_items([3.0, 3.0])
        post = make_items([6.0, 6.0])
        r = BrandRoi.compute(
            pre_stage_raw=None, post_stage_raw=None,
            stage_var=None,
            pre_scale_items=pre, post_scale_items=post,
            funnel_weight=0.0, scale_weight=1.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=1, social_inf_score=0.5, overclaim_flag=False,
        )
        assert r.position_score > 0.0
        assert r.roi_total > 0.0

    def test_funnel_only_mode(self):
        r = BrandRoi.compute(
            pre_stage_raw=0, post_stage_raw=4,
            stage_var='STAGE',
            pre_scale_items=[], post_scale_items=[],
            funnel_weight=1.0, scale_weight=0.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
        )
        assert r.movement_score > 0.0
        assert r.position_score == 0.0

    def test_both_components_blend(self):
        pre  = make_items([3.0])
        post = make_items([6.0])
        r_both = BrandRoi.compute(
            pre_stage_raw=1, post_stage_raw=3,
            stage_var='STAGE',
            pre_scale_items=pre, post_scale_items=post,
            funnel_weight=0.45, scale_weight=0.35, activation_weight=0.20,
            p1_raw=3, p2_raw=4, p2n_raw=3,
            inf360_level=1, social_inf_score=0.6, overclaim_flag=False,
        )
        assert r_both.movement_score > 0.0
        assert r_both.position_score  > 0.0
        assert r_both.has_activation == True
        assert 0.0 <= r_both.roi_total <= 100.0

    def test_configurable_weights_affect_total(self):
        pre  = make_items([3.0])
        post = make_items([6.0])
        kwargs = dict(
            pre_stage_raw=1, post_stage_raw=4,
            stage_var='STAGE',
            pre_scale_items=pre, post_scale_items=post,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
            activation_weight=0.0,
        )
        r_funnel_heavy = BrandRoi.compute(funnel_weight=0.9, scale_weight=0.1, **kwargs)
        r_scale_heavy  = BrandRoi.compute(funnel_weight=0.1, scale_weight=0.9, **kwargs)
        # Different weights produce different totals
        assert r_funnel_heavy.roi_total != r_scale_heavy.roi_total

    def test_zero_weights_returns_note(self):
        r = BrandRoi.compute(
            pre_stage_raw=1, post_stage_raw=3,
            stage_var='STAGE',
            pre_scale_items=[], post_scale_items=[],
            funnel_weight=0.0, scale_weight=0.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
        )
        assert len(r.notes) > 0

    def test_funnel_position_recorded(self):
        r = BrandRoi.compute(
            pre_stage_raw=1, post_stage_raw=3,
            stage_var='STAGE',
            pre_scale_items=[], post_scale_items=[],
            funnel_weight=1.0, scale_weight=0.0, activation_weight=0.0,
            p1_raw=None, p2_raw=None, p2n_raw=None,
            inf360_level=0, social_inf_score=0.5, overclaim_flag=False,
        )
        assert r.funnel_position == FunnelStage.PREFERRING
        assert r.post_stage == 3

    def test_roi_total_range(self):
        pre  = make_items([1.0, 1.0])
        post = make_items([7.0, 7.0])
        r = BrandRoi.compute(
            pre_stage_raw=0, post_stage_raw=5,
            stage_var='STAGE',
            pre_scale_items=pre, post_scale_items=post,
            funnel_weight=0.45, scale_weight=0.35, activation_weight=0.20,
            p1_raw=4, p2_raw=5, p2n_raw=4,
            inf360_level=3, social_inf_score=0.9, overclaim_flag=False,
        )
        assert 0.0 <= r.roi_total <= 100.0


# ── DISPATCHER TESTS ──────────────────────────────────────────────────────────

class TestDispatcher:
    def test_advocacy_dispatch(self):
        study_config = {
            'roi_config': {
                'roi_model': 'advocacy',
                'common_scale': 7,
                'pre_align': {'items': [
                    {'var': 'AL_PRE_r1', 'weight': 50, 'reversed': False, 'transform': 'none'},
                    {'var': 'AL_PRE_r2', 'weight': 50, 'reversed': False, 'transform': 'none'},
                ]},
                'post_align': {'items': [
                    {'var': 'AL_POST_r1', 'weight': 50, 'reversed': False, 'transform': 'none'},
                    {'var': 'AL_POST_r2', 'weight': 50, 'reversed': False, 'transform': 'none'},
                ]},
                'activation': {'items': [
                    {'var': 'AL_ADV_P1', 'weight': 0.40},
                    {'var': 'AL_ADV_P2', 'weight': 0.30},
                    {'var': 'AL_ADV_P3', 'weight': 0.30},
                ]}
            }
        }
        respondent_data = {
            'AL_PRE_r1': 3.0, 'AL_PRE_r2': 3.0,
            'AL_POST_r1': 6.0, 'AL_POST_r2': 6.0,
            'AL_ADV_P1': 4, 'AL_ADV_P2': 4, 'AL_ADV_P3': 4,
            'INF360_LEVEL': 1, 'SOCIAL_INF_SCORE': 0.6, 'OVERCLAIM_FLAG': False,
        }
        r = compute_roi(respondent_data, study_config)
        assert r.model_type == RoiModelType.ADVOCACY
        assert r.roi_total > 0.0
        assert r.has_movement == True
        assert r.has_activation == True

    def test_brand_dispatch(self):
        study_config = {
            'roi_config': {
                'roi_model': 'brand',
                'common_scale': 7,
                'funnel_config': {
                    'pre_stage_var': 'BRAND_PRE_STAGE',
                    'post_stage_var': 'BRAND_POST_STAGE',
                },
                'component_weights': {
                    'funnel': 0.45, 'scale': 0.35, 'activation': 0.20
                },
                'pre_align': {'items': [
                    {'var': 'BRAND_PRE_1', 'weight': 100, 'reversed': False, 'transform': 'none'}
                ]},
                'post_align': {'items': [
                    {'var': 'BRAND_POST_1', 'weight': 100, 'reversed': False, 'transform': 'none'}
                ]},
                'activation': {'items': [
                    {'var': 'BRAND_P1', 'weight': 0.40},
                    {'var': 'BRAND_P2', 'weight': 0.30},
                    {'var': 'BRAND_P2N', 'weight': 0.30},
                ]}
            }
        }
        respondent_data = {
            'BRAND_PRE_STAGE': 1,   # Aware
            'BRAND_POST_STAGE': 3,  # Preferring
            'BRAND_PRE_1': 3.0,
            'BRAND_POST_1': 5.5,
            'BRAND_P1': 4, 'BRAND_P2': 4, 'BRAND_P2N': 3,
            'INF360_LEVEL': 2, 'SOCIAL_INF_SCORE': 0.65, 'OVERCLAIM_FLAG': False,
        }
        r = compute_roi(respondent_data, study_config)
        assert r.model_type == RoiModelType.BRAND
        assert r.roi_total > 0.0
        assert r.movement_score > 0.0
        assert r.position_score > 0.0
        assert r.funnel_position == FunnelStage.PREFERRING

    def test_defaults_to_advocacy(self):
        # No roi_model specified — should default to advocacy
        study_config = {
            'roi_config': {
                'common_scale': 7,
                'pre_align': {'items': [{'var': 'V1', 'weight': 100, 'reversed': False, 'transform': 'none'}]},
                'post_align': {'items': [{'var': 'V2', 'weight': 100, 'reversed': False, 'transform': 'none'}]},
                'activation': {'items': []}
            }
        }
        respondent_data = {
            'V1': 3.0, 'V2': 5.5,
            'INF360_LEVEL': 0, 'SOCIAL_INF_SCORE': 0.5, 'OVERCLAIM_FLAG': False
        }
        r = compute_roi(respondent_data, study_config)
        assert r.model_type == RoiModelType.ADVOCACY


# ── AL STUDY SCENARIO ─────────────────────────────────────────────────────────

class TestAlScenario:
    """
    End-to-end test using actual AL study config structure.
    """

    AL_CONFIG = {
        'roi_config': {
            'roi_model': 'advocacy',
            'common_scale': 7,
            'pre_align': {
                'index_var': 'AL_PRE_ALIGN',
                'items': [
                    {'var': 'AL_PRE_r1',      'weight': 33, 'reversed': False, 'transform': 'none'},
                    {'var': 'AL_PRE_r2',      'weight': 33, 'reversed': False, 'transform': 'none'},
                    {'var': 'AL_PRE_RANK_r4', 'weight': 34, 'reversed': False,
                     'transform': 'rank_to_7pt', 'transform_params': {'rank_min': 1, 'rank_max': 5}},
                ]
            },
            'post_align': {
                'index_var': 'AL_POST_ALIGN',
                'items': [
                    {'var': 'AL_POST_r1',      'weight': 33, 'reversed': False, 'transform': 'none'},
                    {'var': 'AL_POST_r2',      'weight': 33, 'reversed': False, 'transform': 'none'},
                    {'var': 'AL_POST_RANK_r4', 'weight': 34, 'reversed': False,
                     'transform': 'rank_to_7pt', 'transform_params': {'rank_min': 1, 'rank_max': 5}},
                ]
            },
            'activation': {
                'index_var': 'AL_ARS',
                'items': [
                    {'var': 'AL_ADV_P1',  'weight': 0.40},
                    {'var': 'AL_ADV_P2',  'weight': 0.30},
                    {'var': 'AL_ADV_P3',  'weight': 0.30},
                ]
            }
        }
    }

    def test_typical_cec_respondent(self):
        """CEC segment: high movement, high position, high activation."""
        data = {
            'AL_PRE_r1': 4, 'AL_PRE_r2': 3, 'AL_PRE_RANK_r4': 3,
            'AL_POST_r1': 6, 'AL_POST_r2': 6, 'AL_POST_RANK_r4': 5,
            'AL_ADV_P1': 4, 'AL_ADV_P2': 5, 'AL_ADV_P3': 4,
            'INF360_LEVEL': 2, 'SOCIAL_INF_SCORE': 0.7, 'OVERCLAIM_FLAG': False,
        }
        r = compute_roi(data, self.AL_CONFIG)
        assert r.roi_total > 50.0
        assert r.movement_score > 0.0
        assert r.position_score > 15.0
        assert r.has_activation == True

    def test_typical_abundance_respondent(self):
        """Abundance segment: low movement, low position, low activation."""
        data = {
            'AL_PRE_r1': 5, 'AL_PRE_r2': 5, 'AL_PRE_RANK_r4': 4,
            'AL_POST_r1': 5, 'AL_POST_r2': 4, 'AL_POST_RANK_r4': 3,
            'AL_ADV_P1': 1, 'AL_ADV_P2': 1, 'AL_ADV_P3': 1,
            'INF360_LEVEL': 0, 'SOCIAL_INF_SCORE': 0.3, 'OVERCLAIM_FLAG': False,
        }
        r = compute_roi(data, self.AL_CONFIG)
        assert r.roi_total < 30.0
        assert r.movement_score == 0.0  # No positive movement

    def test_rank_transform_in_composite(self):
        """Verify rank_to_7pt transform integrates correctly."""
        # Rank 5 (most important) in pre and post — no movement
        data = {
            'AL_PRE_r1': 5, 'AL_PRE_r2': 5, 'AL_PRE_RANK_r4': 5,
            'AL_POST_r1': 5, 'AL_POST_r2': 5, 'AL_POST_RANK_r4': 5,
            'INF360_LEVEL': 0, 'SOCIAL_INF_SCORE': 0.5, 'OVERCLAIM_FLAG': False,
        }
        r = compute_roi(data, self.AL_CONFIG)
        assert r.movement_score == 0.0
        assert r.align_move == pytest.approx(0.0, abs=0.01)

    def test_rank_improvement_contributes_to_movement(self):
        """Biopharmaceuticals rising in rank should register as positive movement."""
        data_low  = {
            'AL_PRE_r1': 4, 'AL_PRE_r2': 4, 'AL_PRE_RANK_r4': 2,   # ranked 2nd least
            'AL_POST_r1': 4, 'AL_POST_r2': 4, 'AL_POST_RANK_r4': 2,
            'INF360_LEVEL': 0, 'SOCIAL_INF_SCORE': 0.5, 'OVERCLAIM_FLAG': False,
        }
        data_high = {
            'AL_PRE_r1': 4, 'AL_PRE_r2': 4, 'AL_PRE_RANK_r4': 2,
            'AL_POST_r1': 4, 'AL_POST_r2': 4, 'AL_POST_RANK_r4': 5,  # now most important
            'INF360_LEVEL': 0, 'SOCIAL_INF_SCORE': 0.5, 'OVERCLAIM_FLAG': False,
        }
        r_low  = compute_roi(data_low,  self.AL_CONFIG)
        r_high = compute_roi(data_high, self.AL_CONFIG)
        assert r_high.align_move > r_low.align_move


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
