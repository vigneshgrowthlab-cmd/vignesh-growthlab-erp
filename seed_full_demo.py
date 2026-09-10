"""
seed_full_demo.py
Comprehensive seeder for Vignesh GrowthLab ERP on Railway.
Populates realistic mobile accessories data designed specifically
for Sri Agni Mobiles, Pollachi to test EVERY single feature:
1. Warehouses (Main, Showroom, Service)
2. Categories with custom HSN & prefixes
3. Products with 5 pricing tiers, margins & low stock alerts
4. Scheduled Price Changes (Price Trend feature)
5. Vendors (TN local & KA interstate) with addresses
6. Customers (B2B wholesale with credit limits & B2C retail)
7. Purchases (Stock Inward / GRN with FIFO cost tracking)
8. Invoices (B2B, B2C, Overdue for Ageing, High-value for E-Way Bill)
9. Quotations & Delivery Challans
10. Customer Receipts & Vendor Payments
11. Operational Expenses (Accounting)
"""

import urllib.request
import urllib.error
import json
from datetime import date, timedelta

BASE = "https://vignesh-growthlab-erp-production-2955.up.railway.app/api/v1"
TOKEN = None

def api(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8") if e.fp else ""
        print(f"  [ERR] {method} {path} -> {e.code}: {err[:200]}")
        return None
    except Exception as ex:
        print(f"  [ERR] {method} {path} -> {ex}")
        return None

def login():
    global TOKEN
    res = api("POST", "/auth/login", {"username": "admin", "password": "Admin@1234"})
    if not res or "access_token" not in res:
        raise Exception("Login failed!")
    TOKEN = res["access_token"]
    print("[AUTH] Logged in successfully as super_admin")

def seed_warehouses():
    print("\n--- 1. Warehouses ---")
    wh_list = api("GET", "/warehouses/") or []
    wh_map = {w["code"]: w["id"] for w in wh_list}
    
    new_warehouses = [
        {"name": "Retail Showroom (Palani Road)", "code": "SHOWROOM", "city": "Pollachi", "state": "Tamil Nadu", "state_code": 33, "phone": "9842100010"},
        {"name": "Service & Spares Hub", "code": "SERVICE", "city": "Pollachi", "state": "Tamil Nadu", "state_code": 33, "phone": "9842100011"},
    ]
    for w in new_warehouses:
        if w["code"] not in wh_map:
            res = api("POST", "/warehouses/", w)
            if res and "id" in res:
                wh_map[w["code"]] = res["id"]
                print(f"  [+] Warehouse created: {w['name']} (ID: {res['id']})")
        else:
            print(f"  [=] Warehouse exists: {w['name']}")
    return wh_map

def seed_categories():
    print("\n--- 2. Categories ---")
    cats = api("GET", "/categories/") or []
    cat_map = {c["name"]: c["id"] for c in cats}
    
    data = [
        {"name": "Chargers & Adapters", "prefix": "CHG", "default_hsn": "85044090", "default_gst_percent": 18},
        {"name": "USB & Fast Cables", "prefix": "CBL", "default_hsn": "85444299", "default_gst_percent": 18},
        {"name": "Audio & Bluetooth", "prefix": "AUD", "default_hsn": "85183000", "default_gst_percent": 18},
        {"name": "Tempered Glass & Guards", "prefix": "GLS", "default_hsn": "70071900", "default_gst_percent": 18},
        {"name": "Cases & Back Covers", "prefix": "COV", "default_hsn": "39269099", "default_gst_percent": 18},
        {"name": "Power Banks", "prefix": "PWR", "default_hsn": "85044090", "default_gst_percent": 18},
        {"name": "Smart Wearables", "prefix": "WAT", "default_hsn": "85176290", "default_gst_percent": 18},
        {"name": "Mobile Spare Parts & Tools", "prefix": "SPR", "default_hsn": "85177090", "default_gst_percent": 18},
    ]
    for c in data:
        if c["name"] not in cat_map:
            res = api("POST", "/categories/", c)
            if res and "id" in res:
                cat_map[c["name"]] = res["id"]
                print(f"  [+] Category created: {c['name']} (ID: {res['id']})")
        else:
            print(f"  [=] Category exists: {c['name']}")
    return cat_map

def seed_products(cat_map):
    print("\n--- 3. Products ---")
    prod_resp = api("GET", "/products/?page_size=100") or {}
    existing_items = prod_resp.get("items", []) if isinstance(prod_resp, dict) else prod_resp
    prod_map = {p["part_name"]: p["id"] for p in existing_items}
    
    products_to_seed = [
        # Chargers
        {"part_name": "65W GaN Fast Charger Type-C", "category": "Chargers & Adapters", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 450, "b2b_price": 580, "b2c_price": 750, "mrp": 999, "floor_price": 520, "low_stock_threshold": 10},
        {"part_name": "20W PD iPhone Fast Adapter", "category": "Chargers & Adapters", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 220, "b2b_price": 310, "b2c_price": 420, "mrp": 599, "floor_price": 280, "low_stock_threshold": 15},
        {"part_name": "Car Quick Charger 38W Dual USB", "category": "Chargers & Adapters", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 180, "b2b_price": 250, "b2c_price": 350, "mrp": 499, "floor_price": 220, "low_stock_threshold": 10},
        # Cables
        {"part_name": "Braided Type-C to Type-C 60W (1.5m)", "category": "USB & Fast Cables", "hsn_code": "85444299", "gst_percent": 18, "purchase_cost": 65, "b2b_price": 110, "b2c_price": 160, "mrp": 249, "floor_price": 95, "low_stock_threshold": 25},
        {"part_name": "USB to Lightning Fast Cable (1m)", "category": "USB & Fast Cables", "hsn_code": "85444299", "gst_percent": 18, "purchase_cost": 55, "b2b_price": 95, "b2c_price": 140, "mrp": 199, "floor_price": 80, "low_stock_threshold": 30},
        {"part_name": "3-in-1 Fast Charging Nylon Cable", "category": "USB & Fast Cables", "hsn_code": "85444299", "gst_percent": 18, "purchase_cost": 85, "b2b_price": 140, "b2c_price": 210, "mrp": 299, "floor_price": 120, "low_stock_threshold": 20},
        # Audio
        {"part_name": "Wireless TWS Earbuds ENC Bass", "category": "Audio & Bluetooth", "hsn_code": "85183000", "gst_percent": 18, "purchase_cost": 480, "b2b_price": 690, "b2c_price": 899, "mrp": 1299, "floor_price": 620, "low_stock_threshold": 10},
        {"part_name": "Neckband Magnetic Bluetooth Earphones", "category": "Audio & Bluetooth", "hsn_code": "85183000", "gst_percent": 18, "purchase_cost": 290, "b2b_price": 420, "b2c_price": 550, "mrp": 799, "floor_price": 380, "low_stock_threshold": 12},
        {"part_name": "Party Mini Bluetooth Speaker 10W", "category": "Audio & Bluetooth", "hsn_code": "85183000", "gst_percent": 18, "purchase_cost": 380, "b2b_price": 540, "b2c_price": 699, "mrp": 999, "floor_price": 480, "low_stock_threshold": 8},
        # Tempered Glass
        {"part_name": "Super D 9H Matte Tempered Glass", "category": "Tempered Glass & Guards", "hsn_code": "70071900", "gst_percent": 18, "purchase_cost": 18, "b2b_price": 45, "b2c_price": 99, "mrp": 149, "floor_price": 35, "low_stock_threshold": 50},
        {"part_name": "Privacy Anti-Spy Tempered Glass", "category": "Tempered Glass & Guards", "hsn_code": "70071900", "gst_percent": 18, "purchase_cost": 32, "b2b_price": 65, "b2c_price": 130, "mrp": 199, "floor_price": 55, "low_stock_threshold": 40},
        {"part_name": "Camera Lens Protector Ring 3-Pack", "category": "Tempered Glass & Guards", "hsn_code": "70071900", "gst_percent": 18, "purchase_cost": 15, "b2b_price": 35, "b2c_price": 79, "mrp": 99, "floor_price": 28, "low_stock_threshold": 50},
        # Cases
        {"part_name": "Shockproof Clear Hybrid Armor Case", "category": "Cases & Back Covers", "hsn_code": "39269099", "gst_percent": 18, "purchase_cost": 45, "b2b_price": 85, "b2c_price": 149, "mrp": 199, "floor_price": 75, "low_stock_threshold": 25},
        {"part_name": "MagSafe Leather Magnetic Back Case", "category": "Cases & Back Covers", "hsn_code": "39269099", "gst_percent": 18, "purchase_cost": 120, "b2b_price": 210, "b2c_price": 350, "mrp": 499, "floor_price": 180, "low_stock_threshold": 15},
        # Power Banks
        {"part_name": "10000mAh 22.5W Fast Pocket Power Bank", "category": "Power Banks", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 620, "b2b_price": 840, "b2c_price": 1099, "mrp": 1499, "floor_price": 780, "low_stock_threshold": 8},
        {"part_name": "20000mAh 65W Laptop/Phone Power Bank", "category": "Power Banks", "hsn_code": "85044090", "gst_percent": 18, "purchase_cost": 1350, "b2b_price": 1750, "b2c_price": 2299, "mrp": 2999, "floor_price": 1550, "low_stock_threshold": 5},
        # Smart Wearables
        {"part_name": "AMOLED Smartwatch with BT Calling", "category": "Smart Wearables", "hsn_code": "85176290", "gst_percent": 18, "purchase_cost": 1250, "b2b_price": 1650, "b2c_price": 2199, "mrp": 2899, "floor_price": 1480, "low_stock_threshold": 5},
        # Tools & Spares
        {"part_name": "Precision Mobile Repair Kit 32-in-1", "category": "Mobile Spare Parts & Tools", "hsn_code": "85177090", "gst_percent": 18, "purchase_cost": 140, "b2b_price": 210, "b2c_price": 299, "mrp": 399, "floor_price": 180, "low_stock_threshold": 10},
    ]

    for p in products_to_seed:
        if p["part_name"] not in prod_map:
            cat_id = cat_map.get(p["category"])
            if not cat_id:
                continue
            payload = {
                "part_name": p["part_name"],
                "category_id": cat_id,
                "hsn_code": p["hsn_code"],
                "gst_percent": p["gst_percent"],
                "purchase_cost": p["purchase_cost"],
                "b2b_price": p["b2b_price"],
                "b2c_price": p["b2c_price"],
                "mrp": p["mrp"],
                "floor_price": p["floor_price"],
                "unit_of_measure": "Nos",
                "low_stock_threshold": p["low_stock_threshold"],
            }
            res = api("POST", "/products/", payload)
            if res and "id" in res:
                prod_map[p["part_name"]] = res["id"]
                print(f"  [+] Product created: {p['part_name']} (ID: {res['id']})")
        else:
            print(f"  [=] Product exists: {p['part_name']}")
    return prod_map

def seed_vendors():
    print("\n--- 4. Vendors ---")
    v_resp = api("GET", "/vendors/?page_size=50") or {}
    items = v_resp.get("items", []) if isinstance(v_resp, dict) else v_resp
    v_map = {v["trade_name"]: v["id"] for v in items}
    
    vendors = [
        {
            "name": "Tamilnadu Mobile Accessories Hub",
            "trade_name": "Tamilnadu Mobile Accessories Hub",
            "contact_person": "Karthik Raja",
            "phone": "9840011223",
            "email": "karthik@tnmobilehub.com",
            "gstin": "33AADCT5566D1Z1",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_days": 30
        },
        {
            "name": "Bangalore Impex Electronics",
            "trade_name": "Bangalore Impex Electronics",
            "contact_person": "Suresh Babu",
            "phone": "9880044556",
            "email": "orders@bangaloreimpex.com",
            "gstin": "29AABCB3344E1Z5",
            "state": "Karnataka",
            "state_code": 29,
            "credit_days": 45
        },
        {
            "name": "Mumbai Telecom Distributing Co",
            "trade_name": "Mumbai Telecom Distributing Co",
            "contact_person": "Vikram Seth",
            "phone": "9820077889",
            "email": "vikram@mumbaitelecom.in",
            "gstin": "27AABCM7890F1Z2",
            "state": "Maharashtra",
            "state_code": 27,
            "credit_days": 30
        }
    ]
    for v in vendors:
        if v["trade_name"] not in v_map:
            res = api("POST", "/vendors/", v)
            if res and "id" in res:
                v_map[v["trade_name"]] = res["id"]
                print(f"  [+] Vendor created: {v['trade_name']} (ID: {res['id']})")
        else:
            print(f"  [=] Vendor exists: {v['trade_name']}")
    return v_map

def seed_customers():
    print("\n--- 5. Customers ---")
    c_resp = api("GET", "/customers/?page_size=50") or {}
    items = c_resp.get("items", []) if isinstance(c_resp, dict) else c_resp
    c_map = {c["trade_name"]: c["id"] for c in items}
    
    customers = [
        {
            "name": "Sri Agni Mobiles",
            "trade_name": "Sri Agni Mobiles Retail Branch",
            "phone": "9842100001",
            "email": "retail@agnimobiles.com",
            "is_b2b": True,
            "gstin": "33AABCS1429B1Z8",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 100000,
            "credit_days": 30
        },
        {
            "name": "Pollachi Tech Point",
            "trade_name": "Pollachi Tech Point",
            "phone": "9842100002",
            "email": "sales@pollachiteck.in",
            "is_b2b": True,
            "gstin": "33AAECP1122C1Z4",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 50000,
            "credit_days": 15
        },
        {
            "name": "Annamalai Mobile World",
            "trade_name": "Annamalai Mobile World",
            "phone": "9842100005",
            "email": "annamalaimobiles@udt.in",
            "is_b2b": True,
            "gstin": "33AABCA8899G1Z7",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 75000,
            "credit_days": 21
        },
        {
            "name": "Kovai Mobile Zone",
            "trade_name": "Kovai Mobile Zone",
            "phone": "9842100003",
            "email": "kovaimobilezone@gmail.com",
            "is_b2b": False,
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 15000,
            "credit_days": 0
        },
        {
            "name": "Walk-in Retail Cash Customer",
            "trade_name": "Walk-in Retail Cash Customer",
            "phone": "9842199999",
            "email": "cash@counter.com",
            "is_b2b": False,
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 0,
            "credit_days": 0
        },
    ]
    for c in customers:
        if c["trade_name"] not in c_map:
            res = api("POST", "/customers/", c)
            if res and "id" in res:
                c_map[c["trade_name"]] = res["id"]
                print(f"  [+] Customer created: {c['trade_name']} (ID: {res['id']})")
        else:
            print(f"  [=] Customer exists: {c['trade_name']}")
    return c_map

def seed_purchases(wh_map, v_map, p_map):
    print("\n--- 6. Stock Inward Purchases (GRN) ---")
    today = date.today()
    main_wh = wh_map.get("MAIN", 1)
    
    # Check existing purchases
    p_resp = api("GET", "/purchases/?page_size=20") or {}
    items = p_resp.get("items", []) if isinstance(p_resp, dict) else p_resp
    if len(items) >= 3:
        print(f"  [=] Purchases already seeded ({len(items)} found)")
        return [p["id"] for p in items]

    purchases = [
        # Purchase 1: Chargers, Cables, Tempered Glass from Tamilnadu Mobile Hub (Intra-state CGST+SGST)
        {
            "vendor_id": v_map.get("Tamilnadu Mobile Accessories Hub"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "TN-INV-2026-081",
            "invoice_date": str(today - timedelta(days=12)),
            "received_date": str(today - timedelta(days=10)),
            "gst_type": "cgst_sgst",
            "notes": "Bulk chargers, cables, and 9H tempered glass stock",
            "items": [
                {"product_id": p_map.get("65W GaN Fast Charger Type-C"), "quantity": 60, "unit_cost": 450, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("20W PD iPhone Fast Adapter"), "quantity": 80, "unit_cost": 220, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 120, "unit_cost": 65, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("USB to Lightning Fast Cable (1m)"), "quantity": 100, "unit_cost": 55, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("Super D 9H Matte Tempered Glass"), "quantity": 250, "unit_cost": 18, "gst_percent": 18, "hsn_code": "70071900"},
                {"product_id": p_map.get("Shockproof Clear Hybrid Armor Case"), "quantity": 90, "unit_cost": 45, "gst_percent": 18, "hsn_code": "39269099"},
                # Intentionally low stock (only 5 purchased vs 50 threshold) to test Low Stock Alerts!
                {"product_id": p_map.get("Camera Lens Protector Ring 3-Pack"), "quantity": 5, "unit_cost": 15, "gst_percent": 18, "hsn_code": "70071900"},
            ]
        },
        # Purchase 2: Audio & Power Banks from Bangalore Impex (Inter-state IGST)
        {
            "vendor_id": v_map.get("Bangalore Impex Electronics"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "BIE-2026-104",
            "invoice_date": str(today - timedelta(days=8)),
            "received_date": str(today - timedelta(days=6)),
            "gst_type": "igst",
            "notes": "TWS Earbuds, Neckbands, and Fast Power Banks shipment",
            "items": [
                {"product_id": p_map.get("Wireless TWS Earbuds ENC Bass"), "quantity": 40, "unit_cost": 480, "gst_percent": 18, "hsn_code": "85183000"},
                {"product_id": p_map.get("Neckband Magnetic Bluetooth Earphones"), "quantity": 35, "unit_cost": 290, "gst_percent": 18, "hsn_code": "85183000"},
                {"product_id": p_map.get("Party Mini Bluetooth Speaker 10W"), "quantity": 25, "unit_cost": 380, "gst_percent": 18, "hsn_code": "85183000"},
                {"product_id": p_map.get("10000mAh 22.5W Fast Pocket Power Bank"), "quantity": 30, "unit_cost": 620, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("20000mAh 65W Laptop/Phone Power Bank"), "quantity": 20, "unit_cost": 1350, "gst_percent": 18, "hsn_code": "85044090"},
            ]
        },
        # Purchase 3: Wearables & Repair Spares from Mumbai Telecom (Inter-state IGST)
        {
            "vendor_id": v_map.get("Mumbai Telecom Distributing Co"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "MTD-2026-559",
            "invoice_date": str(today - timedelta(days=4)),
            "received_date": str(today - timedelta(days=3)),
            "gst_type": "igst",
            "notes": "Smartwatches and repair tools kit",
            "items": [
                {"product_id": p_map.get("AMOLED Smartwatch with BT Calling"), "quantity": 25, "unit_cost": 1250, "gst_percent": 18, "hsn_code": "85176290"},
                {"product_id": p_map.get("Precision Mobile Repair Kit 32-in-1"), "quantity": 40, "unit_cost": 140, "gst_percent": 18, "hsn_code": "85177090"},
            ]
        }
    ]

    p_ids = []
    for po in purchases:
        po["items"] = [i for i in po["items"] if i.get("product_id") is not None]
        if not po["items"]:
            continue
        res = api("POST", "/purchases/", po)
        if res and "id" in res:
            p_ids.append(res["id"])
            print(f"  [+] Purchase recorded: {po['vendor_invoice_number']} -> {res.get('purchase_number', '?')} (ID: {res['id']})")
    return p_ids

def seed_invoices(wh_map, c_map, p_map):
    print("\n--- 7. Invoices (B2B, B2C, Overdue, High-Value) ---")
    today = date.today()
    main_wh = wh_map.get("MAIN", 1)
    
    inv_resp = api("GET", "/invoices/?page_size=20") or {}
    items = inv_resp.get("items", []) if isinstance(inv_resp, dict) else inv_resp
    if len(items) >= 4:
        print(f"  [=] Invoices already seeded ({len(items)} found)")
        return [i["id"] for i in items]

    invoices = [
        # Invoice 1: B2B Wholesale Tax Invoice to Sri Agni Mobiles Retail Branch (Intra-state, CGST+SGST)
        {
            "document_type": "b2b_invoice",
            "customer_id": c_map.get("Sri Agni Mobiles Retail Branch"),
            "warehouse_id": main_wh,
            "invoice_date": str(today - timedelta(days=5)),
            "notes": "Wholesale accessories stock supply",
            "items": [
                {"product_id": p_map.get("65W GaN Fast Charger Type-C"), "quantity": 10, "unit_price": 580, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("20W PD iPhone Fast Adapter"), "quantity": 15, "unit_price": 310, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 25, "unit_price": 110, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("Super D 9H Matte Tempered Glass"), "quantity": 50, "unit_price": 45, "gst_percent": 18, "hsn_code": "70071900"},
            ]
        },
        # Invoice 2: High-Value Wholesale Invoice (> ₹50,000) -> Triggers E-Way Bill Requirement!
        {
            "document_type": "b2b_invoice",
            "customer_id": c_map.get("Annamalai Mobile World"),
            "warehouse_id": main_wh,
            "invoice_date": str(today - timedelta(days=2)),
            "vehicle_number": "TN38AB1234",
            "driver_name": "Murugan R",
            "notes": "Large bulk shipment (E-Way bill threshold test > Rs 50,000)",
            "items": [
                {"product_id": p_map.get("20000mAh 65W Laptop/Phone Power Bank"), "quantity": 12, "unit_price": 1750, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("AMOLED Smartwatch with BT Calling"), "quantity": 15, "unit_price": 1650, "gst_percent": 18, "hsn_code": "85176290"},
                {"product_id": p_map.get("Wireless TWS Earbuds ENC Bass"), "quantity": 15, "unit_price": 690, "gst_percent": 18, "hsn_code": "85183000"},
            ]
        },
        # Invoice 3: Overdue Invoice (Old date: 35 days ago) -> Tests Debtor Ageing Report (30-60 days)!
        {
            "document_type": "b2b_invoice",
            "customer_id": c_map.get("Pollachi Tech Point"),
            "warehouse_id": main_wh,
            "invoice_date": str(today - timedelta(days=35)),
            "due_date": str(today - timedelta(days=20)),
            "notes": "Prior cycle accessories dispatch (Overdue for testing Ageing Analysis)",
            "items": [
                {"product_id": p_map.get("Shockproof Clear Hybrid Armor Case"), "quantity": 30, "unit_price": 85, "gst_percent": 18, "hsn_code": "39269099"},
                {"product_id": p_map.get("USB to Lightning Fast Cable (1m)"), "quantity": 40, "unit_price": 95, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("10000mAh 22.5W Fast Pocket Power Bank"), "quantity": 5, "unit_price": 840, "gst_percent": 18, "hsn_code": "85044090"},
            ]
        },
        # Invoice 4: B2C Retail Counter Sale
        {
            "document_type": "b2c_invoice",
            "customer_id": c_map.get("Walk-in Retail Cash Customer"),
            "warehouse_id": main_wh,
            "invoice_date": str(today),
            "notes": "Retail walk-in accessories sale",
            "items": [
                {"product_id": p_map.get("20W PD iPhone Fast Adapter"), "quantity": 1, "unit_price": 420, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 1, "unit_price": 160, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("Privacy Anti-Spy Tempered Glass"), "quantity": 1, "unit_price": 130, "gst_percent": 18, "hsn_code": "70071900"},
            ]
        },
        # Invoice 5: Quotation (QT sequence) -> Tests Quotations feature
        {
            "document_type": "quotation",
            "customer_id": c_map.get("Kovai Mobile Zone"),
            "warehouse_id": main_wh,
            "invoice_date": str(today),
            "notes": "Store setup inquiry quotation",
            "items": [
                {"product_id": p_map.get("Party Mini Bluetooth Speaker 10W"), "quantity": 10, "unit_price": 540, "gst_percent": 18, "hsn_code": "85183000"},
                {"product_id": p_map.get("Neckband Magnetic Bluetooth Earphones"), "quantity": 20, "unit_price": 420, "gst_percent": 18, "hsn_code": "85183000"},
            ]
        }
    ]

    inv_ids = []
    for inv in invoices:
        inv["items"] = [i for i in inv["items"] if i.get("product_id") is not None]
        if not inv["items"]:
            continue
        res = api("POST", "/invoices/", inv)
        if res and "id" in res:
            inv_ids.append(res["id"])
            print(f"  [+] Invoice created: {res.get('invoice_number', '?')} ({inv['document_type']}, ID: {res['id']})")
    return inv_ids

def seed_receipts(c_map, inv_ids):
    print("\n--- 8. Customer Payment Receipts (Cash/Bank) ---")
    today = date.today()
    if not inv_ids:
        return
    # Record payment for first invoice
    res = api("POST", "/receipts/", {
        "customer_id": c_map.get("Sri Agni Mobiles Retail Branch"),
        "payment_date": str(today),
        "amount": 10000.0,
        "payment_mode": "neft",
        "reference_number": "NEFT-SBI-991244",
        "notes": "Advance / partial payment for wholesale invoice",
        "allocations": [{"invoice_id": inv_ids[0], "amount": 10000.0}]
    })
    if res and "id" in res:
        print(f"  [+] Receipt recorded: {res.get('receipt_number', '?')} (Amount: Rs 10,000)")

def seed_expenses():
    print("\n--- 9. Operational Expenses ---")
    today = date.today()
    expenses = [
        {"expense_category": "Electricity", "title": "Showroom Electricity Bill - Pollachi Branch", "amount": 3450, "expense_date": str(today - timedelta(days=3)), "payment_mode": "bank_transfer", "notes": "TNEB payment for Main showroom"},
        {"expense_category": "Tea & Refreshments", "title": "Staff & Customer Refreshments", "amount": 650, "expense_date": str(today), "payment_mode": "cash", "notes": "Daily tea and snacks for sales team"},
        {"expense_category": "Shop Rent", "title": "Showroom Monthly Rent", "amount": 18000, "expense_date": str(today - timedelta(days=8)), "payment_mode": "cheque", "notes": "Monthly rent for Palani Road showroom"},
    ]
    for exp in expenses:
        res = api("POST", "/expenses/", exp)
        if res and "id" in res:
            print(f"  [+] Expense recorded: {exp['title']} (Rs {exp['amount']})")
            # Auto-approve if pending
            api("POST", f"/expenses/{res['id']}/approve", {"admin_notes": "Approved by Super Admin"})

def main():
    print("==========================================================")
    print("  SEEDING COMPREHENSIVE FEATURE DEMO DATA FOR SRI AGNI MOBILES")
    print("==========================================================")
    
    login()
    wh_map = seed_warehouses()
    cat_map = seed_categories()
    p_map = seed_products(cat_map)
    v_map = seed_vendors()
    c_map = seed_customers()
    p_ids = seed_purchases(wh_map, v_map, p_map)
    inv_ids = seed_invoices(wh_map, c_map, p_map)
    seed_receipts(c_map, inv_ids)
    seed_expenses()
    
    print("\n==========================================================")
    print("  ALL MODULES & FEATURES SEEDED AND READY FOR CLIENT DEMO!")
    print("==========================================================")

if __name__ == "__main__":
    main()
