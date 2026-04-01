# PRISM Normative Database Specification

**Source:** `prism_norms.db` (SQLite — Layer 3)  
**Seeded from:** `prism_norms_seed.sql` (run once at platform deployment)  
**Backfill basis:** 7,651 respondents × 10 study-waves (backfilled Feb 14, 2026)  
**Updated:** April 2026 — revised for new platform architecture

---

## Architecture Note

`prism_norms.db` is a **read-mostly** SQLite database. It is distinct from the PostgreSQL transactional database. Two things live here:

1. **DQMA normative data** — segment registry and cross-study ROI priors used by the routing engine
2. **Typing tool parameters** — B-W item Z-score parameters, segment centroids, and fixed BIBD designs

Both the DQMA and the typing tool read from this single file. It is never written to during fielding. It is updated only when a study closes (new priors computed) or when the typing tool is revised.

---

## Section 1: Database Schema

```python
import sqlite3
conn = sqlite3.connect("prism_norms.db")
conn.row_factory = sqlite3.Row
```

### Table: `segments`

Canonical segment registry. Segment IDs 1–16 are fixed and must not change.

| Column | Type | Description |
|---|---|---|
| `segment_id` | INTEGER PRIMARY KEY | 1–16 (canonical — never reassign) |
| `abbreviation` | TEXT | Short code: TSP, CEC, TC, HF, PP, WE, PFF, HHN, MFL, VS, UCP, FJP, HCP, HAD, HCI, GHI |
| `full_name` | TEXT | Full segment name |
| `party_block` | TEXT | GOP or DEM |
| `pop_share` | REAL | Validated national population share (sums to 1.0) |

**Canonical segment table:**

| ID | Abbr | Full Name | Block | Pop Share |
|---|---|---|---|---|
| 1 | TSP | Trust-the-Science Pragmatists | GOP | 0.02404566 |
| 2 | CEC | Consumer Empowerment Champions | GOP | 0.064877912 |
| 3 | TC | Traditional Conservatives | GOP | 0.056711461 |
| 4 | HF | Health Futurist | GOP | 0.022684585 |
| 5 | PP | Price Populists | GOP | 0.024499351 |
| 6 | WE | Wellness Evangelists | GOP | 0.09119203 |
| 7 | PFF | Paleo Freedom Fighters | GOP | 0.042647019 |
| 8 | HHN | Holistic Health Naturalists | GOP | 0.02676781 |
| 9 | MFL | Medical Freedom Libertarians | GOP | 0.050359778 |
| 10 | VS | Vaccine Skeptics | GOP | 0.049906086 |
| 11 | UCP | Universal Care Progressives | DEM | 0.109261662 |
| 12 | FJP | Faith & Justice Progressives | DEM | 0.102159654 |
| 13 | HCP | Health Care Protectionists | DEM | 0.078122088 |
| 14 | HAD | Health Abundance Democrats | DEM | 0.083585171 |
| 15 | HCI | Health Care Incrementalists | DEM | 0.070473772 |
| 16 | GHI | Global Health Institutionalists | DEM | 0.102705962 |

**Note on prior segment IDs:** The pre-April 2026 database used different ID assignments (CEC=1, HHN=2, etc.). These were corrected when the typing tool was revised. All current platform code uses the IDs above. Do not reference the old numbering.

---

### Table: `segment_roi_norms`

Cross-study ROI priors. Read by DQMA at routing time for Bayesian shrinkage.

| Column | Type | Description |
|---|---|---|
| `segment_id` | INTEGER PRIMARY KEY | FK → segments |
| `roi_mean` | REAL | Mean-anchored ROI index (1.0 = cross-segment average) |
| `roi_std` | REAL | Standard deviation of ROI index across completed studies |
| `n_studies` | INTEGER | Number of completed studies contributing to this prior |
| `n_total` | INTEGER | Total respondents across contributing studies |
| `updated_at` | TEXT | Timestamp of last recomputation |

**ROI scale:** Values are mean-anchored index, not raw scores. Raw ROI (0–100 scale) was converted: `roi_index = raw_roi / mean_raw_roi_across_segments`. The cross-study mean was 32.91 raw, which becomes 1.0 in the index. Values above 1.0 indicate above-average ROI for that segment.

**Current priors (backfilled from 10 study-waves):**

