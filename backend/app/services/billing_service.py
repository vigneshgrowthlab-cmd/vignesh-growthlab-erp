from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi import HTTPException
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from typing import Optional, List
import json
import smtplib
from email.mime.text import MIMEText

from app.models.models import (
    Invoice, InvoiceItem, InvoiceSequence, Customer, CustomerAddress,
    Warehouse, Product, LedgerEntry, TransactionType, JournalEntry,
    JournalLine, Account, CustomerPayment, DocumentType, GSTType,
    EInvoiceStatus, CompanySettings
)
from app.schemas.billing import InvoiceCreate, CustomerPaymentCreate, CreditNoteCreate
from app.services.product_service import StockService
from app.services.price_history_service import activate_scheduled_prices
from app.models.models import StockTransactionType
from app.utils.helpers import (
    get_or_create_account, paginate, get_current_fy, get_financial_year,
    determine_gst_type, calculate_gst, next_sequence_number, fmt_inr,
    _seed_from_suffix, resolve_state_code, state_name_for_code,
    format_document_number,
)
from app.services.audit import audit


def _qr_data_uri(signed_qr: Optional[str]) -> Optional[str]:
    """Render a NIC SignedQRCode string into a PNG data-URI for display.

    Returns None for empty values and for MOCK-QR-* sandbox placeholders so
    no meaningless QR is shown in dev. Returns None silently if the qrcode
    lib is unavailable, so invoice rendering never breaks.
    """
    if not signed_qr or str(signed_qr).startswith("MOCK-QR"):
        return None
    try:
        import io, base64, qrcode
        img = qrcode.make(str(signed_qr))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None

from app.core.config import settings
from app.services.company_service import CompanyService
from app.services.config_service import ConfigService
from app.services.gst_master_service import GstMasterService


DOC_TYPE_AFFECTS_STOCK = {
    DocumentType.b2b_invoice, DocumentType.b2c_invoice, DocumentType.delivery_challan
}
DOC_TYPE_AFFECTS_ACCOUNTING = {
    DocumentType.b2b_invoice, DocumentType.b2c_invoice
}


class InvoiceNumberingService:

    # Built-in fallbacks if the CompanySettings row/column is unset.
    _DEFAULT_PREFIXES = {
        DocumentType.b2b_invoice: "BINV",
        DocumentType.b2c_invoice: "CINV",
        DocumentType.quotation: "QT",
        DocumentType.delivery_challan: "DC",
        DocumentType.credit_note: "CN",
    }

    _SETTINGS_PREFIX_COLUMNS = {
        DocumentType.b2b_invoice: "b2b_invoice_prefix",
        DocumentType.b2c_invoice: "b2c_invoice_prefix",
        DocumentType.quotation: "quotation_prefix",
        DocumentType.delivery_challan: "challan_prefix",
        DocumentType.credit_note: "credit_note_prefix",
    }

    @staticmethod
    def _prefix_for(db: Session, doc_type: DocumentType) -> str:
        """Resolve the document prefix from the editable Settings screen
        (CompanySettings), falling back to the built-in default."""
        col = InvoiceNumberingService._SETTINGS_PREFIX_COLUMNS.get(doc_type)
        default = InvoiceNumberingService._DEFAULT_PREFIXES.get(doc_type, "INV")
        if not col:
            return default
        s = db.query(CompanySettings).first()
        val = (getattr(s, col, None) or "").strip() if s else ""
        return val or default

    @staticmethod
    def get_next_number(db: Session, doc_type: DocumentType, fy: str) -> str:
        seq = db.query(InvoiceSequence).filter(
            InvoiceSequence.document_type == doc_type,
            InvoiceSequence.financial_year == fy,
        ).with_for_update().first()

        if not seq:
            prefix = InvoiceNumberingService._prefix_for(db, doc_type)
            seq = InvoiceSequence(
                document_type=doc_type, prefix=prefix,
                financial_year=fy, last_number=0
            )
            db.add(seq)
            db.flush()

        seq.last_number += 1
        # Format: PREFIX/YY-YY/NNN  e.g. BINV/26-27/001
        fy_parts = fy.split("-")  # ["2026", "27"]
        fy_short = f"{fy_parts[0][-2:]}-{fy_parts[1]}" if len(fy_parts) == 2 else fy[-5:]
        number = f"{seq.prefix}/{fy_short}/{seq.last_number:03d}"
        # GST caps the invoice serial at 16 characters (Rule 46). Fail loudly if
        # an over-long prefix (or a >9999 running counter) would emit an invalid
        # number, rather than silently storing a non-compliant one.
        if len(number) > 16:
            raise HTTPException(
                status_code=400,
                detail=(f"Generated invoice number '{number}' ({len(number)} chars) exceeds "
                        f"the 16-character GST limit. Shorten the '{seq.prefix}' prefix in Settings."),
            )
        return number


