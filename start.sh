#!/usr/bin/env bash
set -e

echo "=== Starting Vignesh GrowthLab Wholesale ERP ==="

cd /app/backend

# Check if an external database URL or host is configured
IS_EXTERNAL_DB=0
if [ -n "$DATABASE_URL" ] || [ -n "$MYSQL_URL" ] || [ -n "$MYSQL_PRIVATE_URL" ] || [ -n "$MYSQL_PUBLIC_URL" ] || [ -n "$MYSQLHOST" ] || [ -n "$MYSQL_HOST" ]; then
    IS_EXTERNAL_DB=1
fi

if [ "$IS_EXTERNAL_DB" -eq 0 ]; then
    echo "[DB] No external MySQL configured. Starting embedded MariaDB on localhost..."
    service mariadb start || /etc/init.d/mariadb start || true
    sleep 2
    mariadb -u root -e "
        CREATE DATABASE IF NOT EXISTS wholesale_erp;
        CREATE USER IF NOT EXISTS 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
        CREATE USER IF NOT EXISTS 'erp_user'@'127.0.0.1' IDENTIFIED BY 'erp_password';
        GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
        GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'127.0.0.1';
        FLUSH PRIVILEGES;
    " || mysql -u root -e "
        CREATE DATABASE IF NOT EXISTS wholesale_erp;
        CREATE USER IF NOT EXISTS 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
        CREATE USER IF NOT EXISTS 'erp_user'@'127.0.0.1' IDENTIFIED BY 'erp_password';
        GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
        GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'127.0.0.1';
        FLUSH PRIVILEGES;
    " || true
    echo "[DB] Embedded MariaDB ready!"
else
    echo "[DB] Using external MySQL database from Railway environment."
fi

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

# Detect port assigned by Railway or default to 8000
PORT="${PORT:-8000}"
echo "Starting FastAPI server on port $PORT..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"