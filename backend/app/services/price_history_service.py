"""Price History Service — multi-type pricing with effective date support."""
import json
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text, desc
from fastapi import HTTPException

from app.services.config_service import ConfigService

PRICE_TYPES = ["purchase_cost", "b2b_price", "b2c_price", "mrp", "floor_price"]

PRICE_LABELS = {
    "purchase_cost": "Purchase Cost",
    "b2b_price": "B2B Price",
    "b2c_price": "B2C Price",
    "mrp": "MRP",
    "floor_price": "Floor Price",
}

# Force activation logic to use IST regardless of the server's local timezone.
# Matches the MariaDB session timezone set in db/session.py (+05:30) and the
# project-wide assumption that all dates are Indian financial-year dates.
IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist() -> date:
    """Return today's date in IST (Asia/Kolkata)."""
    return datetime.now(IST).date()


def activate_scheduled_prices(db: Session, product_id: Optional[int] = None):
    """Activate scheduled prices whose effective_from <= today (IST).
    Called on app startup, on price_history reads, and on purchase create."""
    today = _today_ist().isoformat()
    try:
        where = "AND product_id = :pid" if product_id else ""
        params = {"today": today}
        if product_id:
            params["pid"] = product_id

        rows = db.execute(text(f"""
            SELECT id, product_id, price_type, price, previous_price
            FROM product_prices
            WHERE is_scheduled = TRUE AND is_active = FALSE
            AND effective_from <= :today
            {where}
        """), params).fetchall()

        for row in rows:
            pid, ptype, price = row[1], row[2], row[3]
            # Deactivate current active price for this type
            db.execute(text("""
                UPDATE product_prices
                SET is_active = FALSE, effective_to = :today
                WHERE product_id = :pid AND price_type = :ptype
                AND is_active = TRUE AND is_scheduled = FALSE
            """), {"today": today, "pid": pid, "ptype": ptype})

            # Activate the scheduled price
            db.execute(text("""
                UPDATE product_prices
                SET is_active = TRUE, is_scheduled = FALSE
                WHERE id = :id
            """), {"id": row[0]})

            # Update product table column
            col_map = {
                "purchase_cost": "purchase_cost",
                "b2b_price": "b2b_price",
                "b2c_price": "b2c_price",
                "mrp": "mrp",
                "floor_price": "floor_price",
            }
            col = col_map.get(ptype)
            if col:
                db.execute(text(f"UPDATE products SET {col} = :price WHERE id = :pid"),
                           {"price": float(price), "pid": pid})

            # Create price_alert for activation
            prod_row = db.execute(text("SELECT part_name FROM products WHERE id = :id"),
                                  {"id": pid}).fetchone()
            pname = prod_row[0] if prod_row else f"Product {pid}"
            db.execute(text("""
                INSERT INTO price_alerts (product_id, alert_type, message, severity)
                VALUES (:pid, 'scheduled_activated',
                    :msg, 'info')
            """), {"pid": pid, "msg": f"{PRICE_LABELS.get(ptype, ptype)} for {pname} activated: ₹{price}"})

        # Note: caller is responsible for db.commit()
        # Only commit here if called standalone (not within a transaction)
        return len(rows)
    except Exception as e:
        print(f"[PRICE_SCHEDULE] Activation failed: {e}")
        return 0


