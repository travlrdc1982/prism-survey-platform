"""
PRISM Survey Platform — Page Flow Engine

Implements the instrument page sequence per build brief §1.1.
This module has no heavy dependencies (no FastAPI, no psycopg2, no dqma)
so it can be tested independently.

Sequence:
    Pre-test → Inf360 → Awareness → Info channels → Issue views →
    Critics Block A (50%) → Investment → MSG MaxDiff → Critics Block B (50%) →
    Post-test → Mobilization → ADV battery → Bespoke → Demographics → Opt-in

The session object must implement:
    - get_splits() -> dict
    - get_all_responses() -> dict
"""

import re
from typing import Optional


def build_page_sequence(study_config: dict, session) -> list[str]:
    """
    Build the full ordered page sequence for a study instrument.

    Sequence (from build brief §1.1):
        a. Inf360 gateway     (Layer 1 hardcoded)
        b. Awareness          (XX_AWARE)        — if present in config
        c. Info channels      (XX_INFO)         — if present in config
        d. Issue views        (XX_ISSUES + XX_IMP) — if present in config
        e. Critics battery    — Block A (xrandom4 == 'r1' only)
        f. Investment stimulus
        g. MSG MaxDiff
        h. Critics battery    — Block B (xrandom4 != 'r1' only)
        i. Post-test          (locked order matching pre-test)
        j. Mobilization
        k. ADV battery
        l. Bespoke questions
        m. Demographics       (Layer 1 hardcoded)
        n. Opt-in             (Layer 1 hardcoded)

    Pre-test questions come before the study instrument (served during
    the pre-routing / early study phase).
    """
    pages: list[str] = []

    # ── Pre-test questions ────────────────────────────────────────────────
    for q in study_config.get("pre_test", {}).get("questions", []):
        pages.append(f"pre_test.{q['var']}")

    # ── a. Inf360 gateway (Layer 1 hardcoded) ─────────────────────────────
    pages.append("inf360")

    # ── b. Awareness ──────────────────────────────────────────────────────
    for q in study_config.get("awareness", {}).get("questions", []):
        pages.append(f"awareness.{q['var']}")

    # ── c. Info channels ──────────────────────────────────────────────────
    for q in study_config.get("info_channels", {}).get("questions", []):
        pages.append(f"info_channels.{q['var']}")

    # ── d. Issue views ────────────────────────────────────────────────────
    for q in study_config.get("issue_views", {}).get("questions", []):
        pages.append(f"issue_views.{q['var']}")

    # ── e. Critics Block A (before MaxDiff — 50% of sample) ──────────────
    critics_enabled = study_config.get("critics_enabled", False)
    if critics_enabled:
        pages.append("critics_block_a")

    # ── f. Investment stimulus ────────────────────────────────────────────
    if study_config.get("investment_variable"):
        pages.append("investment")

    # ── g. MSG MaxDiff ────────────────────────────────────────────────────
    if study_config.get("msg_maxdiff"):
        pages.append("msg_maxdiff")

    # ── h. Critics Block B (after MaxDiff — other 50%) ───────────────────
    if critics_enabled:
        pages.append("critics_block_b")

    # ── i. Post-test (locked order) ──────────────────────────────────────
    for q in study_config.get("post_test", {}).get("questions", []):
        pages.append(f"post_test.{q['var']}")

    # ── j. Mobilization battery ──────────────────────────────────────────
    mob = study_config.get("mob_battery", {})
    if mob and mob.get("enabled", True):
        pages.append("mob_battery")

    # ── k. ADV battery ───────────────────────────────────────────────────
    for q in study_config.get("adv_battery", {}).get("questions", []):
        pages.append(f"adv_battery.{q['var']}")

    # ── l. Bespoke questions ─────────────────────────────────────────────
    for q in study_config.get("bespoke_questions", {}).get("questions", []):
        pages.append(f"bespoke.{q['var']}")

    # ── m. Demographics (Layer 1 hardcoded) ──────────────────────────────
    pages.append("demographics")

    # ── n. Opt-in (Layer 1 hardcoded) ────────────────────────────────────
    pages.append("opt_in")

    return pages


