"""Pre-flight validation for NIC IRP (e-invoice) submissions.

These checks mirror the validations the NIC Invoice Registration Portal
runs server-side, so we fail fast with a clear message BEFORE spending a
Cleartax/IRP API call on an invoice that would be rejected anyway.

Pure functions only — no DB, no network. `validate_einvoice` collects ALL
problems and raises a single HTTP 400 listing every one.
"""
import re
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException

from app.core.config import settings


# GSTIN: 2-digit state code, 5 letters (PAN), 4 digits, 1 letter, 1 entity
# digit/letter, 'Z' (default), 1 checksum digit/letter.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# Document number character class: alphanumeric plus '/' and '-'. Length
# (max 16) and the leading '/'/'0' rule are checked separately so each
# failure reports its own accurate reason.
DOC_NO_RE = re.compile(r"^[0-9A-Za-z/-]+$")

# GST rates the IRP accepts (percent). Cess not handled (not applicable here).
VALID_GST_RATES = {0, 0.1, 0.25, 1, 1.5, 3, 5, 6, 7.5, 12, 18, 28}

# Valid GST state codes (UTs + states + 97 Other Territory, 96 Other Country).
VALID_STATE_CODES = set(range(1, 39)) | {96, 97, 99}

# Common Unit Quantity Codes accepted by the IRP UQC master.
UQC_MAP = {
    "NOS": "NOS", "NO": "NOS", "NOS.": "NOS", "NUMBERS": "NOS", "NUMBER": "NOS",
    "PCS": "PCS", "PC": "PCS", "PIECE": "PCS", "PIECES": "PCS",
    "KG": "KGS", "KGS": "KGS", "KILOGRAM": "KGS", "KILOGRAMS": "KGS",
    "GM": "GMS", "GMS": "GMS", "GRAM": "GMS", "GRAMS": "GMS",
    "LTR": "LTR", "L": "LTR", "LITRE": "LTR", "LITRES": "LTR", "LITER": "LTR",
    "ML": "MLT", "MLT": "MLT",
    "MTR": "MTR", "M": "MTR", "METRE": "MTR", "METER": "MTR", "METERS": "MTR",
    "CM": "CMS", "CMS": "CMS",
    "BOX": "BOX", "BOXES": "BOX",
    "BAG": "BAG", "BAGS": "BAG",
    "BTL": "BTL", "BOTTLE": "BTL", "BOTTLES": "BTL",
    "BDL": "BDL", "BUNDLE": "BDL",
    "DOZ": "DOZ", "DOZEN": "DOZ", "DZN": "DOZ",
    "PAC": "PAC", "PACK": "PAC", "PACKET": "PAC", "PACKS": "PAC",
    "PR": "PRS", "PRS": "PRS", "PAIR": "PRS", "PAIRS": "PRS",
    "ROL": "ROL", "ROLL": "ROL", "ROLLS": "ROL",
    "SET": "SET", "SETS": "SET",
    "SQM": "SQM", "SQF": "SQF", "SQFT": "SQF",
    "TON": "TON", "TONNE": "TON", "MT": "TON",
    "UNT": "UNT", "UNIT": "UNT", "UNITS": "UNT",
    "QTL": "QTL", "QUINTAL": "QTL",
}

DEFAULT_UQC = "NOS"


def normalize_uqc(unit: Optional[str], uqc_map: Optional[dict] = None) -> str:
    """Map a free-text unit of measure to a valid IRP UQC code.

    `uqc_map` lets the caller inject the effective-dated UQC master (resolved
    from uqc_master as of the invoice date); when None it falls back to the
    in-code UQC_MAP so the module stays pure and backward-compatible.
    """
    if not unit:
        return DEFAULT_UQC
    m = uqc_map if uqc_map else UQC_MAP
    key = unit.strip().upper().replace(" ", "")
    return m.get(key, DEFAULT_UQC)