def record_price_change(db: Session, product_id: int, price_type: str,
                         new_price: Decimal, effective_from: date,
                         created_by: int, change_reason: str = None,
                         is_scheduled: bool = False):
    """Record a price change. If is_scheduled and future date, mark as pending."""
    today = _today_ist()
    is_future = effective_from > today

    try:
        # Get current active price for this type
        current = db.execute(text("""
            SELECT id, price FROM product_prices
            WHERE product_id = :pid AND price_type = :ptype AND is_active = TRUE
            ORDER BY effective_from DESC LIMIT 1
        """), {"pid": product_id, "ptype": price_type}).fetchone()

        previous_price = current[1] if current else None

        if is_future:
            # Future price — store as scheduled, don't activate
            db.execute(text("""
                INSERT INTO product_prices
                (product_id, price_type, price, previous_price, effective_from,
                 is_active, is_scheduled, change_reason, created_by)
                VALUES (:pid, :ptype, :price, :prev, :eff,
                        FALSE, TRUE, :reason, :uid)
            """), {
                "pid": product_id, "ptype": price_type, "price": float(new_price),
                "prev": float(previous_price) if previous_price else None,
                "eff": effective_from.isoformat(), "reason": change_reason, "uid": created_by
            })
        else:
            # Immediate — deactivate current, insert new active
            if current:
                db.execute(text("""
                    UPDATE product_prices SET is_active = FALSE, effective_to = :today
                    WHERE id = :id
                """), {"today": today.isoformat(), "id": current[0]})

            db.execute(text("""
                INSERT INTO product_prices
                (product_id, price_type, price, previous_price, effective_from,
                 is_active, is_scheduled, change_reason, created_by)
                VALUES (:pid, :ptype, :price, :prev, :eff,
                        TRUE, FALSE, :reason, :uid)
            """), {
                "pid": product_id, "ptype": price_type, "price": float(new_price),
                "prev": float(previous_price) if previous_price else None,
                "eff": effective_from.isoformat(), "reason": change_reason, "uid": created_by
            })

            # Update product table column
            col_map = {"purchase_cost": "purchase_cost", "b2b_price": "b2b_price",
                       "b2c_price": "b2c_price", "mrp": "mrp", "floor_price": "floor_price"}
            col = col_map.get(price_type)
            if col:
                db.execute(text(f"UPDATE products SET {col} = :price WHERE id = :pid"),
                           {"price": float(new_price), "pid": product_id})

            # Check alerts for b2b/b2c below cost
            _check_price_alerts(db, product_id, price_type, new_price, previous_price)

    except Exception as e:
        print(f"[PRICE_CHANGE] Failed: {e}")


def _check_price_alerts(db: Session, product_id: int, price_type: str,
                         new_price: Decimal, previous_price):
    """Generate alerts for below-cost or low-margin pricing."""
    try:
        prod = db.execute(text(
            "SELECT part_name, purchase_cost, b2b_price, b2c_price, min_margin_pct FROM products WHERE id = :id"
        ), {"id": product_id}).fetchone()
        if not prod:
            return

        pname, cost, b2b, b2c, min_margin = prod
        cost = Decimal(str(cost or 0))

        if price_type in ("b2b_price", "b2c_price") and cost > 0:
            label = PRICE_LABELS.get(price_type, price_type)
            p = Decimal(str(new_price))

            if p < cost:
                db.execute(text("""
                    INSERT INTO price_alerts (product_id, alert_type, message, severity)
                    VALUES (:pid, 'below_cost', :msg, 'critical')
                """), {"pid": product_id,
                       "msg": f"{pname}: {label} ₹{p} is BELOW purchase cost ₹{cost}"})

            elif p > 0:
                margin = ((p - cost) / p * 100)
                min_m = Decimal(str(min_margin or ConfigService.get_decimal(db, "business.min_margin_pct", default=Decimal("10"))))
                if margin < min_m:
                    db.execute(text("""
                        INSERT INTO price_alerts (product_id, alert_type, message, severity)
                        VALUES (:pid, 'low_margin', :msg, 'warning')
                    """), {"pid": product_id,
                           "msg": f"{pname}: {label} margin {margin:.1f}% below threshold {min_m}% (on price)"})
    except Exception as e:
        print(f"[PRICE_ALERT] Failed: {e}")


