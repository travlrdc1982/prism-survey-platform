"""
PRISM Survey Platform — FastAPI Application
Layer 1: Hardcoded platform infrastructure

Endpoints:
    GET  /survey/entry          — Dynata entry, create session, serve screener
    POST /survey/screener       — Screener responses, route to typing battery
    POST /survey/typing         — Typing battery responses, segment assignment + DQMA routing
    GET  /survey/study/{page}   — Serve study page from Layer 2 config
    POST /survey/study/{page}   — Record study page responses, advance to next page
    POST /survey/complete       — Compute ROI, fire Dynata complete redirect
    GET  /survey/terminate      — Fire Dynata terminate redirect
    GET  /survey/overquota      — Fire Dynata overquota redirect

    GET  /admin/studies         — List active studies and quota state
    GET  /admin/rebalance       — Trigger manual DQMA rebalance
    POST /admin/initialize      — Initialize a new study from config
"""

import sys
import io
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Annotated

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

import os as _os
_here = _os.path.dirname(_os.path.abspath(__file__))
_root = _os.path.dirname(_here)
if _here not in sys.path:
    sys.path.insert(0, _here)
if _os.path.join(_root, 'dqma') not in sys.path:
    sys.path.insert(0, _os.path.join(_root, 'dqma'))
from dqma import (
    route_respondent, record_exit, rebalance as dqma_rebalance,
    initialize_study, evaluate_eligibility,
    compute_quota_balance_factor, check_hard_quota_caps,
    ExitType,
)
from roi import compute_roi, write_roi_result
from bibd import generate_bibd, bibd_for_study

