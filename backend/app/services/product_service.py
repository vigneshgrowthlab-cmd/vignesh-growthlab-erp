from sqlalchemy.orm import Session
from sqlalchemy import func, case
from fastapi import HTTPException
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List
import csv
import io

from app.models.models import (
    Product, Category, WarehouseStock, StockEntry, ProductCostHistory,
    CostAlert, AlertType, StockTransactionType, StockAdjustment, Warehouse,
    User
)
from app.schemas.products import (
    ProductCreate, ProductUpdate, CategoryCreate, CategoryUpdate,
    StockAdjustmentCreate, BulkPriceUpdate
)
from app.utils.helpers import (
    get_current_fy, get_financial_year, paginate,
    next_sequence_number, _seed_from_number_fy, format_document_number,
)
from app.services.config_service import ConfigService
from app.services.audit import audit, diff


# ─── Category Service ────────────────────────────────────────

class CategoryService:

    @staticmethod
    def get_all(db: Session, include_inactive: bool = False) -> List[Category]:
        q = db.query(Category)
        if not include_inactive:
            q = q.filter(Category.is_active == True)
        return q.order_by(Category.name).all()

    @staticmethod
    def get_by_id(db: Session, category_id: int) -> Category:
        cat = db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        return cat

    @staticmethod
    def create(db: Session, payload: CategoryCreate, user_id: int) -> Category:
        if db.query(Category).filter(Category.prefix == payload.prefix.upper()).first():
            raise HTTPException(status_code=400, detail=f"Prefix '{payload.prefix}' already exists")
        if db.query(Category).filter(Category.name == payload.name).first():
            raise HTTPException(status_code=400, detail="Category name already exists")
        cat = Category(**payload.dict(), created_by=user_id)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        audit(db, user_id, "create", "products",
              f"Created category {cat.name} ({cat.prefix})",
              record_type="category", record_id=cat.id)
        return cat

    @staticmethod
    def update(db: Session, category_id: int, payload: CategoryUpdate, user_id: int) -> Category:
        cat = CategoryService.get_by_id(db, category_id)
        _fields = ("name", "prefix", "default_hsn", "default_gst_percent",
                   "description", "is_active")
        old = {f: getattr(cat, f, None) for f in _fields}
        for field, value in payload.dict(exclude_none=True).items():
            setattr(cat, field, value)
        cat.updated_by = user_id
        db.commit()
        db.refresh(cat)
        new = {f: getattr(cat, f, None) for f in _fields}
        changed, summary = diff(old, new, _fields)
        if changed:
            audit(db, user_id, "update", "products",
                  f"Updated category {cat.name}: {summary}",
                  record_type="category", record_id=cat.id,
                  old={k: v[0] for k, v in changed.items()},
                  new={k: v[1] for k, v in changed.items()})
        return cat

    @staticmethod
    def delete(db: Session, category_id: int, user_id: Optional[int] = None) -> dict:
        cat = CategoryService.get_by_id(db, category_id)
        if db.query(Product).filter(Product.category_id == category_id).first():
            raise HTTPException(status_code=400, detail="Cannot delete category with existing products. Deactivate instead.")
        name, prefix, cid = cat.name, cat.prefix, cat.id
        db.delete(cat)
        db.commit()
        audit(db, user_id, "delete", "products",
              f"Deleted category {name} ({prefix})",
              record_type="category", record_id=cid)
        return {"message": "Category deleted"}


# ─── Part Code Generation ────────────────────────────────────

def generate_part_code(db: Session, category_id: int) -> str:
    """Thread-safe part code generation using DB-level lock."""
    cat = db.query(Category).filter(Category.id == category_id).with_for_update().first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.sequence_counter += 1
    db.flush()
    return f"{cat.prefix}{cat.sequence_counter}"


# ─── Price-ordering guard ────────────────────────────────────

def price_order_error(floor, b2b, b2c, mrp, purchase_cost=None) -> Optional[str]:
    """Return an error message if the non-zero prices violate either:
      • floor >= purchase_cost  (floor must not be below cost)
      • floor <= b2b <= b2c <= mrp  (selling tiers must be ordered)
    Zero / None values are treated as "not set" and skipped.
    """
    def _d(v):
        if v is None:
            return Decimal("0")
        return v if isinstance(v, Decimal) else Decimal(str(v))

    # Rule 1: floor price must be >= purchase cost
    if purchase_cost is not None:
        cost = _d(purchase_cost)
        fp = _d(floor)
        if cost > 0 and fp > 0 and fp < cost:
            return f"Floor price (₹{fp}) cannot be below purchase cost (₹{cost})"

    # Rule 2: selling tiers must be ordered floor <= b2b <= b2c <= mrp
    cleaned = []
    for name, val in (("Floor", floor), ("B2B", b2b), ("B2C", b2c), ("MRP", mrp)):
        d = _d(val)
        if d > 0:
            cleaned.append((name, d))
    for (n1, v1), (n2, v2) in zip(cleaned, cleaned[1:]):
        if v1 > v2:
            return f"{n1} price (₹{v1}) cannot exceed {n2} price (₹{v2})"
    return None


# ─── Product Service ─────────────────────────────────────────

