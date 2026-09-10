"""
seed_live_complete.py
Comprehensive Master Seeder for Live ERP (https://erp.vigneshgrowthlab.dev/api/v1).
Populates complete, realistic business data for CCTV & Security (KMS Vision, Sree Murugan Mills)
and Wholesale Tech/Electronics (Sri Agni Mobiles) so that clients can test EVERY SINGLE FEATURE:

1. Multi-Warehouse Management (Main Godown, Palani Rd Showroom, New Scheme Rd Service Hub)
2. Categories with custom prefixes and HSN codes
3. Products with 5-Tier Pricing (Purchase Cost, B2B, B2C, MRP, Floor Price) & Low Stock Alert
4. Vendors (Tamil Nadu local CGST/SGST & Karnataka/Maharashtra Inter-state IGST)
5. Customers (B2B wholesale with credit limits & B2C walk-in retail)
6. Purchases (Stock Inward / GRN with FIFO layers)
7. Vendor Payments (reducing payables)
8. Invoices:
   - B2B Wholesale Tax Invoice (CGST + SGST)
   - High-Value Invoice (> Rs 50,000) triggering E-Way Bill requirement
   - Overdue Invoice (35 days old) triggering 30-60 day Debtors Ageing bucket
   - B2C Retail Counter Sale
   - Quotation (QT sequence) for CCTV site installation
   - Delivery Challan (DC) for material dispatch (populating Pending Deliveries widget)
9. Inter-Warehouse Stock Transfer (Main -> Showroom)
10. Customer Receipts / Collections (NEFT & UPI partial allocations)
11. Operational Expenses (Rent, Electricity, Tea, Internet - approved)
12. Cash Closing (populating Cash/Bank balance)
"""

import urllib.request
import urllib.error
import json
from datetime import date, timedelta
from decimal import Decimal

BASE = "https://erp.vigneshgrowthlab.dev/api/v1"
TOKEN = None

