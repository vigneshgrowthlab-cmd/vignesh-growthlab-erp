from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, case
from fastapi import HTTPException
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List

from app.models.models import (
    Cheque, ChequeStatus, CashClosing, CashClosingStatus,
    Expense, ExpenseStatus, TDSEntry, Customer, Vendor,
    LedgerEntry, TransactionType, JournalEntry, JournalLine,
    Account, CustomerPayment, Invoice, DocumentType
)
from app.schemas.accounting import (
    ChequeCreate, ChequeDepositUpdate, ChequeClearanceUpdate,
    ChequeBounceUpdate, CashClosingApprove, ExpenseCreate,
    ExpenseApprove, TDSEntryCreate, Form26ASImport
)
from app.utils.helpers import get_or_create_account, paginate, get_financial_year, next_sequence_number, _seed_from_suffix, format_document_number
from app.services.audit import audit
from app.services.config_service import ConfigService
from app.services.tax_master_service import TaxMasterService
from app.core.config import settings


class ChequeService:

    @staticmethod
    def _get_name(db, customer_id, vendor_id):
        cname = vname = None
        if customer_id:
            c = db.query(Customer).filter(Customer.id == customer_id).first()
            cname = c.trade_name if c else None
        if vendor_id:
            v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
            vname = v.trade_name if v else None
        return cname, vname

    @staticmethod
    def _fmt(ch, cname, vname):
        return {
            "id": ch.id, "cheque_number": ch.cheque_number,
            "cheque_date": ch.cheque_date, "bank_name": ch.bank_name,
            "amount": ch.amount, "customer_name": cname, "vendor_name": vname,
            "status": ch.status, "is_pdc": ch.is_pdc,
            "deposit_date": ch.deposit_date, "clearance_date": ch.clearance_date,
            "bounce_date": ch.bounce_date, "bounce_reason": ch.bounce_reason,
            "bounce_charges": ch.bounce_charges, "notes": ch.notes,
            "created_at": ch.created_at,
        }

    @staticmethod
    def create(db: Session, payload: ChequeCreate, user_id: int) -> dict:
        ch = Cheque(
            cheque_number=payload.cheque_number,
            cheque_date=payload.cheque_date,
            bank_name=payload.bank_name,
            amount=payload.amount,
            customer_id=payload.customer_id,
            vendor_id=payload.vendor_id,
            receipt_id=payload.receipt_id,
            payment_id=payload.payment_id,
            is_pdc=payload.is_pdc,
            deposit_date=payload.deposit_date,
            status=ChequeStatus.received,
            notes=payload.notes,
            created_by=user_id,
        )
        db.add(ch)
        db.commit()
        db.refresh(ch)
        audit(db, user_id, "create", "accounting",
              f"Recorded cheque {ch.cheque_number} ({ch.bank_name}) for ₹{ch.amount}",
              record_type="cheque", record_id=ch.id)
        cname, vname = ChequeService._get_name(db, ch.customer_id, ch.vendor_id)
        return ChequeService._fmt(ch, cname, vname)

    @staticmethod
    def deposit(db: Session, cheque_id: int, payload: ChequeDepositUpdate, user_id: int) -> dict:
        ch = db.query(Cheque).filter(Cheque.id == cheque_id).first()
        if not ch:
            raise HTTPException(status_code=404, detail="Cheque not found")
        if ch.status not in (ChequeStatus.received, ChequeStatus.pdc_pending):
            raise HTTPException(status_code=400, detail=f"Cannot deposit cheque in status: {ch.status}")
        old_status = str(ch.status)
        ch.status = ChequeStatus.deposited
        ch.deposit_date = payload.deposit_date
        ch.updated_by = user_id
        db.commit()
        audit(db, user_id, "update", "accounting",
              f"Cheque {ch.cheque_number} marked deposited",
              record_type="cheque", record_id=ch.id,
              old={"status": old_status}, new={"status": "deposited"})
        cname, vname = ChequeService._get_name(db, ch.customer_id, ch.vendor_id)
        return ChequeService._fmt(ch, cname, vname)

    @staticmethod
    def clear(db: Session, cheque_id: int, payload: ChequeClearanceUpdate, user_id: int) -> dict:
        ch = db.query(Cheque).filter(Cheque.id == cheque_id).first()
        if not ch:
            raise HTTPException(status_code=404, detail="Cheque not found")
        if ch.status != ChequeStatus.deposited:
            raise HTTPException(status_code=400, detail="Cheque must be deposited before clearing")
        ch.status = ChequeStatus.cleared
        ch.clearance_date = payload.clearance_date
        ch.updated_by = user_id
        db.commit()
        audit(db, user_id, "update", "accounting",
              f"Cheque {ch.cheque_number} marked cleared",
              record_type="cheque", record_id=ch.id,
              old={"status": "deposited"}, new={"status": "cleared"})
        cname, vname = ChequeService._get_name(db, ch.customer_id, ch.vendor_id)
        return ChequeService._fmt(ch, cname, vname)

    @staticmethod
    def bounce(db: Session, cheque_id: int, payload: ChequeBounceUpdate, user_id: int) -> dict:
        ch = db.query(Cheque).filter(Cheque.id == cheque_id).first()
        if not ch:
            raise HTTPException(status_code=404, detail="Cheque not found")
        ch.status = ChequeStatus.bounced
        ch.bounce_date = payload.bounce_date
        ch.bounce_reason = payload.bounce_reason
        ch.bounce_charges = payload.bounce_charges
        ch.updated_by = user_id

        # Reverse the customer payment if linked
        if ch.customer_id and ch.receipt_id:
            payment = db.query(CustomerPayment).filter(CustomerPayment.id == ch.receipt_id).first()
            if payment:
                # Reverse ledger entry
                last = db.query(LedgerEntry).filter(
                    LedgerEntry.customer_id == ch.customer_id
                ).order_by(desc(LedgerEntry.id)).first()
                prev_bal = last.balance if last else Decimal("0")
                le = LedgerEntry(
                    customer_id=ch.customer_id,
                    transaction_type=TransactionType.debit,
                    amount=ch.amount,
                    balance=prev_bal + ch.amount,
                    reference_type="cheque_bounce",
                    reference_id=ch.id,
                    narration=f"Cheque bounce reversal — {ch.cheque_number}",
                    entry_date=payload.bounce_date,
                    financial_year=get_financial_year(payload.bounce_date),
                )
                db.add(le)

        db.commit()
        audit(db, user_id, "update", "accounting",
              f"Cheque {ch.cheque_number} bounced — {payload.bounce_reason or 'no reason given'}"
              + (f" (charges ₹{payload.bounce_charges})" if payload.bounce_charges else ""),
              record_type="cheque", record_id=ch.id,
              old={"status": "deposited"}, new={"status": "bounced"})
        cname, vname = ChequeService._get_name(db, ch.customer_id, ch.vendor_id)
        return ChequeService._fmt(ch, cname, vname)

    @staticmethod
    def list_cheques(db: Session, status: Optional[str] = None,
                     customer_id: Optional[int] = None,
                     page: int = 1, page_size: int = 20) -> dict:
        q = db.query(Cheque)
        if status:
            q = q.filter(Cheque.status == status)
        if customer_id:
            q = q.filter(Cheque.customer_id == customer_id)
        result = paginate(q.order_by(desc(Cheque.cheque_date), desc(Cheque.id)), page, page_size)
        items = []
        for ch in result["items"]:
            cname, vname = ChequeService._get_name(db, ch.customer_id, ch.vendor_id)
            items.append(ChequeService._fmt(ch, cname, vname))
        result["items"] = items
        return result

    @staticmethod
    def get_pdc_alerts(db: Session) -> List[dict]:
        """Get post-dated cheques due for deposit in the configured window."""
        today = date.today()
        pdc_days = ConfigService.get_int(db, "company.pdc_alert_days", default=7)
        upcoming = today + timedelta(days=pdc_days)
        cheques = db.query(Cheque).filter(
            Cheque.is_pdc == True,
            Cheque.status == ChequeStatus.received,
            Cheque.cheque_date <= upcoming,
            Cheque.cheque_date >= today,
        ).all()
        result = []
        for ch in cheques:
            cname, vname = ChequeService._get_name(db, ch.customer_id, ch.vendor_id)
            days_until = (ch.cheque_date - today).days
            result.append({
                **ChequeService._fmt(ch, cname, vname),
                "days_until_due": days_until,
            })
        return result


