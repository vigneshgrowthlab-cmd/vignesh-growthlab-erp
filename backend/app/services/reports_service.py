import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, case, distinct, text
from fastapi import HTTPException
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List

from app.models.models import (
    Invoice, InvoiceItem, Purchase, PurchaseItem,
    Customer, Vendor, Product, Category, Warehouse,
    WarehouseStock, StockEntry, StockTransactionType, LedgerEntry, TransactionType,
    JournalEntry, JournalLine, Account, CustomerPayment,
    VendorPayment, Expense, ExpenseStatus, DocumentType, User,
    CashClosing, CashClosingStatus
)
from app.utils.helpers import get_financial_year
from app.services.price_history_service import _today_ist

logger = logging.getLogger(__name__)


class DashboardService:

    # Sale document types reused across every metric.
    _SALES = [DocumentType.b2b_invoice, DocumentType.b2c_invoice]

    @staticmethod
    def _safe(db: Session, fn, default):
        """Run one metric in isolation. On error, log, roll back the session
        (a failed SELECT poisons the transaction for following queries) and
        return the default — so one bad metric degrades gracefully instead of
        500-ing the whole dashboard."""
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - dashboard must not hard-fail
            logger.warning("dashboard metric failed: %s", e)
            try:
                db.rollback()
            except Exception:
                pass
            return default

    # Roles that see the full, company-wide dashboard. Everyone else gets a
    # reduced, warehouse-scoped view (current/previous-month + today sales only).
    _FULL_VIEW_ROLES = ("super_admin", "accountant")

    @staticmethod
    def _role_of(user) -> str:
        role = getattr(user, "role", None)
        return role.value if hasattr(role, "value") else (role or "")

    @staticmethod
    def _reduced_metrics(db: Session, current_user) -> dict:
        """Warehouse-scoped sales snapshot for non-privileged roles: this month,
        previous month and today, restricted to the user's mapped warehouse.
        A user with no mapped warehouse sees zeros (no all-warehouse fallback)."""
        today = _today_ist()
        month_start = today.replace(day=1)
        prev_month_end = month_start                       # exclusive
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        SALES = DashboardService._SALES
        safe = lambda fn, default=0.0: DashboardService._safe(db, fn, default)

        wid = getattr(current_user, "warehouse_id", None)
        wh_name = None
        if wid:
            wh_name = safe(lambda: (
                db.query(Warehouse.name).filter(Warehouse.id == wid).scalar()
            ), None)

        def _sales(lo=None, hi_excl=None, on=None):
            if not wid:
                return 0.0
            q = db.query(func.coalesce(func.sum(Invoice.total_amount), 0)).filter(
                Invoice.is_cancelled == False,
                Invoice.document_type.in_(SALES),
                Invoice.warehouse_id == wid,
            )
            if on is not None:
                q = q.filter(Invoice.invoice_date == on)
            else:
                q = q.filter(Invoice.invoice_date >= lo)
                if hi_excl is not None:
                    q = q.filter(Invoice.invoice_date < hi_excl)
            return float(q.scalar() or 0)

        return {
            "reduced": True,
            "warehouse_id": wid,
            "warehouse_name": wh_name,
            "today_sales": safe(lambda: _sales(on=today)),
            "month_sales": safe(lambda: _sales(month_start, today + timedelta(days=1))),
            "prev_month_sales": safe(lambda: _sales(prev_month_start, prev_month_end)),
        }

    @staticmethod
    def get_metrics(db: Session, financial_year: str, current_user=None) -> dict:
        from app.services.vendor_service import VendorService

        if current_user is not None and \
                DashboardService._role_of(current_user) not in DashboardService._FULL_VIEW_ROLES:
            return DashboardService._reduced_metrics(db, current_user)

        today = _today_ist()  # IST, matching the DB session timezone (+05:30)
        month_start = today.replace(day=1)
        fy_start = date(int(financial_year[:4]), 4, 1)
        fy_end = date(fy_start.year + 1, 4, 1)  # exclusive upper bound (next FY start)
        SALES = DashboardService._SALES
        safe = lambda fn, default=0.0: DashboardService._safe(db, fn, default)

        def _sales_sum(lo, hi_excl=None, on=None):
            """Return (gross, net-taxable) sales over a date window."""
            q = db.query(
                func.coalesce(func.sum(Invoice.total_amount), 0),
                func.coalesce(func.sum(Invoice.taxable_amount), 0),
            ).filter(
                Invoice.is_cancelled == False,
                Invoice.document_type.in_(SALES),
            )
            if on is not None:
                q = q.filter(Invoice.invoice_date == on)
            else:
                q = q.filter(Invoice.invoice_date >= lo)
                if hi_excl is not None:
                    q = q.filter(Invoice.invoice_date < hi_excl)
            r = q.one()
            return float(r[0]), float(r[1])

        today_sales, today_sales_net = safe(lambda: _sales_sum(None, on=today), (0.0, 0.0))
        # month: [month_start, today] inclusive → use exclusive next-day bound
        month_sales, month_sales_net = safe(
            lambda: _sales_sum(month_start, today + timedelta(days=1)), (0.0, 0.0))
        fy_sales, fy_sales_net = safe(lambda: _sales_sum(fy_start, fy_end), (0.0, 0.0))

        # Receivables + overdue in one pass. Outstanding derives from (total -
        # paid) since the cached column drifts; overdue falls back to
        # invoice_date + credit_days when an invoice has no explicit due_date.
        def _receivables():
            rows = db.query(
                Invoice.due_date, Invoice.invoice_date,
                (Invoice.total_amount - func.coalesce(Invoice.paid_amount, 0)).label("out"),
                func.coalesce(Customer.credit_days, 0).label("cd"),
            ).outerjoin(Customer, Customer.id == Invoice.customer_id).filter(
                Invoice.is_cancelled == False,
                Invoice.document_type.in_(SALES),
                (Invoice.total_amount - func.coalesce(Invoice.paid_amount, 0)) > 0,
            ).all()
            total = Decimal("0")
            od = Decimal("0")
            for r in rows:
                out = Decimal(str(r.out or 0))
                total += out
                due = r.due_date or (r.invoice_date + timedelta(days=int(r.cd or 0)))
                if due and due < today:
                    od += out
            return float(total), float(od)

        total_outstanding, overdue = safe(_receivables, (0.0, 0.0))

        # Total payables — company-wide vendor outstanding (positive balances
        # only), same source of truth as the vendor screen.
        total_payables = safe(
            lambda: float(VendorService._total_outstanding_all(db)), 0.0)

        # Purchases (gross) this month and this FY.
        month_purchases = safe(lambda: float(
            db.query(func.coalesce(func.sum(Purchase.total_amount), 0)).filter(
                Purchase.invoice_date >= month_start,
                Purchase.invoice_date <= today,
                Purchase.is_cancelled == False,
            ).scalar() or 0))
        fy_purchases = safe(lambda: float(
            db.query(func.coalesce(func.sum(Purchase.total_amount), 0)).filter(
                Purchase.invoice_date >= fy_start,
                Purchase.invoice_date < fy_end,
                Purchase.is_cancelled == False,
            ).scalar() or 0))

        # Stock valuation — FIFO remaining_qty * unit_cost over inbound layers.
        stock_value = safe(lambda: float(
            db.query(func.coalesce(
                func.sum(StockEntry.remaining_qty * StockEntry.unit_cost), 0)
            ).filter(
                StockEntry.remaining_qty > 0,
                StockEntry.transaction_type.in_([
                    StockTransactionType.purchase, StockTransactionType.return_in,
                    StockTransactionType.transfer_in, StockTransactionType.adjustment_in,
                ]),
            ).scalar() or 0))

        # Pending deliveries — delivery challans whose warehouse transfer has not
        # been executed yet (dc_status still 'pending' or 'linked'; 'delivered'
        # means the transfer is done, 'rejected'/'cancelled' are terminal).
        # dc_status is a column on the invoices table but is NOT mapped on the
        # Invoice ORM model, so it must be read with raw SQL (NULL = legacy
        # pending). Match both stored document_type spellings.
        pending_deliveries = safe(lambda: db.execute(text(
            "SELECT COUNT(*) FROM invoices "
            "WHERE LOWER(document_type) IN ('delivery_challan', 'documenttype.delivery_challan') "
            "AND COALESCE(is_cancelled, 0) = 0 "
            "AND (dc_status IN ('pending', 'linked') OR dc_status IS NULL)"
        )).scalar() or 0, 0)

        # Low stock count — total qty per product across ACTIVE warehouses only.
        # LEFT JOIN + COALESCE so never-stocked products (no stock row, qty 0)
        # are still counted as low stock instead of being dropped by an inner join.
        def _low_stock():
            stock_totals = db.query(
                WarehouseStock.product_id.label("product_id"),
                func.sum(WarehouseStock.quantity).label("total_qty"),
            ).join(
                Warehouse, Warehouse.id == WarehouseStock.warehouse_id
            ).filter(Warehouse.is_active == True).group_by(WarehouseStock.product_id).subquery()
            return db.query(func.count()).select_from(Product).outerjoin(
                stock_totals, stock_totals.c.product_id == Product.id
            ).filter(
                Product.is_active == True,
                Product.low_stock_threshold > 0,
                func.coalesce(stock_totals.c.total_qty, 0) <= Product.low_stock_threshold,
            ).scalar() or 0
        low_stock_count = safe(_low_stock, 0)

        # Cash balance (last approved closing)
        def _cash():
            last = db.query(CashClosing).filter(
                CashClosing.status == CashClosingStatus.approved
            ).order_by(desc(CashClosing.closing_date)).first()
            return float(last.closing_balance) if last else 0.0
        cash_balance = safe(_cash)

        # Today's collections
        today_collections = safe(lambda: float(
            db.query(func.coalesce(func.sum(CustomerPayment.amount), 0)).filter(
                CustomerPayment.payment_date == today,
            ).scalar() or 0))

        # Top 5 customers by sales this month (gross + net)
        def _top_customers():
            rows = db.query(
                Customer.trade_name,
                func.sum(Invoice.total_amount).label("total"),
                func.sum(Invoice.taxable_amount).label("total_net"),
            ).join(Invoice, Invoice.customer_id == Customer.id).filter(
                Invoice.invoice_date >= month_start,
                Invoice.is_cancelled == False,
                Invoice.document_type.in_(SALES),
            ).group_by(Customer.id, Customer.trade_name).order_by(
                func.sum(Invoice.total_amount).desc()
            ).limit(5).all()
            return [{"name": r[0], "total": float(r[1] or 0), "total_net": float(r[2] or 0)} for r in rows]
        top_customers = safe(_top_customers, [])

        # Recent invoices
        def _recent():
            rows = db.query(Invoice, Customer).join(
                Customer, Invoice.customer_id == Customer.id
            ).filter(
                Invoice.document_type.in_(SALES),
                Invoice.is_cancelled == False,
            ).order_by(desc(Invoice.created_at)).limit(5).all()
            return [
                {
                    "id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "customer_name": cust.trade_name,
                    "total_amount": float(inv.total_amount),
                    "outstanding_amount": float(inv.outstanding_amount),
                    "invoice_date": inv.invoice_date,
                }
                for inv, cust in rows
            ]
        recent_invoices = safe(_recent, [])

        # Monthly sales trend (last 6 calendar months, oldest first), gross + net.
        # Single grouped query; walk months in Python so gaps render as 0 and a
        # fixed 30-day step can't duplicate/skip a month.
        def _trend():
            months = []
            y, mo = today.year, today.month
            for _ in range(6):
                months.append((y, mo))
                mo -= 1
                if mo == 0:
                    mo, y = 12, y - 1
            trend_start = date(months[-1][0], months[-1][1], 1)
            rows = db.query(
                func.year(Invoice.invoice_date).label("y"),
                func.month(Invoice.invoice_date).label("m"),
                func.sum(Invoice.total_amount).label("gross"),
                func.sum(Invoice.taxable_amount).label("net"),
            ).filter(
                Invoice.invoice_date >= trend_start,
                Invoice.invoice_date < (today.replace(day=1) + timedelta(days=32)).replace(day=1),
                Invoice.is_cancelled == False,
                Invoice.document_type.in_(SALES),
            ).group_by("y", "m").all()
            lookup = {(int(r.y), int(r.m)): (float(r.gross or 0), float(r.net or 0)) for r in rows}
            out = []
            for y, mo in reversed(months):
                g, n = lookup.get((y, mo), (0.0, 0.0))
                out.append({
                    "month": date(y, mo, 1).strftime("%b %Y"),
                    "sales": g, "sales_net": n,
                })
            return out
        trend = safe(_trend, [])

        return {
            "today_sales": today_sales,
            "today_sales_net": today_sales_net,
            "month_sales": month_sales,
            "month_sales_net": month_sales_net,
            "fy_sales": fy_sales,
            "fy_sales_net": fy_sales_net,
            "total_outstanding": total_outstanding,
            "overdue_amount": overdue,
            "total_payables": total_payables,
            "month_purchases": month_purchases,
            "fy_purchases": fy_purchases,
            "stock_value": stock_value,
            "pending_deliveries": pending_deliveries,
            "low_stock_count": low_stock_count,
            "cash_balance": cash_balance,
            "today_collections": today_collections,
            "top_customers": top_customers,
            "recent_invoices": recent_invoices,
            "monthly_trend": trend,
            "financial_year": financial_year,
            "as_of": today,
        }


