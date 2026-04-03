#!/usr/bin/env python3
"""
PRISM Survey Platform — Realistic respondent simulation.

Sends proper variable names and values matching the AL study config,
then dumps all stored responses from the session to show the full
variable → value map.

Usage:
    python tests/test_realistic_flow.py
    python tests/test_realistic_flow.py https://your-custom-url.vercel.app
"""

import sys
import json
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://prism-survey-platform-rcghealthprism.vercel.app"
client = httpx.Client(base_url=BASE, timeout=30)

# ── Realistic response data for each page ────────────────────────────────────

RESPONSES = {
    "pre_test.SECTORFAV": {
        "SECTORFAV_r1": 6,    # Biopharma: 6/10
        "SECTORFAV_r2": 3,    # Health insurance: 3/10
        "SECTORFAV_r3": 8,    # Hospitals: 8/10
        "SECTORFAV_r7": 7,    # Auto: 7/10
        "SECTORFAV_r8": 5,    # Oil & gas: 5/10
        "SECTORFAV_r9": 8,    # AI/Tech: 8/10
        "SECTORFAV_r10": 4,   # NIH: 4/10
        "SECTORFAV_r11": 3,   # CDC: 3/10
        "SECTORFAV_r12": 5,   # FDA: 5/10
        "SECTORFAV_r4A": 9,   # Pediatricians (split A)
        "SECTORFAV_r5A": 8,   # Family Physicians (split A)
        "SECTORFAV_r6A": 9,   # Medical scientists (split A)
    },
    "pre_test.CORPFAV": {
        "CORPFAV_r15": 5,     # Pfizer
        "CORPFAV_r16": 4,     # BMS
        "CORPFAV_r17": 99,    # Amgen (not familiar)
        "CORPFAV_r18": 6,     # Eli Lilly
        "CORPFAV_r19": 99,    # Novartis (not familiar)
        "CORPFAV_r20": 5,     # Merck
        "CORPFAV_r21": 7,     # J&J
        "CORPFAV_r22": 6,     # Ford
        "CORPFAV_r23": 5,     # GM
        "CORPFAV_r24": 7,     # OpenAI
        "CORPFAV_r25": 8,     # Google
        "CORPFAV_r26": 4,     # Chevron
    },
    "pre_test.INVEST_AWARE": {
        "INVEST_AWARE": 2,    # "Yes, I've heard a little"
    },
    "pre_test.INVEST_AWARE_OE": {
        "INVEST_AWARE_OE": "I heard about some car companies building new factories in the US",
    },
    "pre_test.INVEST_AWARE_CO": {
        "INVEST_AWARE_CO": "Ford, maybe Tesla",
    },
    "pre_test.JOBALIGNA": {
        "JOBALIGNA_r1": 3,    # Oil & Gas: "Some"
        "JOBALIGNA_r2": 4,    # Auto: "A great deal"
        "JOBALIGNA_r3": 2,    # AI/Tech: "Not very much"
        "JOBALIGNA_r4": 3,    # Biopharma: "Some"
    },
    "pre_test.JOBALIGNB": {
        "JOBALIGNB_r1": 3,
        "JOBALIGNB_r2": 4,
        "JOBALIGNB_r3": 2,
        "JOBALIGNB_r4": 3,
    },
    "pre_test.FUTUREJOB": {
        "FUTUREJOB": 4,       # Biopharmaceuticals
    },
    "pre_test.JOBMOST": {
        "JOBMOST_OilGas": 2,          # Skilled trade workers
        "JOBMOST_Auto": 1,            # Front-line manufacturing
        "JOBMOST_AITech": 4,          # Highly educated professionals
        "JOBMOST_Biopharma": 3,       # Scientists/researchers
    },
    "pre_test.JOBLEAST": {
        "JOBLEAST_OilGas": 7,         # Admin/support staff
        "JOBLEAST_Auto": 4,           # Highly educated professionals
        "JOBLEAST_AITech": 1,         # Front-line manufacturing
        "JOBLEAST_Biopharma": 6,      # Corporate/marketing executives
    },
    "pre_test.AL_PRE_RANK": {
        "AL_PRE_RANK_r1": 2,  # Oil & Gas: 4th
        "AL_PRE_RANK_r2": 3,  # Auto: 3rd
        "AL_PRE_RANK_r3": 5,  # AI/Tech: 1st (most important)
        "AL_PRE_RANK_r4": 4,  # Biopharma: 2nd
        "AL_PRE_RANK_r5": 1,  # Aerospace: 5th (least)
    },
    "pre_test.AL_PRE": {
        "AL_PRE_r1": 6,       # Medicine manufacturing in US: "Important"
        "AL_PRE_r2": 5,       # Congress support: "Somewhat Important"
    },
    "inf360": {
        "qinf360": [1, 3, 5],         # Civic activities: voted, contacted official, donated
        "qtot_followers": 250,         # Social media followers
        "qsocialinfluence": [2, 1, 3], # Card shuffle ranking
    },
    "investment": {
        "INVEST_STIMULUS_AWARE": 4,    # "No, I had not heard anything"
    },
    "msg_maxdiff": {
        "task_1": {"best": 3, "worst": 5},
        "task_2": {"best": 8, "worst": 6},
        "task_3": {"best": 1, "worst": 3},
        "task_4": {"best": 2, "worst": 9},
        "task_5": {"best": 4, "worst": 11},
        "task_6": {"best": 1, "worst": 9},
        "task_7": {"best": 10, "worst": 5},
        "task_8": {"best": 11, "worst": 2},
        "task_9": {"best": 3, "worst": 8},
        "task_10": {"best": 4, "worst": 1},
        "task_11": {"best": 7, "worst": 6},
    },
    "post_test.AL_POST": {
        "AL_POST_r1": 7,      # Medicine manufacturing: "Very Important" (moved from 6)
        "AL_POST_r2": 6,      # Congress support: "Important" (moved from 5)
    },
    "post_test.AL_POST_RANK": {
        "AL_POST_RANK_r1": 1, # Oil & Gas: 5th (dropped)
        "AL_POST_RANK_r2": 3, # Auto: 3rd (same)
        "AL_POST_RANK_r3": 4, # AI/Tech: 2nd (dropped from 1st)
        "AL_POST_RANK_r4": 5, # Biopharma: 1st! (moved up from 2nd)
        "AL_POST_RANK_r5": 2, # Aerospace: 4th (moved up)
    },
    "post_test.CORPFAV_POST": {
        "CORPFAV_POST_r1": 7,   # Biopharma sector: 7/10 (up from 6)
        "CORPFAV_POST_r7": 7,   # Auto: same
        "CORPFAV_POST_r8": 5,   # Oil: same
        "CORPFAV_POST_r11": 8,  # AI/Tech: same
        "CORPFAV_POST_r15": 6,  # Pfizer: up from 5
        "CORPFAV_POST_r16": 5,  # BMS: up from 4
        "CORPFAV_POST_r17": 99, # Amgen: still not familiar
        "CORPFAV_POST_r18": 7,  # Lilly: up from 6 (saw investment stimulus)
        "CORPFAV_POST_r19": 99, # Novartis: still not familiar
        "CORPFAV_POST_r20": 5,  # Merck: same
        "CORPFAV_POST_r21": 7,  # J&J: same
    },
    "mob_battery": {
        "AL_MOB_r1": 5,  # "Somewhat Agree" — can influence policymakers
        "AL_MOB_r2": 6,  # "Agree" — willing to contact elected officials
        "AL_MOB_r3": 4,  # "Neither" — willing to share on social media
        "AL_MOB_r4": 5,  # "Somewhat Agree" — willing to sign petition
        "AL_MOB_r5": 3,  # "Somewhat Disagree" — willing to attend event
    },
    "adv_battery.AL_ADV_P1": {
        "AL_ADV_P1": 3,       # Advocacy disposition
    },
    "adv_battery.AL_ADV_P2": {
        "AL_ADV_P2": 2,       # Advocacy action
    },
    "adv_battery.AL_ADV_P2n": {
        "AL_ADV_P2n": 4,      # Advocacy opposition
    },
    "bespoke.PHRMA01": {
        "PHRMA01": 5,         # PhRMA perception 1
    },
    "bespoke.PHRMA02": {
        "PHRMA02": 4,         # PhRMA perception 2
    },
    "bespoke.PHRMA03": {
        "PHRMA03": 6,         # PhRMA perception 3
    },
    "bespoke.PHRMA04": {
        "PHRMA04": 3,         # PhRMA perception 4
    },
    "demographics": {
        "qedu": 5,            # Bachelor's degree
        "qincome": 7,         # $75k-$99k
        "qrace": 1,           # White
        "qhispanic": 2,       # Not Hispanic
        "qregion": 3,         # South
        "qchildren": 2,       # 2 children under 18
    },
    "opt_in": {
        "qoptin": 1,          # Yes, willing to be recontacted
        "qoptin_email": "test@example.com",
    },
}


