import re
from datetime import date, datetime
from decimal import Decimal
from typing import Tuple, Union
from app.core.config import settings


def get_financial_year(d: date = None) -> str:
    """Returns financial year string like '2025-26' for a given date."""
    if d is None:
        d = date.today()
    fy_start_month = settings.FINANCIAL_YEAR_START_MONTH
    if d.month >= fy_start_month:
        return f"{d.year}-{str(d.year + 1)[2:]}"
    else:
        return f"{d.year - 1}-{str(d.year)[2:]}"


def get_fy_date_range(fy: str) -> Tuple[date, date]:
    """Returns (start_date, end_date) for a financial year string like '2025-26'."""
    start_year = int(fy.split("-")[0])
    fy_start = settings.FINANCIAL_YEAR_START_MONTH
    start = date(start_year, fy_start, 1)
    end_year = start_year + 1
    end_month = fy_start - 1 if fy_start > 1 else 12
    import calendar
    end_day = calendar.monthrange(end_year, end_month)[1]
    end = date(end_year, end_month, end_day)
    return start, end


def get_current_fy() -> str:
    return get_financial_year(date.today())


def determine_gst_type(customer_state_code: int, company_state_code: int) -> str:
    """Returns 'cgst_sgst' for same state, 'igst' for different state."""
    if customer_state_code == company_state_code:
        return "cgst_sgst"
    return "igst"


# GST state-code master (mirrors the list served by /settings/states). Used to
# resolve a free-text state NAME (e.g. a warehouse's `state`) to its numeric
# state code so the CGST/SGST-vs-IGST decision can compare CODES rather than
# fragile name strings ("Tamilnadu" vs "Tamil Nadu").
_STATE_NAME_TO_CODE = {
    "jammukashmir": 1, "himachalpradesh": 2, "punjab": 3, "chandigarh": 4,
    "uttarakhand": 5, "haryana": 6, "delhi": 7, "rajasthan": 8,
    "uttarpradesh": 9, "bihar": 10, "sikkim": 11, "arunachalpradesh": 12,
    "nagaland": 13, "manipur": 14, "mizoram": 15, "tripura": 16,
    "meghalaya": 17, "assam": 18, "westbengal": 19, "jharkhand": 20,
    "odisha": 21, "orissa": 21, "chhattisgarh": 22, "madhyapradesh": 23,
    "gujarat": 24, "dadranagarhavelidamandiu": 26, "maharashtra": 27,
    "andhrapradeshnew": 28, "karnataka": 29, "goa": 30, "lakshadweep": 31,
    "kerala": 32, "tamilnadu": 33, "puducherry": 34, "pondicherry": 34,
    "andamannicobarislands": 35, "telangana": 36, "andhrapradeshresidual": 37,
    "andhrapradesh": 37, "ladakh": 38,
}


def get_client_ip(request) -> str:
    """Best-effort real client IP from a FastAPI/Starlette Request.

    Honours X-Forwarded-For (first hop) when behind a proxy, else falls back
    to the direct peer. Returns 'unknown' if neither is available.
    """
    try:
        xff = request.headers.get("x-forwarded-for") if request else None
        if xff:
            return xff.split(",")[0].strip()
        if request and request.client:
            return request.client.host
    except Exception:
        pass
    return "unknown"


def resolve_state_code(name) -> "int | None":
    """Resolve a state name to its GST state code, or None if unknown.

    Normalises by lowercasing and stripping all non-alphanumeric characters so
    minor spelling/spacing differences still match.
    """
    if not name:
        return None
    key = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return _STATE_NAME_TO_CODE.get(key)


# Reverse map for display (code -> proper state name), mirrors /settings/states.
_STATE_CODE_TO_NAME = {
    1: "Jammu & Kashmir", 2: "Himachal Pradesh", 3: "Punjab", 4: "Chandigarh",
    5: "Uttarakhand", 6: "Haryana", 7: "Delhi", 8: "Rajasthan",
    9: "Uttar Pradesh", 10: "Bihar", 11: "Sikkim", 12: "Arunachal Pradesh",
    13: "Nagaland", 14: "Manipur", 15: "Mizoram", 16: "Tripura",
    17: "Meghalaya", 18: "Assam", 19: "West Bengal", 20: "Jharkhand",
    21: "Odisha", 22: "Chhattisgarh", 23: "Madhya Pradesh", 24: "Gujarat",
    26: "Dadra and Nagar Haveli and Daman and Diu", 27: "Maharashtra",
    28: "Andhra Pradesh (New)", 29: "Karnataka", 30: "Goa", 31: "Lakshadweep",
    32: "Kerala", 33: "Tamil Nadu", 34: "Puducherry",
    35: "Andaman & Nicobar Islands", 36: "Telangana",
    37: "Andhra Pradesh (Residual)", 38: "Ladakh",
}