from export import export_spss
from config import (
    get_settings, init_db_pool, get_db,
    load_study_config, get_all_study_codes,
)
from typing_tool import type_respondent, determine_batteries
from session import (
    create_session, load_session,
    assign_random_split, assign_eligibility_gated_split,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ── APP LIFECYCLE ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown. Pool init is best-effort for serverless."""
    try:
        init_db_pool()
    except Exception as e:
        logger.warning(f"DB pool init deferred (serverless ok): {e}")
        # Patch get_db to use simple connections for serverless
        import config as _cfg
        _cfg._serverless_mode = True
    logger.info("PRISM Survey Platform started")
    yield
    logger.info("PRISM Survey Platform shutting down")


class _UpperKeyConnection:
    """
    Wraps a psycopg2 connection so that DictCursor returns uppercase keys
    for columns that DQMA expects (Q, C, OQT, TERM).

    PostgreSQL folds unquoted column names to lowercase, but DQMA's queries
    reference them as uppercase via DictCursor. This shim translates.
    """

    _UPPER_COLS = {'q', 'c', 'oqt', 'term'}

    def __init__(self, conn):
        self._conn = conn

    def cursor(self, cursor_factory=None, **kwargs):
        import psycopg2.extras
        real_cur = self._conn.cursor(cursor_factory=cursor_factory, **kwargs)
        if cursor_factory in (psycopg2.extras.DictCursor, psycopg2.extras.RealDictCursor):
            return _UpperKeyCursor(real_cur, self._UPPER_COLS)
        return real_cur

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _UpperKeyCursor:
    """Wraps a DictCursor to uppercase select column keys."""

    def __init__(self, cursor, upper_cols):
        self._cursor = cursor
        self._upper_cols = upper_cols

    def _fix_row(self, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return {(k.upper() if k in self._upper_cols else k): v for k, v in row.items()}
        # psycopg2 DictRow — convert to dict first
        try:
            d = dict(row)
            return {(k.upper() if k in self._upper_cols else k): v for k, v in d.items()}
        except Exception:
            return row

    def fetchone(self):
        return self._fix_row(self._cursor.fetchone())

    def fetchall(self):
        return [self._fix_row(r) for r in self._cursor.fetchall()]

    def execute(self, *args, **kwargs):
        return self._cursor.execute(*args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def _get_db_serverless():
    """Serverless-compatible DB connection — no pool, just connect/close."""
    import psycopg2 as _pg2
    settings = get_settings()
    conn = _pg2.connect(settings.database_url)
    try:
        yield _UpperKeyConnection(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Override get_db to fall back to serverless mode
_original_get_db = get_db

def get_db_with_fallback():
    """Try pool first, fall back to direct connection."""
    import config as _cfg
    if getattr(_cfg, '_serverless_mode', False) or _cfg._pool is None:
        yield from _get_db_serverless()
    else:
        for conn in _original_get_db():
            yield _UpperKeyConnection(conn)


app = FastAPI(
    title="PRISM Survey Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.dependency_overrides[get_db] = get_db_with_fallback


# ── PYDANTIC MODELS ───────────────────────────────────────────────────────────

class ScreenerPayload(BaseModel):
    resp_id:     str
    qvote:       Optional[int] = None    # voter registration (1=yes, 2=no)
    qballot:     Optional[int] = None    # 2024 vote: 1=Trump, 2=Harris, 3=Other
    qparty:      Optional[int] = None    # party ID 1-7
    qgender:     Optional[int] = None
    qage:        Optional[int] = None
    qzip:        Optional[str] = None
    extra:       Optional[dict] = None   # pre-routing study questions


class TypingPayload(BaseModel):
    resp_id:        str
    battery:        str                  # GOP | DEM | BOTH
    raw_responses:  dict[str, float]     # {item_id: score}


class PageResponsePayload(BaseModel):
    resp_id:   str
    page_id:   str
    responses: dict                      # {var_name: value}


class InitializeStudyPayload(BaseModel):
    study_code: str
    n_base:     int = 75


# ── DYNATA ENTRY ──────────────────────────────────────────────────────────────

@app.get("/survey/entry")
async def survey_entry(
    psid:   str = Query(..., description="Dynata respondent ID"),
    source: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """
    Dynata entry point. Creates respondent session, returns session token.
    The frontend uses resp_id to track state through the instrument.
    """
    resp_id = create_session(psid=psid, source=source, conn=db)
    logger.info(f"Entry: resp_id={resp_id} psid={psid}")

    return {
        "resp_id":  resp_id,
        "next":     "screener",
        "status":   "ok",
    }


# ── SCREENER ──────────────────────────────────────────────────────────────────

@app.post("/survey/screener")
async def submit_screener(
    payload: ScreenerPayload,
    db=Depends(get_db),
):
    """
    Receive Layer 1 screener responses.
    Determines battery assignment from QBALLOT + QPARTY.
    Terminates non-voters and true independents before typing.
    """
    from typing_tool import determine_batteries

    session = load_session(payload.resp_id, db)

    screener_data = {k: v for k, v in {
        "qvote":   payload.qvote,
        "qballot": payload.qballot,
        "qparty":  payload.qparty,
        "qgender": payload.qgender,
        "qage":    payload.qage,
        "qzip":    payload.qzip,
    }.items() if v is not None}
    if payload.extra:
        screener_data.update(payload.extra)

    session.record_screener(screener_data=screener_data)

    # ── Non-voter terminate ────────────────────────────────────────────────────
    # qvote=2 (not registered) or qballot missing/invalid → terminate
    if payload.qvote == 2:
        logger.info(f"Terminate: not registered resp_id={payload.resp_id}")
        return {"resp_id": payload.resp_id, "status": "terminate", "next": "terminate"}

    qballot = payload.qballot or 0
    qparty  = payload.qparty  or 4   # default to Independent if missing

    # ── Battery routing ────────────────────────────────────────────────────────
    battery = determine_batteries(qballot, qparty)

    if battery == "TERMINATE":
        logger.info(
            f"Terminate: true independent resp_id={payload.resp_id} "
            f"qballot={qballot} qparty={qparty}"
        )
        return {"resp_id": payload.resp_id, "status": "terminate", "next": "terminate"}

    logger.info(
        f"Battery: resp_id={payload.resp_id} battery={battery} "
        f"qballot={qballot} qparty={qparty}"
    )

    return {
        "resp_id": payload.resp_id,
        "battery": battery,          # GOP | DEM | BOTH
        "next":    "typing",
        "status":  "ok",
    }


# ── TYPING TOOL ───────────────────────────────────────────────────────────────

@app.post("/survey/typing")
async def submit_typing(
    payload: TypingPayload,
    db=Depends(get_db),
):
    """
    Receive typing battery responses.
    Runs typing algorithm, calls DQMA router, assigns within-study splits.
    """
    session = load_session(payload.resp_id, db)

    # ── 1. Type the respondent ─────────────────────────────────────────────
    try:
        result = type_respondent(
            battery       = payload.battery,
            raw_responses = payload.raw_responses,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Typing failed for resp_id={payload.resp_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Typing error: {e}")

    session.record_typing_result(
        segment_id      = result.segment_id,
        party_block     = result.party_block,
        seg_probability = result.seg_probability,
        seg_gap         = result.seg_gap,
        seg_entropy     = result.seg_entropy,
        all_probs       = result.all_probs,
    )

    # Store D² distances and second-best segment in session_data
    sorted_segs = sorted(result.all_probs.items(), key=lambda x: x[1], reverse=True)
    xseg_final_2 = sorted_segs[1][0] if len(sorted_segs) > 1 else None
    session.record_responses("typing_diagnostics", {
        "d2_values":    {str(k): round(v, 4) for k, v in result.d2_values.items()},
        "all_probs":    {str(k): round(v, 6) for k, v in result.all_probs.items()},
        "xseg_final_1": result.segment_id,
        "xseg_final_2": xseg_final_2,
        "seg_probability": round(result.seg_probability, 6),
        "seg_gap":      round(result.seg_gap, 6),
        "seg_entropy":  round(result.seg_entropy, 6),
        "party_block":  result.party_block,
    })

    logger.info(
        f"Typed: resp_id={payload.resp_id} "
        f"seg={result.segment_id} P={result.seg_probability:.3f} "
        f"gap={result.seg_gap:.3f}"
    )

    # ── 2. Get screener data for eligibility evaluation ────────────────────
    screener_data = session.get_screener_data()

    # ── 3. Route via DQMA ─────────────────────────────────────────────────
    try:
        assigned_study = route_respondent(
            conn            = db,
            resp_id         = payload.resp_id,
            segment_id      = result.segment_id,
            seg_probability = result.seg_probability,
            screener_data   = screener_data,
        )
    except Exception as e:
        logger.error(f"DQMA routing failed for resp_id={payload.resp_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Routing error: {e}")

    if assigned_study is None:
        # No study available — overquota or all studies closed
        logger.info(f"No study available for resp_id={payload.resp_id}")
        return {
            "resp_id": payload.resp_id,
            "status":  "overquota",
            "next":    "overquota",
        }

    # ── 4. Assign within-study splits ─────────────────────────────────────
    study_config = load_study_config(assigned_study)

    xrandom4   = None
    xinvestvar = None
    msg_version = None

    wq = study_config.get("within_study_quotas", {})
    for split in wq.get("splits", []):
        split_id = split["split_id"]
        cells    = split["cells"]

        if split["type"] == "random_split":
            value = assign_random_split(db, assigned_study, split_id, cells)
            if split_id == "XRANDOM4":
                xrandom4 = value

        elif split["type"] == "eligibility_gated":
            all_responses = session.get_all_responses()
            all_responses.update(screener_data)
            value = assign_eligibility_gated_split(
                db, assigned_study, split_id, cells, all_responses
            )
            if split_id == "XINVESTVAR":
                xinvestvar = value

    # ── 5. Assign BIBD MaxDiff version ────────────────────────────────────
    bibd_specs = study_config.get("bibd_specs", {})
    if bibd_specs:
        spec_key = next(iter(bibd_specs))
        version_split_id = f"{assigned_study}_MSG_VERSION"
        n_versions = study_config.get("msg_maxdiff", {}).get("n_tasks", 11)
        version_cell = assign_random_split(
            db, assigned_study, version_split_id,
            [{"value": str(i), "label": f"v{i}"} for i in range(1, n_versions + 1)]
        )
        msg_version = int(version_cell)

    session.record_routing(
        study_code  = assigned_study,
        xrandom4    = xrandom4,
        xinvestvar  = xinvestvar,
        msg_version = msg_version,
    )

    logger.info(
        f"Routed: resp_id={payload.resp_id} → {assigned_study} "
        f"xrandom4={xrandom4} xinvestvar={xinvestvar} msg_v={msg_version}"
    )

    return {
        "resp_id":         payload.resp_id,
        "study_code":      assigned_study,
        "segment_id":      result.segment_id,
        "xseg_final_2":    xseg_final_2,
        "seg_probability":  round(result.seg_probability, 4),
        "seg_gap":          round(result.seg_gap, 4),
        "seg_entropy":      round(result.seg_entropy, 4),
        "all_probs":       {str(k): round(v, 4) for k, v in result.all_probs.items()},
        "d2_values":       {str(k): round(v, 4) for k, v in result.d2_values.items()},
        "party_block":     result.party_block,
        "xrandom4":        xrandom4,
        "xinvestvar":      xinvestvar,
        "msg_version":     msg_version,
        "next":            "study",
        "status":          "ok",
    }


# ── STUDY INSTRUMENT ──────────────────────────────────────────────────────────

@app.get("/survey/study/{page_id}")
async def get_study_page(
    page_id:  str,
    resp_id:  str = Query(...),
    db=Depends(get_db),
):
    """
    Serve a study question page.
    Reads the study config, resolves conditional display,
    personalizes MaxDiff items by segment and split condition.
    """
    session      = load_session(resp_id, db)
    study_code   = session.study_code
    if not study_code:
        raise HTTPException(status_code=400, detail="Respondent not routed to a study")

    study_config = load_study_config(study_code)
    splits       = session.get_splits()

    segment_id   = session.segment_id
    xrandom4     = splits.get("xrandom4", "r1")
    xinvestvar   = splits.get("xinvestvar", "r1")
    msg_version  = splits.get("msg_version", 1)
    is_persona   = (xrandom4 == "r1")  # persona variant vs control

    # Resolve the page content from config
    # Developer implements full page resolver — this returns the raw config section
    page_content = _resolve_page(
        study_config = study_config,
        page_id      = page_id,
        segment_id   = segment_id,
        is_persona   = is_persona,
        xinvestvar   = xinvestvar,
        msg_version  = msg_version,
        conn         = db,
    )

    return {
        "resp_id":    resp_id,
        "page_id":    page_id,
        "content":    page_content,
        "status":     "ok",
    }


@app.post("/survey/study/{page_id}")
async def submit_study_page(
    page_id:  str,
    payload:  PageResponsePayload,
    db=Depends(get_db),
):
    """Record responses for a study page and advance to next."""
    session = load_session(payload.resp_id, db)
    session.record_responses(page_id, payload.responses)

    study_config = load_study_config(session.study_code)
    next_page = _get_next_page(page_id, study_config, session)

    return {
        "resp_id": payload.resp_id,
        "page_id": page_id,
        "status":  "ok" if next_page else "complete",
        "next":    next_page or "complete",
    }


# ── COMPLETION ────────────────────────────────────────────────────────────────

@app.post("/survey/complete")
async def survey_complete(
    resp_id: str,
    db=Depends(get_db),
):
    """
    Respondent has completed all study questions.
    Computes ROI, records exit, fires Dynata complete redirect.
    """
    session      = load_session(resp_id, db)
    study_code   = session.study_code
    segment_id   = session.segment_id
    study_config = load_study_config(study_code)

    # ── Compute ROI ────────────────────────────────────────────────────────
    all_responses = session.get_all_responses()
    try:
        roi_result = compute_roi(all_responses, study_config)
        write_roi_result(db, resp_id, study_code, segment_id, roi_result)
    except Exception as e:
        logger.error(f"ROI computation failed for resp_id={resp_id}: {e}")
        # Don't block completion on ROI failure

    # ── Record exit ────────────────────────────────────────────────────────
    record_exit(db, resp_id, study_code, segment_id, ExitType.COMPLETE)

    # ── Check rebalance trigger ────────────────────────────────────────────
    _maybe_rebalance(db, study_code)

    # ── Fire Dynata redirect ───────────────────────────────────────────────
    redirect_url = _build_redirect_url(study_config, "complete", session.psid)
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/survey/terminate")
async def survey_terminate(
    resp_id: str,
    db=Depends(get_db),
):
    """Terminate respondent and fire Dynata terminate redirect."""
    session    = load_session(resp_id, db)
    study_code = session.study_code
    segment_id = session.segment_id

    if study_code and segment_id:
        record_exit(db, resp_id, study_code, segment_id, ExitType.TERMINATE)

    study_config = load_study_config(study_code) if study_code else {}
    redirect_url = _build_redirect_url(study_config, "terminate", session.psid)
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/survey/overquota")
async def survey_overquota(
    resp_id: str,
    psid:    Optional[str] = Query(None),
    db=Depends(get_db),
):
    """Fire Dynata overquota redirect."""
    # May be called before routing — psid passed as query param
    try:
        session    = load_session(resp_id, db)
        study_code = session.study_code
        psid       = psid or session.psid
    except Exception:
        study_code = None

    study_config = load_study_config(study_code) if study_code else {}
    redirect_url = _build_redirect_url(study_config, "overquota", psid or "")
    return RedirectResponse(url=redirect_url, status_code=302)


# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.get("/admin/studies")
async def admin_studies(db=Depends(get_db)):
    """Return quota state for all active studies."""
    import psycopg2.extras
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                sr.study_code, sr.phase, sr.kappa,
                SUM(ds.C)   AS total_completes,
                SUM(ds.Q)   AS total_quota,
                SUM(ds.OQT) AS total_oqt,
                SUM(ds.TERM) AS total_terms,
                COUNT(*)    AS n_segments
            FROM study_registry sr
            JOIN dqma_state ds ON ds.study_code = sr.study_code
            WHERE sr.active = TRUE
            GROUP BY sr.study_code, sr.phase, sr.kappa
            ORDER BY sr.study_code
        """)
        studies = cur.fetchall()

    return {"studies": [dict(s) for s in studies]}