# ── Run the flow ─────────────────────────────────────────────────────────────

print("=" * 70)
print("  PRISM AL Study — Full Respondent Simulation (Variable/Value Output)")
print("=" * 70)

# 1. Entry
r = client.get("/survey/entry", params={"psid": "REALISTIC_001", "source": "test"}).json()
rid = r["resp_id"]
print(f"\n{'─'*70}")
print(f"ENTRY: resp_id = {rid}")

# 2. Screener
screener_data = {
    "resp_id": rid, "qvote": 1, "qballot": 1, "qparty": 1,
    "qgender": 1, "qage": 42, "qzip": "30301",
}
s = client.post("/survey/screener", json=screener_data).json()
print(f"\n{'─'*70}")
print(f"SCREENER:")
for k, v in screener_data.items():
    if k != "resp_id":
        print(f"  {k:20s} = {v}")
print(f"  → battery = {s['battery']}")

# 3. Typing
gop_responses = {f"zGOP{i}": float((i % 3) - 1) for i in range(1, 13)}
t = client.post("/survey/typing", json={
    "resp_id": rid, "battery": "GOP", "raw_responses": gop_responses,
}).json()

if t.get("status") == "overquota":
    print("\n  !! OVERQUOTA — study not initialized")
    sys.exit(1)

