# PRISM Survey Platform — Claude Code Build Brief

**Version:** 1.0 — April 2026  
**Author:** Reservoir Communications Group  
**For:** Syed H. (Upwork) + Claude Code

---

## Overview

PRISM is a 16-segment behavioral audience intelligence platform. This document specifies everything needed to bring the survey engine to full operational status. The algorithm layer is complete and tested. What remains is the application layer — the FastAPI survey instrument, frontend renderer, and supporting infrastructure.

Read this document fully before writing any code. The architecture has specific constraints that are not obvious from the file names alone.

---

## Repository Structure

```
prism/
├── dqma/                          # Algorithm layer (COMPLETE — do not modify)
│   ├── dqma.py                    # DQMA routing engine
│   ├── roi.py                     # ROI computation (AdvocacyRoi + BrandRoi)
│   ├── bibd.py                    # MaxDiff BIBD generator
│   ├── schema.sql                 # PostgreSQL schema
│   ├── prism_norms_seed.sql       # SQLite seed (segments + ROI priors + typing params)
│   ├── test_dqma.py               # 68 tests
│   ├── test_roi.py                # 45 tests
│   └── test_bibd.py               # 30 tests  [153 total, all passing]
│
├── platform/                      # Application layer (PARTIALLY COMPLETE)
│   ├── main.py                    # FastAPI app — endpoints wired, stubs remain
│   ├── typing_tool.py             # Typing algorithm — COMPLETE including BOTH battery
│   ├── session.py                 # Session management — COMPLETE
│   ├── config.py                  # Settings + DB connections — COMPLETE
│   ├── export.py                  # SPSS export — COMPLETE
│   └── requirements.txt
│
├── configs/                       # Study config JSON files (Layer 2)
│   └── AL.json                    # American Leadership study — COMPLETE
│
└── prism_norms.db                 # SQLite normative database (generated from seed SQL)
```

---

## What Is Complete

### Algorithm layer — do not touch

`dqma.py` — full DQMA v2 implementation. Entry points:
- `route_respondent(conn, resp_id, segment_id, seg_probability, screener_data)` — call after typing, returns `study_code`
- `record_exit(conn, resp_id, study_code, segment_id, ExitType)` — call on complete/terminate/overquota
- `rebalance(conn, study_code)` — call on schedule or completion trigger

`roi.py` — ROI dispatcher. Entry point:
- `compute_roi(all_responses, study_config)` — returns ROI result dict
- `write_roi_result(conn, resp_id, study_code, segment_id, roi_result)` — writes to DB

`bibd.py` — MaxDiff design generator. Entry point:
- `bibd_for_study(study_config, n_versions=11)` — reads params from config, returns design

### Platform layer — complete files

`typing_tool.py` — complete. Do not modify. Key functions:
- `determine_batteries(qballot, qparty)` → `'GOP' | 'DEM' | 'BOTH' | 'TERMINATE'`
- `type_respondent(battery, raw_responses)` → `TypingResult`

`session.py` — complete. Do not modify.

`config.py` — complete. Do not modify.

`export.py` — complete. Do not modify.

### Databases

`prism_norms.db` — SQLite. Seed by running `prism_norms_seed.sql`. Contains:
- `segments` — 16 rows, canonical segment IDs/names/population shares
- `segment_roi_norms` — 16 rows, cross-study ROI priors
- `typing_items` — 24 rows, B-W items + attitude vectors with μ/σ
- `typing_centroids` — 192 rows, segment centroid matrix
- `typing_bibd_dem` — 40 rows, DEM typing BIBD (10 items, 4/task, 10 tasks)
- `typing_bibd_gop` — 48 rows, GOP typing BIBD (12 items, 4/task, 12 tasks)

PostgreSQL — initialize by running `schema.sql`.

---

## What Needs To Be Built

### Priority 1 — Core instrument (blocking)

#### 1.1 Page flow engine

**File:** `platform/main.py` — replace `_get_next_page()` stub