class SalesReportService:

    @staticmethod
    def generate(db: Session,
                 date_from: date, date_to: date,
                 customer_id: Optional[int] = None,
                 product_id: Optional[int] = None,
                 salesperson_id: Optional[int] = None,
                 document_type: Optional[str] = None,
                 financial_year: Optional[str] = None) -> dict:

        q = db.query(Invoice).filter(
            Invoice.invoice_date >= date_from,
            Invoice.invoice_date <= date_to,
            Invoice.is_cancelled == False,
        )
        if customer_id:
            q = q.filter(Invoice.customer_id == customer_id)
        if document_type:
            q = q.filter(Invoice.document_type == document_type)
        else:
            q = q.filter(Invoice.document_type.in_([
                DocumentType.b2b_invoice, DocumentType.b2c_invoice
            ]))
        if financial_year:
            q = q.filter(Invoice.financial_year == financial_year)

        invoices = q.order_by(desc(Invoice.invoice_date)).all()

        rows = []
        total_taxable = total_tax = total_amount = total_outstanding = Decimal("0")

        for inv in invoices:
            cust = db.query(Customer).filter(Customer.id == inv.customer_id).first()
            rows.append({
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "customer_name": cust.trade_name if cust else None,
                "customer_gstin": cust.gstin if cust else None,
                "document_type": inv.document_type,
                "taxable_amount": inv.taxable_amount,
                "total_cgst": inv.total_cgst,
                "total_sgst": inv.total_sgst,
                "total_igst": inv.total_igst,
                "total_amount": inv.total_amount,
                "paid_amount": inv.paid_amount,
                "outstanding_amount": inv.outstanding_amount,
                "irn": inv.irn,
                "financial_year": inv.financial_year,
            })
            total_taxable += inv.taxable_amount
            total_tax += inv.total_cgst + inv.total_sgst + inv.total_igst
            total_amount += inv.total_amount
            total_outstanding += inv.outstanding_amount

        return {
            "date_from": date_from, "date_to": date_to,
            "invoice_count": len(rows),
            "rows": rows,
            "summary": {
                "total_taxable": float(total_taxable),
                "total_tax": float(total_tax),
                "total_amount": float(total_amount),
                "total_outstanding": float(total_outstanding),
                "total_collected": float(total_amount - total_outstanding),
            }
        }


