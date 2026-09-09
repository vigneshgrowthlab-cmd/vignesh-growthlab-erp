# Wholesale ERP — Deployment (CloudPanel / Debian 13)

Two environments on one CloudPanel server (`37.221.199.121`), Percona MySQL 8.4,
nginx reverse proxy, Let's Encrypt SSL. Each is an isolated CloudPanel site.

| | **PROD** | **DEV** |
|---|---|---|
| Domain | `erp.globaltradeforce.com` | `dev.erp.globaltradeforce.com` |
| Git branch | `main` | `dev` |
| Site user | `gtferp` | `gtferp-dev` |
| App dir | `/home/gtferp/GTF` | `/home/gtferp-dev/GTF` |
| Backend port | `127.0.0.1:8000` | `127.0.0.1:8001` |
| systemd service | `erp-backend` | `erp-backend-dev` |
| Database | `wholesaleerp` / `erpuser` | `wholesaleerpdev` / `erpuserdev` |
| DEBUG / docs | `false` / off | `true` / `/api/docs` on |
| env template | `backend/.env.production.template` | `backend/.env.dev.template` |
| nginx ref | `deploy/nginx-vhost.conf` | `deploy/nginx-vhost-dev.conf` |
| service unit | `deploy/erp-backend.service` | `deploy/erp-backend-dev.service` |

```
                          ┌─ erp.globaltradeforce.com ──── nginx ─┬─ / → /home/gtferp/GTF/frontend/dist
                          │                                       └─ /api,/uploads → 127.0.0.1:8000  (erp-backend)
Browser ──https──▶ CloudPanel
                          │  dev.erp.globaltradeforce.com ─ nginx ─┬─ / → /home/gtferp-dev/GTF/frontend/dist
                          └                                        └─ /api,/uploads → 127.0.0.1:8001  (erp-backend-dev)
                                              │
                                     Percona MySQL 8.4  ── wholesaleerp + wholesaleerpdev
```

**Workflow:** work on `dev` → deploys to DEV. Merge `dev`→`main` → deploys to PROD.

---

## Step 0 — System prerequisites  ✅ (done, server-wide, shared by both)
`deploy/01-server-prep.sh` already run as root.

---

## The rest of the steps are per-environment.
Do **DEV first** (safe to break), then repeat for **PROD**. Below, `<ENV>` is `dev`
or `prod`, and `<USER>` is `gtferp-dev` or `gtferp` respectively.

### Step 1 — DNS
Point an **A record** to `37.221.199.121`:
- PROD: `erp.globaltradeforce.com`
- DEV:  `dev.erp.globaltradeforce.com`
```powershell
nslookup dev.erp.globaltradeforce.com
```

### Step 2 — Create the CloudPanel site
CloudPanel → **Sites → Add Site → Create a Reverse Proxy**
- **Domain:** the env's domain
- **Reverse Proxy URL:** `http://127.0.0.1:8000` (prod) or `http://127.0.0.1:8001` (dev)
- **Site User:** `gtferp` (prod) or `gtferp-dev` (dev)  ← must match exactly

### Step 3 — Create the database
CloudPanel → **Databases → Add Database**
- PROD: db `wholesaleerp`, user `erpuser`
- DEV:  db `wholesaleerpdev`, user `erpuserdev`
- Strong password (entered into `backend/.env` on the server in Step 4).

### Step 4 — Deploy the app  (as the site user)
```powershell
cd C:\Sindhu\D\WholesaleERPModule\wholesale-erp-final-build
# DEV:
scp deploy/02-app-deploy.sh gtferp-dev@37.221.199.121:~/
ssh gtferp-dev@37.221.199.121 "bash ~/02-app-deploy.sh dev"
# PROD:
scp deploy/02-app-deploy.sh gtferp@37.221.199.121:~/
ssh gtferp@37.221.199.121 "bash ~/02-app-deploy.sh prod"
```
First run clones + builds the venv, then **stops** to have you fill `backend/.env`:
```bash
cd /home/<USER>/GTF/backend
python -c "import secrets; print(secrets.token_urlsafe(48))"   # copy
nano .env        # set SECRET_KEY=<that> and the DB password in DATABASE_URL
```
Re-run the same command — it migrates, seeds (admin/Admin@1234), and builds the frontend.

### Step 5 — Install the backend service  (as root)
```powershell
# DEV
scp deploy/erp-backend-dev.service root@37.221.199.121:~/
# PROD
scp deploy/erp-backend.service root@37.221.199.121:~/
```
```bash
ssh root@37.221.199.121
# DEV
cp ~/erp-backend-dev.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now erp-backend-dev
systemctl status erp-backend-dev && curl -s http://127.0.0.1:8001/health
# PROD
cp ~/erp-backend.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now erp-backend
systemctl status erp-backend && curl -s http://127.0.0.1:8000/health
```

### Step 6 — nginx + SSL  (CloudPanel UI, per site)
- **SSL:** site → **SSL/TLS → New Let's Encrypt Certificate** (DNS must resolve first).
- **Vhost:** site → **Vhost** editor → replace the default `location /` block with the
  `root` + four `location` blocks from the env's nginx ref file
  (`deploy/nginx-vhost.conf` for prod, `deploy/nginx-vhost-dev.conf` for dev),
  leaving CloudPanel's listen/server_name/ssl_* lines intact. Save → auto-reload.

### Step 7 — Smoke test
Open the env's URL, log in `admin`/`Admin@1234` → **change the password**, create a
test invoice → download its PDF (WeasyPrint), confirm a product image loads (`/uploads/`).

---

## Updating later
```powershell
# push work to dev branch → deploy DEV
git push origin dev
ssh gtferp-dev@37.221.199.121 "bash ~/02-app-deploy.sh dev"
ssh root@37.221.199.121 "systemctl restart erp-backend-dev"

# promote: merge dev → main, push → deploy PROD
git checkout main; git merge dev; git push origin main
ssh gtferp@37.221.199.121 "bash ~/02-app-deploy.sh prod"
ssh root@37.221.199.121 "systemctl restart erp-backend"
```

## Troubleshooting
| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status erp-backend[-dev]`, `journalctl -u erp-backend[-dev] -e` |
| Wrong port | dev=8001, prod=8000 — vhost `proxy_pass` must match the service |
| DB connection error | password in `DATABASE_URL`, the env's DB + user exist, `@localhost` grant |
| GROUP BY / error 1055 | handled by the `sql_mode` strip in `session.py` (MySQL 8.4) |
| PDF download 500 | WeasyPrint libs (`ldconfig -p \| grep pango`) |
| Blank page / 404 on refresh | nginx `root` path + SPA `try_files` fallback |
| Images 404 | `/uploads/` proxy block present, pointing at the right port |
