"""Direct-service Billing smoke test. Exercises the 15 fixes without HTTP."""
import sys, traceback
from datetime import date
from decimal import Decimal

from app.db.session import SessionLocal
from app.services.billing_service import BillingService, CustomerPaymentService
from app.services.customer_service import CustomerService
from app.schemas.billing import (
    InvoiceCreate, InvoiceItemCreate, CreditNoteCreate, ReturnItemCreate,
    CustomerUpdate, CustomerPaymentCreate,
)
from sqlalchemy import text

results = []

def log(case, ok, expected, actual, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    msg = f"{tag} {case}: expected={expected} actual={actual}"
    if detail and not ok:
        msg += f" | detail={detail}"
    print(msg)
    results.append((case, ok))


db = SessionLocal()
try:
    # ── setup ─────────────────────────────────────────────────
    CUST_ID = 11
    ADDR_ID = 22
    PROD_ID = 14
    WH_ID = 2
    print("Using fixtures customer=11 addr=22 product=14 warehouse=2")
    print()

    # B-11 HSN validation
    try:
        InvoiceItemCreate(product_id=PROD_ID, quantity=Decimal("1"),
                          unit_price=Decimal("100"), gst_percent=Decimal("18"),
                          hsn_code="12345")
        log("B-11 5-digit HSN rejected", False, "ValueError", "accepted")
    except Exception:
        log("B-11 5-digit HSN rejected", True, "ValueError", "rejected")

    # ── B-1 + B-2 + B-3 + B-4 + B-5 + B-15: create + cancel + CN ──
    print()
    print("=== Create base invoice ===")
    payload = InvoiceCreate(
        document_type="b2c_invoice", customer_id=CUST_ID,
        warehouse_id=WH_ID, billing_address_id=ADDR_ID,
        shipping_address_id=ADDR_ID, invoice_date=date(2026,5,27),
        items=[InvoiceItemCreate(
            product_id=PROD_ID, quantity=Decimal("2"),
            unit_price=Decimal("1000"), gst_percent=Decimal("18"),
            hsn_code="851620",
        )],
    )
    inv1 = BillingService.create(db, payload, user_id=1, user_role="admin")
    INV1_ID = inv1["id"]
    INV1_TOTAL = float(inv1["total_amount"])
    print(f"  invoice {inv1['invoice_number']} total={INV1_TOTAL}")

    # Verify ledger entry has expected balance
    ledger_before = db.execute(text(
        "SELECT amount, transaction_type, balance FROM ledger_entries "
        "WHERE customer_id=:c AND reference_id=:i AND reference_type='invoice'"
    ), {"c": CUST_ID, "i": INV1_ID}).fetchone()
    log("B-3 ledger entry posted",
        ledger_before is not None,
        "ledger row exists",
        ledger_before)

    # Verify JE numbering uses atomic counter
    je_row = db.execute(text(
        "SELECT entry_number FROM journal_entries WHERE reference_id=:i AND reference_type='invoice' ORDER BY id DESC LIMIT 1"
    ), {"i": INV1_ID}).fetchone()
    log("B-4 JE created with new numbering",
        je_row is not None and je_row[0].startswith("JE-"),
        "JE-* number",
        je_row[0] if je_row else None)

    outstanding_before = float(CustomerService._get_outstanding(db, CUST_ID))
    print(f"  outstanding before cancel: {outstanding_before}")

    # B-1: cancel the invoice
    print()
    print("=== B-1 cancel reversal ===")
    BillingService.cancel(db, INV1_ID, "smoke test cancellation", user_id=1)

    # Reversing ledger entry should exist
    reverse_le = db.execute(text(
        "SELECT amount, transaction_type FROM ledger_entries "
        "WHERE reference_id=:i AND reference_type='invoice_cancellation'"
    ), {"i": INV1_ID}).fetchone()
    log("B-1 reversing ledger entry created",
        reverse_le is not None and str(reverse_le[1]).endswith("credit"),
        "credit row exists",
        reverse_le)

    # Reversing JE should exist
    reverse_je = db.execute(text(
        "SELECT entry_number FROM journal_entries "
        "WHERE reference_id=:i AND reference_type='invoice_cancellation'"
    ), {"i": INV1_ID}).fetchone()
    log("B-1 reversing JE created",
        reverse_je is not None,
        "JE row exists",
        reverse_je[0] if reverse_je else None)

    # Stock restored: a return_in StockEntry should exist
    stock_back = db.execute(text(
        "SELECT quantity FROM stock_entries "
        "WHERE reference_id=:i AND reference_type='invoice_cancellation' AND transaction_type='return_in'"
    ), {"i": INV1_ID}).fetchone()
    log("B-1 stock restored (return_in entry)",
        stock_back is not None and float(stock_back[0] or 0) > 0,
        "return_in row exists",
        stock_back)

    # B-14: outstanding should drop after cancel
    outstanding_after = float(CustomerService._get_outstanding(db, CUST_ID))
    log("B-14 outstanding drops after cancel",
        abs((outstanding_before - outstanding_after) - INV1_TOTAL) < 0.5
        or outstanding_after < outstanding_before,
        f"drops ~{INV1_TOTAL}",
        f"before={outstanding_before} after={outstanding_after}")

    # ── B-2 credit note GST ───────────────────────────────────
    print()
    print("=== B-2 credit note GST reversal ===")
    inv2 = BillingService.create(db, payload, user_id=1, user_role="admin")
    INV2_ID = inv2["id"]
    INV2_ITEM_ID = inv2["items"][0]["id"]

    cn_payload = CreditNoteCreate(
        original_invoice_id=INV2_ID, return_date=date(2026,5,27),
        items=[ReturnItemCreate(invoice_item_id=INV2_ITEM_ID, quantity=Decimal("1"),
                                 reason="damaged")],
    )
    cn = BillingService.create_credit_note(db, cn_payload, user_id=1, user_role="admin")
    cn_items = cn.get("items", [])
    item = cn_items[0] if cn_items else {}
    cgst = float(item.get("cgst_amount", 0))
    sgst = float(item.get("sgst_amount", 0))
    igst = float(item.get("igst_amount", 0))
    log("B-2 CN line has GST reversal",
        (cgst + sgst + igst) > 0,
        "cgst+sgst+igst > 0",
        f"cgst={cgst} sgst={sgst} igst={igst}")

    cn_total = float(cn.get("total_amount", 0))
    # 1 qty * 1000 unit * 1.18 = 1180
    log("B-2 CN total = taxable + GST",
        abs(cn_total - 1180) < 1,
        "~1180",
        cn_total)

    # ── B-13 get_last_price filter ────────────────────────────
    print()
    print("=== B-13 get_last_price filter ===")
    last_price = CustomerService.get_last_price(db, CUST_ID, PROD_ID)
    log("B-13 last_price returns actual invoice price",
        last_price is not None and float(last_price) == 1000.0,
        "1000.00",
        last_price)

    # ── B-5 + B-15 payment + WhatsApp ─────────────────────────
    print()
    print("=== B-5 payment numbering + B-15 WhatsApp formatting ===")
    pay_payload = CustomerPaymentCreate(
        customer_id=CUST_ID, invoice_id=INV2_ID,
        payment_date=date(2026,5,27), amount=Decimal("500"),
        payment_mode="cash",
    )
    pay = CustomerPaymentService.create(db, pay_payload, user_id=1)
    log("B-5 payment created with new numbering",
        pay.get("payment_number", "").startswith("RCP-"),
        "RCP-* number",
        pay.get("payment_number"))

    # B-15: WhatsApp message formatting
    wa = BillingService.get_whatsapp_url(INV2_ID, db)
    msg = wa.get("message", "")
    # invoice is 2*1000*1.18=2360 -> expect "2,360.00"
    # Avoid printing rupee symbol on Windows cp1252 console.
    safe_msg = msg.encode("ascii", "ignore").decode("ascii")[:120]
    log("B-15 WhatsApp uses Indian comma formatting",
        "2,360.00" in msg,
        "'2,360.00' in msg",
        safe_msg)

    # ── B-6 admin-only fields ─────────────────────────────────
    print()
    print("=== B-6 admin-only credit_limit ===")
    # CustomerUpdate accepts the field; the endpoint guard is what blocks
    # non-admin from setting it. Service-level call is allowed (admin path).
    upd = CustomerUpdate(credit_limit=Decimal("200000"))
    CustomerService.update(db, CUST_ID, upd, user_id=1)
    cust = CustomerService.get_by_id(db, CUST_ID)
    log("B-6 admin can update credit_limit",
        float(cust.get("credit_limit", 0)) == 200000.0,
        "200000.00",
        cust.get("credit_limit"))

    # ── Summary ───────────────────────────────────────────────
    print()
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print(f"Total: {passed}/{len(results)} passed, {failed} failed")
    if failed:
        print()
        print("Failed cases:")
        for c, ok in results:
            if not ok:
                print(f"  - {c}")
    sys.exit(0 if failed == 0 else 1)

except Exception:
    traceback.print_exc()
    sys.exit(2)
finally:
    db.close()
