-- PRISM DQMA Database Schema
-- Three tables: respondents, respondent_roi, dqma_state
-- PostgreSQL

-- ── RESPONDENTS ──────────────────────────────────────────────────────────────
-- One row per respondent. Written by survey platform throughout session.
CREATE TABLE IF NOT EXISTS respondents (
    resp_id         TEXT        PRIMARY KEY,
    psid            TEXT        NOT NULL,           -- Dynata respondent ID
    source          TEXT,                           -- Panel source code
    study_code      TEXT,                           -- Assigned after DQMA routing
    segment_id      INTEGER,                        -- 1-16, written after typing tool
    typing_module   TEXT,                           -- GOP / DEM / BOTH
    status          TEXT        NOT NULL DEFAULT 'active',
                                                    -- active / complete / terminate / overquota / partial
    entry_ts        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    complete_ts     TIMESTAMPTZ,
    xrandompick     INTEGER,                        -- Study block assignment
    xseg_final_1    INTEGER,                        -- Primary segment
    xseg_final_2    INTEGER,                        -- Secondary segment
    seg_probability REAL,                           -- Softmax probability of assignment
    seg_gap         REAL,                           -- P1 - P2 gap
    seg_entropy     REAL,                           -- Classification entropy
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT status_check CHECK (
        status IN ('active','complete','terminate','overquota','partial')
    )
);

CREATE INDEX IF NOT EXISTS idx_respondents_study
    ON respondents(study_code, segment_id, status);

CREATE INDEX IF NOT EXISTS idx_respondents_entry
    ON respondents(entry_ts);


-- ── RESPONDENT ROI ───────────────────────────────────────────────────────────
-- One row per respondent per study. Written by ROI algorithm on completion.
-- Read by DQMA rebalance cycle to aggregate per segment per study.
CREATE TABLE IF NOT EXISTS respondent_roi (
    resp_id             TEXT        NOT NULL,
    study_code          TEXT        NOT NULL,
    segment_id          INTEGER     NOT NULL,       -- 1-16
    roi_model           TEXT        NOT NULL DEFAULT 'advocacy',
                                                    -- advocacy | brand

    -- Model-agnostic component scores
    -- Advocacy:  movement=persuasion, position=coalition destination
    -- Brand:     movement=funnel stage transition, position=scale shift
    movement_score      REAL,                       -- 0-40 (advocacy) / 0-100 weighted (brand)
    position_score      REAL,                       -- 0-30 (advocacy) / 0-100 weighted (brand)
    activation_score    REAL,                       -- 0-30, NULL if no ADV battery
    influence_score     REAL,                       -- 0-20, BCS-derived

    roi_total           REAL,                       -- 0-100

    -- Brand-specific diagnostics (NULL for advocacy studies)
    funnel_position     INTEGER,                    -- Post-exposure funnel stage 0-5
    pre_stage           INTEGER,                    -- Pre-exposure funnel stage 0-5
    post_stage          INTEGER,                    -- Post-exposure funnel stage 0-5
    stage_delta         INTEGER,                    -- post - pre

    -- Component availability flags (drive kappa computation in DQMA)
    has_movement        BOOLEAN     NOT NULL DEFAULT FALSE,
    has_position        BOOLEAN     NOT NULL DEFAULT FALSE,
    has_activation      BOOLEAN     NOT NULL DEFAULT FALSE,
    has_influence       BOOLEAN     NOT NULL DEFAULT FALSE,

    completed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resp_id, study_code),
    FOREIGN KEY (resp_id) REFERENCES respondents(resp_id)
);

CREATE INDEX IF NOT EXISTS idx_roi_segment_study
    ON respondent_roi(study_code, segment_id);