class CashClosingService:

    @staticmethod
    def get_current(db: Session, closing_date: date) -> dict:
        """Get or prepare today's cash closing."""
        existing = db.query(CashClosing).filter(CashClosing.closing_date == closing_date).first()
        if existing:
            return CashClosingService._fmt(db, existing)

        # Find previous day closing balance
        prev = db.query(CashClosing).filter(
            CashClosing.closing_date < closing_date,
            CashClosing.status == CashClosingStatus.approved
        ).order_by(desc(CashClosing.closing_date)).first()

        opening = prev.closing_balance if prev else Decimal("0")
        fy = get_financial_year(closing_date)

        # Calculate today's movements
        receipts = db.query(func.sum(CustomerPayment.amount)).filter(
            CustomerPayment.payment_date == closing_date,
            CustomerPayment.payment_mode == "cash",
        ).scalar() or Decimal("0")

        expenses = db.query(func.sum(Expense.amount)).filter(
            Expense.expense_date == closing_date,
            Expense.payment_mode == "cash",
            Expense.status == ExpenseStatus.approved,
        ).scalar() or Decimal("0")

        closing = opening + receipts - expenses
        entries = CashClosingService._get_entries(db, closing_date)

        return {
            "id": None,
            "closing_date": closing_date,
            "opening_balance": opening,
            "total_receipts": receipts,
            "total_payments": Decimal("0"),
            "total_expenses": expenses,
            "total_deposits": Decimal("0"),
            "closing_balance": closing,
            "status": "draft",
            "approved_by_name": None,
            "approved_at": None,
            "financial_year": fy,
            "created_at": None,
            "entries": entries,
        }

    @staticmethod
    def _get_entries(db: Session, closing_date: date) -> List[dict]:
        entries = []
        receipts = db.query(CustomerPayment).filter(
            CustomerPayment.payment_date == closing_date,
            CustomerPayment.payment_mode == "cash",
        ).all()
        for r in receipts:
            c = db.query(Customer).filter(Customer.id == r.customer_id).first()
            entries.append({
                "type": "receipt", "reference": r.payment_number,
                "narration": f"Receipt from {c.trade_name if c else 'Customer'}",
                "amount": r.amount, "direction": "in",
            })
        expenses = db.query(Expense).filter(
            Expense.expense_date == closing_date,
            Expense.payment_mode == "cash",
            Expense.status == ExpenseStatus.approved,
        ).all()
        for e in expenses:
            entries.append({
                "type": "expense", "reference": e.expense_number,
                "narration": e.description, "amount": e.amount, "direction": "out",
            })
        return entries

    @staticmethod
    def create(db: Session, payload, user_id: int) -> dict:
        """Persist (or update) a DRAFT cash closing, capturing bank deposits."""
        closing_date = payload.closing_date
        existing = db.query(CashClosing).filter(CashClosing.closing_date == closing_date).first()
        if existing and existing.status == CashClosingStatus.approved:
            raise HTTPException(status_code=400, detail="Cash closing already approved")

        prev = db.query(CashClosing).filter(
            CashClosing.closing_date < closing_date,
            CashClosing.status == CashClosingStatus.approved,
        ).order_by(desc(CashClosing.closing_date)).first()
        opening = prev.closing_balance if prev else Decimal("0")
        fy = get_financial_year(closing_date)

        receipts = db.query(func.sum(CustomerPayment.amount)).filter(
            CustomerPayment.payment_date == closing_date,
            CustomerPayment.payment_mode == "cash",
        ).scalar() or Decimal("0")

        expenses = db.query(func.sum(Expense.amount)).filter(
            Expense.expense_date == closing_date,
            Expense.payment_mode == "cash",
            Expense.status == ExpenseStatus.approved,
        ).scalar() or Decimal("0")

        deposits = payload.total_deposits or Decimal("0")
        closing_balance = opening + receipts - expenses - deposits

        if existing:
            existing.opening_balance = opening
            existing.total_receipts = receipts
            existing.total_expenses = expenses
            existing.total_deposits = deposits
            existing.closing_balance = closing_balance
            existing.financial_year = fy
            existing.notes = payload.notes
            row = existing
            action = "update"
        else:
            row = CashClosing(
                closing_date=closing_date,
                opening_balance=opening,
                total_receipts=receipts,
                total_payments=Decimal("0"),
                total_expenses=expenses,
                total_deposits=deposits,
                closing_balance=closing_balance,
                status=CashClosingStatus.draft,
                financial_year=fy,
                notes=payload.notes,
                created_by=user_id,
            )
            db.add(row)
            action = "create"

        db.commit()
        db.refresh(row)
        audit(db, user_id, action, "accounting",
              f"{'Updated' if action == 'update' else 'Saved'} draft cash closing for "
              f"{closing_date.isoformat()} — closing balance ₹{closing_balance}",
              record_type="cash_closing", record_id=row.id)
        return CashClosingService._fmt(db, row)

    @staticmethod
    def approve(db: Session, payload: CashClosingApprove, user_id: int,
                closing_id: Optional[int] = None, closing_date: Optional[date] = None) -> dict:
        if closing_id is not None:
            existing = db.query(CashClosing).filter(CashClosing.id == closing_id).first()
            if not existing:
                raise HTTPException(status_code=404, detail="Cash closing not found")
            closing_date = existing.closing_date
        else:
            if closing_date is None:
                closing_date = date.today()
            existing = db.query(CashClosing).filter(CashClosing.closing_date == closing_date).first()

        if existing and existing.status == CashClosingStatus.approved:
            raise HTTPException(status_code=400, detail="Cash closing already approved")

        draft = CashClosingService.get_current(db, closing_date)

        if existing:
            existing.status = CashClosingStatus.approved
            existing.approved_by = user_id
            existing.approved_at = datetime.utcnow()
            closing = existing
        else:
            fy = get_financial_year(closing_date)
            closing = CashClosing(
                closing_date=closing_date,
                opening_balance=draft["opening_balance"],
                total_receipts=draft["total_receipts"],
                total_payments=draft["total_payments"],
                total_expenses=draft["total_expenses"],
                total_deposits=draft["total_deposits"],
                closing_balance=draft["closing_balance"],
                status=CashClosingStatus.approved,
                approved_by=user_id,
                approved_at=datetime.utcnow(),
                financial_year=fy,
                created_by=user_id,
            )
            db.add(closing)

        db.commit()
        db.refresh(closing if hasattr(closing, 'id') else existing)
        _c = closing if hasattr(closing, 'id') and closing.id else existing
        audit(db, user_id, "approve", "accounting",
              f"Approved cash closing for {closing_date.isoformat()} — "
              f"closing balance ₹{draft['closing_balance']}",
              record_type="cash_closing", record_id=getattr(_c, 'id', None))
        return CashClosingService._fmt(db, _c)

    @staticmethod
    def list_closings(db: Session, page: int = 1, page_size: int = 20) -> dict:
        q = db.query(CashClosing).order_by(desc(CashClosing.closing_date))
        result = paginate(q, page, page_size)
        items = [CashClosingService._fmt(db, c) for c in result["items"]]
        result["items"] = items
        return result

    @staticmethod
    def _fmt(db: Session, c) -> dict:
        approved_name = None
        if c.approved_by:
            from app.models.models import User
            u = db.query(User).filter(User.id == c.approved_by).first()
            approved_name = u.full_name if u else None
        return {
            "id": c.id, "closing_date": c.closing_date,
            "opening_balance": c.opening_balance,
            "total_receipts": c.total_receipts,
            "total_payments": c.total_payments,
            "total_expenses": c.total_expenses,
            "total_deposits": c.total_deposits,
            "closing_balance": c.closing_balance,
            "status": c.status, "approved_by_name": approved_name,
            "approved_at": c.approved_at,
            "financial_year": c.financial_year,
            "created_at": c.created_at, "entries": [],
        }