@app.get("/admin/export/{study_code}")
async def admin_export(
    study_code: str,
    db=Depends(get_db),
):
    """
    Export all completes for a study as an SPSS .sav file.
    Returns a file download. Call this manually whenever you want fresh data.
    """
    study_config = load_study_config(study_code)
    try:
        sav_bytes = export_spss(conn=db, study_code=study_code, study_config=study_config)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed for {study_code}: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    filename = f"PRISM_{study_code}_completes.sav"
    return StreamingResponse(
        content        = iter([sav_bytes]),
        media_type     = "application/octet-stream",
        headers        = {"Content-Disposition": f'attachment; filename="{filename}"'},
    )



async def admin_rebalance(
    study_code: str,
    db=Depends(get_db),
):
    """Manually trigger DQMA rebalance for a study."""
    try:
        summary = dqma_rebalance(db, study_code)
        return {"status": "ok", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/initialize")
async def admin_initialize(
    payload: InitializeStudyPayload,
    db=Depends(get_db),
):
    """
    Initialize a new study from its config file.
    Registers in study_registry, seeds dqma_state,
    generates and caches BIBD design.
    """
    study_config = load_study_config(payload.study_code)

    # Initialize DQMA
    initialize_study(
        conn        = db,
        study_code  = payload.study_code,
        n_base      = payload.n_base,
    )

    # Generate and persist BIBD design if needed
    bibd_specs = study_config.get("bibd_specs", {})
    if bibd_specs:
        bibd_result = bibd_for_study(study_config, n_versions=11)
        _persist_bibd(db, payload.study_code, bibd_result)
        _cache_bibd(payload.study_code, bibd_result)

    logger.info(f"Study initialized: {payload.study_code}")
    return {
        "status":     "ok",
        "study_code": payload.study_code,
        "n_base":     payload.n_base,
        "bibd":       bool(bibd_specs),
    }


@app.get("/admin/export/{study_code}")
async def admin_export(
    study_code: str,
    db=Depends(get_db),
):
    """
    Export study data as SPSS .sav file. Completes only.
    Returns file download — open directly in browser or wget.

    Usage:
        curl -o AL_export.sav http://host/admin/export/AL
    """
    from export import export_spss

    study_config = load_study_config(study_code)

    sav_bytes = export_spss(
        conn         = db,
        study_code   = study_code,
        study_config = study_config,
    )

    filename = f"{study_code}_{datetime.now().strftime('%Y%m%d')}.sav"

    return StreamingResponse(
        io.BytesIO(sav_bytes),
        media_type  = "application/octet-stream",
        headers     = {"Content-Disposition": f"attachment; filename={filename}"},
    )

def _build_redirect_url(study_config: dict, redirect_type: str, psid: str) -> str:
    """Build Dynata redirect URL with psid token substitution."""
    dynata = study_config.get("dynata", {})
    key_map = {
        "complete":   "complete_redirect",
        "terminate":  "terminate_redirect",
        "overquota":  "overquota_redirect",
    }
    template = dynata.get(key_map.get(redirect_type, "terminate_redirect"), "")
    if not template:
        return f"https://www.samplicio.us/router/{redirect_type}?psid={psid}"
    return template.replace("{psid}", psid)


def _maybe_rebalance(conn, study_code: str) -> None:
    """Check if rebalance should trigger. Called after each completion."""
    import psycopg2.extras
    with conn.cursor() as cur:
        cur.execute(
            "SELECT SUM(C) FROM dqma_state WHERE study_code = %s",
            (study_code,)
        )
        total_c = cur.fetchone()[0] or 0

    settings = get_settings()
    if total_c % settings.rebalance_every_n == 0:
        try:
            dqma_rebalance(conn, study_code)
            logger.info(f"Auto-rebalance triggered: {study_code} at n={total_c}")
        except Exception as e:
            logger.error(f"Rebalance failed: {e}")


_bibd_cache: dict = {}


def _cache_bibd(study_code: str, bibd_result: dict) -> None:
    """Cache BIBD in memory after loading from DB."""
    _bibd_cache[study_code] = bibd_result


def _persist_bibd(conn, study_code: str, bibd_result: dict) -> None:
    """Write BIBD versions to study_bibd table. Called at study initialization."""
    versions = bibd_result.get("versions", [])
    with conn.cursor() as cur:
        cur.execute("DELETE FROM study_bibd WHERE study_code = %s", (study_code,))
        rows = []
        for v_idx, version in enumerate(versions):
            for t_idx, task in enumerate(version):
                for p_idx, item_num in enumerate(task):
                    rows.append((study_code, v_idx + 1, t_idx + 1, p_idx + 1, item_num))
        if rows:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO study_bibd (study_code, version_num, task_num, position, item_num) "
                "VALUES %s",
                rows,
            )
    conn.commit()