class BillingService:

    @staticmethod
    def _get_account(db, code):
        return get_or_create_account(db, code)

    @staticmethod
    def _round_to_rupee(exact_total: Decimal):
        """Round a grand total to the nearest rupee (ROUND_HALF_UP).

        Returns (rounded_total, round_off) where
        round_off = rounded_total - exact_total  (e.g. +0.40 / -0.30).
        """
        exact_total = (exact_total or Decimal("0")).quantize(Decimal("0.01"))
        rounded_total = exact_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        round_off = (rounded_total - exact_total).quantize(Decimal("0.01"))
        return rounded_total, round_off

    @staticmethod
    def _post_journal(db: Session, entry_date: date, ref_type: str,
                      ref_id: int, narration: str, fy: str,
                      lines: list, user_id: int):
        # Atomic row-locked counter — replaces unsafe count()+1 which races
        # under concurrent invoice / payment writes. Seed from existing
        # journal_entries.entry_number suffix so first call doesn't collide
        # with legacy data written by the old buggy scheme.
        seq = next_sequence_number(
            db, "journal_entry", "JE", fy,
            seed_from=lambda d, f: _seed_from_suffix(d, f, "journal_entries", "entry_number"),
        )
        je = JournalEntry(
            entry_number=format_document_number(db, "JE", fy, seq, "JE", 5),
            entry_date=entry_date, reference_type=ref_type,
            reference_id=ref_id, narration=narration,
            financial_year=fy, created_by=user_id,
        )
        db.add(je)
        db.flush()
        for acc_code, txn_type, amount in lines:
            acc = BillingService._get_account(db, acc_code)
            jl = JournalLine(
                journal_entry_id=je.id, account_id=acc.id,
                transaction_type=txn_type, amount=amount,
            )
            db.add(jl)

    @staticmethod
    def _post_customer_ledger(db: Session, customer_id: int,
                               txn_type: TransactionType, amount: Decimal,
                               ref_type: str, ref_id: int, narration: str,
                               entry_date: date, fy: str):
        # Lock the customer row so concurrent ledger posts for this customer
        # serialise. Without this lock, two concurrent invoices both read the
        # same `last.balance`, both write the same `balance`, and the running
        # balance ends up wrong on the second row.
        db.query(Customer).filter(
            Customer.id == customer_id
        ).with_for_update().first()
        last = db.query(LedgerEntry).filter(
            LedgerEntry.customer_id == customer_id
        ).order_by(desc(LedgerEntry.id)).first()
        prev_bal = last.balance if last else Decimal("0")
        balance = (prev_bal + amount if txn_type == TransactionType.debit
                   else prev_bal - amount)
        le = LedgerEntry(
            customer_id=customer_id, transaction_type=txn_type,
            amount=amount, balance=balance,
            reference_type=ref_type, reference_id=ref_id,
            narration=narration, entry_date=entry_date, financial_year=fy,
        )
        db.add(le)

    @staticmethod
    def _check_floor_price(product: Product, unit_price: Decimal,
                           is_admin: bool) -> bool:
        """Returns True if price is valid, False if below floor."""
        if unit_price < product.floor_price and not is_admin:
            return False
        return True

    @staticmethod
    def list_invoices(db: Session, page: int = 1, page_size: int = 20,
                      customer_id: Optional[int] = None,
                      document_type: Optional[str] = None,
                      financial_year: Optional[str] = None,
                      search: Optional[str] = None,
                      restrict_to_warehouse_id: Optional[int] = None) -> dict:
        """List invoices. When restrict_to_warehouse_id is set AND the
        document_type filter targets delivery_challan, only DCs where
        warehouse_id = restrict_to_warehouse_id OR
        dc_destination_warehouse_id = restrict_to_warehouse_id are returned.
        Other doc types are not restricted by this param (it's specifically
        for DC visibility RBAC for non-super-admin warehouse-mapped users)."""
        q = db.query(Invoice)
        if customer_id:
            q = q.filter(Invoice.customer_id == customer_id)
        if document_type:
            q = q.filter(Invoice.document_type == document_type)
        if financial_year:
            q = q.filter(Invoice.financial_year == financial_year)
        if search:
            q = q.filter(Invoice.invoice_number.ilike(f"%{search}%"))

        # DC visibility RBAC: only applies when listing delivery challans
        if restrict_to_warehouse_id is not None and document_type \
                and "delivery_challan" in str(document_type).lower():
            from sqlalchemy import or_ as _or, text as _sqltxt
            q = q.filter(_or(
                Invoice.warehouse_id == restrict_to_warehouse_id,
                _sqltxt("invoices.dc_destination_warehouse_id = :uwh")
                    .bindparams(uwh=restrict_to_warehouse_id),
            ))

        result = paginate(q.order_by(desc(Invoice.invoice_date), desc(Invoice.id)), page, page_size)

        # Recalculate paid/outstanding from actual customer_payments (source of truth)
        # Quotations and DCs excluded — they never have outstanding
        EXCLUDED_TYPES = ("quotation", "DocumentType.quotation", "delivery_challan")
        inv_ids = [inv.id for inv in result["items"]
                   if str(inv.document_type) not in EXCLUDED_TYPES]
        paid_map = {}
        if inv_ids:
            rows = db.query(
                CustomerPayment.invoice_id,
                func.sum(CustomerPayment.amount).label("paid")
            ).filter(
                CustomerPayment.invoice_id.in_(inv_ids)
            ).group_by(CustomerPayment.invoice_id).all()
            paid_map = {r.invoice_id: float(r.paid) for r in rows}

        # Sync: use MAX of linked payments and stored paid_amount
        # FIFO sets stored paid_amount directly (payments not linked via invoice_id)
        # Never reduce stored paid_amount — only increase it
        synced = False
        for inv in result["items"]:
            if str(inv.document_type) in EXCLUDED_TYPES:
                continue
            linked_paid = paid_map.get(inv.id, 0.0)
            stored_paid = float(inv.paid_amount or 0)
            # Take the higher value — FIFO may have stored more than what's linked
            actual_paid = max(linked_paid, stored_paid)
            actual_outstanding = max(0.0, float(inv.total_amount or 0) - actual_paid)
            if abs(stored_paid - actual_paid) > 0.001:
                inv.paid_amount = Decimal(str(round(actual_paid, 2)))
                inv.outstanding_amount = Decimal(str(round(actual_outstanding, 2)))
                synced = True
        if synced:
            try:
                db.commit()
            except Exception:
                db.rollback()

        items = []
        for inv in result["items"]:
            cust = db.query(Customer).filter(Customer.id == inv.customer_id).first()
            # Quotations don't count toward outstanding
            is_no_outstanding = str(inv.document_type) in EXCLUDED_TYPES
            if is_no_outstanding:
                paid = 0.0
                outstanding = 0.0
            else:
                linked_paid = paid_map.get(inv.id, 0.0)
                stored_paid = float(inv.paid_amount or 0)
                paid = max(linked_paid, stored_paid)
                outstanding = max(0.0, float(inv.total_amount or 0) - paid)
            wh = db.query(Warehouse).filter(Warehouse.id == inv.warehouse_id).first()
            # Read DC fields via raw SQL
            from sqlalchemy import text as _text2
            try:
                _dc_r = db.execute(_text2(
                    "SELECT dc_destination_warehouse_id, vehicle_number, dc_status "
                    "FROM invoices WHERE id = :id"
                ), {"id": inv.id}).fetchone()
                _dst_id = _dc_r[0] if _dc_r else None
                _vnum = _dc_r[1] if _dc_r else None
                _dcst = _dc_r[2] if _dc_r else None
            except Exception:
                _dst_id = getattr(inv, 'dc_destination_warehouse_id', None)
                _vnum = getattr(inv, 'vehicle_number', None)
                _dcst = getattr(inv, 'dc_status', None)
            _dst_wh = db.query(Warehouse).filter(Warehouse.id == _dst_id).first() if _dst_id else None
            items.append({
                "id": inv.id, "invoice_number": inv.invoice_number,
                "document_type": inv.document_type,
                "customer_name": cust.trade_name if cust else None,
                "customer_gstin": cust.gstin if cust else None,
                "customer_id": inv.customer_id,
                "invoice_date": inv.invoice_date, "due_date": inv.due_date,
                "total_amount": inv.total_amount,
                "paid_amount": paid,
                "outstanding_amount": outstanding,
                "credited_amount": float(getattr(inv, "credited_amount", None) or Decimal("0")),
                "gst_type": inv.gst_type, "is_cancelled": inv.is_cancelled,
                "irn_status": inv.irn_status,
                "financial_year": inv.financial_year, "created_at": inv.created_at,
                "salesperson_name": None,
                "warehouse_id": inv.warehouse_id,
                "warehouse_name": wh.name if wh else None,
                "dc_destination_warehouse_id": _dst_id,
                "destination_warehouse_name": _dst_wh.name if _dst_wh else None,
                "vehicle_number": _vnum,
                "driver_name": getattr(inv, 'driver_name', None),
                "lr_number": getattr(inv, 'lr_number', None),
                "quotation_status": getattr(inv, "quotation_status", None),
                "quotation_id": getattr(inv, "quotation_id", None),
                "dc_status": _dcst,
            })
        result["items"] = items
        return result

    @staticmethod
    def get_by_id(db: Session, invoice_id: int) -> dict:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        cust = db.query(Customer).filter(Customer.id == inv.customer_id).first()
        wh = db.query(Warehouse).filter(Warehouse.id == inv.warehouse_id).first()
        bill_addr = db.query(CustomerAddress).filter(CustomerAddress.id == inv.billing_address_id).first()
        ship_addr = db.query(CustomerAddress).filter(CustomerAddress.id == inv.shipping_address_id).first()

        items = []
        for item in inv.items:
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            items.append({
                "id": item.id, "product_id": item.product_id,
                "part_code": prod.part_code if prod else None,
                "part_name": prod.part_name if prod else None,
                "quantity": item.quantity, "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "discount_amount": item.discount_amount,
                "taxable_amount": item.taxable_amount,
                "gst_percent": item.gst_percent,
                "cgst_percent": item.cgst_percent, "sgst_percent": item.sgst_percent,
                "igst_percent": item.igst_percent,
                "cgst_amount": item.cgst_amount, "sgst_amount": item.sgst_amount,
                "igst_amount": item.igst_amount,
                "line_total": item.line_total, "hsn_code": item.hsn_code,
                "fifo_cost": item.fifo_cost,
                "notes": getattr(item, 'notes', None),
            })

        def addr_dict(a):
            if not a:
                return None
            # Read state_code via raw SQL to avoid ORM column mapping issues
            _state_code = None
            try:
                from sqlalchemy import text as _sqta
                _row = db.execute(_sqta(
                    "SELECT state_code FROM customer_addresses WHERE id=:id"
                ), {"id": a.id}).fetchone()
                _state_code = _row[0] if _row else None
            except Exception:
                _state_code = getattr(a, 'state_code', None)
            return {
                "id": a.id, "label": a.label, "address_line1": a.address_line1,
                "address_line2": a.address_line2, "city": a.city,
                "state": a.state, "state_code": _state_code,
                "pincode": a.pincode,
                "contact_person": a.contact_person, "phone": a.phone,
            }

        # DC/quotation/cancelled invoices have no outstanding
        _no_outstanding = (
            str(inv.document_type) in ("quotation", "DocumentType.quotation", "delivery_challan")
            or bool(inv.is_cancelled)
        )
        if _no_outstanding:
            _paid_actual = Decimal("0")
        else:
            _paid_rows = db.query(func.sum(CustomerPayment.amount)).filter(
                CustomerPayment.invoice_id == inv.id
            ).scalar()
            _paid_actual = _paid_rows if _paid_rows else Decimal("0")

        # Read DC fields via raw SQL to avoid ORM column mapping issues
        from sqlalchemy import text as _text
        _dc_row = db.execute(_text(
            "SELECT dc_destination_warehouse_id, vehicle_id, vehicle_number, "
            "driver_name, lr_number, dc_status, transporter_id, transporter_name, show_transport_on_print "
            "FROM invoices WHERE id = :id"
        ), {"id": inv.id}).fetchone()
        _dst_wh_id = _dc_row[0] if _dc_row else None
        _dst_wh = db.query(Warehouse).filter(Warehouse.id == _dst_wh_id).first() if _dst_wh_id else None
        _vehicle_id = _dc_row[1] if _dc_row else None
        _vehicle_number = _dc_row[2] if _dc_row else None
        _driver_name = _dc_row[3] if _dc_row else None
        _lr_number = _dc_row[4] if _dc_row else None
        _dc_status = _dc_row[5] if _dc_row else None
        _transporter_id = _dc_row[6] if _dc_row else None
        _transporter_name = _dc_row[7] if _dc_row else None
        _raw_stp = _dc_row[8] if _dc_row else None
        _show_transport_on_print = bool(_raw_stp) if _raw_stp is not None else None
        if _transporter_id and not _transporter_name:
            from app.models.models import Transporter as _TP
            _tp = db.query(_TP).filter(_TP.id == _transporter_id).first()
            _transporter_name = _tp.name if _tp else None

        return {
            "id": inv.id, "invoice_number": inv.invoice_number,
            "document_type": inv.document_type,
            "customer_id": inv.customer_id,
            "customer_name": cust.trade_name if cust else None,
            "customer_gstin": cust.gstin if cust else None,
            "warehouse_id": inv.warehouse_id,
            "warehouse_name": wh.name if wh else None,
            "dc_destination_warehouse_id": _dst_wh_id,
            "destination_warehouse_name": _dst_wh.name if _dst_wh else None,
            "vehicle_number": _vehicle_number,
            "vehicle_id": _vehicle_id,
            "driver_name": _driver_name,
            "lr_number": _lr_number,
            "dc_status": _dc_status,
            "transporter_id": _transporter_id,
            "transporter_name": _transporter_name,
            "show_transport_on_print": _show_transport_on_print,
            "billing_address_id": inv.billing_address_id,
            "shipping_address_id": inv.shipping_address_id,
            "billing_address": addr_dict(bill_addr),
            "shipping_address": addr_dict(ship_addr),
            "invoice_date": inv.invoice_date, "due_date": inv.due_date,
            "subtotal": inv.subtotal, "item_discount": inv.item_discount,
            "invoice_discount": inv.invoice_discount,
            "taxable_amount": inv.taxable_amount,
            "total_cgst": inv.total_cgst, "total_sgst": inv.total_sgst,
            "total_igst": inv.total_igst,
            "round_off": inv.round_off or Decimal("0"),
            "total_amount": inv.total_amount,
            "paid_amount": float(_paid_actual),
            "outstanding_amount": float(Decimal("0") if _no_outstanding else max(Decimal("0"), inv.total_amount - _paid_actual)),
            "credited_amount": float(getattr(inv, "credited_amount", None) or Decimal("0")),
            "gst_type": inv.gst_type, "terms_conditions": inv.terms_conditions,
            "place_of_supply": getattr(inv, "place_of_supply", None),
            "place_of_supply_name": state_name_for_code(getattr(inv, "place_of_supply", None)),
            "notes": inv.notes, "financial_year": inv.financial_year,
            "is_cancelled": inv.is_cancelled, "cancelled_reason": inv.cancelled_reason,
            "irn": inv.irn, "irn_status": inv.irn_status,
            "irn_ack_number": getattr(inv, "irn_ack_number", None),
            "qr_code_image": _qr_data_uri(getattr(inv, "qr_code", None)),
            "eway_bill_number": inv.eway_bill_number,
            "eway_bill_status": getattr(inv, "eway_bill_status", None),
            "salesperson_id": getattr(inv, 'salesperson_id', None),
            "salesperson_name": None,
            "created_at": inv.created_at,
            "items": items,
            "quotation_status": getattr(inv, "quotation_status", None),
            "quotation_id": getattr(inv, "quotation_id", None),
            "original_invoice_id": getattr(inv, "original_invoice_id", None),
            "dc_status": getattr(inv, "dc_status", None),
        }

    @staticmethod
    def create(db: Session, payload: InvoiceCreate,
               user_id: int, user_role: str) -> dict:
        customer = None
        if payload.customer_id:
            customer = db.query(Customer).filter(
                Customer.id == payload.customer_id, Customer.is_active == True
            ).first()
            if not customer:
                raise HTTPException(status_code=404, detail="Customer not found")

        warehouse = db.query(Warehouse).filter(
            Warehouse.id == payload.warehouse_id, Warehouse.is_active == True
        ).first()
        if not warehouse:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        # Validate addresses — skip for DC and quotation (no addresses required)
        doc_type = str(payload.document_type).lower().replace("documenttype.", "")
        is_dc = doc_type == "delivery_challan"
        if doc_type in ("b2b_invoice", "b2c_invoice") and payload.customer_id:
            for addr_id in [payload.billing_address_id, payload.shipping_address_id]:
                if not addr_id:
                    continue
                addr = db.query(CustomerAddress).filter(
                    CustomerAddress.id == addr_id,
                    CustomerAddress.customer_id == payload.customer_id
                ).first()
                if not addr:
                    raise HTTPException(status_code=404, detail=f"Address {addr_id} not found for this customer")

        # ── Credit limit check (only for actual invoices, not quotations/challans) ──
        if str(payload.document_type) in ("b2b_invoice", "b2c_invoice") and customer:
            credit_limit = float(customer.credit_limit or 0)
            estimated_total = sum(
                float(item.quantity) * float(item.unit_price)
                for item in payload.items
            )
            if credit_limit == 0:
                # Zero credit: frontend enforces full payment before allowing save
                # Backend does not block here since payment is recorded separately
                pass
            else:
                from app.services.customer_service import CustomerService
                current_outstanding = float(CustomerService._get_outstanding(db, customer.id))
                if current_outstanding + estimated_total > credit_limit:
                    available = max(0, credit_limit - current_outstanding)
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "CREDIT_LIMIT_EXCEEDED",
                            "message": (
                                f"Credit limit exceeded for {customer.trade_name}. "
                                f"Credit limit: ₹{credit_limit:,.2f} | "
                                f"Current outstanding: ₹{current_outstanding:,.2f} | "
                                f"Available credit: ₹{available:,.2f} | "
                                f"This invoice: ₹{estimated_total:,.2f} | "
                                f"Shortfall: ₹{max(0, estimated_total - available):,.2f}"
                            ),
                            "credit_limit": credit_limit,
                            "current_outstanding": round(current_outstanding, 2),
                            "this_invoice": round(estimated_total, 2),
                            "available_credit": round(available, 2),
                            "shortfall": round(max(0, estimated_total - available), 2),
                        }
                    )

        fy = get_financial_year(payload.invoice_date)

        # Determine GST type from shipping address state
        # For DC/quotation: customer and ship_addr may be None — default to cgst_sgst (intrastate)
        ship_addr = None
        if payload.shipping_address_id:
            ship_addr = db.query(CustomerAddress).filter(
                CustomerAddress.id == payload.shipping_address_id
            ).first()
        ship_state = getattr(ship_addr, 'state_code', None) or getattr(customer, 'state_code', None) or 0

        # Use warehouse state for GST determination (not company state)
        # Compare warehouse state name vs shipping address state name
        wh_state_name = None
        if payload.warehouse_id:
            from app.models.models import Warehouse as _WH
            _wh = db.query(_WH).filter(_WH.id == payload.warehouse_id).first()
            wh_state_name = getattr(_wh, 'state', None) if _wh else None

        ship_state_name = getattr(ship_addr, 'state', None) if ship_addr else None

        # Decide CGST/SGST vs IGST by comparing state CODES (primary path).
        # Origin = warehouse state, resolved to a code via the states master
        # (warehouses store only a name); falls back to the company state code.
        # Destination = shipping-address / customer state code, else resolved
        # from the address state name. Code comparison avoids the fragile
        # name string-match ("Tamilnadu" vs "Tamil Nadu"). The legacy name
        # comparison is kept only as a last resort when no code can be derived.
        origin_code = (getattr(warehouse, "state_code", None)
                       or resolve_state_code(wh_state_name)
                       or CompanyService.identity(db).state_code)
        dest_code = ship_state or resolve_state_code(ship_state_name)

        if origin_code and dest_code:
            gst_type_str = determine_gst_type(dest_code, origin_code)
        elif wh_state_name and ship_state_name:
            gst_type_str = "cgst_sgst" if (
                wh_state_name.lower().strip() == ship_state_name.lower().strip()
            ) else "igst"
        else:
            gst_type_str = determine_gst_type(ship_state, CompanyService.identity(db).state_code)
        gst_type = GSTType.cgst_sgst if gst_type_str == "cgst_sgst" else GSTType.igst

        is_admin = str(user_role) in ("admin", "super_admin")

        invoice_number = InvoiceNumberingService.get_next_number(db, payload.document_type, fy)

        invoice = Invoice(
            invoice_number=invoice_number,
            document_type=payload.document_type,
            customer_id=payload.customer_id,
            warehouse_id=payload.warehouse_id,
            billing_address_id=payload.billing_address_id,
            shipping_address_id=payload.shipping_address_id,
            invoice_date=payload.invoice_date,
            due_date=payload.due_date,
            gst_type=gst_type,
            place_of_supply=(dest_code or None),
            invoice_discount=payload.invoice_discount,
            terms_conditions=payload.terms_conditions,
            notes=payload.notes,
            financial_year=fy,
            created_by=user_id,
        )
        try:
            invoice.salesperson_id = user_id
        except Exception:
            pass
        db.add(invoice)
        db.flush()

        # Save DC-specific fields via raw SQL — guaranteed to work regardless of ORM state
        from sqlalchemy import text
        if is_dc:
            try:
                db.execute(text(
                    "UPDATE invoices SET "
                    "dc_destination_warehouse_id = :dst, "
                    "dc_status = 'pending' "
                    "WHERE id = :iid"
                ), {
                    "dst": getattr(payload, 'dc_destination_warehouse_id', None),
                    "iid": invoice.id,
                })
            except Exception as e:
                print(f"[DC] FAILED to save DC fields: {e}")

        # Save transport fields for all document types. Vehicle/LR were previously
        # persisted only for delivery challans, so invoices silently lost them.
        _tp_id = getattr(payload, 'transporter_id', None)
        _tp_name = (getattr(payload, 'transporter_name', None) or '').strip() or None
        _show_tp = getattr(payload, 'show_transport_on_print', None)
        try:
            db.execute(text(
                "UPDATE invoices SET transporter_id = :tid, transporter_name = :tname, "
                "vehicle_id = :vid, vehicle_number = :vnum, driver_name = :dname, "
                "lr_number = :lr, show_transport_on_print = :stp WHERE id = :iid"
            ), {
                "tid": _tp_id, "tname": _tp_name,
                "vid": getattr(payload, 'vehicle_id', None),
                "vnum": (getattr(payload, 'vehicle_number', None) or None),
                "dname": (getattr(payload, 'driver_name', None) or None),
                "lr": (getattr(payload, 'lr_number', None) or None),
                "stp": _show_tp, "iid": invoice.id,
            })
        except Exception as e:
            print(f"[Invoice] FAILED to save transport fields: {e}")

        subtotal = Decimal("0")
        item_discount_total = Decimal("0")
        taxable_total = Decimal("0")
        total_cgst = Decimal("0")
        total_sgst = Decimal("0")
        total_igst = Decimal("0")

        doc_type_str = str(payload.document_type).lower().replace("documenttype.", "")
        affects_stock = payload.document_type in DOC_TYPE_AFFECTS_STOCK and doc_type_str != "quotation"
        affects_accounting = payload.document_type in DOC_TYPE_AFFECTS_ACCOUNTING
        is_quotation = doc_type_str == "quotation"

        for item_data in payload.items:
            product = db.query(Product).filter(
                Product.id == item_data.product_id, Product.is_active == True
            ).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item_data.product_id} not found")

            # Floor price check — skipped for DCs (valued at 10% of b2b price, not a sale)
            if not is_dc and not BillingService._check_floor_price(product, item_data.unit_price, is_admin):
                raise HTTPException(
                    status_code=400,
                    detail=f"Price ₹{item_data.unit_price} for {product.part_name} is below floor price ₹{product.floor_price}"
                )

            # Check stock availability - skip for quotation
            if affects_stock and not is_quotation:
                ws = db.query(__import__('app.models.models', fromlist=['WarehouseStock']).WarehouseStock).filter_by(
                    warehouse_id=payload.warehouse_id, product_id=item_data.product_id
                ).first()
                available = ws.quantity if ws else Decimal("0")
                if available < item_data.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock for {product.part_name}. Available: {available}, Requested: {item_data.quantity}"
                    )

            # GST rate is sourced from the product master, never the request
            # payload — the rate cannot be modified during invoice creation.
            gst_rate = product.gst_percent
            if gst_rate is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"GST rate not configured for {product.part_name}. Set the product's GST % before billing."
                )

            line_subtotal = item_data.unit_price * item_data.quantity
            discount_amount = (line_subtotal * item_data.discount_percent / 100).quantize(Decimal("0.01"))
            taxable = (line_subtotal - discount_amount).quantize(Decimal("0.01"))
            gst_amounts = calculate_gst(float(taxable), float(gst_rate), gst_type_str)

            half_gst = gst_rate / 2
            cgst_pct = half_gst if gst_type_str == "cgst_sgst" else Decimal("0")
            sgst_pct = half_gst if gst_type_str == "cgst_sgst" else Decimal("0")
            igst_pct = gst_rate if gst_type_str == "igst" else Decimal("0")

            line_total = (taxable + Decimal(str(gst_amounts['cgst'])) +
                         Decimal(str(gst_amounts['sgst'])) +
                         Decimal(str(gst_amounts['igst']))).quantize(Decimal("0.01"))

            fifo_cost = None
            if affects_stock and not is_dc:
                fifo_cost = StockService.consume_fifo(
                    db, item_data.product_id, payload.warehouse_id, item_data.quantity
                )

            ii = InvoiceItem(
                invoice_id=invoice.id, product_id=item_data.product_id,
                quantity=item_data.quantity, unit_price=item_data.unit_price,
                discount_percent=item_data.discount_percent,
                discount_amount=discount_amount, taxable_amount=taxable,
                gst_percent=gst_rate,
                cgst_percent=cgst_pct, sgst_percent=sgst_pct, igst_percent=igst_pct,
                cgst_amount=Decimal(str(gst_amounts['cgst'])),
                sgst_amount=Decimal(str(gst_amounts['sgst'])),
                igst_amount=Decimal(str(gst_amounts['igst'])),
                line_total=line_total, hsn_code=item_data.hsn_code,
                fifo_cost=fifo_cost,
            )
            db.add(ii)
            db.flush()  # get ii.id before raw SQL
            try:
                from sqlalchemy import text as _sqn
                if getattr(item_data, 'notes', None):
                    db.execute(_sqn(
                        "UPDATE invoice_items SET notes=:n WHERE id=:id"
                    ), {"n": item_data.notes, "id": ii.id})
            except Exception as _ne:
                print(f"[NOTES] save failed: {_ne}")

            subtotal += line_subtotal
            item_discount_total += discount_amount
            taxable_total += taxable
            total_cgst += Decimal(str(gst_amounts['cgst']))
            total_sgst += Decimal(str(gst_amounts['sgst']))
            total_igst += Decimal(str(gst_amounts['igst']))

        # Apply invoice-level discount (fixed amount, not percent)
        inv_disc = Decimal(str(payload.invoice_discount or 0)).quantize(Decimal("0.01"))
        final_taxable = (taxable_total - inv_disc).quantize(Decimal("0.01"))
        exact_total = (final_taxable + total_cgst + total_sgst + total_igst).quantize(Decimal("0.01"))

        # Round the grand total to the nearest rupee for tax invoices only
        # (quotations / delivery challans keep exact paise). round_off is the
        # signed adjustment, stored and posted as a balancing journal line.
        if doc_type_str in ("b2b_invoice", "b2c_invoice"):
            total_amount, round_off = BillingService._round_to_rupee(exact_total)
        else:
            total_amount, round_off = exact_total, Decimal("0.00")

        invoice.subtotal = subtotal.quantize(Decimal("0.01"))
        invoice.item_discount = item_discount_total.quantize(Decimal("0.01"))
        invoice.taxable_amount = final_taxable
        invoice.total_cgst = total_cgst.quantize(Decimal("0.01"))
        invoice.total_sgst = total_sgst.quantize(Decimal("0.01"))
        invoice.total_igst = total_igst.quantize(Decimal("0.01"))
        invoice.round_off = round_off
        invoice.total_amount = total_amount
        invoice.paid_amount = Decimal("0")
        invoice.outstanding_amount = total_amount

        if affects_accounting and payload.customer_id:
            BillingService._post_customer_ledger(
                db, payload.customer_id, TransactionType.debit,
                total_amount, "invoice", invoice.id,
                f"Invoice {invoice_number}", payload.invoice_date, fy
            )
            # Journal: DR Debtors, CR Sales, CR GST Payable, +/- Round Off
            journal_lines = [
                ("DEBTORS", TransactionType.debit, total_amount),
                ("SALES", TransactionType.credit, final_taxable),
            ]
            if total_cgst > 0:
                journal_lines.append(("GST_PAY", TransactionType.credit, total_cgst.quantize(Decimal("0.01"))))
            if total_sgst > 0:
                journal_lines.append(("GST_PAY", TransactionType.credit, total_sgst.quantize(Decimal("0.01"))))
            if total_igst > 0:
                journal_lines.append(("GST_PAY", TransactionType.credit, total_igst.quantize(Decimal("0.01"))))
            # Balancing line: rounded up -> CR income, rounded down -> DR expense
            if round_off > 0:
                journal_lines.append(("ROUND_OFF", TransactionType.credit, round_off))
            elif round_off < 0:
                journal_lines.append(("ROUND_OFF", TransactionType.debit, -round_off))
            BillingService._post_journal(
                db, payload.invoice_date, "invoice", invoice.id,
                f"Sales invoice {invoice_number}",
                fy, journal_lines, user_id
            )

        db.commit()

        audit(db, user_id, "create", "billing",
              f"Created {str(payload.document_type).split('.')[-1]} {invoice.invoice_number}"
              + (f" for {customer.trade_name}" if customer else "")
              + f" — ₹{invoice.total_amount}",
              record_type="invoice", record_id=invoice.id)

        # Auto-email to customer (fire and forget)
        if customer and customer.email and affects_accounting:
            try:
                BillingService._send_invoice_email(customer, invoice)
            except Exception:
                pass

        return BillingService.get_by_id(db, invoice.id)

    @staticmethod
    def set_einvoice_manual(db: Session, invoice_id: int, data: dict, user_id: int) -> dict:
        """Record portal-generated e-invoice details entered manually.

        For businesses that generate the IRN on the government IRP/Cleartax
        portal and paste the result back. Validation is advisory only (the
        portal already accepted it). Editable until the invoice is cancelled.
        """
        from datetime import datetime as _dt
        from app.models.models import EInvoiceLog, EInvoiceStatus, Customer, CustomerAddress
        from app.utils.irp_validation import collect_einvoice_issues
        from app.core.config import settings as _settings

        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.is_cancelled:
            raise HTTPException(status_code=400, detail="Cannot set e-invoice on a cancelled invoice")

        # E-invoicing applies to B2B tax invoices and credit/debit notes only,
        # never to B2C (unregistered buyer). Block at the source.
        doc_type = str(inv.document_type).replace("DocumentType.", "")
        if doc_type not in ("b2b_invoice", "credit_note", "debit_note"):
            raise HTTPException(
                status_code=400,
                detail="E-Invoice applies only to B2B invoices and credit/debit notes",
            )

        irn = (data.get("irn") or "").strip()
        if not irn:
            raise HTTPException(status_code=400, detail="IRN is required")
        # IRN format: 64 alphanumeric characters (NIC hash). Catches paste/typos.
        if len(irn) != 64 or not irn.isalnum():
            raise HTTPException(
                status_code=400,
                detail=f"IRN must be exactly 64 alphanumeric characters (got {len(irn)})",
            )
        # IRN is globally unique — reject if already on another live invoice.
        dup = (db.query(Invoice)
               .filter(Invoice.irn == irn, Invoice.id != invoice_id,
                       Invoice.is_cancelled == False)
               .first())
        if dup:
            raise HTTPException(
                status_code=400,
                detail=f"IRN already recorded on invoice {dup.invoice_number}",
            )

        ack_number = (data.get("ack_number") or "").strip() or None
        signed_qr = (data.get("signed_qr") or data.get("qr_code") or "").strip() or None
        ack_date_raw = (data.get("ack_date") or "").strip()
        ack_date = None
        ack_date_bad = False
        if ack_date_raw:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
                try:
                    ack_date = _dt.strptime(ack_date_raw, fmt)
                    break
                except ValueError:
                    continue
            ack_date_bad = ack_date is None

        # Advisory validation — collect warnings, never block.
        warnings = []
        if ack_date_bad:
            warnings.append(f"Ack date '{ack_date_raw}' was not understood and was not saved.")
        try:
            customer = db.query(Customer).filter(Customer.id == inv.customer_id).first()
            bill_addr = db.query(CustomerAddress).filter(CustomerAddress.id == inv.billing_address_id).first()
            ship_addr = db.query(CustomerAddress).filter(CustomerAddress.id == inv.shipping_address_id).first()
            _company = CompanyService.identity(db)
            warnings.extend(collect_einvoice_issues(
                inv, customer, bill_addr, ship_addr,
                _company.gstin, _company.state_code,
                min_hsn_digits=ConfigService.get_int(
                    db, "gst.hsn_min_digits",
                    as_of=inv.invoice_date, default=_settings.HSN_MIN_DIGITS,
                ),
                valid_gst_rates=GstMasterService.valid_gst_rates(db, inv.invoice_date) or None,
                valid_state_codes=GstMasterService.valid_state_codes(db, inv.invoice_date) or None,
            ))
        except Exception:
            pass

        inv.irn = irn
        inv.irn_status = EInvoiceStatus.generated
        inv.irn_ack_number = ack_number
        inv.irn_ack_date = ack_date
        inv.qr_code = signed_qr
        inv.irn_generated_at = _dt.now()
        inv.irn_error = None

        log = EInvoiceLog(
            invoice_id=invoice_id, irn=irn, status=EInvoiceStatus.generated,
            ack_number=ack_number, ack_date=ack_date,
            request_payload=json.dumps({"manual_entry": True}),
            response_payload=json.dumps({"irn": irn, "ack_number": ack_number,
                                         "ack_date": ack_date_raw or None}),
            created_by=user_id,
        )
        db.add(log)
        db.commit()
        return {
            "invoice_id": invoice_id, "invoice_number": inv.invoice_number,
            "irn": irn, "irn_status": "generated", "ack_number": ack_number,
            "warnings": warnings,
        }

    @staticmethod
    def set_eway_manual(db: Session, invoice_id: int, data: dict, user_id: int) -> dict:
        """Record portal-generated e-way bill details entered manually."""
        from datetime import datetime as _dt
        from app.models.models import EWayBillLog, EWayBillStatus

        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.is_cancelled:
            raise HTTPException(status_code=400, detail="Cannot set e-way bill on a cancelled invoice")

        ewb = (data.get("eway_bill_number") or "").strip().replace(" ", "")
        if not ewb:
            raise HTTPException(status_code=400, detail="E-Way Bill number is required")
        # E-Way Bill number is exactly 12 digits. Catches paste/typo errors.
        if not (ewb.isdigit() and len(ewb) == 12):
            raise HTTPException(
                status_code=400,
                detail=f"E-Way Bill number must be exactly 12 digits (got '{ewb}')",
            )

        vehicle_number = (data.get("vehicle_number") or "").strip() or None
        transporter_name = (data.get("transporter_name") or "").strip() or None
        transport_mode = (data.get("transport_mode") or "road").strip() or "road"
        distance_km = data.get("distance_km")
        try:
            distance_km = int(distance_km) if distance_km not in (None, "") else None
        except (ValueError, TypeError):
            distance_km = None

        def _parse_dt(raw):
            raw = (raw or "").strip()
            if not raw:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                        "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
                try:
                    return _dt.strptime(raw, fmt)
                except ValueError:
                    continue
            return None

        valid_upto = _parse_dt(data.get("valid_upto"))

        inv.eway_bill_number = ewb
        inv.eway_bill_status = EWayBillStatus.generated

        log = EWayBillLog(
            invoice_id=invoice_id, eway_bill_number=ewb, irn=inv.irn,
            vehicle_number=vehicle_number, transporter_name=transporter_name,
            transport_mode=transport_mode, distance_km=distance_km,
            valid_upto=valid_upto, status=EWayBillStatus.generated,
            entry_type="generate",
            request_payload=json.dumps({"manual_entry": True}),
            response_payload=json.dumps({"eway_bill_number": ewb}),
            created_by=user_id,
        )
        db.add(log)
        db.commit()
        return {
            "invoice_id": invoice_id, "invoice_number": inv.invoice_number,
            "eway_bill_number": ewb, "eway_bill_status": "generated",
            "valid_upto": valid_upto.strftime("%Y-%m-%d %H:%M:%S") if valid_upto else None,
        }

    @staticmethod
    def update_eway_vehicle(db: Session, invoice_id: int, data: dict, user_id: int) -> dict:
        """Record a Part-B / vehicle update for an existing e-way bill (Rule 138(5)).

        Used when the conveyance changes mid-transit (transshipment, breakdown).
        Updates the invoice's current vehicle and appends an audit log row.
        """
        from datetime import datetime as _dt
        from app.models.models import EWayBillLog, EWayBillStatus

        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.is_cancelled:
            raise HTTPException(status_code=400, detail="Cannot update a cancelled invoice")
        if not inv.eway_bill_number:
            raise HTTPException(status_code=400, detail="No e-way bill on this invoice to update")
        if inv.eway_bill_status == EWayBillStatus.cancelled:
            raise HTTPException(status_code=400, detail="E-way bill is cancelled; cannot update vehicle")

        vehicle_number = (data.get("vehicle_number") or "").strip() or None
        if not vehicle_number:
            raise HTTPException(status_code=400, detail="New vehicle number is required")
        transport_mode = (data.get("transport_mode") or "road").strip() or "road"
        reason = (data.get("reason") or "").strip() or None

        log = EWayBillLog(
            invoice_id=invoice_id, eway_bill_number=inv.eway_bill_number, irn=inv.irn,
            vehicle_number=vehicle_number, transport_mode=transport_mode,
            status=EWayBillStatus.generated, entry_type="update_vehicle",
            request_payload=json.dumps({"manual_entry": True, "reason": reason}),
            response_payload=json.dumps({"vehicle_number": vehicle_number}),
            created_by=user_id,
        )
        db.add(log)
        db.commit()
        return {
            "invoice_id": invoice_id, "invoice_number": inv.invoice_number,
            "eway_bill_number": inv.eway_bill_number, "vehicle_number": vehicle_number,
            "eway_bill_status": "generated",
        }

    @staticmethod
    def cancel_eway_manual(db: Session, invoice_id: int, data: dict, user_id: int) -> dict:
        """Record cancellation of an e-way bill (Rule 138(9), within 24h).

        Manual-entry counterpart: the user cancels on the portal, then records
        it here. The 24-hour window is advisory (a warning), since the portal
        is the authority on whether the cancel was accepted.
        """
        from datetime import datetime as _dt, timedelta as _td
        from app.models.models import EWayBillLog, EWayBillStatus

        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv.eway_bill_number:
            raise HTTPException(status_code=400, detail="No e-way bill on this invoice to cancel")
        if inv.eway_bill_status == EWayBillStatus.cancelled:
            raise HTTPException(status_code=400, detail="E-way bill already cancelled")

        reason = (data.get("reason") or data.get("cancel_reason") or "").strip() or "Cancelled"

        warnings = []
        # Advisory 24h check based on the latest generate log, if present.
        gen_log = (db.query(EWayBillLog)
                   .filter(EWayBillLog.invoice_id == invoice_id,
                           EWayBillLog.eway_bill_number == inv.eway_bill_number,
                           EWayBillLog.entry_type == "generate")
                   .order_by(EWayBillLog.created_at.desc()).first())
        eway_cancel_hours = ConfigService.get_int(
            db, "gst.eway_cancel_window_hours",
            as_of=gen_log.created_at.date() if (gen_log and gen_log.created_at) else None,
            default=24,
        )
        if gen_log and gen_log.created_at and (_dt.now() - gen_log.created_at) > _td(hours=eway_cancel_hours):
            warnings.append(f"E-way bill is older than {eway_cancel_hours} hours; the portal may not allow cancellation.")

        now = _dt.now()
        inv.eway_bill_status = EWayBillStatus.cancelled
        log = EWayBillLog(
            invoice_id=invoice_id, eway_bill_number=inv.eway_bill_number, irn=inv.irn,
            status=EWayBillStatus.cancelled, entry_type="cancel",
            cancel_reason=reason[:200], cancelled_at=now,
            request_payload=json.dumps({"manual_entry": True, "reason": reason}),
            response_payload=json.dumps({"cancelled": True}),
            created_by=user_id,
        )
        db.add(log)
        db.commit()
        return {
            "invoice_id": invoice_id, "invoice_number": inv.invoice_number,
            "eway_bill_number": inv.eway_bill_number, "eway_bill_status": "cancelled",
            "cancelled_at": now.strftime("%Y-%m-%d %H:%M:%S"), "warnings": warnings,
        }

    @staticmethod
    def cancel(db: Session, invoice_id: int, reason: str, user_id: int) -> dict:
        """Cancel an invoice and reverse all of its side effects.

        Previously this just flipped is_cancelled=TRUE, leaving the customer
        ledger, journal, and stock un-touched — so cancelled invoices kept
        inflating outstanding balances and journal totals.

        Now reverses:
          * Customer ledger: post offsetting credit (or debit for CN)
          * Journal: post reversing JE with debits/credits swapped
          * Stock: restore consumed FIFO via add_stock for stock-affecting docs
        """
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.is_cancelled:
            raise HTTPException(status_code=400, detail="Invoice already cancelled")
        if not reason:
            raise HTTPException(status_code=400, detail="Cancellation reason is required")

        doc_type_str = str(inv.document_type).lower().replace("documenttype.", "")
        affects_accounting = doc_type_str in ("b2b_invoice", "b2c_invoice")
        affects_stock = doc_type_str in ("b2b_invoice", "b2c_invoice", "delivery_challan")
        fy = inv.financial_year or get_financial_year(inv.invoice_date)

        # ── Credit note reversal ──────────────────────────────────
        # A credit note had three effects (see create_credit_note): it added
        # the returned stock back, credited the customer ledger, and reduced
        # the original invoice's outstanding. Reverse all three.
        if doc_type_str == "credit_note":
            # 1) Debit the customer ledger (undo the credit)
            if inv.customer_id and (inv.total_amount or 0) > 0:
                BillingService._post_customer_ledger(
                    db, inv.customer_id, TransactionType.debit,
                    inv.total_amount, "credit_note_reversal", inv.id,
                    f"Reverse credit note {inv.invoice_number}: {reason[:80]}",
                    date.today(), fy,
                )
            # 1b) Reverse the credit note's journal (undo the GST_PAY/SALES
            #     reduction it posted): DR Debtors, CR Sales, CR GST Payable.
            if (inv.total_amount or 0) > 0:
                cn_rev = [
                    ("DEBTORS", TransactionType.debit, inv.total_amount),
                    ("SALES", TransactionType.credit, inv.taxable_amount or Decimal("0")),
                ]
                cgst = inv.total_cgst or Decimal("0")
                sgst = inv.total_sgst or Decimal("0")
                igst = inv.total_igst or Decimal("0")
                if cgst > 0:
                    cn_rev.append(("GST_PAY", TransactionType.credit, cgst))
                if sgst > 0:
                    cn_rev.append(("GST_PAY", TransactionType.credit, sgst))
                if igst > 0:
                    cn_rev.append(("GST_PAY", TransactionType.credit, igst))
                round_off = inv.round_off or Decimal("0")
                if round_off > 0:
                    cn_rev.append(("ROUND_OFF", TransactionType.credit, round_off))
                elif round_off < 0:
                    cn_rev.append(("ROUND_OFF", TransactionType.debit, -round_off))
                BillingService._post_journal(
                    db, date.today(), "credit_note_reversal", inv.id,
                    f"Reverse credit note {inv.invoice_number}: {reason[:80]}",
                    fy, cn_rev, user_id,
                )
            # 2) Remove the stock the credit note added back (FIFO consume).
            #    If the returned goods were re-sold or transferred out since the
            #    credit note was raised, the consume will fail because the FIFO
            #    layers no longer exist. This is a genuine business constraint —
            #    you cannot un-return goods that have already left the warehouse.
            for item in inv.items:
                if not item.quantity or item.quantity <= 0:
                    continue
                try:
                    StockService.consume_fifo(
                        db, item.product_id, inv.warehouse_id, item.quantity
                    )
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Cannot reverse credit note {inv.invoice_number}: "
                            f"insufficient stock for product ID {item.product_id} "
                            f"in warehouse {inv.warehouse_id}. The returned goods "
                            f"may have already been re-sold or transferred out."
                        ),
                    )
            # 3) Restore the original invoice's outstanding
            if inv.original_invoice_id:
                orig = db.query(Invoice).filter(
                    Invoice.id == inv.original_invoice_id).first()
                if orig:
                    restored = (orig.outstanding_amount or Decimal("0")) + (inv.total_amount or Decimal("0"))
                    cap = orig.total_amount if orig.total_amount is not None else restored
                    orig.outstanding_amount = min(cap, restored)
                    orig.credited_amount = max(
                        Decimal("0"),
                        (orig.credited_amount or Decimal("0")) - (inv.total_amount or Decimal("0"))
                    )

            inv.is_cancelled = True
            inv.cancelled_reason = reason
            inv.cancelled_at = datetime.utcnow()
            inv.updated_by = user_id
            db.commit()
            audit(db, user_id, "cancel", "billing",
                  f"Reversed credit note {inv.invoice_number}. Reason: {reason}",
                  record_type="credit_note", record_id=inv.id,
                  old={"is_cancelled": False}, new={"is_cancelled": True})
            return {"message": "Credit note reversed", "invoice_number": inv.invoice_number}

        # 1) Reverse customer ledger
        if affects_accounting and inv.customer_id and (inv.total_amount or 0) > 0:
            BillingService._post_customer_ledger(
                db, inv.customer_id, TransactionType.credit,
                inv.total_amount, "invoice_cancellation", inv.id,
                f"Cancel {inv.invoice_number}: {reason[:80]}",
                date.today(), fy,
            )

        # 2) Reverse journal entry (DR/CR swapped)
        if affects_accounting and (inv.total_amount or 0) > 0:
            reverse_lines = [
                ("DEBTORS", TransactionType.credit, inv.total_amount),
                ("SALES",   TransactionType.debit,  inv.taxable_amount or Decimal("0")),
            ]
            cgst = inv.total_cgst or Decimal("0")
            sgst = inv.total_sgst or Decimal("0")
            igst = inv.total_igst or Decimal("0")
            if cgst > 0:
                reverse_lines.append(("GST_PAY", TransactionType.debit, cgst))
            if sgst > 0:
                reverse_lines.append(("GST_PAY", TransactionType.debit, sgst))
            if igst > 0:
                reverse_lines.append(("GST_PAY", TransactionType.debit, igst))
            # Mirror the original Round Off line so the reversal also balances
            round_off = inv.round_off or Decimal("0")
            if round_off > 0:
                reverse_lines.append(("ROUND_OFF", TransactionType.debit, round_off))
            elif round_off < 0:
                reverse_lines.append(("ROUND_OFF", TransactionType.credit, -round_off))
            BillingService._post_journal(
                db, date.today(), "invoice_cancellation", inv.id,
                f"Reverse {inv.invoice_number}: {reason[:80]}",
                fy, reverse_lines, user_id,
            )

        # 3) Restore stock for stock-affecting docs (skip quotation/credit_note)
        if affects_stock and doc_type_str != "delivery_challan":
            # b2b/b2c: items.fifo_cost was set on create. Add a stock layer back.
            for item in inv.items:
                if not item.quantity or item.quantity <= 0:
                    continue
                StockService.add_stock(
                    db, item.product_id, inv.warehouse_id,
                    item.quantity,
                    item.fifo_cost or item.unit_price or Decimal("0"),
                    StockTransactionType.return_in,
                    "invoice_cancellation", inv.id,
                    date.today(), user_id,
                )

        inv.is_cancelled = True
        inv.cancelled_reason = reason
        inv.cancelled_at = datetime.utcnow()
        inv.updated_by = user_id
        # Outstanding is now zero on a cancelled invoice
        inv.outstanding_amount = Decimal("0")
        db.commit()
        audit(db, user_id, "cancel", "billing",
              f"Cancelled invoice {inv.invoice_number}. Reason: {reason}",
              record_type="invoice", record_id=inv.id,
              old={"is_cancelled": False}, new={"is_cancelled": True})
        return {"message": "Invoice cancelled", "invoice_number": inv.invoice_number}

    @staticmethod
    def convert_quotation(db: Session, quotation_id: int, user_id: int,
                          user_role: str) -> dict:
        """Convert a quotation to a B2B/B2C invoice."""
        quot = db.query(Invoice).filter(Invoice.id == quotation_id).first()
        if not quot:
            raise HTTPException(status_code=404, detail="Quotation not found")
        # str() handles both enum and raw string stored in DB
        if str(quot.document_type) not in ("quotation", "DocumentType.quotation"):
            raise HTTPException(status_code=400, detail=f"Document is not a quotation (type={quot.document_type})")
        if getattr(quot, "quotation_status", None) == "invoiced":
            raise HTTPException(status_code=400, detail="Quotation already converted to invoice")
        if quot.is_cancelled:
            raise HTTPException(status_code=400, detail="Cannot convert a cancelled quotation")

        # Determine document type based on customer GSTIN
        cust = db.query(Customer).filter(Customer.id == quot.customer_id).first()
        doc_type = "b2b_invoice" if (cust and cust.gstin) else "b2c_invoice"

        # Get default warehouse
        from app.models.models import Warehouse
        warehouse = db.query(Warehouse).filter(Warehouse.is_active == True).first()
        if not warehouse:
            raise HTTPException(status_code=400, detail="No active warehouse found")

        # Get billing/shipping addresses — use customer's first address if not set
        billing_addr_id = quot.billing_address_id
        shipping_addr_id = quot.shipping_address_id
        if not billing_addr_id:
            from app.models.models import CustomerAddress
            addr = db.query(CustomerAddress).filter(
                CustomerAddress.customer_id == quot.customer_id
            ).first()
            if addr:
                billing_addr_id = addr.id
                shipping_addr_id = addr.id

        # Build InvoiceCreate-like payload from quotation
        from app.schemas.billing import InvoiceCreate, InvoiceItemCreate
        items = []
        for item in quot.items:
            # Use the quotation item's HSN as-is if it's valid (4/6/8 digits),
            # otherwise fall back to the product's HSN. The old code padded
            # invalid HSNs with zeros which produced nonsense values like
            # "123400". InvoiceItemCreate's validator will reject anything
            # not matching the rule, so we feed it None rather than garbage.
            def _valid_hsn(h):
                if h and h.isdigit() and len(h) in (4, 6, 8):
                    return h
                return None
            hsn = _valid_hsn(item.hsn_code)
            if hsn is None:
                prod = db.query(Product).filter(Product.id == item.product_id).first()
                hsn = _valid_hsn(prod.hsn_code) if prod else None
            items.append(InvoiceItemCreate(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price or Decimal("0"),
                discount_percent=item.discount_percent or Decimal("0"),
                gst_percent=item.gst_percent or Decimal("0"),
                hsn_code=hsn,
            ))

        if not items:
            raise HTTPException(status_code=400, detail="Quotation has no line items to convert")

        payload = InvoiceCreate(
            customer_id=quot.customer_id,
            document_type=doc_type,
            warehouse_id=warehouse.id,
            billing_address_id=billing_addr_id or 0,
            shipping_address_id=shipping_addr_id or 0,
            invoice_date=date.today(),
            invoice_discount=Decimal("0"),
            notes=f"Converted from Quotation {quot.invoice_number}",
            terms_conditions=quot.terms_conditions,
            items=items,
        )

        # Create the invoice with the caller's actual role. Previously this
        # was hardcoded to "admin", which let non-admin users bypass the
        # floor-price check during quotation conversion.
        new_inv = BillingService.create(db, payload, user_id, user_role)

        # Mark quotation as invoiced and link
        try:
            quot.quotation_status = "invoiced"
        except Exception:
            pass
        quot.original_invoice_id = new_inv["id"]
        db.commit()

        return {**new_inv, "quotation_id": quotation_id}

    @staticmethod
    def create_credit_note(db: Session, payload: CreditNoteCreate,
                           user_id: int, user_role: str) -> dict:
        original = db.query(Invoice).filter(
            Invoice.id == payload.original_invoice_id, Invoice.is_cancelled == False
        ).first()
        if not original:
            raise HTTPException(status_code=404, detail="Original invoice not found")
        if payload.return_date < original.invoice_date:
            raise HTTPException(
                status_code=400,
                detail="Return date cannot be before the original invoice date",
            )

        # Build a map of already-returned qty per original invoice_item_id across
        # all non-cancelled credit notes against this invoice.
        existing_cn_ids = db.query(Invoice.id).filter(
            Invoice.original_invoice_id == payload.original_invoice_id,
            Invoice.document_type == DocumentType.credit_note,
            Invoice.is_cancelled == False,
        ).subquery()
        returned_rows = (
            db.query(InvoiceItem.original_item_id, func.sum(InvoiceItem.quantity))
            .filter(
                InvoiceItem.invoice_id.in_(existing_cn_ids),
                InvoiceItem.original_item_id.isnot(None),
            )
            .group_by(InvoiceItem.original_item_id)
            .all()
        )
        already_returned: dict = {row[0]: Decimal(str(row[1])) for row in returned_rows}

        # Accumulate within-payload quantities so duplicate item_ids in one
        # request don't each individually pass the check but together over-return.
        payload_qty: dict = {}
        for ret_item in payload.items:
            payload_qty[ret_item.invoice_item_id] = (
                payload_qty.get(ret_item.invoice_item_id, Decimal("0")) + ret_item.quantity
            )

        # Validate each requested return line before touching the DB.
        # Use payload_qty (combined) so duplicate item_ids in one request are
        # checked as a single total, not individually.
        seen_item_ids: set = set()
        for ret_item in payload.items:
            if ret_item.invoice_item_id in seen_item_ids:
                continue  # already validated the combined qty for this item
            seen_item_ids.add(ret_item.invoice_item_id)

            orig_item = db.query(InvoiceItem).filter(
                InvoiceItem.id == ret_item.invoice_item_id,
                InvoiceItem.invoice_id == payload.original_invoice_id,
            ).first()
            if not orig_item:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invoice item {ret_item.invoice_item_id} not found on invoice {payload.original_invoice_id}",
                )
            orig_qty = Decimal(str(orig_item.quantity or 0))
            prev_returned = already_returned.get(orig_item.id, Decimal("0"))
            available = orig_qty - prev_returned
            total_requested = payload_qty[ret_item.invoice_item_id]
            if total_requested > available:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot return {total_requested} units for item "
                        f"{ret_item.invoice_item_id}: only {available} units available to return"
                    ),
                )

        fy = get_financial_year(payload.return_date)
        cn_number = InvoiceNumberingService.get_next_number(db, DocumentType.credit_note, fy)

        credit_note = Invoice(
            invoice_number=cn_number,
            document_type=DocumentType.credit_note,
            customer_id=original.customer_id,
            warehouse_id=original.warehouse_id,
            billing_address_id=original.billing_address_id,
            shipping_address_id=original.shipping_address_id,
            invoice_date=payload.return_date,
            gst_type=original.gst_type,
            place_of_supply=original.place_of_supply,
            financial_year=fy,
            original_invoice_id=payload.original_invoice_id,
            notes=payload.notes,
            created_by=user_id,
        )
        db.add(credit_note)
        db.flush()

        total_taxable = Decimal("0")
        total_cgst = Decimal("0")
        total_sgst = Decimal("0")
        total_igst = Decimal("0")
        total = Decimal("0")
        for ret_item in payload.items:
            orig_item = db.query(InvoiceItem).filter(InvoiceItem.id == ret_item.invoice_item_id).first()
            if not orig_item:
                continue  # already validated above; defensive guard only
            # Returned line — taxable = unit_price * returned_qty (no per-line
            # discount applied to returns; matches the existing simplification).
            taxable = (orig_item.unit_price * ret_item.quantity).quantize(Decimal("0.01"))

            # Reverse the GST that was charged on the original line, prorated
            # to the returned quantity. This is required for GST returns —
            # without it, output GST liability stays inflated by returns.
            cgst_pct = orig_item.cgst_percent or Decimal("0")
            sgst_pct = orig_item.sgst_percent or Decimal("0")
            igst_pct = orig_item.igst_percent or Decimal("0")
            cgst_amt = (taxable * cgst_pct / Decimal("100")).quantize(Decimal("0.01"))
            sgst_amt = (taxable * sgst_pct / Decimal("100")).quantize(Decimal("0.01"))
            igst_amt = (taxable * igst_pct / Decimal("100")).quantize(Decimal("0.01"))
            line_total = (taxable + cgst_amt + sgst_amt + igst_amt).quantize(Decimal("0.01"))

            total_taxable += taxable
            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt
            total += line_total

            cn_item = InvoiceItem(
                invoice_id=credit_note.id,
                product_id=orig_item.product_id,
                original_item_id=orig_item.id,
                quantity=ret_item.quantity,
                unit_price=orig_item.unit_price,
                discount_percent=orig_item.discount_percent,
                discount_amount=Decimal("0"),
                taxable_amount=taxable,
                gst_percent=orig_item.gst_percent,
                cgst_percent=cgst_pct,
                sgst_percent=sgst_pct,
                igst_percent=igst_pct,
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                line_total=line_total,
                hsn_code=orig_item.hsn_code,
            )
            db.add(cn_item)

            # Reverse stock (FIFO reversal — add back to warehouse)
            StockService.add_stock(
                db, orig_item.product_id, original.warehouse_id,
                ret_item.quantity, orig_item.fifo_cost or orig_item.unit_price,
                StockTransactionType.return_in, "credit_note", credit_note.id,
                payload.return_date, user_id
            )

        # Round the credit-note total to the nearest rupee, mirroring invoices
        rounded_total, round_off = BillingService._round_to_rupee(total)

        credit_note.subtotal = total_taxable
        credit_note.taxable_amount = total_taxable
        credit_note.total_cgst = total_cgst
        credit_note.total_sgst = total_sgst
        credit_note.total_igst = total_igst
        credit_note.round_off = round_off
        credit_note.total_amount = rounded_total
        credit_note.outstanding_amount = Decimal("0")
        credit_note.paid_amount = Decimal("0")

        # Credit customer ledger
        BillingService._post_customer_ledger(
            db, original.customer_id, TransactionType.credit,
            rounded_total, "credit_note", credit_note.id,
            f"Credit note {cn_number} against {original.invoice_number}",
            payload.return_date, fy
        )

        # Double-entry reversal of the original sale so output-GST liability
        # (GST_PAY) and SALES are actually reduced in the ledger — not just the
        # customer subledger. Mirrors the invoice journal with DR/CR swapped:
        # DR Sales, DR GST Payable, CR Debtors, +/- Round Off.
        cn_journal = [
            ("DEBTORS", TransactionType.credit, rounded_total),
            ("SALES", TransactionType.debit, total_taxable),
        ]
        if total_cgst > 0:
            cn_journal.append(("GST_PAY", TransactionType.debit, total_cgst.quantize(Decimal("0.01"))))
        if total_sgst > 0:
            cn_journal.append(("GST_PAY", TransactionType.debit, total_sgst.quantize(Decimal("0.01"))))
        if total_igst > 0:
            cn_journal.append(("GST_PAY", TransactionType.debit, total_igst.quantize(Decimal("0.01"))))
        if round_off > 0:
            cn_journal.append(("ROUND_OFF", TransactionType.debit, round_off))
        elif round_off < 0:
            cn_journal.append(("ROUND_OFF", TransactionType.credit, -round_off))
        BillingService._post_journal(
            db, payload.return_date, "credit_note", credit_note.id,
            f"Credit note {cn_number} against {original.invoice_number}",
            fy, cn_journal, user_id
        )

        # Update original invoice outstanding and credited totals
        original.outstanding_amount = max(
            Decimal("0"),
            original.outstanding_amount - rounded_total
        )
        original.credited_amount = (original.credited_amount or Decimal("0")) + rounded_total

        db.commit()
        audit(db, user_id, "create", "billing",
              f"Created credit note {cn_number} against {original.invoice_number} "
              f"— ₹{rounded_total}",
              record_type="credit_note", record_id=credit_note.id)
        return BillingService.get_by_id(db, credit_note.id)

    @staticmethod
    def _send_invoice_email(customer, invoice):
        """Send invoice notification email to customer."""
        pass  # Implemented when email service is configured

    @staticmethod
    def get_whatsapp_url(invoice_id: int, db: Session) -> dict:
        """Generate WhatsApp Web share URL for an invoice."""
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        cust = db.query(Customer).filter(Customer.id == inv.customer_id).first()
        phone = cust.phone.replace("+", "").replace("-", "").replace(" ", "") if cust and cust.phone else ""
        msg = (
            f"Dear {cust.trade_name if cust else 'Customer'},%0A%0A"
            f"Please find your invoice {inv.invoice_number} "
            f"dated {inv.invoice_date} "
            f"for ₹{fmt_inr(inv.total_amount)}.%0A%0A"
            f"Outstanding amount: ₹{fmt_inr(inv.outstanding_amount)}%0A%0A"
            f"Thank you for your business.%0A{settings.COMPANY_NAME}"
        )
        url = f"https://wa.me/{phone}?text={msg}"
        return {"whatsapp_url": url, "phone": phone, "message": msg}