def api(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8") if e.fp else ""
        print(f"  [ERR] {method} {path} -> {e.code}: {err[:300]}")
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
    print(f"[AUTH] Logged in successfully as {res.get('user', {}).get('role')}")

def seed_warehouses():
    print("\n--- 1. Multi-Warehouse Setup ---")
    wh_list = api("GET", "/warehouses/") or []
    wh_map = {w["code"]: w["id"] for w in wh_list}
    
    new_warehouses = [
        {"name": "Retail Showroom (Palani Road)", "code": "SHOWROOM", "city": "Pollachi", "state": "Tamil Nadu", "state_code": 33, "phone": "9842100010"},
        {"name": "Service & Spares Hub (New Scheme Rd)", "code": "SERVICE", "city": "Pollachi", "state": "Tamil Nadu", "state_code": 33, "phone": "9842100011"},
    ]
    for w in new_warehouses:
        if w["code"] not in wh_map:
            res = api("POST", "/warehouses/", w)
            if res and "id" in res:
                wh_map[w["code"]] = res["id"]
                print(f"  [+] Warehouse created: {w['name']} (ID: {res['id']})")
        else:
            print(f"  [=] Warehouse exists: {w['name']} (ID: {wh_map[w['code']]})")
    return wh_map

def seed_categories():
    print("\n--- 2. Product Categories ---")
    cats = api("GET", "/categories/") or []
    cat_map = {c["name"]: c["id"] for c in cats}
    
    data = [
        {"name": "CCTV & IP Cameras", "prefix": "CAM", "default_hsn": "85258900", "default_gst_percent": 18},
        {"name": "DVR & NVR Recorders", "prefix": "DVR", "default_hsn": "85219090", "default_gst_percent": 18},
        {"name": "Surveillance Storage & HDDs", "prefix": "HDD", "default_hsn": "84717020", "default_gst_percent": 18},
        {"name": "Networking & Cat6 Cables", "prefix": "CBL", "default_hsn": "85444299", "default_gst_percent": 18},
        {"name": "Power Supplies & SMPS", "prefix": "PWR", "default_hsn": "85044090", "default_gst_percent": 18},
        {"name": "Chargers & Fast Adapters", "prefix": "CHG", "default_hsn": "85044090", "default_gst_percent": 18},
        {"name": "Audio & Bluetooth", "prefix": "AUD", "default_hsn": "85183000", "default_gst_percent": 18},
        {"name": "Smart Wearables", "prefix": "WAT", "default_hsn": "85176290", "default_gst_percent": 18},
    ]
    for c in data:
        if c["name"] not in cat_map:
            res = api("POST", "/categories/", c)
            if res and "id" in res:
                cat_map[c["name"]] = res["id"]
                print(f"  [+] Category created: {c['name']} (ID: {res['id']})")
        else:
            print(f"  [=] Category exists: {c['name']} (ID: {cat_map[c['name']]})")
    return cat_map

def seed_products(cat_map):
    print("\n--- 3. Products Catalog with 5-Tier Pricing ---")
    prod_resp = api("GET", "/products/?page_size=100") or {}
    existing_items = prod_resp.get("items", []) if isinstance(prod_resp, dict) else prod_resp
    prod_map = {p["part_name"]: p["id"] for p in existing_items}
    
    products_to_seed = [
        # CCTV Cameras
        {
            "part_name": "Hikvision 4MP DarkFighter Bullet Camera",
            "category": "CCTV & IP Cameras",
            "hsn_code": "85258900",
            "gst_percent": 18,
            "purchase_cost": 2450,
            "b2b_price": 3100,
            "b2c_price": 3950,
            "mrp": 4999,
            "floor_price": 2800,
            "low_stock_threshold": 10
        },
        {
            "part_name": "Hikvision 2MP Smart Hybrid Light Dome Camera",
            "category": "CCTV & IP Cameras",
            "hsn_code": "85258900",
            "gst_percent": 18,
            "purchase_cost": 1250,
            "b2b_price": 1650,
            "b2c_price": 2150,
            "mrp": 2800,
            "floor_price": 1450,
            "low_stock_threshold": 15
        },
        {
            "part_name": "CP Plus 5MP ColorView Full Color Bullet Camera",
            "category": "CCTV & IP Cameras",
            "hsn_code": "85258900",
            "gst_percent": 18,
            "purchase_cost": 1850,
            "b2b_price": 2400,
            "b2c_price": 3100,
            "mrp": 3999,
            "floor_price": 2100,
            "low_stock_threshold": 10
        },
        # Recorders
        {
            "part_name": "CP Plus 8-Channel 4K Ultra HD NVR",
            "category": "DVR & NVR Recorders",
            "hsn_code": "85219090",
            "gst_percent": 18,
            "purchase_cost": 4200,
            "b2b_price": 5400,
            "b2c_price": 6800,
            "mrp": 8999,
            "floor_price": 4800,
            "low_stock_threshold": 5
        },
        {
            "part_name": "Hikvision 16-Channel HD Turbo DVR",
            "category": "DVR & NVR Recorders",
            "hsn_code": "85219090",
            "gst_percent": 18,
            "purchase_cost": 5800,
            "b2b_price": 7200,
            "b2c_price": 8900,
            "mrp": 11500,
            "floor_price": 6500,
            "low_stock_threshold": 4
        },
        # Surveillance Storage
        {
            "part_name": "Seagate SkyHawk 2TB Surveillance Hard Drive",
            "category": "Surveillance Storage & HDDs",
            "hsn_code": "84717020",
            "gst_percent": 18,
            "purchase_cost": 4100,
            "b2b_price": 4850,
            "b2c_price": 5600,
            "mrp": 6999,
            "floor_price": 4500,
            "low_stock_threshold": 8
        },
        {
            "part_name": "Seagate SkyHawk 4TB Surveillance Hard Drive",
            "category": "Surveillance Storage & HDDs",
            "hsn_code": "84717020",
            "gst_percent": 18,
            "purchase_cost": 6900,
            "b2b_price": 7950,
            "b2c_price": 9200,
            "mrp": 11999,
            "floor_price": 7400,
            "low_stock_threshold": 6
        },
        # Cables & Networking
        {
            "part_name": "D-Link Pure Copper Cat6 Solid Cable 305M Drum",
            "category": "Networking & Cat6 Cables",
            "hsn_code": "85444299",
            "gst_percent": 18,
            "purchase_cost": 6200,
            "b2b_price": 7300,
            "b2c_price": 8500,
            "mrp": 10499,
            "floor_price": 6800,
            "low_stock_threshold": 5
        },
        {
            "part_name": "Hikvision 4+2 Port 100Mbps PoE Switch",
            "category": "Networking & Cat6 Cables",
            "hsn_code": "85176290",
            "gst_percent": 18,
            "purchase_cost": 1750,
            "b2b_price": 2250,
            "b2c_price": 2900,
            "mrp": 3800,
            "floor_price": 2000,
            "low_stock_threshold": 8  # Stock purchased will be 3, triggering Low Stock Alert!
        },
        # Power SMPS
        {
            "part_name": "12V 8-Channel CCTV Regulated SMPS Power Supply",
            "category": "Power Supplies & SMPS",
            "hsn_code": "85044090",
            "gst_percent": 18,
            "purchase_cost": 550,
            "b2b_price": 780,
            "b2c_price": 1050,
            "mrp": 1499,
            "floor_price": 680,
            "low_stock_threshold": 12
        },
        # Tech / Electronics
        {
            "part_name": "65W GaN Fast Charger Type-C",
            "category": "Chargers & Fast Adapters",
            "hsn_code": "85044090",
            "gst_percent": 18,
            "purchase_cost": 450,
            "b2b_price": 580,
            "b2c_price": 750,
            "mrp": 999,
            "floor_price": 520,
            "low_stock_threshold": 10
        },
        {
            "part_name": "20W PD iPhone Fast Adapter",
            "category": "Chargers & Fast Adapters",
            "hsn_code": "85044090",
            "gst_percent": 18,
            "purchase_cost": 220,
            "b2b_price": 310,
            "b2c_price": 420,
            "mrp": 599,
            "floor_price": 280,
            "low_stock_threshold": 15
        },
        {
            "part_name": "Braided Type-C to Type-C 60W (1.5m)",
            "category": "Networking & Cat6 Cables",
            "hsn_code": "85444299",
            "gst_percent": 18,
            "purchase_cost": 65,
            "b2b_price": 110,
            "b2c_price": 160,
            "mrp": 249,
            "floor_price": 95,
            "low_stock_threshold": 25
        },
        {
            "part_name": "Wireless TWS Earbuds ENC Bass",
            "category": "Audio & Bluetooth",
            "hsn_code": "85183000",
            "gst_percent": 18,
            "purchase_cost": 480,
            "b2b_price": 690,
            "b2c_price": 899,
            "mrp": 1299,
            "floor_price": 620,
            "low_stock_threshold": 10
        },
        {
            "part_name": "20000mAh 65W Laptop/Phone Power Bank",
            "category": "Power Supplies & SMPS",
            "hsn_code": "85044090",
            "gst_percent": 18,
            "purchase_cost": 1350,
            "b2b_price": 1750,
            "b2c_price": 2299,
            "mrp": 2999,
            "floor_price": 1550,
            "low_stock_threshold": 5
        },
        {
            "part_name": "AMOLED Smartwatch with BT Calling",
            "category": "Smart Wearables",
            "hsn_code": "85176290",
            "gst_percent": 18,
            "purchase_cost": 1250,
            "b2b_price": 1650,
            "b2c_price": 2199,
            "mrp": 2899,
            "floor_price": 1480,
            "low_stock_threshold": 5
        }
    ]

    for p in products_to_seed:
        if p["part_name"] not in prod_map:
            cat_id = cat_map.get(p["category"])
            if not cat_id:
                print(f"  [!] Missing category ID for: {p['category']}")
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
            print(f"  [=] Product exists: {p['part_name']} (ID: {prod_map[p['part_name']]})")
    return prod_map

def seed_vendors():
    print("\n--- 4. Vendors (Local & Interstate) ---")
    v_resp = api("GET", "/vendors/?page_size=50") or {}
    items = v_resp.get("items", []) if isinstance(v_resp, dict) else v_resp
    v_map = {v["trade_name"]: v["id"] for v in items}
    
    vendors = [
        {
            "name": "Prama India Pvt Ltd",
            "trade_name": "Prama India Pvt Ltd (Hikvision)",
            "contact_person": "Rajesh Kumar",
            "phone": "9840123456",
            "email": "chennai.sales@pramaindia.com",
            "gstin": "33AAACP2931F1Z3",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_days": 30
        },
        {
            "name": "Aditya Infotech Ltd",
            "trade_name": "Aditya Infotech Ltd (CP Plus)",
            "contact_person": "Sanjay Rao",
            "phone": "9880198765",
            "email": "orders.south@adityagroup.com",
            "gstin": "29AAACA1234D1Z2",
            "state": "Karnataka",
            "state_code": 29,
            "credit_days": 45
        },
        {
            "name": "D-Link India Ltd",
            "trade_name": "D-Link India Ltd",
            "contact_person": "Nitin Desai",
            "phone": "9820155443",
            "email": "sales@dlink.co.in",
            "gstin": "27AABCD4567E1Z5",
            "state": "Maharashtra",
            "state_code": 27,
            "credit_days": 30
        },
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
        }
    ]
    for v in vendors:
        if v["trade_name"] not in v_map:
            res = api("POST", "/vendors/", v)
            if res and "id" in res:
                v_map[v["trade_name"]] = res["id"]
                print(f"  [+] Vendor created: {v['trade_name']} (ID: {res['id']})")
        else:
            print(f"  [=] Vendor exists: {v['trade_name']} (ID: {v_map[v['trade_name']]})")
    return v_map