def _load_bibd_from_db(conn, study_code: str) -> Optional[dict]:
    """Load BIBD from DB into cache. Returns None if not found."""
    import psycopg2.extras as _extras
    with conn.cursor(cursor_factory=_extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT version_num, task_num, position, item_num "
            "FROM study_bibd WHERE study_code = %s "
            "ORDER BY version_num, task_num, position",
            (study_code,)
        )
        rows = cur.fetchall()

    if not rows:
        return None

    # Reconstruct versions structure
    from collections import defaultdict
    versions_dict = defaultdict(lambda: defaultdict(list))
    for row in rows:
        versions_dict[row["version_num"]][row["task_num"]].append(row["item_num"])

    versions = []
    for v_num in sorted(versions_dict):
        tasks = [versions_dict[v_num][t_num] for t_num in sorted(versions_dict[v_num])]
        versions.append(tasks)

    return {"versions": versions}


def get_bibd_version(conn, study_code: str, version: int) -> Optional[list]:
    """
    Return task matrix for a specific BIBD version.
    Reads from in-memory cache, falling back to DB on cache miss.
    """
    if study_code not in _bibd_cache:
        result = _load_bibd_from_db(conn, study_code)
        if result:
            _cache_bibd(study_code, result)

    result = _bibd_cache.get(study_code)
    if not result:
        return None
    versions = result.get("versions", [])
    if 1 <= version <= len(versions):
        return versions[version - 1]
    return None


