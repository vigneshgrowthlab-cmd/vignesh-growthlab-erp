from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case
from fastapi import HTTPException
from decimal import Decimal
from typing import Optional, List
import csv
import io
import httpx

from app.models.models import (
    Vendor, VendorAddress, LedgerEntry, TransactionType,
    VendorPayment, Purchase
)
from app.schemas.purchase import (
    VendorCreate, VendorUpdate, VendorAddressCreate, _validate_gstin,
)
from app.utils.helpers import paginate, get_current_fy, derive_state_code, resolve_state_code
from app.utils.csv_import import clean, parse_int
from app.services.audit import audit, diff
from app.core.config import settings


class VendorService:

    @staticmethod
    def _get_outstanding(db: Session, vendor_id: int) -> Decimal:
        result = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.vendor_id == vendor_id,
            LedgerEntry.transaction_type == TransactionType.credit
        ).scalar() or Decimal("0")
        paid = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.vendor_id == vendor_id,
            LedgerEntry.transaction_type == TransactionType.debit
        ).scalar() or Decimal("0")
        return result - paid

    @staticmethod
    def _total_outstanding_all(db: Session) -> Decimal:
        """Company-wide payable across ALL vendors, independent of any list
        filter. Computed per vendor as (Σ credit − Σ debit) in one grouped
        ledger query, then summing only vendors that still owe (balance > 0) —
        vendors carrying a credit/advance balance are not netted off.
        """
        balance = func.sum(case(
            (LedgerEntry.transaction_type == TransactionType.credit, LedgerEntry.amount),
            else_=-LedgerEntry.amount,
        )).label("balance")
        rows = db.query(LedgerEntry.vendor_id, balance).group_by(LedgerEntry.vendor_id).all()
        total = Decimal("0")
        for r in rows:
            bal = Decimal(str(r.balance or 0))
            if bal > 0:
                total += bal
        return total

    @staticmethod
    def list_vendors(db: Session, page: int = 1, page_size: int = 20,
                     search: Optional[str] = None, is_active: Optional[bool] = True) -> dict:
        q = db.query(Vendor)
        if is_active is not None:
            q = q.filter(Vendor.is_active == is_active)
        if search:
            q = q.filter(
                (Vendor.trade_name.ilike(f"%{search}%")) |
                (Vendor.gstin.ilike(f"%{search}%"))
            )
        result = paginate(q.order_by(Vendor.trade_name), page, page_size)
        items = []
        for v in result["items"]:
            items.append({
                "id": v.id, "trade_name": v.trade_name, "gstin": v.gstin,
                "state": v.state, "phone": v.phone, "is_active": v.is_active,
                "outstanding_balance": VendorService._get_outstanding(db, v.id),
            })
        result["items"] = items
        # Company-wide payable, independent of the search / is_active filters.
        result["total_outstanding_all"] = VendorService._total_outstanding_all(db)
        return result

    @staticmethod
    def get_by_id(db: Session, vendor_id: int) -> dict:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found")
        return {
            "id": v.id, "trade_name": v.trade_name, "legal_name": v.legal_name,
            "gstin": v.gstin, "business_type": v.business_type, "gst_status": v.gst_status,
            "state": v.state, "state_code": v.state_code, "phone": v.phone,
            "email": v.email, "contact_person": v.contact_person,
            "bank_name": v.bank_name, "bank_account": v.bank_account,
            "bank_ifsc": v.bank_ifsc, "credit_days": v.credit_days,
            "is_active": v.is_active, "created_at": v.created_at,
            "addresses": [
                {"id": a.id, "label": a.label, "address_line1": a.address_line1,
                 "address_line2": a.address_line2, "city": a.city, "state": a.state,
                 "state_code": a.state_code, "pincode": a.pincode,
                 "contact_person": a.contact_person, "phone": a.phone,
                 "address_type": a.address_type, "is_preferred": a.is_preferred,
                 "vendor_id": a.vendor_id}
                for a in v.addresses
            ],
            "outstanding_balance": VendorService._get_outstanding(db, v.id),
        }

    @staticmethod
    def _derive_state_code(gstin: Optional[str], explicit: Optional[int],
                           state: Optional[str] = None) -> Optional[int]:
        # explicit > GSTIN prefix > state name (shared helper)
        return derive_state_code(gstin, state, explicit)

    @staticmethod
    def create(db: Session, payload: VendorCreate, user_id: int) -> dict:
        if payload.gstin:
            existing = db.query(Vendor).filter(Vendor.gstin == payload.gstin).first()
            if existing:
                raise HTTPException(status_code=400, detail="Vendor with this GSTIN already exists")
        data = payload.dict()
        derived = VendorService._derive_state_code(
            data.get("gstin"), data.get("state_code"), data.get("state"))
        if derived is not None:
            data["state_code"] = derived
        v = Vendor(**data, created_by=user_id)
        db.add(v)
        db.commit()
        db.refresh(v)
        audit(db, user_id, "create", "purchase",
              f"Created vendor {v.trade_name}"
              + (f" (GSTIN {v.gstin})" if v.gstin else ""),
              record_type="vendor", record_id=v.id)
        return VendorService.get_by_id(db, v.id)

    # ── Bulk CSV import ───────────────────────────────────────
    IMPORT_COLUMNS = [
        "trade_name", "legal_name", "gstin", "gst_status",
        "phone", "email", "contact_person", "credit_days",
        "bank_name", "bank_account", "bank_ifsc", "state",
        "addr_label", "address_line1", "address_line2",
        "city", "addr_state", "pincode",
    ]

    @staticmethod
    def get_import_csv_template() -> str:
        sample = [
            "Sunrise Imports", "Sunrise Imports LLP", "27FGHIJ5678K1Z2", "Registered",
            "9820011223", "sales@sunrise.com", "Meera", "45",
            "HDFC Bank", "50100123456789", "HDFC0000123", "Maharashtra",
            "Office", "8 Industrial Estate", "", "Mumbai", "Maharashtra", "400001",
        ]
        return "\n".join([",".join(VendorService.IMPORT_COLUMNS), ",".join(sample)])

    @staticmethod
    def bulk_import(db: Session, file_content: str, user_id: int) -> dict:
        """Bulk-create vendors from CSV.

        Required column: trade_name. GSTIN is format-validated when present and a
        row whose gstin already exists is skipped and reported (not an error).
        state_code is derived from the GSTIN when not supplied. If address_line1
        is given, a preferred address is created (city/addr_state/pincode
        required). Each valid row commits via its own SAVEPOINT.
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
            if gstin:
                try:
                    gstin = _validate_gstin(gstin)
                except Exception as e:
                    row_errors.append(str(e))
            try:
                credit_days = parse_int(row.get("credit_days"))
            except Exception:
                row_errors.append(f"Invalid credit_days: '{row.get('credit_days')}'")

            if row_errors:
                errors.append({"row": idx, "data": trade_name, "errors": row_errors})
                continue

            if gstin and db.query(Vendor).filter(Vendor.gstin == gstin).first():
                skipped.append({"row": idx, "data": trade_name,
                                "reason": f"GSTIN {gstin} already exists"})
                continue

            try:
                with db.begin_nested():
                    v = Vendor(
                        trade_name=trade_name,
                        legal_name=clean(row.get("legal_name")),
                        gstin=gstin,
                        gst_status=clean(row.get("gst_status")),
                        state=clean(row.get("state")),
                        state_code=VendorService._derive_state_code(gstin, None, clean(row.get("state"))),
                        phone=clean(row.get("phone")),
                        email=clean(row.get("email")),
                        contact_person=clean(row.get("contact_person")),
                        bank_name=clean(row.get("bank_name")),
                        bank_account=clean(row.get("bank_account")),
                        bank_ifsc=clean(row.get("bank_ifsc")),
                        credit_days=credit_days,
                        created_by=user_id,
                    )
                    db.add(v)
                    db.flush()

                    line1 = (row.get("address_line1") or "").strip()
                    if line1:
                        city = (row.get("city") or "").strip()
                        astate = (row.get("addr_state") or "").strip()
                        pincode = (row.get("pincode") or "").strip()
                        missing = [n for n, val in (("city", city), ("addr_state", astate),
                                                    ("pincode", pincode)) if not val]
                        if missing:
                            raise ValueError(f"address needs {', '.join(missing)}")
                        db.add(VendorAddress(
                            vendor_id=v.id,
                            label=(row.get("addr_label") or "Office").strip(),
                            address_line1=line1,
                            address_line2=clean(row.get("address_line2")),
                            city=city, state=astate,
                            state_code=resolve_state_code(astate),
                            pincode=pincode,
                            is_preferred=True,
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
    def update(db: Session, vendor_id: int, payload: VendorUpdate, user_id: int) -> dict:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found")

        data = payload.dict(exclude_none=True)

        # Duplicate-GSTIN check when gstin is being changed
        new_gstin = data.get("gstin")
        if new_gstin and new_gstin != v.gstin:
            clash = db.query(Vendor).filter(
                Vendor.gstin == new_gstin, Vendor.id != vendor_id
            ).first()
            if clash:
                raise HTTPException(status_code=400, detail="Another vendor already uses this GSTIN")
            # Re-derive state_code from new GSTIN unless caller supplied one explicitly
            if "state_code" not in data:
                derived = VendorService._derive_state_code(new_gstin, None)
                if derived is not None:
                    data["state_code"] = derived

        # State name changed without GSTIN/state_code: re-derive from the name.
        if "state" in data and "state_code" not in data and not new_gstin:
            rc = resolve_state_code(data["state"])
            if rc is not None:
                data["state_code"] = rc

        # Block deactivation when outstanding balance is non-zero
        if data.get("is_active") is False and v.is_active:
            outstanding = VendorService._get_outstanding(db, vendor_id)
            if outstanding != Decimal("0"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot deactivate vendor with non-zero outstanding balance ({outstanding})"
                )

        old = {f: getattr(v, f, None) for f in data.keys()}
        for field, value in data.items():
            setattr(v, field, value)
        v.updated_by = user_id
        db.commit()
        new = {f: getattr(v, f, None) for f in data.keys()}
        changed, summary = diff(old, new, list(data.keys()))
        if changed:
            audit(db, user_id, "update", "purchase",
                  f"Updated vendor {v.trade_name}: {summary}",
                  record_type="vendor", record_id=v.id,
                  old={k: val[0] for k, val in changed.items()},
                  new={k: val[1] for k, val in changed.items()})
        return VendorService.get_by_id(db, vendor_id)

    @staticmethod
    def add_address(db: Session, vendor_id: int, payload: VendorAddressCreate, user_id: int) -> dict:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found")
        addr = VendorAddress(vendor_id=vendor_id, **payload.dict(), created_by=user_id)
        if addr.state_code is None:
            addr.state_code = resolve_state_code(addr.state)
        db.add(addr)
        db.commit()
        db.refresh(addr)
        return {"id": addr.id, "label": addr.label, "city": addr.city,
                "state": addr.state, "pincode": addr.pincode}

    @staticmethod
    def get_ledger(db: Session, vendor_id: int, page: int = 1, page_size: int = 50) -> dict:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found")
        q = db.query(LedgerEntry).filter(LedgerEntry.vendor_id == vendor_id)\
              .order_by(LedgerEntry.entry_date.desc())
        result = paginate(q, page, page_size)
        result["vendor_name"] = v.trade_name
        result["outstanding_balance"] = VendorService._get_outstanding(db, vendor_id)
        return result

    @staticmethod
    async def fetch_gstin_details(gstin: str) -> dict:
        """Fetch vendor details from Cleartax GSTIN API.

        Returns the parsed details on success, or a dict with `error` and
        `error_code` describing the failure mode so the caller can show a
        meaningful message instead of a generic 'try again'.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.GSTIN_LOOKUP_URL}{gstin}",
                    headers={"x-cleartax-auth-token": settings.GSTIN_LOOKUP_TOKEN}
                )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "trade_name": data.get("tradeNam", ""),
                    "legal_name": data.get("lgnm", ""),
                    "business_type": data.get("dty", ""),
                    "gst_status": data.get("sts", ""),
                    "state": data.get("pradr", {}).get("addr", {}).get("stcd", ""),
                    "address": data.get("pradr", {}).get("addr", {}),
                    "registration_date": data.get("rgdt", ""),
                    "nature_of_business": ", ".join(data.get("nba", [])),
                }
            if resp.status_code in (401, 403):
                return {"error": "GSTIN lookup is not authorised. Check CLEARTAX_AUTH_TOKEN.",
                        "error_code": "unauthorized"}
            if resp.status_code == 404:
                return {"error": "GSTIN not found.", "error_code": "not_found"}
            return {"error": f"GSTIN lookup failed (HTTP {resp.status_code}).",
                    "error_code": "upstream_error"}
        except httpx.TimeoutException:
            return {"error": "GSTIN lookup timed out. Please try again.",
                    "error_code": "timeout"}
        except httpx.HTTPError as e:
            return {"error": f"GSTIN lookup network error: {e.__class__.__name__}",
                    "error_code": "network_error"}
        except Exception as e:
            return {"error": f"Unexpected error: {e.__class__.__name__}",
                    "error_code": "unexpected"}
