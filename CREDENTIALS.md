# Vignesh GrowthLab Wholesale ERP - System Credentials & Access Guide

## 1. Master Super-Admin Credentials

Both accounts below are configured with full **`super_admin`** privileges (100% access to all 14 modules, Audit Log, Configuration, Opening Balances, and Settings).

| Account | Username | Email | Password | Role | Permissions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Admin** | `admin` | `admin@vigneshgrowthlab.com` | `Admin@1234` | `super_admin` | Full System Access (All Modules) |
| **Backup Superadmin** | `superadmin` | `superadmin@vigneshgrowthlab.com` | `Admin@1234` | `super_admin` | Full System Access (All Modules) |

> **Note:** You can use either `admin` or `superadmin`. Both have identical top-level Super Administrator permissions.

---

## 2. Access URLs

* **Local Machine Access:** [http://localhost:5173](http://localhost:5173)
* **Local Network (LAN / Wi-Fi):** `http://<YOUR-PC-IP>:5173`
* **FastAPI Backend API Docs:** [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)
* **Public Client Demo (Cloudflare):** Run `start-cloudflare-tunnel.bat` to get the instant public HTTPS URL.

---

## 3. Database Credentials (MariaDB 12.3)

* **Host:** `127.0.0.1`
* **Port:** `3307`
* **Database Name:** `wholesale_erp`
* **Username:** `erp_user`
* **Password:** `erp_password`