| Seg | Abbr | roi_mean | roi_std | n_studies | n_total |
|---|---|---|---|---|---|
| 1 | TSP | 0.9924 | 0.6585 | 9 | 349 |
| 2 | CEC | 1.0961 | 0.6541 | 10 | 606 |
| 3 | TC | 1.0718 | 0.6314 | 9 | 445 |
| 4 | HF | 0.9671 | 0.6550 | 9 | 215 |
| 5 | PP | 1.0326 | 0.5985 | 9 | 386 |
| 6 | WE | 1.0159 | 0.5929 | 9 | 555 |
| 7 | PFF | 0.9357 | 0.6021 | 9 | 353 |
| 8 | HHN | 0.8935 | 0.6336 | 9 | 554 |
| 9 | MFL | 1.0144 | 0.6064 | 8 | 542 |
| 10 | VS | 0.9149 | 0.6233 | 9 | 350 |
| 11 | UCP | 1.0505 | 0.6580 | 8 | 580 |
| 12 | FJP | 0.9868 | 0.6229 | 9 | 685 |
| 13 | HCP | 1.0114 | 0.6321 | 9 | 588 |
| 14 | HAD | 1.0066 | 0.6099 | 10 | 455 |
| 15 | HCI | 0.9156 | 0.6113 | 9 | 500 |
| 16 | GHI | 1.0945 | 0.6560 | 9 | 488 |

---

### Table: `typing_items`

B-W items and attitude vectors for the typing tool. Z-score parameters (μ, σ) used to normalize raw responses before centroid distance computation.

**Source:** Revised Typing Tool sheet (`PRISM_Master_Specs_03_29_26.xlsx`). That sheet is canonical. Discrepancies elsewhere are errors.

| Column | Type | Description |
|---|---|---|
| `item_id` | TEXT PRIMARY KEY | e.g. zGOP1, zDEM1, vector_justice |
| `battery` | TEXT | GOP or DEM |
| `item_type` | TEXT | `bw_item` (in MaxDiff) or `attitude_vector` (standalone 7-pt question) |
| `item_order` | INTEGER | Position in battery (1-based) |
| `item_text` | TEXT | Full statement text |
| `scale_min` | REAL | -4 for B-W items, 1 for attitude vectors |
| `scale_max` | REAL | +4 for B-W items, 7 for attitude vectors |
| `mu` | REAL | Population mean for Z-scoring |
| `sigma` | REAL | Population SD for Z-scoring |

**Battery structure:**
- **GOP:** 12 B-W items (zGOP1–zGOP12), shown in MaxDiff, scale −4 to +4
- **DEM:** 10 B-W items (zDEM1–zDEM10) in MaxDiff + 2 attitude vectors (vector_justice, vector_industry) as standalone 7-pt questions

All 12 DEM items (10 B-W + 2 vectors) are used in the centroid distance calculation, even though only the 10 B-W items appear in the MaxDiff battery.

---

### Table: `typing_centroids`

Segment centroid values for the typing algorithm. One row per (item, segment) pair.

| Column | Type | Description |
|---|---|---|
| `item_id` | TEXT | FK → typing_items |
| `segment_id` | INTEGER | FK → segments |
| `centroid` | REAL | Centroid value in Z-score space |

**Coverage:**
- GOP centroids: 12 items × 10 segments = 120 rows
- DEM centroids: 12 items × 6 segments = 72 rows
- Total: 192 rows

---

### Table: `typing_bibd_dem`

Fixed BIBD design for the DEM typing MaxDiff battery. Same for every respondent, every study.

| Column | Type | Description |
|---|---|---|
| `task_num` | INTEGER | Task number (1–10) |
| `position` | INTEGER | Position within task (1–4) |
| `item_num` | INTEGER | 1-based item index (maps to item_order in typing_items) |

**Parameters:** 10 B-W items, 4 per task, 10 tasks. Cyclic base block {0,1,2,5} mod 10. Seed=2024.

---

### Table: `typing_bibd_gop`

Fixed BIBD design for the GOP typing MaxDiff battery.

| Column | Type | Description |
|---|---|---|
| `task_num` | INTEGER | Task number (1–12) |
| `position` | INTEGER | Position within task (1–4) |
| `item_num` | INTEGER | 1-based item index (maps to item_order in typing_items) |

