"""
reset_to_fresh_install.py
=========================
Wipe all data from the wholesale ERP database, keep one (or more) admin users,
and re-seed the minimum bootstrap data (chart of accounts, default warehouse,
company settings, invoice sequences) so the system is immediately usable as
if freshly installed.

DESTRUCTIVE AND IRREVERSIBLE without the backup it creates by default.

The script reads DB credentials from app.core.config.Settings (the same
SQLAlchemy engine the rest of the app uses), so it works on any system that
has a valid .env file in backend/.

Tables NEVER touched:
    alembic_version  - Alembic migration state.
Table handled specially:
    users            - rows deleted EXCEPT those matching --keep-user.

Usage (interactive, recommended for first run on a new system):
    python reset_to_fresh_install.py

Usage (non-interactive, for automation):
    python reset_to_fresh_install.py --keep-user system_administrator --yes
    python reset_to_fresh_install.py --keep-user admin --keep-user owner --yes
    python reset_to_fresh_install.py --no-backup --no-seed --yes    # nuclear
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

from sqlalchemy import text
from app.core.config import settings
from app.db.session import engine, SessionLocal
from app.utils.helpers import get_current_fy


PROTECTED_TABLES = {"alembic_version", "users"}  # users handled separately below
BANNER = "=" * 60


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


def role_str(user) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else (role or "")


# ── Backup ────────────────────────────────────────────────────────────────

def find_mysqldump() -> str:
    """Locate mysqldump executable. Tries PATH first, then common Windows
    MariaDB/MySQL install directories. Returns the resolved path or
    raises RuntimeError with a helpful message."""
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
    # Build command. We pass the password via the MYSQL_PWD env var rather
    # than -p<pwd> on the command line — this avoids:
    #   (a) `-p` with empty value triggering an interactive prompt that hangs
    #       the script (when DATABASE_URL has no password),
    #   (b) the password being visible to `ps` on shared Linux hosts.
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
    # Open in BINARY mode so Windows doesn't translate LF -> CRLF, which
    # would bloat the file and potentially corrupt mysqldump's hex-encoded
    # BLOB literals if they ever span line boundaries.
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
    if size_bytes < 1024:  # < 1 KB is definitely not a real backup
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


def wipe(conn, keep_user_ids: set):
    tables = list_all_base_tables(conn)
    to_clear = [t for t in tables if t not in PROTECTED_TABLES]

    print(f"\n  Disabling foreign key checks...")
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

    print(f"  Clearing {len(to_clear)} data table(s) ...")
    ok, fallback, failed = 0, 0, 0
    for t in to_clear:
        try:
            conn.execute(text(f"TRUNCATE TABLE `{t}`"))
            ok += 1
        except Exception:
            # TRUNCATE can fail when other tables hold FKs into this one even
            # with FK_CHECKS=0 on some MySQL/MariaDB versions. Fall back to
            # DELETE + AUTO_INCREMENT reset.
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

    keep_ids_csv = ",".join(str(i) for i in sorted(keep_user_ids))
    print(f"\n  Deleting users not in ({keep_ids_csv}) ...")
    result = conn.execute(text(f"DELETE FROM users WHERE id NOT IN ({keep_ids_csv})"))
    print(f"    OK: removed {result.rowcount} user(s)")

    # Clean state on kept users: null out warehouse references (warehouses
    # were just truncated), clear refresh token, reset lockout/failed count.
    # warehouse_ids is a TEXT JSON column on the schema; null it too.
    conn.execute(text(
        f"UPDATE users SET warehouse_id = NULL, warehouse_ids = NULL, "
        f"refresh_token = NULL, failed_login_count = 0, is_locked = 0, "
        f"locked_until = NULL, last_login = NULL "
        f"WHERE id IN ({keep_ids_csv})"
    ))

    print(f"\n  Re-enabling foreign key checks...")
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
]

# Invoice sequence document types and prefixes. The financial year is filled
# in at runtime via get_current_fy() so a fresh install on any date gets the
# correct April-start FY (e.g. 2026-04-01 onwards = "2026-27").
INVOICE_SEQUENCE_TYPES = [
    ("b2b_invoice",      "BINV"),
    ("b2c_invoice",      "CINV"),
    ("quotation",        "QT"),
    ("delivery_challan", "DC"),
    ("credit_note",      "CN"),
]


def reseed(conn):
    """Mirrors seed.py except for the default-admin user (which would
    conflict with the --keep-user choice)."""
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

    # Always seed the CURRENT financial year so a fresh install on any
    # date gets matching invoice sequences. NOTE: invoice_sequences has no
    # UNIQUE composite index on (document_type, financial_year), so INSERT
    # IGNORE only dedupes by id. We rely on the upstream TRUNCATE having
    # cleared the table; do not call reseed() without wipe() first.
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


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Wipe all data, keep chosen admin user(s), re-seed bootstrap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--keep-user", action="append", default=[],
                        help="Username to keep (repeatable). If omitted, prompted.")
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
    print("   Wholesale ERP - Reset to Fresh Install")
    print(BANNER)
    print()
    print("  Wipes ALL data; keeps chosen admin user(s) + Alembic state;")
    print("  re-seeds minimum bootstrap so the system is usable on first login.")
    print()

    _, _, host, port_db, dbname = parse_db_url(settings.DATABASE_URL)
    print(f"  Database : {dbname}  @ {host}:{port_db}")

    # Load users
    from app.models.models import User
    db = SessionLocal()
    try:
        all_users = db.query(User).order_by(User.id).all()
    finally:
        db.close()

    if not all_users:
        print("\n  ERROR: No users in database. Nothing to keep. Aborting.")
        sys.exit(1)

    print(f"  Users    : {len(all_users)} currently present")
    for u in all_users:
        print(f"      id={u.id:<3d}  {u.username:<32s}  role={role_str(u)}")
    print()

    # Resolve --keep-user (case-insensitive, deduplicated, empties filtered)
    keep_usernames = [u.strip() for u in args.keep_user if u and u.strip()]
    if not keep_usernames:
        raw = input("  Username(s) to KEEP (comma-separated): ").strip()
        if not raw:
            print("  Aborted: no username provided.")
            sys.exit(1)
        keep_usernames = [u.strip() for u in raw.split(",") if u.strip()]

    if not keep_usernames:
        print("  Aborted: no valid username provided.")
        sys.exit(1)

    # Dedup while preserving order (handles --keep-user foo --keep-user foo)
    _seen_lc = set()
    keep_usernames_dedup = []
    for n in keep_usernames:
        nl = n.lower()
        if nl not in _seen_lc:
            _seen_lc.add(nl)
            keep_usernames_dedup.append(n)
    keep_usernames = keep_usernames_dedup

    keep_users = []
    for name in keep_usernames:
        # Case-insensitive match to align with MariaDB's default collation.
        match = next((u for u in all_users if u.username.lower() == name.lower()), None)
        if not match:
            print(f"  ERROR: User '{name}' not found in database.")
            print(f"         Available: {', '.join(u.username for u in all_users)}")
            print(f"  Aborting.")
            sys.exit(1)
        keep_users.append(match)

    keep_user_ids = {u.id for u in keep_users}
    delete_count = len(all_users) - len(keep_users)

    print()
    print(f"  WILL KEEP   ({len(keep_users)} user(s)):")
    for u in keep_users:
        print(f"      id={u.id}  {u.username}  role={role_str(u)}")
    print(f"  WILL DELETE ({delete_count} other user(s) + all rows in non-protected tables)")
    print()

    # E3: warn if no kept user is admin/super_admin — they may not have
    # permission to "create all data" after login.
    admin_roles = {"admin", "super_admin"}
    kept_roles = {role_str(u).lower() for u in keep_users}
    if not (kept_roles & admin_roles):
        print(f"  WARNING: None of the kept users has role 'admin' or 'super_admin'.")
        print(f"           They may be blocked from many modules after login.")
        print(f"           Consider keeping an admin user as well.")
        print()
        if not args.yes:
            cont = input("  Continue anyway? (yes/no): ").strip().lower()
            if cont not in ("yes", "y"):
                print("  Aborted.")
                sys.exit(0)

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
        print("  This action is IRREVERSIBLE without the backup.")
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
        wipe(conn, keep_user_ids)

    # Re-seed
    if not args.no_seed:
        print()
        print("-- Re-seed bootstrap --")
        with engine.connect() as conn:
            reseed(conn)
    else:
        print("\n  (skipping bootstrap re-seed per --no-seed)")

    # Verify — tolerant of missing tables (older schemas may not have all)
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
    print(f"   2. Log in as one of the kept users:")
    for u in keep_users:
        print(f"        - {u.username}  (role={role_str(u)})")
    print(f"   3. If login fails, reset the password:")
    print(f"        python reset_password.py")
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
