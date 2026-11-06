#!/usr/bin/env bash
# Linux/macOS: expects mongod already running on 127.0.0.1:27017 (or set MONGO_URL in backend/.env).
set -e
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
uvicorn app.main:app --reload --port 8000 &
cd ../frontend
[ -d node_modules ] || npm install
npm run dev