class PurchaseReportService:

    @staticmethod
    def generate(db: Session,
                 date_from: date, date_to: date,
                 vendor_id: Optional[int] = None,
                 financial_year: Optional[str] = None) -> dict:

        q = db.query(Purchase).filter(
            Purchase.invoice_date >= date_from,
            Purchase.invoice_date <= date_to,
            Purchase.is_cancelled == False,
        )
        if vendor_id:
            q = q.filter(Purchase.vendor_id == vendor_id)
        if financial_year:
            q = q.filter(Purchase.financial_year == financial_year)

        purchases = q.order_by(desc(Purchase.invoice_date)).all()
        rows = []
        total_taxable = total_tax = total_amount = Decimal("0")

        for p in purchases:
            v = db.query(Vendor).filter(Vendor.id == p.vendor_id).first()
            rows.append({
                "vendor_invoice_number": p.vendor_invoice_number,
                "invoice_date": p.invoice_date,
                "vendor_name": v.trade_name if v else None,
                "vendor_gstin": v.gstin if v else None,
                "subtotal": p.subtotal,
                "total_cgst": p.total_cgst,
                "total_sgst": p.total_sgst,
                "total_igst": p.total_igst,
                "total_amount": p.total_amount,
                "gst_type": p.gst_type,
                "financial_year": p.financial_year,
            })
            total_taxable += p.subtotal
            total_tax += p.total_cgst + p.total_sgst + p.total_igst
            total_amount += p.total_amount

        return {
            "date_from": date_from, "date_to": date_to,
            "purchase_count": len(rows), "rows": rows,
            "summary": {
                "total_taxable": float(total_taxable),
                "total_tax": float(total_tax),
                "total_amount": float(total_amount),
            }
        }


