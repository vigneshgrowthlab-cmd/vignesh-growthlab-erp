#!/bin/bash
set -e

echo "============================================================"
echo " Wholesale ERP - Linux Production Setup"
echo "============================================================"
echo ""

# ── Variables ─────────────────────────────────────────────────
APP_DIR="/opt/wholesale-erp"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
SERVICE_USER="erp"
DB_NAME="wholesale_erp"
DB_USER="erp_user"
DB_PASS="erp_password"  # Change this!

# ── Step 1: System packages ───────────────────────────────────
echo "── Installing system packages ─────────────────────────────"
sudo apt-get update -qq
sudo apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    nodejs npm \
    mariadb-server mariadb-client \
    redis-server \
    nginx \
    curl wget git \
    build-essential \
    libssl-dev libffi-dev \
    python3-dev \
    libpango-1.0-0 libpangoft2-1.0-0 \
    wkhtmltopdf
echo "[OK] System packages installed"

# ── Step 2: Install PM2 ──────────────────────────────────────
echo "── Installing PM2 ─────────────────────────────────────────"
sudo npm install -g pm2
echo "[OK] PM2 installed"

# ── Step 3: MariaDB setup ─────────────────────────────────────
echo "── Configuring MariaDB ─────────────────────────────────────"
sudo systemctl start mariadb
sudo systemctl enable mariadb

sudo mysql -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
sudo mysql -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"
echo "[OK] MariaDB configured"

# ── Step 4: Redis ─────────────────────────────────────────────
echo "── Configuring Redis ───────────────────────────────────────"
sudo systemctl start redis-server
sudo systemctl enable redis-server
echo "[OK] Redis running"

# ── Step 5: App directory ─────────────────────────────────────
echo "── Setting up application directory ───────────────────────"
sudo mkdir -p $APP_DIR
sudo useradd -r -s /bin/false $SERVICE_USER 2>/dev/null || true
sudo chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR

# Copy application files
sudo cp -r ./backend $BACKEND_DIR
sudo cp -r ./frontend $FRONTEND_DIR
echo "[OK] Application files copied"

# ── Step 6: Backend ───────────────────────────────────────────
echo "── Setting up backend ─────────────────────────────────────"
cd $BACKEND_DIR

sudo -u $SERVICE_USER python3.11 -m venv venv
sudo -u $SERVICE_USER venv/bin/pip install -r requirements.txt --quiet

if [ ! -f ".env" ]; then
    sudo cp .env.example .env
    echo "[!!] Edit $BACKEND_DIR/.env with production values!"
fi

sudo -u $SERVICE_USER venv/bin/alembic upgrade head
sudo -u $SERVICE_USER venv/bin/python seed.py
echo "[OK] Backend configured and database migrated"

# ── Step 7: Frontend build ────────────────────────────────────
echo "── Building frontend ───────────────────────────────────────"
cd $FRONTEND_DIR
sudo -u $SERVICE_USER npm install --silent
echo "VITE_API_URL=https://your-domain.com" | sudo tee .env.production
sudo -u $SERVICE_USER npm run build
echo "[OK] Frontend built"

# ── Step 8: PM2 ecosystem file ────────────────────────────────
echo "── Creating PM2 configuration ─────────────────────────────"
cat > /tmp/ecosystem.config.js << 'EOF'
module.exports = {
  apps: [
    {
      name: "erp-backend",
      cwd: "/opt/wholesale-erp/backend",
      script: "venv/bin/uvicorn",
      args: "app.main:app --host 127.0.0.1 --port 8000 --workers 4",
      interpreter: "none",
      env: { NODE_ENV: "production" },
      error_file: "/var/log/erp/backend-err.log",
      out_file: "/var/log/erp/backend-out.log",
      merge_logs: true,
      restart_delay: 3000,
      max_restarts: 10,
    },
    {
      name: "erp-celery",
      cwd: "/opt/wholesale-erp/backend",
      script: "venv/bin/celery",
      args: "-A app.celery_app worker --loglevel=info --concurrency=2",
      interpreter: "none",
      error_file: "/var/log/erp/celery-err.log",
      out_file: "/var/log/erp/celery-out.log",
    },
  ],
};
EOF
sudo mkdir -p /var/log/erp
sudo chown $SERVICE_USER:$SERVICE_USER /var/log/erp
sudo cp /tmp/ecosystem.config.js $APP_DIR/ecosystem.config.js
echo "[OK] PM2 config created"

# ── Step 9: Nginx config ──────────────────────────────────────
echo "── Configuring Nginx ───────────────────────────────────────"
cat > /tmp/erp-nginx.conf << 'NGINX'
server {
    listen 80;
    server_name your-domain.com;

    # Frontend static files
    root /opt/wholesale-erp/frontend/dist;
    index index.html;

    # React router - serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy to FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        client_max_body_size 20M;
    }

    # File uploads/exports
    location /uploads/ {
        alias /opt/wholesale-erp/backend/uploads/;
        internal;
    }

    gzip on;
    gzip_types text/plain application/json application/javascript text/css;
}
NGINX

sudo cp /tmp/erp-nginx.conf /etc/nginx/sites-available/wholesale-erp
sudo ln -sf /etc/nginx/sites-available/wholesale-erp /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
echo "[OK] Nginx configured"

# ── Step 10: Start with PM2 ──────────────────────────────────
echo "── Starting application with PM2 ───────────────────────────"
cd $APP_DIR
sudo -u $SERVICE_USER pm2 start ecosystem.config.js
sudo -u $SERVICE_USER pm2 save
sudo pm2 startup systemd -u $SERVICE_USER --hp /home/$SERVICE_USER 2>/dev/null || true
echo "[OK] Application started"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Deployment complete!"
echo ""
echo " Application:  http://your-domain.com"
echo " API docs:     http://your-domain.com/api/docs (DEBUG only)"
echo " Login:        admin / Admin@1234"
echo ""
echo " Useful commands:"
echo "   pm2 status            - Check running processes"
echo "   pm2 logs erp-backend  - View backend logs"
echo "   pm2 restart all       - Restart all services"
echo "   sudo systemctl status mariadb"
echo "   sudo systemctl status redis-server"
echo "   sudo systemctl status nginx"
echo ""
echo " IMPORTANT: "
echo "   1. Edit $BACKEND_DIR/.env with production SECRET_KEY and DB credentials"
echo "   2. Set DEBUG=False in .env"
echo "   3. Update server_name in /etc/nginx/sites-available/wholesale-erp"
echo "   4. Set up SSL with: sudo certbot --nginx -d your-domain.com"
echo "============================================================"
