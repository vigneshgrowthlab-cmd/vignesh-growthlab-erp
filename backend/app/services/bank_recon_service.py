from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException
from decimal import Decimal
from datetime import datetime, date

from app.models.models import (
    BankReconciliation, BankReconciliationLine,
    JournalEntry, JournalLine, TransactionType, User,
)
from app.services.purchase_service import PurchaseService
from app.services.audit import audit
from app.services.config_service import ConfigService
from app.utils.helpers import (
    get_or_create_account, paginate, get_financial_year, next_sequence_number,
)

TOL = Decimal("1")


class BankReconService:

    # ── internal helpers ─────────────────────────────────────

    @staticmethod
    def _account_id(db: Session, code: str) -> int:
        return get_or_create_account(db, code or "BANK").id

    @staticmethod
    def _period_book_rows(db: Session, account_id: int, period_from: date, period_to: date):
        """All non-cancelled journal lines on the bank account within the period."""
        return db.query(JournalLine, JournalEntry).join(
            JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
        ).filter(
            JournalLine.account_id == account_id,
            JournalEntry.is_cancelled == False,
            JournalEntry.entry_date >= period_from,
            JournalEntry.entry_date <= period_to,
        ).order_by(JournalEntry.entry_date, JournalLine.id).all()

    @staticmethod
    def _book_entry(jl: JournalLine, je: JournalEntry) -> dict:
        is_debit = jl.transaction_type == TransactionType.debit
        return {
            "journal_line_id": jl.id,
            "date": str(je.entry_date) if je.entry_date else None,
            "entry_number": je.entry_number,
            "narration": je.narration or jl.narration,
            "debit": float(jl.amount) if is_debit else 0.0,
            "credit": float(jl.amount) if not is_debit else 0.0,
            "amount": float(jl.amount),
            "direction": "debit" if is_debit else "credit",
        }

    @staticmethod
    def _recompute(db: Session, recon: BankReconciliation):
        bank_credit = sum((l.bank_credit or Decimal("0")) for l in recon.lines)
        bank_debit = sum((l.bank_debit or Decimal("0")) for l in recon.lines)
        bank_mv = bank_credit - bank_debit

        acct_id = BankReconService._account_id(db, recon.account_code)
        rows = BankReconService._period_book_rows(db, acct_id, recon.period_from, recon.period_to)
        books_mv = Decimal("0")
        for jl, _je in rows:
            if jl.transaction_type == TransactionType.debit:
                books_mv += jl.amount
            else:
                books_mv -= jl.amount

        recon.statement_closing_balance = bank_mv
        recon.books_closing_balance = books_mv
        recon.difference = bank_mv - books_mv

    @staticmethod
    def _user_names(db: Session, ids) -> dict:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = db.query(User.id, User.full_name).filter(User.id.in_(ids)).all()
        return {uid: name for uid, name in rows}

    # ── create + auto-match ──────────────────────────────────

    @staticmethod
    def create_draft(db: Session, payload, user_id: int) -> dict:
        code = payload.account_code or "BANK"
        acct_id = BankReconService._account_id(db, code)
        fy = get_financial_year(payload.period_to)
        seq = next_sequence_number(db, "bank_reconciliation", "RECON", fy)
        number = f"RECON-{fy.replace('-', '')}-{seq:04d}"

        recon = BankReconciliation(
            reconciliation_number=number,
            account_code=code,
            period_from=payload.period_from,
            period_to=payload.period_to,
            status="draft",
            notes=getattr(payload, "notes", None),
            financial_year=fy,
            created_by=user_id,
        )
        db.add(recon)
        db.flush()

        # Candidate book lines (unreconciled only)
        candidates = [
            (jl, je) for jl, je in
            BankReconService._period_book_rows(db, acct_id, payload.period_from, payload.period_to)
            if not jl.is_reconciled
        ]
        used = set()
        now = datetime.now()

        tol = ConfigService.get_decimal(
            db, "rbi.recon_amount_tolerance",
            as_of=payload.period_from, default=TOL)
        window_days = ConfigService.get_int(
            db, "rbi.recon_date_window_days",
            as_of=payload.period_from, default=2)

        for entry in payload.entries:
            credit = entry.credit or Decimal("0")
            debit = entry.debit or Decimal("0")
            line = BankReconciliationLine(
                reconciliation_id=recon.id,
                bank_date=entry.entry_date,
                bank_description=entry.description,
                bank_debit=debit,
                bank_credit=credit,
                bank_reference=entry.reference,
                match_type="unmatched",
            )

            need_dir = None
            bank_amount = None
            if credit > 0:
                need_dir, bank_amount = TransactionType.debit, credit
            elif debit > 0:
                need_dir, bank_amount = TransactionType.credit, debit

            chosen, reason = None, None
            if need_dir is not None:
                ref = (entry.reference or "").strip().lower()
                if ref:
                    for jl, je in candidates:
                        if jl.id in used or jl.transaction_type != need_dir:
                            continue
                        if abs(jl.amount - bank_amount) >= tol:
                            continue
                        if (je.entry_number and ref == je.entry_number.lower()) or \
                           (je.narration and ref in je.narration.lower()):
                            chosen, reason = (jl, je), "auto: reference + amount"
                            break
                if not chosen:
                    for jl, je in candidates:
                        if jl.id in used or jl.transaction_type != need_dir:
                            continue
                        if abs(jl.amount - bank_amount) >= tol:
                            continue
                        if je.entry_date and entry.entry_date and \
                           abs((je.entry_date - entry.entry_date).days) <= window_days:
                            chosen, reason = (jl, je), "auto: amount + date"
                            break

            if chosen:
                jl, _je = chosen
                used.add(jl.id)
                line.journal_line_id = jl.id
                line.match_type = "auto"
                line.match_reason = reason
                line.matched_by = user_id
                line.matched_at = now

            db.add(line)

        db.flush()
        BankReconService._recompute(db, recon)
        db.commit()
        db.refresh(recon)
        audit(db, user_id, "create", "bank",
              f"Created bank reconciliation {recon.reconciliation_number} "
              f"({recon.account_code}) for {recon.period_from} to {recon.period_to}",
              record_type="bank_reconciliation", record_id=recon.id)
        return BankReconService.get(db, recon.id)

    # ── read ─────────────────────────────────────────────────

    @staticmethod
    def list_recons(db: Session, page=1, page_size=20) -> dict:
        q = db.query(BankReconciliation).order_by(
            desc(BankReconciliation.period_to), desc(BankReconciliation.id))
        result = paginate(q, page, page_size)
        names = BankReconService._user_names(db, [r.created_by for r in result["items"]])
        result["items"] = [{
            "id": r.id,
            "reconciliation_number": r.reconciliation_number,
            "account_code": r.account_code,
            "period_from": r.period_from,
            "period_to": r.period_to,
            "statement_closing_balance": r.statement_closing_balance,
            "books_closing_balance": r.books_closing_balance,
            "difference": r.difference,
            "status": r.status,
            "financial_year": r.financial_year,
            "created_at": r.created_at,
            "created_by_name": names.get(r.created_by),
        } for r in result["items"]]
        return result

    @staticmethod
    def get(db: Session, recon_id: int) -> dict:
        recon = db.query(BankReconciliation).filter(BankReconciliation.id == recon_id).first()
        if not recon:
            raise HTTPException(status_code=404, detail="Reconciliation not found")

        acct_id = BankReconService._account_id(db, recon.account_code)
        rows = BankReconService._period_book_rows(db, acct_id, recon.period_from, recon.period_to)
        book_map = {jl.id: BankReconService._book_entry(jl, je) for jl, je in rows}
        recon_flag = {jl.id: bool(jl.is_reconciled) for jl, _je in rows}

        names = BankReconService._user_names(
            db, [recon.created_by, recon.finalized_by] + [l.matched_by for l in recon.lines])

        matched_jl_ids = set()
        lines = []
        bank_only = []
        for l in recon.lines:
            mbe = book_map.get(l.journal_line_id) if l.journal_line_id else None
            if l.journal_line_id:
                matched_jl_ids.add(l.journal_line_id)
            row = {
                "id": l.id,
                "bank_date": str(l.bank_date) if l.bank_date else None,
                "bank_description": l.bank_description,
                "bank_debit": float(l.bank_debit or 0),
                "bank_credit": float(l.bank_credit or 0),
                "bank_reference": l.bank_reference,
                "match_type": l.match_type,
                "match_reason": l.match_reason,
                "is_adjustment": bool(l.is_adjustment),
                "journal_line_id": l.journal_line_id,
                "matched_book_entry": mbe,
                "matched_by_name": names.get(l.matched_by),
                "matched_at": l.matched_at,
            }
            lines.append(row)
            if l.match_type == "unmatched" or not l.journal_line_id:
                bank_only.append(row)

        # Book entries with no matching bank line in this recon (and not locked elsewhere)
        unmatched_books = [
            be for jl_id, be in book_map.items()
            if jl_id not in matched_jl_ids and not recon_flag.get(jl_id)
        ]

        return {
            "id": recon.id,
            "reconciliation_number": recon.reconciliation_number,
            "account_code": recon.account_code,
            "period_from": recon.period_from,
            "period_to": recon.period_to,
            "statement_closing_balance": recon.statement_closing_balance,
            "books_closing_balance": recon.books_closing_balance,
            "difference": recon.difference,
            "status": recon.status,
            "notes": recon.notes,
            "financial_year": recon.financial_year,
            "created_at": recon.created_at,
            "created_by_name": names.get(recon.created_by),
            "finalized_by_name": names.get(recon.finalized_by),
            "finalized_at": recon.finalized_at,
            "lines": lines,
            "unmatched_in_bank": bank_only,
            "unmatched_in_books": unmatched_books,
            "matched_count": sum(1 for l in lines if l["journal_line_id"]),
            "unmatched_bank_count": len(bank_only),
            "unmatched_books_count": len(unmatched_books),
        }

    # ── mutations ────────────────────────────────────────────

    @staticmethod
    def _get_draft(db: Session, recon_id: int) -> BankReconciliation:
        recon = db.query(BankReconciliation).filter(BankReconciliation.id == recon_id).first()
        if not recon:
            raise HTTPException(status_code=404, detail="Reconciliation not found")
        if recon.status != "draft":
            raise HTTPException(status_code=400, detail="Reconciliation is locked and cannot be modified")
        return recon

    @staticmethod
    def _get_line(recon: BankReconciliation, line_id: int) -> BankReconciliationLine:
        for l in recon.lines:
            if l.id == line_id:
                return l
        raise HTTPException(status_code=404, detail="Reconciliation line not found")

    @staticmethod
    def manual_match(db: Session, recon_id: int, line_id: int, journal_line_id: int, user_id: int) -> dict:
        recon = BankReconService._get_draft(db, recon_id)
        line = BankReconService._get_line(recon, line_id)

        jl = db.query(JournalLine).filter(JournalLine.id == journal_line_id).first()
        if not jl:
            raise HTTPException(status_code=404, detail="Journal line not found")
        if jl.is_reconciled:
            raise HTTPException(status_code=400, detail="Journal line already reconciled")
        acct_id = BankReconService._account_id(db, recon.account_code)
        if jl.account_id != acct_id:
            raise HTTPException(status_code=400, detail="Journal line is not on the bank account")
        for other in recon.lines:
            if other.id != line.id and other.journal_line_id == journal_line_id:
                raise HTTPException(status_code=400, detail="Journal line already matched in this reconciliation")

        line.previous_journal_line_id = line.journal_line_id
        line.journal_line_id = journal_line_id
        line.match_type = "manual"
        line.match_reason = "manual match"
        line.matched_by = user_id
        line.matched_at = datetime.now()
        db.commit()
        return BankReconService.get(db, recon_id)

    @staticmethod
    def unmatch(db: Session, recon_id: int, line_id: int, user_id: int) -> dict:
        recon = BankReconService._get_draft(db, recon_id)
        line = BankReconService._get_line(recon, line_id)
        if line.is_adjustment:
            raise HTTPException(status_code=400, detail="Cannot unmatch an adjustment line; delete is not supported")
        line.previous_journal_line_id = line.journal_line_id
        line.journal_line_id = None
        line.match_type = "unmatched"
        line.match_reason = None
        line.matched_by = user_id
        line.matched_at = datetime.now()
        db.commit()
        return BankReconService.get(db, recon_id)

    @staticmethod
    def add_adjustment(db: Session, recon_id: int, payload, user_id: int) -> dict:
        recon = BankReconService._get_draft(db, recon_id)
        amount = payload.amount
        if amount is None or amount <= 0:
            raise HTTPException(status_code=400, detail="Adjustment amount must be positive")
        fy = recon.financial_year or get_financial_year(recon.period_to)

        if payload.kind == "charge":
            narration = payload.narration or "Bank charges"
            lines = [
                ("BANK_CHARGES", TransactionType.debit, amount),
                (recon.account_code, TransactionType.credit, amount),
            ]
            bank_debit, bank_credit = amount, Decimal("0")
        elif payload.kind == "interest":
            narration = payload.narration or "Bank interest"
            lines = [
                (recon.account_code, TransactionType.debit, amount),
                ("INTEREST", TransactionType.credit, amount),
            ]
            bank_debit, bank_credit = Decimal("0"), amount
        else:
            raise HTTPException(status_code=400, detail="kind must be 'charge' or 'interest'")

        PurchaseService._post_journal(
            db, recon.period_to, "bank_reconciliation", recon.id, narration, fy, lines, user_id)
        db.flush()

        je = db.query(JournalEntry).filter(
            JournalEntry.reference_type == "bank_reconciliation",
            JournalEntry.reference_id == recon.id,
        ).order_by(desc(JournalEntry.id)).first()
        acct_id = BankReconService._account_id(db, recon.account_code)
        bank_jl = db.query(JournalLine).filter(
            JournalLine.journal_entry_id == je.id,
            JournalLine.account_id == acct_id,
        ).first()

        now = datetime.now()
        line_id = getattr(payload, "line_id", None)
        if line_id:
            line = BankReconService._get_line(recon, line_id)
            line.journal_line_id = bank_jl.id if bank_jl else None
            line.match_type = "adjustment"
            line.match_reason = narration
            line.is_adjustment = True
            line.adjustment_journal_entry_id = je.id
            line.matched_by = user_id
            line.matched_at = now
        else:
            line = BankReconciliationLine(
                reconciliation_id=recon.id,
                bank_date=recon.period_to,
                bank_description=narration,
                bank_debit=bank_debit,
                bank_credit=bank_credit,
                bank_reference=None,
                journal_line_id=bank_jl.id if bank_jl else None,
                match_type="adjustment",
                match_reason=narration,
                is_adjustment=True,
                adjustment_journal_entry_id=je.id,
                matched_by=user_id,
                matched_at=now,
            )
            db.add(line)

        db.flush()
        db.refresh(recon)
        BankReconService._recompute(db, recon)
        db.commit()
        audit(db, user_id, "adjustment", "bank",
              f"Added {payload.kind} adjustment of ₹{amount} to reconciliation "
              f"{recon.reconciliation_number}: {narration}",
              record_type="bank_reconciliation", record_id=recon.id)
        return BankReconService.get(db, recon_id)

    # ── statement file import ────────────────────────────────

    @staticmethod
    def parse_statement_file(filename: str, content: bytes) -> list:
        import io
        import pandas as pd

        name = (filename or "").lower()
        try:
            if name.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(content))
            elif name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(content))
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type; upload .csv, .xlsx or .xls")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

        cols = {str(c).strip().lower(): c for c in df.columns}

        def find(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            for key, orig in cols.items():
                if any(key == n or key.replace(".", "").replace("/", " ") == n for n in names):
                    return orig
            for key, orig in cols.items():
                if any(n in key for n in names):
                    return orig
            return None

        date_col = find("date", "txn date", "transaction date", "value date", "tran date")
        desc_col = find("description", "narration", "particulars", "details", "remarks", "transaction details")
        debit_col = find("debit", "withdrawal", "withdrawal amt", "withdrawal amount", "withdrawals", "paid out")
        credit_col = find("credit", "deposit", "deposit amt", "deposit amount", "deposits", "paid in")
        ref_col = find("reference", "ref no", "chq no", "cheque no", "utr", "ref", "chq", "instrument no")
        amount_col = find("amount", "amt")

        def num(v):
            if v is None:
                return 0.0
            try:
                if pd.isna(v):
                    return 0.0
            except Exception:
                pass
            try:
                return float(str(v).replace(",", "").replace("₹", "").strip() or 0)
            except (ValueError, TypeError):
                return 0.0

        def parse_date(v):
            try:
                d = pd.to_datetime(v, dayfirst=True, errors="coerce")
                if pd.isna(d):
                    return None
                return d.date().isoformat()
            except Exception:
                return None

        entries = []
        for _, r in df.iterrows():
            debit = num(r[debit_col]) if debit_col else 0.0
            credit = num(r[credit_col]) if credit_col else 0.0
            if debit == 0 and credit == 0 and amount_col:
                amt = num(r[amount_col])
                if amt >= 0:
                    credit = amt
                else:
                    debit = abs(amt)
            if debit == 0 and credit == 0:
                continue
            entries.append({
                "entry_date": parse_date(r[date_col]) if date_col else None,
                "description": (str(r[desc_col]).strip() if desc_col and not pd.isna(r[desc_col]) else ""),
                "debit": debit,
                "credit": credit,
                "reference": (str(r[ref_col]).strip() if ref_col and not pd.isna(r[ref_col]) else None),
            })
        return entries

    @staticmethod
    def finalize(db: Session, recon_id: int, user_id: int) -> dict:
        recon = BankReconService._get_draft(db, recon_id)
        BankReconService._recompute(db, recon)
        for l in recon.lines:
            if l.journal_line_id:
                jl = db.query(JournalLine).filter(JournalLine.id == l.journal_line_id).first()
                if jl:
                    jl.is_reconciled = True
                    jl.reconciliation_id = recon.id
        recon.status = "locked"
        recon.finalized_by = user_id
        recon.finalized_at = datetime.now()
        db.commit()
        audit(db, user_id, "approve", "bank",
              f"Finalized (locked) bank reconciliation {recon.reconciliation_number} "
              f"— difference ₹{recon.difference}",
              record_type="bank_reconciliation", record_id=recon.id,
              old={"status": "draft"}, new={"status": "locked"})
        return BankReconService.get(db, recon_id)