**Parameters:** 12 B-W items, 4 per task, 12 tasks. Cyclic base block {0,1,3,7} mod 12. Seed=2024.

---

## Section 2: Typing Algorithm

```
z_i = (raw_i − μ_i) / σ_i                           [Z-score each item]

D²_j = Σ (z_i − centroid_{i,j})²                    [squared Euclidean distance to segment j]
       for all items in battery (incl. attitude vectors)

P_j = exp(−D²_j / 2) / Σ exp(−D²_k / 2)             [softmax over party block]

segment = argmax(P_j)                                 [assign to closest centroid]
gap     = P_best − P_second                           [classification confidence]
entropy = −Σ P_j log(P_j)                             [classification uncertainty]
```

**BOTH battery (cross-pressured respondents):** Run GOP and DEM algorithms independently. Merge probability vectors across all 16 segments. Normalize so probabilities sum to 1. Assign to argmax across all 16.

---

## Section 3: DQMA Query Interface

```python
# Get ROI prior for a segment
cur.execute(
    "SELECT roi_mean, roi_std, n_studies, n_total "
    "FROM segment_roi_norms WHERE segment_id = ?",
    (segment_id,)
)

# Get all population shares
cur.execute("SELECT segment_id, pop_share FROM segments ORDER BY segment_id")

# Get typing items for a battery
cur.execute(
    "SELECT item_id, item_type, item_order, mu, sigma, scale_min, scale_max "
    "FROM typing_items WHERE battery = ? ORDER BY item_order",
    (battery,)
)

# Get centroids for all segments in a battery
cur.execute(
    "SELECT item_id, segment_id, centroid FROM typing_centroids "
    "WHERE item_id IN (SELECT item_id FROM typing_items WHERE battery = ?)",
    (battery,)
)
```

---

## Section 4: Bayesian Shrinkage Specification

The DQMA blends observed study-level ROI with cross-study priors using Bayesian shrinkage. All computation is in `dqma.py` `effective_roi()`.

**Blending formula:**

```
ROI_blended(s) = λ × prior_mean_roi(s) + (1 − λ) × observed_roi(s)
```

**Shrinkage weight:**

```
λ = τ² / (τ² + σ²)

τ² = prior_std_roi²                          [prior variance from segment_roi_norms]
σ² = 625.0 / max(1, n_segment)              [sampling variance; assumes pop SD ≈ 25]
```

Fallback if prior_std_roi is 0 or NULL: τ² = 625.0 (i.e., 25²)

Cold-start fallback (no prior — 0 completed studies):
```
prior_mean_roi = 1.0    [neutral — average ROI]
prior_std_roi  = 0.3    [moderate uncertainty]
```

**Shrinkage behavior:**

| n (respondents in segment) | λ | Interpretation |
|---|---|---|
| 10 | ≈ 0.91 | 91% prior, 9% observed |
| 30 | ≈ 0.77 | 77% prior, 23% observed |
| 100 | ≈ 0.50 | equal blend |
| 500 | ≈ 0.17 | 17% prior, 83% observed |

**ROI index normalization:**

```
ROI_INDEX(s) = ROI_blended(s) / arithmetic_mean(ROI_blended for all 16 segments)
```

Denominator is a simple unweighted mean of all 16 blended values — not population-share weighted.  
Output is normed to 1.0. Above 1.0 = above-average ROI; below 1.0 = below.

---

## Section 5: ROI Scale and Component Handling

**Raw ROI (0–100):** Used in historical backfill data and `respondent_roi` table in PostgreSQL.

**ROI index (mean-anchored):** Used in `segment_roi_norms` for DQMA. Conversion: `roi_index = raw_roi / 32.91` (the cross-study mean from the 10-wave backfill).

**P+C rescaling (when ACTIVATION unavailable):**

```
roi_total = (persuasion + coalition) × (100 / 70)
```

- PERSUASION range: 0–40
- COALITION range: 0–30  
- Combined: 0–70 → scaled to 0–100
- Used when `components = 'PC'` (study did not collect ADV battery)

**Full P+C+A (when ACTIVATION available):**

```
roi_total = persuasion + coalition + activation    [already 0–100]
```

Used when `components = 'PCA'` (study collected ADV_P1, ADV_P2, ADV_P2n).

**All new studies must collect:** ADV_P1, ADV_P2, ADV_P2n (activation), LOWINF, SOCIALINF (for full BCS). Studies missing these produce systematically attenuated ROI and incomplete BCS.