class StockReportService:

    @staticmethod
    def generate(db: Session,
                 warehouse_id: Optional[int] = None,
                 category_id: Optional[int] = None,
                 low_stock_only: bool = False) -> dict:

        q = db.query(WarehouseStock, Product, Warehouse).join(
            Product, WarehouseStock.product_id == Product.id
        ).join(
            Warehouse, WarehouseStock.warehouse_id == Warehouse.id
        ).filter(Product.is_active == True, Warehouse.is_active == True)

        if warehouse_id:
            q = q.filter(WarehouseStock.warehouse_id == warehouse_id)
        if category_id:
            q = q.filter(Product.category_id == category_id)
        if low_stock_only:
            q = q.filter(WarehouseStock.quantity <= Product.low_stock_threshold)

        rows_raw = q.order_by(Product.part_name, Warehouse.name).all()

        product_map = {}
        total_value = Decimal("0")

        for ws, prod, wh in rows_raw:
            fifo_val = db.query(func.sum(StockEntry.remaining_qty * StockEntry.unit_cost)).filter(
                StockEntry.warehouse_id == wh.id,
                StockEntry.product_id == prod.id,
                StockEntry.remaining_qty > 0,
            ).scalar() or Decimal("0")

            if prod.id not in product_map:
                cat = db.query(Category).filter(Category.id == prod.category_id).first()
                product_map[prod.id] = {
                    "product_id": prod.id,
                    "part_code": prod.part_code,
                    "part_name": prod.part_name,
                    "category_name": cat.name if cat else None,
                    "unit_of_measure": prod.unit_of_measure,
                    "selling_price": float(prod.selling_price),
                    "purchase_cost": float(prod.purchase_cost),
                    "low_stock_threshold": float(prod.low_stock_threshold),
                    "total_quantity": Decimal("0"),
                    "total_fifo_value": Decimal("0"),
                    "warehouses": [],
                }
            item = product_map[prod.id]
            item["total_quantity"] += ws.quantity
            item["total_fifo_value"] += fifo_val
            item["warehouses"].append({
                "warehouse_name": wh.name,
                "quantity": float(ws.quantity),
                "fifo_value": float(fifo_val),
            })
            total_value += fifo_val

        rows = list(product_map.values())
        for r in rows:
            r["total_quantity"] = float(r["total_quantity"])
            r["total_fifo_value"] = float(r["total_fifo_value"])
            r["is_low_stock"] = r["total_quantity"] <= r["low_stock_threshold"]

        return {
            "as_of_date": date.today(),
            "product_count": len(rows),
            "total_stock_value": float(total_value),
            "low_stock_count": sum(1 for r in rows if r["is_low_stock"]),
            "rows": rows,
        }


