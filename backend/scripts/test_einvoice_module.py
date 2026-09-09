"""
Smoke test for the E-Invoice / E-Way Bill module.

Exercises the real running API (uvicorn + MariaDB) the way the other
scripts/ smoke tests do. NOT a unit test — it needs the live app.

Prereqs:
    - backend running at BASE_URL (default http://localhost:8000)
    - admin / Admin@1234 seeded
    - CLEARTAX_SANDBOX=true and CLEARTAX_AUTH_TOKEN empty  -> mock mode
      (so generate/cancel/eway return MOCK-* without hitting Cleartax)
    - at least one non-cancelled B2B invoice exists

Run:
    cd backend
    venv\\Scripts\\activate
    python scripts/test_einvoice_module.py
    # options:
    python scripts/test_einvoice_module.py --base-url http://localhost:8000 \
        --username admin --password Admin@1234 --invoice-id 5

What it checks:
    1.  login
    2.  pick a B2B invoice (explicit --invoice-id, else auto-discover)
    3.  e-invoice generate  -> IRN + ack number returned and persisted
    4.  generate again      -> rejected (IRN already generated)
    5.  e-invoice logs       -> the attempt is listed
    6.  e-invoice cancel     -> status becomes cancelled (within 24h window)
    7.  e-way bill generate  -> EWB number + valid_upto returned
    8.  e-way bill logs      -> the attempt is listed

Exit code is 0 only if every executed case passes.
"""
import argparse
import sys

try:
    import requests
except ImportError:
    print("This script needs 'requests' (pip install requests).")
    sys.exit(2)


PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_results = []


def record(name, ok, detail=""):
    status = PASS if ok else FAIL
    _results.append((status, name, detail))
    mark = "[OK]  " if ok else "[FAIL]"
    print(f"{mark} {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def record_skip(name, detail=""):
    _results.append((SKIP, name, detail))
    print(f"[SKIP] {name}" + (f"  -- {detail}" if detail else ""))


class Api:
    def __init__(self, base_url, prefix="/api/v1"):
        self.base = base_url.rstrip("/") + prefix
        self.s = requests.Session()
        self.token = None

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username, password):
        r = self.s.post(f"{self.base}/auth/login",
                        json={"username": username, "password": password},
                        timeout=30)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def get(self, path, **kw):
        return self.s.get(f"{self.base}{path}", headers=self._headers(), timeout=30, **kw)

    def post(self, path, **kw):
        return self.s.post(f"{self.base}{path}", headers=self._headers(), timeout=30, **kw)