class ExpenseService:

    @staticmethod
    def create(db: Session, payload: ExpenseCreate, user_id: int) -> dict:
        fy = get_financial_year(payload.expense_date)
        count = db.query(Expense).count()
        exp_number = format_document_number(db, "EXP", fy, count + 1, "EXP", 4)

        approval_threshold = ConfigService.get_decimal(
            db, "company.expense_approval_threshold",
            as_of=payload.expense_date, default=settings.EXPENSE_APPROVAL_THRESHOLD,
        )
        needs_approval = payload.amount > Decimal(str(approval_threshold))
        status = ExpenseStatus.pending_approval if needs_approval else ExpenseStatus.approved

        exp = Expense(
            expense_number=exp_number,
            expense_date=payload.expense_date,
            category=payload.category,
            description=payload.description,
            amount=payload.amount,
            payment_mode=payload.payment_mode,
            reference_number=payload.reference_number,
            vendor_id=payload.vendor_id,
            notes=payload.notes,
            status=status,
            financial_year=fy,
            created_by=user_id,
        )
        db.add(exp)

        if status == ExpenseStatus.approved:
            ExpenseService._post_journal(db, exp, user_id, fy)

        db.commit()
        db.refresh(exp)
        audit(db, user_id, "create", "accounting",
              f"Created expense {exp.expense_number} — {exp.category} ₹{exp.amount} "
              f"({str(exp.status).split('.')[-1]})",
              record_type="expense", record_id=exp.id)
        return ExpenseService._fmt(db, exp)

    @staticmethod
    def approve(db: Session, expense_id: int, payload: ExpenseApprove, user_id: int) -> dict:
        exp = db.query(Expense).filter(Expense.id == expense_id).first()
        if not exp:
            raise HTTPException(status_code=404, detail="Expense not found")
        if exp.status != ExpenseStatus.pending_approval:
            raise HTTPException(status_code=400, detail=f"Expense is {exp.status}")

        if payload.approved:
            exp.status = ExpenseStatus.approved
            exp.approved_by = user_id
            exp.approved_at = datetime.utcnow()
            exp.admin_notes = payload.admin_notes
            fy = get_financial_year(exp.expense_date)
            ExpenseService._post_journal(db, exp, user_id, fy)
        else:
            exp.status = ExpenseStatus.rejected
            exp.admin_notes = payload.admin_notes

        db.commit()
        audit(db, user_id, "approve", "accounting",
              f"Expense {exp.expense_number} ({exp.category} ₹{exp.amount}) "
              f"{str(exp.status).split('.')[-1]}",
              record_type="expense", record_id=exp.id,
              old={"status": "pending_approval"},
              new={"status": str(exp.status).split('.')[-1]})
        return ExpenseService._fmt(db, exp)

    @staticmethod
    def _post_journal(db: Session, exp, user_id: int, fy: str):
        seq = next_sequence_number(
            db, "journal_entry", "JE", fy,
            seed_from=lambda d, f: _seed_from_suffix(d, f, "journal_entries", "entry_number"),
        )
        je = JournalEntry(
            entry_number=format_document_number(db, "JE", fy, seq, "JE", 5),
            entry_date=exp.expense_date,
            reference_type="expense",
            reference_id=exp.id,
            narration=f"Expense: {exp.description}",
            financial_year=fy,
            created_by=user_id,
        )
        db.add(je)
        db.flush()
        pay_acc = "CASH" if str(exp.payment_mode).lower() == "cash" else "BANK"
        exp_acc = get_or_create_account(db, "EXPENSES")
        pay_acc_obj = db.query(Account).filter(Account.account_code == pay_acc).first()
        if exp_acc and pay_acc_obj:
            db.add(JournalLine(journal_entry_id=je.id, account_id=exp_acc.id,
                               transaction_type=TransactionType.debit, amount=exp.amount))
            db.add(JournalLine(journal_entry_id=je.id, account_id=pay_acc_obj.id,
                               transaction_type=TransactionType.credit, amount=exp.amount))

    @staticmethod
    def list_expenses(db: Session, status: Optional[str] = None,
                      category: Optional[str] = None,
                      page: int = 1, page_size: int = 20) -> dict:
        q = db.query(Expense)
        if status:
            q = q.filter(Expense.status == status)
        if category:
            q = q.filter(Expense.category == category)
        result = paginate(q.order_by(desc(Expense.expense_date), desc(Expense.id)), page, page_size)
        items = [ExpenseService._fmt(db, e) for e in result["items"]]
        result["items"] = items
        return result

    @staticmethod
    def _fmt(db: Session, e) -> dict:
        vendor_name = None
        if e.vendor_id:
            v = db.query(Vendor).filter(Vendor.id == e.vendor_id).first()
            vendor_name = v.trade_name if v else None
        return {
            "id": e.id, "expense_number": e.expense_number,
            "expense_date": e.expense_date, "category": e.category,
            "description": e.description, "amount": e.amount,
            "payment_mode": e.payment_mode, "reference_number": e.reference_number,
            "vendor_name": vendor_name, "status": e.status,
            "admin_notes": e.admin_notes, "notes": e.notes,
            "financial_year": e.financial_year, "created_at": e.created_at,
        }

    @staticmethod
    def get_categories(db: Session) -> List[str]:
        rows = db.query(Expense.category).distinct().all()
        fixed = ["Office Supplies", "Travel", "Utilities", "Rent", "Salaries",
                 "Marketing", "Maintenance", "Logistics", "Professional Fees", "Other"]
        dynamic = [r[0] for r in rows if r[0] not in fixed]
        return fixed + dynamic