-- ── DQMA STATE ───────────────────────────────────────────────────────────────
-- One row per segment per study. The live quota state.
-- Written by: survey platform (C, OQT, TERM increments)
--             DQMA rebalance cycle (Q, phase, kappa, roi_*)
-- Read by: survey platform router (Q, C, roi_effective, phase)
--          admin dashboard (all fields)
CREATE TABLE IF NOT EXISTS dqma_state (
    study_code      TEXT        NOT NULL,
    segment_id      INTEGER     NOT NULL,           -- 1-16

    -- Quota counters (written by survey platform, row-locked)
    Q               INTEGER     NOT NULL DEFAULT 0, -- Current quota target
    C               INTEGER     NOT NULL DEFAULT 0, -- Completions
    OQT             INTEGER     NOT NULL DEFAULT 0, -- Over-quota absorbed
    TERM            INTEGER     NOT NULL DEFAULT 0, -- Terminates

    -- Phase and confidence (written by rebalance cycle)
    phase           TEXT        NOT NULL DEFAULT 'SEED',
                                                    -- SEED/EMERGING/RESPONSIVE/COMMITTED/SCORING
    kappa           REAL        NOT NULL DEFAULT 0.0, -- Confidence index 0-1

    -- ROI aggregates (written by rebalance cycle from respondent_roi)
    roi_mean        REAL,                           -- Mean ROI across completions
    roi_se          REAL,                           -- Standard error of ROI estimate
    roi_effective   REAL,                           -- Blended ROI after Bayesian shrinkage
    movement_n      INTEGER     NOT NULL DEFAULT 0, -- Completions with movement_score
    position_n      INTEGER     NOT NULL DEFAULT 0, -- Completions with position_score
    activation_n    INTEGER     NOT NULL DEFAULT 0, -- Completions with activation_score
    influence_n     INTEGER     NOT NULL DEFAULT 0, -- Completions with influence_score

    -- Algorithmic tier (written by rebalance cycle)
    algo_tier       INTEGER,                        -- 1, 2, or 3
    client_tier     INTEGER,                        -- NULL until client approves
    tier_locked     BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Flags
    supply_flag     BOOLEAN     NOT NULL DEFAULT FALSE,
    oqt_flood_flag  BOOLEAN     NOT NULL DEFAULT FALSE,
    roi_anomaly_flag BOOLEAN    NOT NULL DEFAULT FALSE,

    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (study_code, segment_id),
    CONSTRAINT phase_check CHECK (
        phase IN ('SEED','EMERGING','RESPONSIVE','COMMITTED','SCORING')
    ),
    CONSTRAINT tier_check CHECK (algo_tier IN (1,2,3) OR algo_tier IS NULL)
);

-- ── SESSION DATA ────────────────────────────────────────────────────────────────
-- Key-value store for respondent session state.
-- Stores screener responses, typing results, study responses, split assignments.
-- Written by: survey platform throughout session
-- Read by: survey platform to restore state on each request

CREATE TABLE IF NOT EXISTS session_data (
    resp_id     TEXT        NOT NULL REFERENCES respondents(resp_id),
    key         TEXT        NOT NULL,   -- e.g. 'screener', 'splits', 'responses.pre_test'
    value       TEXT        NOT NULL,   -- JSON
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resp_id, key)
);

CREATE INDEX IF NOT EXISTS idx_session_resp
    ON session_data(resp_id);


-- Unified quota tracking for two purposes:
--
-- 1. Analytical splits (from within_study_quotas in study config)
--    split_type = 'analytical'
--    e.g. XINVESTVAR cells r1-r7, XRANDOM4 cells r1-r2
--    Enforced hard at assignment time with SELECT FOR UPDATE.
--
-- 2. Pre-routing quota targets (from quota_targets in study config)
--    split_type = 'soft_representation' or 'hard_cohort'
--    e.g. QDISEASE cells 1-3, QREGIMEN cells 1-3
--    Soft: routing score penalty when cell exceeds tolerance.
--    Hard: result=0 injected into eligibility when target_n reached.
--
-- Written by: survey platform at assignment (analytical splits)
--             survey platform at routing (quota targets, on completion)
-- Read by:    routing score computation (quota_balance_factor)
--             eligibility evaluation (hard cap enforcement)
--             rebalance cycle (quota monitoring and flagging)

CREATE TABLE IF NOT EXISTS within_study_quota_state (
    study_code      TEXT        NOT NULL,
    split_id        TEXT        NOT NULL,   -- quota_id or split_id from config
    split_type      TEXT        NOT NULL DEFAULT 'analytical',
                                            -- analytical | soft_representation | hard_cohort
    cell_value      TEXT        NOT NULL,   -- e.g. r1, r2, 1, 2, 'biologic'
    cell_label      TEXT,                   -- human readable
    segment_id      INTEGER,                -- NULL = cross-segment tracking
    C               INTEGER     NOT NULL DEFAULT 0,  -- completions in this cell
    target_n        INTEGER,                -- hard quota cap (hard_cohort only)
    target_share    REAL,                   -- desired proportion (soft_representation)
    tolerance       REAL,                   -- off-target tolerance before penalty
    penalty_floor   REAL,                   -- minimum routing score factor (soft only)
    cap_reached     BOOLEAN     NOT NULL DEFAULT FALSE,  -- hard cap hit flag
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (study_code, split_id, cell_value, COALESCE(segment_id::TEXT, '_'))
);

CREATE INDEX IF NOT EXISTS idx_wsq_study_split
    ON within_study_quota_state(study_code, split_id);

CREATE INDEX IF NOT EXISTS idx_wsq_hard_caps
    ON within_study_quota_state(study_code, split_type, cap_reached)
    WHERE split_type = 'hard_cohort';