def _state_code_from_gstin(gstin: str) -> Optional[int]:
    try:
        return int(gstin[:2])
    except (ValueError, TypeError):
        return None


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def collect_einvoice_issues(invoice, customer, bill_addr, ship_addr,
                            seller_gstin: str, seller_state_code: int,
                            min_hsn_digits: Optional[int] = None,
                            valid_gst_rates: Optional[set] = None,
                            valid_state_codes: Optional[set] = None) -> List[str]:
    """Return a list of IRP problems (empty if none). Does not raise.

    Used both by the strict API path (which raises) and the manual-entry
    path (which only warns), so the rules live in one place.

    `min_hsn_digits`, `valid_gst_rates`, `valid_state_codes` let the caller
    inject the effective-dated config/masters (resolved as of the invoice
    date); each falls back to the in-code constant when None, so the module
    stays pure and backward-compatible.
    """
    errors: List[str] = []
    rates = valid_gst_rates if valid_gst_rates else VALID_GST_RATES
    states = valid_state_codes if valid_state_codes else VALID_STATE_CODES

    # ── Document number ───────────────────────────────────────────
    doc_no = (invoice.invoice_number or "").strip()
    if not doc_no:
        errors.append("Invoice number is missing.")
    else:
        if len(doc_no) > 16:
            errors.append(f"Invoice number '{doc_no}' exceeds 16 characters.")
        if doc_no[0] in ("/", "0"):
            errors.append(f"Invoice number '{doc_no}' must not start with '/' or '0'.")
        if not DOC_NO_RE.match(doc_no):
            errors.append(
                f"Invoice number '{doc_no}' has invalid characters "
                "(allowed: letters, digits, '/' and '-')."
            )

    # ── Document date (not future-dated) ──────────────────────────
    if invoice.invoice_date:
        from datetime import date as _date
        if invoice.invoice_date > _date.today():
            errors.append(
                f"Invoice date {invoice.invoice_date.isoformat()} is in the future."
            )

    # ── Seller GSTIN / state ──────────────────────────────────────
    if not seller_gstin or not GSTIN_RE.match(seller_gstin):
        errors.append(f"Company GSTIN '{seller_gstin}' is not a valid GSTIN.")
    else:
        sgst_state = _state_code_from_gstin(seller_gstin)
        if sgst_state != int(seller_state_code):
            errors.append(
                f"Company GSTIN state prefix ({sgst_state}) does not match "
                f"company state code ({seller_state_code})."
            )

    # ── Buyer GSTIN / state (skip if URP / unregistered) ──────────
    buyer_gstin = (getattr(customer, "gstin", None) or "").strip().upper()
    if buyer_gstin and buyer_gstin != "URP":
        if not GSTIN_RE.match(buyer_gstin):
            errors.append(f"Buyer GSTIN '{buyer_gstin}' is not a valid GSTIN.")
        else:
            gstin_state = _state_code_from_gstin(buyer_gstin)
            addr_state = None
            if bill_addr is not None:
                addr_state = getattr(bill_addr, "state_code", None)
            if addr_state is not None and gstin_state != int(addr_state):
                errors.append(
                    f"Buyer GSTIN state prefix ({gstin_state}) does not match "
                    f"billing address state code ({addr_state})."
                )

    # ── Place of supply must be resolvable ────────────────────────
    pos = None
    if ship_addr is not None:
        pos = getattr(ship_addr, "state_code", None)
    if pos is None and bill_addr is not None:
        pos = getattr(bill_addr, "state_code", None)
    if pos is None:
        errors.append(
            "Place of supply cannot be determined: shipping/billing address "
            "has no state code."
        )
    elif int(pos) not in states:
        errors.append(f"Place of supply state code ({pos}) is not a valid GST state code.")

    # ── Line items: HSN, GST rate, quantity ───────────────────────
    items = list(getattr(invoice, "items", []) or [])
    if not items:
        errors.append("Invoice has no line items.")
    min_hsn = min_hsn_digits if min_hsn_digits is not None else settings.HSN_MIN_DIGITS
    for idx, item in enumerate(items, 1):
        hsn = (item.hsn_code or "").strip()
        if not hsn:
            errors.append(f"Line {idx}: HSN code is missing.")
        elif not hsn.isdigit():
            errors.append(f"Line {idx}: HSN '{hsn}' must be numeric.")
        elif len(hsn) < min_hsn:
            errors.append(
                f"Line {idx}: HSN '{hsn}' has {len(hsn)} digits; at least "
                f"{min_hsn} required."
            )

        rate = _to_float(item.gst_percent)
        if rate not in rates:
            errors.append(
                f"Line {idx}: GST rate {rate} is not a valid IRP rate "
                f"({sorted(rates)})."
            )

        if _to_float(item.quantity) <= 0:
            errors.append(f"Line {idx}: quantity must be greater than 0.")

    # ── Value reconciliation (TotInvVal ~= AssVal + taxes + roundoff) ──
    ass = _to_float(invoice.taxable_amount)
    cgst = _to_float(invoice.total_cgst)
    sgst = _to_float(invoice.total_sgst)
    igst = _to_float(invoice.total_igst)
    tot = _to_float(invoice.total_amount)
    round_off = compute_round_off(invoice)
    diff = abs(tot - (ass + cgst + sgst + igst + round_off))
    if diff > 1.0:
        errors.append(
            f"Invoice totals do not reconcile: TotInvVal {tot} vs "
            f"AssVal+taxes {ass + cgst + sgst + igst} (diff {round(diff, 2)} > 1.00)."
        )

    return errors


def validate_einvoice(invoice, customer, bill_addr, ship_addr,
                      seller_gstin: str, seller_state_code: int,
                      min_hsn_digits: Optional[int] = None,
                      valid_gst_rates: Optional[set] = None,
                      valid_state_codes: Optional[set] = None) -> None:
    """Strict mode: collect every IRP problem and raise one HTTP 400 if any.

    Args mirror what EInvoiceService._build_payload already loads, so the
    caller passes them in rather than re-querying.
    """
    errors = collect_einvoice_issues(
        invoice, customer, bill_addr, ship_addr, seller_gstin, seller_state_code,
        min_hsn_digits=min_hsn_digits,
        valid_gst_rates=valid_gst_rates,
        valid_state_codes=valid_state_codes,
    )
    if errors:
        raise HTTPException(
            status_code=400,
            detail="E-Invoice validation failed: " + " ".join(errors),
        )


def compute_round_off(invoice) -> float:
    """RndOffAmt = TotInvVal - (AssVal + CGST + SGST + IGST), rounded to 2dp.

    Captures any sub-rupee rounding the stored total already absorbed so the
    IRP value reconciliation passes. Clamped to the IRP's +/- 99.99 range.
    """
    ass = _to_float(invoice.taxable_amount)
    cgst = _to_float(invoice.total_cgst)
    sgst = _to_float(invoice.total_sgst)
    igst = _to_float(invoice.total_igst)
    tot = _to_float(invoice.total_amount)
    ro = round(tot - (ass + cgst + sgst + igst), 2)
    if ro > 99.99:
        ro = 99.99
    elif ro < -99.99:
        ro = -99.99
    return ro