def seed_customers():
    print("\n--- 5. Customers (B2B & B2C) ---")
    c_resp = api("GET", "/customers/?page_size=50") or {}
    items = c_resp.get("items", []) if isinstance(c_resp, dict) else c_resp
    c_map = {c["trade_name"]: c["id"] for c in items}
    
    customers = [
        {
            "trade_name": "KMS Vision & Security Solutions",
            "legal_name": "KMS Vision & Security Solutions",
            "phone": "9842211000",
            "email": "kmsvision.cctv@gmail.com",
            "contact_person": "M. Senthil Kumar",
            "is_b2b": True,
            "gstin": "33AAAFK1234A1Z9",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 150000,
            "credit_days": 30
        },
        {
            "trade_name": "Sree Murugan Textile Mills Pvt Ltd",
            "legal_name": "Sree Murugan Textile Mills Pvt Ltd",
            "phone": "9842100008",
            "email": "purchase@sreemuruganmills.com",
            "contact_person": "R. Murugesan (Admin Mgr)",
            "is_b2b": True,
            "gstin": "33AABCS5566K1Z4",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 200000,
            "credit_days": 30
        },
        {
            "trade_name": "K.R. Cotton Textiles",
            "legal_name": "K.R. Cotton Textiles",
            "phone": "9842100009",
            "email": "krcotton@negamam.in",
            "contact_person": "K. Ramasamy",
            "is_b2b": True,
            "gstin": "33AAECK8899M1Z8",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 75000,
            "credit_days": 15
        },
        {
            "trade_name": "Sri Agni Mobiles Retail Branch",
            "legal_name": "Sri Agni Mobiles Retail Branch",
            "phone": "9842100001",
            "email": "retail@agnimobiles.com",
            "contact_person": "Vignesh Prabhu",
            "is_b2b": True,
            "gstin": "33AABCS1429B1Z8",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 100000,
            "credit_days": 30
        },
        {
            "trade_name": "Pollachi Tech Point",
            "legal_name": "Pollachi Tech Point",
            "phone": "9842100002",
            "email": "sales@pollachiteck.in",
            "contact_person": "S. Anand",
            "is_b2b": True,
            "gstin": "33AAECP1122C1Z4",
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 50000,
            "credit_days": 15
        },
        {
            "trade_name": "Walk-in Retail Cash Customer",
            "legal_name": "Walk-in Retail Cash Customer",
            "phone": "9842199999",
            "email": "cash@counter.com",
            "is_b2b": False,
            "state": "Tamil Nadu",
            "state_code": 33,
            "credit_limit": 0,
            "credit_days": 0
        }
    ]
    for c in customers:
        if c["trade_name"] not in c_map:
            res = api("POST", "/customers/", c)
            if res and "id" in res:
                c_map[c["trade_name"]] = res["id"]
                print(f"  [+] Customer created: {c['trade_name']} (ID: {res['id']})")
        else:
            print(f"  [=] Customer exists: {c['trade_name']} (ID: {c_map[c['trade_name']]})")
    return c_map

