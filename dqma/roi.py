"""
PRISM ROI Algorithm v3.2
Implements advocacy and brand ROI models with shared Bayesian infrastructure.

Architecture: dispatcher pattern.
  - RoiBase: shared normative framework, confidence, shrinkage
  - AdvocacyRoi: current PERSUASION + COALITION + ACTIVATION model
  - BrandRoi: FUNNEL_MOVE + SCALE_MOVE + ACTIVATION model, configurable weights

Entry point for the survey platform:
    compute_roi(respondent_data, study_config) -> RoiResult

The result is written to respondent_roi by the survey platform on completion.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class RoiModelType(str, Enum):
    ADVOCACY = "advocacy"
    BRAND    = "brand"


class FunnelStage(int, Enum):
    """Ordered funnel stages. Higher = more advanced."""
    UNAWARE             = 0
    AWARE               = 1
    CONSIDERING         = 2
    PREFERRING          = 3
    INTENT_TO_REQUEST   = 4
    ADOPTED             = 5


# ── RESULT DATACLASS ──────────────────────────────────────────────────────────

@dataclass
class RoiResult:
    """
    Output of compute_roi(). Written to respondent_roi table.
    All scored components normalized to their stated ranges.
    """
    model_type:     RoiModelType

    roi_total:       float = 0.0    # 0-100

    # Model-agnostic component scores
    # Advocacy:  movement=persuasion, position=coalition destination
    # Brand:     movement=funnel stage transition, position=scale shift
    movement_score:  float = 0.0    # 0-40 (advocacy) / 0-100 weighted (brand)
    position_score:  float = 0.0    # 0-30 (advocacy) / 0-100 weighted (brand)
    activation_score: float = 0.0   # 0-30, NULL if no ADV battery
    influence_score: float = 0.0    # 0-20, BCS-derived

    has_movement:    bool = False
    has_position:    bool = False
    has_activation:  bool = False
    has_influence:   bool = False

    # Brand-specific diagnostics (None for advocacy)
    funnel_position: Optional[FunnelStage] = None
    pre_stage:       Optional[int]  = None
    post_stage:      Optional[int]  = None
    stage_delta:     Optional[int]  = None

    # Shared diagnostics
    align_pre:       Optional[float] = None
    align_post:      Optional[float] = None
    align_move:      Optional[float] = None
    dest_mult:       Optional[float] = None
    bcs:             Optional[float] = None
    notes:           list = field(default_factory=list)


# ── SHARED INFRASTRUCTURE ──────────────────────────────────────────────────────

class RoiBase:
    """
    Shared methods used by both advocacy and brand models.
    No instantiation needed — all class methods.
    """

    # ── Behavioral Confirmation Score (BCS) ───────────────────────────────────

    @staticmethod
    def compute_bcs(
        inf360_level: int,      # 0-3: L0=no inf, L1=low, L2=med, L3=high
        social_inf_score: float, # 0-1 normalized social influence
        overclaim_flag: bool,    # True if follower count inconsistent with behavior
    ) -> float:
        """
        Behavioral Confirmation Score — how much the respondent's
        real-world influence track record confirms their survey responses.
        Returns 0-1. Used as a multiplier on activation. Spec v3.1.

        Inf360 levels (from DQMA BCS mapping):
            L0 = 0 (no advocacy behavior)
            L1 = 1 (low: petition, meeting, donation)
            L2 = 2 (moderate: org involvement, media)
            L3 = 3 (high: govt, leadership, elite roles)
        """
        # Base from influence tier
        tier_scores = {0: 0.0, 1: 0.33, 2: 0.67, 3: 1.0}
        base = tier_scores.get(inf360_level, 0.0)

        # Social influence modifier (+/- 0.15)
        social_adj = (social_inf_score - 0.5) * 0.30

        # Overclaim penalty
        overclaim_penalty = -0.20 if overclaim_flag else 0.0

        bcs = base + social_adj + overclaim_penalty
        return max(0.0, min(1.0, round(bcs, 4)))

    # ── Destination multiplier ─────────────────────────────────────────────────

    @staticmethod
    def compute_dest_mult(post_align: float, scale: int = 7) -> float:
        """
        DESTINATION_MULT: where did the respondent land post-exposure?
        Higher post-alignment = higher coalition value.
        Returns 0-1. Spec v3.1.
        """
        return round(post_align / scale, 4)

    # ── Activation (ARS) ──────────────────────────────────────────────────────

    @staticmethod
    def compute_activation(
        p1_raw: Optional[int],      # AL_ADV_P1: 1-4 + not_sure=5
        p2_raw: Optional[int],      # AL_ADV_P2: 1-5
        p2n_raw: Optional[int],     # AL_ADV_P3: 1-4 + not_sure=5
        bcs: float,
        p1_not_sure_value: int = 5,
        p2n_not_sure_value: int = 5,
        p1_weight: float = 0.40,
        p2_weight: float = 0.30,
        p2n_weight: float = 0.30,
        max_points: float = 30.0,
    ) -> tuple[float, bool]:
        """
        Advocacy Readiness Score (ARS) → ACTIVATION component.
        Returns (activation_score 0-max_points, has_activation bool).
        Spec v3.1.1 ARS formula.
        """
        if p1_raw is None or p2_raw is None or p2n_raw is None:
            return 0.0, False

        # Normalize each item to 0-1
        NOT_SURE_SCORE = 0.33

        p1n = NOT_SURE_SCORE if p1_raw == p1_not_sure_value else (p1_raw - 1) / 3.0
        p2n = (p2_raw - 1) / 4.0
        p2pn = NOT_SURE_SCORE if p2n_raw == p2n_not_sure_value else (p2n_raw - 1) / 3.0

        ars = p1_weight * p1n + p2_weight * p2n + p2n_weight * p2pn

        # BCS adjustment: penalty for low BCS, boost for high BCS
        if bcs < 0.33:
            ars_adj = ars * (0.7 + bcs * 0.9)   # penalty
        elif bcs > 0.67:
            ars_adj = ars * (1.0 + (bcs - 0.67) * 0.6)  # boost
        else:
            ars_adj = ars

        ars_adj = max(0.0, min(1.0, ars_adj))
        activation = round(ars_adj * max_points, 4)
        return activation, True

    # ── Influence component ────────────────────────────────────────────────────

    @staticmethod
    def compute_influence(bcs: float, max_points: float = 20.0) -> float:
        """
        Influence component — upstream, lateral, downstream reach.
        BCS already encodes the behavioral confirmation of influence claims.
        Returns 0-max_points.
        """
        return round(bcs * max_points, 4)


# ── ADVOCACY ROI MODEL ────────────────────────────────────────────────────────

class AdvocacyRoi:
    """
    PRISM Advocacy ROI v3.1.1
    PERSUASION (0-40) + COALITION (0-30) + ACTIVATION (0-30) = ROI_SCORE (0-100)
    Plus optional INFLUENCE (0-20) drawn from BCS.

    Spec: ROI Algorithm sheet, v3.1.1
    """

    # Component max points
    PERSUASION_MAX  = 40.0
    COALITION_MAX   = 30.0
    ACTIVATION_MAX  = 30.0

    # Persuasion divisor: movement of +0.8 on 7pt scale = full score
    PERSUASION_DIVISOR = 0.8

    @classmethod
    def compute(
        cls,
        pre_items: list[dict],     # [{var, value, weight, reversed, transform}]
        post_items: list[dict],    # same structure, same order
        scale: int,                # upper bound of rating scale (usually 7)
        p1_raw: Optional[int],
        p2_raw: Optional[int],
        p2n_raw: Optional[int],
        inf360_level: int,
        social_inf_score: float,
        overclaim_flag: bool,
        p1_weight: float = 0.40,
        p2_weight: float = 0.30,
        p2n_weight: float = 0.30,
        include_influence: bool = True,
    ) -> RoiResult:
        """
        Compute full advocacy ROI for one respondent.

        pre_items / post_items: list of dicts, one per alignment item.
        Each dict: {var, value (raw response), weight (0-100), reversed (bool),
                    transform ('none' | 'rank_to_7pt'), transform_params (dict)}
        Weights should sum to 100.
        """
        result = RoiResult(model_type=RoiModelType.ADVOCACY)

        # ── PRE_ALIGN ──────────────────────────────────────────────────────────
        pre_align = cls._compute_index(pre_items, scale)
        post_align = cls._compute_index(post_items, scale)

        if pre_align is None or post_align is None:
            result.notes.append("Incomplete pre/post data — ROI not computed")
            return result

        align_move = post_align - pre_align
        result.align_pre   = round(pre_align, 4)
        result.align_post  = round(post_align, 4)
        result.align_move  = round(align_move, 4)

        # ── PERSUASION → movement_score (0-40) ────────────────────────────────
        movement = min(1.0, max(0.0, align_move / cls.PERSUASION_DIVISOR)) * cls.PERSUASION_MAX
        result.movement_score = round(movement, 4)
        result.has_movement   = True

        # ── BCS ────────────────────────────────────────────────────────────────
        bcs = RoiBase.compute_bcs(inf360_level, social_inf_score, overclaim_flag)
        result.bcs = bcs

        # ── COALITION → position_score (0-30) ──────────────────────────────────
        dest_mult = RoiBase.compute_dest_mult(post_align, scale)
        position  = dest_mult * cls.COALITION_MAX
        result.position_score = round(position, 4)
        result.dest_mult      = dest_mult
        result.has_position   = True

        # ── ACTIVATION → activation_score (0-30) ──────────────────────────────
        activation, has_act = RoiBase.compute_activation(
            p1_raw, p2_raw, p2n_raw, bcs,
            p1_weight=p1_weight, p2_weight=p2_weight, p2n_weight=p2n_weight,
            max_points=cls.ACTIVATION_MAX,
        )
        result.activation_score = activation
        result.has_activation   = has_act

        # ── INFLUENCE → influence_score (0-20) ────────────────────────────────
        if include_influence:
            result.influence_score = RoiBase.compute_influence(bcs)
            result.has_influence   = True

        # ── ROI TOTAL ──────────────────────────────────────────────────────────
        if not has_act:
            roi_total = (result.movement_score + result.position_score) * (100.0 / 70.0)
        else:
            roi_total = result.movement_score + result.position_score + result.activation_score
        result.roi_total = round(roi_total, 4)

        return result

    @staticmethod
    def _compute_index(items: list[dict], scale: int) -> Optional[float]:
        """
        Weighted composite alignment index from a list of pre/post items.
        Handles transform='none' and transform='rank_to_7pt'.
        Returns None if any required item is missing.
        """
        if not items:
            return None

        total_weight = sum(item['weight'] for item in items)
        if total_weight == 0:
            return None

        weighted_sum = 0.0
        for item in items:
            raw = item.get('value')
            if raw is None:
                return None

            val = AdvocacyRoi._transform(raw, item.get('transform','none'),
                                          item.get('transform_params',{}), scale)

            if item.get('reversed', False):
                val = (scale + 1) - val

            weighted_sum += val * (item['weight'] / total_weight)

        return weighted_sum

    @staticmethod
    def _transform(raw: float, transform: str, params: dict, scale: int) -> float:
        """Apply transform to normalize raw value to common scale."""
        if transform == 'none':
            return float(raw)
        elif transform == 'rank_to_7pt':
            rank_min = params.get('rank_min', 1)
            rank_max = params.get('rank_max', 5)
            return ((raw - rank_min) / (rank_max - rank_min)) * (scale - 1) + 1
        elif transform == 'semantic_to_7pt':
            # Semantic differential already on 1-7 — just ensure direction
            return float(raw)
        else:
            return float(raw)


# ── BRAND ROI MODEL ───────────────────────────────────────────────────────────

class BrandRoi:
    """
    PRISM Brand ROI v1.0
    Consideration-to-adoption funnel model.

    ROI_TOTAL = w_funnel × FUNNEL_MOVE + w_scale × SCALE_MOVE + w_act × ACTIVATION

    Weights sum to 1.0 and are configurable per study:
        funnel_weight:  default 0.45  (stage transition)
        scale_weight:   default 0.35  (continuous scale shift)
        activation_weight: default 0.20 (intent to act)

    Can use funnel only (scale_weight=0), scale only (funnel_weight=0),
    or any blend. Activation is always optional based on battery presence.
    """

    # Stage transition value weights
    # Moving from stage N to stage N+1 is worth progressively more
    # because later transitions are harder and more strategically valuable
    STAGE_TRANSITION_VALUE = {
        (0, 1): 0.10,   # Unaware → Aware          (awareness creation)
        (1, 2): 0.20,   # Aware → Considering       (interest)
        (2, 3): 0.30,   # Considering → Preferring  (preference formation)
        (3, 4): 0.40,   # Preferring → Intent       (high value)
        (4, 5): 0.50,   # Intent → Adopted          (highest value)
    }

    # Penalty for regression (moving backward on funnel)
    REGRESSION_PENALTY = -0.10  # per stage regressed

    # Max points per component (before weight application)
    FUNNEL_MAX  = 100.0
    SCALE_MAX   = 100.0
    ACTIVATION_MAX = 100.0

    @classmethod
    def compute(
        cls,
        # Funnel stage items
        pre_stage_raw: Optional[int],       # Raw pre-exposure funnel stage (0-5)
        post_stage_raw: Optional[int],      # Raw post-exposure funnel stage (0-5)
        stage_var: Optional[str],           # Variable name (for diagnostics)

        # Continuous scale items (same structure as advocacy)
        pre_scale_items: list[dict],        # [{var, value, weight, reversed, transform}]
        post_scale_items: list[dict],

        # Component weights (sum to 1.0, activation excluded from sum)
        funnel_weight: float,
        scale_weight: float,
        activation_weight: float,

        # Activation battery (optional)
        p1_raw: Optional[int],
        p2_raw: Optional[int],
        p2n_raw: Optional[int],

        # Influence / BCS inputs
        inf360_level: int,
        social_inf_score: float,
        overclaim_flag: bool,

        # Scale used for continuous items
        scale: int = 7,

        # Activation scoring parameters
        p1_weight: float = 0.40,
        p2_weight: float = 0.30,
        p2n_weight: float = 0.30,
        p1_not_sure_value: int = 5,
        p2n_not_sure_value: int = 5,

        include_influence: bool = True,
    ) -> RoiResult:
        """
        Compute brand ROI for one respondent.
        """
        result = RoiResult(model_type=RoiModelType.BRAND)

        # ── BCS (shared) ───────────────────────────────────────────────────────
        bcs = RoiBase.compute_bcs(inf360_level, social_inf_score, overclaim_flag)
        result.bcs = bcs

        # ── FUNNEL MOVE component ──────────────────────────────────────────────
        funnel_score = 0.0
        has_funnel = False

        if pre_stage_raw is not None and post_stage_raw is not None:
            pre_stage  = max(0, min(5, int(pre_stage_raw)))
            post_stage = max(0, min(5, int(post_stage_raw)))
            delta      = post_stage - pre_stage

            result.pre_stage   = pre_stage
            result.post_stage  = post_stage
            result.stage_delta = delta
            result.funnel_position = FunnelStage(post_stage)

            if delta > 0:
                # Advancement — sum transition values for each step moved
                move_value = 0.0
                for step in range(delta):
                    from_s = pre_stage + step
                    to_s   = from_s + 1
                    move_value += cls.STAGE_TRANSITION_VALUE.get((from_s, to_s), 0.20)
                funnel_score = min(1.0, move_value) * cls.FUNNEL_MAX
            elif delta < 0:
                # Regression — penalty
                funnel_score = max(0.0, cls.REGRESSION_PENALTY * abs(delta) * cls.FUNNEL_MAX)
            else:
                # No movement — score based on current position (maintenance value)
                funnel_score = post_stage / 5.0 * 20.0  # Partial credit for being on funnel

            has_funnel = True
            result.has_persuasion = True  # Funnel move maps to persuasion slot in DB

        result.funnel_move = round(funnel_score, 4)
        result.movement_score = round(funnel_score, 4)

        # ── SCALE MOVE → position_score ───────────────────────────────────────
        scale_score = 0.0
        has_scale   = False

        if pre_scale_items and post_scale_items:
            pre_align  = AdvocacyRoi._compute_index(pre_scale_items, scale)
            post_align = AdvocacyRoi._compute_index(post_scale_items, scale)

            if pre_align is not None and post_align is not None:
                align_move = post_align - pre_align
                result.align_pre   = round(pre_align, 4)
                result.align_post  = round(post_align, 4)
                result.align_move  = round(align_move, 4)

                scale_score = min(1.0, max(0.0, align_move / 0.8)) * cls.SCALE_MAX

                dest_mult = RoiBase.compute_dest_mult(post_align, scale)
                result.dest_mult = dest_mult
                scale_score = scale_score * 0.7 + dest_mult * cls.SCALE_MAX * 0.3

                has_scale = True
                result.has_position = True

        result.scale_move     = round(scale_score, 4)
        result.position_score = round(scale_score, 4)

        # ── ACTIVATION → activation_score ─────────────────────────────────────
        activation, has_act = RoiBase.compute_activation(
            p1_raw, p2_raw, p2n_raw, bcs,
            p1_weight=p1_weight, p2_weight=p2_weight, p2n_weight=p2n_weight,
            max_points=cls.ACTIVATION_MAX,
            p1_not_sure_value=p1_not_sure_value,
            p2n_not_sure_value=p2n_not_sure_value,
        )
        result.activation_score = round(activation, 4)
        result.has_activation   = has_act

        # ── INFLUENCE → influence_score ────────────────────────────────────────
        if include_influence:
            result.influence_score = RoiBase.compute_influence(bcs)
            result.has_influence   = True

        # ── WEIGHTED ROI TOTAL ─────────────────────────────────────────────────
        # Normalize weights to sum to 1.0 (excluding activation)
        w_total = funnel_weight + scale_weight
        if w_total == 0:
            result.notes.append("Both funnel_weight and scale_weight are 0 — ROI not computed")
            return result

        w_f = funnel_weight / w_total
        w_s = scale_weight  / w_total

        # Base score from funnel and scale
        base_score = w_f * funnel_score + w_s * scale_score

        # Apply activation weight if battery present
        if has_act and activation_weight > 0:
            total_weight = 1.0 + activation_weight
            roi_total = (base_score + activation_weight * activation) / total_weight
        else:
            roi_total = base_score

        result.roi_total = round(max(0.0, min(100.0, roi_total)), 4)

        # Validation notes
        if not has_funnel and funnel_weight > 0:
            result.notes.append("funnel_weight > 0 but no funnel stage data available")
        if not has_scale and scale_weight > 0:
            result.notes.append("scale_weight > 0 but no scale items available")

        return result


# ── DISPATCHER ────────────────────────────────────────────────────────────────

def compute_roi(
    respondent_data: dict,
    study_config: dict,
) -> RoiResult:
    """
    Main entry point. Dispatches to AdvocacyRoi or BrandRoi
    based on study_config['roi_model'].

    respondent_data: flat dict of all collected variable values.
        Keys are canonical variable names (e.g. AL_PRE_r1, AL_ADV_P1).

    study_config: the parsed study config JSON (roi_config section).

    Returns RoiResult ready to be written to respondent_roi table.
    """
    roi_cfg = study_config.get('roi_config', {})
    model_type = RoiModelType(roi_cfg.get('roi_model', 'advocacy'))

    # ── Shared inputs ──────────────────────────────────────────────────────────
    inf360_level     = int(respondent_data.get('INF360_LEVEL', 0))
    social_inf_score = float(respondent_data.get('SOCIAL_INF_SCORE', 0.0))
    overclaim_flag   = bool(respondent_data.get('OVERCLAIM_FLAG', False))
    scale            = int(roi_cfg.get('common_scale', 7))

    # Build pre/post item lists from config
    def build_items(item_cfg_list: list, data: dict) -> list[dict]:
        items = []
        for cfg in item_cfg_list:
            val = data.get(cfg['var'])
            items.append({
                'var':             cfg['var'],
                'value':           float(val) if val is not None else None,
                'weight':          cfg.get('weight', 33),
                'reversed':        cfg.get('reversed', False),
                'transform':       cfg.get('transform', 'none'),
                'transform_params': cfg.get('transform_params', {}),
            })
        return items

    if model_type == RoiModelType.ADVOCACY:
        pre_items  = build_items(roi_cfg.get('pre_align', {}).get('items', []),  respondent_data)
        post_items = build_items(roi_cfg.get('post_align', {}).get('items', []), respondent_data)
        act_cfg    = roi_cfg.get('activation', {})

        return AdvocacyRoi.compute(
            pre_items        = pre_items,
            post_items       = post_items,
            scale            = scale,
            p1_raw           = respondent_data.get(act_cfg.get('items', [{}])[0].get('var') if act_cfg.get('items') else None),
            p2_raw           = respondent_data.get(act_cfg.get('items', [{},{}])[1].get('var') if len(act_cfg.get('items',[])) > 1 else None),
            p2n_raw          = respondent_data.get(act_cfg.get('items', [{},{},{}])[2].get('var') if len(act_cfg.get('items',[])) > 2 else None),
            inf360_level     = inf360_level,
            social_inf_score = social_inf_score,
            overclaim_flag   = overclaim_flag,
            p1_weight        = act_cfg.get('items', [{}])[0].get('weight', 0.40) if act_cfg.get('items') else 0.40,
            p2_weight        = act_cfg.get('items', [{},{}])[1].get('weight', 0.30) if len(act_cfg.get('items',[])) > 1 else 0.30,
            p2n_weight       = act_cfg.get('items', [{},{},{}])[2].get('weight', 0.30) if len(act_cfg.get('items',[])) > 2 else 0.30,
        )

    elif model_type == RoiModelType.BRAND:
        funnel_cfg  = roi_cfg.get('funnel_config', {})
        weights_cfg = roi_cfg.get('component_weights', {})
        act_cfg     = roi_cfg.get('activation', {})

        pre_scale_items  = build_items(roi_cfg.get('pre_align',  {}).get('items', []), respondent_data)
        post_scale_items = build_items(roi_cfg.get('post_align', {}).get('items', []), respondent_data)

        act_items = act_cfg.get('items', [])

        return BrandRoi.compute(
            pre_stage_raw    = respondent_data.get(funnel_cfg.get('pre_stage_var')),
            post_stage_raw   = respondent_data.get(funnel_cfg.get('post_stage_var')),
            stage_var        = funnel_cfg.get('pre_stage_var'),
            pre_scale_items  = pre_scale_items,
            post_scale_items = post_scale_items,
            funnel_weight    = weights_cfg.get('funnel',     0.45),
            scale_weight     = weights_cfg.get('scale',      0.35),
            activation_weight= weights_cfg.get('activation', 0.20),
            p1_raw           = respondent_data.get(act_items[0].get('var')) if len(act_items) > 0 else None,
            p2_raw           = respondent_data.get(act_items[1].get('var')) if len(act_items) > 1 else None,
            p2n_raw          = respondent_data.get(act_items[2].get('var')) if len(act_items) > 2 else None,
            inf360_level     = inf360_level,
            social_inf_score = social_inf_score,
            overclaim_flag   = overclaim_flag,
            scale            = scale,
            p1_weight        = act_items[0].get('weight', 0.40) if act_items else 0.40,
            p2_weight        = act_items[1].get('weight', 0.30) if len(act_items) > 1 else 0.30,
            p2n_weight       = act_items[2].get('weight', 0.30) if len(act_items) > 2 else 0.30,
        )

    else:
        raise ValueError(f"Unknown roi_model: {model_type}")


# ── DB WRITER ─────────────────────────────────────────────────────────────────

def write_roi_result(
    conn,
    resp_id: str,
    study_code: str,
    segment_id: int,
    result: RoiResult,
) -> None:
    """
    Write RoiResult to respondent_roi table using model-agnostic column names.
    Called by survey platform after compute_roi() on completion.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO respondent_roi (
                resp_id, study_code, segment_id, roi_model,
                movement_score, position_score, activation_score, influence_score,
                roi_total,
                funnel_position, pre_stage, post_stage, stage_delta,
                has_movement, has_position, has_activation, has_influence,
                completed_at
            ) VALUES (%s,%s,%s,%s, %s,%s,%s,%s, %s, %s,%s,%s,%s, %s,%s,%s,%s, NOW())
            ON CONFLICT (resp_id, study_code) DO UPDATE SET
                movement_score   = EXCLUDED.movement_score,
                position_score   = EXCLUDED.position_score,
                activation_score = EXCLUDED.activation_score,
                influence_score  = EXCLUDED.influence_score,
                roi_total        = EXCLUDED.roi_total,
                funnel_position  = EXCLUDED.funnel_position,
                pre_stage        = EXCLUDED.pre_stage,
                post_stage       = EXCLUDED.post_stage,
                stage_delta      = EXCLUDED.stage_delta,
                has_movement     = EXCLUDED.has_movement,
                has_position     = EXCLUDED.has_position,
                has_activation   = EXCLUDED.has_activation,
                has_influence    = EXCLUDED.has_influence,
                completed_at     = NOW()
        """, (
            resp_id, study_code, segment_id, result.model_type.value,
            result.movement_score, result.position_score,
            result.activation_score, result.influence_score,
            result.roi_total,
            result.funnel_position.value if result.funnel_position else None,
            result.pre_stage, result.post_stage, result.stage_delta,
            result.has_movement, result.has_position,
            result.has_activation, result.has_influence,
        ))
    conn.commit()