class StockClearanceService:
    """Per-batch (FIFO layer) view to guide clearance-sale discounting.

    Discount itself is keyed in manually at invoice time; this report only
    tells staff which batches are old/limited and how much profit cushion
    each one still has down to the product's floor_price. Older, cheaper
    batches show a larger profit_at_floor and are the ones to discount.
    Nothing here is booked profit — these are remaining (unsold) layers.
    """

    _INBOUND = [
        StockTransactionType.purchase, StockTransactionType.return_in,
        StockTransactionType.transfer_in, StockTransactionType.adjustment_in,
    ]

    @staticmethod
    def generate(db: Session,
                 warehouse_id: Optional[int] = None,
                 category_id: Optional[int] = None,
                 min_age_days: int = 0) -> dict:

        today = date.today()

        q = db.query(StockEntry, Product, Warehouse).join(
            Product, StockEntry.product_id == Product.id
        ).join(
            Warehouse, StockEntry.warehouse_id == Warehouse.id
        ).filter(
            Product.is_active == True,
            Warehouse.is_active == True,
            StockEntry.remaining_qty > 0,
            StockEntry.transaction_type.in_(StockClearanceService._INBOUND),
        )

        if warehouse_id:
            q = q.filter(StockEntry.warehouse_id == warehouse_id)
        if category_id:
            q = q.filter(Product.category_id == category_id)

        rows_raw = q.order_by(
            Product.part_name, StockEntry.batch_date, StockEntry.id
        ).all()

        rows = []
        total_value = Decimal("0")
        for se, prod, wh in rows_raw:
            age = (today - se.batch_date).days if se.batch_date else 0
            if min_age_days and age < min_age_days:
                continue

            unit_cost = se.unit_cost or Decimal("0")
            remaining = se.remaining_qty or Decimal("0")
            floor = prod.floor_price or Decimal("0")
            profit_at_floor = floor - unit_cost
            batch_value = remaining * unit_cost
            total_value += batch_value

            rows.append({
                "entry_id": se.id,
                "product_id": prod.id,
                "part_code": prod.part_code,
                "part_name": prod.part_name,
                "warehouse_name": wh.name,
                "batch_date": se.batch_date,
                "age_days": age,
                "remaining_qty": float(remaining),
                "unit_cost": float(unit_cost),
                "floor_price": float(floor),
                "b2b_price": float(prod.b2b_price or 0),
                "b2c_price": float(prod.b2c_price or 0),
                "mrp": float(prod.mrp or 0),
                "profit_at_floor": float(profit_at_floor),
                "margin_at_floor_pct": float(round(profit_at_floor / floor * 100, 2)) if floor > 0 else 0.0,
                "batch_value": float(batch_value),
            })

        return {
            "as_of_date": today,
            "batch_count": len(rows),
            "product_count": len({r["product_id"] for r in rows}),
            "total_stock_value": float(total_value),
            "rows": rows,
        }


