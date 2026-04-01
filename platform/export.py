"""
PRISM Survey Platform — SPSS Export

GET /admin/export/{study_code} returns a .sav file download.
Completes only. Manual trigger.

Output: one row per complete respondent, columns:
    System    — resp_id, psid, segment_id, typing vars, split assignments
    Responses — all study question responses, flattened from session_data
    ROI       — movement_score, position_score, activation_score, roi_realtime
"""

import io
import json
import logging
from datetime import datetime

import psycopg2.extras
import pandas as pd
import pyreadstat

logger = logging.getLogger(__name__)


SEGMENT_LABELS = {
    1: "TSP: Trust-the-Science Pragmatists",
    2: "CEC: Consumer Empowerment Champions",
    3: "TC: Traditional Conservatives",
    4: "HF: Health Futurist",
    5: "PP: Price Populists",
    6: "WE: Wellness Evangelists",
    7: "PFF: Paleo Freedom Fighters",
    8: "HHN: Holistic Health Naturalists",
    9: "MFL: Medical Freedom Libertarians",
    10: "VS: Vaccine Skeptics",
    11: "UCP: Universal Care Progressives",
    12: "FJP: Faith & Justice Progressives",
    13: "HCP: Health Care Protectionists",
    14: "HAD: Health Abundance Democrats",
    15: "HCI: Health Care Incrementalists",
    16: "GHI: Global Health Institutionalists",
}

# System variables always in this order, always first
SYSTEM_VARS = [
    ("resp_id",         "Respondent ID"),
    ("psid",            "Dynata panel ID"),
    ("study_code",      "Study code"),
    ("segment_id",      "PRISM segment (1-16)"),
    ("seg_probability", "Softmax P for assigned segment"),
    ("seg_gap",         "P1 minus P2 classification gap"),
    ("seg_entropy",     "Classification entropy"),
    ("typing_module",   "Typing battery GOP or DEM"),
    ("xrandom4",        "Persona vs control split"),
    ("xinvestvar",      "Investment variable cell"),
    ("msg_version",     "MaxDiff BIBD version"),
    ("complete_ts",     "Completion timestamp"),
]

ROI_VARS = [
    ("movement_score",   "ROI movement component (persuasion)"),
    ("position_score",   "ROI position component (coalition)"),
    ("activation_score", "ROI activation component"),
    ("influence_score",  "ROI influence component"),
    ("roi_realtime",     "ROI total score"),
    ("bcs",              "Behavioral Confirmation Score"),
    ("ars_adj",          "Anchor Readiness Score"),
]


def export_spss(conn, study_code: str, study_config: dict) -> bytes:
    """
    Build .sav bytes for a study. Returns raw bytes for streaming.
    """
    logger.info(f"Export: {study_code}")

    # Load data
    respondents = _load_respondents(conn, study_code)
    if not respondents:
        return _write_empty_sav(study_code)

    resp_ids    = [r["resp_id"] for r in respondents]
    session_map = _load_session_data(conn, resp_ids)
    roi_map     = _load_roi_data(conn, study_code, resp_ids)

    # Build variable list from config
    study_vars = _vars_from_config(study_config)

    # Assemble dataframe
    df, col_labels, val_labels = _assemble(
        respondents, session_map, roi_map, study_vars
    )

    logger.info(f"Export: {len(df)} rows × {len(df.columns)} cols")
    return _to_sav_bytes(df, col_labels, val_labels, study_code)