class ProductService:

    @staticmethod
    def _calc_profit(cost: Decimal, price: Decimal) -> tuple:
        # Markup on cost: (price - cost) / cost. Returned as "profit".
        if not cost or cost == 0:
            return Decimal("0"), Decimal("0")
        profit_val = price - cost
        profit_pct = (profit_val / cost * 100).quantize(Decimal("0.01"))
        return profit_pct, profit_val.quantize(Decimal("0.01"))

    @staticmethod
    def _calc_margin(cost: Decimal, price: Decimal) -> Decimal:
        # True margin on selling price: (price - cost) / price.
        if not price or price == 0:
            return Decimal("0")
        return ((price - cost) / price * 100).quantize(Decimal("0.01"))

    @staticmethod
    def _get_total_stock(db: Session, product_id: int) -> Decimal:
        # Only count stock in active warehouses — deactivated warehouses
        # shouldn't contribute to "available" totals.
        result = db.query(func.sum(WarehouseStock.quantity)).join(
            Warehouse, Warehouse.id == WarehouseStock.warehouse_id
        ).filter(
            WarehouseStock.product_id == product_id,
            Warehouse.is_active == True,
        ).scalar()
        return result or Decimal("0")

    @staticmethod
    def list_products(
        db: Session, page: int = 1, page_size: int = 20,
        category_id: Optional[int] = None, search: Optional[str] = None,
        is_active: Optional[bool] = True, low_stock_only: bool = False
    ) -> dict:
        q = db.query(Product)
        if is_active is not None:
            q = q.filter(Product.is_active == is_active)
        if category_id:
            q = q.filter(Product.category_id == category_id)
        if search:
            q = q.filter(
                (Product.part_name.ilike(f"%{search}%")) |
                (Product.part_code.ilike(f"%{search}%"))
            )
        if low_stock_only:
            # Only count stock in active warehouses for the low-stock comparison.
            q = q.outerjoin(
                    WarehouseStock,
                    (WarehouseStock.product_id == Product.id),
                )\
                 .outerjoin(
                    Warehouse,
                    (Warehouse.id == WarehouseStock.warehouse_id) & (Warehouse.is_active == True),
                )\
                 .group_by(Product.id)\
                 .having(
                    func.coalesce(
                        func.sum(case((Warehouse.is_active == True, WarehouseStock.quantity), else_=0)),
                        0
                    ) <= Product.low_stock_threshold
                 )

        result = paginate(q.order_by(Product.part_code), page, page_size)

        products = result["items"]
        product_ids = [p.id for p in products]

        # Batch total stock (active warehouses only) in one grouped query,
        # rather than calling _get_total_stock once per row (N+1).
        stock_map = {}
        if product_ids:
            for pid, qty in db.query(
                WarehouseStock.product_id, func.sum(WarehouseStock.quantity)
            ).join(
                Warehouse, Warehouse.id == WarehouseStock.warehouse_id
            ).filter(
                WarehouseStock.product_id.in_(product_ids),
                Warehouse.is_active == True,
            ).group_by(WarehouseStock.product_id).all():
                stock_map[pid] = qty or Decimal("0")

        # Batch category names in one query to avoid per-row lazy loads.
        cat_ids = {p.category_id for p in products if p.category_id}
        cat_map = {}
        if cat_ids:
            for cid, cname in db.query(Category.id, Category.name).filter(
                Category.id.in_(cat_ids)
            ).all():
                cat_map[cid] = cname

        result["items"] = [
            {
                "id": p.id, "part_code": p.part_code, "part_name": p.part_name,
                "hsn_code": p.hsn_code, "gst_percent": p.gst_percent,
                "b2b_price": p.b2b_price, "b2c_price": p.b2c_price, "mrp": p.mrp,
                "purchase_cost": p.purchase_cost,
                "unit_of_measure": p.unit_of_measure, "is_active": p.is_active,
                "category_name": cat_map.get(p.category_id),
                "total_stock": stock_map.get(p.id, Decimal("0")),
            }
            for p in products
        ]
        return result

    @staticmethod
    def get_by_id(db: Session, product_id: int) -> dict:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Product not found")
        profit_pct, profit_val = ProductService._calc_profit(p.purchase_cost, p.b2b_price or Decimal("0"))
        return {
            "id": p.id, "part_code": p.part_code, "part_name": p.part_name,
            "category_id": p.category_id,
            "category_name": p.category.name if p.category else None,
            "hsn_code": p.hsn_code, "gst_percent": p.gst_percent,
            "purchase_cost": p.purchase_cost, "b2b_price": p.b2b_price,
            "b2c_price": p.b2c_price, "mrp": p.mrp,
            "floor_price": p.floor_price, "profit_percent": profit_pct,
            "profit_value": profit_val, "unit_of_measure": p.unit_of_measure,
            "low_stock_threshold": p.low_stock_threshold,
            "description": p.description,
            "is_active": p.is_active, "cost_alert_threshold_pct": p.cost_alert_threshold_pct,
            "min_margin_pct": p.min_margin_pct, "created_at": p.created_at,
            "image_path": p.image_path,
            "total_stock": ProductService._get_total_stock(db, p.id),
        }

    @staticmethod
    def create(db: Session, payload: ProductCreate, user_id: int) -> dict:
        cat = db.query(Category).filter(Category.id == payload.category_id, Category.is_active == True).first()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found or inactive")

        err = price_order_error(payload.floor_price, payload.b2b_price, payload.b2c_price, payload.mrp, payload.purchase_cost)
        if err:
            raise HTTPException(status_code=400, detail=err)

        part_code = generate_part_code(db, payload.category_id)

        product = Product(
            part_code=part_code,
            part_name=payload.part_name,
            category_id=payload.category_id,
            hsn_code=payload.hsn_code,
            gst_percent=payload.gst_percent,
            purchase_cost=payload.purchase_cost,
            b2b_price=payload.b2b_price,
            b2c_price=payload.b2c_price,
            mrp=payload.mrp,
            floor_price=payload.floor_price,
            unit_of_measure=payload.unit_of_measure,
            low_stock_threshold=payload.low_stock_threshold,
            description=payload.description,
            cost_alert_threshold_pct=(
                payload.cost_alert_threshold_pct
                if payload.cost_alert_threshold_pct is not None
                else ConfigService.get_decimal(db, "business.cost_alert_pct", default=Decimal("5"))
            ),
            min_margin_pct=(
                payload.min_margin_pct
                if payload.min_margin_pct is not None
                else ConfigService.get_decimal(db, "business.min_margin_pct", default=Decimal("10"))
            ),
            created_by=user_id,
        )
        db.add(product)
        db.flush()

        # Record initial cost history
        CostTrackingService.record_cost(
            db, product.id, None, None,
            payload.purchase_cost, Decimal("0"), get_current_fy()
        )

        db.commit()
        db.refresh(product)
        audit(db, user_id, "create", "products",
              f"Created product {product.part_code} — {product.part_name}",
              record_type="product", record_id=product.id)
        return ProductService.get_by_id(db, product.id)

    @staticmethod
    def update(db: Session, product_id: int, payload: ProductUpdate, user_id: int) -> dict:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Product not found")

        if payload.category_id is not None and payload.category_id != p.category_id:
            raise HTTPException(status_code=400, detail="Category cannot be changed after creation")

        # Snapshot every price tier before the merge so we can record history
        # for whichever ones actually change. The edit screen is one of the
        # three cost-change entry points (with bulk-create and purchase invoice);
        # recording here keeps the Recent-Changes view complete.
        _price_fields = ("purchase_cost", "floor_price", "b2b_price", "b2c_price", "mrp")
        old_prices = {f: getattr(p, f) for f in _price_fields}
        old_cost = old_prices["purchase_cost"]
        old_b2b = old_prices["b2b_price"]

        # Snapshot for the audit trail (broader than just price tiers).
        _audit_fields = (
            "part_name", "hsn_code", "gst_percent", "purchase_cost", "floor_price",
            "b2b_price", "b2c_price", "mrp", "low_stock_threshold", "unit_of_measure",
            "description", "is_active", "min_margin_pct", "cost_alert_threshold_pct",
        )
        _audit_old = {f: getattr(p, f, None) for f in _audit_fields}

        for field, value in payload.dict(exclude_none=True).items():
            if field != "category_id":
                setattr(p, field, value)
        p.updated_by = user_id

        # HSN is mandatory — an edit can never leave a product without one,
        # including legacy rows that predate this rule.
        if not (p.hsn_code and str(p.hsn_code).strip()):
            raise HTTPException(status_code=400, detail="HSN code is required")

        # Validate the merged price tiers (skips any 0/unset value)
        err = price_order_error(p.floor_price, p.b2b_price, p.b2c_price, p.mrp, p.purchase_cost)
        if err:
            raise HTTPException(status_code=400, detail=err)

        # Check cost / margin alerts when either purchase_cost or b2b_price changes
        cost_changed = payload.purchase_cost is not None and payload.purchase_cost != old_cost
        b2b_changed = payload.b2b_price is not None and payload.b2b_price != old_b2b
        if cost_changed or b2b_changed:
            CostTrackingService.check_and_alert(db, p, old_cost, p.purchase_cost)

        # Record a price-history row for each tier the edit actually changed.
        from app.services.price_history_service import record_price_change
        reason = "Product edit"
        for f in _price_fields:
            new_val = getattr(p, f)
            if new_val is not None and new_val != old_prices[f]:
                record_price_change(db, product_id, f, new_val, date.today(), user_id, reason)

        db.commit()
        db.refresh(p)
        _audit_new = {f: getattr(p, f, None) for f in _audit_fields}
        changed, summary = diff(_audit_old, _audit_new, _audit_fields)
        if changed:
            audit(db, user_id, "update", "products",
                  f"Updated product {p.part_code}: {summary}",
                  record_type="product", record_id=p.id,
                  old={k: v[0] for k, v in changed.items()},
                  new={k: v[1] for k, v in changed.items()})
        return ProductService.get_by_id(db, product_id)

    @staticmethod
    def update_image(db: Session, product_id: int, image_path: Optional[str], user_id: int) -> dict:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Product not found")
        old_image = p.image_path
        p.image_path = image_path
        p.updated_by = user_id
        db.commit()
        audit(db, user_id, "update", "products",
              f"{'Updated' if image_path else 'Removed'} image for product {p.part_code}",
              record_type="product", record_id=p.id,
              old={"image_path": old_image}, new={"image_path": image_path})
        return ProductService.get_by_id(db, product_id)

    @staticmethod
    def bulk_price_update(db: Session, payload: BulkPriceUpdate, user_id: int) -> dict:
        """Apply one price type/value to many products via the price-history engine.

        Each product gets a versioned product_prices row (immediate or scheduled
        for a future effective_from). Selling tiers are validated against the
        product's other tiers (floor<=b2b<=b2c<=mrp); violators are skipped and
        reported rather than aborting the whole batch.
        """
        from app.services.price_history_service import (
            record_price_change, PRICE_TYPES, PRICE_LABELS, _today_ist,
        )

        if payload.price_type not in PRICE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid price_type. Must be one of {PRICE_TYPES}",
            )
        if payload.price is None or payload.price <= 0:
            raise HTTPException(status_code=400, detail="price must be greater than 0")
        if not payload.product_ids:
            raise HTTPException(status_code=400, detail="No products selected")

        new_price = payload.price if isinstance(payload.price, Decimal) else Decimal(str(payload.price))
        today = _today_ist()
        eff_date = payload.effective_from or today
        is_scheduled = eff_date > today

        tier_key = {"floor_price": "floor", "b2b_price": "b2b", "b2c_price": "b2c", "mrp": "mrp"}
        updated, scheduled, errors = 0, 0, []

        for raw_id in payload.product_ids:
            try:
                pid = int(raw_id)
            except (TypeError, ValueError):
                errors.append({"product_id": raw_id, "error": "Invalid product id"})
                continue

            p = db.query(Product).filter(Product.id == pid).first()
            if not p:
                errors.append({"product_id": pid, "error": "Product not found"})
                continue

            # Enforce price ordering.
            if payload.price_type in tier_key:
                # Selling tier change — substitute new value and validate full set.
                tiers = {"floor": p.floor_price, "b2b": p.b2b_price, "b2c": p.b2c_price, "mrp": p.mrp}
                tiers[tier_key[payload.price_type]] = new_price
                order_err = price_order_error(tiers["floor"], tiers["b2b"], tiers["b2c"], tiers["mrp"], p.purchase_cost)
                if order_err:
                    errors.append({"product_id": pid, "part_code": p.part_code, "error": order_err})
                    continue
            elif payload.price_type == "purchase_cost":
                # Cost change — ensure new cost doesn't exceed existing floor (if set).
                cost_err = price_order_error(p.floor_price, p.b2b_price, p.b2c_price, p.mrp, new_price)
                if cost_err:
                    errors.append({"product_id": pid, "part_code": p.part_code, "error": cost_err})
                    continue

            record_price_change(
                db, pid, payload.price_type, new_price, eff_date,
                user_id, payload.change_reason, is_scheduled=is_scheduled,
            )
            if is_scheduled:
                scheduled += 1
            else:
                updated += 1

        db.commit()
        _label = PRICE_LABELS.get(payload.price_type, payload.price_type)
        _verb = "scheduled" if is_scheduled else "updated"
        audit(db, user_id, "update", "products",
              f"Bulk {_label} {_verb} to ₹{new_price} (effective {eff_date.isoformat()}) "
              f"for {updated + scheduled} product(s); {len(errors)} skipped",
              record_type="product_bulk_price", record_id=None)
        return {
            "price_type": payload.price_type,
            "price_type_label": PRICE_LABELS.get(payload.price_type, payload.price_type),
            "price": float(new_price),
            "effective_from": eff_date.isoformat(),
            "is_scheduled": is_scheduled,
            "total": len(payload.product_ids),
            "updated": updated,
            "scheduled": scheduled,
            "skipped": len(errors),
            "errors": errors,
        }

    @staticmethod
    def search_for_billing(db: Session, search: str, warehouse_id: Optional[int] = None) -> List[dict]:
        """Fast product search for billing screen."""
        products = db.query(Product).filter(
            Product.is_active == True,
            (Product.part_name.ilike(f"%{search}%")) | (Product.part_code.ilike(f"%{search}%"))
        ).limit(20).all()

        results = []
        for p in products:
            stock = Decimal("0")
            if warehouse_id:
                ws = db.query(WarehouseStock).filter(
                    WarehouseStock.product_id == p.id,
                    WarehouseStock.warehouse_id == warehouse_id
                ).first()
                stock = ws.quantity if ws else Decimal("0")
            else:
                stock = ProductService._get_total_stock(db, p.id)

            results.append({
                "id": p.id, "part_code": p.part_code, "part_name": p.part_name,
                "b2b_price": p.b2b_price, "b2c_price": p.b2c_price, "mrp": p.mrp, "floor_price": p.floor_price,
                "gst_percent": p.gst_percent, "hsn_code": p.hsn_code,
                "unit_of_measure": p.unit_of_measure, "stock": stock,
            })
        return results

    @staticmethod
    def bulk_upload(db: Session, file_content: str, user_id: int) -> dict:
        reader = csv.DictReader(io.StringIO(file_content))
        required_cols = {"part_name", "category_prefix", "gst_percent",
                         "purchase_cost", "b2b_price", "floor_price"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            raise HTTPException(status_code=400, detail=f"Missing columns. Required: {required_cols}")

        errors = []
        created = []
        skipped = []
        rows = list(reader)

        for idx, row in enumerate(rows, start=2):
            row_errors = []

            # Validate numerics
            for field in ["gst_percent", "purchase_cost", "b2b_price", "floor_price"]:
                try:
                    Decimal(row.get(field, "").strip())
                except Exception:
                    row_errors.append(f"Invalid {field}: '{row.get(field)}'")

            part_name = row.get("part_name", "").strip()
            if not part_name:
                row_errors.append("part_name is required")

            prefix = row.get("category_prefix", "").upper().strip()
            if not prefix:
                row_errors.append("category_prefix is required")

            # HSN is mandatory (matches single-product create)
            hsn = row.get("hsn_code", "").strip()
            if not hsn:
                row_errors.append("hsn_code is required")
            elif not hsn.isdigit() or len(hsn) not in (4, 6, 8):
                row_errors.append("hsn_code must be 4, 6, or 8 digits, numeric only")

            # Enforce price ordering once the numerics above are known-good
            if not row_errors:
                def _dec(v):
                    try:
                        return Decimal((v or "0").strip() or "0")
                    except Exception:
                        return Decimal("0")
                order_err = price_order_error(
                    _dec(row.get("floor_price")), _dec(row.get("b2b_price")),
                    _dec(row.get("b2c_price")), _dec(row.get("mrp")),
                    _dec(row.get("purchase_cost")),
                )
                if order_err:
                    row_errors.append(order_err)

            if row_errors:
                errors.append({"row": idx, "data": row.get("part_name", ""), "errors": row_errors})
                continue

            # Resolve category by prefix; auto-create a new one when missing so a
            # fresh deployment can load products (and their categories) in one file.
            cat = db.query(Category).filter(
                Category.prefix == prefix, Category.is_active == True
            ).first()
            if not cat:
                try:
                    cat = ProductService._autocreate_category(
                        db, prefix, row.get("category_name", "").strip(),
                        Decimal(row["gst_percent"].strip()), hsn or None, user_id,
                    )
                except Exception as e:
                    errors.append({"row": idx, "data": part_name,
                                   "errors": [f"Could not auto-create category '{prefix}': {e}"]})
                    continue

            # Skip & report duplicates (same part_name within the same category).
            dup = db.query(Product).filter(
                func.lower(Product.part_name) == part_name.lower(),
                Product.category_id == cat.id,
            ).first()
            if dup:
                skipped.append({"row": idx, "data": part_name,
                                "reason": f"Already exists in '{cat.name}' as {dup.part_code}"})
                continue

            # Per-row SAVEPOINT — a bad row rolls back its own writes (including
            # the category sequence_counter increment) without poisoning the
            # outer transaction, so valid rows still commit.
            try:
                with db.begin_nested():
                    part_code = generate_part_code(db, cat.id)
                    product = Product(
                        part_code=part_code, part_name=row["part_name"].strip(),
                        category_id=cat.id, hsn_code=hsn or None,
                        gst_percent=Decimal(row["gst_percent"].strip()),
                        purchase_cost=Decimal(row["purchase_cost"].strip()),
                        b2b_price=Decimal(row.get("b2b_price","0").strip() or "0"),
                        b2c_price=Decimal(row.get("b2c_price","0").strip() or "0"),
                        mrp=Decimal(row.get("mrp","0").strip() or "0"),
                        floor_price=Decimal(row["floor_price"].strip()),
                        unit_of_measure=row.get("unit_of_measure", "Nos").strip() or "Nos",
                        low_stock_threshold=Decimal(row.get("low_stock_threshold", "0").strip() or "0"),
                        description=row.get("description", "").strip() or None,
                        created_by=user_id,
                    )
                    db.add(product)
                    db.flush()
                    CostTrackingService.record_cost(
                        db, product.id, None, None,
                        Decimal(row["purchase_cost"].strip()), Decimal("0"), get_current_fy()
                    )
                created.append(part_code)
            except Exception as e:
                errors.append({"row": idx, "data": row.get("part_name", ""), "errors": [str(e)]})

        db.commit()
        return {"total_rows": len(rows), "success_count": len(created),
                "skipped_count": len(skipped), "error_count": len(errors),
                "errors": errors, "skipped": skipped, "created_products": created}

    @staticmethod
    def _autocreate_category(db: Session, prefix: str, name: str,
                             gst_percent: Decimal, hsn: Optional[str],
                             user_id: int) -> Category:
        """Create a category on the fly during bulk import.

        Reuses an inactive category with the same prefix if one exists (the
        unique prefix would otherwise clash), reactivating it. Otherwise creates
        a new one named after `category_name` (falling back to the prefix).
        """
        existing = db.query(Category).filter(Category.prefix == prefix).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                db.flush()
            return existing
        cat = Category(
            name=(name or prefix),
            prefix=prefix,
            default_hsn=hsn,
            default_gst_percent=gst_percent,
            description="Auto-created during bulk import",
            created_by=user_id,
        )
        db.add(cat)
        db.flush()
        return cat

    @staticmethod
    def get_csv_template() -> str:
        headers = [
            "part_name", "category_prefix", "category_name", "hsn_code", "gst_percent",
            "purchase_cost", "b2b_price", "b2c_price", "mrp", "floor_price",
            "unit_of_measure", "low_stock_threshold", "description"
        ]
        sample = [
            "Sample Product 1", "GTY", "General Toys", "85162000", "18",
            "1000.00", "1500.00", "1650.00", "1800.00", "1200.00",
            "Nos", "5", "Sample description"
        ]
        return "\n".join([",".join(headers), ",".join(sample)])

    @staticmethod
    def export_csv(
        db: Session,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> str:
        import csv, io as _io
        q = db.query(Product)
        if is_active is not None:
            q = q.filter(Product.is_active == is_active)
        if category_id:
            q = q.filter(Product.category_id == category_id)
        if search:
            q = q.filter(
                (Product.part_name.ilike(f"%{search}%")) |
                (Product.part_code.ilike(f"%{search}%"))
            )
        products = q.order_by(Product.part_code).all()

        cat_ids = {p.category_id for p in products if p.category_id}
        cat_map = {}
        if cat_ids:
            for cid, cname in db.query(Category.id, Category.name).filter(Category.id.in_(cat_ids)).all():
                cat_map[cid] = cname

        buf = _io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "part_code", "part_name", "category", "hsn_code", "gst_percent",
            "purchase_cost", "b2b_price", "b2c_price", "mrp", "floor_price",
            "unit_of_measure", "low_stock_threshold", "is_active", "description",
        ])
        for p in products:
            w.writerow([
                p.part_code, p.part_name, cat_map.get(p.category_id, ""),
                p.hsn_code or "", p.gst_percent,
                p.purchase_cost, p.b2b_price or "", p.b2c_price or "", p.mrp or "", p.floor_price,
                p.unit_of_measure, p.low_stock_threshold,
                "Yes" if p.is_active else "No",
                p.description or "",
            ])
        return buf.getvalue()