-- Cross-study ROI priors per segment. Updated after each study completes.
-- Read by DQMA confidence calculation and effective ROI blending.
CREATE TABLE IF NOT EXISTS segment_norms (
    segment_id      INTEGER     PRIMARY KEY,
    abbreviation    TEXT        NOT NULL,
    full_name       TEXT        NOT NULL,
    party_block     TEXT        NOT NULL,  -- GOP or DEM
    pop_share       REAL        NOT NULL,  -- Validated national population share (sums to 1.0)
    roi_mean        REAL        NOT NULL DEFAULT 1.0,
    roi_std         REAL        NOT NULL DEFAULT 0.3,
    n_studies       INTEGER     NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Segment IDs match prism_norms.db canonical ordering.
-- Population shares validated from PRISM Wave 1 national sample.
-- ROI priors normalized from 8-10 completed studies via crosswalk.
-- DO NOT change segment_ids — all historical ROI data is keyed to these IDs.
INSERT INTO segment_norms (segment_id, abbreviation, full_name, party_block, pop_share, roi_mean, roi_std, n_studies)
VALUES
--  id  abbr   full_name                               block   pop_share    roi_mean   roi_std  n_studies
    (1,  'CEC', 'Consumer Empowerment Champions',      'GOP',  0.064877912, 1.096140,  0.654148, 10),
    (2,  'HHN', 'Holistic Health Naturalists',         'GOP',  0.026767810, 0.893507,  0.633630,  9),
    (3,  'TC',  'Traditional Conservatives',           'GOP',  0.056711461, 1.071804,  0.631358,  9),
    (4,  'PFF', 'Paleo Freedom Fighters',              'GOP',  0.042647019, 0.935717,  0.602114,  9),
    (5,  'PP',  'Price Populists',                     'GOP',  0.024499351, 1.032647,  0.598548,  9),
    (6,  'WE',  'Wellness Evangelists',                'GOP',  0.091192030, 1.015921,  0.592924,  9),
    (7,  'HF',  'Health Futurist',                     'GOP',  0.022684585, 0.967069,  0.654968,  9),
    (8,  'VS',  'Vaccine Skeptics',                    'GOP',  0.049906086, 0.914908,  0.623312,  9),
    (9,  'MFL', 'Medical Freedom Libertarians',        'GOP',  0.050359778, 1.014372,  0.606411,  8),
    (10, 'TSP', 'Trust-the-Science Pragmatists',       'GOP',  0.024045660, 0.992402,  0.658492,  9),
    (11, 'UCP', 'Universal Care Progressives',         'DEM',  0.109261662, 1.050542,  0.658009,  8),
    (12, 'FJP', 'Faith & Justice Progressives',        'DEM',  0.102159654, 0.986830,  0.622920,  9),
    (13, 'HCP', 'Health Care Protectionists',          'DEM',  0.078122088, 1.011422,  0.632132,  9),
    (14, 'HAD', 'Health Abundance Democrats',          'DEM',  0.083585171, 1.006597,  0.609929, 10),
    (15, 'HCI', 'Health Care Incrementalists',         'DEM',  0.070473772, 0.915610,  0.611323,  9),
    (16, 'GHI', 'Global Health Institutionalists',     'DEM',  0.102705962, 1.094512,  0.656016,  9)
ON CONFLICT (segment_id) DO NOTHING;

-- ── STUDY BIBD DESIGNS ───────────────────────────────────────────────────────
-- Persists message testing BIBD designs across server restarts.
-- Generated at study initialization via bibd_for_study(study_config).
-- Read by platform at instrument time to serve MaxDiff task sets.
-- One row per (study, version, task, position).

CREATE TABLE IF NOT EXISTS study_bibd (
    study_code  TEXT    NOT NULL,
    version_num INTEGER NOT NULL,   -- 1 to n_versions (respondent's assigned version)
    task_num    INTEGER NOT NULL,   -- 1 to n_tasks
    position    INTEGER NOT NULL,   -- 1 to items_per_task (display order within task)
    item_num    INTEGER NOT NULL,   -- 1-based item index into study config items[]
    PRIMARY KEY (study_code, version_num, task_num, position)
);

CREATE INDEX IF NOT EXISTS idx_study_bibd_lookup
    ON study_bibd(study_code, version_num, task_num);


-- Active studies and their parameters. Loaded from study config JSON.
CREATE TABLE IF NOT EXISTS study_registry (
    study_code      TEXT        PRIMARY KEY,
    client_label    TEXT,
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    roi_model       TEXT        NOT NULL DEFAULT 'advocacy',  -- advocacy | brand

    -- Eligibility rules evaluated per respondent to compute φ_j(r).
    -- JSON array, evaluated in order, first match wins.
    -- Rule format: {"var": "INS1", "op": "eq",  "value": 2,      "result": 0}
    --              {"var": "INS2", "op": "in",   "value": [1,2,3],"result": 3}
    --              {"var": "*",    "op": "default",               "result": 2}
    -- result: 0=not_eligible, 2=secondary_match, 3=primary_match, 4=strong_primary
    -- Spec Section 6.4. Default rule = all respondents are secondary match.
    eligibility_rules JSONB NOT NULL DEFAULT '[{"var":"*","op":"default","result":3}]',

    n_base          INTEGER     NOT NULL DEFAULT 75,
    n_total_target  INTEGER,                        -- 16 * n_base
    phase           TEXT        NOT NULL DEFAULT 'SEED',
    kappa           REAL        NOT NULL DEFAULT 0.0,
    client_tiers_approved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