def _resolve_page(
    study_config: dict,
    page_id:      str,
    segment_id:   int,
    is_persona:   bool,
    xinvestvar:   Optional[str],
    msg_version:  Optional[int],
    conn=None,
) -> dict:
    """
    Resolve a page from study config to its displayable content.
    Developer implements full renderer — this is the integration skeleton.

    Page IDs map to config sections:
        pre_test.{var}      → pre_test question
        msg_maxdiff         → MaxDiff battery
        post_test.{var}     → post_test question
        mob_battery         → mobilization battery
        adv_battery.{var}   → ADV question
        bespoke.{var}       → bespoke question
        investment          → investment variable stimulus
    """
    section, *rest = page_id.split(".", 1)
    var = rest[0] if rest else None

    if section == "msg_maxdiff":
        return _resolve_maxdiff(study_config, segment_id, is_persona, msg_version, conn=conn)

    if section == "investment":
        return _resolve_investment(study_config, xinvestvar)

    # For all other pages: find the question definition in config
    config_map = {
        "pre_test":    study_config.get("pre_test", {}).get("questions", []),
        "post_test":   study_config.get("post_test", {}).get("questions", []),
        "adv_battery": study_config.get("adv_battery", {}).get("questions", []),
        "bespoke":     study_config.get("bespoke_questions", {}).get("questions", []),
    }
    questions = config_map.get(section, [])
    for q in questions:
        if q.get("var") == var:
            return q

    if section == "mob_battery":
        return study_config.get("mob_battery", {})

    return {}


