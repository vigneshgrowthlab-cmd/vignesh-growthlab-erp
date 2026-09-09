import json
import csv
import io
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from fastapi import HTTPException
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List

from app.models.models import (
    Warehouse, Product, WarehouseStock, StockEntry, StockTransactionType,
    StockTransfer, StockAdjustment, StockWriteoff, WriteoffStatus,
    Account, JournalEntry, JournalLine, TransactionType, Category
)
from app.schemas.warehouse import (
    WarehouseCreate, WarehouseUpdate,
    StockTransferCreate, StockAdjustmentCreate,
    StockWriteoffCreate, StockWriteoffApprove,
    OpeningBalanceCreate
)
from app.services.product_service import StockService
from app.services.audit import audit, diff
from app.services.workflow_service import WorkflowService
from app.utils.helpers import (
    get_or_create_account, paginate, get_financial_year,
    next_sequence_number, _seed_from_number_fy, _seed_from_suffix,
    resolve_state_code, format_document_number,
)
from app.core.config import settings


class WarehouseService:

    @staticmethod
    def list_warehouses(db: Session, include_inactive: bool = False) -> List[dict]:
        q = db.query(Warehouse)
        if not include_inactive:
            q = q.filter(Warehouse.is_active == True)
        warehouses = q.order_by(Warehouse.is_default.desc(), Warehouse.name).all()
        result = []
        for wh in warehouses:
            stock_value = db.query(func.sum(StockEntry.remaining_qty * StockEntry.unit_cost)).filter(
                StockEntry.warehouse_id == wh.id,
                StockEntry.remaining_qty > 0
            ).scalar() or Decimal("0")
            result.append({
                "id": wh.id, "name": wh.name, "code": wh.code,
                "address": wh.address, "city": wh.city, "state": wh.state,
                "pincode": wh.pincode, "contact_person": wh.contact_person,
                "phone": wh.phone, "is_default": wh.is_default,
                "is_active": wh.is_active, "created_at": wh.created_at,
                "stock_value": stock_value.quantize(Decimal("0.01")),
            })
        return result

    @staticmethod
    def get_by_id(db: Session, warehouse_id: int) -> dict:
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        return {
            "id": wh.id, "name": wh.name, "code": wh.code,
            "address": wh.address, "city": wh.city, "state": wh.state,
            "pincode": wh.pincode, "contact_person": wh.contact_person,
            "phone": wh.phone, "is_default": wh.is_default,
            "is_active": wh.is_active, "created_at": wh.created_at,
        }

    @staticmethod
    def _next_code(db: Session) -> str:
        """Generate the next WH-prefixed code (WH03, WH04, …).

        Seeds from the max numeric suffix of existing WH% codes, then walks
        forward past any collision (legacy codes like WH2/WH02 coexist).
        """
        mx = 0
        for (code,) in db.query(Warehouse.code).filter(Warehouse.code.like("WH%")).all():
            suffix = (code or "")[2:]
            if suffix.isdigit():
                mx = max(mx, int(suffix))
        n = mx + 1
        code = f"WH{n:02d}"
        while db.query(Warehouse).filter(Warehouse.code == code).first():
            n += 1
            code = f"WH{n:02d}"
        return code

    @staticmethod
    def create(db: Session, payload: WarehouseCreate, user_id: int) -> dict:
        if payload.is_default:
            db.query(Warehouse).update({"is_default": False})
        # Code is always server-generated — manual entry is not allowed.
        data = payload.dict()
        data["code"] = WarehouseService._next_code(db)
        wh = Warehouse(**data, created_by=user_id)
        # Keep state_code in sync with the state name for GST determination.
        if wh.state and wh.state_code is None:
            wh.state_code = resolve_state_code(wh.state)
        db.add(wh)
        db.commit()
        db.refresh(wh)
        audit(db, user_id, "create", "warehouse",
              f"Created warehouse {wh.name} ({wh.code})",
              record_type="warehouse", record_id=wh.id)
        return WarehouseService.get_by_id(db, wh.id)

    @staticmethod
    def update(db: Session, warehouse_id: int, payload: WarehouseUpdate, user_id: int) -> dict:
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        _fields = ("name", "address", "city", "state", "pincode",
                   "contact_person", "phone", "is_default", "is_active")
        old = {f: getattr(wh, f, None) for f in _fields}
        if payload.is_default:
            db.query(Warehouse).filter(Warehouse.id != warehouse_id).update({"is_default": False})
        for field, value in payload.dict(exclude_none=True).items():
            setattr(wh, field, value)
        # Re-derive state_code from the (possibly updated) state name.
        if wh.state:
            rc = resolve_state_code(wh.state)
            if rc is not None:
                wh.state_code = rc
        wh.updated_by = user_id
        db.commit()
        new = {f: getattr(wh, f, None) for f in _fields}
        changed, summary = diff(old, new, _fields)
        if changed:
            audit(db, user_id, "update", "warehouse",
                  f"Updated warehouse {wh.name}: {summary}",
                  record_type="warehouse", record_id=wh.id,
                  old={k: v[0] for k, v in changed.items()},
                  new={k: v[1] for k, v in changed.items()})
        return WarehouseService.get_by_id(db, warehouse_id)

    @staticmethod
    def get_stock(db: Session, warehouse_id: Optional[int] = None,
                  product_id: Optional[int] = None,
                  search: Optional[str] = None,
                  low_stock_only: bool = False) -> List[dict]:
        """Get current stock levels across warehouses."""
        q = db.query(WarehouseStock, Warehouse, Product).join(
            Warehouse, WarehouseStock.warehouse_id == Warehouse.id
        ).join(
            Product, WarehouseStock.product_id == Product.id
        ).filter(
            Warehouse.is_active == True,
            Product.is_active == True,
        )
        if warehouse_id:
            q = q.filter(WarehouseStock.warehouse_id == warehouse_id)
        if product_id:
            q = q.filter(WarehouseStock.product_id == product_id)
        if search:
            q = q.filter(
                (Product.part_name.ilike(f"%{search}%")) |
                (Product.part_code.ilike(f"%{search}%"))
            )
        if low_stock_only:
            q = q.filter(WarehouseStock.quantity <= Product.low_stock_threshold)

        rows = q.order_by(Product.part_name, Warehouse.name).all()
        result = []
        seen_products = {}
        for ws, wh, prod in rows:
            fifo_val = db.query(func.sum(StockEntry.remaining_qty * StockEntry.unit_cost)).filter(
                StockEntry.warehouse_id == wh.id,
                StockEntry.product_id == prod.id,
                StockEntry.remaining_qty > 0
            ).scalar() or Decimal("0")

            if prod.id not in seen_products:
                seen_products[prod.id] = {
                    "product_id": prod.id,
                    "part_code": prod.part_code,
                    "part_name": prod.part_name,
                    "category_name": None,
                    "unit_of_measure": prod.unit_of_measure,
                    "total_quantity": Decimal("0"),
                    "fifo_value": Decimal("0"),
                    "low_stock_threshold": prod.low_stock_threshold,
                    "is_low_stock": False,
                    "warehouses": [],
                }
                result.append(seen_products[prod.id])
            item = seen_products[prod.id]
            item["total_quantity"] += ws.quantity
            item["fifo_value"] += fifo_val
            item["warehouses"].append({
                "warehouse_id": wh.id,
                "warehouse_name": wh.name,
                "quantity": ws.quantity,
                "fifo_value": fifo_val.quantize(Decimal("0.01")),
            })
        for item in result:
            item["is_low_stock"] = item["total_quantity"] <= item["low_stock_threshold"]
            item["fifo_value"] = item["fifo_value"].quantize(Decimal("0.01"))
        return result

    @staticmethod
    def get_consolidated_stock(db: Session, product_id: int,
                               selected_warehouse_id: int) -> dict:
        """Get stock for billing screen — selected WH + total + breakup."""
        all_stock = db.query(WarehouseStock, Warehouse).join(
            Warehouse, WarehouseStock.warehouse_id == Warehouse.id
        ).filter(
            WarehouseStock.product_id == product_id,
            Warehouse.is_active == True,
        ).all()

        selected_qty = Decimal("0")
        total_qty = Decimal("0")
        breakup = []
        for ws, wh in all_stock:
            total_qty += ws.quantity
            if wh.id == selected_warehouse_id:
                selected_qty = ws.quantity
            breakup.append({
                "warehouse_id": wh.id,
                "warehouse_name": wh.name,
                "quantity": ws.quantity,
                "is_selected": wh.id == selected_warehouse_id,
            })

        return {
            "product_id": product_id,
            "selected_warehouse_quantity": selected_qty,
            "total_all_warehouses": total_qty,
            "warehouse_breakup": sorted(breakup, key=lambda x: -x["quantity"]),
        }



    @staticmethod
    def validate_obsolete(db: Session, warehouse_id: int) -> dict:
        """Check all conditions before marking warehouse as obsolete."""
        from sqlalchemy import text as _sql
        blocks = []

        # 1. Pending stock
        stock_rows = db.execute(_sql("""
            SELECT p.part_name, p.part_code, ws.quantity
            FROM warehouse_stock ws
            JOIN products p ON p.id = ws.product_id
            WHERE ws.warehouse_id = :wid AND ws.quantity > 0
        """), {"wid": warehouse_id}).fetchall()
        if stock_rows:
            blocks.append({
                "type": "stock",
                "message": f"{len(stock_rows)} product(s) still have stock in this warehouse",
                "items": [{"name": r[0], "code": r[1], "qty": float(r[2])} for r in stock_rows]
            })

        # 2. Pending / Linked DCs (source or destination)
        dc_rows = db.execute(_sql("""
            SELECT invoice_number, dc_status
            FROM invoices
            WHERE is_cancelled = 0
            AND LOWER(document_type) IN ('delivery_challan', 'documenttype.delivery_challan')
            AND (warehouse_id = :wid OR dc_destination_warehouse_id = :wid)
            AND dc_status IN ('pending', 'linked')
        """), {"wid": warehouse_id}).fetchall()
        if dc_rows:
            blocks.append({
                "type": "pending_dcs",
                "message": f"{len(dc_rows)} pending/linked DC(s) reference this warehouse",
                "items": [{"invoice_number": r[0], "status": r[1]} for r in dc_rows]
            })

        # 3. Pending transfers
        tr_rows = db.execute(_sql("""
            SELECT transfer_number
            FROM stock_transfers
            WHERE (source_warehouse_id = :wid OR destination_warehouse_id = :wid)
            AND (transfer_status IS NULL OR transfer_status != 'completed')
        """), {"wid": warehouse_id}).fetchall()
        if tr_rows:
            blocks.append({
                "type": "pending_transfers",
                "message": f"{len(tr_rows)} pending transfer(s) reference this warehouse",
                "items": [{"transfer_number": r[0]} for r in tr_rows]
            })

        # 4. Active users assigned to this warehouse
        user_rows = db.execute(_sql("""
            SELECT username, full_name FROM users
            WHERE warehouse_id = :wid AND is_active = 1
        """), {"wid": warehouse_id}).fetchall()
        if user_rows:
            blocks.append({
                "type": "assigned_users",
                "message": f"{len(user_rows)} active user(s) are assigned to this warehouse",
                "items": [{"username": r[0], "full_name": r[1]} for r in user_rows]
            })

        # 5. Open invoices (outstanding > 0)
        inv_rows = db.execute(_sql("""
            SELECT invoice_number, outstanding_amount
            FROM invoices
            WHERE warehouse_id = :wid
            AND is_cancelled = 0
            AND outstanding_amount > 0.01
            AND LOWER(document_type) IN ('b2b_invoice', 'b2c_invoice')
        """), {"wid": warehouse_id}).fetchall()
        if inv_rows:
            blocks.append({
                "type": "open_invoices",
                "message": f"{len(inv_rows)} invoice(s) have outstanding amounts",
                "items": [{"invoice_number": r[0], "outstanding": float(r[1])} for r in inv_rows]
            })

        return {
            "can_obsolete": len(blocks) == 0,
            "blocks": blocks
        }

    @staticmethod
    def rename_warehouse(db: Session, warehouse_id: int, updates: dict, user_id: int) -> dict:
        """Rename/edit warehouse — all fields except code."""
        from sqlalchemy import text as _sql
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        # Allow editing name, address, city, state, pincode, contact_person, phone — not code
        allowed = ['name', 'address', 'city', 'state', 'pincode', 'contact_person', 'phone', 'is_default', 'use_company_bank', 'bank_name', 'bank_account_number', 'bank_ifsc', 'bank_branch', 'bank_account_name', 'upi_id']
        for k, v in updates.items():
            if k in allowed and hasattr(wh, k):
                setattr(wh, k, v)
        db.commit()
        db.refresh(wh)
        return {"id": wh.id, "name": wh.name, "code": wh.code, "is_active": wh.is_active}

    @staticmethod
    def obsolete_warehouse(db: Session, warehouse_id: int, user_id: int) -> dict:
        """Mark warehouse as inactive (obsolete) after validation."""
        validation = WarehouseService.validate_obsolete(db, warehouse_id)
        if not validation["can_obsolete"]:
            raise HTTPException(
                status_code=422,
                detail={"message": "Cannot obsolete warehouse", "blocks": validation["blocks"]}
            )
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        wh.is_active = False
        db.commit()
        audit(db, user_id, "update", "warehouse",
              f"Marked warehouse {wh.name} ({wh.code}) as obsolete",
              record_type="warehouse", record_id=warehouse_id,
              old={"is_active": True}, new={"is_active": False})
        return {"status": "obsoleted", "warehouse_id": warehouse_id, "name": wh.name}

    @staticmethod
    def validate_delete(db: Session, warehouse_id: int) -> dict:
        """Hard-delete validation: warehouse must have NO references whatsoever.
        Stricter than validate_obsolete — blocks on ANY historical row, not just
        pending/active ones. Use 'obsolete' instead for warehouses with history."""
        from sqlalchemy import text as _sql
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        blocks = []
        checks = [
            ("warehouse_stocks",
             "SELECT COUNT(*) FROM warehouse_stocks WHERE warehouse_id = :wid",
             "stock record(s) exist for this warehouse"),
            ("stock_entries",
             "SELECT COUNT(*) FROM stock_entries WHERE warehouse_id = :wid",
             "FIFO entry/entries exist (historical stock movements)"),
            ("invoices",
             "SELECT COUNT(*) FROM invoices "
             "WHERE warehouse_id = :wid OR dc_destination_warehouse_id = :wid",
             "invoice(s)/DC(s) reference this warehouse"),
            ("stock_transfers",
             "SELECT COUNT(*) FROM stock_transfers "
             "WHERE source_warehouse_id = :wid OR destination_warehouse_id = :wid",
             "transfer(s) reference this warehouse"),
            ("stock_adjustments",
             "SELECT COUNT(*) FROM stock_adjustments WHERE warehouse_id = :wid",
             "adjustment(s) reference this warehouse"),
            ("stock_writeoffs",
             "SELECT COUNT(*) FROM stock_writeoffs WHERE warehouse_id = :wid",
             "write-off(s) reference this warehouse"),
            ("users",
             "SELECT COUNT(*) FROM users WHERE warehouse_id = :wid",
             "user(s) are assigned to this warehouse"),
        ]
        for kind, sql, suffix in checks:
            try:
                cnt = db.execute(_sql(sql), {"wid": warehouse_id}).scalar() or 0
            except Exception:
                cnt = 0
            if cnt:
                blocks.append({
                    "type": kind,
                    "message": f"{cnt} {suffix}",
                    "count": int(cnt),
                })

        return {
            "can_delete": len(blocks) == 0,
            "blocks": blocks,
            "warehouse_name": wh.name,
        }

    @staticmethod
    def delete_warehouse(db: Session, warehouse_id: int, user_id: int) -> dict:
        """Hard delete a warehouse — only if no references exist anywhere.
        For warehouses with any history, use 'obsolete' instead."""
        validation = WarehouseService.validate_delete(db, warehouse_id)
        if not validation["can_delete"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Cannot delete warehouse — references exist. "
                               "Use 'Obsolete' to soft-delete instead.",
                    "blocks": validation["blocks"],
                },
            )
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        name = wh.name
        code = wh.code
        db.delete(wh)
        db.commit()
        audit(db, user_id, "delete", "warehouse",
              f"Deleted warehouse {name} ({code})",
              record_type="warehouse", record_id=warehouse_id)
        return {"status": "deleted", "warehouse_id": warehouse_id, "name": name}



