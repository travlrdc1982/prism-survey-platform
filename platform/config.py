"""
PRISM Survey Platform — Configuration and Database
"""

import os
import json
import sqlite3
from pathlib import Path
from functools import lru_cache
from typing import Optional

import psycopg2
import psycopg2.pool
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


# ── SETTINGS ──────────────────────────────────────────────────────────────────

class Settings(BaseModel):
    # PostgreSQL — transactional data
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://prism:prism@localhost:5432/prism"
    )

    # SQLite — normative data (Layer 3)
    norms_db_path: str = os.getenv(
        "NORMS_DB_PATH",
        "prism_norms.db"
    )

    # Study configs directory
    configs_dir: str = os.getenv(
        "CONFIGS_DIR",
        "configs"
    )

    # BIBD design cache directory
    bibd_cache_dir: str = os.getenv(
        "BIBD_CACHE_DIR",
        "bibd_cache"
    )

    # Connection pool
    db_pool_min: int = 2
    db_pool_max: int = 20

    # Rebalance trigger
    rebalance_every_n: int = 50

    # Environment
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# ── POSTGRESQL CONNECTION POOL ─────────────────────────────────────────────────

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def init_db_pool() -> None:
    global _pool
    settings = get_settings()
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=settings.db_pool_min,
        maxconn=settings.db_pool_max,
        dsn=settings.database_url,
    )


def get_db():
    """Context manager — get a connection from the pool, return when done."""
    global _pool
    if _pool is None:
        init_db_pool()
    conn = _pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# ── SQLITE NORMS DB ────────────────────────────────────────────────────────────

def get_norms_db():
    """Open the normative SQLite database (read-only)."""
    settings = get_settings()
    conn = sqlite3.connect(
        f"file:{settings.norms_db_path}?mode=ro",
        uri=True
    )
    conn.row_factory = sqlite3.Row
    return conn


def load_segments() -> dict:
    """
    Load segment registry from prism_norms.db.
    Returns {segment_id: {abbreviation, full_name, party_block, pop_share}}
    """
    conn = get_norms_db()
    rows = conn.execute(
        "SELECT segment_id, abbreviation, full_name, party_block, pop_share "
        "FROM segments ORDER BY segment_id"
    ).fetchall()
    conn.close()
    return {
        r["segment_id"]: {
            "abbreviation": r["abbreviation"],
            "full_name":    r["full_name"],
            "party_block":  r["party_block"],
            "pop_share":    r["pop_share"],
        }
        for r in rows
    }


def load_roi_norms() -> dict:
    """
    Load ROI normative priors from prism_norms.db.
    Returns {segment_id: {roi_mean, roi_std, n_studies, n_total}}
    """
    conn = get_norms_db()
    rows = conn.execute(
        "SELECT segment_id, roi_mean, roi_std, n_studies, n_total "
        "FROM segment_roi_norms ORDER BY segment_id"
    ).fetchall()
    conn.close()
    return {
        r["segment_id"]: {
            "roi_mean":  r["roi_mean"],
            "roi_std":   r["roi_std"],
            "n_studies": r["n_studies"],
            "n_total":   r["n_total"],
        }
        for r in rows
    }


# ── STUDY CONFIG LOADER ────────────────────────────────────────────────────────

_config_cache: dict = {}


def load_study_config(study_code: str) -> dict:
    """
    Load and cache a study config JSON.
    Looks for {configs_dir}/{study_code}.json
    """
    if study_code in _config_cache:
        return _config_cache[study_code]

    settings  = get_settings()
    path      = Path(settings.configs_dir) / f"{study_code}.json"

    if not path.exists():
        raise FileNotFoundError(f"Study config not found: {path}")

    with open(path) as f:
        config = json.load(f)

    _config_cache[study_code] = config
    return config


def get_all_study_codes() -> list[str]:
    """Return all study codes with config files in the configs directory."""
    settings = get_settings()
    configs_dir = Path(settings.configs_dir)
    if not configs_dir.exists():
        return []
    return [p.stem for p in configs_dir.glob("*.json")]


def invalidate_config_cache(study_code: Optional[str] = None) -> None:
    """Clear config cache. Pass study_code to clear one, None to clear all."""
    global _config_cache
    if study_code:
        _config_cache.pop(study_code, None)
    else:
        _config_cache.clear()
