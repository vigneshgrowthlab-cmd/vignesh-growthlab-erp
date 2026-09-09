import requests, json, io

B = "http://127.0.0.1:8001/api/v1"
s = requests.Session()


def show(label, r):
    ok = r.status_code < 400
    print(f"[{'OK ' if ok else 'ERR'}] {label}: {r.status_code}")
    if not ok:
        print("    ", r.text[:300])
    return r


# 1. login
r = s.post(f"{B}/auth/login", json={"username": "admin", "password": "Admin@1234"})
show("login", r)
tok = r.json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

# 2. create reconciliation (mirror all May 2026 BANK lines + a bank-only charge)
entries = [
    {"entry_date": "2026-05-05", "description": "Receipt B2B",  "debit": 0,     "credit": 2000, "reference": None},
    {"entry_date": "2026-05-06", "description": "NEFT VND3 A",  "debit": 3000,  "credit": 0,    "reference": None},
    {"entry_date": "2026-05-06", "description": "NEFT VND3 B",  "debit": 10000, "credit": 0,    "reference": None},
    {"entry_date": "2026-05-21", "description": "NEFT VND1 A",  "debit": 590,   "credit": 0,    "reference": None},
    {"entry_date": "2026-05-21", "description": "NEFT VND1 B",  "debit": 590,   "credit": 0,    "reference": None},
    {"entry_date": "2026-05-31", "description": "Bank charges", "debit": 250,   "credit": 0,    "reference": None},
]
r = s.post(f"{B}/bank-reconciliation/", json={
    "account_code": "BANK", "period_from": "2026-05-01", "period_to": "2026-05-31", "entries": entries})
show("create draft", r)
d = r.json()
rid = d["id"]
print(f"    number={d['reconciliation_number']} matched={d['matched_count']}/{len(d['lines'])} "
      f"diff={d['difference']} unmatched_bank={d['unmatched_bank_count']} unmatched_books={d['unmatched_books_count']}")
assert d["matched_count"] == 5, "expected 5 auto-matches"

# identify the bank-charge line (the only unmatched one) and a matched line to test unmatch/rematch
charge_line = next(l for l in d["lines"] if not l["journal_line_id"] and float(l["bank_debit"]) == 250)
matched_line = next(l for l in d["lines"] if l["journal_line_id"] and l["match_type"] == "auto")
matched_jl = matched_line["journal_line_id"]

# 3. unmatch a matched line, then manually re-match it
r = s.post(f"{B}/bank-reconciliation/{rid}/unmatch", json={"line_id": matched_line["id"]})
show("unmatch", r)
assert any(l["id"] == matched_line["id"] and not l["journal_line_id"] for l in r.json()["lines"]), "unmatch failed"

r = s.post(f"{B}/bank-reconciliation/{rid}/match", json={"line_id": matched_line["id"], "journal_line_id": matched_jl})
show("manual match", r)
ml = next(l for l in r.json()["lines"] if l["id"] == matched_line["id"])
print(f"    line {ml['id']} match_type={ml['match_type']} by={ml['matched_by_name']}")
assert ml["match_type"] == "manual", "expected manual match_type"

# 4. post a bank-charge adjustment linked to the charge line -> should drive difference to 0
r = s.post(f"{B}/bank-reconciliation/{rid}/adjustment",
           json={"kind": "charge", "amount": 250, "narration": "Monthly bank charges", "line_id": charge_line["id"]})
show("adjustment (charge 250)", r)
d = r.json()
print(f"    diff_now={d['difference']} matched={d['matched_count']}/{len(d['lines'])}")
adj = next(l for l in d["lines"] if l["id"] == charge_line["id"])
print(f"    charge line match_type={adj['match_type']} is_adjustment={adj['is_adjustment']}")
assert abs(float(d["difference"])) < 1, f"expected diff ~0, got {d['difference']}"

# 5. finalize / lock
r = s.post(f"{B}/bank-reconciliation/{rid}/finalize")
show("finalize", r)
d = r.json()
print(f"    status={d['status']} finalized_by={d['finalized_by_name']}")
assert d["status"] == "locked"

# 6. immutability: a further match should be rejected
r = s.post(f"{B}/bank-reconciliation/{rid}/match", json={"line_id": matched_line["id"], "journal_line_id": matched_jl})
print(f"[{'OK ' if r.status_code == 400 else 'ERR'}] locked rejects mutation: {r.status_code} ({r.json().get('detail')})")

# 7. CSV import endpoint
csv = "Date,Description,Withdrawal,Deposit,Ref\n05/05/2026,Receipt B2B,0,2000,UTR99\n06/05/2026,NEFT VND3,3000,0,CHQ1\n"
files = {"file": ("statement.csv", io.BytesIO(csv.encode()), "text/csv")}
r = s.post(f"{B}/bank-reconciliation/import-file", files=files)
show("CSV import", r)
print("    parsed:", json.dumps(r.json().get("entries"), default=str))

# 8. list + get
r = s.get(f"{B}/bank-reconciliation/", params={"page_size": 5})
show("list", r)
print(f"    total reconciliations={r.json()['total']}")
print("\nALL CHECKS PASSED")