class StockTransferService:

    @staticmethod
    def create(db: Session, payload: StockTransferCreate, user_id: int) -> dict:
        src = db.query(Warehouse).filter(Warehouse.id == payload.source_warehouse_id, Warehouse.is_active == True).first()
        dst = db.query(Warehouse).filter(Warehouse.id == payload.destination_warehouse_id, Warehouse.is_active == True).first()

        if not src: raise HTTPException(status_code=404, detail="Source warehouse not found")
        if not dst: raise HTTPException(status_code=404, detail="Destination warehouse not found")
        if payload.source_warehouse_id == payload.destination_warehouse_id:
            raise HTTPException(status_code=400, detail="Source and destination cannot be the same warehouse")

        # Validate DC links
        dc_ids = getattr(payload, 'dc_ids', None) or []
        if not dc_ids:
            raise HTTPException(status_code=400, detail="At least one Delivery Challan must be linked to this transfer")

        # Check stock availability in source warehouse for each DC line item
        from app.models.models import Invoice as InvoiceModel, InvoiceItem, WarehouseStock
        for dc_id in dc_ids:
            dc_items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == dc_id).all()
            for item in dc_items:
                ws = db.query(WarehouseStock).filter_by(
                    warehouse_id=payload.source_warehouse_id,
                    product_id=item.product_id
                ).first()
                available = ws.quantity if ws else Decimal("0")
                if available < item.quantity:
                    prod = db.query(Product).filter(Product.id == item.product_id).first()
                    pname = prod.part_name if prod else str(item.product_id)
                    raise HTTPException(status_code=400,
                        detail=f"Insufficient stock for {pname} in source warehouse. Available: {available}, Required: {item.quantity}")

        # Verify DCs are not already linked to another transfer
        existing_transfers = db.query(StockTransfer).filter(StockTransfer.dc_ids.isnot(None)).all()
        linked_dcs = set()
        for t in existing_transfers:
            try:
                linked_dcs.update(json.loads(t.dc_ids or "[]"))
            except Exception:
                pass
        for dc_id in dc_ids:
            if dc_id in linked_dcs:
                dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
                dc_num = dc.invoice_number if dc else dc_id
                raise HTTPException(status_code=400, detail=f"DC {dc_num} is already linked to another transfer")

        fy = get_financial_year(payload.transfer_date)
        count = db.query(StockTransfer).count()
        transfer_number = f"TRF-{fy.replace('-','')}-{count+1:04d}"

        # Use first DC's first item as representative product/qty for StockTransfer record
        first_dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_ids[0]).first()
        first_item = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == dc_ids[0]).first() if first_dc else None
        rep_product_id = first_item.product_id if first_item else None
        rep_quantity = first_item.quantity if first_item else Decimal("0")

        transfer = StockTransfer(
            transfer_number=transfer_number,
            source_warehouse_id=payload.source_warehouse_id,
            destination_warehouse_id=payload.destination_warehouse_id,
            product_id=rep_product_id,
            quantity=rep_quantity,
            transfer_date=payload.transfer_date,
            notes=payload.notes,
            dc_ids=json.dumps(dc_ids),
            created_by=user_id,
        )
        db.add(transfer)
        db.flush()

        # Mark linked DCs as 'linked' via raw SQL
        from sqlalchemy import text as _sql
        for dc_id in dc_ids:
            try:
                db.execute(_sql("UPDATE invoices SET dc_status='linked' WHERE id=:id"), {"id": dc_id})
            except Exception:
                pass

        # Reduce stock from source warehouse for each DC line item
        from app.models.models import WarehouseStock, InvoiceItem
        for dc_id in dc_ids:
            dc_items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == dc_id).all()
            for item in dc_items:
                ws = db.query(WarehouseStock).filter_by(
                    warehouse_id=payload.source_warehouse_id,
                    product_id=item.product_id
                ).first()
                if ws:
                    ws.quantity = max(Decimal("0"), ws.quantity - item.quantity)
                    print(f"[TRANSFER] Reduced {item.quantity} of product {item.product_id} from warehouse {payload.source_warehouse_id}. Remaining: {ws.quantity}")
                else:
                    print(f"[TRANSFER] WARNING: No stock record for product {item.product_id} in warehouse {payload.source_warehouse_id}")
        # Stock-in to destination happens when DC is confirmed (marked Delivered)

        db.commit()
        audit(db, user_id, "transfer", "warehouse",
              f"Created stock transfer {transfer.transfer_number} from {src.name} "
              f"to {dst.name} ({len(dc_ids)} DC(s) linked)",
              record_type="stock_transfer", record_id=transfer.id)
        rep_prod = db.query(Product).filter(Product.id == rep_product_id).first() if rep_product_id else None
        return {
            "id": transfer.id, "transfer_number": transfer.transfer_number,
            "source_warehouse_id": transfer.source_warehouse_id,
            "source_warehouse_name": src.name,
            "destination_warehouse_id": transfer.destination_warehouse_id,
            "destination_warehouse_name": dst.name,
            "product_id": transfer.product_id,
            "part_code": rep_prod.part_code if rep_prod else None,
            "part_name": rep_prod.part_name if rep_prod else None,
            "quantity": transfer.quantity,
            "transfer_date": transfer.transfer_date,
            "notes": transfer.notes,
            "created_at": transfer.created_at,
        }


    @staticmethod
    def confirm_dc(db: Session, transfer_id: int, dc_id: int, user_id: int) -> dict:
        """Confirm a DC delivery — adds stock to destination warehouse."""
        import json
        from app.models.models import Invoice as InvoiceModel, InvoiceItem, WarehouseStock
        from sqlalchemy import text as _sql

        t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Transfer not found")

        dc_ids = json.loads(t.dc_ids or "[]")
        if dc_id not in dc_ids:
            raise HTTPException(status_code=400, detail="DC not linked to this transfer")

        dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
        if not dc:
            raise HTTPException(status_code=404, detail="DC not found")

        dc_status = None
        try:
            row = db.execute(_sql("SELECT dc_status FROM invoices WHERE id=:id"), {"id": dc_id}).fetchone()
            dc_status = row[0] if row else None
        except Exception:
            dc_status = getattr(dc, 'dc_status', None)

        if dc_status == 'delivered':
            raise HTTPException(status_code=400, detail="DC already confirmed/delivered")
        if dc_status == 'cancelled':
            raise HTTPException(status_code=400, detail="Cannot confirm a cancelled DC")

        # Add stock to destination warehouse for each line item
        items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == dc_id).all()
        for item in items:
            ws = db.query(WarehouseStock).filter_by(
                warehouse_id=t.destination_warehouse_id,
                product_id=item.product_id
            ).first()
            if ws:
                ws.quantity += item.quantity
            else:
                ws = WarehouseStock(
                    warehouse_id=t.destination_warehouse_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
                db.add(ws)

        # Mark DC as delivered + record approval audit
        try:
            db.execute(
                _sql("UPDATE invoices SET dc_status='delivered', "
                     "dc_approved_by=:uid, dc_approved_at=:ts WHERE id=:id"),
                {"id": dc_id, "uid": user_id, "ts": datetime.utcnow()},
            )
        except Exception:
            pass

        # Check if all DCs in this transfer are delivered -> mark transfer completed
        all_delivered = True
        for did in dc_ids:
            try:
                row = db.execute(_sql("SELECT dc_status FROM invoices WHERE id=:id"), {"id": did}).fetchone()
                if not row or row[0] != 'delivered':
                    all_delivered = False
                    break
            except Exception:
                all_delivered = False
                break

        if all_delivered:
            try:
                db.execute(_sql("UPDATE stock_transfers SET transfer_status='completed' WHERE id=:id"), {"id": transfer_id})
            except Exception as _tse:
                print(f"[TRANSFER] status update failed: {_tse}")

        db.commit()
        audit(db, user_id, "transfer", "warehouse",
              f"Confirmed DC {dc.invoice_number} for transfer {t.transfer_number} "
              f"(stock received at destination)"
              + ("; transfer completed" if all_delivered else ""),
              record_type="stock_transfer", record_id=transfer_id)
        return {"status": "confirmed", "dc_id": dc_id, "transfer_completed": all_delivered}

    @staticmethod
    def reject_dc(db: Session, transfer_id: int, dc_id: int,
                  reason: str, user_id: int) -> dict:
        """Reject a DC at the destination — restores source stock to source
        warehouse (it was deducted at transfer create), marks DC 'rejected',
        records rejected_by + rejected_at + reason. The transfer remains so
        the audit trail is preserved; only this DC moves to rejected status."""
        import json
        from app.models.models import Invoice as InvoiceModel, InvoiceItem, WarehouseStock
        from sqlalchemy import text as _sql

        t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Transfer not found")

        dc_ids = json.loads(t.dc_ids or "[]")
        if dc_id not in dc_ids:
            raise HTTPException(status_code=400, detail="DC not linked to this transfer")

        dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
        if not dc:
            raise HTTPException(status_code=404, detail="DC not found")

        dc_status = None
        try:
            row = db.execute(_sql("SELECT dc_status FROM invoices WHERE id=:id"),
                             {"id": dc_id}).fetchone()
            dc_status = row[0] if row else None
        except Exception:
            dc_status = getattr(dc, "dc_status", None)

        if dc_status == "delivered":
            raise HTTPException(status_code=400,
                                detail="Cannot reject an already-delivered DC")
        if dc_status == "rejected":
            raise HTTPException(status_code=400, detail="DC already rejected")
        if dc_status == "cancelled":
            raise HTTPException(status_code=400,
                                detail="Cannot reject a cancelled DC")

        # Restore source stock for each line item (source was deducted at create)
        items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == dc_id).all()
        for item in items:
            ws = db.query(WarehouseStock).filter_by(
                warehouse_id=t.source_warehouse_id,
                product_id=item.product_id,
            ).first()
            if ws:
                ws.quantity = (ws.quantity or Decimal("0")) + item.quantity
            else:
                ws = WarehouseStock(
                    warehouse_id=t.source_warehouse_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
                db.add(ws)

        # Mark DC rejected + audit
        try:
            db.execute(
                _sql("UPDATE invoices SET dc_status='rejected', "
                     "dc_rejected_by=:uid, dc_rejected_at=:ts, "
                     "dc_rejection_reason=:reason WHERE id=:id"),
                {"id": dc_id, "uid": user_id, "ts": datetime.utcnow(),
                 "reason": reason},
            )
        except Exception as e:
            print(f"[REJECT] failed to mark DC rejected: {e}")

        db.commit()
        audit(db, user_id, "transfer", "warehouse",
              f"Rejected DC {dc.invoice_number} for transfer {t.transfer_number} "
              f"(source stock restored). Reason: {reason}",
              record_type="stock_transfer", record_id=transfer_id)
        return {
            "status": "rejected",
            "dc_id": dc_id,
            "reason": reason,
            "source_stock_restored": True,
        }

    @staticmethod
    def list_transfers(db: Session, warehouse_id: Optional[int] = None,
                       product_id: Optional[int] = None,
                       page: int = 1, page_size: int = 20,
                       user_warehouse_id: Optional[int] = None,
                       pending_dest_whs: Optional[list] = None) -> dict:
        q = db.query(StockTransfer)
        if warehouse_id:
            q = q.filter(
                (StockTransfer.source_warehouse_id == warehouse_id) |
                (StockTransfer.destination_warehouse_id == warehouse_id)
            )
        # Warehouse role: only show transfers where source or destination = their warehouse
        if user_warehouse_id:
            q = q.filter(
                (StockTransfer.source_warehouse_id == user_warehouse_id) |
                (StockTransfer.destination_warehouse_id == user_warehouse_id)
            )
        # pending_for_me: destination in caller's assigned warehouses AND not completed
        if pending_dest_whs:
            q = q.filter(
                StockTransfer.destination_warehouse_id.in_(pending_dest_whs),
                (StockTransfer.transfer_status.is_(None)) |
                (StockTransfer.transfer_status != "completed"),
            )
        if product_id:
            q = q.filter(StockTransfer.product_id == product_id)
        result = paginate(q.order_by(desc(StockTransfer.transfer_date), desc(StockTransfer.id)), page, page_size)
        items = []
        for t in result["items"]:
            src = db.query(Warehouse).filter(Warehouse.id == t.source_warehouse_id).first()
            dst = db.query(Warehouse).filter(Warehouse.id == t.destination_warehouse_id).first()
            prod = db.query(Product).filter(Product.id == t.product_id).first()
            # Build linked DCs summary
            linked_dcs = []
            try:
                dc_id_list = json.loads(t.dc_ids or "[]")
                from app.models.models import Invoice as InvoiceModel
                for dc_id in dc_id_list:
                    dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
                    if dc:
                        try:
                            from sqlalchemy import text as _sqlt
                            _row = db.execute(_sqlt(
                                "SELECT dc_status, vehicle_number, dc_approved_by, "
                                "dc_approved_at, dc_rejected_by, dc_rejected_at, "
                                "dc_rejection_reason FROM invoices WHERE id=:id"
                            ), {"id": dc_id}).fetchone()
                            _dc_status = _row[0] if _row else 'pending'
                            _vehicle = _row[1] if _row else None
                            _appr_by = _row[2] if _row else None
                            _appr_at = _row[3] if _row else None
                            _rej_by = _row[4] if _row else None
                            _rej_at = _row[5] if _row else None
                            _rej_reason = _row[6] if _row else None
                        except Exception:
                            _dc_status = getattr(dc, 'dc_status', 'pending')
                            _vehicle = getattr(dc, 'vehicle_number', None)
                            _appr_by = _appr_at = _rej_by = _rej_at = _rej_reason = None
                        linked_dcs.append({
                            "id": dc.id,
                            "invoice_number": dc.invoice_number,
                            "dc_status": _dc_status or 'pending',
                            "vehicle_number": _vehicle,
                            "invoice_date": str(dc.invoice_date) if dc.invoice_date else None,
                            "approved_by": _appr_by,
                            "approved_at": str(_appr_at) if _appr_at else None,
                            "rejected_by": _rej_by,
                            "rejected_at": str(_rej_at) if _rej_at else None,
                            "rejection_reason": _rej_reason,
                        })
            except Exception:
                dc_id_list = []
            try:
                from sqlalchemy import text as _sqt
                _trow = db.execute(_sqt(
                    "SELECT transfer_status FROM stock_transfers WHERE id=:id"
                ), {"id": t.id}).fetchone()
                _tstatus = _trow[0] if _trow and _trow[0] else "pending"
            except Exception:
                _tstatus = "pending"
            items.append({
                "id": t.id, "transfer_number": t.transfer_number,
                "source_warehouse_id": t.source_warehouse_id,
                "destination_warehouse_id": t.destination_warehouse_id,
                "source_warehouse_name": src.name if src else None,
                "destination_warehouse_name": dst.name if dst else None,
                "part_code": prod.part_code if prod else None,
                "part_name": prod.part_name if prod else None,
                "quantity": t.quantity,
                "transfer_date": t.transfer_date,
                "created_at": t.created_at,
                "dc_ids": dc_id_list,
                "linked_dcs": linked_dcs,
                "notes": t.notes,
                "transfer_status": _tstatus,
            })
        result["items"] = items
        return result


class StockAdjustmentService:

    @staticmethod
    def create(db: Session, payload: StockAdjustmentCreate, user_id: int) -> dict:
        wh = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id, Warehouse.is_active == True).first()
        product = db.query(Product).filter(Product.id == payload.product_id, Product.is_active == True).first()
        if not wh: raise HTTPException(status_code=404, detail="Warehouse not found")
        if not product: raise HTTPException(status_code=404, detail="Product not found")

        if payload.adjustment_type == "out":
            ws = db.query(WarehouseStock).filter(
                WarehouseStock.warehouse_id == payload.warehouse_id,
                WarehouseStock.product_id == payload.product_id
            ).first()
            available = ws.quantity if ws else Decimal("0")
            if available < payload.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock. Available: {available}, Requested: {payload.quantity}"
                )

        fy = get_financial_year(payload.adjustment_date)
        seq = next_sequence_number(
            db, "stock_adjustment", "ADJ", fy,
            seed_from=lambda d, f: _seed_from_number_fy(
                d, f, "stock_adjustments", "adjustment_number", "ADJ"
            ),
        )
        adj_number = format_document_number(db, "ADJ", fy, seq, "ADJ", 4)

        adj = StockAdjustment(
            adjustment_number=adj_number,
            warehouse_id=payload.warehouse_id,
            product_id=payload.product_id,
            adjustment_type=payload.adjustment_type,
            quantity=payload.quantity,
            reason=payload.reason,
            adjustment_date=payload.adjustment_date,
            unit_cost=payload.unit_cost,
            notes=payload.notes,
            created_by=user_id,
        )
        db.add(adj)
        db.flush()

        txn_type = StockTransactionType.adjustment_in if payload.adjustment_type == "in" else StockTransactionType.adjustment_out
        if payload.adjustment_type == "in":
            StockService.add_stock(
                db, payload.product_id, payload.warehouse_id,
                payload.quantity, payload.unit_cost or product.purchase_cost,
                txn_type, "adjustment", adj.id,
                payload.adjustment_date, user_id
            )
            unit_cost_for_je = Decimal(str(payload.unit_cost or product.purchase_cost or 0))
        else:
            avg_cost = StockService.consume_fifo(db, payload.product_id, payload.warehouse_id, payload.quantity)
            unit_cost_for_je = Decimal(str(avg_cost or payload.unit_cost or product.purchase_cost or 0))

        adj_value = (unit_cost_for_je * payload.quantity).quantize(Decimal("0.01"))
        if adj_value > 0:
            je_seq = next_sequence_number(
                db, "journal_entry", "JE", fy,
                seed_from=lambda d, f: _seed_from_suffix(d, f, "journal_entries", "entry_number"),
            )
            je = JournalEntry(
                entry_number=format_document_number(db, "JE", fy, je_seq, "JE", 5),
                entry_date=payload.adjustment_date,
                reference_type="stock_adjustment", reference_id=adj.id,
                narration=f"Stock adjustment {adj_number} — {product.part_name} ({payload.adjustment_type})",
                financial_year=fy, created_by=user_id,
            )
            db.add(je)
            db.flush()
            stock_acc = get_or_create_account(db, "STOCK")
            adj_acc = get_or_create_account(db, "STOCK_ADJ")
            if stock_acc and adj_acc:
                if payload.adjustment_type == "in":
                    db.add(JournalLine(journal_entry_id=je.id, account_id=stock_acc.id,
                                       transaction_type=TransactionType.debit, amount=adj_value))
                    db.add(JournalLine(journal_entry_id=je.id, account_id=adj_acc.id,
                                       transaction_type=TransactionType.credit, amount=adj_value))
                else:
                    db.add(JournalLine(journal_entry_id=je.id, account_id=adj_acc.id,
                                       transaction_type=TransactionType.debit, amount=adj_value))
                    db.add(JournalLine(journal_entry_id=je.id, account_id=stock_acc.id,
                                       transaction_type=TransactionType.credit, amount=adj_value))

        db.commit()
        audit(db, user_id, "adjustment", "warehouse",
              f"Stock adjustment {adj.adjustment_number}: {adj.adjustment_type} "
              f"{adj.quantity} of {product.part_code} at {wh.name}"
              + (f" — {adj.reason}" if adj.reason else ""),
              record_type="stock_adjustment", record_id=adj.id)
        return {
            "id": adj.id, "adjustment_number": adj.adjustment_number,
            "warehouse_name": wh.name, "part_code": product.part_code,
            "part_name": product.part_name,
            "adjustment_type": adj.adjustment_type,
            "quantity": adj.quantity, "reason": adj.reason,
            "adjustment_date": adj.adjustment_date,
            "created_at": adj.created_at,
        }

    @staticmethod
    def list_adjustments(db: Session, warehouse_id: Optional[int] = None,
                         page: int = 1, page_size: int = 20) -> dict:
        q = db.query(StockAdjustment)
        if warehouse_id:
            q = q.filter(StockAdjustment.warehouse_id == warehouse_id)
        result = paginate(q.order_by(desc(StockAdjustment.adjustment_date), desc(StockAdjustment.id)), page, page_size)
        items = []
        for a in result["items"]:
            wh = db.query(Warehouse).filter(Warehouse.id == a.warehouse_id).first()
            prod = db.query(Product).filter(Product.id == a.product_id).first()
            items.append({
                "id": a.id, "adjustment_number": a.adjustment_number,
                "warehouse_name": wh.name if wh else None,
                "part_code": prod.part_code if prod else None,
                "part_name": prod.part_name if prod else None,
                "adjustment_type": a.adjustment_type,
                "quantity": a.quantity, "reason": a.reason,
                "adjustment_date": a.adjustment_date, "created_at": a.created_at,
            })
        result["items"] = items
        return result


