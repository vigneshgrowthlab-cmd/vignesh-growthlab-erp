"""
clear_for_prod.py
=================
Prepare a clean system for loading PRODUCTION data.

Wipes ALL data from the wholesale ERP database (including every user),
re-seeds the minimum bootstrap (chart of accounts, default company settings,
default warehouse, invoice sequences), and creates a single SUPER-ADMIN user
so you can log in, create the real users, and assign roles yourself.

DESTRUCTIVE AND IRREVERSIBLE without the backup it takes by default.

The script reads DB credentials from app.core.config.Settings (the same
SQLAlchemy engine the rest of the app uses), so it works on any system that
has a valid .env file in backend/.

Tables NEVER touched:
    alembic_version  - Alembic migration state.

Default super-admin (change the password after first login):
    username: superadmin
    password: Admin@1234
    role:     super_admin

Usage (interactive, recommended):
    python clear_for_prod.py

Usage (non-interactive, for automation):
    python clear_for_prod.py --yes
    python clear_for_prod.py --yes --no-backup            # nuclear, no backup
    python clear_for_prod.py --yes --username owner --password "S3cret!"
"""
import argparse
import glob
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bcrypt
from sqlalchemy import text
from app.core.config import settings
from app.db.session import engine, SessionLocal
from app.utils.helpers import get_current_fy


PROTECTED_TABLES = {"alembic_version"}
BANNER = "=" * 60

DEFAULT_SUPER_USERNAME = "superadmin"
DEFAULT_SUPER_PASSWORD = "Admin@1234"
DEFAULT_SUPER_EMAIL = "superadmin@company.com"
DEFAULT_SUPER_FULLNAME = "Super Administrator"


def parse_db_url(url: str):
    """Returns (user, password, host, port, dbname)."""
    parsed = urlparse(url)
    return (
        parsed.username or "root",
        parsed.password or "",
        parsed.hostname or "localhost",
        str(parsed.port or 3306),
        parsed.path.lstrip("/").split("?")[0],
    )


def is_port_in_use(port: int) -> bool:
    if not (0 < port < 65536):
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        finally:
            s.close()
    except Exception:
        return False


# ── Backup ────────────────────────────────────────────────────────────────

def find_mysqldump() -> str:
    """Locate mysqldump executable. Tries PATH first, then common Windows
    MariaDB/MySQL install directories."""
    found = shutil.which("mysqldump") or shutil.which("mysqldump.exe")
    if found:
        return found
    if sys.platform == "win32":
        patterns = [
            r"C:\Program Files\MariaDB *\bin\mysqldump.exe",
            r"C:\Program Files (x86)\MariaDB *\bin\mysqldump.exe",
            r"C:\Program Files\MySQL\MySQL Server *\bin\mysqldump.exe",
            r"C:\Program Files (x86)\MySQL\MySQL Server *\bin\mysqldump.exe",
            r"C:\xampp\mysql\bin\mysqldump.exe",
            r"C:\wamp64\bin\mariadb\mariadb*\bin\mysqldump.exe",
            r"C:\wamp64\bin\mysql\mysql*\bin\mysqldump.exe",
        ]
        for pat in patterns:
            hits = glob.glob(pat)
            if hits:
                return hits[0]
    raise RuntimeError(
        "Could not locate 'mysqldump'. Install MariaDB/MySQL client tools,\n"
        "  or add the existing bin directory to PATH, then re-run.\n"
        "  (You can also pass --no-backup to skip, NOT recommended.)"
    )


def take_backup(backup_dir: Path) -> Path:
    user, pwd, host, port, db = parse_db_url(settings.DATABASE_URL)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = backup_dir / f"{db}_{ts}.sql"
    mysqldump = find_mysqldump()
    print(f"  Using mysqldump: {mysqldump}")
    print(f"  Creating backup: {out_path.name}")
    cmd = [
        mysqldump,
        f"-h{host}", f"-P{port}", f"-u{user}",
        "--single-transaction", "--routines", "--triggers", "--events",
        db,
    ]
    env = os.environ.copy()
    if pwd:
        env["MYSQL_PWD"] = pwd
    else:
        env.pop("MYSQL_PWD", None)
    with out_path.open("wb") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env)
    if result.returncode != 0:
        try:
            out_path.unlink()
        except Exception:
            pass
        err = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"mysqldump failed (exit {result.returncode}): {err}")
    size_bytes = out_path.stat().st_size
    if size_bytes < 1024:
        try:
            head = out_path.read_bytes()[:500].decode("utf-8", errors="replace")
        except Exception:
            head = "(could not read backup file)"
        try:
            out_path.unlink()
        except Exception:
            pass
        raise RuntimeError(
            f"mysqldump produced suspiciously small output ({size_bytes} bytes). "
            f"Content head:\n{head}"
        )
    print(f"  OK: {size_bytes / 1024:,.1f} KB written")
    return out_path


