"""Smoke test for the bulk CSV importers (customers, vendors, products).

Run against a live backend (uvicorn :8000) seeded with admin/Admin@1234.
Creates clearly-tagged 'ZZIMPORT' test records; safe to deactivate afterward.
"""
import io
import requests

BASE = "http://localhost:8000/api/v1"
S = requests.Session()


def login():
    r = S.post(f"{BASE}/auth/login", json={"username": "admin", "password": "Admin@1234"})
    r.raise_for_status()
    S.headers["Authorization"] = f"Bearer {r.json()['access_token']}"


def upload(path, csv_text):
    files = {"file": ("test.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    return S.post(f"{BASE}{path}", files=files)


def template(path):
    r = S.get(f"{BASE}{path}")
    return r.status_code, (r.text.splitlines()[0] if r.text else "")


def show(name, r):
    print(f"\n=== {name} -> HTTP {r.status_code}")
    if r.status_code >= 400:
        print("  ERROR:", r.text[:300]); return
    d = r.json()
    print(f"  total={d['total_rows']} created={d['success_count']} "
          f"skipped={d.get('skipped_count')} failed={d['error_count']}")
    for s in d.get("skipped", []):
        print(f"    skip row {s['row']} ({s['data']}): {s['reason']}")
    for e in d.get("errors", []):
        print(f"    err  row {e['row']} ({e['data']}): {e['errors']}")


login()
print("templates:",
      template("/customers/import/template"),
      template("/vendors/import/template"),
      template("/products/template/csv"))

# ── Customers: 1 valid+address, 1 dup GSTIN, 1 bad is_b2b ──
cust = (
    "trade_name,legal_name,gstin,gst_status,is_b2b,phone,email,contact_person,credit_limit,credit_days,state,addr_label,address_line1,address_line2,city,addr_state,pincode\n"
    "ZZIMPORT Cust A,,29ABCDE9999F1Z5,Registered,TRUE,9990001111,a@zz.com,Ravi,50000,30,Karnataka,Billing,1 Test St,,Bengaluru,Karnataka,560001\n"
    "ZZIMPORT Cust Dup,,29ABCDE9999F1Z5,Registered,TRUE,,,,,,Karnataka,,,,,,\n"
    "ZZIMPORT Cust Bad,,,,notabool,,,,,,,,,,,,\n"
)
show("customers import (run 1)", upload("/customers/import", cust))
show("customers import (run 2 - all dup/exist)", upload("/customers/import", cust))

# ── Vendors: 1 valid, 1 invalid GSTIN, 1 dup ──
vend = (
    "trade_name,legal_name,gstin,gst_status,phone,email,contact_person,credit_days,bank_name,bank_account,bank_ifsc,state,addr_label,address_line1,address_line2,city,addr_state,pincode\n"
    "ZZIMPORT Vend A,,27FGHIJ9999K1Z2,Registered,9820011111,v@zz.com,Meera,45,HDFC,500111,HDFC0000123,Maharashtra,Office,8 Estate,,Mumbai,Maharashtra,400001\n"
    "ZZIMPORT Vend BadGST,,12BADGSTIN,Registered,,,,,,,,,,,,,,\n"
    "ZZIMPORT Vend Dup,,27FGHIJ9999K1Z2,Registered,,,,,,,,,,,,,,\n"
)
show("vendors import (run 1)", upload("/vendors/import", vend))

# ── Products: auto-create category 'ZZT', 1 valid, dup, bad price order ──
prod = (
    "part_name,category_prefix,category_name,hsn_code,gst_percent,purchase_cost,b2b_price,b2c_price,mrp,floor_price,unit_of_measure,low_stock_threshold,description\n"
    "ZZIMPORT Widget,ZZT,ZZ Test Cat,95030090,18,100,150,180,220,120,Nos,5,test\n"
    "ZZIMPORT Widget,ZZT,ZZ Test Cat,95030090,18,100,150,180,220,120,Nos,5,dup row\n"
    "ZZIMPORT BadPrice,ZZT,ZZ Test Cat,,18,200,150,180,220,120,Nos,5,floor below cost? no - b2b<cost\n"
)
show("products import (run 1)", upload("/products/bulk-upload", prod))
show("products import (run 2 - dup)", upload("/products/bulk-upload", prod))
print("\nDONE. Test records are tagged 'ZZIMPORT' / category prefix 'ZZT'.")
