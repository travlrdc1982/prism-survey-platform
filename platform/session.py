"""
PRISM Survey Platform — Session Manager

Manages respondent state through the survey instrument.
Each respondent has a session stored in PostgreSQL.

Session lifecycle:
    1. ENTRY      — psid captured, screener begins
    2. SCREENER   — Layer 1 screener questions
    3. TYPING     — B-W typing battery
    4. ROUTED     — DQMA assigned study, within-study splits assigned
    5. IN_STUDY   — respondent answering study questions
    6. COMPLETE   — study complete, ROI computed, Dynata redirect fired
    7. TERMINATE  — terminated at any point, redirect fired
    8. OVERQUOTA  — quota full, redirect fired
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras


# ── SESSION DATA MODEL ────────────────────────────────────────────────────────

class RespondentSession:
    """
    Live respondent session. Loaded from PostgreSQL on each request.
    All state is stored in the database — no in-memory session store.
    """

    def __init__(self, resp_id: str, conn):
        self.resp_id = resp_id
        self.conn    = conn
        self._data   = self._load()

    def _load(self) -> dict:
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM respondents WHERE resp_id = %s",
                (self.resp_id,)
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Respondent {self.resp_id} not found")
            return dict(row)

    # ── Accessors ─────────────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._data.get("status", "active")

    @property
    def study_code(self) -> Optional[str]:
        return self._data.get("study_code")

    @property
    def segment_id(self) -> Optional[int]:
        return self._data.get("segment_id")

    @property
    def seg_probability(self) -> Optional[float]:
        return self._data.get("seg_probability")

    @property
    def psid(self) -> str:
        return self._data.get("psid", "")

    @property
    def party_block(self) -> Optional[str]:
        """GOP or DEM — stored after typing battery routing."""
        return self._data.get("typing_module")

    # ── State updates ─────────────────────────────────────────────────────────

    def record_screener(
        self,
        qvote: Optional[int] = None,
        qgender: Optional[int] = None,
        qage: Optional[int] = None,
        qzip: Optional[str] = None,
        qparty: Optional[int] = None,
        qparty_lean: Optional[int] = None,
        screener_data: Optional[dict] = None,
    ) -> None:
        """Record screener responses. Stores in respondents row."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE respondents SET
                    updated_at = NOW()
                WHERE resp_id = %s
            """, (self.resp_id,))
        self.conn.commit()

        # Store screener data in session_data table
        if screener_data:
            self._upsert_session_data("screener", screener_data)

    def record_typing_result(
        self,
        segment_id: int,
        party_block: str,
        seg_probability: float,
        seg_gap: float,
        seg_entropy: float,
        all_probs: dict,
    ) -> None:
        """Record typing tool results."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE respondents SET
                    segment_id      = %s,
                    typing_module   = %s,
                    seg_probability = %s,
                    seg_gap         = %s,
                    seg_entropy     = %s,
                    xseg_final_1    = %s
                WHERE resp_id = %s
            """, (
                segment_id, party_block, seg_probability,
                seg_gap, seg_entropy, segment_id,
                self.resp_id
            ))
        self.conn.commit()
        self._data["segment_id"]      = segment_id
        self._data["typing_module"]   = party_block
        self._data["seg_probability"] = seg_probability

        self._upsert_session_data("typing_probs", all_probs)

    def record_routing(
        self,
        study_code: str,
        xrandom4: str,
        xinvestvar: Optional[str] = None,
        msg_version: Optional[int] = None,
    ) -> None:
        """Record DQMA routing and within-study split assignments."""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE respondents SET
                    study_code  = %s,
                    xrandompick = %s
                WHERE resp_id = %s
            """, (study_code, msg_version, self.resp_id))
        self.conn.commit()
        self._data["study_code"] = study_code

        splits = {
            "xrandom4":   xrandom4,
            "xinvestvar": xinvestvar,
            "msg_version": msg_version,
        }
        self._upsert_session_data("splits", splits)

    def record_responses(self, page_id: str, responses: dict) -> None:
        """Store respondent answers for a question page."""
        self._upsert_session_data(f"responses.{page_id}", responses)

    def get_responses(self, page_id: str) -> dict:
        """Retrieve stored responses for a page."""
        return self._get_session_data(f"responses.{page_id}") or {}

    def get_all_responses(self) -> dict:
        """Retrieve all stored responses across all pages."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT key, value FROM session_data
                WHERE resp_id = %s AND key LIKE 'responses.%%'
            """, (self.resp_id,))
            rows = cur.fetchall()

        all_responses = {}
        for key, value in rows:
            page_responses = json.loads(value)
            all_responses.update(page_responses)
        return all_responses

    def get_splits(self) -> dict:
        """Retrieve split assignments."""
        return self._get_session_data("splits") or {}

    def get_screener_data(self) -> dict:
        """Retrieve screener responses."""
        return self._get_session_data("screener") or {}

    # ── Internal storage ──────────────────────────────────────────────────────

    def _upsert_session_data(self, key: str, value: dict) -> None:
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO session_data (resp_id, key, value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (resp_id, key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
            """, (self.resp_id, key, json.dumps(value)))
        self.conn.commit()

    def _get_session_data(self, key: str) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM session_data WHERE resp_id = %s AND key = %s",
                (self.resp_id, key)
            )
            row = cur.fetchone()
        return json.loads(row[0]) if row else None


# ── SESSION CREATION ──────────────────────────────────────────────────────────

def create_session(psid: str, source: Optional[str], conn) -> str:
    """
    Create a new respondent session. Called on Dynata entry.
    Returns resp_id (UUID).
    """
    resp_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO respondents (resp_id, psid, source, status, entry_ts)
            VALUES (%s, %s, %s, 'active', NOW())
        """, (resp_id, psid, source))
    conn.commit()
    return resp_id


def load_session(resp_id: str, conn) -> RespondentSession:
    """Load an existing session."""
    return RespondentSession(resp_id, conn)


# ── WITHIN-STUDY QUOTA ASSIGNMENT ─────────────────────────────────────────────

def assign_random_split(
    conn,
    study_code: str,
    split_id: str,
    cells: list[dict],
) -> str:
    """
    Assign respondent to the least-filled cell of a random split.
    Uses SELECT FOR UPDATE to prevent concurrent over-assignment.

    cells: list of {value, label, target_share}
    Returns: assigned cell value (e.g. 'r1', 'r2')
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cell_value, C
            FROM within_study_quota_state
            WHERE study_code = %s AND split_id = %s
            ORDER BY C ASC
            FOR UPDATE
        """, (study_code, split_id))
        rows = cur.fetchall()

        if not rows:
            # Initialize cells
            for cell in cells:
                cur.execute("""
                    INSERT INTO within_study_quota_state
                        (study_code, split_id, split_type, cell_value, cell_label, C)
                    VALUES (%s, %s, 'analytical', %s, %s, 0)
                    ON CONFLICT DO NOTHING
                """, (study_code, split_id, cell["value"], cell.get("label", "")))
            conn.commit()
            return cells[0]["value"]

        # Least-filled cell
        assigned_value = rows[0][0]

        cur.execute("""
            UPDATE within_study_quota_state
            SET C = C + 1, updated_at = NOW()
            WHERE study_code = %s AND split_id = %s AND cell_value = %s
        """, (study_code, split_id, assigned_value))

    conn.commit()
    return assigned_value


