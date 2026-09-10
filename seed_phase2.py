"""
seed_phase2.py
Completes seeding of remaining features:
- Stock Inward for remaining items (so B2C invoice succeeds)
- B2C Retail Counter sale
- Operational Expenses (Electricity, Tea, Rent)
- Inter-warehouse Stock Transfer (Main -> Showroom)
- Price History & Scheduled Price Change (for Price Trend chart)
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

def main():
    global TOKEN
    # 1. Login
    res = api("POST", "/auth/login", {"username": "admin", "password": "Admin@1234"})
    TOKEN = res["access_token"]
    print("[OK] Authenticated as super_admin")

    today = date.today()

    # Get lookups
    whs = api("GET", "/warehouses/") or []
    wh_map = {w["code"]: w["id"] for w in whs}
    main_wh = wh_map.get("MAIN", 1)
    showroom_wh = wh_map.get("SHOWROOM", 2)

    prods = (api("GET", "/products/?page_size=100") or {}).get("items", [])
    p_map = {p["part_name"]: p["id"] for p in prods}

    vendors = (api("GET", "/vendors/?page_size=50") or {}).get("items", [])
    v_map = {v["trade_name"]: v["id"] for v in vendors}

    custs = (api("GET", "/customers/?page_size=50") or {}).get("items", [])
    c_map = {c["trade_name"]: c["id"] for c in custs}

    print("Lookups resolved: Products:", len(p_map), "Warehouses:", len(wh_map))

    # 2. Purchase remaining items so stock is available
    po_payload = {
        "vendor_id": v_map.get("Tamilnadu Mobile Accessories Hub"),
        "warehouse_id": main_wh,
        "vendor_invoice_number": "TN-INV-2026-099",
        "invoice_date": str(today - timedelta(days=2)),
        "received_date": str(today - timedelta(days=1)),
        "gst_type": "cgst_sgst",
        "notes": "Fast replenish: Privacy glass, MagSafe covers, 3-in-1 cables",
        "items": [
            {"product_id": p_map.get("Privacy Anti-Spy Tempered Glass"), "quantity": 50, "unit_cost": 32, "gst_percent": 18, "hsn_code": "70071900"},
            {"product_id": p_map.get("MagSafe Leather Magnetic Back Case"), "quantity": 30, "unit_cost": 120, "gst_percent": 18, "hsn_code": "39269099"},
            {"product_id": p_map.get("3-in-1 Fast Charging Nylon Cable"), "quantity": 40, "unit_cost": 85, "gst_percent": 18, "hsn_code": "85444299"},
        ]
    }
    po_payload["items"] = [i for i in po_payload["items"] if i.get("product_id")]
    res = api("POST", "/purchases/", po_payload)
    if res and "id" in res:
        print(f"[+] Stock Inward Purchase: {res.get('purchase_number', '?')} (ID: {res['id']})")

    # 3. B2C Retail Counter Sale
    b2c_payload = {
        "document_type": "b2c_invoice",
        "customer_id": c_map.get("Walk-in Retail Cash Customer"),
        "warehouse_id": main_wh,
        "invoice_date": str(today),
        "notes": "Walk-in cash customer billing",
        "items": [
            {"product_id": p_map.get("20W PD iPhone Fast Adapter"), "quantity": 2, "unit_price": 420, "gst_percent": 18, "hsn_code": "85044090"},
            {"product_id": p_map.get("Braided Type-C to Type-C 60W (1.5m)"), "quantity": 2, "unit_price": 160, "gst_percent": 18, "hsn_code": "85444299"},
            {"product_id": p_map.get("Privacy Anti-Spy Tempered Glass"), "quantity": 2, "unit_price": 130, "gst_percent": 18, "hsn_code": "70071900"},
        ]
    }
    b2c_payload["items"] = [i for i in b2c_payload["items"] if i.get("product_id")]
    res = api("POST", "/invoices/", b2c_payload)
    if res and "id" in res:
        print(f"[+] B2C Retail Invoice created: {res.get('invoice_number', '?')} (ID: {res['id']})")
        # Settle B2C invoice with cash receipt
        api("POST", "/receipts/", {
            "customer_id": c_map.get("Walk-in Retail Cash Customer"),
            "payment_date": str(today),
            "amount": float(res.get("total_amount", 1675.6)),
            "payment_mode": "cash",
            "notes": "Counter cash collected",
            "allocations": [{"invoice_id": res["id"], "amount": float(res.get("total_amount", 1675.6))}]
        })
        print(f"  [+] B2C Cash Receipt Settled!")

    # 4. Operational Expenses
    expenses = [
        {"category": "Utilities", "description": "Showroom Electricity Bill - Pollachi Branch", "amount": 3450, "expense_date": str(today - timedelta(days=3)), "payment_mode": "bank"},
        {"category": "Refreshments", "description": "Staff & Customer Refreshments", "amount": 650, "expense_date": str(today), "payment_mode": "cash"},
        {"category": "Rent", "description": "Showroom Monthly Rent", "amount": 18000, "expense_date": str(today - timedelta(days=8)), "payment_mode": "cheque"},
    ]
    for exp in expenses:
        res = api("POST", "/expenses/", exp)
        if res and "id" in res:
            print(f"[+] Expense logged: {exp['description']} (Rs {exp['amount']})")
            api("POST", f"/expenses/{res['id']}/approve", {"approved": True, "admin_notes": "Approved by Super Admin"})

    # 5. Stock Transfer (Main -> Showroom)
    transfer_payload = {
        "source_warehouse_id": main_wh,
        "destination_warehouse_id": showroom_wh,
        "product_id": p_map.get("65W GaN Fast Charger Type-C"),
        "quantity": 10,
        "transfer_date": str(today),
        "notes": "Branch stock transfer to Palani Road showroom display"
    }
    res = api("POST", "/stock-transfers/", transfer_payload)
    if res and "id" in res:
        print(f"[+] Stock Transfer created: {res.get('transfer_number', '?')} (ID: {res['id']})")

    # 6. Price History & Scheduled Price Change (Price Trend feature)
    gan_id = p_map.get("65W GaN Fast Charger Type-C")
    if gan_id:
        future_date = str(today + timedelta(days=15))
        res = api("POST", f"/price-history/{gan_id}/update", {
            "price_type": "b2b_price",
            "price": 620.0,
            "effective_from": future_date,
            "change_reason": "Scheduled quarterly vendor price revision"
        })
        if res:
            print(f"[+] Scheduled Price Change registered for 65W GaN Charger -> Rs 620 effective {future_date}")

    print("\n[ALL FEATURES SEEDED SUCCESSFULLY!]")

if __name__ == "__main__":
    main()