class StockWriteoffService:

    @staticmethod
    def create(db: Session, payload: StockWriteoffCreate, user_id: int) -> dict:
        wh = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id, Warehouse.is_active == True).first()
        product = db.query(Product).filter(Product.id == payload.product_id, Product.is_active == True).first()
        if not wh: raise HTTPException(status_code=404, detail="Warehouse not found")
        if not product: raise HTTPException(status_code=404, detail="Product not found")

        ws = db.query(WarehouseStock).filter(
            WarehouseStock.warehouse_id == payload.warehouse_id,
            WarehouseStock.product_id == payload.product_id
        ).first()
        available = ws.quantity if ws else Decimal("0")
        if available < payload.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {available}, Requested: {payload.quantity}"
            )

        fy = get_financial_year(payload.writeoff_date)
        count = db.query(StockWriteoff).count()
        wo_number = format_document_number(db, "WO", fy, count + 1, "WO", 4)

        wo = StockWriteoff(
            writeoff_number=wo_number,
            warehouse_id=payload.warehouse_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            reason_type=payload.reason_type,
            reason_detail=payload.reason_detail,
            writeoff_date=payload.writeoff_date,
            status="pending",
            notes=payload.notes,
            created_by=user_id,
        )
        db.add(wo)
        db.commit()
        db.refresh(wo)
        audit(db, user_id, "writeoff", "warehouse",
              f"Created stock write-off {wo.writeoff_number}: {wo.quantity} of "
              f"{product.part_code} at {wh.name} ({wo.reason_type})",
              record_type="stock_writeoff", record_id=wo.id)
        return StockWriteoffService._format(db, wo, wh, product)

    @staticmethod
    def approve(db: Session, writeoff_id: int, payload: StockWriteoffApprove,
                user_id: int) -> dict:
        wo = db.query(StockWriteoff).filter(StockWriteoff.id == writeoff_id).first()
        if not wo: raise HTTPException(status_code=404, detail="Write-off not found")
        if wo.status != "pending":
            raise HTTPException(status_code=400, detail=f"Write-off is already {wo.status}")

        # Advisory transition policy (Phase 5c): logs a warning if disallowed,
        # never blocks. Enforcement is a deliberate later opt-in.
        WorkflowService.check_transition(
            db, "stock_writeoff", wo.status,
            "approved" if payload.approved else "rejected", user_id=user_id)

        wh = db.query(Warehouse).filter(Warehouse.id == wo.warehouse_id).first()
        product = db.query(Product).filter(Product.id == wo.product_id).first()

        if payload.approved:
            wo.status = "approved"
            wo.approved_by = user_id
            wo.approved_at = datetime.utcnow()
            wo.admin_notes = payload.admin_notes

            # Consume FIFO stock
            avg_cost = StockService.consume_fifo(
                db, wo.product_id, wo.warehouse_id, wo.quantity
            )
            writeoff_value = (avg_cost or product.purchase_cost) * wo.quantity

            # Journal: Debit Loss account, Credit Stock account
            fy = get_financial_year(wo.writeoff_date)
            seq = next_sequence_number(
                db, "journal_entry", "JE", fy,
                seed_from=lambda d, f: _seed_from_suffix(d, f, "journal_entries", "entry_number"),
            )
            je = JournalEntry(
                entry_number=format_document_number(db, "JE", fy, seq, "JE", 5),
                entry_date=wo.writeoff_date,
                reference_type="stock_writeoff", reference_id=wo.id,
                narration=f"Stock write-off {wo.writeoff_number} — {product.part_name}",
                financial_year=fy, created_by=user_id,
            )
            db.add(je)
            db.flush()

            loss_acc = get_or_create_account(db, "LOSS_WRITEOFF")
            stock_acc = get_or_create_account(db, "STOCK")

            if loss_acc and stock_acc:
                db.add(JournalLine(journal_entry_id=je.id, account_id=loss_acc.id,
                                    transaction_type=TransactionType.debit,
                                    amount=writeoff_value.quantize(Decimal("0.01"))))
                db.add(JournalLine(journal_entry_id=je.id, account_id=stock_acc.id,
                                    transaction_type=TransactionType.credit,
                                    amount=writeoff_value.quantize(Decimal("0.01"))))
        else:
            wo.status = "rejected"
            wo.admin_notes = payload.admin_notes

        db.commit()
        audit(db, user_id, "approve", "warehouse",
              f"Write-off {wo.writeoff_number} {wo.status} "
              f"({wo.quantity} of {product.part_code if product else '?'})",
              record_type="stock_writeoff", record_id=wo.id,
              old={"status": "pending"}, new={"status": wo.status})
        return StockWriteoffService._format(db, wo, wh, product)

    @staticmethod
    def list_writeoffs(db: Session, status: Optional[str] = None,
                       page: int = 1, page_size: int = 20) -> dict:
        q = db.query(StockWriteoff)
        if status:
            q = q.filter(StockWriteoff.status == status)
        result = paginate(q.order_by(desc(StockWriteoff.created_at), desc(StockWriteoff.id)), page, page_size)
        items = []
        for wo in result["items"]:
            wh = db.query(Warehouse).filter(Warehouse.id == wo.warehouse_id).first()
            prod = db.query(Product).filter(Product.id == wo.product_id).first()
            items.append(StockWriteoffService._format(db, wo, wh, prod))
        result["items"] = items
        return result

    @staticmethod
    def _format(db, wo, wh, prod) -> dict:
        return {
            "id": wo.id, "writeoff_number": wo.writeoff_number,
            "warehouse_id": wo.warehouse_id,
            "warehouse_name": wh.name if wh else None,
            "product_id": wo.product_id,
            "part_code": prod.part_code if prod else None,
            "part_name": prod.part_name if prod else None,
            "quantity": wo.quantity,
            "reason_type": wo.reason_type,
            "reason_detail": wo.reason_detail,
            "writeoff_date": wo.writeoff_date,
            "status": wo.status,
            "admin_notes": wo.admin_notes,
            "notes": wo.notes,
            "created_at": wo.created_at,
        }


class StockAgeingService:

    @staticmethod
    def get_ageing(db: Session, warehouse_id: Optional[int] = None) -> dict:
        today = date.today()
        q = db.query(StockEntry, Warehouse, Product).join(
            Warehouse, StockEntry.warehouse_id == Warehouse.id
        ).join(
            Product, StockEntry.product_id == Product.id
        ).filter(
            StockEntry.remaining_qty > 0,
            Warehouse.is_active == True,
            Product.is_active == True,
        )
        if warehouse_id:
            q = q.filter(StockEntry.warehouse_id == warehouse_id)

        eff_date_expr = func.coalesce(
            func.nullif(StockEntry.entry_date, '0000-00-00'),
            StockEntry.batch_date,
            func.date(StockEntry.created_at),
        )
        rows = q.order_by(eff_date_expr).all()
        buckets = {"0-30": [], "31-60": [], "61-90": [], "90+": []}
        summary = {"0-30": Decimal("0"), "31-60": Decimal("0"), "61-90": Decimal("0"), "90+": Decimal("0")}

        for se, wh, prod in rows:
            ed = se.entry_date if isinstance(se.entry_date, date) else None
            eff_date = ed or se.batch_date or se.created_at.date()
            age_days = (today - eff_date).days
            if age_days <= 30: bucket = "0-30"
            elif age_days <= 60: bucket = "31-60"
            elif age_days <= 90: bucket = "61-90"
            else: bucket = "90+"
            value = (se.remaining_qty * se.unit_cost).quantize(Decimal("0.01"))
            item = {
                "product_id": prod.id, "part_code": prod.part_code,
                "part_name": prod.part_name,
                "warehouse_name": wh.name,
                "batch_date": eff_date, "age_days": age_days,
                "quantity": se.remaining_qty,
                "unit_cost": se.unit_cost, "value": value,
                "age_bucket": bucket,
            }
            buckets[bucket].append(item)
            summary[bucket] += value

        return {
            "as_of_date": today,
            "buckets": buckets,
            "summary": {k: v.quantize(Decimal("0.01")) for k, v in summary.items()},
            "total_value": sum(summary.values()).quantize(Decimal("0.01")),
        }


class OpeningBalanceService:

    @staticmethod
    def create(db: Session, payload: OpeningBalanceCreate, user_id: int) -> dict:
        from app.models.models import (
            LedgerEntry, TransactionType, Customer, Vendor,
            Account
        )
        created_records = {"stock": 0, "customers": 0, "vendors": 0, "cash": 0, "bank": 0}

        # Opening stock
        for item in payload.stock_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
            StockService.add_stock(
                db, item.product_id, item.warehouse_id, item.quantity, item.unit_cost,
                StockTransactionType.adjustment_in, "opening_balance", 0,
                item.opening_date, user_id
            )
            created_records["stock"] += 1

        # Customer opening balances
        for cb in payload.customer_balances:
            customer = db.query(Customer).filter(Customer.id == cb.customer_id).first()
            if not customer:
                continue
            le = LedgerEntry(
                customer_id=cb.customer_id,
                transaction_type=TransactionType.debit,
                amount=cb.opening_balance,
                balance=cb.opening_balance,
                reference_type="opening_balance",
                reference_id=0,
                narration=f"Opening balance — {customer.trade_name}",
                entry_date=cb.opening_date,
                financial_year=payload.financial_year,
            )
            db.add(le)
            created_records["customers"] += 1

        # Vendor opening balances
        from app.models.models import Vendor
        for vb in payload.vendor_balances:
            vendor = db.query(Vendor).filter(Vendor.id == vb.vendor_id).first()
            if not vendor:
                continue
            le = LedgerEntry(
                vendor_id=vb.vendor_id,
                transaction_type=TransactionType.credit,
                amount=vb.opening_balance,
                balance=vb.opening_balance,
                reference_type="opening_balance",
                reference_id=0,
                narration=f"Opening balance — {vendor.trade_name}",
                entry_date=vb.opening_date,
                financial_year=payload.financial_year,
            )
            db.add(le)
            created_records["vendors"] += 1

        # Cash opening balance
        if payload.cash_balance:
            cash_acc = get_or_create_account(db, "CASH")
            if cash_acc:
                cash_acc.opening_balance = payload.cash_balance.amount
                created_records["cash"] = 1

        # Bank opening balances
        for bb in payload.bank_balances:
            bank_acc = db.query(Account).filter(Account.account_code == bb.account_code).first()
            if not bank_acc:
                bank_acc = Account(
                    account_code=bb.account_code,
                    account_name=f"{bb.bank_name} — {bb.account_number}",
                    account_type="bank",
                    opening_balance=bb.amount,
                    created_by=user_id,
                )
                db.add(bank_acc)
            else:
                bank_acc.opening_balance = bb.amount
            created_records["bank"] += 1

        db.commit()
        return {
            "message": "Opening balances created successfully",
            "created": created_records,
            "financial_year": payload.financial_year,
        }

    @staticmethod
    def get_stock_csv_template() -> str:
        headers = ["part_code", "warehouse_name", "quantity", "unit_cost", "opening_date"]
        sample = ["GTY00001", "Main Warehouse", "100", "250.00", "2025-04-01"]
        return "\n".join([",".join(headers), ",".join(sample)])

    @staticmethod
    def bulk_upload_stock(db: Session, file_content: str,
                          default_opening_date: date, user_id: int) -> dict:
        """Bulk-load opening stock from CSV.

        Columns: part_code, warehouse_name, quantity, unit_cost, opening_date (optional).
        Products are matched by part_code, warehouses by name (case-insensitive).
        opening_date falls back to default_opening_date when a row leaves it blank.
        Each valid row creates an 'opening_balance' FIFO layer (adjustment_in) — same
        path as the JSON endpoint. Adds to existing stock; it does not replace it.
        """
        reader = csv.DictReader(io.StringIO(file_content))
        required_cols = {"part_code", "warehouse_name", "quantity", "unit_cost"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            raise HTTPException(
                status_code=400,
                detail=f"Missing columns. Required: {sorted(required_cols)}",
            )

        errors = []
        created = []
        rows = list(reader)

        for idx, row in enumerate(rows, start=2):
            row_errors = []

            part_code = (row.get("part_code") or "").strip()
            product = None
            if not part_code:
                row_errors.append("part_code is required")
            else:
                product = db.query(Product).filter(
                    Product.part_code == part_code
                ).first()
                if not product:
                    row_errors.append(f"Product part_code '{part_code}' not found")

            wh_name = (row.get("warehouse_name") or "").strip()
            warehouse = None
            if not wh_name:
                row_errors.append("warehouse_name is required")
            else:
                warehouse = db.query(Warehouse).filter(
                    func.lower(Warehouse.name) == wh_name.lower(),
                    Warehouse.is_active == True,
                ).first()
                if not warehouse:
                    row_errors.append(f"Warehouse '{wh_name}' not found")

            quantity = None
            try:
                quantity = Decimal((row.get("quantity") or "").strip())
                if quantity <= 0:
                    row_errors.append("quantity must be greater than 0")
            except Exception:
                row_errors.append(f"Invalid quantity: '{row.get('quantity')}'")

            unit_cost = None
            try:
                unit_cost = Decimal((row.get("unit_cost") or "").strip())
                if unit_cost <= 0:
                    row_errors.append("unit_cost must be greater than 0")
            except Exception:
                row_errors.append(f"Invalid unit_cost: '{row.get('unit_cost')}'")

            opening_date = default_opening_date
            raw_date = (row.get("opening_date") or "").strip()
            if raw_date:
                try:
                    opening_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except ValueError:
                    row_errors.append(f"Invalid opening_date (use YYYY-MM-DD): '{raw_date}'")

            if row_errors:
                errors.append({"row": idx, "data": part_code, "errors": row_errors})
                continue

            try:
                with db.begin_nested():
                    StockService.add_stock(
                        db, product.id, warehouse.id, quantity, unit_cost,
                        StockTransactionType.adjustment_in, "opening_balance", 0,
                        opening_date, user_id,
                    )
                created.append(part_code)
            except Exception as e:
                errors.append({"row": idx, "data": part_code, "errors": [str(e)]})

        db.commit()
        return {
            "total_rows": len(rows),
            "success_count": len(created),
            "error_count": len(errors),
            "errors": errors,
            "created": created,
        }
