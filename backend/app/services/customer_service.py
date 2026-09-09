from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi import HTTPException
from decimal import Decimal
from typing import Optional
import csv
import io
import httpx

from app.models.models import (
    Customer, CustomerAddress, LedgerEntry, TransactionType,
    CustomerPayment, Invoice
)
from app.schemas.billing import CustomerCreate, CustomerUpdate, CustomerAddressCreate
from app.utils.helpers import paginate, derive_state_code, resolve_state_code
from app.utils.csv_import import clean, parse_decimal, parse_int, parse_bool
from app.services.audit import audit, diff
from app.core.config import settings


class CustomerService:

    @staticmethod
    def _get_outstanding(db: Session, customer_id: int) -> Decimal:
        # Exclude BOTH the original invoice ledger entry AND its B-1 reversal
        # entry for cancelled invoices. Excluding only one side would
        # double-count: the reversal credit subtracts the invoice value once,
        # and exclusion of the original debit subtracts it a second time.
        # Excluding both cancels the invoice's effect to zero either way:
        #   - Post-B-1 cancellation: debit and credit both excluded -> 0 net
        #   - Legacy cancellation (no reversal): only debit excluded -> 0 net
        invoice_subq = db.query(Invoice.id).filter(
            Invoice.is_cancelled == True
        ).subquery()
        base = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.customer_id == customer_id,
            ~(
                LedgerEntry.reference_type.in_(("invoice", "invoice_cancellation"))
                & (LedgerEntry.reference_id.in_(invoice_subq))
            ),
        )
        debits = base.filter(LedgerEntry.transaction_type == TransactionType.debit).scalar() or Decimal("0")
        credits = base.filter(LedgerEntry.transaction_type == TransactionType.credit).scalar() or Decimal("0")
        return debits - credits

    @staticmethod
    def list_customers(db: Session, page: int = 1, page_size: int = 20,
                       search: Optional[str] = None,
                       is_active: Optional[bool] = True) -> dict:
        q = db.query(Customer)
        if is_active is not None:
            q = q.filter(Customer.is_active == is_active)
        if search:
            q = q.filter(
                (Customer.trade_name.ilike(f"%{search}%")) |
                (Customer.gstin.ilike(f"%{search}%")) |
                (Customer.phone.ilike(f"%{search}%"))
            )
        result = paginate(q.order_by(Customer.trade_name), page, page_size)
        items = []
        for c in result["items"]:
            items.append({
                "id": c.id, "trade_name": c.trade_name, "gstin": c.gstin,
                "state": c.state, "phone": c.phone, "credit_limit": c.credit_limit,
                "is_active": c.is_active, "is_b2b": c.is_b2b,
                "outstanding_balance": CustomerService._get_outstanding(db, c.id),
            })
        result["items"] = items
        return result

    @staticmethod
    def get_by_id(db: Session, customer_id: int) -> dict:
        c = db.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")
        return {
            "id": c.id, "trade_name": c.trade_name, "legal_name": c.legal_name,
            "gstin": c.gstin, "business_type": c.business_type,
            "gst_status": c.gst_status, "state": c.state, "state_code": c.state_code,
            "phone": c.phone, "email": c.email, "contact_person": c.contact_person,
            "credit_limit": c.credit_limit, "credit_days": c.credit_days,
            "is_b2b": c.is_b2b, "is_active": c.is_active, "created_at": c.created_at,
            "addresses": [
                {"id": a.id, "label": a.label, "address_line1": a.address_line1,
                 "address_line2": a.address_line2, "city": a.city, "state": a.state,
                 "state_code": a.state_code, "pincode": a.pincode,
                 "contact_person": a.contact_person, "phone": a.phone,
                 "address_type": a.address_type,
                 "is_preferred_billing": a.is_preferred_billing,
                 "is_preferred_shipping": a.is_preferred_shipping,
                 "customer_id": a.customer_id}
                for a in c.addresses
            ],
            "outstanding_balance": CustomerService._get_outstanding(db, c.id),
        }

    @staticmethod
    def create(db: Session, payload: CustomerCreate, user_id: int) -> dict:
        if payload.gstin:
            existing = db.query(Customer).filter(Customer.gstin == payload.gstin).first()
            if existing:
                raise HTTPException(status_code=400, detail="Customer with this GSTIN already exists")
        c = Customer(**payload.dict(), created_by=user_id)
        # Keep state_code in sync for GST determination (GSTIN prefix > name).
        if c.state_code is None:
            c.state_code = derive_state_code(c.gstin, c.state)
        db.add(c)
        db.commit()
        db.refresh(c)
        audit(db, user_id, "create", "billing",
              f"Created customer {c.trade_name}"
              + (f" (GSTIN {c.gstin})" if c.gstin else ""),
              record_type="customer", record_id=c.id)
        return CustomerService.get_by_id(db, c.id)

    # ── Bulk CSV import ───────────────────────────────────────
    IMPORT_COLUMNS = [
        "trade_name", "legal_name", "gstin", "gst_status", "is_b2b",
        "phone", "email", "contact_person", "credit_limit", "credit_days",
        "state", "addr_label", "address_line1", "address_line2",
        "city", "addr_state", "pincode",
    ]

    @staticmethod
    def get_import_csv_template() -> str:
        sample = [
            "Kumar Traders", "Kumar Traders Pvt Ltd", "29ABCDE1234F1Z5", "Registered", "TRUE",
            "9845012345", "kumar@example.com", "Anil Kumar", "100000.00", "30",
            "Karnataka", "Billing", "23 Market Rd", "", "Bengaluru", "Karnataka", "560002",
        ]
        return "\n".join([",".join(CustomerService.IMPORT_COLUMNS), ",".join(sample)])

    @staticmethod
    def bulk_import(db: Session, file_content: str, user_id: int) -> dict:
        """Bulk-create customers from CSV.

        Required column: trade_name. A row whose gstin already exists is skipped
        and reported (not an error). If address_line1 is given, a preferred
        billing address is created alongside (city/addr_state/pincode required).
        Each valid row commits via its own SAVEPOINT — one bad row never poisons
        the batch.
        """
        reader = csv.DictReader(io.StringIO(file_content))
        if "trade_name" not in set(reader.fieldnames or []):
            raise HTTPException(status_code=400, detail="Missing required column: trade_name")

        errors, created, skipped = [], [], []
        rows = list(reader)

        for idx, row in enumerate(rows, start=2):
            row_errors = []
            trade_name = (row.get("trade_name") or "").strip()
            if not trade_name:
                row_errors.append("trade_name is required")

            gstin = (row.get("gstin") or "").strip().upper() or None
            try:
                credit_limit = parse_decimal(row.get("credit_limit"))
            except Exception:
                row_errors.append(f"Invalid credit_limit: '{row.get('credit_limit')}'")
            try:
                credit_days = parse_int(row.get("credit_days"))
            except Exception:
                row_errors.append(f"Invalid credit_days: '{row.get('credit_days')}'")
            try:
                is_b2b = parse_bool(row.get("is_b2b"), default=True)
            except Exception as e:
                row_errors.append(f"is_b2b: {e}")

            if row_errors:
                errors.append({"row": idx, "data": trade_name, "errors": row_errors})
                continue

            if gstin and db.query(Customer).filter(Customer.gstin == gstin).first():
                skipped.append({"row": idx, "data": trade_name,
                                "reason": f"GSTIN {gstin} already exists"})
                continue

            try:
                with db.begin_nested():
                    c = Customer(
                        trade_name=trade_name,
                        legal_name=clean(row.get("legal_name")),
                        gstin=gstin,
                        gst_status=clean(row.get("gst_status")),
                        state=clean(row.get("state")),
                        state_code=derive_state_code(gstin, clean(row.get("state"))),
                        phone=clean(row.get("phone")),
                        email=clean(row.get("email")),
                        contact_person=clean(row.get("contact_person")),
                        credit_limit=credit_limit,
                        credit_days=credit_days,
                        is_b2b=is_b2b,
                        created_by=user_id,
                    )
                    db.add(c)
                    db.flush()

                    line1 = (row.get("address_line1") or "").strip()
                    if line1:
                        city = (row.get("city") or "").strip()
                        astate = (row.get("addr_state") or "").strip()
                        pincode = (row.get("pincode") or "").strip()
                        missing = [n for n, v in (("city", city), ("addr_state", astate),
                                                  ("pincode", pincode)) if not v]
                        if missing:
                            raise ValueError(f"address needs {', '.join(missing)}")
                        db.add(CustomerAddress(
                            customer_id=c.id,
                            label=(row.get("addr_label") or "Billing").strip(),
                            address_line1=line1,
                            address_line2=clean(row.get("address_line2")),
                            city=city, state=astate,
                            state_code=resolve_state_code(astate),
                            pincode=pincode,
                            is_preferred_billing=True,
                            is_preferred_shipping=True,
                            created_by=user_id,
                        ))
                created.append(trade_name)
            except Exception as e:
                errors.append({"row": idx, "data": trade_name, "errors": [str(e)]})

        db.commit()
        return {
            "total_rows": len(rows),
            "success_count": len(created),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def update(db: Session, customer_id: int, payload: CustomerUpdate, user_id: int) -> dict:
        c = db.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")
        data = payload.dict(exclude_none=True)
        # GSTIN is unique — block editing onto another customer's GSTIN.
        if data.get("gstin") and data["gstin"] != c.gstin:
            clash = db.query(Customer).filter(
                Customer.gstin == data["gstin"], Customer.id != customer_id
            ).first()
            if clash:
                raise HTTPException(status_code=400, detail="Customer with this GSTIN already exists")
        old = {f: getattr(c, f, None) for f in data.keys()}
        for field, value in data.items():
            setattr(c, field, value)
        # Re-derive state_code when GSTIN/state changed without an explicit code.
        if ("gstin" in data or "state" in data) and "state_code" not in data:
            rc = derive_state_code(c.gstin, c.state)
            if rc is not None:
                c.state_code = rc
        c.updated_by = user_id
        db.commit()
        new = {f: getattr(c, f, None) for f in data.keys()}
        changed, summary = diff(old, new, list(data.keys()))
        if changed:
            audit(db, user_id, "update", "billing",
                  f"Updated customer {c.trade_name}: {summary}",
                  record_type="customer", record_id=c.id,
                  old={k: val[0] for k, val in changed.items()},
                  new={k: val[1] for k, val in changed.items()})
        return CustomerService.get_by_id(db, customer_id)

    @staticmethod
    def add_address(db: Session, customer_id: int,
                    payload: CustomerAddressCreate, user_id: int) -> dict:
        c = db.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")
        addr = CustomerAddress(customer_id=customer_id, **payload.dict(), created_by=user_id)
        if addr.state_code is None:
            addr.state_code = resolve_state_code(addr.state)
        db.add(addr)
        db.commit()
        db.refresh(addr)
        return {
            "id": addr.id, "label": addr.label, "city": addr.city,
            "state": addr.state, "pincode": addr.pincode,
            "customer_id": addr.customer_id,
            "address_line1": addr.address_line1,
        }

    @staticmethod
    def update_address(db: Session, customer_id: int, address_id: int,
                       payload: CustomerAddressCreate, user_id: int) -> dict:
        addr = db.query(CustomerAddress).filter(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id,
        ).first()
        if not addr:
            raise HTTPException(status_code=404, detail="Address not found")
        data = payload.dict()
        for field, value in data.items():
            setattr(addr, field, value)
        if addr.state_code is None:
            addr.state_code = resolve_state_code(addr.state)
        addr.updated_by = user_id
        db.commit()
        db.refresh(addr)
        return {
            "id": addr.id, "label": addr.label, "city": addr.city,
            "state": addr.state, "pincode": addr.pincode,
            "customer_id": addr.customer_id,
            "address_line1": addr.address_line1,
        }

    @staticmethod
    def bulk_set_status(db: Session, customer_ids: list, is_active: bool,
                        user_id: int) -> dict:
        customers = db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
        updated = 0
        for c in customers:
            if c.is_active == is_active:
                continue
            c.is_active = is_active
            c.updated_by = user_id
            updated += 1
        if updated:
            db.commit()
            audit(db, user_id, "update", "billing",
                  f"Bulk set {updated} customer(s) to "
                  f"{'active' if is_active else 'inactive'}",
                  record_type="customer", record_id=None)
        return {"updated": updated, "is_active": is_active}

    @staticmethod
    def get_ledger(db: Session, customer_id: int,
                   page: int = 1, page_size: int = 50) -> dict:
        c = db.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")
        q = db.query(LedgerEntry).filter(LedgerEntry.customer_id == customer_id)\
              .order_by(desc(LedgerEntry.entry_date))
        result = paginate(q, page, page_size)
        result["customer_name"] = c.trade_name
        result["outstanding_balance"] = CustomerService._get_outstanding(db, customer_id)
        result["credit_limit"] = c.credit_limit
        result["credit_days"] = c.credit_days
        return result

    @staticmethod
    async def fetch_gstin_details(gstin: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.GSTIN_LOOKUP_URL}{gstin}",
                    headers={"x-cleartax-auth-token": settings.GSTIN_LOOKUP_TOKEN}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pradr = data.get("pradr", {}).get("addr", {})
                    return {
                        "trade_name": data.get("tradeNam", ""),
                        "legal_name": data.get("lgnm", ""),
                        "business_type": data.get("dty", ""),
                        "gst_status": data.get("sts", ""),
                        "state": pradr.get("stcd", ""),
                        "address_line1": pradr.get("bnm", ""),
                        "city": pradr.get("dst", ""),
                        "pincode": pradr.get("pncd", ""),
                        "registration_date": data.get("rgdt", ""),
                        "nature_of_business": ", ".join(data.get("nba", [])),
                    }
        except Exception:
            pass
        return {"error": "Could not fetch GSTIN details. Please enter manually."}

    @staticmethod
    def get_last_price(db: Session, customer_id: int, product_id: int) -> Optional[Decimal]:
        """Get last price billed to this customer for this product.

        Filters to actual sales (b2b_invoice / b2c_invoice). Quotations and
        credit notes are excluded — a high-priced quotation that never
        converted shouldn't masquerade as a real billed price.
        """
        from app.models.models import InvoiceItem, Invoice
        result = db.query(InvoiceItem.unit_price).join(Invoice).filter(
            Invoice.customer_id == customer_id,
            InvoiceItem.product_id == product_id,
            Invoice.is_cancelled == False,
            func.lower(Invoice.document_type).in_(["b2b_invoice", "b2c_invoice"]),
        ).order_by(desc(Invoice.invoice_date)).first()
        return result[0] if result else None

    @staticmethod
    def generate_statement(db: Session, customer_id: int,
                           date_from, date_to) -> dict:
        """Generate customer statement of account."""
        c = db.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")

        entries = db.query(LedgerEntry).filter(
            LedgerEntry.customer_id == customer_id,
            LedgerEntry.entry_date >= date_from,
            LedgerEntry.entry_date <= date_to,
        ).order_by(LedgerEntry.entry_date).all()

        # Opening balance before date_from
        opening_debit = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.customer_id == customer_id,
            LedgerEntry.transaction_type == TransactionType.debit,
            LedgerEntry.entry_date < date_from,
        ).scalar() or Decimal("0")
        opening_credit = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.customer_id == customer_id,
            LedgerEntry.transaction_type == TransactionType.credit,
            LedgerEntry.entry_date < date_from,
        ).scalar() or Decimal("0")
        opening_balance = opening_debit - opening_credit

        return {
            "customer": {"id": c.id, "name": c.trade_name, "gstin": c.gstin,
                         "phone": c.phone, "email": c.email},
            "period": {"from": date_from, "to": date_to},
            "opening_balance": opening_balance,
            "entries": [
                {
                    "date": e.entry_date,
                    "narration": e.narration,
                    "debit": e.amount if e.transaction_type == TransactionType.debit else Decimal("0"),
                    "credit": e.amount if e.transaction_type == TransactionType.credit else Decimal("0"),
                    "balance": e.balance,
                }
                for e in entries
            ],
            "closing_balance": CustomerService._get_outstanding(db, customer_id),
        }