# ── Wipe ──────────────────────────────────────────────────────────────────

def list_all_base_tables(conn):
    rows = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)).fetchall()
    return [r[0] for r in rows]


def wipe(conn):
    """Truncate every base table except alembic_version (users included)."""
    tables = list_all_base_tables(conn)
    to_clear = [t for t in tables if t not in PROTECTED_TABLES]

    print("\n  Disabling foreign key checks...")
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

    print(f"  Clearing {len(to_clear)} data table(s) ...")
    ok, fallback, failed = 0, 0, 0
    for t in to_clear:
        try:
            conn.execute(text(f"TRUNCATE TABLE `{t}`"))
            ok += 1
        except Exception:
            try:
                conn.execute(text(f"DELETE FROM `{t}`"))
                try:
                    conn.execute(text(f"ALTER TABLE `{t}` AUTO_INCREMENT = 1"))
                except Exception:
                    pass
                fallback += 1
            except Exception as e2:
                failed += 1
                print(f"    FAIL {t}: {e2}")
    print(f"    OK truncated={ok}  fallback(DELETE)={fallback}  failed={failed}")

    print("  Re-enabling foreign key checks...")
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    conn.commit()


# ── Re-seed bootstrap ─────────────────────────────────────────────────────

ACCOUNTS = [
    ("CASH",          "Cash in Hand",                "asset"),
    ("BANK",          "Bank Account",                "asset"),
    ("STOCK",         "Stock / Inventory",           "asset"),
    ("DEBTORS",       "Accounts Receivable",         "asset"),
    ("GST_ITC",       "GST Input Tax Credit",        "asset"),
    ("CREDITORS",     "Accounts Payable",            "liability"),
    ("GST_PAY",       "GST Payable",                 "liability"),
    ("SALES",         "Sales Revenue",               "income"),
    ("PURCHASES",     "Purchase Cost of Goods",      "expense"),
    ("EXPENSES",      "General Expenses",            "expense"),
    ("LOSS_WRITEOFF", "Stock Writeoff Loss",         "expense"),
    ("TDS_PAYABLE",   "TDS Payable",                 "liability"),
    ("ADVANCE_PAY",   "Advance Payments",            "asset"),
    ("ADVANCE_REC",   "Advance Receipts",            "liability"),
    ("DISCOUNT",      "Discount Allowed",            "expense"),
    ("INTEREST",      "Interest Income",             "income"),
    ("BANK_CHARGES",  "Bank Charges",                "expense"),
    ("OPENING_STOCK", "Opening Stock",               "asset"),
    ("ROUND_OFF",     "Round Off",                   "income"),
]

INVOICE_SEQUENCE_TYPES = [
    ("b2b_invoice",      "BINV"),
    ("b2c_invoice",      "CINV"),
    ("quotation",        "QT"),
    ("delivery_challan", "DC"),
    ("credit_note",      "CN"),
]


def reseed(conn):
    print("\n  Chart of accounts:")
    for code, name, atype in ACCOUNTS:
        conn.execute(text(
            "INSERT INTO accounts (account_code, name, account_type, is_system, "
            "is_active, opening_balance, current_balance) "
            "VALUES (:code, :name, :type, 1, 1, 0, 0) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name), account_type=VALUES(account_type)"
        ), {"code": code, "name": name, "type": atype})
    print(f"    OK: {len(ACCOUNTS)} accounts")

    print("  Company settings:")
    exists = conn.execute(text("SELECT id FROM company_settings LIMIT 1")).fetchone()
    if not exists:
        conn.execute(text(
            "INSERT INTO company_settings "
            "(company_name, gstin, state, state_code, address_line1, city, pincode, financial_year_start) "
            "VALUES ('My Wholesale Company', '29AAAAA0000A1Z5', 'Karnataka', 29, "
            "'123 Main Street', 'Bangalore', '560001', 4)"
        ))
        print("    OK: default created (edit via Settings page after login)")
    else:
        print("    OK: already exists")

    print("  Default warehouse:")
    exists = conn.execute(text("SELECT id FROM warehouses LIMIT 1")).fetchone()
    if not exists:
        conn.execute(text(
            "INSERT INTO warehouses (name, code, is_active, is_default) "
            "VALUES ('Main Warehouse', 'MAIN', 1, 1)"
        ))
        print("    OK: 'Main Warehouse' created")
    else:
        print("    OK: already exists")

    fy = get_current_fy()
    print(f"  Invoice sequences (FY {fy}):")
    for doc_type, prefix in INVOICE_SEQUENCE_TYPES:
        conn.execute(text(
            "INSERT IGNORE INTO invoice_sequences "
            "(document_type, prefix, financial_year, last_number) "
            "VALUES (:dt, :pfx, :fy, 0)"
        ), {"dt": doc_type, "pfx": prefix, "fy": fy})
    print(f"    OK: {len(INVOICE_SEQUENCE_TYPES)} sequence(s)")

    conn.commit()