def evaluate_condition(condition: str, session) -> bool:
    """
    Evaluate a display condition against respondent's stored responses and splits.

    Supported condition formats:
        'Xrandom2.r1'              — split variable equals value
        'IF VAR=1,2,3 THEN show'   — response variable in value set

    Returns True if the question should be shown.
    """
    if not condition:
        return True

    condition = condition.strip()

    # ── Split-variable condition: 'Xrandom2.r1' ─────────────────────────
    if "." in condition and "IF" not in condition.upper():
        split_var, expected_value = condition.rsplit(".", 1)
        splits = session.get_splits() if hasattr(session, "get_splits") else {}
        all_responses = session.get_all_responses() if hasattr(session, "get_all_responses") else {}
        # Check splits first, then responses
        actual = splits.get(split_var) or splits.get(split_var.lower())
        if actual is None:
            actual = all_responses.get(split_var) or all_responses.get(split_var.lower())
        return str(actual) == str(expected_value)

    # ── COND: IF VAR=1,2,3 THEN show TARGET ─────────────────────────────
    upper = condition.upper()
    if "IF" in upper:
        m = re.match(
            r"(?:COND:\s*)?IF\s+(\w+)\s*=\s*([\w,]+)\s+THEN\b",
            condition,
            re.IGNORECASE,
        )
        if m:
            var_name = m.group(1)
            allowed_values = {v.strip() for v in m.group(2).split(",")}
            all_responses = session.get_all_responses() if hasattr(session, "get_all_responses") else {}
            actual = all_responses.get(var_name)
            if actual is None:
                return False
            return str(actual) in allowed_values

    # If we can't parse the condition, default to showing the question
    return True


def should_show_page(page_id: str, study_config: dict, session) -> bool:
    """
    Determine if a page should be shown based on conditions and split logic.

    - Critics blocks respect xrandom4 rotation
    - Individual questions may have display conditions
    """
    splits = session.get_splits() if hasattr(session, "get_splits") else {}
    xrandom4 = splits.get("xrandom4", "r1")

    # ── Critics rotation ─────────────────────────────────────────────────
    if page_id == "critics_block_a":
        return xrandom4 == "r1"
    if page_id == "critics_block_b":
        return xrandom4 != "r1"

    # ── Layer 1 hardcoded pages always show ──────────────────────────────
    if page_id in ("inf360", "demographics", "opt_in", "msg_maxdiff",
                    "investment", "mob_battery"):
        return True

    # ── Look up question-level condition from config ─────────────────────
    section, *rest = page_id.split(".", 1)
    var = rest[0] if rest else None

    config_sections = {
        "pre_test":      study_config.get("pre_test", {}).get("questions", []),
        "post_test":     study_config.get("post_test", {}).get("questions", []),
        "adv_battery":   study_config.get("adv_battery", {}).get("questions", []),
        "bespoke":       study_config.get("bespoke_questions", {}).get("questions", []),
        "awareness":     study_config.get("awareness", {}).get("questions", []),
        "info_channels": study_config.get("info_channels", {}).get("questions", []),
        "issue_views":   study_config.get("issue_views", {}).get("questions", []),
    }

    questions = config_sections.get(section, [])
    for q in questions:
        if q.get("var") == var:
            cond = q.get("condition", "")
            if cond:
                return evaluate_condition(cond, session)
            return True

    return True


def get_next_page(current_page: str, study_config: dict, session) -> Optional[str]:
    """
    Return the next page ID after the current one.

    Builds the full instrument sequence from the study config, finds the
    current page, then walks forward skipping any pages whose display
    conditions are not met for this respondent.

    Returns None when the instrument is complete.
    """
    sequence = build_page_sequence(study_config, session)

    # Find current position
    try:
        idx = sequence.index(current_page)
    except ValueError:
        # Current page not in sequence — return the first applicable page
        if not sequence:
            return None
        for page in sequence:
            if should_show_page(page, study_config, session):
                return page
        return None

    # Walk forward from current position
    for next_idx in range(idx + 1, len(sequence)):
        candidate = sequence[next_idx]
        if should_show_page(candidate, study_config, session):
            return candidate

    # No more pages — instrument is complete
    return None