class TDSService:

    @staticmethod
    def create(db: Session, payload: TDSEntryCreate, user_id: int) -> dict:
        count = db.query(TDSEntry).count()
        tds_number = format_document_number(db, "TDS", payload.financial_year, count + 1, "TDS", 4)
        entry = TDSEntry(
            tds_number=tds_number,
            customer_id=payload.customer_id,
            receipt_id=payload.receipt_id,
            tds_amount=payload.tds_amount,
            tds_percent=payload.tds_percent,
            invoice_amount=payload.invoice_amount,
            deduction_date=payload.deduction_date,
            tan_number=payload.tan_number,
            section_code=payload.section_code,
            financial_year=payload.financial_year,
            is_reconciled=False,
            notes=payload.notes,
            created_by=user_id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        audit(db, user_id, "create", "accounting",
              f"Created TDS entry {entry.tds_number} — ₹{entry.tds_amount} "
              f"@ {entry.tds_percent}% (section {entry.section_code})",
              record_type="tds_entry", record_id=entry.id)
        return TDSService._fmt(db, entry)

    @staticmethod
    def list_entries(db: Session, financial_year: Optional[str] = None,
                     customer_id: Optional[int] = None,
                     is_reconciled: Optional[bool] = None,
                     page: int = 1, page_size: int = 20) -> dict:
        q = db.query(TDSEntry)
        if financial_year:
            q = q.filter(TDSEntry.financial_year == financial_year)
        if customer_id:
            q = q.filter(TDSEntry.customer_id == customer_id)
        if is_reconciled is not None:
            q = q.filter(TDSEntry.is_reconciled == is_reconciled)
        result = paginate(q.order_by(desc(TDSEntry.deduction_date), desc(TDSEntry.id)), page, page_size)
        items = [TDSService._fmt(db, e) for e in result["items"]]
        result["items"] = items
        return result

    @staticmethod
    def import_26as(db: Session, payload: Form26ASImport, user_id: int) -> dict:
        """Import Form 26AS entries and reconcile against TDS records."""
        matched = 0
        unmatched = []
        for entry in payload.entries:
            tan = entry.get("tan_number", "")
            amount = Decimal(str(entry.get("amount", 0)))
            section = entry.get("section", "194C")
            fy = payload.financial_year
            existing = db.query(TDSEntry).filter(
                TDSEntry.financial_year == fy,
                TDSEntry.tds_amount == amount,
                TDSEntry.section_code == section,
                TDSEntry.is_reconciled == False,
            ).first()
            if existing:
                existing.is_reconciled = True
                existing.tan_number = tan
                matched += 1
            else:
                unmatched.append(entry)
        db.commit()
        return {
            "financial_year": payload.financial_year,
            "total_imported": len(payload.entries),
            "matched": matched,
            "unmatched_count": len(unmatched),
            "unmatched_entries": unmatched,
        }

    @staticmethod
    def _fmt(db: Session, e) -> dict:
        c = db.query(Customer).filter(Customer.id == e.customer_id).first()
        return {
            "id": e.id, "tds_number": e.tds_number,
            "customer_name": c.trade_name if c else None,
            "receipt_id": e.receipt_id, "tds_amount": e.tds_amount,
            "tds_percent": e.tds_percent, "invoice_amount": e.invoice_amount,
            "deduction_date": e.deduction_date, "tan_number": e.tan_number,
            "section_code": e.section_code, "financial_year": e.financial_year,
            "is_reconciled": e.is_reconciled, "created_at": e.created_at,
        }


class CustomerAgeingService:

    @staticmethod
    def get_ageing(db: Session, as_of_date: Optional[date] = None) -> dict:
        if not as_of_date:
            as_of_date = date.today()

        # Effective-dated bucket boundaries + priority weights. The response
        # keeps its fixed 4-bucket shape; only the day boundaries and weights
        # are configurable. Falls back to 30/60/90 + 1/2/3/5 when unseeded.
        _bk = TaxMasterService.aging_buckets(db, as_of_date)
        if len(_bk) == 4 and all(_bk[i]["to_days"] is not None for i in range(3)):
            t1, t2, t3 = _bk[0]["to_days"], _bk[1]["to_days"], _bk[2]["to_days"]
            w1, w2, w3, w4 = (Decimal(str(b["weight"])) for b in _bk)
        else:
            t1, t2, t3 = 30, 60, 90
            w1, w2, w3, w4 = Decimal("1"), Decimal("2"), Decimal("3"), Decimal("5")

        customers = db.query(Customer).filter(Customer.is_active == True).all()
        items = []

        for customer in customers:
            outstanding = db.query(Invoice).filter(
                Invoice.customer_id == customer.id,
                Invoice.document_type.in_([DocumentType.b2b_invoice, DocumentType.b2c_invoice]),
                Invoice.is_cancelled == False,
                Invoice.outstanding_amount > 0,
                Invoice.invoice_date <= as_of_date,
            ).all()

            if not outstanding:
                continue

            b0_30 = b31_60 = b61_90 = b90plus = Decimal("0")
            for inv in outstanding:
                age = (as_of_date - inv.invoice_date).days
                amt = inv.outstanding_amount
                if age <= t1:
                    b0_30 += amt
                elif age <= t2:
                    b31_60 += amt
                elif age <= t3:
                    b61_90 += amt
                else:
                    b90plus += amt

            total = b0_30 + b31_60 + b61_90 + b90plus
            # Collection priority = weighted by age and amount
            priority = (b0_30 * w1 + b31_60 * w2 + b61_90 * w3 + b90plus * w4)

            last_payment = db.query(CustomerPayment.payment_date).filter(
                CustomerPayment.customer_id == customer.id
            ).order_by(desc(CustomerPayment.payment_date)).first()

            items.append({
                "customer_id": customer.id,
                "customer_name": customer.trade_name,
                "gstin": customer.gstin,
                "phone": customer.phone,
                "bucket_0_30": b0_30.quantize(Decimal("0.01")),
                "bucket_31_60": b31_60.quantize(Decimal("0.01")),
                "bucket_61_90": b61_90.quantize(Decimal("0.01")),
                "bucket_90_plus": b90plus.quantize(Decimal("0.01")),
                "total_outstanding": total.quantize(Decimal("0.01")),
                "collection_priority_score": priority.quantize(Decimal("0.01")),
                "last_payment_date": last_payment[0] if last_payment else None,
                "credit_days": customer.credit_days,
                "credit_limit": customer.credit_limit,
            })

        items.sort(key=lambda x: x["collection_priority_score"], reverse=True)
        total_outstanding = sum(i["total_outstanding"] for i in items)

        return {
            "as_of_date": as_of_date,
            "total_outstanding": total_outstanding.quantize(Decimal("0.01")),
            "customer_count": len(items),
            "items": items,
            "summary": {
                "bucket_0_30": sum(i["bucket_0_30"] for i in items).quantize(Decimal("0.01")),
                "bucket_31_60": sum(i["bucket_31_60"] for i in items).quantize(Decimal("0.01")),
                "bucket_61_90": sum(i["bucket_61_90"] for i in items).quantize(Decimal("0.01")),
                "bucket_90_plus": sum(i["bucket_90_plus"] for i in items).quantize(Decimal("0.01")),
            }
        }


class JournalService:

    @staticmethod
    def list_accounts(db: Session) -> List[dict]:
        accounts = db.query(Account).filter(Account.is_active == True).order_by(Account.account_code).all()
        return [
            {
                "account_code": acc.account_code,
                "account_name": acc.account_name or acc.name,
                "account_type": acc.account_type,
            }
            for acc in accounts
        ]

    @staticmethod
    def create(db: Session, payload, user_id: int) -> dict:
        debit_total = sum((l.amount for l in payload.lines if l.transaction_type == "debit"), Decimal("0"))
        credit_total = sum((l.amount for l in payload.lines if l.transaction_type == "credit"), Decimal("0"))
        if debit_total == 0:
            raise HTTPException(status_code=400, detail="Journal entry must have a non-zero amount")
        if abs(debit_total - credit_total) >= Decimal("0.01"):
            raise HTTPException(
                status_code=400,
                detail=f"Entry not balanced — debits ₹{debit_total} ≠ credits ₹{credit_total}",
            )

        resolved = []
        for line in payload.lines:
            acc = db.query(Account).filter(Account.account_code == line.account_code).first()
            if not acc:
                raise HTTPException(status_code=400, detail=f"Unknown account: {line.account_code}")
            resolved.append((acc, line))

        fy = get_financial_year(payload.entry_date)
        seq = next_sequence_number(
            db, "journal_entry", "JE", fy,
            seed_from=lambda d, f: _seed_from_suffix(d, f, "journal_entries", "entry_number"),
        )
        je = JournalEntry(
            entry_number=format_document_number(db, "JE", fy, seq, "JE", 5),
            entry_date=payload.entry_date,
            reference_type=payload.reference_type or "manual",
            reference_id=None,
            narration=payload.narration,
            financial_year=fy,
            created_by=user_id,
        )
        db.add(je)
        db.flush()
        for acc, line in resolved:
            db.add(JournalLine(
                journal_entry_id=je.id,
                account_id=acc.id,
                transaction_type=TransactionType(line.transaction_type),
                amount=line.amount,
                narration=line.narration,
            ))

        db.commit()
        db.refresh(je)
        audit(db, user_id, "create", "accounting",
              f"Posted manual journal entry {je.entry_number} — ₹{debit_total} ({je.narration})",
              record_type="journal_entry", record_id=je.id)

        lines = db.query(JournalLine, Account).join(
            Account, JournalLine.account_id == Account.id
        ).filter(JournalLine.journal_entry_id == je.id).all()
        return {
            "id": je.id, "entry_number": je.entry_number,
            "entry_date": je.entry_date,
            "reference_type": je.reference_type,
            "reference_id": je.reference_id,
            "narration": je.narration,
            "financial_year": je.financial_year,
            "created_at": je.created_at,
            "lines": [
                {
                    "account_code": acc.account_code,
                    "account_name": acc.account_name or acc.name,
                    "transaction_type": jl.transaction_type,
                    "amount": jl.amount,
                }
                for jl, acc in lines
            ],
        }

    @staticmethod
    def list_entries(db: Session, reference_type: Optional[str] = None,
                     financial_year: Optional[str] = None,
                     date_from: Optional[date] = None,
                     date_to: Optional[date] = None,
                     page: int = 1, page_size: int = 20) -> dict:
        q = db.query(JournalEntry)
        if reference_type:
            q = q.filter(JournalEntry.reference_type == reference_type)
        if financial_year:
            q = q.filter(JournalEntry.financial_year == financial_year)
        if date_from:
            q = q.filter(JournalEntry.entry_date >= date_from)
        if date_to:
            q = q.filter(JournalEntry.entry_date <= date_to)

        result = paginate(q.order_by(desc(JournalEntry.entry_date), desc(JournalEntry.id)), page, page_size)
        items = []
        for je in result["items"]:
            lines = db.query(JournalLine, Account).join(
                Account, JournalLine.account_id == Account.id
            ).filter(JournalLine.journal_entry_id == je.id).all()
            items.append({
                "id": je.id, "entry_number": je.entry_number,
                "entry_date": je.entry_date,
                "reference_type": je.reference_type,
                "reference_id": je.reference_id,
                "narration": je.narration,
                "financial_year": je.financial_year,
                "created_at": je.created_at,
                "lines": [
                    {
                        "account_code": acc.account_code,
                        "account_name": acc.account_name,
                        "transaction_type": jl.transaction_type,
                        "amount": jl.amount,
                    }
                    for jl, acc in lines
                ],
            })
        result["items"] = items
        return result

    @staticmethod
    def get_trial_balance(db: Session, financial_year: str) -> dict:
        accounts = db.query(Account).filter(Account.is_active == True).all()
        items = []
        total_debit = total_credit = Decimal("0")

        for acc in accounts:
            debits = db.query(func.sum(JournalLine.amount)).join(JournalEntry).filter(
                JournalLine.account_id == acc.id,
                JournalLine.transaction_type == TransactionType.debit,
                JournalEntry.financial_year == financial_year,
            ).scalar() or Decimal("0")

            credits = db.query(func.sum(JournalLine.amount)).join(JournalEntry).filter(
                JournalLine.account_id == acc.id,
                JournalLine.transaction_type == TransactionType.credit,
                JournalEntry.financial_year == financial_year,
            ).scalar() or Decimal("0")

            if debits == 0 and credits == 0:
                continue

            net = debits - credits
            total_debit += debits
            total_credit += credits
            items.append({
                "account_code": acc.account_code,
                "account_name": acc.account_name,
                "account_type": acc.account_type,
                "debit_total": debits.quantize(Decimal("0.01")),
                "credit_total": credits.quantize(Decimal("0.01")),
                "net_balance": net.quantize(Decimal("0.01")),
            })

        return {
            "financial_year": financial_year,
            "items": items,
            "total_debit": total_debit.quantize(Decimal("0.01")),
            "total_credit": total_credit.quantize(Decimal("0.01")),
            "is_balanced": abs(total_debit - total_credit) < Decimal("0.01"),
        }


class VendorDueAlertService:

    @staticmethod
    def get_due_alerts(db: Session, days_ahead: int = 7) -> List[dict]:
        """All purchases with an outstanding balance — overdue first, then by due date,
        no-due-date last. days_ahead is retained for API compatibility but no longer filters."""
        from app.models.models import Purchase
        today = date.today()

        dues = db.query(Purchase).filter(
            Purchase.outstanding_amount > 0,
            Purchase.is_cancelled == False,
        ).order_by(
            Purchase.payment_due_date.is_(None),
            Purchase.payment_due_date,
        ).all()

        result = []
        for p in dues:
            v = db.query(Vendor).filter(Vendor.id == p.vendor_id).first()
            days_left = (p.payment_due_date - today).days if p.payment_due_date else None
            is_overdue = days_left is not None and days_left < 0
            result.append({
                "purchase_id": p.id,
                "purchase_number": p.purchase_number,
                "vendor_id": p.vendor_id,
                "vendor_name": v.trade_name if v else None,
                "vendor_phone": v.phone if v else None,
                "vendor_invoice_number": p.vendor_invoice_number,
                "invoice_date": p.invoice_date,
                "total_amount": p.total_amount,
                "paid_amount": p.paid_amount,
                "outstanding_amount": p.outstanding_amount,
                "payment_due_date": p.payment_due_date,
                "days_until_due": days_left,
                "is_overdue": is_overdue,
                "overdue_days": -days_left if is_overdue else 0,
            })
        return result
