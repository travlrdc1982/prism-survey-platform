# PRISM Survey Platform

Behavioral audience intelligence survey engine. 16-segment B-W typing tool, DQMA quota routing, ROI computation, SPSS export.

## Structure

```
dqma/           Algorithm layer — routing, ROI, BIBD (153 tests, do not modify)
platform/       FastAPI application layer
configs/        Study config JSON files (one per study)
api/            Vercel entry point
prism_norms.db  SQLite normative database (segments, ROI priors, typing params)
```

## Setup

```bash
pip install -r requirements.txt

# PostgreSQL schema
psql $DATABASE_URL < dqma/schema.sql

# Initialize a study
curl -X POST http://localhost:8000/admin/initialize \
  -H "Content-Type: application/json" \
  -d '{"study_code": "AL", "n_base": 75}'
```

## Running locally

```bash
cd platform
uvicorn main:app --reload
```

## Environment variables

```
DATABASE_URL    postgresql://...
NORMS_DB_PATH   ./prism_norms.db
CONFIGS_DIR     ./configs
DEBUG           false
```

## Export data

```bash
curl -o AL_20260401.sav http://localhost:8000/admin/export/AL
```

## See also

- `PRISM_Platform_Build_Brief.md` — full build specification for Claude Code
- `PRISM_Normative_Database_Spec.md` — normative database documentation