The instrument follows this sequence. Every section except screener and typing is defined in the Layer 2 study config JSON.

```
1. Screener          (Layer 1 hardcoded)
2. Typing battery    (Layer 1 hardcoded — GOP, DEM, or BOTH)
3. Pre-routing Qs    (Layer 2 — study config pre_routing_questions[])
4. DQMA routing      (Layer 1 — assigns study)
5. Study instrument  (Layer 2 — in this order):
   a. Inf360 gateway     (Layer 1 hardcoded questions)
   b. Awareness          (XX_AWARE)
   c. Info channels      (XX_INFO)
   d. Issue views        (XX_ISSUES + XX_IMP)
   e. Critics battery    (CRITIC_1..N) — Block A position (50% of sample)
   f. Investment stimulus (investment_variable)
   g. MSG MaxDiff         (msg_maxdiff)
   h. Critics battery    (CRITIC_1..N) — Block B position (other 50%)
   i. Post-test          (post_test questions — same vars as pre, locked order)
   j. Mobilization       (mob_battery)
   k. ADV battery        (adv_battery — P1, P2, P2n)
   l. Bespoke questions  (bespoke_questions)
   m. Demographics       (Layer 1 hardcoded)
   n. Opt-in             (Layer 1 hardcoded)
6. Complete → compute ROI → Dynata redirect
```

**Critics rotation:** `critic_block_rotation: true` in config means half the sample sees critics before MSG MaxDiff (Block A), half after (Block B). The `xrandom4` split determines which block. Block A = `xrandom4 == 'r1'`.

**Display conditions:** Some questions have conditions in the config. Example: `COND: IF MAHA_AWARE=1,2,3 THEN show MAHA_PERCEP`. Parse the `condition` field on each question and skip if the condition evaluates false against the respondent's stored responses.

**Post-test ordering:** Post-test variables must appear in exactly the same item order as their pre-test counterparts. The config marks this — do not shuffle.

**Implementation:** `_get_next_page(page_id, study_config, session)` should return the next page ID string given the current page, the study config, and the session (for evaluating conditions against stored responses). Page IDs follow the pattern `{section}.{var}`, e.g. `pre_test.AL_SECTOR_FAV`, `msg_maxdiff`, `mob_battery.AL_MOB_1`.

---

#### 1.2 Inf360 scoring

**File:** new `platform/inf360.py`

Inf360 is a Layer 1 influence scoring module. It runs after typing and segment assignment. Questions are hardcoded (not in study config).

Questions (always in this order):
1. `qinf360` — gateway checklist: civic activities (multi-select)
2. Based on gateway, show one or more upgrade modules:
   - `qinf360_eliteup` — elite upgrade activities
   - `qinf360_recruitup` — recruit upgrade activities
   - `qinf360_orglat` — organizational lateral activities
   - `qinf360_medialat` — media lateral activities
   - `qinf360_down` — downward influence activities
3. `qlowinf` — low-influence checklist (shown if gateway = 0)
4. `qtot_followers` — social media followers (always shown)
5. `qsocialinfluence` — 3-card activity shuffle

Scoring produces:
- `bcs` — Behavioral Confirmation Score (0–1), written to `respondent_roi.bcs`
- `influence_score` — raw influence tier (1–5), written to `respondent_roi.influence_score`

The exact scoring algorithm is in `roi.py` `_compute_influence_score()`. Inf360 responses need to be stored in session_data under key `responses.inf360` and passed to `compute_roi()` at completion.

---

#### 1.3 MaxDiff response recording and B-W score reconstruction

**Defined format (do not change):**

The frontend sends task-level responses. The platform stores them as-is:

```json
{
  "task_1": {"best": 3, "worst": 7},
  "task_2": {"best": 11, "worst": 2}
}
```

Where `best` and `worst` are 1-based item numbers from the BIBD task definition.

**At export time** (`platform/export.py`), reconstruct item-level B-W scores:

```python
def reconstruct_bw_scores(task_responses: dict, bibd_version: list, n_items: int) -> dict:
    """
    task_responses: {"task_1": {"best": 3, "worst": 7}, ...}
    bibd_version:   [[3,7,11,2], [1,5,8,4], ...]  (item_nums per task)
    Returns: {"item_1": 0, "item_2": -1, "item_3": 1, ...}
    """
    scores = {f"item_{i}": 0 for i in range(1, n_items + 1)}
    for task_key, response in task_responses.items():
        task_idx = int(task_key.split("_")[1]) - 1
        if task_idx < len(bibd_version):
            best  = response.get("best")
            worst = response.get("worst")
            if best:  scores[f"item_{best}"]  = 1
            if worst: scores[f"item_{worst}"] = -1
    return scores
```

Wire this into `_vars_from_config()` in `export.py` — MaxDiff items should appear in the output as `{item_id}` with values 1, -1, or 0.

---

### Priority 2 — Frontend renderer

**Stack:** React + Vite, deployed separately from the FastAPI backend. The backend serves JSON; the frontend renders it.

The frontend calls `GET /survey/study/{page_id}?resp_id=...` and receives a content object. Based on `content.component`, it renders the appropriate UI component.

#### Component map

| `component` value | Renders | Key config fields |
|---|---|---|
| `STYLE.HORIZONTAL.RADIO` | Horizontal radio row | `options[]`, `scale_points`, `has_pnta` |
| `STYLE.RADIO.VERTICAL` | Vertical stacked radio | `options[]`, `has_specify`, `has_not_sure` |
| `STYLE.BUTTON.HORIZONTAL` | Horizontal pill buttons | `options[]`, `scale_gradient`, `has_or_99` |
| `STYLE.MATRIX` | Grid matrix | `items[]`, `scale_points`, `left_anchor`, `right_anchor` |
| `STYLE.CARDSHUFFLE` | One card at a time | `items[]`, `scale_points`, `shuffle` |
| `STYLE.7PTSEMANTIC` | Semantic differential | `statement_a`, `statement_b`, `midpoint_label` |
| `STYLE.RANKSORT` | Drag-and-drop ranking | `items[]`, `item_count` |
| `STYLE.CHECKLIST` | Multi-select checkboxes | `items[]`, `has_none`, `expandable` |
| `STYLE.DIGITBOXES` | Numeric digit entry | `item_count`, `min_value`, `max_value` |
| `STYLE.DROPDOWN` | Single-select dropdown | `options[]` |
| `CUSTOM.BALLOT` | 2024 vote question | Fixed — non-configurable |
| `CUSTOM.PARTYID` | Party ID chain (3 Qs) | Fixed — non-configurable |
| `MAXDIFF.TYPING` | Typing tool MaxDiff | Fixed — loads from `prism_norms.db` |
| `MAXDIFF.MESSAGE` | Message testing MaxDiff | `bibd_tasks`, `item_texts`, `is_persona` |

#### Design tokens (from master spec)

```
brand_green (CTA):    #6B7F4E
bg_page:              #F5F2ED
bg_card:              #FFFFFF
text_primary:         #333333
text_secondary:       #888888
text_red (disagree):  #C62828
text_green (agree):   #2E7D32
radio_selected_green: #4CAF50
radio_selected_red:   #C62828
card_selected_green:  #E8F5E9
card_selected_red:    #FFEBEE
font_primary:         Fraunces (question text, statements)
font_secondary:       Inter (helper text, labels, instructions)
max_content_width:    600-680px
```

#### MaxDiff component (MAXDIFF.MESSAGE) — critical

Each task shows `items_per_task` items. Respondent selects MOST COMPELLING and LEAST COMPELLING.

- Left column: "MOST COMPELLING" — green radio
- Right column: "LEAST COMPELLING" — red radio
- Selected MOST row: green background `#E8F5E9`
- Selected LEAST row: red background `#FFEBEE`
- Validation: must select exactly one MOST and one LEAST before advancing
- Cannot select same item for both