def assign_eligibility_gated_split(
    conn,
    study_code: str,
    split_id: str,
    cells: list[dict],
    respondent_responses: dict,
) -> Optional[str]:
    """
    Assign respondent to an eligibility-gated split cell.
    Filters to eligible cells based on respondent's responses,
    then assigns to least-filled eligible cell.

    cells: list of {value, label, always_eligible, company_row}
    respondent_responses: flat dict of all respondent answers so far
    Returns: assigned cell value, or None if no eligible cells
    """
    # Determine eligible cells
    eligible_cells = []
    for cell in cells:
        if cell.get("always_eligible"):
            eligible_cells.append(cell)
            continue
        company_row = cell.get("company_row")
        if company_row and respondent_responses.get(company_row) != 99:
            eligible_cells.append(cell)

    if not eligible_cells:
        return None

    with conn.cursor() as cur:
        eligible_values = [c["value"] for c in eligible_cells]
        placeholders = ",".join(["%s"] * len(eligible_values))

        cur.execute(f"""
            SELECT cell_value, C
            FROM within_study_quota_state
            WHERE study_code = %s AND split_id = %s
              AND cell_value IN ({placeholders})
            ORDER BY C ASC
            FOR UPDATE
        """, [study_code, split_id] + eligible_values)
        rows = cur.fetchall()

        if not rows:
            # Initialize eligible cells
            for cell in eligible_cells:
                cur.execute("""
                    INSERT INTO within_study_quota_state
                        (study_code, split_id, split_type, cell_value, cell_label, C)
                    VALUES (%s, %s, 'analytical', %s, %s, 0)
                    ON CONFLICT DO NOTHING
                """, (study_code, split_id, cell["value"], cell.get("label", "")))
            conn.commit()
            return eligible_cells[0]["value"]

        assigned_value = rows[0][0]
        cur.execute("""
            UPDATE within_study_quota_state
            SET C = C + 1, updated_at = NOW()
            WHERE study_code = %s AND split_id = %s AND cell_value = %s
        """, (study_code, split_id, assigned_value))

    conn.commit()
    return assigned_value