---

## Section 6: Data Sources (Backfill)

| Study | N | Components | BCS Depth |
|---|---|---|---|
| ESI_W1 | 783 | PC | L2+L3 only |
| MA_W1 | 700 | PC | L2+L3 only |
| GLP1_W1 | 1,826 | PC | L2+L3 only |
| ESI_W2 | 666 | PC | L2+L3 only |
| MA_W2 | 762 | PC | L2+L3 only |
| GLP1_W2 | 498 | PC | L2+L3 only |
| PREG_W2 | 883 | PCA (ARS only) | L2+L3 only |
| AL_W2 | 333 | PCA (ARS+BCS) | Full L0–L3 |
| VAX_W2 | 599 | PCA (ARS+BCS) | Full L0–L3 |
| VICP_W2 | 601 | PCA (ARS+BCS) | Full L0–L3 |
| **Total** | **7,651** | | |

**BCS depth legend:**
- L0 = SOCIALINF (social network activation)
- L1 = LOWINF (low-influence civic activities)
- L2 = QELECTED (elected official contact)
- L3 = QINF360 gateway (general civic activities)

---

## Section 7: Norm Maturity

| Phase | Studies Completed | λ at n=100 | Allocation Strategy | Current Status |
|---|---|---|---|---|
| Nascent | 1–3 | < 0.5 | Equal n_base per segment | — |
| Emerging | 4–8 | 0.5–0.7 | Equal, flag outliers | — |
| Mature | 9+ | > 0.7 | Norm-weighted (min n=30) | ✓ Current (10 waves) |

All 16 segments are in Mature phase. The DQMA starts AL in EMERGING phase (κ=0.30) because the normative data provides strong prior signal from day one.

---

## Section 8: Update Protocol

**During fielding:** Every rebalance cycle (triggered every 50 completions or 6 hours), the DQMA reads from PostgreSQL `respondent_roi` to update `segment_norms` in PostgreSQL. The SQLite `segment_roi_norms` is not updated during fielding — only at study close.

**At study close:**
1. Final ROI scores computed and written to PostgreSQL `respondent_roi`
2. `compute_priors()` reruns N-weighted aggregation across all completed studies
3. `segment_roi_norms` in `prism_norms.db` updated with new cross-study priors
4. `prism_norms_seed.sql` regenerated to reflect updated priors

**Backfill (historical data):**
Historical `.sav` files → `backfill_production.py` → seeds PostgreSQL `respondent_roi` → `compute_priors()` → seeds `prism_norms.db`

---

## Section 9: Known Gaps and Forward Requirements

| Gap | Detail | Impact | Resolution |
|---|---|---|---|
| BCS partial (7/10 waves) | AL/VAX/VICP have full L0–L3. Others have L2+L3 only. | REACH_wgt attenuated → ACTIVATION underestimated | All new studies must include LOWINF + SOCIALINF |
| ACTIVATION missing (6/10 waves) | ESI, MA, GLP1 never collected ADV battery | ROI is rescaled P+C (×100/70), not true 3-component score | All new studies must include ADV_P1, ADV_P2, ADV_P2n |
| Cross-component comparability | P+C-only and P+C+A studies produce different ROI distributions | Blended priors may be biased for activation-sensitive segments | Flag `components` column in shrinkage; consider separate priors as DB grows |
| Segment N imbalance | HF (n=215), TSP (n=349), PP (n=386) have narrower prior support | Shrinkage stronger for rare segments → slower to detect study-specific deviations | Monitor via DQMA anomaly detection |
| Segment ID remapping | Pre-April 2026 DB used different ID assignments | Historical analysis files reference old IDs | Use abbreviation (TSP, CEC etc.) as stable identifier in cross-wave analysis |

---

## Section 10: What Is NOT in This Database

These exist in **PostgreSQL** (transactional), not in `prism_norms.db`:

- `respondents` — respondent session data
- `respondent_roi` — individual ROI scores
- `session_data` — survey responses
- `dqma_state` — live quota state per study × segment
- `study_registry` — active studies and their parameters
- `study_bibd` — generated message testing BIBD designs
- `within_study_quota_state` — split cell counts
- `segment_norms` — study-level segment ROI summaries (feeds compute_priors)