Response sent to `POST /survey/study/msg_maxdiff`:
```json
{
  "resp_id": "...",
  "page_id": "msg_maxdiff",
  "responses": {
    "task_1": {"best": 3, "worst": 7},
    "task_2": {"best": 11, "worst": 2}
  }
}
```

---

### Priority 3 — Infrastructure

#### 3.1 BIBD persistence (already in schema, needs wiring)

`study_bibd` table exists in `schema.sql`. At `POST /admin/initialize`, the platform:
1. Calls `bibd_for_study(study_config, n_versions=11)`
2. Calls `_persist_bibd(conn, study_code, bibd_result)` — already implemented in `main.py`
3. Calls `_cache_bibd(study_code, bibd_result)` — in-memory cache for speed

At instrument time, `get_bibd_version(conn, study_code, version)` reads from cache, falls back to DB. This is already implemented. No additional work needed beyond confirming it works end-to-end.

#### 3.2 Environment configuration

Required environment variables:

```bash
DATABASE_URL=postgresql://prism:prism@localhost:5432/prism
NORMS_DB_PATH=/path/to/prism_norms.db
CONFIGS_DIR=/path/to/configs
BIBD_CACHE_DIR=/path/to/bibd_cache
DEBUG=false
```

#### 3.3 Dynata redirect URLs

Must be populated in each study config before fielding:

```json
"dynata": {
  "complete_redirect":  "https://[confirm with account manager]",
  "terminate_redirect": "https://[confirm with account manager]",
  "overquota_redirect": "https://[confirm with account manager]"
}
```

Confirm REX vs Samplify format with Dynata account manager before AL goes to field.

---

### Priority 4 — Study initialization flow

Before fielding a study, run these steps in order:

```bash
# 1. Create prism_norms.db from seed
sqlite3 prism_norms.db < dqma/prism_norms_seed.sql

# 2. Initialize PostgreSQL schema
psql $DATABASE_URL < dqma/schema.sql

# 3. Initialize study via API
curl -X POST http://host/admin/initialize \
  -H "Content-Type: application/json" \
  -d '{"study_code": "AL", "n_base": 75}'
```

Step 3 triggers:
- `initialize_study()` in `dqma.py` — seeds `dqma_state` and `study_registry`
- `bibd_for_study()` — generates message BIBD
- `_persist_bibd()` — writes BIBD to `study_bibd` table

---

### Priority 5 — Testing

#### Unit tests needed (Syed implements)

- `test_page_flow.py` — verify correct page sequence for AL config, critics rotation, conditional display
- `test_inf360.py` — gateway routing, upgrade module selection, BCS computation
- `test_bw_reconstruction.py` — task responses → item-level B-W scores

#### Integration test (run before fielding)

Use the survey tester endpoint (to be built — see future work) to walk through:
- Trump voter, Strong Republican → GOP battery → AL → persona variant
- Harris voter, Lean Republican → BOTH battery → AL → control
- Other voter, True independent → TERMINATE before typing

#### Field QA checklist

- [ ] All 21 battery routing cases verified
- [ ] Critics Block A appears before MaxDiff for xrandom4=r1
- [ ] Critics Block B appears after MaxDiff for xrandom4=r2
- [ ] Post-test item order matches pre-test exactly
- [ ] Investment variant assignment balanced across cells
- [ ] MSG MaxDiff version assignment balanced across versions
- [ ] SPSS export produces valid .sav with correct variable labels
- [ ] Dynata redirects confirmed with account manager
- [ ] DQMA rebalance runs after every 50 completions

---

## Key Architecture Constraints

**Layer 1 vs Layer 2 separation is absolute.** Layer 1 code (anything in `platform/`) must never hardcode study-specific content. All study content — question text, item text, response options, ROI mappings — comes from the Layer 2 study config JSON. The only exceptions are: screener questions (qvote, qballot, qparty, qgender, qage, qzip), the typing battery (loaded from `prism_norms.db`), Inf360 questions, the demographics battery, and the opt-in screen.

