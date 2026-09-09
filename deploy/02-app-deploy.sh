#!/usr/bin/env bash
#
# Wholesale ERP — application deploy / update (CloudPanel / Debian 13)
# Usage (run as the matching SITE USER, NOT root):
#     ssh gtferp@37.221.199.121      "bash ~/02-app-deploy.sh prod"
#     ssh gtferp-dev@37.221.199.121  "bash ~/02-app-deploy.sh dev"
#
# Re-runnable: first run clones + builds; later runs pull + rebuild.
# Does NOT touch systemd (root) or nginx (CloudPanel UI) — see DEPLOY.md.
set -euo pipefail

ENV="${1:-}"
case "$ENV" in
  prod)
    SITE_USER="gtferp"
    DOMAIN="erp.globaltradeforce.com"
    BRANCH="main"
    ENV_TEMPLATE=".env.production.template"
    VITE_MODE="production"
    SERVICE="erp-backend"
    ;;
  dev)
    SITE_USER="gtferp-dev"
    DOMAIN="dev.erp.globaltradeforce.com"
    BRANCH="dev"
    ENV_TEMPLATE=".env.dev.template"
    VITE_MODE="dev"
    SERVICE="erp-backend-dev"
    ;;
  *)
    echo "Usage: $0 <prod|dev>"; exit 2 ;;
esac

REPO="https://github.com/iboomdev/GTF.git"
APP_DIR="/home/${SITE_USER}/GTF"
PY_VERSION="3.12"

echo "============================================================"
echo " Deploying ENV=${ENV}  user=${SITE_USER}  branch=${BRANCH}"
echo " app=${APP_DIR}  domain=${DOMAIN}"
echo "============================================================"

# Guard: refuse to run as the wrong user (prevents prod/dev cross-contamination)
if [ "$(id -un)" != "${SITE_USER}" ]; then
  echo "ERROR: run this as '${SITE_USER}' (current: $(id -un))." >&2
  exit 3
fi

echo "== 0. Ensure uv + Python ${PY_VERSION} =="
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv python install "${PY_VERSION}"

echo "== 1. Fetch source (branch ${BRANCH}) =="
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch origin "${BRANCH}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
else
  git clone -b "${BRANCH}" "${REPO}" "${APP_DIR}"
fi

echo "== 2. Backend: venv + dependencies =="
cd "${APP_DIR}/backend"
if [ ! -d venv ]; then
  uv venv --python "${PY_VERSION}" venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
uv pip install -r requirements.txt

echo "== 3. Backend: .env (from ${ENV_TEMPLATE}) =="
if [ ! -f .env ]; then
  cp "${ENV_TEMPLATE}" .env
  echo "  >>> Created backend/.env from ${ENV_TEMPLATE}."
  echo "  >>> EDIT IT NOW: set SECRET_KEY and the DB password, then re-run."
  echo "  >>>   python -c \"import secrets; print(secrets.token_urlsafe(48))\""
  exit 1
fi
mkdir -p uploads exports

echo "== 4. Schema bootstrap / migrations =="
# There is NO base migration that creates the core tables — the base schema is
# produced by Base.metadata.create_all() (see reset_db.py). The 30 alembic
# revisions are incremental only. So on a FRESH db we must create_all + stamp
# head; only an EXISTING db gets `alembic upgrade head`.
if python -c "from app.db.session import engine; from sqlalchemy import inspect; import sys; sys.exit(0 if 'users' in inspect(engine).get_table_names() else 1)" 2>/dev/null; then
  echo "  'users' table present → existing db → alembic upgrade head"
  alembic upgrade head
else
  echo "  fresh database → create_all + alembic stamp head"
  python -c "from app.db.session import engine; from app.models.models import Base; Base.metadata.create_all(bind=engine); print('  created', len(Base.metadata.tables), 'tables')"
  alembic stamp head
fi

echo "== 5. First-time seed (admin, chart of accounts, sequences) =="
if python -c "
from app.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
n = db.execute(text('SELECT COUNT(*) FROM users')).scalar() or 0
db.close()
raise SystemExit(0 if n == 0 else 1)
" 2>/dev/null; then
  echo "  users table empty → seeding"
  python seed.py
else
  echo "  users already present → skipping seed"
fi
deactivate

echo "== 6. Frontend: build (vite --mode ${VITE_MODE}) =="
cd "${APP_DIR}/frontend"
npm ci
npm run build -- --mode "${VITE_MODE}"

echo
echo "== ${ENV} app deploy complete =="
echo "  Next (root):  sudo systemctl restart ${SERVICE}"
echo "  If first install, see DEPLOY.md (systemd unit + nginx vhost + SSL)."