print(f"\n{'─'*70}")
print(f"TYPING (GOP battery):")
print(f"  Raw B-W inputs (these are TEST DATA — not real MaxDiff scores):")
for k, v in sorted(gop_responses.items()):
    print(f"    {k:20s} = {v:+.1f}")

print(f"\n  SEGMENT ASSIGNMENT:")
print(f"    xseg_final_1     = {t['segment_id']}")
print(f"    xseg_final_2     = {t.get('xseg_final_2', '?')}")
print(f"    party_block      = {t.get('party_block', '?')}")

print(f"\n  CLASSIFICATION DIAGNOSTICS:")
print(f"    seg_probability  = {t.get('seg_probability', '?')}")
print(f"    seg_gap          = {t.get('seg_gap', '?')}")
print(f"    seg_entropy      = {t.get('seg_entropy', '?')}")

print(f"\n  ROUTING:")
print(f"    study_code       = {t['study_code']}")
print(f"    xrandom4         = {t['xrandom4']}")
print(f"    xinvestvar       = {t['xinvestvar']}")
print(f"    msg_version      = {t['msg_version']}")

all_probs = t.get('all_probs', {})
d2_values = t.get('d2_values', {})
if all_probs:
    print(f"\n  SOFTMAX P(segment) & MAHALANOBIS D²:")
    print(f"  {'Seg':>5s}  {'P':>8s}  {'D²':>8s}  {'':40s}")
    for seg_id in sorted(all_probs.keys(), key=lambda x: int(x)):
        p = all_probs[seg_id]
        d2 = d2_values.get(seg_id, d2_values.get(str(seg_id), 0))
        bar = '█' * int(p * 60)
        marker = ' ← ASSIGNED' if int(seg_id) == t['segment_id'] else ''
        marker2 = ' ← 2nd' if int(seg_id) == t.get('xseg_final_2') else ''
        print(f"  {seg_id:>5s}  {p:>8.4f}  {d2:>8.2f}  {bar}{marker}{marker2}")

# 4. Walk through study pages
page_id = "pre_test.SECTORFAV"
all_responses = {}

while page_id and page_id != "complete":
    # GET page
    page = client.get(f"/survey/study/{page_id}", params={"resp_id": rid}).json()

    # Get response data for this page
    resp_data = RESPONSES.get(page_id, {"_no_response_defined": 1})
    all_responses[page_id] = resp_data

    # Print
    component = page.get("content", {}).get("component", page.get("content", {}).get("var", "—"))
    print(f"\n{'─'*70}")
    print(f"PAGE: {page_id}  [{component}]")
    for k, v in resp_data.items():
        if isinstance(v, dict):
            print(f"  {k:30s} = best:{v.get('best')}, worst:{v.get('worst')}")
        elif isinstance(v, list):
            print(f"  {k:30s} = {v}")
        elif isinstance(v, str) and len(v) > 50:
            print(f"  {k:30s} = \"{v[:47]}...\"")
        else:
            print(f"  {k:30s} = {v}")

    # POST response
    result = client.post(f"/survey/study/{page_id}", json={
        "resp_id": rid, "page_id": page_id, "responses": resp_data,
    }).json()

    next_page = result.get("next")
    if next_page == "complete" or result.get("status") == "complete":
        page_id = None
    else:
        page_id = next_page


# ── Final summary ────────────────────────────────────────────────────────────

print(f"\n{'='*70}")
print(f"  COMPLETE — ALL VARIABLES AND VALUES")
print(f"{'='*70}")

# Flatten all responses
flat = {}
flat["qvote"] = 1
flat["qballot"] = 1
flat["qparty"] = 1
flat["qgender"] = 1
flat["qage"] = 42
flat["qzip"] = "30301"
flat["battery"] = "GOP"
flat["segment_id"] = t["segment_id"]
flat["study_code"] = t["study_code"]
flat["xrandom4"] = t["xrandom4"]
flat["xinvestvar"] = t["xinvestvar"]
flat["msg_version"] = t["msg_version"]

for page_id, responses in all_responses.items():
    for k, v in responses.items():
        flat[k] = v

print(f"\n  Total variables: {len(flat)}")
print(f"\n  {'VARIABLE':<35s} {'VALUE'}")
print(f"  {'─'*35} {'─'*35}")
for k, v in flat.items():
    if isinstance(v, dict):
        print(f"  {k:<35s} best:{v.get('best')}, worst:{v.get('worst')}")
    elif isinstance(v, list):
        print(f"  {k:<35s} {v}")
    elif isinstance(v, str) and len(str(v)) > 35:
        print(f"  {k:<35s} \"{str(v)[:32]}...\"")
    else:
        print(f"  {k:<35s} {v}")
