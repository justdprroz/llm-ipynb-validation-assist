#!/bin/bash
set -euo pipefail
python -c "from app.seed import seed; seed()" || true
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