class PnLService:

    @staticmethod
    def generate(db: Session, financial_year: Optional[str] = None,
                 date_from: Optional[date] = None,
                 date_to: Optional[date] = None) -> dict:
        # A custom date range takes priority; otherwise fall back to the whole FY.
        use_range = date_from is not None and date_to is not None
        if not use_range and not financial_year:
            financial_year = get_financial_year()

        def _invoice_period(q):
            if use_range:
                return q.filter(Invoice.invoice_date >= date_from,
                                Invoice.invoice_date <= date_to)
            return q.filter(Invoice.financial_year == financial_year)

        def _expense_period(q):
            if use_range:
                return q.filter(Expense.expense_date >= date_from,
                                Expense.expense_date <= date_to)
            return q.filter(Expense.financial_year == financial_year)

        sale_types = [DocumentType.b2b_invoice, DocumentType.b2c_invoice]

        # Revenue from sales
        revenue = _invoice_period(db.query(func.sum(Invoice.taxable_amount)).filter(
            Invoice.is_cancelled == False,
            Invoice.document_type.in_(sale_types),
        )).scalar() or Decimal("0")

        # COGS from FIFO cost on invoice items
        cogs_result = _invoice_period(db.query(func.sum(
            InvoiceItem.fifo_cost * InvoiceItem.quantity
        )).join(Invoice, InvoiceItem.invoice_id == Invoice.id).filter(
            Invoice.is_cancelled == False,
            Invoice.document_type.in_(sale_types),
            InvoiceItem.fifo_cost.isnot(None),
        )).scalar() or Decimal("0")

        gross_profit = revenue - cogs_result
        gross_margin = (gross_profit / revenue * 100) if revenue > 0 else Decimal("0")

        # Expenses
        expenses = _expense_period(db.query(func.sum(Expense.amount)).filter(
            Expense.status == ExpenseStatus.approved,
        )).scalar() or Decimal("0")

        # Expense by category
        exp_by_cat = _expense_period(db.query(
            Expense.category,
            func.sum(Expense.amount).label("total"),
        ).filter(
            Expense.status == ExpenseStatus.approved,
        )).group_by(Expense.category).all()

        net_profit = gross_profit - expenses
        net_margin = (net_profit / revenue * 100) if revenue > 0 else Decimal("0")

        invoice_count = _invoice_period(db.query(func.count(Invoice.id)).filter(
            Invoice.is_cancelled == False,
            Invoice.document_type.in_(sale_types),
        )).scalar() or 0

        return {
            "financial_year": None if use_range else financial_year,
            "date_from": date_from if use_range else None,
            "date_to": date_to if use_range else None,
            "revenue": float(revenue),
            "cogs": float(cogs_result),
            "gross_profit": float(gross_profit),
            "gross_margin_pct": float(gross_margin.quantize(Decimal("0.01"))),
            "total_expenses": float(expenses),
            "expenses_by_category": [
                {"category": r[0], "amount": float(r[1])} for r in exp_by_cat
            ],
            "net_profit": float(net_profit),
            "net_margin_pct": float(net_margin.quantize(Decimal("0.01"))),
            "invoice_count": invoice_count,
        }