def get_price_history(db: Session, product_id: int, limit: int = 50) -> dict:
    """Get all price type history for a product."""
    try:
        # Ensure table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS product_prices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                price_type VARCHAR(20) NOT NULL,
                price DECIMAL(12,2) NOT NULL,
                previous_price DECIMAL(12,2),
                effective_from DATE NOT NULL,
                effective_to DATE,
                is_active BOOLEAN DEFAULT TRUE,
                is_scheduled BOOLEAN DEFAULT FALSE,
                change_reason VARCHAR(200),
                notes TEXT,
                created_by INT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_pp_product_type (product_id, price_type)
            )
        """))

        prod = db.execute(text("""
            SELECT part_code, part_name, purchase_cost,
                   COALESCE(b2b_price, 0), COALESCE(b2c_price, 0), COALESCE(mrp, 0)
            FROM products WHERE id = :id
        """), {"id": product_id}).fetchone()

        if not prod:
            raise HTTPException(status_code=404, detail="Product not found")

        # Get history for all price types
        rows = db.execute(text("""
            SELECT pp.id, pp.price_type, pp.price, pp.previous_price,
                   pp.effective_from, pp.effective_to, pp.is_active, pp.is_scheduled,
                   pp.change_reason, pp.created_at,
                   u.full_name as changed_by
            FROM product_prices pp
            LEFT JOIN users u ON u.id = pp.created_by
            WHERE pp.product_id = :pid
              AND NOT (pp.price_type = 'purchase_cost'
                       AND (pp.is_scheduled = 0 OR pp.is_scheduled IS NULL))
            ORDER BY pp.created_at DESC
            LIMIT :lim
        """), {"pid": product_id, "lim": limit}).fetchall()

        history = []
        for r in rows:
            price = float(r[2] or 0)
            prev = float(r[3] or 0) if r[3] else None
            cost = float(prod[2] or 0)
            margin = round(((price - cost) / price * 100), 2) if price > 0 and r[1] != "purchase_cost" else None
            history.append({
                "id": r[0],
                "price_type": r[1],
                "price_type_label": PRICE_LABELS.get(r[1], r[1]),
                "price": price,
                "previous_price": prev,
                "change_pct": round(((price - prev) / prev * 100), 2) if prev and prev > 0 else None,
                "effective_from": str(r[4]),
                "effective_to": str(r[5]) if r[5] else None,
                "is_active": bool(r[6]),
                "is_scheduled": bool(r[7]),
                "change_reason": r[8],
                "changed_at": str(r[9]),
                "changed_by": r[10],
                "margin_pct": margin,
            })

        # ── Purchase-cost history: the per-purchase cost ledger
        # (product_cost_history) is the authoritative record of what we actually
        # paid; the product_prices purchase_cost rows are unreliable/sparse, so
        # merge BOTH sources and collapse to actual cost *changes*. Non-scheduled
        # purchase_cost rows were excluded from the query above to avoid double
        # counting; scheduled ones stay in the normal flow (scheduled banner).
        pc_events = []
        for r in db.execute(text("""
            SELECT pch.unit_cost, pch.recorded_at, v.trade_name
            FROM product_cost_history pch
            LEFT JOIN vendors v ON v.id = pch.vendor_id
            WHERE pch.product_id = :pid
        """), {"pid": product_id}).fetchall():
            ts = r[1]
            pc_events.append({
                "cost": float(r[0] or 0), "ts": ts,
                "eff": str(ts)[:10] if ts else None,
                "reason": f"Purchase from {r[2]}" if r[2] else "Purchase",
                "changed_by": None,
            })
        for r in db.execute(text("""
            SELECT pp.price, pp.effective_from, pp.created_at, pp.change_reason, u.full_name
            FROM product_prices pp
            LEFT JOIN users u ON u.id = pp.created_by
            WHERE pp.product_id = :pid AND pp.price_type = 'purchase_cost'
              AND (pp.is_scheduled = 0 OR pp.is_scheduled IS NULL)
        """), {"pid": product_id}).fetchall():
            ts = r[2] or r[1]
            pc_events.append({
                "cost": float(r[0] or 0), "ts": ts,
                "eff": str(r[1])[:10] if r[1] else (str(ts)[:10] if ts else None),
                "reason": r[3] or "Manual cost update",
                "changed_by": r[4],
            })

        def _ts_key(ev):
            t = ev["ts"]
            if isinstance(t, datetime):
                return t
            if isinstance(t, date):
                return datetime(t.year, t.month, t.day)
            return datetime.min
        pc_events.sort(key=_ts_key)

        # Collapse to changes only: emit when the cost differs from the previous.
        pc_changes = []
        prev_cost = None
        for ev in pc_events:
            c = ev["cost"]
            if c <= 0:
                continue
            if prev_cost is not None and c == prev_cost:
                continue
            pc_changes.append({
                "price": c, "previous_price": prev_cost,
                "change_pct": round(((c - prev_cost) / prev_cost * 100), 2) if prev_cost else None,
                "effective_from": ev["eff"],
                "changed_at": str(ev["ts"]) if ev["ts"] else ev["eff"],
                "change_reason": ev["reason"], "changed_by": ev["changed_by"],
            })
            prev_cost = c

        # newest-first to match the rest of `history`; latest change is active.
        n = len(pc_changes)
        for i, ch in enumerate(reversed(pc_changes)):
            history.append({
                "id": f"pc-{product_id}-{n - i}",
                "price_type": "purchase_cost",
                "price_type_label": PRICE_LABELS["purchase_cost"],
                "price": ch["price"], "previous_price": ch["previous_price"],
                "change_pct": ch["change_pct"],
                "effective_from": ch["effective_from"], "effective_to": None,
                "is_active": (i == 0), "is_scheduled": False,
                "change_reason": ch["change_reason"], "changed_at": ch["changed_at"],
                "changed_by": ch["changed_by"], "margin_pct": None,
            })

        # Keep the whole list newest-first so the table and per-type trend logic
        # (which treats index 0 as the latest) stay correct after the merge.
        history.sort(key=lambda h: (h.get("effective_from") or "", str(h.get("changed_at") or "")),
                     reverse=True)

        # Trend per price type
        trends = {}
        for ptype in PRICE_TYPES:
            type_rows = [h for h in history if h["price_type"] == ptype and not h["is_scheduled"]]
            costs = [h["price"] for h in type_rows if h["price"] > 0]
            if len(costs) >= 2:
                trends[ptype] = {
                    "latest": costs[0], "previous": costs[1],
                    "change_pct": round(((costs[0] - costs[1]) / costs[1] * 100), 2) if costs[1] > 0 else 0,
                    "direction": "up" if costs[0] > costs[1] else "down" if costs[0] < costs[1] else "stable",
                    "min": min(costs), "max": max(costs),
                    "avg": round(sum(costs) / len(costs), 2),
                }
            elif len(costs) == 1:
                trends[ptype] = {"latest": costs[0], "previous": None, "change_pct": 0,
                                  "direction": "stable", "min": costs[0], "max": costs[0], "avg": costs[0]}

        # Scheduled prices
        scheduled = db.execute(text("""
            SELECT price_type, price, effective_from, change_reason
            FROM product_prices
            WHERE product_id = :pid AND is_scheduled = TRUE AND is_active = FALSE
            ORDER BY effective_from
        """), {"pid": product_id}).fetchall()

        return {
            "product_id": product_id,
            "part_code": prod[0],
            "part_name": prod[1],
            "current": {
                "purchase_cost": float(prod[2] or 0),
                "b2b_price": float(prod[3] or 0),
                "b2c_price": float(prod[4] or 0),
                "mrp": float(prod[5] or 0),
            },
            "history": history,
            "trends": trends,
            "scheduled": [
                {"price_type": s[0], "price_type_label": PRICE_LABELS.get(s[0], s[0]),
                 "price": float(s[1]), "effective_from": str(s[2]), "reason": s[3]}
                for s in scheduled
            ],
            "total_entries": len(history),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get price history: {e}")


def get_recent_changes(db: Session, from_date: date, to_date: date,
                        page: int = 1, page_size: int = 20) -> dict:
    """All products whose prices changed within [from_date, to_date], grouped.

    One product per row, each carrying every price-type change (cost, floor,
    b2b, b2c, mrp — immediate or scheduled) recorded in the window, with the
    old value, new value and % change. Ordered by most-recently-changed first.
    Filters on created_at (when the change was recorded), inclusive of both
    endpoints. Super-admin facing.
    """
    try:
        params = {"from": from_date.isoformat(), "to": to_date.isoformat()}

        total = db.execute(text("""
            SELECT COUNT(DISTINCT product_id) FROM product_prices
            WHERE DATE(created_at) BETWEEN :from AND :to
        """), params).scalar() or 0

        # Page of distinct products, newest change first.
        page_rows = db.execute(text("""
            SELECT product_id, MAX(created_at) AS last_changed
            FROM product_prices
            WHERE DATE(created_at) BETWEEN :from AND :to
            GROUP BY product_id
            ORDER BY last_changed DESC
            LIMIT :limit OFFSET :offset
        """), {**params, "limit": page_size, "offset": (page - 1) * page_size}).fetchall()

        product_ids = [int(r[0]) for r in page_rows]
        items = []
        if product_ids:
            id_csv = ",".join(str(pid) for pid in product_ids)
            rows = db.execute(text(f"""
                SELECT pp.product_id, p.part_code, p.part_name,
                       pp.price_type, pp.price, pp.previous_price,
                       pp.effective_from, pp.is_scheduled, pp.change_reason,
                       pp.created_at, u.full_name
                FROM product_prices pp
                JOIN products p ON p.id = pp.product_id
                LEFT JOIN users u ON u.id = pp.created_by
                WHERE pp.product_id IN ({id_csv})
                  AND DATE(pp.created_at) BETWEEN :from AND :to
                ORDER BY pp.created_at DESC
            """), params).fetchall()

            grouped = {}
            for r in rows:
                pid = int(r[0])
                if pid not in grouped:
                    grouped[pid] = {
                        "product_id": pid, "part_code": r[1], "part_name": r[2],
                        "last_changed_at": str(r[9]), "changes": [],
                    }
                new_price = float(r[4] or 0)
                old_price = float(r[5]) if r[5] is not None else None
                change_pct = (round(((new_price - old_price) / old_price * 100), 2)
                              if old_price and old_price > 0 else None)
                grouped[pid]["changes"].append({
                    "price_type": r[3],
                    "price_type_label": PRICE_LABELS.get(r[3], r[3]),
                    "old_price": old_price,
                    "new_price": new_price,
                    "change_pct": change_pct,
                    "effective_from": str(r[6]),
                    "is_scheduled": bool(r[7]),
                    "change_reason": r[8],
                    "changed_at": str(r[9]),
                    "changed_by": r[10],
                })
            # Preserve the newest-first product order from page_rows.
            items = [grouped[pid] for pid in product_ids if pid in grouped]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if total else 0,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent changes: {e}")


def get_stock_valuation(db: Session, warehouse_id: Optional[int] = None) -> dict:
    """Stock valuation report — FIFO cost vs latest purchase cost."""
    try:
        where = "AND se.warehouse_id = :wid" if warehouse_id else ""
        params = {}
        if warehouse_id:
            params["wid"] = warehouse_id

        rows = db.execute(text(f"""
            SELECT
                p.id, p.part_code, p.part_name,
                p.purchase_cost as latest_cost,
                p.b2b_price, p.b2c_price, p.mrp,
                SUM(se.remaining_qty) as total_qty,
                SUM(se.remaining_qty * se.unit_cost) as fifo_value
            FROM products p
            LEFT JOIN stock_entries se ON se.product_id = p.id
                AND se.remaining_qty > 0
                AND se.transaction_type IN ('purchase', 'return_in', 'transfer_in', 'adjustment_in')
                {where}
            WHERE p.is_active = TRUE
            GROUP BY p.id, p.part_code, p.part_name, p.purchase_cost,
                     p.b2b_price, p.b2c_price, p.mrp
            HAVING total_qty > 0
            ORDER BY fifo_value DESC
        """), params).fetchall()

        items = []
        total_fifo = 0
        total_latest = 0

        for r in rows:
            qty = float(r[7] or 0)
            fifo_val = float(r[8] or 0)
            latest_cost = float(r[3] or 0)
            latest_val = qty * latest_cost
            b2b = float(r[4] or 0)
            fifo_margin = round(((b2b - (fifo_val / qty if qty > 0 else 0)) / (fifo_val / qty) * 100), 2) if fifo_val > 0 and qty > 0 and b2b > 0 else None
            latest_margin = round(((b2b - latest_cost) / latest_cost * 100), 2) if latest_cost > 0 and b2b > 0 else None

            items.append({
                "product_id": r[0], "part_code": r[1], "part_name": r[2],
                "qty": qty,
                "fifo_unit_cost": round(fifo_val / qty, 2) if qty > 0 else 0,
                "fifo_value": round(fifo_val, 2),
                "latest_cost": latest_cost,
                "latest_value": round(latest_val, 2),
                "b2b_price": b2b,
                "fifo_margin_pct": fifo_margin,
                "latest_margin_pct": latest_margin,
                "value_difference": round(fifo_val - latest_val, 2),
            })
            total_fifo += fifo_val
            total_latest += latest_val

        return {
            "items": items,
            "summary": {
                "total_fifo_value": round(total_fifo, 2),
                "total_latest_value": round(total_latest, 2),
                "difference": round(total_fifo - total_latest, 2),
                "item_count": len(items),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stock valuation failed: {e}")


def get_margin_trend(db: Session, product_id: int) -> dict:
    """Margin trend — how margin has changed across purchase history."""
    try:
        prod = db.execute(text(
            "SELECT part_code, part_name, b2b_price, b2c_price FROM products WHERE id = :id"
        ), {"id": product_id}).fetchone()
        if not prod:
            raise HTTPException(status_code=404, detail="Product not found")

        rows = db.execute(text("""
            SELECT pch.unit_cost, pch.recorded_at, pch.quantity,
                   v.trade_name as vendor_name
            FROM product_cost_history pch
            LEFT JOIN vendors v ON v.id = pch.vendor_id
            WHERE pch.product_id = :pid
            ORDER BY pch.recorded_at DESC
            LIMIT 50
        """), {"pid": product_id}).fetchall()

        b2b = float(prod[2] or 0)
        b2c = float(prod[3] or 0)

        trend = []
        for r in rows:
            cost = float(r[0] or 0)
            b2b_margin = round(((b2b - cost) / b2b * 100), 2) if b2b > 0 else None
            b2c_margin = round(((b2c - cost) / b2c * 100), 2) if b2c > 0 else None
            trend.append({
                "purchase_cost": cost,
                "b2b_price": b2b,
                "b2c_price": b2c,
                "b2b_margin_pct": b2b_margin,
                "b2c_margin_pct": b2c_margin,
                "recorded_at": str(r[1]),
                "quantity": float(r[2] or 0),
                "vendor_name": r[3],
            })

        return {
            "product_id": product_id,
            "part_code": prod[0],
            "part_name": prod[1],
            "current_b2b_price": b2b,
            "current_b2c_price": b2c,
            "trend": trend,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Margin trend failed: {e}")


def record_price_history(db, product_id, purchase_cost=None, b2b_price=None,
                          b2c_price=None, vendor_id=None,
                          vendor_name=None, purchase_invoice_id=None,
                          purchase_invoice_number=None, notes=None, created_by=None):
    """Legacy compatibility wrapper — records all price types passed."""
    today = _today_ist()
    if purchase_cost is not None:
        record_price_change(db, product_id, "purchase_cost",
                            Decimal(str(purchase_cost)), today, created_by or 0)
    if b2b_price is not None:
        record_price_change(db, product_id, "b2b_price",
                            Decimal(str(b2b_price)), today, created_by or 0)
    if b2c_price is not None:
        record_price_change(db, product_id, "b2c_price",
                            Decimal(str(b2c_price)), today, created_by or 0)