**`bibd.py` is for message testing only.** The typing tool BIBD designs are static data in `prism_norms.db` (`typing_bibd_dem`, `typing_bibd_gop`). The platform reads them from the database. `bibd.py` is never called for typing tool purposes.

**Party routing uses QBALLOT (2024 vote), not party registration.** `determine_batteries(qballot, qparty)` in `typing_tool.py` implements the full 21-case matrix. True independents (QBALLOT=3, QPARTY=4) are terminated before the typing tool.

**BOTH battery respondents get all 16 segments.** When `determine_batteries()` returns `'BOTH'`, the platform runs both GOP (12-item) and DEM (10-item + 2 attitude vectors) batteries. The typing algorithm combines probability vectors across all 16 segments and assigns to argmax P.

**MaxDiff responses stored as raw task data.** The format is `{"task_1": {"best": 3, "worst": 7}, ...}` using 1-based item numbers. Item-level B-W scores (1/-1/0) are derived at export time, not stored. This preserves full task structure for future HB utility estimation.

**`prism_norms.db` is a single SQLite file.** It contains both DQMA normative data (segments, ROI priors) and typing tool parameters (items, centroids, BIBD designs). Both `prism_norms_seed.sql` files have been merged into one. Run it once; the resulting database serves both the DQMA and the typing tool.

---

## File Handoff Inventory

### Complete — do not modify

| File | Description |
|---|---|
| `dqma/dqma.py` | DQMA routing engine (68 tests) |
| `dqma/roi.py` | ROI algorithm (45 tests) |
| `dqma/bibd.py` | BIBD generator (30 tests) |
| `dqma/schema.sql` | PostgreSQL schema |
| `dqma/prism_norms_seed.sql` | SQLite seed — all normative + typing data |
| `platform/typing_tool.py` | Typing algorithm + battery routing |
| `platform/session.py` | Session management + split assignment |
| `platform/config.py` | Settings + DB connections |
| `platform/export.py` | SPSS .sav export |
| `configs/AL.json` | AL study config (v8) |

### Partially complete — needs implementation

| File | What's done | What remains |
|---|---|---|
| `platform/main.py` | All endpoints wired, BIBD persistence, export endpoint | `_get_next_page()` page flow engine, pass `conn` to `_resolve_maxdiff` |
| `platform/export.py` | Column structure, session data flattening | `reconstruct_bw_scores()` for MaxDiff items |

### To be created

| File | Description |
|---|---|
| `platform/inf360.py` | Inf360 gateway + scoring |
| `frontend/` | React app — all UI components |
| `tests/test_page_flow.py` | Page flow unit tests |
| `tests/test_inf360.py` | Inf360 unit tests |
| `tests/test_bw_reconstruction.py` | B-W score reconstruction tests |

---

## Future Work (not in scope for this build)

- **Admin UI** — web form for authoring study config JSON, replacing manual JSON editing
- **Survey tester** — QA tool to walk through instrument as a test respondent with specified characteristics
- **HB estimation** — post-field MaxDiff utility scoring using raw task data stored in `session_data`
- **ROI dashboard** — real-time segment ROI visualization during field
- **Multi-study panel** — simultaneous routing across multiple active studies (DQMA already supports this)

---

## Questions Before Starting

Before writing any frontend code, confirm with Bryan:

1. **Dynata integration type** — REX or Samplify? Affects redirect URL format.
2. **Hosting** — where does FastAPI deploy? (Vercel, Railway, EC2?) Affects WSGI config.
3. **Frontend hosting** — separate domain or same origin? Affects CORS config in `main.py`.
4. **Variable renames** — AL config v8 has ~10 pending variable renames (see `PRISM_AL_Variable_Map.xlsx`). Apply before fielding.
