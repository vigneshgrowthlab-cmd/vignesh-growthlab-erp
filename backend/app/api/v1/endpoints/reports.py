from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.models.models import User
from app.core.security import get_current_user, require_admin_or_accountant, require_super_admin
from app.services.reports_service import (
    DashboardService, SalesReportService, PurchaseReportService,
    StockReportService, StockClearanceService, PnLService, DayBookService, LedgerReportService,
)
from app.utils.helpers import get_financial_year

# ── Dashboard ─────────────────────────────────────────────────
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@dashboard_router.get("/")
async def get_dashboard(
    financial_year: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Default to the current financial year, computed per request (a static
    # Query default would freeze at process-start date).
    return DashboardService.get_metrics(
        db, financial_year or get_financial_year(), current_user
    )


# ── Reports Router ────────────────────────────────────────────
reports_router = APIRouter(prefix="/reports", tags=["reports"])

@reports_router.get("/sales")
async def sales_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    document_type: Optional[str] = None,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return SalesReportService.generate(
        db, date_from, date_to, customer_id, product_id, None, document_type, financial_year
    )


@reports_router.get("/purchases")
async def purchase_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    vendor_id: Optional[int] = None,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return PurchaseReportService.generate(db, date_from, date_to, vendor_id, financial_year)


@reports_router.get("/stock")
async def stock_report(
    warehouse_id: Optional[int] = None,
    category_id: Optional[int] = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return StockReportService.generate(db, warehouse_id, category_id, low_stock_only)


@reports_router.get("/stock-clearance")
async def stock_clearance_report(
    warehouse_id: Optional[int] = None,
    category_id: Optional[int] = None,
    min_age_days: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return StockClearanceService.generate(db, warehouse_id, category_id, min_age_days)


@reports_router.get("/pnl")
async def pnl_report(
    financial_year: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return PnLService.generate(db, financial_year, date_from, date_to)


@reports_router.get("/day-book")
async def day_book(
    for_date: date = Query(default=date.today()),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return DayBookService.generate(db, for_date)


@reports_router.get("/customer-ledger")
async def customer_ledger(
    customer_id: int = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return LedgerReportService.customer_ledger(db, customer_id, date_from, date_to)


@reports_router.get("/vendor-ledger")
async def vendor_ledger(
    vendor_id: int = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return LedgerReportService.vendor_ledger(db, vendor_id, date_from, date_to)