class DayBookService:

    @staticmethod
    def generate(db: Session, for_date: date) -> dict:
        entries = []

        # Sales invoices
        invoices = db.query(Invoice, Customer).join(
            Customer, Invoice.customer_id == Customer.id
        ).filter(
            Invoice.invoice_date == for_date,
            Invoice.is_cancelled == False,
            Invoice.document_type.in_([DocumentType.b2b_invoice, DocumentType.b2c_invoice]),
        ).all()
        for inv, cust in invoices:
            entries.append({
                "type": "sale", "reference": inv.invoice_number,
                "party": cust.trade_name, "narration": f"Sales invoice — {cust.trade_name}",
                "debit": float(inv.total_amount), "credit": 0,
            })

        # Purchases
        purchases = db.query(Purchase, Vendor).join(
            Vendor, Purchase.vendor_id == Vendor.id
        ).filter(
            Purchase.invoice_date == for_date,
            Purchase.is_cancelled == False,
        ).all()
        for p, v in purchases:
            entries.append({
                "type": "purchase", "reference": p.vendor_invoice_number,
                "party": v.trade_name, "narration": f"Purchase — {v.trade_name}",
                "debit": 0, "credit": float(p.total_amount),
            })

        # Receipts
        receipts = db.query(CustomerPayment, Customer).join(
            Customer, CustomerPayment.customer_id == Customer.id
        ).filter(CustomerPayment.payment_date == for_date).all()
        for r, c in receipts:
            entries.append({
                "type": "receipt", "reference": r.payment_number,
                "party": c.trade_name, "narration": f"Receipt from {c.trade_name}",
                "debit": 0, "credit": float(r.amount),
            })

        # Expenses
        exps = db.query(Expense).filter(
            Expense.expense_date == for_date,
            Expense.status == ExpenseStatus.approved,
        ).all()
        for e in exps:
            entries.append({
                "type": "expense", "reference": e.expense_number,
                "party": "—", "narration": e.description,
                "debit": float(e.amount), "credit": 0,
            })

        total_debit = sum(e["debit"] for e in entries)
        total_credit = sum(e["credit"] for e in entries)

        return {
            "date": for_date,
            "entries": entries,
            "entry_count": len(entries),
            "total_debit": total_debit,
            "total_credit": total_credit,
        }


