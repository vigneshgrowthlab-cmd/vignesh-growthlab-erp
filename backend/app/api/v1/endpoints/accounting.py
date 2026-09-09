from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.models.models import User
from app.core.security import get_current_user, require_admin, require_admin_or_accountant
from app.schemas.accounting import (
    ChequeCreate, ChequeDepositUpdate, ChequeClearanceUpdate,
    ChequeBounceUpdate, CashClosingCreate, CashClosingApprove, ExpenseCreate,
    ExpenseApprove, TDSEntryCreate, Form26ASImport,
    JournalEntryCreate,
)
from app.services.accounting_service import (
    ChequeService, CashClosingService, ExpenseService,
    TDSService, CustomerAgeingService, JournalService,
    VendorDueAlertService,
)

# ── Cheque Register ───────────────────────────────────────────
cheque_router = APIRouter(prefix="/cheques", tags=["cheques"])

@cheque_router.get("/")
async def list_cheques(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return ChequeService.list_cheques(db, status, customer_id, page, page_size)


@cheque_router.post("/", status_code=201)
async def create_cheque(
    payload: ChequeCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return ChequeService.create(db, payload, current_user.id)


@cheque_router.get("/pdc-alerts")
async def get_pdc_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return ChequeService.get_pdc_alerts(db)


@cheque_router.post("/{cheque_id}/deposit")
async def deposit_cheque(
    cheque_id: int,
    payload: ChequeDepositUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return ChequeService.deposit(db, cheque_id, payload, current_user.id)


@cheque_router.post("/{cheque_id}/clear")
async def clear_cheque(
    cheque_id: int,
    payload: ChequeClearanceUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return ChequeService.clear(db, cheque_id, payload, current_user.id)


@cheque_router.post("/{cheque_id}/bounce")
async def bounce_cheque(
    cheque_id: int,
    payload: ChequeBounceUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return ChequeService.bounce(db, cheque_id, payload, current_user.id)


# ── Cash Closing ──────────────────────────────────────────────
cash_router = APIRouter(prefix="/cash-closing", tags=["cash-closing"])

@cash_router.get("/")
async def list_closings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CashClosingService.list_closings(db, page, page_size)


@cash_router.get("/today")
async def get_today_closing(
    closing_date: date = Query(default=date.today()),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CashClosingService.get_current(db, closing_date)


@cash_router.post("/", status_code=201)
async def create_closing(
    payload: CashClosingCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return CashClosingService.create(db, payload, current_user.id)


@cash_router.post("/approve")
async def approve_closing(
    payload: CashClosingApprove,
    closing_id: Optional[int] = Query(None),
    closing_date: date = Query(default=date.today()),
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return CashClosingService.approve(
        db, payload, current_user.id, closing_id=closing_id, closing_date=closing_date
    )


# ── Expenses ──────────────────────────────────────────────────
expense_router = APIRouter(prefix="/expenses", tags=["expenses"])

@expense_router.get("/")
async def list_expenses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return ExpenseService.list_expenses(db, status, category, page, page_size)


@expense_router.get("/categories")
async def get_expense_categories(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return ExpenseService.get_categories(db)


@expense_router.post("/", status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return ExpenseService.create(db, payload, current_user.id)


@expense_router.post("/{expense_id}/approve")
async def approve_expense(
    expense_id: int,
    payload: ExpenseApprove,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ExpenseService.approve(db, expense_id, payload, current_user.id)


# ── TDS ───────────────────────────────────────────────────────
tds_router = APIRouter(prefix="/tds", tags=["tds"])

@tds_router.get("/")
async def list_tds_entries(
    financial_year: Optional[str] = None,
    customer_id: Optional[int] = None,
    is_reconciled: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return TDSService.list_entries(db, financial_year, customer_id, is_reconciled, page, page_size)


@tds_router.post("/", status_code=201)
async def create_tds_entry(
    payload: TDSEntryCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return TDSService.create(db, payload, current_user.id)


@tds_router.post("/import-26as")
async def import_form_26as(
    payload: Form26ASImport,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return TDSService.import_26as(db, payload, current_user.id)


# ── Customer Ageing ───────────────────────────────────────────
ageing_router = APIRouter(prefix="/customer-ageing", tags=["customer-ageing"])

@ageing_router.get("/")
async def get_customer_ageing(
    as_of_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CustomerAgeingService.get_ageing(db, as_of_date)


# ── Journal Entries ───────────────────────────────────────────
journal_router = APIRouter(prefix="/journal", tags=["journal"])

@journal_router.get("/")
async def list_journal_entries(
    reference_type: Optional[str] = None,
    financial_year: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return JournalService.list_entries(
        db, reference_type, financial_year, date_from, date_to, page, page_size
    )


@journal_router.get("/accounts")
async def list_journal_accounts(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return JournalService.list_accounts(db)


@journal_router.post("/", status_code=201)
async def create_journal_entry(
    payload: JournalEntryCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return JournalService.create(db, payload, current_user.id)


@journal_router.get("/trial-balance")
async def get_trial_balance(
    financial_year: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return JournalService.get_trial_balance(db, financial_year)


# ── Vendor Due Alerts ─────────────────────────────────────────
vendor_due_router = APIRouter(prefix="/vendor-due-alerts", tags=["vendor-due-alerts"])

@vendor_due_router.get("/")
async def get_vendor_due_alerts(
    days_ahead: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return VendorDueAlertService.get_due_alerts(db, days_ahead)