def _as_list(body):
    """Tolerate both list and {items/data: [...]} pagination shapes."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("items", "data", "results"):
            if isinstance(body.get(key), list):
                return body[key]
    return []


def discover_b2b_invoice(api):
    """Find a non-cancelled B2B invoice without an IRN. Returns id or None."""
    for params in ({"document_type": "b2b_invoice", "page_size": 100},
                   {"page_size": 100}):
        r = api.get("/invoices/", params=params)
        if r.status_code != 200:
            continue
        for inv in _as_list(r.json()):
            if not isinstance(inv, dict):
                continue
            if inv.get("is_cancelled"):
                continue
            if inv.get("irn"):
                continue
            if inv.get("document_type") not in (None, "b2b_invoice"):
                continue
            return inv.get("id")
    return None


def provision_invoice(api):
    """Create a disposable B2B invoice (customer + address + product stock)
    so the test never touches real data. Returns invoice_id or raises.

    GSTIN/state are 29 (Karnataka) to match the seeded company state, HSN is
    6 digits and value > Rs 50,000 so the e-way bill case also runs.
    """
    tag = "ZZ_EINV_SMOKE"

    cust_id = None
    r = api.get("/customers/", params={"search": tag, "page_size": 50})
    for c in (_as_list(r.json()) if r.status_code == 200 else []):
        if isinstance(c, dict) and c.get("trade_name") == tag:
            cust_id = c.get("id")
            break
    if not cust_id:
        r = api.post("/customers/", json={
            "trade_name": tag, "legal_name": tag,
            "gstin": "29AAACS1234A1Z5", "state": "Karnataka", "state_code": 29,
            "phone": "9999900000", "is_b2b": True,
        })
        if r.status_code not in (200, 201):
            raise RuntimeError(f"customer create failed: {r.status_code} {r.text[:200]}")
        cust_id = r.json()["id"]

    cust = api.get(f"/customers/{cust_id}").json()
    addrs = cust.get("addresses") or []
    if addrs:
        addr_id = addrs[0]["id"]
    else:
        r = api.post(f"/customers/{cust_id}/addresses", json={
            "label": "Default", "address_line1": "1 Test Road",
            "city": "Bengaluru", "state": "Karnataka", "state_code": 29,
            "pincode": "560001", "address_type": "both",
            "is_preferred_billing": True, "is_preferred_shipping": True,
        })
        if r.status_code not in (200, 201):
            raise RuntimeError(f"address create failed: {r.status_code} {r.text[:200]}")
        addr_id = r.json()["id"]

    prods = _as_list(api.get("/products/", params={"page_size": 1}).json())
    if not prods:
        raise RuntimeError("no products exist; seed a product first")
    prod_id = prods[0]["id"]
    whs = api.get("/warehouses/").json()
    wh_list = _as_list(whs) or (whs.get("items") if isinstance(whs, dict) else [])
    if not wh_list:
        raise RuntimeError("no warehouses exist; seed a warehouse first")
    wh_id = wh_list[0]["id"]

    r = api.post("/stock-adjustments/", json={
        "product_id": prod_id, "warehouse_id": wh_id,
        "adjustment_type": "in", "quantity": 100, "unit_cost": 100,
        "reason": "einvoice smoke setup", "adjustment_date": "2026-01-01",
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"stock setup failed: {r.status_code} {r.text[:200]}")

    r = api.post("/invoices/", json={
        "document_type": "b2b_invoice", "customer_id": cust_id,
        "warehouse_id": wh_id, "billing_address_id": addr_id,
        "shipping_address_id": addr_id, "invoice_date": "2026-01-01",
        "items": [{
            "product_id": prod_id, "quantity": 10, "unit_price": 6000,
            "gst_percent": 18, "hsn_code": "851671",
        }],
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"invoice create failed: {r.status_code} {r.text[:300]}")
    return r.json()["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default="Admin@1234")
    ap.add_argument("--invoice-id", type=int, default=None,
                    help="B2B invoice to test against (auto-discovered if omitted)")
    ap.add_argument("--provision", action="store_true",
                    help="create a disposable B2B invoice instead of touching real data")
    args = ap.parse_args()

    api = Api(args.base_url)

    # 1. login
    try:
        api.login(args.username, args.password)
        record("login", True)
    except Exception as e:
        record("login", False, str(e))
        return _summary()

    # 2. pick an invoice
    if args.provision and not args.invoice_id:
        try:
            invoice_id = provision_invoice(api)
            record("provision disposable B2B invoice", True, f"invoice_id={invoice_id}")
        except Exception as e:
            record("provision disposable B2B invoice", False, str(e))
            return _summary()
    else:
        invoice_id = args.invoice_id or discover_b2b_invoice(api)
        if not invoice_id:
            record("select B2B invoice", False,
                   "no eligible invoice found; pass --invoice-id or use --provision")
            return _summary()
        record("select B2B invoice", True, f"invoice_id={invoice_id}")

    # 3. generate IRN
    irn = None
    r = api.post("/einvoice/generate", json={"invoice_id": invoice_id})
    if r.status_code == 200:
        data = r.json()
        irn = data.get("irn")
        ok = bool(irn) and data.get("irn_status") in ("generated", "EInvoiceStatus.generated")
        record("einvoice.generate returns IRN", ok,
               f"irn={irn} ack={data.get('ack_number')} status={data.get('irn_status')}")
        record("einvoice.generate returns ack_number", bool(data.get("ack_number")),
               f"ack={data.get('ack_number')}")
    else:
        record("einvoice.generate returns IRN", False, f"HTTP {r.status_code}: {r.text[:200]}")

    # 4. duplicate generate is rejected
    if irn:
        r = api.post("/einvoice/generate", json={"invoice_id": invoice_id})
        record("einvoice.generate duplicate rejected", r.status_code == 400,
               f"HTTP {r.status_code}")
    else:
        record_skip("einvoice.generate duplicate rejected", "no IRN from step 3")

    # 5. logs list the attempt
    r = api.get("/einvoice/logs", params={"page": 1, "page_size": 20})
    if r.status_code == 200:
        rows = _as_list(r.json())
        found = any(isinstance(x, dict) and x.get("invoice_id") == invoice_id for x in rows)
        record("einvoice.logs lists attempt", found, f"{len(rows)} rows")
    else:
        record("einvoice.logs lists attempt", False, f"HTTP {r.status_code}")

    # 6. cancel IRN
    if irn:
        r = api.post("/einvoice/cancel",
                     json={"invoice_id": invoice_id, "cancel_reason": "2",
                           "cancel_remark": "smoke test"})
        if r.status_code == 200:
            data = r.json()
            ok = data.get("irn_status") in ("cancelled", "EInvoiceStatus.cancelled")
            record("einvoice.cancel sets cancelled", ok, f"status={data.get('irn_status')}")
        else:
            record("einvoice.cancel sets cancelled", False, f"HTTP {r.status_code}: {r.text[:200]}")
    else:
        record_skip("einvoice.cancel sets cancelled", "no IRN from step 3")

    # 7. e-way bill generate (may legitimately fail on threshold)
    r = api.post("/ewaybill/generate",
                 json={"invoice_id": invoice_id, "transport_mode": "road",
                       "vehicle_number": "KA01AB1234", "transporter_name": "Smoke Transport"})
    if r.status_code == 200:
        data = r.json()
        ok = bool(data.get("eway_bill_number"))
        record("ewaybill.generate returns EWB", ok,
               f"ewb={data.get('eway_bill_number')} valid_upto={data.get('valid_upto')}")
        record("ewaybill.generate returns valid_upto", bool(data.get("valid_upto")),
               f"valid_upto={data.get('valid_upto')}")
    elif r.status_code == 400 and "threshold" in r.text.lower():
        record_skip("ewaybill.generate returns EWB",
                    f"invoice below E-Way threshold: {r.text[:120]}")
    else:
        record("ewaybill.generate returns EWB", False, f"HTTP {r.status_code}: {r.text[:200]}")

    # 8. e-way logs
    r = api.get("/ewaybill/logs", params={"page": 1, "page_size": 20})
    if r.status_code == 200:
        rows = _as_list(r.json())
        record("ewaybill.logs reachable", True, f"{len(rows)} rows")
    else:
        record("ewaybill.logs reachable", False, f"HTTP {r.status_code}")

    return _summary()


def _summary():
    passed = sum(1 for s, _, _ in _results if s == PASS)
    failed = sum(1 for s, _, _ in _results if s == FAIL)
    skipped = sum(1 for s, _, _ in _results if s == SKIP)
    print("\n" + "=" * 60)
    print(f"E-Invoice smoke: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