class CustomerPaymentService:

    @staticmethod
    def create(db: Session, payload: CustomerPaymentCreate, user_id: int) -> dict:
        customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        fy = get_financial_year(payload.payment_date)
        # Atomic row-locked counter — replaces unsafe count()+1.
        # Seed from existing customer_payments.payment_number suffix so first
        # call doesn't collide with legacy data.
        seq = next_sequence_number(
            db, "customer_payment", "RCP", fy,
            seed_from=lambda d, f: _seed_from_suffix(d, f, "customer_payments", "payment_number"),
        )
        payment_number = f"RCP-{fy.replace('-','')}-{seq:04d}"

        payment = CustomerPayment(
            payment_number=payment_number,
            customer_id=payload.customer_id,
            invoice_id=payload.invoice_id,
            payment_date=payload.payment_date,
            amount=payload.amount,
            payment_mode=payload.payment_mode,
            reference_number=payload.reference_number,
            notes=payload.notes,
            is_advance=payload.is_advance,
            financial_year=fy,
            created_by=user_id,
        )
        db.add(payment)
        db.flush()

        net_amount = payload.amount - getattr(payload, 'tds_amount', Decimal("0"))

        # Update invoice outstanding using FIFO
        print(f"[FIFO] payment={payload.amount} invoice_id={payload.invoice_id} is_advance={payload.is_advance} customer_id={payload.customer_id}")
        if not payload.is_advance:
            remaining = net_amount
            print(f"[FIFO] remaining={remaining}")

            if payload.invoice_id:
                # Pay the linked invoice first
                inv = db.query(Invoice).filter(Invoice.id == payload.invoice_id).first()
                if inv:
                    stored_paid = Decimal(str(inv.paid_amount or 0))
                    total = Decimal(str(inv.total_amount or 0))
                    actual_outstanding = max(Decimal("0"), total - stored_paid)
                    apply = min(remaining, actual_outstanding)
                    inv.paid_amount = stored_paid + apply
                    inv.outstanding_amount = max(Decimal("0"), actual_outstanding - apply)
                    remaining -= apply
                    db.flush()
                    print(f"[FIFO] Direct: inv {inv.id} apply={apply} remaining={remaining}")

            if payload.customer_id and remaining > Decimal("0"):
                # FIFO: apply remaining to oldest unpaid invoices
                all_invoices = db.query(Invoice).filter(
                    Invoice.customer_id == payload.customer_id,
                    Invoice.is_cancelled == False,
                ).filter(
                    func.lower(Invoice.document_type).in_(["b2b_invoice", "b2c_invoice"])
                ).order_by(Invoice.invoice_date.asc(), Invoice.id.asc()).all()

                # Skip already-paid invoice (handled above)
                fifo_ids = [i.id for i in all_invoices
                            if not payload.invoice_id or i.id != payload.invoice_id]
                fifo_invoices = [i for i in all_invoices
                                 if not payload.invoice_id or i.id != payload.invoice_id]

                # Batch-fetch linked payments
                paid_rows = db.query(
                    CustomerPayment.invoice_id,
                    func.sum(CustomerPayment.amount).label("paid")
                ).filter(
                    CustomerPayment.invoice_id.in_(fifo_ids)
                ).group_by(CustomerPayment.invoice_id).all() if fifo_ids else []
                paid_lookup = {r.invoice_id: Decimal(str(r.paid)) for r in paid_rows}

                print(f"[FIFO] FIFO invoices: {[i.id for i in fifo_invoices]}")
                for inv in fifo_invoices:
                    if remaining <= Decimal("0"):
                        break
                    total = Decimal(str(inv.total_amount or 0))
                    stored_paid = Decimal(str(inv.paid_amount or 0))
                    linked_paid = paid_lookup.get(inv.id, Decimal("0"))
                    already_paid = max(stored_paid, linked_paid)
                    actual_outstanding = max(Decimal("0"), total - already_paid)
                    print(f"[FIFO] inv {inv.id}: total={total} already_paid={already_paid} outstanding={actual_outstanding} remaining={remaining}")
                    if actual_outstanding <= Decimal("0"):
                        continue
                    apply = min(remaining, actual_outstanding)
                    inv.paid_amount = already_paid + apply
                    inv.outstanding_amount = max(Decimal("0"), actual_outstanding - apply)
                    remaining -= apply
                    print(f"[FIFO] Applied {apply} to inv {inv.id}, remaining={remaining}")

                db.flush()

        # Customer ledger credit
        BillingService._post_customer_ledger(
            db, payload.customer_id, TransactionType.credit,
            net_amount, "payment", payment.id,
            f"Receipt {payment_number} {'(Advance)' if payload.is_advance else ''}",
            payload.payment_date, fy
        )

        # Journal
        pay_acc = "CASH" if str(payload.payment_mode).lower() == "cash" else "BANK"
        BillingService._post_journal(
            db, payload.payment_date, "customer_payment", payment.id,
            f"Receipt from {customer.trade_name if customer else 'Customer'}",
            fy,
            [
                (pay_acc, TransactionType.debit, net_amount),
                ("DEBTORS", TransactionType.credit, net_amount),
            ],
            user_id
        )

        db.commit()
        db.refresh(payment)
        audit(db, user_id, "payment", "billing",
              f"Receipt {payment.payment_number} of ₹{payment.amount} from "
              f"{customer.trade_name} via {payload.payment_mode}"
              + (" (advance)" if payment.is_advance else ""),
              record_type="customer_payment", record_id=payment.id)
        return {
            "id": payment.id, "payment_number": payment.payment_number,
            "customer_id": payment.customer_id, "customer_name": customer.trade_name,
            "invoice_id": payment.invoice_id,
            "payment_date": payment.payment_date, "amount": payment.amount,
            "payment_mode": payment.payment_mode, "is_advance": payment.is_advance,
            "financial_year": payment.financial_year, "created_at": payment.created_at,
        }

    @staticmethod
    def list_payments(db: Session, customer_id: Optional[int] = None,
                      page: int = 1, page_size: int = 20) -> dict:
        q = db.query(CustomerPayment)
        if customer_id:
            q = q.filter(CustomerPayment.customer_id == customer_id)
        result = paginate(q.order_by(desc(CustomerPayment.payment_date), desc(CustomerPayment.id)), page, page_size)
        items = []
        for p in result["items"]:
            c = db.query(Customer).filter(Customer.id == p.customer_id).first()
            items.append({
                "id": p.id, "payment_number": p.payment_number,
                "customer_id": p.customer_id,
                "customer_name": c.trade_name if c else None,
                "invoice_id": p.invoice_id,
                "payment_date": p.payment_date, "amount": p.amount,
                "payment_mode": p.payment_mode, "is_advance": p.is_advance,
                "financial_year": p.financial_year, "created_at": p.created_at,
                "reference_number": p.reference_number, "notes": p.notes,
            })
        result["items"] = items
        return result
