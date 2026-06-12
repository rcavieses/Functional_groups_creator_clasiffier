# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Marine ecosystem modeling tool for the Gulf of California. Classifies ~10,787 marine species into functional groups for ATLANTIS ecosystem models using LLM-based classification, then provides a Streamlit web app for expert validation.

## How to Run

```bash
# Web app (validation UI)
streamlit run app.py

# Classify species with local Ollama LLM
python classifier/classify_species.py --input data/final_taxonomy_occ.csv

# Classify with Claude API
python classifier/classify_species.py --input data/species.csv --provider anthropic --workers 3

# Dynamic group creation (no pre-defined groups needed)
python classifier/main_dynamic_groups.py --input data/species.csv --batch-size 25

# DB connectivity check
python test_connection.py

# Ollama health check
python classifier/check_ollama.py
```

## Architecture

### Data Layer (`sql_client.py`)
Single file that handles all Azure SQL interaction. Uses pymssql driver with SQLAlchemy. Key functions:
- `get_db()` — engine with retry logic for Azure transient errors (codes 40613, 40197, 49918, 1205)
- `sign_in(email, password)` — PBKDF2-HMAC hash-based auth (no external auth provider)
- `load_species(db)` — fetches taxa, writes local cache at `~/.cache/species.csv` to reduce DB reads
- All mutations (validate, move, rate, propose) write an audit log entry

### LLM Classification Pipeline (`classifier/`)
Two backends, same interface — switch via `--provider` flag or `ANTHROPIC_API_KEY` env var:
- **Ollama** (default): HTTP to `localhost:11434`, model `qwen3:8b`
- **Anthropic Claude API**: uses `claude-haiku-4-5` by default

`classify_species.py` — assigns existing functional groups to taxa (25 species per batch, resume-capable)  
`main_dynamic_groups.py` — creates groups organically from species data (no pre-defined groups), outputs `dynamic_groups.json`  
`config.py` — all tunable params: MAX_GROUPS=80, batch size, LLM timeouts, scoring weights

### Streamlit Web App (`app.py` + `pages/`)
- `app.py` — login + dashboard (session state management, cache seeding)
- `pages/0_Admin.py` — manage experts, distribute groups, set descriptions
- `pages/1_Validar_Grupos.py` — main expert UI: rate groups, propose changes
- `pages/2_Validar_Especies.py` — species-level validation (validate/move/remove)
- `pages/2_Resultados_Finales.py` — export results (CSV/JSON)

## Environment Variables

See `.env.example`. Required:
```
AZURE_SQL_SERVER=gocfg.database.windows.net
AZURE_SQL_DATABASE=free-sql-db-5085999
AZURE_SQL_USER=rcavieses
AZURE_SQL_PASSWORD=...

OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen3:8b
```

Optional (for Claude API backend):
```
ANTHROPIC_API_KEY=sk-...
CLAUDE_MODEL=claude-haiku-4-5
```

Streamlit Cloud uses `.streamlit/secrets.toml` instead of `.env`.

## Key Conventions

- **UI language is Spanish** — all user-facing text, button labels, page names
- **Caching pattern:** `@st.cache_resource` for DB connections; local CSV file cache for species list
- **Azure SQL can pause** (free tier) — the retry logic in `get_db()` handles this; connection attempts may take ~60s on first wake
- `firebase_client.py` is legacy — Azure SQL (`sql_client.py`) is the active data layer
- `validator_app/` directory is obsolete — the active pages are in `pages/` at the root
- Species status values: `pending`, `validated`, `removed`
- The pre-defined 19 functional groups live in `data/functional_groups_final.csv`