def state_name_for_code(code) -> "str | None":
    """Resolve a GST state code to its display name, or None if unknown."""
    if code is None:
        return None
    try:
        return _STATE_CODE_TO_NAME.get(int(code))
    except (ValueError, TypeError):
        return None


def derive_state_code(gstin=None, state=None, explicit=None) -> "int | None":
    """Best-available GST state code: explicit value > GSTIN prefix > state name.

    The first two digits of a GSTIN are the state code, which is more
    authoritative than a free-text state name; the name is the fallback for
    unregistered parties.
    """
    if explicit is not None:
        return explicit
    if gstin and len(gstin) >= 2 and str(gstin)[:2].isdigit():
        code = int(str(gstin)[:2])
        if code in _STATE_CODE_TO_NAME:
            return code
    return resolve_state_code(state)


def calculate_gst(taxable_amount: float, gst_percent: float, gst_type: str) -> dict:
    """Calculate GST amounts given taxable amount, rate, and type."""
    total_gst = round(taxable_amount * gst_percent / 100, 2)
    if gst_type == "cgst_sgst":
        half = round(total_gst / 2, 2)
        return {"cgst": half, "sgst": total_gst - half, "igst": 0.0}
    return {"cgst": 0.0, "sgst": 0.0, "igst": total_gst}


def next_sequence_number(db, key: str, prefix: str, fy: str,
                          seed_from=None) -> int:
    """Atomically increment and return the next sequence number for (key, fy).

    Uses invoice_sequences as a generic counter table with row-level locking
    (SELECT ... FOR UPDATE) so concurrent inserts don't collide. Callers
    format the returned int into their own numbering scheme.

    Replaces the unsafe `db.query(Model).count() + 1` pattern used in journal
    entries, customer payments, stock adjustments, etc.

    Optional `seed_from(db, fy) -> int` callback: when the counter row for
    (key, fy) doesn't exist yet, the helper calls this to compute the starting
    value (max already-issued number) so the new counter doesn't collide with
    data written under the old `count() + 1` scheme. Returns 0 + 1 = 1 if
    no callback is provided.
    """
    from sqlalchemy import text
    row = db.execute(text(
        "SELECT id, last_number FROM invoice_sequences "
        "WHERE document_type = :key AND financial_year = :fy "
        "FOR UPDATE"
    ), {"key": key, "fy": fy}).fetchone()
    if row:
        current = int(row[1] or 0)
        # Sync counter to actual committed state when seed_from is provided.
        # This handles both forward-drift (old count()+1 code wrote records
        # past the counter) and backward-drift (a rolled-back transaction left
        # the counter ahead of committed data due to an intermediate db.commit()
        # from a helper like get_or_create_account). The FOR UPDATE lock on this
        # row serialises access, so actual_max is the true committed floor.
        if seed_from is not None:
            try:
                actual_max = int(seed_from(db, fy) or 0)
                current = actual_max
            except Exception:
                pass
        next_num = current + 1
        db.execute(text(
            "UPDATE invoice_sequences SET last_number = :n WHERE id = :id"
        ), {"n": next_num, "id": row[0]})
    else:
        start = 0
        if seed_from is not None:
            try:
                start = int(seed_from(db, fy) or 0)
            except Exception:
                start = 0
        next_num = start + 1
        db.execute(text(
            "INSERT INTO invoice_sequences "
            "(document_type, prefix, financial_year, last_number) "
            "VALUES (:key, :prefix, :fy, :n)"
        ), {"key": key, "prefix": prefix, "fy": fy, "n": next_num})
    return next_num


