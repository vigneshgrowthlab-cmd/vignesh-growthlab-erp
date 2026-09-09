"""One-off verification for the purchase gst_type derivation fix.

Creates a purchase from a Tamil Nadu vendor (expect cgst_sgst) and one from
an out-of-state vendor (expect igst) against the running backend.
"""
import sys
from datetime import date

import requests

BASE = "http://localhost:8000/api/v1"
TODAY = date.today().isoformat()


def main():
    r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "Admin@1234"})
    r.raise_for_status()
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def get(path, **params):
        resp = requests.get(f"{BASE}{path}", headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def post(path, payload):
        resp = requests.post(f"{BASE}{path}", headers=headers, json=payload)
        if resp.status_code >= 400:
            print(f"  ERROR {resp.status_code} on {path}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def create_purchase(payload):
        resp = requests.post(f"{BASE}/purchases", headers=headers, json=payload)
        if resp.status_code == 409:
            listed = get("/purchases", vendor_id=payload["vendor_id"],
                         search=payload["vendor_invoice_number"])["items"]
            print(f"  (already exists, fetched purchase id {listed[0]['id']})")
            return get(f"/purchases/{listed[0]['id']}")
        if resp.status_code >= 400:
            print(f"  ERROR {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    company = get("/settings/company")
    print(f"Company: state={company.get('state')!r} state_code={company.get('state_code')}")

    vendors = get("/vendors", search="Bright Toys")["items"]
    if not vendors:
        print("FAIL: vendor 'Bright Toys' not found")
        sys.exit(1)
    tn_vendor = get(f"/vendors/{vendors[0]['id']}")
    print(f"TN vendor: {tn_vendor['trade_name']} gstin={tn_vendor['gstin']} "
          f"state={tn_vendor['state']!r} state_code={tn_vendor['state_code']}")

    warehouses = get("/warehouses")
    wh_items = warehouses.get("items", warehouses) if isinstance(warehouses, dict) else warehouses
    wh = next((w for w in wh_items if w.get("is_active", True)), None)
    print(f"Warehouse: {wh['name']} state={wh.get('state')!r} state_code={wh.get('state_code')}")

    products = get("/products", page=1, page_size=5)["items"]
    if not products:
        print("FAIL: no products to purchase")
        sys.exit(1)
    prod = get(f"/products/{products[0]['id']}")
    hsn = prod.get("hsn_code") or "9503"
    print(f"Product: {prod['part_code']} hsn={hsn}")

    item = {"product_id": prod["id"], "quantity": "1", "unit_cost": "100.00",
            "gst_percent": str(prod.get("gst_percent") or 18), "hsn_code": hsn}

    print("\n-- Test 1: purchase from TN vendor (expect cgst_sgst) --")
    p1 = create_purchase({
        "vendor_id": tn_vendor["id"], "warehouse_id": wh["id"],
        "vendor_invoice_number": f"GSTFIX-TN-{TODAY}",
        "invoice_date": TODAY, "items": [item],
    })
    print(f"  {p1['vendor_invoice_number']}: gst_type={p1['gst_type']} "
          f"cgst={p1['total_cgst']} sgst={p1['total_sgst']} igst={p1['total_igst']}")
    ok1 = p1["gst_type"] == "cgst_sgst" and float(p1["total_igst"]) == 0

    print("\n-- Test 2: purchase from out-of-state vendor (expect igst) --")
    oos = get("/vendors", search="29AABCT1332L1ZU")["items"]
    if oos:
        oos_vendor = oos[0]
    else:
        oos_vendor = post("/vendors", {
            "trade_name": "KA Test Supplier (GST fix verify)",
            "gstin": "29AABCT1332L1ZU", "state": "Karnataka",
        })
    print(f"  OOS vendor: {oos_vendor['trade_name']} state_code={oos_vendor.get('state_code')}")
    p2 = create_purchase({
        "vendor_id": oos_vendor["id"], "warehouse_id": wh["id"],
        "vendor_invoice_number": f"GSTFIX-KA-{TODAY}",
        "invoice_date": TODAY, "items": [item],
    })
    print(f"  {p2['vendor_invoice_number']}: gst_type={p2['gst_type']} "
          f"cgst={p2['total_cgst']} sgst={p2['total_sgst']} igst={p2['total_igst']}")
    ok2 = p2["gst_type"] == "igst" and float(p2["total_cgst"]) == 0

    print(f"\nTest 1 (TN intra-state -> cgst_sgst): {'PASS' if ok1 else 'FAIL'}")
    print(f"Test 2 (KA inter-state -> igst):      {'PASS' if ok2 else 'FAIL'}")
    sys.exit(0 if (ok1 and ok2) else 1)


if __name__ == "__main__":
    main()
