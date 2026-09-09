#!/usr/bin/env bash
set -e

echo "=== Starting Vignesh GrowthLab Wholesale ERP ==="

cd /app/backend

# Initialize / auto-migrate DB tables if needed
python -c "
from app.db.session import engine
from app.models import models
print('Ensuring database schema exists...')
models.Base.metadata.create_all(bind=engine)
" || true

# Seed default admin user, initial configurations, document formats
python seed.py || true
python seed_config.py || true
python seed_doc_formats.py || true

PORT=
echo "Starting FastAPI server on port $PORT..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"