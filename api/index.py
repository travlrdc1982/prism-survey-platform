"""
Vercel entry point for PRISM Survey Platform.
Vercel runs this as a serverless function.

NOTE: For testing only. Production should use Railway, Render, or EC2
where persistent connections and background tasks are supported.

Environment variables to set in Vercel dashboard:
  DATABASE_URL   — Supabase pooled connection string
                   (use the "Transaction" pool mode URL, not "Session")
  NORMS_DB_PATH  — /var/task/prism_norms.db  (bundled in repo)
  CONFIGS_DIR    — /var/task/configs
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dqma'))

os.environ.setdefault("NORMS_DB_PATH",  "/var/task/prism_norms.db")
os.environ.setdefault("CONFIGS_DIR",    "/var/task/configs")

from platform.main import app