class LedgerReportService:

    @staticmethod
    def customer_ledger(db: Session, customer_id: int,
                        date_from: date, date_to: date) -> dict:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

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

        entries = db.query(LedgerEntry).filter(
            LedgerEntry.customer_id == customer_id,
            LedgerEntry.entry_date >= date_from,
            LedgerEntry.entry_date <= date_to,
        ).order_by(LedgerEntry.entry_date).all()

        rows = []
        running = opening_balance
        for e in entries:
            if e.transaction_type == TransactionType.debit:
                running += e.amount
                rows.append({"date": e.entry_date, "narration": e.narration,
                             "debit": float(e.amount), "credit": 0, "balance": float(running)})
            else:
                running -= e.amount
                rows.append({"date": e.entry_date, "narration": e.narration,
                             "debit": 0, "credit": float(e.amount), "balance": float(running)})

        return {
            "customer_id": customer_id,
            "customer_name": customer.trade_name,
            "customer_gstin": customer.gstin,
            "date_from": date_from, "date_to": date_to,
            "opening_balance": float(opening_balance),
            "closing_balance": float(running),
            "rows": rows,
        }

    @staticmethod
    def vendor_ledger(db: Session, vendor_id: int,
                      date_from: date, date_to: date) -> dict:
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        opening_credit = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.vendor_id == vendor_id,
            LedgerEntry.transaction_type == TransactionType.credit,
            LedgerEntry.entry_date < date_from,
        ).scalar() or Decimal("0")
        opening_debit = db.query(func.sum(LedgerEntry.amount)).filter(
            LedgerEntry.vendor_id == vendor_id,
            LedgerEntry.transaction_type == TransactionType.debit,
            LedgerEntry.entry_date < date_from,
        ).scalar() or Decimal("0")
        opening_balance = opening_credit - opening_debit

        entries = db.query(LedgerEntry).filter(
            LedgerEntry.vendor_id == vendor_id,
            LedgerEntry.entry_date >= date_from,
            LedgerEntry.entry_date <= date_to,
        ).order_by(LedgerEntry.entry_date).all()

        rows = []
        running = opening_balance
        for e in entries:
            if e.transaction_type == TransactionType.credit:
                running += e.amount
                rows.append({"date": e.entry_date, "narration": e.narration,
                             "debit": 0, "credit": float(e.amount), "balance": float(running)})
            else:
                running -= e.amount
                rows.append({"date": e.entry_date, "narration": e.narration,
                             "debit": float(e.amount), "credit": 0, "balance": float(running)})

        return {
            "vendor_id": vendor_id,
            "vendor_name": vendor.trade_name,
            "vendor_gstin": vendor.gstin,
            "date_from": date_from, "date_to": date_to,
            "opening_balance": float(opening_balance),
            "closing_balance": float(running),
            "rows": rows,
        }