def _load_respondents(conn, study_code):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT resp_id, psid, study_code, segment_id,
                   seg_probability, seg_gap, seg_entropy,
                   typing_module, xrandompick AS msg_version,
                   status, complete_ts
            FROM respondents
            WHERE study_code = %s AND status = 'complete'
            ORDER BY complete_ts ASC
        """, (study_code,))
        return [dict(r) for r in cur.fetchall()]


def _load_session_data(conn, resp_ids):
    if not resp_ids:
        return {}
    placeholders = ",".join(["%s"] * len(resp_ids))
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT resp_id, key, value FROM session_data "
            f"WHERE resp_id IN ({placeholders})",
            resp_ids
        )
        rows = cur.fetchall()
    result = {}
    for resp_id, key, value in rows:
        if resp_id not in result:
            result[resp_id] = {}
        try:
            result[resp_id][key] = json.loads(value)
        except Exception:
            result[resp_id][key] = {}
    return result


def _load_roi_data(conn, study_code, resp_ids):
    if not resp_ids:
        return {}
    placeholders = ",".join(["%s"] * len(resp_ids))
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT resp_id, movement_score, position_score, "
            f"activation_score, influence_score, roi_realtime, bcs, ars_adj "
            f"FROM respondent_roi "
            f"WHERE study_code = %s AND resp_id IN ({placeholders})",
            [study_code] + resp_ids
        )
        return {r["resp_id"]: dict(r) for r in cur.fetchall()}


def _vars_from_config(config: dict) -> list[dict]:
    """
    Walk the study config and return ordered list of
    {var, label, value_labels} for every study question variable.
    """
    vars_ = []

    def add(var, label, q=None):
        vl = {}
        if q:
            for opt in q.get("options", []):
                v, l = opt.get("value"), opt.get("label", "")
                if v is not None:
                    vl[v] = str(l)[:60]
        vars_.append({"var": var, "label": label[:120], "value_labels": vl})

    def walk_questions(questions, section_label=""):
        for q in questions:
            var   = q.get("var", "")
            label = q.get("question_text", var)
            add(var, label, q)
            for sub in (q.get("items", []) + q.get("items_always", []) +
                        q.get("items_split_a", []) + q.get("items_split_b", [])):
                add(sub.get("var", ""), sub.get("text", sub.get("var", "")), q)

    walk_questions(config.get("pre_test",  {}).get("questions", []))

    # Investment awareness
    inv = config.get("investment_variable", {})
    if inv:
        prefix = config.get("study", {}).get("topic_prefix", "")
        avar   = f"{prefix}_INVEST_AWARE" if prefix else "INVEST_AWARE"
        add(avar, "Investment awareness",
            {"options": [
                {"value":1,"label":"Yes, heard a lot"},
                {"value":2,"label":"Yes, a little"},
                {"value":3,"label":"Heard name only"},
                {"value":4,"label":"No, never heard"},
                {"value":99,"label":"Not sure"},
            ]})

    # MaxDiff items — B-W score per item (best=1, worst=-1, neither=0)
    for item in config.get("msg_maxdiff", {}).get("items", []):
        add(item.get("item_id",""),
            f"MSG: {item.get('control_text','')[:80]}",
            {"options":[{"value":1,"label":"Best"},{"value":-1,"label":"Worst"},{"value":0,"label":"Neither"}]})

    walk_questions(config.get("post_test",        {}).get("questions", []))
    walk_questions(config.get("mob_battery",      {}).get("questions", []))
    walk_questions(config.get("adv_battery",      {}).get("questions", []))
    walk_questions(config.get("bespoke_questions",{}).get("questions", []))

    return vars_


def _assemble(respondents, session_map, roi_map, study_vars):
    sys_names  = [v[0] for v in SYSTEM_VARS]
    roi_names  = [v[0] for v in ROI_VARS]
    study_names = [v["var"] for v in study_vars]
    all_cols   = sys_names + study_names + roi_names

    col_labels = {v[0]: v[1] for v in SYSTEM_VARS}
    col_labels.update({v["var"]: v["label"] for v in study_vars})
    col_labels.update({v[0]: v[1] for v in ROI_VARS})

    val_labels = {"segment_id": SEGMENT_LABELS}
    for v in study_vars:
        if v["value_labels"]:
            val_labels[v["var"]] = v["value_labels"]

    rows = []
    for r in respondents:
        rid     = r["resp_id"]
        session = session_map.get(rid, {})
        roi     = roi_map.get(rid, {})
        splits  = session.get("splits", {})

        # Flatten all responses.* into one dict
        flat = {}
        for key, val in session.items():
            if key.startswith("responses.") and isinstance(val, dict):
                flat.update(val)

        row = {
            "resp_id":         r.get("resp_id",""),
            "psid":            r.get("psid",""),
            "study_code":      r.get("study_code",""),
            "segment_id":      r.get("segment_id"),
            "seg_probability": r.get("seg_probability"),
            "seg_gap":         r.get("seg_gap"),
            "seg_entropy":     r.get("seg_entropy"),
            "typing_module":   r.get("typing_module",""),
            "xrandom4":        splits.get("xrandom4",""),
            "xinvestvar":      splits.get("xinvestvar",""),
            "msg_version":     r.get("msg_version"),
            "complete_ts":     str(r["complete_ts"]) if r.get("complete_ts") else "",
        }
        for v in study_vars:
            row[v["var"]] = flat.get(v["var"])
        for v in ROI_VARS:
            row[v[0]] = roi.get(v[0])

        rows.append(row)

    df = pd.DataFrame(rows, columns=all_cols)

    # Type coercion: string cols stay string, everything else numeric
    str_cols = {"resp_id","psid","study_code","typing_module",
                "xrandom4","xinvestvar","complete_ts"}
    for col in df.columns:
        if col in str_cols:
            df[col] = df[col].fillna("").astype(str)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df, col_labels, val_labels


def _to_sav_bytes(df, col_labels, val_labels, study_code) -> bytes:
    buf = io.BytesIO()
    pyreadstat.write_sav(
        df,
        buf,
        column_labels         = col_labels,
        variable_value_labels = val_labels,
        file_label            = f"PRISM {study_code} {datetime.now().strftime('%Y-%m-%d')}",
    )
    buf.seek(0)
    return buf.read()


def _write_empty_sav(study_code: str) -> bytes:
    """Return an empty .sav with just system columns when no completes exist."""
    df = pd.DataFrame(columns=[v[0] for v in SYSTEM_VARS])
    buf = io.BytesIO()
    pyreadstat.write_sav(
        df, buf,
        column_labels={v[0]: v[1] for v in SYSTEM_VARS},
        file_label=f"PRISM {study_code} — no completes",
    )
    buf.seek(0)
    return buf.read()
