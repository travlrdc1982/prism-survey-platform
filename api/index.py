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
import importlib.util

# Set up paths
root = os.path.dirname(os.path.dirname(__file__))
platform_dir = os.path.join(root, 'platform')
dqma_dir = os.path.join(root, 'dqma')

sys.path.insert(0, root)
sys.path.insert(0, dqma_dir)
sys.path.insert(0, platform_dir)

os.environ.setdefault("NORMS_DB_PATH", os.path.join(root, "prism_norms.db"))
os.environ.setdefault("CONFIGS_DIR", os.path.join(root, "configs"))

# Import main.py directly by file path to avoid conflict with stdlib 'platform'
spec = importlib.util.spec_from_file_location("prism_main", os.path.join(platform_dir, "main.py"))
prism_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prism_main)

app = prism_main.app