def _seed_from_suffix(db, fy: str, table: str, column: str) -> int:
    """Return max numeric suffix of values in `column` of `table` for the
    given financial year. Used to seed atomic counters that need to coexist
    with legacy data produced by the older `count() + 1` numbering pattern.
    """
    from sqlalchemy import text
    rows = db.execute(text(
        f"SELECT `{column}` FROM `{table}` "
        f"WHERE financial_year = :fy AND `{column}` IS NOT NULL"
    ), {"fy": fy}).fetchall()
    max_num = 0
    for (val,) in rows:
        if not val:
            continue
        try:
            n = int(str(val).rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            continue
        if n > max_num:
            max_num = n
    return max_num


def _seed_from_number_fy(db, fy: str, table: str, column: str, doc_prefix: str) -> int:
    """Return max numeric suffix of values in `column` matching
    {doc_prefix}-{fy_without_dash}-NNNN.

    Like `_seed_from_suffix` but for tables that embed the financial year in the
    number itself rather than carrying a `financial_year` column (e.g.
    stock_adjustments). Lets an atomic counter coexist with legacy data written
    by the old `count() + 1` pattern without colliding on the UNIQUE number.
    """
    from sqlalchemy import text
    fy_key = fy.replace("-", "")
    rows = db.execute(text(
        f"SELECT `{column}` FROM `{table}` WHERE `{column}` LIKE :pat"
    ), {"pat": f"{doc_prefix}-{fy_key}-%"}).fetchall()
    max_num = 0
    for (val,) in rows:
        if not val:
            continue
        try:
            n = int(str(val).rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            continue
        if n > max_num:
            max_num = n
    return max_num


def fmt_inr(amount: Union[Decimal, float, int, None]) -> str:
    """Format a number with Indian thousands grouping: 12,34,567.89.

    Last group is 3 digits, all others are 2 digits. Uses 2 decimal places.
    Returns "0.00" for None or invalid input.
    """
    if amount is None:
        return "0.00"
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return "0.00"
    neg = n < 0
    n = abs(n)
    s = f"{n:.2f}"
    intpart, dec = s.split(".")
    if len(intpart) <= 3:
        return f"{'-' if neg else ''}{intpart}.{dec}"
    last3 = intpart[-3:]
    rest = intpart[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    formatted = f"{','.join(groups)},{last3}.{dec}"
    return f"{'-' if neg else ''}{formatted}"


def paginate(query, page: int = 1, page_size: int = 20):
    """Apply pagination to a SQLAlchemy query."""
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def format_document_number(db, doc_type: str, fy: str, seq: int,
                           default_prefix: str, default_pad: int = 4) -> str:
    """Build an internal document number from the effective-dated
    document_number_format master, falling back to the in-code prefix/padding
    when the table is empty/absent.

    Pattern: ``{prefix}{sep}{FY-without-dash}{sep}{seq:0Nd}`` — byte-identical to
    the previous hardcoded f-strings when the master mirrors the defaults.
    """
    prefix, pad, sep = default_prefix, default_pad, "-"
    try:
        from sqlalchemy import text
        # `separator` is a MariaDB reserved word -> backtick-quote identifiers.
        row = db.execute(text(
            "SELECT `prefix`, `padding`, `separator` FROM `document_number_format` "
            "WHERE `doc_type` = :dt AND `status` = 'active' LIMIT 1"
        ), {"dt": doc_type}).fetchone()
        if row:
            prefix = row[0] or default_prefix
            pad = int(row[1]) if row[1] is not None else default_pad
            sep = row[2] or "-"
    except Exception:
        prefix, pad, sep = default_prefix, default_pad, "-"
    fy_key = (fy or "").replace("-", "")
    return f"{prefix}{sep}{fy_key}{sep}{seq:0{int(pad)}d}"


# ── Account Helper ────────────────────────────────────────────

_ACCOUNT_TYPE_MAP = {
    "STOCK": ("asset",     "Stock / Inventory"),
    "CASH":  ("asset",     "Cash in Hand"),
    "BANK":  ("asset",     "Bank Account"),
    "DEBTORS":      ("asset",     "Accounts Receivable"),
    "GST_ITC":      ("asset",     "GST Input Tax Credit"),
    "ADVANCE_PAY":  ("asset",     "Advance Payments"),
    "ADVANCE_REC":  ("liability", "Advance Receipts"),
    "CREDITORS":    ("liability", "Accounts Payable"),
    "GST_PAY":      ("liability", "GST Payable"),
    "TDS_PAYABLE":  ("liability", "TDS Payable"),
    "SALES":        ("income",    "Sales Revenue"),
    "PURCHASES":    ("expense",   "Purchase Cost"),
    "EXPENSES":     ("expense",   "General Expenses"),
    "LOSS_WRITEOFF":("expense",   "Stock Writeoff Loss"),
    "STOCK_ADJ":    ("expense",   "Stock Inventory Adjustment"),
    "DISCOUNT":     ("expense",   "Discount Allowed"),
    "BANK_CHARGES": ("expense",   "Bank Charges"),
    "INTEREST":     ("income",    "Interest Income"),
    "ROUND_OFF":    ("income",    "Round Off"),
}

def get_or_create_account(db, code: str):
    """Get account by code. Auto-fixes schema and creates account if missing."""
    from sqlalchemy import text

    # Fix accounts table schema using raw SQL (safe regardless of column state)
    _acct_cols = [
        ("name",            "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("account_type",    "VARCHAR(30) NOT NULL DEFAULT 'asset'"),
        ("parent_id",       "INT"),
        ("is_system",       "BOOLEAN DEFAULT FALSE"),
        ("is_active",       "BOOLEAN DEFAULT TRUE"),
        ("opening_balance", "DECIMAL(14,2) DEFAULT 0"),
        ("current_balance", "DECIMAL(14,2) DEFAULT 0"),
        ("created_by",      "INT"),
        ("updated_by",      "INT"),
        ("updated_at",      "DATETIME"),
    ]
    for col, defn in _acct_cols:
        try:
            db.execute(text(f"ALTER TABLE accounts ADD COLUMN `{col}` {defn}"))
            db.commit()
        except Exception:
            pass  # already exists

    # Resolve (account_type, default name) from the effective-dated
    # chart_of_account_map; fall back to the in-code map (and finally to
    # ("expense", code)) so an unseeded/absent table behaves as before.
    atype = name = None
    try:
        _today = date.today().isoformat()
        _r = db.execute(text(
            "SELECT account_type, default_name FROM chart_of_account_map "
            "WHERE code = :c AND status IN ('active','superseded','expired') "
            "AND effective_from <= :d AND (effective_to IS NULL OR effective_to >= :d) "
            "ORDER BY effective_from DESC LIMIT 1"
        ), {"c": code, "d": _today}).fetchone()
        if _r:
            atype, name = _r[0], _r[1]
    except Exception:
        atype = name = None
    if atype is None:
        atype, name = _ACCOUNT_TYPE_MAP.get(code, ("expense", code))

    # Check existence via raw SQL
    try:
        row = db.execute(
            text("SELECT id FROM accounts WHERE account_code = :c LIMIT 1"),
            {"c": code}
        ).fetchone()
    except Exception:
        row = None

    if not row:
        # Insert via raw SQL
        try:
            db.execute(text(
                "INSERT IGNORE INTO accounts "
                "(account_code, name, account_type, is_system, is_active, opening_balance, current_balance) "
                "VALUES (:code, :name, :type, 1, 1, 0, 0)"
            ), {"code": code, "name": name, "type": atype})
            db.commit()
        except Exception:
            db.rollback()

    # Fetch the id directly
    try:
        row = db.execute(
            text("SELECT id FROM accounts WHERE account_code = :c LIMIT 1"),
            {"c": code}
        ).fetchone()
    except Exception:
        row = None

    if row and row[0]:
        # Fetch full object via ORM now that schema is fixed
        from app.models.models import Account
        acc = db.query(Account).filter(Account.account_code == code).first()
        if acc:
            return acc
        # ORM still fails (edge case) - return minimal object with real id
        acc = Account()
        acc.id = row[0]
        acc.account_code = code
        acc.name = name
        acc.account_type = atype
        return acc

    # Complete fallback - shouldn't reach here
    from app.models.models import Account
    acc = Account()
    acc.id = 1  # use first account as fallback to avoid NULL FK
    acc.account_code = code
    acc.name = name
    acc.account_type = atype
    return acc

