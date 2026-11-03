#!/usr/bin/env bash
# One command: ./run.sh   (creates venv, installs, seeds the demo data if needed, starts the app)
# Use ./run.sh --reset to wipe and re-seed the demo data first.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
if [ "$1" = "--reset" ] || [ ! -f shaha.db ]; then python seed.py; fi
streamlit run app.py
