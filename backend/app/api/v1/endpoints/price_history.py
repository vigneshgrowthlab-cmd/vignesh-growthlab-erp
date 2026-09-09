"""Price History & Valuation API endpoints."""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from decimal import Decimal

from app.db.session import get_db
from app.models.models import User
from app.core.security import get_current_user, require_admin, require_super_admin, is_super_admin
from app.services.price_history_service import (
    get_price_history, record_price_change, get_stock_valuation,
    get_margin_trend, activate_scheduled_prices, get_recent_changes,
    PRICE_TYPES, PRICE_LABELS,
)

price_history_router = APIRouter(prefix="/price-history", tags=["price-history"])


@price_history_router.get("/recent")
async def recent_price_changes(
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to 1st of current month"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Recent price changes across all products in a date range (super-admin)."""
    from datetime import date as _date
    today = _date.today()
    try:
        end = _date.fromisoformat(to_date) if to_date else today
        start = _date.fromisoformat(from_date) if from_date else today.replace(day=1)
    except ValueError:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=400, detail="Dates must be YYYY-MM-DD")
    if start > end:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=400, detail="from_date cannot be after to_date")
    return get_recent_changes(db, start, end, page, page_size)


@price_history_router.get("/{product_id}")
async def get_product_price_history(
    product_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Activate any due scheduled prices (effective_from <= today) before
    # rendering history, so the user sees an up-to-date view without
    # needing an invoice/purchase to trigger activation.
    activated = activate_scheduled_prices(db, product_id)
    if activated:
        db.commit()
    return get_price_history(db, product_id, limit)


@price_history_router.post("/{product_id}/update")
async def update_product_price(
    product_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a price type for a product. If effective_from is future, schedules it."""
    price_type = payload.get("price_type")
    price = payload.get("price")
    effective_from = payload.get("effective_from")
    change_reason = payload.get("change_reason")
    if not price_type or price_type not in PRICE_TYPES:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=400, detail=f"Invalid price_type. Must be one of {PRICE_TYPES}")
    if not price or float(price) <= 0:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=400, detail="Price must be greater than 0")
    if not effective_from:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=400, detail="effective_from date is required")
    eff_date = date.fromisoformat(effective_from)
    record_price_change(
        db, product_id, price_type, Decimal(str(price)),
        eff_date, current_user.id, change_reason,
        is_scheduled=(eff_date > date.today())
    )
    db.commit()
    return get_price_history(db, product_id)


@price_history_router.get("/valuation/stock")
async def stock_valuation_report(
    warehouse_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Stock valuation — FIFO cost vs latest purchase cost.

    FIFO/latest valuation is returned to admins; the margin columns are
    profit data and stripped for anyone who is not a super-admin.
    """
    data = get_stock_valuation(db, warehouse_id)
    if not is_super_admin(current_user):
        for item in data.get("items", []):
            item.pop("fifo_margin_pct", None)
            item.pop("latest_margin_pct", None)
    return data


@price_history_router.get("/{product_id}/margin-trend")
async def margin_trend(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return get_margin_trend(db, product_id)


@price_history_router.get("/alerts/unread")
async def get_price_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get unread price alerts — low margin, below cost, scheduled activation.

    Activates any due scheduled prices first so freshly-activated entries
    surface as `scheduled_activated` alerts on the same call.
    """
    activated = activate_scheduled_prices(db)
    if activated:
        db.commit()
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT pa.id, pa.product_id, p.part_code, p.part_name,
               pa.alert_type, pa.message, pa.severity,
               pa.is_read, pa.email_sent, pa.created_at
        FROM price_alerts pa
        JOIN products p ON p.id = pa.product_id
        WHERE pa.is_read = FALSE
        ORDER BY pa.created_at DESC
        LIMIT 100
    """)).fetchall()
    return [
        {"id": r[0], "product_id": r[1], "part_code": r[2], "part_name": r[3],
         "alert_type": r[4], "message": r[5], "severity": r[6],
         "is_read": r[7], "email_sent": r[8], "created_at": str(r[9])}
        for r in rows
    ]


@price_history_router.get("/alerts")
async def get_all_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """All price alerts (read and unread), unread first then newest first.

    Activates any due scheduled prices first so freshly-activated entries
    surface on the same call.
    """
    activated = activate_scheduled_prices(db)
    if activated:
        db.commit()
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT pa.id, pa.product_id, p.part_code, p.part_name,
               pa.alert_type, pa.message, pa.severity,
               pa.is_read, pa.email_sent, pa.created_at
        FROM price_alerts pa
        JOIN products p ON p.id = pa.product_id
        ORDER BY pa.is_read ASC, pa.created_at DESC
        LIMIT 200
    """)).fetchall()
    return [
        {"id": r[0], "product_id": r[1], "part_code": r[2], "part_name": r[3],
         "alert_type": r[4], "message": r[5], "severity": r[6],
         "is_read": r[7], "email_sent": r[8], "created_at": str(r[9])}
        for r in rows
    ]


@price_history_router.post("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from sqlalchemy import text
    db.execute(text("UPDATE price_alerts SET is_read = TRUE WHERE id = :id"), {"id": alert_id})
    db.commit()
    return {"message": "Alert marked as read"}


@price_history_router.post("/alerts/{alert_id}/unread")
async def mark_alert_unread(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from sqlalchemy import text
    db.execute(text("UPDATE price_alerts SET is_read = FALSE WHERE id = :id"), {"id": alert_id})
    db.commit()
    return {"message": "Alert marked as unread"}


@price_history_router.post("/alerts/read-all")
async def mark_all_read(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from sqlalchemy import text
    db.execute(text("UPDATE price_alerts SET is_read = TRUE WHERE is_read = FALSE"))
    db.commit()
    return {"message": "All alerts marked as read"}


@price_history_router.post("/activate-due")
async def activate_due_prices(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Activate any scheduled prices whose effective_from <= today (IST).

    Frontend hits this when opening transactional create screens
    (Invoice Form, Purchase Form) so the user sees freshly-activated
    prices before they start filling line items.
    Returns the count of rows activated for diagnostics.
    """
    count = activate_scheduled_prices(db)
    if count:
        db.commit()
    return {"activated": count}


@price_history_router.delete("/scheduled/{price_id}")
async def cancel_scheduled_price(
    price_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Cancel a scheduled (future) price change."""
    from sqlalchemy import text as _sqc
    row = db.execute(_sqc(
        "SELECT id, product_id, price_type, price, effective_from FROM product_prices WHERE id=:id AND is_scheduled=TRUE AND is_active=FALSE"
    ), {"id": price_id}).fetchone()
    if not row:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=404, detail="Scheduled price not found or already activated")
    db.execute(_sqc(
        "DELETE FROM product_prices WHERE id=:id"
    ), {"id": price_id})
    db.commit()
    return {"message": "Scheduled price cancelled", "price_id": price_id}


@price_history_router.get("/scheduled/all")
async def get_all_scheduled_prices(
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Get all pending scheduled prices across all products, with optional search.

    Auto-activates any due scheduled prices first so the listing only shows
    genuinely future entries (effective_from > today).
    """
    activated = activate_scheduled_prices(db)
    if activated:
        db.commit()
    from sqlalchemy import text as _sqall
    search_clause = ""
    params = {"offset": (page - 1) * page_size, "limit": page_size}
    if search:
        search_clause = "AND (p.part_name LIKE :s OR p.part_code LIKE :s)"
        params["s"] = f"%{search}%"

    rows = db.execute(_sqall(f"""
        SELECT pp.id, pp.product_id, p.part_code, p.part_name,
               pp.price_type, pp.price, pp.previous_price,
               pp.effective_from, pp.change_reason, pp.created_at,
               u.full_name as scheduled_by,
               -- current active price for same type
               (SELECT ap.price FROM product_prices ap
                WHERE ap.product_id = pp.product_id
                AND ap.price_type = pp.price_type
                AND ap.is_active = TRUE
                ORDER BY ap.effective_from DESC LIMIT 1) as current_price
        FROM product_prices pp
        JOIN products p ON p.id = pp.product_id
        LEFT JOIN users u ON u.id = pp.created_by
        WHERE pp.is_scheduled = TRUE AND pp.is_active = FALSE
        {search_clause}
        ORDER BY pp.effective_from ASC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(_sqall(f"""
        SELECT COUNT(*) FROM product_prices pp
        JOIN products p ON p.id = pp.product_id
        WHERE pp.is_scheduled = TRUE AND pp.is_active = FALSE
        {search_clause}
    """), {k: v for k, v in params.items() if k not in ('offset', 'limit')}).scalar()

    items = []
    for r in rows:
        new_price = float(r[5] or 0)
        cur_price = float(r[11] or 0) if r[11] else None
        change_pct = round(((new_price - cur_price) / cur_price * 100), 2) if cur_price and cur_price > 0 else None
        items.append({
            "id": r[0],
            "product_id": r[1],
            "part_code": r[2],
            "part_name": r[3],
            "price_type": r[4],
            "price_type_label": PRICE_LABELS.get(r[4], r[4]),
            "new_price": new_price,
            "previous_price": float(r[6] or 0) if r[6] else None,
            "current_price": cur_price,
            "change_pct": change_pct,
            "effective_from": str(r[7]),
            "change_reason": r[8],
            "scheduled_at": str(r[9]),
            "scheduled_by": r[10],
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }