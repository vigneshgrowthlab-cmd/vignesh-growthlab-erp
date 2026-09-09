from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from fastapi import HTTPException
from decimal import Decimal
from datetime import date, datetime
from typing import Optional, List

from app.models.models import (
    Purchase, PurchaseItem, Vendor, Warehouse, Product,
    LedgerEntry, TransactionType, JournalEntry, JournalLine,
    Account, VendorPayment, StockEntry, StockTransactionType,
    WarehouseStock, VendorProduct, ProductCostHistory, GSTType, PriceAlert,
    CompanySettings,
)
from app.schemas.purchase import PurchaseCreate, VendorPaymentCreate
from app.services.product_service import CostTrackingService, StockService
from app.services.price_history_service import activate_scheduled_prices, record_price_change
from app.utils.helpers import (
    get_or_create_account, paginate, get_current_fy, get_financial_year,
    determine_gst_type, calculate_gst, next_sequence_number, _seed_from_suffix,
    format_document_number, derive_state_code, resolve_state_code,
)
from app.services.audit import audit, diff

from app.core.config import settings


class PurchaseService:

    @staticmethod
    def _get_account(db, code):
        return get_or_create_account(db, code)

    @staticmethod
    def _post_journal(db: Session, entry_date: date, reference_type: str,
                      reference_id: int, narration: str, fy: str,
                      lines: list, user_id: int):
        # Atomic row-locked counter — avoids count()+1 races under concurrent writes.
        seq = next_sequence_number(
            db, "journal_entry", "JE", fy,
            seed_from=lambda d, f: _seed_from_suffix(d, f, "journal_entries", "entry_number"),
        )
        je = JournalEntry(
            entry_number=format_document_number(db, "JE", fy, seq, "JE", 5),
            entry_date=entry_date, reference_type=reference_type,
            reference_id=reference_id, narration=narration,
            financial_year=fy, created_by=user_id,
        )
        db.add(je)
        db.flush()
        for acc_code, txn_type, amount in lines:
            acc = PurchaseService._get_account(db, acc_code)
            jl = JournalLine(
                journal_entry_id=je.id, account_id=acc.id,
                transaction_type=txn_type, amount=amount,
            )
            db.add(jl)

    @staticmethod
    def _post_vendor_ledger(db: Session, vendor_id: int, txn_type: TransactionType,
                            amount: Decimal, ref_type: str, ref_id: int,
                            narration: str, entry_date: date, fy: str):
        # Lock the vendor row for the duration of the transaction so all
        # ledger postings for this vendor serialize. Without this, two
        # concurrent purchases/payments read the same prev_bal and write a
        # wrong running balance (read-modify-write race).
        db.query(Vendor).filter(Vendor.id == vendor_id).with_for_update().first()
        last = db.query(LedgerEntry).filter(
            LedgerEntry.vendor_id == vendor_id
        ).order_by(desc(LedgerEntry.id)).first()
        prev_bal = last.balance if last else Decimal("0")
        balance = prev_bal + amount if txn_type == TransactionType.credit else prev_bal - amount
        le = LedgerEntry(
            vendor_id=vendor_id, transaction_type=txn_type,
            amount=amount, balance=balance,
            reference_type=ref_type, reference_id=ref_id,
            narration=narration, entry_date=entry_date, financial_year=fy,
        )
        db.add(le)

    @staticmethod
    def _reprice_on_cost_change(db: Session, product, old_cost, new_cost, user_id: int):
        """Re-derive floor + selling prices when a product's purchase cost
        changes, preserving each tier's existing margin.

        For every set tier (floor_price, b2b_price, b2c_price, mrp) we keep the
        ratio price/cost constant: new_price = new_cost * (old_price / old_cost).
        Holding that ratio holds BOTH markup% ((p-c)/c) and margin% ((p-c)/p)
        constant, and — because every tier is scaled off the same old_cost —
        it preserves the floor<=b2b<=b2c<=mrp ordering and floor>=cost rule.
        Each changed tier is written to price history. Repricing is skipped when
        there is no prior cost to anchor the ratio to (e.g. first-ever purchase).
        """
        old_cost = Decimal(str(old_cost or 0))
        new_cost = Decimal(str(new_cost or 0))
        if old_cost <= 0 or new_cost <= 0 or new_cost == old_cost:
            return
        reason = f"Auto-reprice on cost change ₹{old_cost} → ₹{new_cost}"
        for ptype in ("floor_price", "b2b_price", "b2c_price", "mrp"):
            old_price = Decimal(str(getattr(product, ptype, None) or 0))
            if old_price <= 0:
                continue  # tier not set — don't invent a price
            new_price = (new_cost * (old_price / old_cost)).quantize(Decimal("0.01"))
            if new_price == old_price:
                continue
            setattr(product, ptype, new_price)
            record_price_change(
                db, product.id, ptype, new_price, date.today(), user_id, reason
            )

    @staticmethod
    def list_purchases(db: Session, page: int = 1, page_size: int = 20,
                       vendor_id: Optional[int] = None,
                       financial_year: Optional[str] = None,
                       search: Optional[str] = None) -> dict:
        q = db.query(Purchase)
        if vendor_id:
            q = q.filter(Purchase.vendor_id == vendor_id)
        if financial_year:
            q = q.filter(Purchase.financial_year == financial_year)
        if search:
            like = f"%{search}%"
            q = q.filter(or_(
                Purchase.vendor_invoice_number.ilike(like),
                Purchase.purchase_number.ilike(like),
            ))
        result = paginate(q.order_by(desc(Purchase.invoice_date), desc(Purchase.id)), page, page_size)

        # Get paid amounts for all purchases in this page in one query
        purchase_ids = [p.id for p in result["items"]]
        paid_map = {}
        if purchase_ids:
            rows = db.query(
                VendorPayment.purchase_id,
                func.sum(VendorPayment.amount).label("paid")
            ).filter(
                VendorPayment.purchase_id.in_(purchase_ids),
                VendorPayment.is_void == False,
            ).group_by(VendorPayment.purchase_id).all()
            paid_map = {r.purchase_id: float(r.paid) for r in rows}

        items = []
        for p in result["items"]:
            total = float(p.total_amount or 0)
            linked_paid = paid_map.get(p.id, 0.0)
            stored_paid = float(getattr(p, 'paid_amount', None) or 0)
            # Use max: FIFO may have stored paid_amount higher than linked payments
            paid = max(linked_paid, stored_paid)
            outstanding = max(0.0, total - paid)
            payment_status = (
                "cancelled" if p.is_cancelled
                else "paid" if outstanding <= 0.001
                else "partial" if paid > 0
                else "outstanding"
            )
            items.append({
                "id": p.id,
                "vendor_name": p.vendor.trade_name if p.vendor else None,
                "warehouse_name": None,
                "vendor_invoice_number": p.vendor_invoice_number,
                "purchase_number": p.purchase_number,
                "invoice_date": p.invoice_date,
                "total_amount": total,
                "paid_amount": paid,
                "outstanding_amount": outstanding,
                "payment_status": payment_status,
                "gst_type": p.gst_type,
                "financial_year": p.financial_year,
                "is_cancelled": p.is_cancelled,
                "created_at": p.created_at,
            })
        result["items"] = items
        return result

    @staticmethod
    def get_by_id(db: Session, purchase_id: int) -> dict:
        p = db.query(Purchase).filter(Purchase.id == purchase_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Purchase not found")
        prod_ids = [item.product_id for item in p.items]
        prod_map = {}
        if prod_ids:
            prod_map = {
                pr.id: pr
                for pr in db.query(Product).filter(Product.id.in_(prod_ids)).all()
            }
        items = []
        for item in p.items:
            prod = prod_map.get(item.product_id)
            items.append({
                "id": item.id, "product_id": item.product_id,
                "part_code": prod.part_code if prod else None,
                "part_name": prod.part_name if prod else None,
                "quantity": item.quantity, "unit_cost": item.unit_cost,
                "gst_percent": item.gst_percent, "cgst_amount": item.cgst_amount,
                "sgst_amount": item.sgst_amount, "igst_amount": item.igst_amount,
                "line_total": item.line_total, "hsn_code": item.hsn_code,
            })
        wh = db.query(Warehouse).filter(Warehouse.id == p.warehouse_id).first()
        return {
            "id": p.id, "vendor_id": p.vendor_id,
            "vendor_name": p.vendor.trade_name if p.vendor else None,
            "warehouse_id": p.warehouse_id,
            "warehouse_name": wh.name if wh else None,
            "vendor_invoice_number": p.vendor_invoice_number,
            "invoice_date": p.invoice_date, "received_date": p.received_date,
            "payment_due_date": getattr(p, 'payment_due_date', None),
            "subtotal": p.subtotal, "total_cgst": p.total_cgst,
            "total_sgst": p.total_sgst, "total_igst": p.total_igst,
            "total_amount": p.total_amount, "gst_type": p.gst_type,
            "notes": p.notes, "financial_year": p.financial_year,
            "is_cancelled": p.is_cancelled, "created_at": p.created_at,
            "items": items,
        }

    @staticmethod
    def update(db: Session, purchase_id: int, payload, user_id: int) -> dict:
        """Edit mutable non-financial fields on a purchase.

        Only `notes`, `received_date`, `payment_due_date` are editable — line
        items / amounts must be cancelled-and-re-entered for an auditable trail.
        """
        p = db.query(Purchase).filter(Purchase.id == purchase_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Purchase not found")
        if p.is_cancelled:
            raise HTTPException(status_code=400, detail="Cannot edit a cancelled purchase")

        data = payload.model_dump(exclude_none=True)
        if "received_date" in data and data["received_date"] < p.invoice_date:
            raise HTTPException(status_code=422, detail="received_date cannot be earlier than invoice_date")
        if "payment_due_date" in data and data["payment_due_date"] < p.invoice_date:
            raise HTTPException(status_code=422, detail="payment_due_date cannot be earlier than invoice_date")

        old = {f: getattr(p, f, None) for f in data.keys()}
        for field, value in data.items():
            setattr(p, field, value)
        p.updated_by = user_id
        db.commit()
        new = {f: getattr(p, f, None) for f in data.keys()}
        changed, summary = diff(old, new, list(data.keys()))
        if changed:
            audit(db, user_id, "update", "purchase",
                  f"Updated purchase {p.vendor_invoice_number}: {summary}",
                  record_type="purchase", record_id=p.id,
                  old={k: val[0] for k, val in changed.items()},
                  new={k: val[1] for k, val in changed.items()})
        return PurchaseService.get_by_id(db, purchase_id)

    @staticmethod
    def create(db: Session, payload: PurchaseCreate, user_id: int) -> dict:
        vendor = db.query(Vendor).filter(Vendor.id == payload.vendor_id, Vendor.is_active == True).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id, Warehouse.is_active == True).first()
        if not warehouse:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        # Idempotency: a supplier invoice number must not be recorded twice for
        # the same vendor (re-submission would double stock, ITC and liability).
        # Cancelled purchases are ignored so a number can be re-entered after a
        # cancel-and-correct.
        dup = db.query(Purchase).filter(
            Purchase.vendor_id == payload.vendor_id,
            Purchase.vendor_invoice_number == payload.vendor_invoice_number,
            Purchase.is_cancelled == False,
        ).first()
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Invoice '{payload.vendor_invoice_number}' is already recorded for this vendor (purchase {dup.purchase_number}).",
            )

        fy = get_financial_year(payload.invoice_date)

        # Decide CGST/SGST vs IGST by comparing state CODES, mirroring the
        # invoice-side logic in billing_service. Origin = vendor, resolved via
        # explicit state_code > GSTIN prefix > state name (older vendor rows
        # may have only a name or GSTIN). Destination = receiving warehouse,
        # falling back to company state. Name comparison is the last resort
        # when no code can be derived for the vendor.
        vendor_code = derive_state_code(vendor.gstin, vendor.state, vendor.state_code)
        company = db.query(CompanySettings).first()
        # Resolve company (buyer) state code: env GSTIN prefix and env state name
        # are more authoritative than a potentially stale DB state_code (e.g. the
        # row may have been seeded with a placeholder before COMPANY_GSTIN/.env
        # was configured). derive_state_code is called without `explicit` so the
        # GSTIN prefix takes precedence over any stored integer.
        company_state_code = (
            derive_state_code(settings.COMPANY_GSTIN, settings.COMPANY_STATE)
            or (company.state_code if company else None)
            or settings.COMPANY_STATE_CODE
        )
        dest_code = (warehouse.state_code
                     or resolve_state_code(warehouse.state)
                     or company_state_code)

        if vendor_code and dest_code:
            gst_type_str = determine_gst_type(vendor_code, dest_code)
        elif vendor.state and warehouse.state:
            gst_type_str = "cgst_sgst" if (
                vendor.state.lower().strip() == warehouse.state.lower().strip()
            ) else "igst"
        else:
            gst_type_str = "igst"
        gst_type = GSTType.cgst_sgst if gst_type_str == "cgst_sgst" else GSTType.igst

        subtotal = Decimal("0")
        total_cgst = Decimal("0")
        total_sgst = Decimal("0")
        total_igst = Decimal("0")
        gst_mismatches = []

        # Generate purchase number via atomic per-FY sequence
        seq = next_sequence_number(db, "purchase", "PO", fy)
        purchase_number = format_document_number(db, "PO", fy, seq, "PO", 4)

        purchase = Purchase(
            purchase_number=purchase_number,
            vendor_id=payload.vendor_id, warehouse_id=payload.warehouse_id,
            vendor_invoice_number=payload.vendor_invoice_number,
            invoice_date=payload.invoice_date, received_date=payload.received_date,
            payment_due_date=getattr(payload, 'payment_due_date', None),
            notes=payload.notes, gst_type=gst_type, financial_year=fy,
            created_by=user_id,
        )
        db.add(purchase)
        db.flush()

        for item_data in payload.items:
            product = db.query(Product).filter(Product.id == item_data.product_id, Product.is_active == True).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item_data.product_id} not found")

            # GST-rate watch: a purchase line carries the vendor's rate, which may
            # differ from our product master. This is non-blocking — the vendor
            # invoice is recorded as entered — but a mismatch is flagged in the
            # in-app alert inbox + audit log for super-admin review.
            master_rate = product.gst_percent
            if (master_rate is not None and item_data.gst_percent is not None
                    and Decimal(str(item_data.gst_percent)) != Decimal(str(master_rate))):
                db.add(PriceAlert(
                    product_id=product.id,
                    alert_type="gst_mismatch",
                    severity="warning",
                    message=(
                        f"GST mismatch on purchase {purchase_number}: entered "
                        f"{item_data.gst_percent}% vs product master {master_rate}% "
                        f"for {product.part_name} ({product.part_code}); vendor "
                        f"{vendor.trade_name}, invoice {payload.vendor_invoice_number}."
                    ),
                ))
                gst_mismatches.append(
                    f"{product.part_code}: {item_data.gst_percent}% vs master {master_rate}%"
                )

            # Quantize each component to paisa BEFORE accumulating. calculate_gst
            # already rounds GST to 2dp; rounding taxable here too means subtotal
            # and the tax totals are exact sums of 2dp values, so the journal
            # legs (STOCK + GST debits vs CREDITORS credit) balance to the paisa.
            taxable = (item_data.unit_cost * item_data.quantity).quantize(Decimal("0.01"))
            gst_amounts = calculate_gst(float(taxable), float(item_data.gst_percent), gst_type_str)
            cgst = Decimal(str(gst_amounts['cgst']))
            sgst = Decimal(str(gst_amounts['sgst']))
            igst = Decimal(str(gst_amounts['igst']))
            line_total = (taxable + cgst + sgst + igst).quantize(Decimal("0.01"))

            pi = PurchaseItem(
                purchase_id=purchase.id, product_id=item_data.product_id,
                quantity=item_data.quantity, unit_cost=item_data.unit_cost,
                gst_percent=item_data.gst_percent, hsn_code=item_data.hsn_code,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                line_total=line_total,
            )
            db.add(pi)
            db.flush()  # get pi.id

            subtotal += taxable
            total_cgst += cgst
            total_sgst += sgst
            total_igst += igst

            # FIFO stock layer
            StockService.add_stock(
                db, item_data.product_id, payload.warehouse_id,
                item_data.quantity, item_data.unit_cost,
                StockTransactionType.purchase, "purchase", purchase.id,
                payload.invoice_date, user_id
            )

            # Activate any scheduled prices for this product
            activate_scheduled_prices(db, item_data.product_id)

            # Price-history source of truth: one purchase_cost row per purchase
            # in product_prices (also updates products.purchase_cost).
            from datetime import date as _dt
            record_price_change(
                db, item_data.product_id, "purchase_cost",
                item_data.unit_cost, _dt.today(), user_id,
                f"Purchase {payload.vendor_invoice_number or 'N/A'}"
            )

            # Cost-ledger source of truth: per-purchase row in product_cost_history
            # (drives the margin-trend report and cost-revert on cancel).
            old_cost = product.purchase_cost
            CostTrackingService.record_cost(
                db, item_data.product_id, payload.vendor_id, purchase.id,
                item_data.unit_cost, item_data.quantity, fy
            )
            # NOTE: the legacy record_price_history() call was removed here — it
            # re-wrote the same purchase_cost row and spuriously snapshotted
            # unchanged b2b/b2c selling prices on every purchase. Selling-price
            # history is recorded only when those prices actually change.
            if item_data.unit_cost != old_cost:
                CostTrackingService.check_and_alert(db, product, old_cost, item_data.unit_cost)
                product.purchase_cost = item_data.unit_cost
                # Propagate the cost change to floor + selling prices, keeping
                # each tier's existing margin (records its own price history).
                PurchaseService._reprice_on_cost_change(
                    db, product, old_cost, item_data.unit_cost, user_id
                )

            # Update vendor product record
            vp = db.query(VendorProduct).filter(
                VendorProduct.vendor_id == payload.vendor_id,
                VendorProduct.product_id == item_data.product_id
            ).first()
            if not vp:
                vp = VendorProduct(vendor_id=payload.vendor_id, product_id=item_data.product_id)
                db.add(vp)
            vp.last_price = item_data.unit_cost
            vp.last_purchase_date = payload.invoice_date

        # subtotal and the tax totals are already exact 2dp sums, so total_amount
        # is an exact sum — no further rounding that could unbalance the journal.
        total_amount = subtotal + total_cgst + total_sgst + total_igst
        purchase.subtotal = subtotal
        purchase.total_cgst = total_cgst
        purchase.total_sgst = total_sgst
        purchase.total_igst = total_igst
        purchase.total_amount = total_amount

        # Vendor ledger
        PurchaseService._post_vendor_ledger(
            db, payload.vendor_id, TransactionType.credit,
            total_amount,
            "purchase", purchase.id,
            f"Purchase {payload.vendor_invoice_number}",
            payload.invoice_date, fy
        )

        # Double-entry journal
        journal_lines = [
            ("STOCK", TransactionType.debit, subtotal),
            ("CREDITORS", TransactionType.credit, total_amount),
        ]
        if total_cgst > 0:
            journal_lines.append(("GST_ITC", TransactionType.debit, total_cgst))
        if total_sgst > 0:
            journal_lines.append(("GST_ITC", TransactionType.debit, total_sgst))
        if total_igst > 0:
            journal_lines.append(("GST_ITC", TransactionType.debit, total_igst))

        PurchaseService._post_journal(
            db, payload.invoice_date, "purchase", purchase.id,
            f"Purchase from {vendor.trade_name} — {payload.vendor_invoice_number}",
            fy, journal_lines, user_id
        )

        # Apply any existing unallocated payments / advances for this vendor to
        # the new purchase so cached paid/outstanding counters stay consistent
        # with the vendor ledger (otherwise advances never reconcile).
        VendorPaymentService._recompute_purchase_paid_amounts(db, payload.vendor_id)

        db.commit()
        audit(db, user_id, "create", "purchase",
              f"Created purchase {payload.vendor_invoice_number} from "
              f"{vendor.trade_name} — ₹{total_amount}",
              record_type="purchase", record_id=purchase.id)
        if gst_mismatches:
            audit(db, user_id, "alert", "purchase",
                  f"GST rate mismatch flagged on purchase {purchase_number} — "
                  + "; ".join(gst_mismatches),
                  record_type="purchase", record_id=purchase.id)
        return PurchaseService.get_by_id(db, purchase.id)

    @staticmethod
    def cancel(db: Session, purchase_id: int, user_id: int) -> dict:
        p = db.query(Purchase).filter(Purchase.id == purchase_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Purchase not found")
        if p.is_cancelled:
            raise HTTPException(status_code=400, detail="Purchase already cancelled")

        # ── Guard: any FIFO layer from this purchase that has been consumed
        # blocks cancellation. The user must reverse the sale / adjustment
        # first so the books stay balanced.
        layers = db.query(StockEntry).filter(
            StockEntry.reference_type == "purchase",
            StockEntry.reference_id == p.id,
            StockEntry.transaction_type == StockTransactionType.purchase,
        ).all()
        consumed = []
        for layer in layers:
            q = Decimal(str(layer.quantity or 0))
            rem = Decimal(str(layer.remaining_qty or 0))
            if rem < q:
                prod = db.query(Product).filter(Product.id == layer.product_id).first()
                consumed.append({
                    "product_id": layer.product_id,
                    "part_code": prod.part_code if prod else None,
                    "consumed_qty": float(q - rem),
                    "original_qty": float(q),
                })
        if consumed:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Cannot cancel: stock from this purchase has been consumed. Reverse the sales / adjustments first.",
                    "consumed_items": consumed,
                }
            )

        # ── Guard: any payment applied to this purchase blocks cancellation.
        # Reversing the full purchase credit while payment debits remain would
        # drive the vendor ledger negative and leave paid_amount dangling. The
        # user must void the payments first. Covers both directly-linked
        # payments and FIFO-applied amounts (reflected in paid_amount).
        linked_paid = db.query(func.sum(VendorPayment.amount)).filter(
            VendorPayment.purchase_id == p.id,
            VendorPayment.is_void == False,
        ).scalar() or Decimal("0")
        applied_paid = max(Decimal(str(linked_paid)), Decimal(str(p.paid_amount or 0)))
        if applied_paid > Decimal("0"):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Cannot cancel: payments have been applied to this purchase. Void the payments first.",
                    "applied_amount": float(applied_paid),
                }
            )

        fy = p.financial_year or get_financial_year(p.invoice_date)
        total_to_reverse = Decimal(str(p.total_amount or 0))

        # ── 1. Reverse stock: zero each FIFO layer, decrement WarehouseStock,
        # and write an audit return_out row so history is greppable.
        for layer in layers:
            layer_qty = Decimal(str(layer.quantity or 0))
            ws = db.query(WarehouseStock).filter(
                WarehouseStock.product_id == layer.product_id,
                WarehouseStock.warehouse_id == layer.warehouse_id
            ).with_for_update().first()
            if ws:
                ws.quantity = max(Decimal("0"), Decimal(str(ws.quantity or 0)) - layer_qty)
            layer.remaining_qty = Decimal("0")
            db.add(StockEntry(
                product_id=layer.product_id,
                warehouse_id=layer.warehouse_id,
                transaction_type=StockTransactionType.return_out,
                quantity=layer_qty,
                unit_cost=layer.unit_cost,
                remaining_qty=Decimal("0"),
                reference_type="purchase_cancel",
                reference_id=p.id,
                batch_date=date.today(),
                created_by=user_id,
            ))

        # ── 2. Revert product.purchase_cost when this purchase was the last
        # cost setter for the product (best-effort: requires cost history).
        for item in p.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product or not product.purchase_cost:
                continue
            if Decimal(str(product.purchase_cost)) != Decimal(str(item.unit_cost or 0)):
                continue
            prev = db.query(ProductCostHistory).filter(
                ProductCostHistory.product_id == item.product_id,
                ProductCostHistory.purchase_id != p.id,
            ).order_by(desc(ProductCostHistory.recorded_at)).first()
            if prev and prev.unit_cost is not None:
                product.purchase_cost = prev.unit_cost

        # ── 3. Reverse the journal entry — mirror the original lines with
        # debit/credit swapped so the net effect on accounts is zero.
        subtotal = Decimal(str(p.subtotal or 0))
        total_cgst = Decimal(str(p.total_cgst or 0))
        total_sgst = Decimal(str(p.total_sgst or 0))
        total_igst = Decimal(str(p.total_igst or 0))
        journal_lines = [
            ("STOCK", TransactionType.credit, subtotal),
            ("CREDITORS", TransactionType.debit, total_to_reverse),
        ]
        if total_cgst > 0:
            journal_lines.append(("GST_ITC", TransactionType.credit, total_cgst))
        if total_sgst > 0:
            journal_lines.append(("GST_ITC", TransactionType.credit, total_sgst))
        if total_igst > 0:
            journal_lines.append(("GST_ITC", TransactionType.credit, total_igst))
        PurchaseService._post_journal(
            db, date.today(), "purchase_cancel", p.id,
            f"Cancellation reversal of {p.purchase_number}",
            fy, journal_lines, user_id
        )

        # ── 4. Reverse vendor ledger (debit reduces outstanding back to pre-purchase)
        PurchaseService._post_vendor_ledger(
            db, p.vendor_id, TransactionType.debit,
            total_to_reverse,
            "purchase_cancel", p.id,
            f"Cancellation of Purchase {p.purchase_number}",
            date.today(), fy
        )

        p.is_cancelled = True
        p.outstanding_amount = Decimal("0")
        p.updated_by = user_id
        db.commit()
        audit(db, user_id, "cancel", "purchase",
              f"Cancelled purchase {p.purchase_number} — reversed ₹{total_to_reverse}",
              record_type="purchase", record_id=p.id,
              old={"is_cancelled": False}, new={"is_cancelled": True})
        return {
            "message": "Purchase cancelled and fully reversed",
            "purchase_number": p.purchase_number,
            "reversed_amount": float(total_to_reverse),
        }


class VendorPaymentService:

    @staticmethod
    def create(db: Session, payload: VendorPaymentCreate, user_id: int) -> dict:
        vendor = db.query(Vendor).filter(Vendor.id == payload.vendor_id).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        # Block payment against a cancelled purchase
        if payload.purchase_id:
            pur = db.query(Purchase).filter(Purchase.id == payload.purchase_id).first()
            if not pur:
                raise HTTPException(status_code=404, detail="Purchase not found")
            if pur.is_cancelled:
                raise HTTPException(status_code=400, detail="Cannot record payment against a cancelled purchase")
            if pur.vendor_id != payload.vendor_id:
                raise HTTPException(status_code=400, detail="Purchase does not belong to this vendor")

        fy = get_financial_year(payload.payment_date)
        seq = next_sequence_number(
            db, "vendor_payment", "VP", fy,
            seed_from=lambda d, f: _seed_from_suffix(d, f, "vendor_payments", "payment_number"),
        )
        payment_number = format_document_number(db, "VP", fy, seq, "VP", 4)

        payment = VendorPayment(
            payment_number=payment_number, vendor_id=payload.vendor_id,
            purchase_id=payload.purchase_id, payment_date=payload.payment_date,
            amount=payload.amount, payment_mode=payload.payment_mode,
            reference_number=payload.reference_number, notes=payload.notes,
            is_advance=payload.is_advance, financial_year=fy,
            created_by=user_id,
        )
        db.add(payment)
        db.flush()

        # Vendor ledger — debit (reduces outstanding)
        PurchaseService._post_vendor_ledger(
            db, payload.vendor_id, TransactionType.debit,
            payload.amount, "vendor_payment", payment.id,
            f"Payment {'(Advance)' if payload.is_advance else ''} — {payment_number}",
            payload.payment_date, fy
        )

        # Journal
        pay_acc = "CASH" if str(payload.payment_mode).lower() == "cash" else "BANK"
        PurchaseService._post_journal(
            db, payload.payment_date, "vendor_payment", payment.id,
            f"Payment to {vendor.trade_name}",
            fy,
            [
                ("CREDITORS", TransactionType.debit, payload.amount),
                (pay_acc, TransactionType.credit, payload.amount),
            ],
            user_id
        )

        # Recompute cached paid/outstanding for ALL of this vendor's purchases
        # from the full set of active payments — specific payments first, then
        # general payments and advances applied FIFO. Single source of truth so
        # advances reconcile and counters stay consistent with the ledger.
        VendorPaymentService._recompute_purchase_paid_amounts(db, payload.vendor_id)

        db.commit()
        db.refresh(payment)
        audit(db, user_id, "payment", "purchase",
              f"Vendor payment {payment.payment_number} of ₹{payload.amount} to "
              f"{vendor.trade_name} via {payload.payment_mode}"
              + (" (advance)" if payload.is_advance else ""),
              record_type="vendor_payment", record_id=payment.id)
        return {
            "id": payment.id, "payment_number": payment.payment_number,
            "vendor_id": payment.vendor_id,
            "vendor_name": vendor.trade_name,
            "purchase_id": payment.purchase_id,
            "payment_date": payment.payment_date,
            "amount": payment.amount, "payment_mode": payment.payment_mode,
            "is_advance": payment.is_advance,
            "financial_year": payment.financial_year,
            "created_at": payment.created_at,
        }

    @staticmethod
    def list_payments(db: Session, vendor_id: Optional[int] = None,
                      purchase_id: Optional[int] = None,
                      financial_year: Optional[str] = None,
                      page: int = 1, page_size: int = 20,
                      include_voided: bool = False) -> dict:
        q = db.query(VendorPayment)
        if not include_voided:
            q = q.filter(VendorPayment.is_void == False)
        if vendor_id:
            q = q.filter(VendorPayment.vendor_id == vendor_id)
        if purchase_id:
            q = q.filter(VendorPayment.purchase_id == purchase_id)
        if financial_year:
            q = q.filter(VendorPayment.financial_year == financial_year)
        result = paginate(q.order_by(desc(VendorPayment.payment_date), desc(VendorPayment.id)), page, page_size)
        vendor_ids = {p.vendor_id for p in result["items"]}
        vendor_map = {}
        if vendor_ids:
            vendor_map = {
                vd.id: vd
                for vd in db.query(Vendor).filter(Vendor.id.in_(vendor_ids)).all()
            }
        items = []
        for p in result["items"]:
            v = vendor_map.get(p.vendor_id)
            items.append({
                "id": p.id, "payment_number": p.payment_number,
                "vendor_id": p.vendor_id,
                "vendor_name": v.trade_name if v else None,
                "purchase_id": p.purchase_id,
                "payment_date": p.payment_date,
                "amount": p.amount, "payment_mode": p.payment_mode,
                "is_advance": p.is_advance,
                "financial_year": p.financial_year,
                "is_void": bool(p.is_void),
                "voided_at": p.voided_at,
                "created_at": p.created_at,
                "reference_number": p.reference_number,
                "notes": p.notes,
            })
        result["items"] = items
        return result

    @staticmethod
    def _recompute_purchase_paid_amounts(db: Session, vendor_id: int):
        """Rebuild paid_amount / outstanding_amount for all non-cancelled
        purchases of a vendor from the set of currently active (non-void)
        payments. This is the single source of truth for the cached counters,
        called from payment create, payment void, and purchase create.

        Two passes:
          1. Payments tied to a specific purchase are applied to that purchase.
          2. Unallocated payments — general payments AND advances (neither has a
             purchase_id) — are applied FIFO to the oldest still-outstanding
             purchases. Including advances here is what lets a prepayment
             reconcile against invoices instead of staying outstanding forever.
        Any advance amount left over after all purchases are settled simply
        remains as a credit balance on the vendor ledger.

        SessionLocal has autoflush=False, so callers that mutated is_void
        in-memory must rely on the flush() here to push it to the DB before
        the payments SELECT runs. Otherwise the just-voided payment leaks
        back in as 'active'.
        """
        db.flush()
        purchases = db.query(Purchase).filter(
            Purchase.vendor_id == vendor_id,
            Purchase.is_cancelled == False,
        ).order_by(Purchase.invoice_date.asc(), Purchase.id.asc()).all()
        for pur in purchases:
            pur.paid_amount = Decimal("0")
            pur.outstanding_amount = Decimal(str(pur.total_amount or 0))

        payments = db.query(VendorPayment).filter(
            VendorPayment.vendor_id == vendor_id,
            VendorPayment.is_void == False,
        ).order_by(VendorPayment.payment_date.asc(), VendorPayment.id.asc()).all()

        # Pass 1: payments tied to a specific purchase.
        for pay in payments:
            if not pay.purchase_id:
                continue
            pur = next((x for x in purchases if x.id == pay.purchase_id), None)
            if not pur:
                continue
            amount = Decimal(str(pay.amount or 0))
            paid = Decimal(str(pur.paid_amount or 0)) + amount
            pur.paid_amount = paid
            total = Decimal(str(pur.total_amount or 0))
            pur.outstanding_amount = max(Decimal("0"), total - paid)

        # Pass 2: unallocated payments + advances applied FIFO.
        for pay in payments:
            if pay.purchase_id:
                continue
            remaining = Decimal(str(pay.amount or 0))
            for pur in purchases:
                if remaining <= Decimal("0"):
                    break
                total = Decimal(str(pur.total_amount or 0))
                already = Decimal(str(pur.paid_amount or 0))
                outstanding = max(Decimal("0"), total - already)
                if outstanding <= Decimal("0"):
                    continue
                apply_amt = min(remaining, outstanding)
                pur.paid_amount = already + apply_amt
                pur.outstanding_amount = max(Decimal("0"), outstanding - apply_amt)
                remaining -= apply_amt
        db.flush()

    @staticmethod
    def void(db: Session, payment_id: int, user_id: int) -> dict:
        pay = db.query(VendorPayment).filter(VendorPayment.id == payment_id).first()
        if not pay:
            raise HTTPException(status_code=404, detail="Payment not found")
        if pay.is_void:
            raise HTTPException(status_code=400, detail="Payment already voided")

        fy = pay.financial_year or get_financial_year(pay.payment_date)
        vendor = db.query(Vendor).filter(Vendor.id == pay.vendor_id).first()
        amount = Decimal(str(pay.amount or 0))

        # ── Reverse vendor ledger: original was DEBIT (reducing outstanding);
        # void posts CREDIT to restore the outstanding back to where it was.
        PurchaseService._post_vendor_ledger(
            db, pay.vendor_id, TransactionType.credit,
            amount,
            "vendor_payment_void", pay.id,
            f"Void of Payment {pay.payment_number}",
            date.today(), fy
        )

        # ── Reverse journal: original was CREDITORS debit + CASH/BANK credit;
        # void posts CREDITORS credit + CASH/BANK debit.
        pay_acc = "CASH" if str(pay.payment_mode).lower() == "cash" else "BANK"
        PurchaseService._post_journal(
            db, date.today(), "vendor_payment_void", pay.id,
            f"Void payment to {vendor.trade_name if vendor else pay.vendor_id}",
            fy,
            [
                ("CREDITORS", TransactionType.credit, amount),
                (pay_acc, TransactionType.debit, amount),
            ],
            user_id
        )

        # ── Mark void after reversing entries so audit timeline is correct.
        pay.is_void = True
        pay.voided_at = datetime.now()
        pay.voided_by = user_id

        # ── Recompute cached counters on the vendor's purchases.
        VendorPaymentService._recompute_purchase_paid_amounts(db, pay.vendor_id)

        db.commit()
        audit(db, user_id, "void", "purchase",
              f"Voided vendor payment {pay.payment_number} of ₹{amount} to "
              f"{vendor.trade_name if vendor else pay.vendor_id}",
              record_type="vendor_payment", record_id=pay.id,
              old={"is_void": False}, new={"is_void": True})
        return {
            "message": "Payment voided",
            "payment_number": pay.payment_number,
            "voided_amount": float(amount),
        }