# ─── Cost Tracking Service ────────────────────────────────────

class CostTrackingService:

    @staticmethod
    def record_cost(db: Session, product_id: int, vendor_id: Optional[int],
                    purchase_id: Optional[int], unit_cost: Decimal,
                    quantity: Decimal, financial_year: str):
        entry = ProductCostHistory(
            product_id=product_id, vendor_id=vendor_id,
            purchase_id=purchase_id, unit_cost=unit_cost,
            quantity=quantity, financial_year=financial_year,
        )
        db.add(entry)

    @staticmethod
    def check_and_alert(db: Session, product: Product, old_cost: Decimal, new_cost: Decimal):
        if old_cost and old_cost > 0:
            change_pct = ((new_cost - old_cost) / old_cost * 100)
            if change_pct > product.cost_alert_threshold_pct:
                # Cost rise alert
                alert = CostAlert(
                    product_id=product.id,
                    alert_type=AlertType.cost_rise,
                    message=f"Cost rose by {change_pct:.1f}% (₹{old_cost} → ₹{new_cost})",
                    old_value=old_cost, new_value=new_cost,
                )
                db.add(alert)

        # Margin alert — true margin on selling price: (price - cost) / price
        b2b = product.b2b_price or Decimal("0")
        if b2b and new_cost > 0:
            margin = (b2b - new_cost) / b2b * 100
            if margin < product.min_margin_pct:
                # Price that yields the target margin m: cost / (1 - m/100)
                m = product.min_margin_pct
                suggested = (new_cost / (1 - m / 100)) if m < 100 else b2b
                alert = CostAlert(
                    product_id=product.id,
                    alert_type=AlertType.low_margin,
                    message=f"Margin dropped to {margin:.1f}% (below {product.min_margin_pct}% threshold)",
                    old_value=b2b, new_value=margin,
                    suggested_price=suggested.quantize(Decimal("0.01")),
                )
                db.add(alert)

    @staticmethod
    def get_trend(db: Session, product_id: int,
                  vendor_id: Optional[int] = None,
                  date_from: Optional[date] = None,
                  date_to: Optional[date] = None) -> dict:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Product not found")

        q = db.query(ProductCostHistory).filter(
            ProductCostHistory.product_id == product_id
        )
        if vendor_id:
            q = q.filter(ProductCostHistory.vendor_id == vendor_id)
        if date_from:
            q = q.filter(ProductCostHistory.recorded_at >= date_from)
        if date_to:
            q = q.filter(ProductCostHistory.recorded_at <= date_to)

        history = q.order_by(ProductCostHistory.recorded_at).all()
        # Defend against legacy rows where _auto_migrate added recorded_at/unit_cost
        # as nullable: drop entries that can't be rendered safely.
        history = [h for h in history if h.recorded_at is not None and h.unit_cost is not None]

        # Vendor summary
        vendor_summary_raw = db.query(
            ProductCostHistory.vendor_id,
            func.min(ProductCostHistory.unit_cost).label("min_cost"),
            func.max(ProductCostHistory.unit_cost).label("max_cost"),
            func.avg(ProductCostHistory.unit_cost).label("avg_cost"),
            func.max(ProductCostHistory.recorded_at).label("last_date"),
            func.sum(ProductCostHistory.quantity).label("total_qty"),
        ).filter(
            ProductCostHistory.product_id == product_id,
            ProductCostHistory.vendor_id != None
        ).group_by(ProductCostHistory.vendor_id).all()

        from app.models.models import Vendor
        vendor_ids = [row.vendor_id for row in vendor_summary_raw]

        # Batch vendor names, 3-month averages, and last prices — one query each
        # rather than three per vendor (N+1).
        vendor_names, avg3m_map, last_price_map = {}, {}, {}
        if vendor_ids:
            for vid, tname in db.query(Vendor.id, Vendor.trade_name).filter(
                Vendor.id.in_(vendor_ids)
            ).all():
                vendor_names[vid] = tname

            cost_avg_days = ConfigService.get_int(db, "business.cost_avg_window_days", default=90)
            cutoff = datetime.utcnow() - timedelta(days=cost_avg_days)
            for vid, avg in db.query(
                ProductCostHistory.vendor_id, func.avg(ProductCostHistory.unit_cost)
            ).filter(
                ProductCostHistory.product_id == product_id,
                ProductCostHistory.vendor_id.in_(vendor_ids),
                ProductCostHistory.recorded_at >= cutoff,
            ).group_by(ProductCostHistory.vendor_id).all():
                avg3m_map[vid] = avg or Decimal("0")

            # Ascending by recorded_at so the last row written per vendor wins.
            for vid, uc in db.query(
                ProductCostHistory.vendor_id, ProductCostHistory.unit_cost
            ).filter(
                ProductCostHistory.product_id == product_id,
                ProductCostHistory.vendor_id.in_(vendor_ids),
            ).order_by(ProductCostHistory.recorded_at).all():
                last_price_map[vid] = uc

        vendor_summary = []
        for row in vendor_summary_raw:
            avg_3m = avg3m_map.get(row.vendor_id, Decimal("0"))
            last_price = last_price_map.get(row.vendor_id) or Decimal("0")
            is_above_avg = last_price > avg_3m * Decimal("1.05") if avg_3m else False

            vendor_summary.append({
                "vendor_id": row.vendor_id,
                "vendor_name": vendor_names.get(row.vendor_id, "Unknown"),
                "min_cost": float(row.min_cost or 0),
                "max_cost": float(row.max_cost or 0),
                "avg_cost": float(row.avg_cost or 0),
                "last_price": float(last_price),
                "last_date": row.last_date,
                "total_qty": float(row.total_qty or 0),
                "is_above_avg": is_above_avg,
            })

        # Price-volume data
        price_volume = []
        from collections import defaultdict
        pv_map = defaultdict(lambda: {"quantity": Decimal("0"), "count": 0})
        for h in history:
            key = str(h.unit_cost)
            pv_map[key]["quantity"] += h.quantity
            pv_map[key]["count"] += 1
        for price_str, data in sorted(pv_map.items(), key=lambda x: Decimal(x[0])):
            price_volume.append({
                "unit_cost": float(price_str),
                "total_quantity": float(data["quantity"]),
                "purchase_count": data["count"],
            })

        margin_pct = ProductService._calc_margin(p.purchase_cost, p.b2b_price or Decimal("0"))

        return {
            "product_id": p.id,
            "part_code": p.part_code,
            "part_name": p.part_name,
            "current_cost": float(p.purchase_cost),
            "current_b2b_price": float(p.b2b_price or 0),
            "current_b2c_price": float(p.b2c_price or 0),
            "current_margin_pct": float(margin_pct),
            "cost_history": [
                {
                    "id": h.id, "unit_cost": float(h.unit_cost or 0),
                    "quantity": float(h.quantity or 0),
                    "recorded_at": h.recorded_at.isoformat(),
                    "financial_year": h.financial_year,
                    "vendor_id": h.vendor_id,
                    "vendor_name": next(
                        (v["vendor_name"] for v in vendor_summary if v["vendor_id"] == h.vendor_id), None
                    ),
                } for h in history
            ],
            "vendor_summary": vendor_summary,
            "price_volume_data": price_volume,
        }

    @staticmethod
    def approve_price_suggestion(db: Session, alert_id: int, approve: bool, user: User) -> dict:
        alert = db.query(CostAlert).filter(CostAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        if alert.is_resolved:
            raise HTTPException(status_code=400, detail="Alert already resolved")

        if approve and alert.suggested_price:
            product = db.query(Product).filter(Product.id == alert.product_id).first()
            if product:
                from app.services.price_history_service import record_price_change
                old_b2b = product.b2b_price or Decimal("0")
                old_b2c = product.b2c_price or Decimal("0")
                reason = f"Cost-alert approval (alert #{alert.id})"
                today = date.today()
                # Route through record_price_change — updates products column AND writes audit row
                record_price_change(db, product.id, "b2b_price", alert.suggested_price, today, user.id, reason)
                # Scale B2C by the product's existing B2C/B2B ratio so its margin is preserved
                if old_b2b > 0 and old_b2c > 0:
                    ratio = old_b2c / old_b2b
                    new_b2c = (alert.suggested_price * ratio).quantize(Decimal("0.01"))
                    record_price_change(db, product.id, "b2c_price", new_b2c, today, user.id, reason)
                product.updated_by = user.id

        alert.is_resolved = True
        alert.resolved_by = user.id
        alert.resolved_at = datetime.utcnow()
        db.commit()
        return {"message": "Price updated successfully" if approve else "Suggestion dismissed"}


# ─── Stock Service ────────────────────────────────────────────

class StockService:

    @staticmethod
    def get_warehouse_stock(db: Session, product_id: int) -> List[dict]:
        from app.models.models import Warehouse
        stocks = db.query(WarehouseStock, Warehouse).join(
            Warehouse, WarehouseStock.warehouse_id == Warehouse.id
        ).filter(
            WarehouseStock.product_id == product_id,
            Warehouse.is_active == True,
        ).all()
        return [
            {
                "warehouse_id": ws.warehouse_id,
                "warehouse_name": wh.name,
                "warehouse_code": wh.code,
                "quantity": float(ws.quantity),
            }
            for ws, wh in stocks
        ]

    @staticmethod
    def adjust_stock(db: Session, payload: StockAdjustmentCreate, user_id: int) -> dict:
        product = db.query(Product).filter(Product.id == payload.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        adj_date = payload.adjustment_date or date.today()

        # Atomic, FY-scoped number. Shares the "stock_adjustment" counter with
        # the canonical warehouse path so the two never collide.
        fy = get_financial_year(adj_date)
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
            unit_cost=payload.unit_cost,
            reason=payload.reason,
            adjustment_date=adj_date,
            notes=payload.notes,
            created_by=user_id,
        )
        db.add(adj)
        db.flush()

        # Route through proper FIFO helpers so stock_entries.remaining_qty stays
        # consistent with warehouse_stocks.quantity. Previously this path wrote
        # a StockEntry without remaining_qty / unit_cost, leaving the FIFO ledger
        # invisible to consume_fifo and causing false "insufficient stock" errors
        # in downstream flows (write-offs, invoices).
        if payload.adjustment_type == "in":
            unit_cost = payload.unit_cost if payload.unit_cost is not None else (product.purchase_cost or Decimal("0"))
            StockService.add_stock(
                db, payload.product_id, payload.warehouse_id,
                payload.quantity, unit_cost,
                StockTransactionType.adjustment_in,
                "adjustment", adj.id, adj_date, user_id,
            )
        else:
            # consume_fifo raises 400 with clear message if aggregate stock is short
            StockService.consume_fifo(
                db, payload.product_id, payload.warehouse_id, payload.quantity
            )
            # Audit row so adjustment_out shows in stock_entries history
            db.add(StockEntry(
                product_id=payload.product_id,
                warehouse_id=payload.warehouse_id,
                transaction_type=StockTransactionType.adjustment_out,
                quantity=payload.quantity,
                unit_cost=payload.unit_cost,
                remaining_qty=Decimal("0"),
                reference_type="adjustment",
                reference_id=adj.id,
                batch_date=adj_date,
                created_by=user_id,
            ))

        db.commit()
        audit(db, user_id, "adjustment", "warehouse",
              f"Stock adjustment {adj_number}: {payload.adjustment_type} "
              f"{payload.quantity} of {product.part_code}"
              + (f" — {payload.reason}" if payload.reason else ""),
              record_type="stock_adjustment", record_id=adj.id)
        return {"message": "Stock adjusted successfully", "adjustment_number": adj_number}

    @staticmethod
    def get_fifo_layers(db: Session, product_id: int, warehouse_id: int) -> List[dict]:
        """Get remaining FIFO layers for a product in a warehouse."""
        from datetime import date as dt
        entries = db.query(StockEntry).filter(
            StockEntry.product_id == product_id,
            StockEntry.warehouse_id == warehouse_id,
            StockEntry.transaction_type.in_([
                StockTransactionType.purchase, StockTransactionType.return_in,
                StockTransactionType.transfer_in, StockTransactionType.adjustment_in
            ]),
            StockEntry.remaining_qty > 0,
        ).order_by(StockEntry.batch_date, StockEntry.id).all()

        today = dt.today()
        return [
            {
                "entry_id": e.id,
                "batch_date": e.batch_date,
                "unit_cost": float(e.unit_cost or 0),
                "remaining_qty": float(e.remaining_qty or 0),
                "age_days": (today - e.batch_date).days if e.batch_date else 0,
            }
            for e in entries
        ]

    @staticmethod
    def consume_fifo(db: Session, product_id: int, warehouse_id: int, quantity: Decimal) -> Decimal:
        """Consume stock using FIFO. Returns weighted average cost consumed."""
        entries = db.query(StockEntry).filter(
            StockEntry.product_id == product_id,
            StockEntry.warehouse_id == warehouse_id,
            StockEntry.transaction_type.in_([
                StockTransactionType.purchase, StockTransactionType.return_in,
                StockTransactionType.transfer_in, StockTransactionType.adjustment_in
            ]),
            StockEntry.remaining_qty > 0,
        ).order_by(StockEntry.batch_date, StockEntry.id).with_for_update().all()

        remaining = quantity
        total_cost = Decimal("0")

        for entry in entries:
            if remaining <= 0:
                break
            consume = min(entry.remaining_qty, remaining)
            total_cost += consume * (entry.unit_cost or Decimal("0"))
            entry.remaining_qty -= consume
            remaining -= consume

        ws = db.query(WarehouseStock).filter(
            WarehouseStock.product_id == product_id,
            WarehouseStock.warehouse_id == warehouse_id
        ).with_for_update().first()

        if remaining > 0:
            # FIFO layers exhausted. WarehouseStock is the source of truth
            # (some flows — opening balances, DC confirm, adjust_stock — bump
            # ws.quantity without writing a usable FIFO layer). If aggregate
            # stock still covers the request, backfill a synthetic layer using
            # the product's purchase_cost so consumption can complete.
            aggregate = ws.quantity if ws else Decimal("0")
            if aggregate >= quantity:
                product = db.query(Product).filter(Product.id == product_id).first()
                fallback_cost = (product.purchase_cost if product and product.purchase_cost else Decimal("0"))
                synthetic = StockEntry(
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    transaction_type=StockTransactionType.adjustment_in,
                    quantity=remaining,
                    unit_cost=fallback_cost,
                    remaining_qty=Decimal("0"),
                    reference_type="fifo_backfill",
                    reference_id=None,
                    batch_date=date.today(),
                )
                db.add(synthetic)
                db.flush()
                total_cost += remaining * fallback_cost
                remaining = Decimal("0")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock. Available: {aggregate}, Requested: {quantity}"
                )

        if ws:
            ws.quantity -= quantity

        avg_cost = total_cost / quantity if quantity > 0 else Decimal("0")
        return avg_cost.quantize(Decimal("0.01"))

    @staticmethod
    def add_stock(db: Session, product_id: int, warehouse_id: int,
                  quantity: Decimal, unit_cost: Decimal,
                  txn_type: StockTransactionType, reference_type: str,
                  reference_id: int, batch_date: date, user_id: int):
        """Add stock and create FIFO layer."""
        ws = db.query(WarehouseStock).filter(
            WarehouseStock.product_id == product_id,
            WarehouseStock.warehouse_id == warehouse_id
        ).with_for_update().first()

        if not ws:
            ws = WarehouseStock(warehouse_id=warehouse_id, product_id=product_id, quantity=Decimal("0"))
            db.add(ws)
            db.flush()

        ws.quantity += quantity

        entry = StockEntry(
            product_id=product_id, warehouse_id=warehouse_id,
            transaction_type=txn_type, quantity=quantity,
            unit_cost=unit_cost, remaining_qty=quantity,
            reference_type=reference_type, reference_id=reference_id,
            batch_date=batch_date, created_by=user_id,
        )
        db.add(entry)
        return entry

    @staticmethod
    def get_ageing_report(db: Session, warehouse_id: Optional[int] = None) -> List[dict]:
        from datetime import date as dt
        today = dt.today()

        q = db.query(StockEntry).filter(
            StockEntry.transaction_type.in_([
                StockTransactionType.purchase, StockTransactionType.return_in,
                StockTransactionType.transfer_in, StockTransactionType.adjustment_in
            ]),
            StockEntry.remaining_qty > 0,
        )
        if warehouse_id:
            q = q.filter(StockEntry.warehouse_id == warehouse_id)

        entries = q.order_by(StockEntry.batch_date).all()

        report = []
        for e in entries:
            age = (today - e.batch_date).days if e.batch_date else 0
            bucket = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
            report.append({
                "product_id": e.product_id,
                "part_code": e.product.part_code if e.product else "",
                "part_name": e.product.part_name if e.product else "",
                "warehouse_id": e.warehouse_id,
                "batch_date": e.batch_date,
                "remaining_qty": float(e.remaining_qty),
                "unit_cost": float(e.unit_cost or 0),
                "stock_value": float((e.remaining_qty or 0) * (e.unit_cost or 0)),
                "age_days": age,
                "age_bucket": bucket,
            })
        return report