def create_super_admin(conn, username, password, email, full_name):
    print("\n  Super-admin user:")
    pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn.execute(text(
        "INSERT INTO users (username, email, full_name, hashed_password, role, is_active) "
        "VALUES (:u, :e, :fn, :pw, 'super_admin', 1)"
    ), {"u": username, "e": email, "fn": full_name, "pw": pw})
    conn.commit()
    print(f"    OK: '{username}' created (role=super_admin)")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Wipe ALL data, re-seed bootstrap, create one super-admin "
                    "(prepare for loading production data).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--username", default=DEFAULT_SUPER_USERNAME,
                        help=f"Super-admin username (default '{DEFAULT_SUPER_USERNAME}').")
    parser.add_argument("--password", default=DEFAULT_SUPER_PASSWORD,
                        help="Super-admin password (default 'Admin@1234'). CHANGE after login.")
    parser.add_argument("--email", default=DEFAULT_SUPER_EMAIL,
                        help=f"Super-admin email (default '{DEFAULT_SUPER_EMAIL}').")
    parser.add_argument("--full-name", default=DEFAULT_SUPER_FULLNAME,
                        help="Super-admin display name.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip mysqldump backup (NOT recommended).")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip re-seeding chart of accounts, warehouse, etc.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompts (for automation).")
    parser.add_argument("--port", type=int, default=8000,
                        help="Backend port to warn about if in use (default 8000).")
    args = parser.parse_args()

    print()
    print(BANNER)
    print("   Wholesale ERP - Clear For Production")
    print(BANNER)
    print()
    print("  Wipes ALL data (every user included) + Alembic state is kept;")
    print("  re-seeds bootstrap and creates ONE super-admin so you can log in")
    print("  and load your production data / create real users.")
    print()

    _, _, host, port_db, dbname = parse_db_url(settings.DATABASE_URL)
    print(f"  Database    : {dbname}  @ {host}:{port_db}")
    print(f"  Super-admin : {args.username}  (role=super_admin)")
    print()

    # Warn if backend appears to be running
    if is_port_in_use(args.port):
        print(f"  WARNING: Port {args.port} is in use (backend likely running).")
        print(f"           Stop uvicorn before continuing, otherwise the wipe may")
        print(f"           race with in-flight requests.")
        print()
        if not args.yes:
            cont = input("  Continue anyway? (yes/no): ").strip().lower()
            if cont not in ("yes", "y"):
                print("  Aborted.")
                sys.exit(0)

    # Final confirmation
    if not args.yes:
        print("  This DELETES ALL DATA AND ALL USERS. Irreversible without the backup.")
        confirm = input('  Type DELETE in capital letters to confirm: ').strip()
        if confirm != "DELETE":
            print("  Aborted.")
            sys.exit(0)

    # Backup
    if not args.no_backup:
        print()
        print("-- Backup --")
        try:
            take_backup(Path(__file__).parent / "backups")
        except Exception as e:
            print(f"  ERROR: {e}")
            print("  Aborting (use --no-backup to skip, NOT recommended).")
            sys.exit(1)
    else:
        print("\n  (skipping backup per --no-backup)")

    # Wipe
    print()
    print("-- Wipe --")
    with engine.connect() as conn:
        wipe(conn)

    # Super-admin FIRST — created right after the wipe so that even if the
    # bootstrap re-seed below fails, the system still has one usable login
    # (and is never left with zero users = locked out). It has no warehouse
    # dependency, so ordering it before reseed is safe.
    print()
    print("-- Super-admin --")
    with engine.connect() as conn:
        create_super_admin(conn, args.username, args.password, args.email, args.full_name)

    # Re-seed bootstrap
    if not args.no_seed:
        print()
        print("-- Re-seed bootstrap --")
        with engine.connect() as conn:
            reseed(conn)
    else:
        print("\n  (skipping bootstrap re-seed per --no-seed)")

    # Verify
    print()
    print("-- Verify --")
    check_tables = [
        "users", "accounts", "warehouses", "company_settings",
        "invoice_sequences", "products", "purchases", "invoices",
        "journal_entries", "stock_entries",
    ]
    with engine.connect() as conn:
        for t in check_tables:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
                print(f"  {t:<20s}: {n}")
            except Exception as e:
                print(f"  {t:<20s}: (skipped: {e.__class__.__name__})")

    print()
    print(BANNER)
    print("   Done. Next steps:")
    print(BANNER)
    print(f"   1. Restart backend:  uvicorn app.main:app --reload --port 8000")
    print(f"   2. Log in:           {args.username} / {args.password}")
    print(f"   3. CHANGE the super-admin password immediately.")
    print(f"   4. Create your real users and load production data.")
    print(BANNER)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Aborted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n  FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