def _resolve_maxdiff(
    study_config: dict,
    segment_id:   int,
    is_persona:   bool,
    msg_version:  Optional[int],
    conn=None,
) -> dict:
    """
    Build MaxDiff task set for a respondent.

    Task response format (stored in session_data as 'responses.msg_maxdiff'):
        {"task_1": {"best": 3, "worst": 7}, "task_2": {"best": 11, "worst": 2}, ...}
    item_num values reference 1-based index into study config items[].
    Export reconstructs item-level B-W scores from this task structure.
    Full task data preserved for future HB estimation.
    """
    md         = study_config.get("msg_maxdiff", {})
    items      = md.get("items", [])
    study_code = study_config.get("study", {}).get("study_code", "")

    bibd_version = get_bibd_version(conn, study_code, msg_version or 1) if conn else None

    item_texts = {}
    for item in items:
        item_id = item.get("item_id", "")
        if is_persona:
            text = item.get("variant_text", {}).get(str(segment_id), item.get("control_text", ""))
        else:
            text = item.get("control_text", "")
        item_texts[item_id] = text

    return {
        "component":       "MAXDIFF.MESSAGE",
        "question_text":   md.get("question_text", ""),
        "comments_text":   md.get("comments_text", ""),
        "n_tasks":         md.get("n_tasks", 11),
        "items_per_task":  md.get("items_per_task", 4),
        "bibd_tasks":      bibd_version,
        "item_texts":      item_texts,
        "is_persona":      is_persona,
        "response_format": "task_N: {best: item_num, worst: item_num}",
    }


def _resolve_investment(study_config: dict, xinvestvar: Optional[str]) -> dict:
    """Resolve the investment variable stimulus for this respondent."""
    inv = study_config.get("investment_variable", {})
    variants = inv.get("variants", [])
    variant = next((v for v in variants if v.get("var") == xinvestvar), variants[0] if variants else {})
    return {
        "stimulus":            variant.get("stimulus", ""),
        "company":             variant.get("company", ""),
        "awareness_question":  inv.get("awareness_question", ""),
        "awareness_options":   inv.get("awareness_options", []),
    }


def _get_next_page(current_page: str, study_config: dict, session) -> Optional[str]:
    """Delegate to page_flow module."""
    from page_flow import get_next_page
    return get_next_page(current_page, study_config, session)