def seed_purchases(wh_map, v_map, p_map):
    print("\n--- 6. Purchases / Stock Inward (FIFO Costing) ---")
    today = date.today()
    main_wh = wh_map.get("MAIN") or list(wh_map.values())[0]

    existing_po = api("GET", "/purchases/?page_size=10") or {}
    items = existing_po.get("items", []) if isinstance(existing_po, dict) else existing_po
    if len(items) >= 4:
        print(f"  [=] Purchases already seeded ({len(items)} found)")
        return [i["id"] for i in items]

    purchases = [
        # PO 1: CCTV Inward from Prama India (Hikvision) - Intra-state
        {
            "vendor_id": v_map.get("Prama India Pvt Ltd (Hikvision)"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "PRAMA-CHN-2026-881",
            "invoice_date": str(today - timedelta(days=10)),
            "received_date": str(today - timedelta(days=9)),
            "notes": "Bulk Hikvision IP & Turbo HD Surveillance gear",
            "items": [
                {"product_id": p_map.get("Hikvision 4MP DarkFighter Bullet Camera"), "quantity": 25, "unit_cost": 2450, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("Hikvision 2MP Smart Hybrid Light Dome Camera"), "quantity": 40, "unit_cost": 1250, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("Hikvision 16-Channel HD Turbo DVR"), "quantity": 10, "unit_cost": 5800, "gst_percent": 18, "hsn_code": "85219090"},
                {"product_id": p_map.get("Hikvision 4+2 Port 100Mbps PoE Switch"), "quantity": 3, "unit_cost": 1750, "gst_percent": 18, "hsn_code": "85176290"}, # Low stock! (Threshold 8, qty 3)
            ]
        },
        # PO 2: CP Plus & Seagate HDDs from Aditya Infotech - Inter-state (IGST)
        {
            "vendor_id": v_map.get("Aditya Infotech Ltd (CP Plus)"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "AIL-BLR-2026-440",
            "invoice_date": str(today - timedelta(days=7)),
            "received_date": str(today - timedelta(days=6)),
            "notes": "CP Plus 4K NVRs, ColorView Bullets & SkyHawk HDDs",
            "items": [
                {"product_id": p_map.get("CP Plus 5MP ColorView Full Color Bullet Camera"), "quantity": 30, "unit_cost": 1850, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("CP Plus 8-Channel 4K Ultra HD NVR"), "quantity": 12, "unit_cost": 4200, "gst_percent": 18, "hsn_code": "85219090"},
                {"product_id": p_map.get("Seagate SkyHawk 2TB Surveillance Hard Drive"), "quantity": 20, "unit_cost": 4100, "gst_percent": 18, "hsn_code": "84717020"},
                {"product_id": p_map.get("Seagate SkyHawk 4TB Surveillance Hard Drive"), "quantity": 15, "unit_cost": 6900, "gst_percent": 18, "hsn_code": "84717020"},
            ]
        },
        # PO 3: Networking Cables & SMPS from D-Link India
        {
            "vendor_id": v_map.get("D-Link India Ltd"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "DLINK-MUM-2026-102",
            "invoice_date": str(today - timedelta(days=5)),
            "received_date": str(today - timedelta(days=4)),
            "notes": "Cat6 solid pure copper drums & SMPS power supplies",
            "items": [
                {"product_id": p_map.get("D-Link Pure Copper Cat6 Solid Cable 305M Drum"), "quantity": 15, "unit_cost": 6200, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("12V 8-Channel CCTV Regulated SMPS Power Supply"), "quantity": 35, "unit_cost": 550, "gst_percent": 18, "hsn_code": "85044090"},
            ]
        },
        # PO 4: Tech & Fast Chargers from Tamilnadu Mobile Accessories Hub
        {
            "vendor_id": v_map.get("Tamilnadu Mobile Accessories Hub"),
            "warehouse_id": main_wh,
            "vendor_invoice_number": "TN-ACC-2026-904",
            "invoice_date": str(today - timedelta(days=3)),
            "received_date": str(today - timedelta(days=2)),
            "notes": "GaN chargers, Type-C cables, TWS and power banks",
            "items": [
                {"product_id": p_map.get("65W GaN Fast Charger Type-C"), "quantity": 30, "unit_cost": 450, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("20W PD iPhone Fast Adapter"), "quantity": 40, "unit_cost": 220, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 60, "unit_cost": 65, "gst_percent": 18, "hsn_code": "85444299"},
                {"product_id": p_map.get("Wireless TWS Earbuds ENC Bass"), "quantity": 25, "unit_cost": 480, "gst_percent": 18, "hsn_code": "85183000"},
                {"product_id": p_map.get("20000mAh 65W Laptop/Phone Power Bank"), "quantity": 20, "unit_cost": 1350, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("AMOLED Smartwatch with BT Calling"), "quantity": 20, "unit_cost": 1250, "gst_percent": 18, "hsn_code": "85176290"},
            ]
        }
    ]

    p_ids = []
    for po in purchases:
        po["items"] = [i for i in po["items"] if i.get("product_id") is not None]
        if not po["items"]:
            print(f"  [!] Skipped empty PO {po['vendor_invoice_number']}")
            continue
        res = api("POST", "/purchases/", po)
        if res and "id" in res:
            p_ids.append(res["id"])
            print(f"  [+] Purchase recorded: {po['vendor_invoice_number']} -> {res.get('purchase_number', '?')} (ID: {res['id']})")
    return p_ids

def seed_vendor_payments(v_map, p_ids):
    print("\n--- 7. Vendor Payments (Reducing Payables) ---")
    today = date.today()
    if not p_ids:
        return
    prama_id = v_map.get("Prama India Pvt Ltd (Hikvision)")
    if prama_id:
        res = api("POST", "/vendor-payments/", {
            "vendor_id": prama_id,
            "purchase_id": p_ids[0],
            "payment_date": str(today - timedelta(days=3)),
            "amount": 50000.0,
            "payment_mode": "bank",
            "reference_number": "HDFC-NEFT-883921",
            "notes": "Part payment against Prama Hikvision consignment"
        })
        if res and "id" in res:
            print(f"  [+] Vendor payment recorded: Rs 50,000 to Prama India (ID: {res['id']})")

def seed_invoices(wh_map, c_map, p_map):
    print("\n--- 8. Invoices (B2B, E-Way Bill > Rs 50k, Overdue, B2C, Quotation, DC) ---")
    today = date.today()
    main_wh = wh_map.get("MAIN") or list(wh_map.values())[0]
    service_wh = wh_map.get("SERVICE") or main_wh
    
    inv_resp = api("GET", "/invoices/?page_size=20") or {}
    items = inv_resp.get("items", []) if isinstance(inv_resp, dict) else inv_resp
    if len(items) >= 5:
        print(f"  [=] Invoices already seeded ({len(items)} found)")
        return [i["id"] for i in items]

    invoices = [
        # Invoice 1: B2B Wholesale Tax Invoice - Sree Murugan Textile Mills (CCTV Plant Security)
        {
            "document_type": "b2b_invoice",
            "customer_id": c_map.get("Sree Murugan Textile Mills Pvt Ltd"),
            "warehouse_id": main_wh,
            "invoice_date": str(today - timedelta(days=6)),
            "notes": "Plant Unit-2 CCTV expansion: DarkFighter cameras, 16CH DVR, SkyHawk HDDs",
            "items": [
                {"product_id": p_map.get("Hikvision 4MP DarkFighter Bullet Camera"), "quantity": 8, "unit_price": 3100, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("Hikvision 2MP Smart Hybrid Light Dome Camera"), "quantity": 12, "unit_price": 1650, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("Hikvision 16-Channel HD Turbo DVR"), "quantity": 1, "unit_price": 7200, "gst_percent": 18, "hsn_code": "85219090"},
                {"product_id": p_map.get("Seagate SkyHawk 4TB Surveillance Hard Drive"), "quantity": 2, "unit_price": 7950, "gst_percent": 18, "hsn_code": "84717020"},
                {"product_id": p_map.get("12V 8-Channel CCTV Regulated SMPS Power Supply"), "quantity": 3, "unit_price": 780, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("D-Link Pure Copper Cat6 Solid Cable 305M Drum"), "quantity": 2, "unit_price": 7300, "gst_percent": 18, "hsn_code": "85444299"},
            ]
        },
        # Invoice 2: High-Value Wholesale Invoice (> Rs 50,000) - KMS Vision & Security Solutions
        # Tests E-Way Bill Requirement & Transport Details!
        {
            "document_type": "b2b_invoice",
            "customer_id": c_map.get("KMS Vision & Security Solutions"),
            "warehouse_id": main_wh,
            "invoice_date": str(today - timedelta(days=2)),
            "vehicle_number": "TN38AB1234",
            "driver_name": "Murugan R",
            "notes": "Bulk supply to KMS Vision: CP Plus 4K NVRs, ColorView cameras, SkyHawk HDDs (E-Way bill threshold test > Rs 50k)",
            "items": [
                {"product_id": p_map.get("CP Plus 5MP ColorView Full Color Bullet Camera"), "quantity": 15, "unit_price": 2400, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("CP Plus 8-Channel 4K Ultra HD NVR"), "quantity": 3, "unit_price": 5400, "gst_percent": 18, "hsn_code": "85219090"},
                {"product_id": p_map.get("Seagate SkyHawk 2TB Surveillance Hard Drive"), "quantity": 5, "unit_price": 4850, "gst_percent": 18, "hsn_code": "84717020"},
                {"product_id": p_map.get("D-Link Pure Copper Cat6 Solid Cable 305M Drum"), "quantity": 3, "unit_price": 7300, "gst_percent": 18, "hsn_code": "85444299"},
            ]
        },
        # Invoice 3: Overdue Invoice (Old date: 35 days ago, due 20 days ago) - Pollachi Tech Point
        # Tests Debtors Ageing Analysis (31-60 days bucket) & Overdue Widget!
        {
            "document_type": "b2b_invoice",
            "customer_id": c_map.get("Pollachi Tech Point"),
            "warehouse_id": main_wh,
            "invoice_date": str(today - timedelta(days=35)),
            "due_date": str(today - timedelta(days=20)),
            "notes": "Previous dispatch of Fast Chargers & Power Banks (Overdue for Ageing Report testing)",
            "items": [
                {"product_id": p_map.get("65W GaN Fast Charger Type-C"), "quantity": 15, "unit_price": 580, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("20000mAh 65W Laptop/Phone Power Bank"), "quantity": 6, "unit_price": 1750, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 20, "unit_price": 110, "gst_percent": 18, "hsn_code": "85444299"},
            ]
        },
        # Invoice 4: B2C Retail Counter Cash Billing - Walk-in Customer
        {
            "document_type": "b2c_invoice",
            "customer_id": c_map.get("Walk-in Retail Cash Customer"),
            "warehouse_id": main_wh,
            "invoice_date": str(today),
            "notes": "Walk-in retail counter sale: 20W PD adapter + Braided cable",
            "items": [
                {"product_id": p_map.get("20W PD iPhone Fast Adapter"), "quantity": 2, "unit_price": 420, "gst_percent": 18, "hsn_code": "85044090"},
                {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 2, "unit_price": 160, "gst_percent": 18, "hsn_code": "85444299"},
            ]
        },
        # Invoice 5: Quotation (QT sequence) - K.R. Cotton Textiles
        # Tests Quotations screen and "Convert to Invoice" feature!
        {
            "document_type": "quotation",
            "customer_id": c_map.get("K.R. Cotton Textiles"),
            "warehouse_id": main_wh,
            "invoice_date": str(today),
            "notes": "Quotation for Negamam Mill compound security installation",
            "items": [
                {"product_id": p_map.get("Hikvision 4MP DarkFighter Bullet Camera"), "quantity": 6, "unit_price": 3100, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("Hikvision 16-Channel HD Turbo DVR"), "quantity": 1, "unit_price": 7200, "gst_percent": 18, "hsn_code": "85219090"},
                {"product_id": p_map.get("Seagate SkyHawk 2TB Surveillance Hard Drive"), "quantity": 1, "unit_price": 4850, "gst_percent": 18, "hsn_code": "84717020"},
                {"product_id": p_map.get("D-Link Pure Copper Cat6 Solid Cable 305M Drum"), "quantity": 2, "unit_price": 7300, "gst_percent": 18, "hsn_code": "85444299"},
            ]
        },
        # Invoice 6: Delivery Challan (DC sequence) - Site Spares Dispatch
        # Tests Delivery Challans & Pending Deliveries Widget on Dashboard!
        {
            "document_type": "delivery_challan",
            "customer_id": c_map.get("KMS Vision & Security Solutions"),
            "warehouse_id": main_wh,
            "dc_destination_warehouse_id": service_wh,
            "invoice_date": str(today),
            "notes": "Site material dispatch challan: Spares for Sree Murugan site installation",
            "items": [
                {"product_id": p_map.get("Hikvision 2MP Smart Hybrid Light Dome Camera"), "quantity": 4, "unit_price": 1650, "gst_percent": 18, "hsn_code": "85258900"},
                {"product_id": p_map.get("12V 8-Channel CCTV Regulated SMPS Power Supply"), "quantity": 2, "unit_price": 780, "gst_percent": 18, "hsn_code": "85044090"},
            ]
        }
    ]

    inv_ids = []
    for inv in invoices:
        inv["items"] = [i for i in inv["items"] if i.get("product_id") is not None]
        if not inv["items"]:
            print(f"  [!] Skipped empty invoice {inv['document_type']}")
            continue
        res = api("POST", "/invoices/", inv)
        if res and "id" in res:
            inv_ids.append(res["id"])
            print(f"  [+] Invoice created: {res.get('invoice_number', '?')} ({inv['document_type']}, ID: {res['id']})")
    return inv_ids

def seed_receipts(c_map, inv_ids):
    print("\n--- 9. Customer Payment Receipts (Cash/Bank Collections) ---")
    today = date.today()
    if len(inv_ids) < 2:
        return
    
    # Receipt 1: Sree Murugan Mills paid Rs 45,000 via NEFT
    res1 = api("POST", "/receipts/", {
        "customer_id": c_map.get("Sree Murugan Textile Mills Pvt Ltd"),
        "payment_date": str(today),
        "amount": 45000.0,
        "payment_mode": "neft",
        "reference_number": "NEFT-SBI-449102",
        "notes": "Advance / partial payment for Unit-2 CCTV bill",
        "allocations": [{"invoice_id": inv_ids[0], "amount": 45000.0}]
    })
    if res1 and "id" in res1:
        print(f"  [+] Receipt 1 recorded: {res1.get('receipt_number', '?')} (Rs 45,000 via NEFT)")

    # Receipt 2: KMS Vision paid Rs 30,000 via UPI
    res2 = api("POST", "/receipts/", {
        "customer_id": c_map.get("KMS Vision & Security Solutions"),
        "payment_date": str(today),
        "amount": 30000.0,
        "payment_mode": "upi",
        "reference_number": "UPI-GPay-77192844",
        "notes": "On-account bulk payment",
        "allocations": [{"invoice_id": inv_ids[1], "amount": 30000.0}]
    })
    if res2 and "id" in res2:
        print(f"  [+] Receipt 2 recorded: {res2.get('receipt_number', '?')} (Rs 30,000 via UPI)")

def seed_stock_transfer(wh_map, p_map):
    print("\n--- 10. Inter-Warehouse Stock Transfer ---")
    today = date.today()
    main_wh = wh_map.get("MAIN") or list(wh_map.values())[0]
    showroom_wh = wh_map.get("SHOWROOM")
    if not showroom_wh:
        print("  [!] Showroom warehouse not found, skipping transfer")
        return
    
    prod_id = p_map.get("Hikvision 2MP Smart Hybrid Light Dome Camera")
    if not prod_id:
        return
    
    res = api("POST", "/stock-transfers/", {
        "source_warehouse_id": main_wh,
        "destination_warehouse_id": showroom_wh,
        "product_id": prod_id,
        "quantity": 5,
        "transfer_date": str(today),
        "notes": "Display units dispatched to Palani Road Showroom"
    })
    if res and "id" in res:
        print(f"  [+] Stock Transfer completed: {res.get('transfer_number', '?')} (5 Domes -> Showroom)")

def seed_expenses():
    print("\n--- 11. Operational Expenses (Accounting) ---")
    today = date.today()
    expenses = [
        {"category": "Shop Rent", "description": "Showroom Monthly Rent (Palani Road)", "amount": 22000, "expense_date": str(today - timedelta(days=5)), "payment_mode": "bank", "notes": "Palani Road showroom rent"},
        {"category": "Electricity", "description": "TNEB Commercial Power Bill", "amount": 4850, "expense_date": str(today - timedelta(days=2)), "payment_mode": "bank", "notes": "Main warehouse & showroom power bill"},
        {"category": "Tea & Refreshments", "description": "Staff & Customer Refreshments", "amount": 850, "expense_date": str(today), "payment_mode": "cash", "notes": "Daily tea and snacks for site crew"},
        {"category": "Office Expenses", "description": "High-Speed Fiber & Cloud Backup", "amount": 1500, "expense_date": str(today - timedelta(days=4)), "payment_mode": "bank", "notes": "BSNL FTTH & AWS CCTV Cloud storage"},
    ]
    for exp in expenses:
        res = api("POST", "/expenses/", exp)
        if res and "id" in res:
            print(f"  [+] Expense created: {exp['description']} (Rs {exp['amount']})")
            # Auto-approve so it hits P&L
            api("POST", f"/expenses/{res['id']}/approve", {"approved": True, "admin_notes": "Approved by Super Admin"})

def seed_cash_closing():
    print("\n--- 12. Cash Closing (Dashboard Cash Balance) ---")
    today = date.today()
    res = api("POST", "/cash-closing/", {
        "closing_date": str(today),
        "total_deposits": 500.0,
        "notes": "Daily counter cash tally and bank deposit"
    })
    if res and "id" in res:
        print(f"  [+] Cash closing recorded: ID {res['id']}")
        # Approve closing
        app_res = api("POST", f"/cash-closing/approve?closing_id={res['id']}&closing_date={today}", {
            "notes": "Cash closing verified and approved"
        })
        if app_res:
            print(f"  [+] Cash closing approved! Closing balance: Rs {app_res.get('closing_balance', '?')}")

def verify_dashboard():
    print("\n--- 13. Dashboard Metrics Verification ---")
    res = api("GET", "/dashboard/")
    if res:
        print("\n================ LIVE DASHBOARD METRICS ================")
        print(f"  Today's Sales:       Rs {res.get('today_sales', 0):,.2f}")
        print(f"  Month Sales:         Rs {res.get('month_sales', 0):,.2f}")
        print(f"  Stock Valuation:     Rs {res.get('stock_value', 0):,.2f}")
        print(f"  Total Receivables:   Rs {res.get('total_outstanding', 0):,.2f}")
        print(f"  Overdue (30+ Days):  Rs {res.get('overdue_amount', 0):,.2f}")
        print(f"  Total Payables:      Rs {res.get('total_payables', 0):,.2f}")
        print(f"  Month Purchases:     Rs {res.get('month_purchases', 0):,.2f}")
        print(f"  Today's Collections: Rs {res.get('today_collections', 0):,.2f}")
        print(f"  Low Stock Alerts:    {res.get('low_stock_count', 0)} items")
        print(f"  Pending Deliveries:  {res.get('pending_deliveries', 0)} DCs")
        print(f"  Top Customers:       {len(res.get('top_customers', []))} active")
        print(f"  Recent Invoices:     {len(res.get('recent_invoices', []))} listed")
        print(f"  Sales Trend Data:    {len(res.get('sales_trend', []))} months")
        print("========================================================\n")
    else:
        print("  [!] Failed to fetch dashboard metrics")

def main():
    print("==========================================================")
    print("  SEEDING COMPREHENSIVE CLIENT DEMO DATA ON LIVE ERP")
    print("  Target: https://erp.vigneshgrowthlab.dev/api/v1")
    print("==========================================================")
    
    login()
    wh_map = seed_warehouses()
    cat_map = seed_categories()
    p_map = seed_products(cat_map)
    v_map = seed_vendors()
    c_map = seed_customers()
    p_ids = seed_purchases(wh_map, v_map, p_map)
    seed_vendor_payments(v_map, p_ids)
    inv_ids = seed_invoices(wh_map, c_map, p_map)
    seed_receipts(c_map, inv_ids)
    seed_stock_transfer(wh_map, p_map)
    seed_expenses()
    seed_cash_closing()
    verify_dashboard()

if __name__ == "__main__":
    main()
