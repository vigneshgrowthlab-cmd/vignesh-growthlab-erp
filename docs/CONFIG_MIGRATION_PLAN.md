# Configuration-Driven Parameter System — Migration Plan

**Status:** PLAN ONLY — no code changed.
**Scope:** Convert every regulation-, policy-, or strategy-sensitive hardcoded value into an effective-dated, versioned, configuration-driven model that can be added, modified, activated, expired, or removed **without code changes**.
**Current Alembic head:** `c5d6e7f8a9b0` (`20260607b_widen_category_prefix.py`). New migrations chain from here.

> **Constraints honoured:** Never break APIs · Add migrations for every DB change · Maintain backward compatibility · No assumptions baked as silent breaking changes — every call-site swap keeps the current value as the fallback default.

---

## 1. The core problem

Regulation-sensitive values are scattered across three layers, each with a different failure mode when the law changes:

| Layer | Example | Failure mode on change |
|---|---|---|
| `app/core/config.py` (env constants) | `EWAY_BILL_THRESHOLD`, `HSN_MIN_DIGITS` | Requires redeploy + restart; **no history** — old invoices recompute with the new value |
| `models.py` column `default=` | `gst_percent default=18`, `margin_percent default=25` | New rows only; change needs a migration + code edit |
| Literal in service/util code | GST slabs, TDS section `194C`, aging buckets `30/60/90`, e-way `200 km`, IRN `24h` | Requires code edit + redeploy; **no audit, no effective date** |

The single most important defect is **temporal incorrectness**: today every calculation reads "the current value." A GST rate change on 1-Oct must NOT alter a 15-Sep invoice when it is reprinted or amended. The target system resolves every value **as of the transaction date**, not "now."

---

## 2. Target architecture

Three building blocks, layered so nothing breaks during rollout.

### 2.1 Generic temporal parameter store (scalar values)
For single-value parameters (thresholds, limits, toggles, percentages, durations).

```
config_definitions   — the catalog: what CAN be configured (metadata, validation, ownership domain)
config_values        — effective-dated, versioned actual values (the temporal table)
```

### 2.2 Structured masters (multi-column / slab / list data)
A scalar row cannot model a rate slab table, a TDS section list, or a status-transition matrix. These get **purpose-built effective-dated tables** that share the same temporal columns (`effective_from`, `effective_to`, `version`, `status`, `regulatory_reference`).

### 2.3 Resolution service + fallback
A single `ConfigService` (and typed structured-master services) that every endpoint/service calls **instead of** reading `settings.X` or a literal. The resolver always accepts an `as_of` date and a `default`:

```
ConfigService.get_decimal("gst.eway_bill_threshold", as_of=invoice.invoice_date,
                          default=settings.EWAY_BILL_THRESHOLD)
```

If no DB row matches, it returns the `default` (= today's behaviour). **This is what makes every phase backward-compatible**: tables can ship empty and the app behaves identically until a value is seeded.

---

## 3. Schema design

### 3.1 `config_definitions` (the catalog)

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `config_key` | VARCHAR(120) UNIQUE | dotted, e.g. `gst.eway_bill_threshold` |
| `domain` | VARCHAR(30) | `GST` · `INCOME_TAX` · `RBI` · `DPDP` · `STATE` · `COMPANY` · `BUSINESS` |
| `data_type` | VARCHAR(20) | `decimal` · `int` · `bool` · `string` · `json` |
| `unit` | VARCHAR(20) | `INR` · `percent` · `days` · `hours` · `km` · `digits` |
| `scope_type` | VARCHAR(30) | `global` · `state` · `customer_type` · `product_category` · `warehouse` · `doc_type` |
| `validation_json` | JSON | min/max/enum/regex for admin-UI validation |
| `description` | TEXT | human label + regulatory source |
| `is_regulatory` | BOOL | true = change is law-driven (needs `regulatory_reference`) |
| `owner_role` | VARCHAR(30) | who may edit (`super_admin`, `accountant`) |

### 3.2 `config_values` (temporal, versioned)

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `config_key` | VARCHAR(120) | FK → `config_definitions.config_key` |
| `scope_value` | VARCHAR(60) NULL | e.g. state code `29`; NULL for global |
| `value_json` | JSON | canonical typed value (`{"v": 50000}`) |
| `value_numeric` | DECIMAL(18,4) NULL | mirror of numeric value for indexed range queries |
| `effective_from` | DATE NOT NULL | inclusive |
| `effective_to` | DATE NULL | inclusive; NULL = open-ended |
| `version` | INT NOT NULL | per (`config_key`,`scope_value`), increments |
| `status` | VARCHAR(15) | `draft` · `scheduled` · `active` · `expired` · `superseded` · `revoked` |
| `regulatory_reference` | VARCHAR(200) NULL | notification / circular / act-section |
| `note` | VARCHAR(500) NULL | |
| `created_by` / `created_at` | | |
| `approved_by` / `approved_at` | NULL | maker-checker |

**Indexes:** `(config_key, scope_value, effective_from)`, `(config_key, status)`.

**Resolution query (as-of):**
```
SELECT value_json FROM config_values
WHERE config_key = :key AND (scope_value = :scope OR scope_value IS NULL)
  AND status = 'active'
  AND effective_from <= :as_of
  AND (effective_to IS NULL OR effective_to >= :as_of)
ORDER BY (scope_value IS NULL), effective_from DESC, version DESC
LIMIT 1;
```
(Scoped value wins over global; latest effective wins over older.)

**Lifecycle without code changes:**
- **Add** → insert `draft`, then `active`/`scheduled`.
- **Modify** → insert new `version` row; set prior row `effective_to = new.effective_from - 1 day`, `status='superseded'`.
- **Activate** → `status='active'` (or scheduler flips `scheduled`→`active` on `effective_from`).
- **Expire** → set `effective_to` (past) and `status='expired'`.
- **Remove** → `status='revoked'` (kept for audit; never hard-deleted).

Overlap prevention (one active row per key+scope+date) is enforced in the service layer (MariaDB lacks range-exclusion constraints).

### 3.3 Structured masters (share the temporal columns above)

| Table | Replaces hardcode | Key columns (beyond temporal) |
|---|---|---|
| `gst_rate_master` | slab set `{0,5,12,18,28,…}`, `settings.py` gst-rates endpoint | `rate`, `label`, `cess_rate`, `applies_to` |
| `hsn_gst_mapping` | per-product `gst_percent default=18` | `hsn_code`, `gst_rate`, `cess_rate`, `description` |
| `tds_section_master` | `section_code default="194C"`, no rate validation | `section_code`, `rate`, `threshold_single`, `threshold_annual`, `deductee_type` |
| `tcs_section_master` | **absent today** (206C(1H) not implemented) | `section_code`, `rate`, `threshold`, `applies_above_turnover` |
| `cess_master` | **absent today** (cess assumed 0) | `hsn_code`/`category`, `cess_rate`, `cess_type` |
| `state_master` | states list hardcoded in `settings.py:198-236`; `VALID_STATE_CODES` | `state_code`, `name`, `is_ut`, `gst_state_code` |
| `uqc_master` | `UQC_MAP` in `irp_validation.py:35-57` | `unit_text`, `uqc_code` |
| `document_number_format` | `_DEFAULT_PREFIXES`, prefix columns, JE/PO/VP/ADJ/WO formats | `doc_type`, `prefix`, `pattern`, `padding`, `reset_basis` |
| `workflow_status_master` | status enums (DC, writeoff, expense, cheque, einvoice, eway…) | `entity`, `status_code`, `label`, `is_terminal`, `sort_order` |
| `workflow_transition_master` | implicit transitions scattered in services | `entity`, `from_status`, `to_status`, `required_role` |
| `aging_bucket_master` | `30/60/90` + weights `1/2/3/5` in `accounting_service.py:582-597` | `seq`, `from_days`, `to_days`, `weight` |
| `chart_of_account_map` | `_ACCOUNT_TYPE_MAP` in `helpers.py:201-220` | `code`, `account_type`, `default_name`, `parent_code` |
| `einvoice_rule` | IRN `24h`, e-way `200 km`/`23:59`, reason codes, transport modes, version strings | (modelled as `config_values` json rows under domain `GST`) |
| `security_policy` | token expiry, lockout, password rules, OTP, session window | (modelled as `config_values` under domain `DPDP`) |
| `data_retention_policy` | **absent** — DPDP gap | `entity`, `retention_days`, `purge_action`, `legal_basis` |
| `consent_master` / `consent_record` | **absent** — DPDP gap | purpose, version, granted/withdrawn timestamps, data-principal id |
| `erasure_request` | **absent** — DPDP right-to-erasure | `subject_type`, `subject_id`, `status`, `requested_at`, `completed_at` |

---

## 4. Per-item register

For each item: **(1)** current implementation · **(2)** hardcoded value · **(3)** risk if law changes · **(4)** recommended config model · **(5)** DB schema · **(6)** effective-date support · **(7)** versioning · **(8)** backward-compat impact.

Legend for (4): **CV** = `config_values` scalar · **SM** = structured master.

### 4.1 GST / E-Invoice / E-Way (domain `GST`) — highest regulatory churn

| # | Item | (1) Current | (2) Value | (3) Risk if law changes | (4) Model | (5) Schema | (6) Eff-date | (7) Version | (8) Backward-compat |
|---|---|---|---|---|---|---|---|---|---|
| G1 | GST rate slabs | literal set `irp_validation.py:29`; endpoint `settings.py:185` | `{0,0.1,0.25,1,1.5,3,5,6,7.5,12,18,28}` | Council adds/removes a slab → IRP validation rejects valid invoices | SM | `gst_rate_master` | **Required** — slab changes are dated | **Required** | Resolver lists from table; seed = current set → identical |
| G2 | Product/HSN GST % | `models.py:210 default=18`; per-product col | `18` | Rate revision per HSN must apply by date, not overwrite history | SM | `hsn_gst_mapping` (+ keep product col as override) | **Required** — invoice uses rate as-of invoice date | **Required** | Product col stays; resolver fills when blank |
| G3 | Cess | **not implemented**; assumed `0` | `0` | New/!changed cess (autos, coal, tobacco) → under-collection, wrong returns | SM | `cess_master` + line `cess_amount` col | **Required** | **Required** | Default 0 = today's behaviour |
| G4 | E-Way threshold | `config.py:43`; `gst_service.py:486` | `₹50,000` | Threshold revision → wrong block/allow of e-way | CV `gst.eway_bill_threshold` | `config_values` | **Required** | **Required** | `default=settings.EWAY_BILL_THRESHOLD` |
| G5 | GSTR-1 B2CL threshold | `config.py:46`; `gst_service.py:763,1033` | `₹2,50,000` | Reclassification of B2CL/B2CS tables → filing errors | CV `gst.gstr1_b2cl_threshold` | `config_values` | **Required** | **Required** | fallback to config |
| G6 | HSN min digits | `config.py:50`; `irp_validation.py:161` | `6` | Turnover-band rule change → e-invoice rejected/over-strict | CV `gst.hsn_min_digits` | `config_values` | **Required** | Recommended | fallback to config |
| G7 | IRN cancellation window | literal `gst_service.py:344`, `billing_service.py:994` | `24h` | NIC changes window → wrong block on cancel | CV `gst.irn_cancel_window_hours` | `config_values` | **Required** | Recommended | fallback literal |
| G8 | E-Way validity per distance | `gst_service.py:459` | `1 day / 200 km`, ends `23:59` | NIC distance-rule revision → wrong validity | CV `gst.eway_km_per_day` + `gst.eway_day_cutoff` | `config_values` | **Required** | Recommended | fallback literal |
| G9 | IRN cancel reason codes | `gst_service.py:350` | `1,2,3,4` | NIC adds codes | SM (small) or CV json | `config_values` json | Optional | Optional | fallback literal |
| G10 | UQC map | `irp_validation.py:35-57` | ~40 unit→code | GSTN master additions | SM | `uqc_master` | Optional | Optional | seed = current map |
| G11 | State codes / list | `settings.py:198`; `irp_validation.py:32` | `1-38 + {96,97,99}` | New state/UT or code reassignment | SM | `state_master` | **Required** (rare) | Recommended | seed = current list |
| G12 | GSTIN regex | `irp_validation.py:21` | regex | Format stable; very low risk | CV `gst.gstin_regex` (string) | `config_values` | Optional | Optional | fallback literal |
| G13 | GSTR-1 JSON version | `gst_service.py:1078` | `"GST3.1.4"` | GSTN schema bump → portal rejects upload | CV `gst.gstr1_json_version` | `config_values` | **Required** | **Required** | fallback literal |
| G14 | Reverse charge flag | hardcoded `"N"` `gst_service.py:1003,1027` | `N` | RCM supply types unsupported → wrong returns | SM flag on customer/category + CV | per-entity col + `config_values` | **Required** | Recommended | default N |
| G15 | Composition scheme | **not implemented** | — | No composition reporting path | new `dealer_type` col + CV | col + `config_values` | **Required** | Recommended | default = regular |
| G16 | Rupee rounding policy | `billing_service.py:119` ROUND_HALF_UP, nearest ₹1 | nearest rupee | Statutory; very low risk | CV `gst.invoice_rounding` (json) | `config_values` | Optional | Optional | fallback literal |

### 4.2 Income Tax / Accounting (domain `INCOME_TAX`)

| # | Item | (1) Current | (2) Value | (3) Risk | (4) | (5) | (6) | (7) | (8) |
|---|---|---|---|---|---|---|---|---|---|
| I1 | TDS section + rate | `models.py:471 default="194C"`; no rate validation | `194C`, free % | Rate/threshold change, wrong default → wrong deduction | SM | `tds_section_master` | **Required** | **Required** | default 194C; resolver validates rate |
| I2 | TCS 206C(1H) | **not implemented** | — | ₹5cr+ sellers must collect 0.1% → non-compliance | SM | `tcs_section_master` + invoice `tcs_amount` | **Required** | **Required** | absent today; additive |
| I3 | Financial-year start month | `config.py:34`; `models.py:1026`; `helpers.py:7` | `4` (April) | Statutory FY change cascades all FY stamping | CV `company.fy_start_month` | `config_values` | **Required** | **Required** | fallback to config |
| I4 | Expense approval threshold | `config.py:53`; `accounting_service.py:348` | `₹5,000` | Policy change | CV `company.expense_approval_threshold` | `config_values` | **Required** | Recommended | fallback to config |
| I5 | Aging buckets + weights | `accounting_service.py:582-597` | `30/60/90`, `1/2/3/5` | Policy/board reporting change | SM | `aging_bucket_master` | Recommended | Recommended | seed = current |
| I6 | Chart-of-accounts map | `helpers.py:201-220`; `seed.py` | 18 codes | New statutory ledgers / sub-accounts | SM | `chart_of_account_map` | Optional | Optional | seed = current map |
| I7 | Payment-mode → account | `accounting_service.py:420` cash/bank only | 2-way | UPI/NEFT/RTGS distinct ledgers wanted | SM | extend `chart_of_account_map` by mode | Optional | Optional | default keeps cash/bank |
| I8 | Currency/qty decimal scale | `Numeric(12,2)`/`(14,2)`/`(12,3)` widespread | 2 / 3 dp | Very low; structural | **No CV** — document only | n/a | n/a | n/a | leave as-is |
| I9 | Form-26AS default section | `accounting_service.py:523` | `194C` | Same as I1 | SM (shared) | `tds_section_master` | **Required** | **Required** | default preserved |

### 4.3 RBI / Banking (domain `RBI`)

| # | Item | (1) Current | (2) Value | (3) Risk | (4) | (5) | (6) | (7) | (8) |
|---|---|---|---|---|---|---|---|---|---|
| R1 | Bank stock margin | `models.py:939,1025`; `schemas/bank.py:12`; `bank_service.py:94` | `25%` | Bank/RBI drawing-power norm change | CV `rbi.bank_stock_margin` (+ per-statement override col stays) | `config_values` | **Required** | **Required** | per-statement col + fallback |
| R2 | Default credit days | `config.py:55`; `models.py:527,589` | `30` (col default `0`) | Policy change | CV `company.credit_days_default` | `config_values` | **Required** | Recommended | fallback to config |
| R3 | Recon amount tolerance | `bank_recon_service.py:17`; `bank_service.py:202` | `₹1` | Policy change | CV `rbi.recon_amount_tolerance` | `config_values` | Optional | Optional | fallback literal |
| R4 | Recon date window | `bank_recon_service.py:153` | `±2 days` | Policy change | CV `rbi.recon_date_window_days` | `config_values` | Optional | Optional | fallback literal |
| R5 | PDC alert window | `accounting_service.py:174` | `7 days` | Policy | CV `company.pdc_alert_days` | `config_values` | Optional | Optional | fallback literal |
| R6 | Large-invoice alert | `bank_service.py:247` | `₹1,00,000` | Policy | CV `company.large_invoice_alert` | `config_values` | Optional | Optional | fallback literal |
| R7 | Cash transaction limit | **not implemented** (269ST ₹2L) | — | 269ST non-compliance not flagged | CV `rbi.cash_txn_limit` | `config_values` | **Required** | **Required** | additive; warn-only |
| R8 | Overdue/penal interest | **not implemented** | — | No penal-interest capability | CV `rbi.overdue_interest_pct` + calc | `config_values` | **Required** | **Required** | additive |
| R9 | Cheque bounce charges | `models.py:415 default=0` | `0` | Policy | CV `company.cheque_bounce_charge` | `config_values` | Optional | Optional | default 0 |

### 4.4 DPDP / Security (domain `DPDP`)

| # | Item | (1) Current | (2) Value | (3) Risk | (4) | (5) | (6) | (7) | (8) |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Access token TTL | `config.py:13` (`.env`=15) | `60 min` | Policy/audit | CV `dpdp.access_token_minutes` | `config_values` | Optional | Recommended | fallback to config |
| D2 | Refresh token TTL | `config.py:14` | `7 days` | Policy | CV `dpdp.refresh_token_days` | `config_values` | Optional | Recommended | fallback to config |
| D3 | Max login attempts | `config.py:56`; `auth.py:51` | `5` | Policy | CV `dpdp.max_login_attempts` | `config_values` | Optional | Recommended | fallback to config |
| D4 | Lockout minutes | `config.py:57`; `auth.py:53` | `15` | Policy | CV `dpdp.lockout_minutes` | `config_values` | Optional | Recommended | fallback to config |
| D5 | Password rules | `security.py:141` min-len only | `min 8`, no complexity | DPDP "reasonable security safeguards" | CV `dpdp.password_policy` (json) | `config_values` | Optional | **Required** | default = len≥8 |
| D6 | Bcrypt rounds | implicit default 12 `security.py:17` | `12` | Crypto-agility | CV `dpdp.bcrypt_rounds` | `config_values` | Optional | Recommended | default 12 |
| D7 | OTP length / TTL | `security_service.py:525,529` | `6 digits / 10 min` | Policy | CV `dpdp.otp_length`,`dpdp.otp_ttl_minutes` | `config_values` | Optional | Optional | fallback literal |
| D8 | Suspicious-activity thresholds | `security_service.py:391,410` | `3 logins / 5 exports / 24h` | Policy | CV under `dpdp.*` | `config_values` | Optional | Optional | fallback literal |
| D9 | **Data retention** | **absent** — logs kept forever | none | **DPDP storage-limitation breach** | SM | `data_retention_policy` + purge job | **Required** | **Required** | new; opt-in per entity |
| D10 | **Consent records** | **absent** | none | **DPDP §6/§7 breach** | SM | `consent_master` / `consent_record` | **Required** | **Required** | new; additive |
| D11 | **Right to erasure** | **absent** | none | **DPDP data-principal right** | SM | `erasure_request` + soft/hard delete flow | **Required** | **Required** | new; additive |
| D12 | Audit-log immutability/TTL | `audit.py` no TTL, deletable | none | DPDP + audit integrity | SM (shared D9) | `data_retention_policy` | **Required** | **Required** | new |

### 4.5 Company / Business strategy (domain `COMPANY` / `BUSINESS`)

| # | Item | (1) Current | (2) Value | (3) Risk | (4) | (5) | (6) | (7) | (8) |
|---|---|---|---|---|---|---|---|---|---|
| B1 | Document prefixes | `_DEFAULT_PREFIXES` `billing_service.py:61`; `CompanySettings` cols | `BINV/CINV/QT/DC/CN` | Rebrand / format policy | SM | `document_number_format` (CompanySettings cols stay) | **Required** (per FY) | Recommended | cols + fallback dict |
| B2 | JE/PO/VP/ADJ/WO formats | literals across services | `JE-…-00001` etc | Format change needs code edit today | SM (shared B1) | `document_number_format` | **Required** | Recommended | seed = current patterns |
| B3 | Status enums (all entities) | enums + string defaults in `models.py` | DC/writeoff/expense/cheque/einvoice/eway/cash/quotation | New workflow states / labels | SM | `workflow_status_master` | Optional | Recommended | seed = current enums; code keeps enum guard |
| B4 | Status transitions | implicit in service methods | scattered | Policy/approval-matrix change | SM | `workflow_transition_master` | Optional | Recommended | advisory first, enforce later |
| B5 | Default GST % (product) | `models.py:210` | `18` | see G2 | SM (G2) | `hsn_gst_mapping` | — | — | — |
| B6 | Low-stock threshold default | `config.py:54`; `models.py:217` | `10` (col `0`) | Strategy | CV `business.low_stock_default` | `config_values` | Optional | Optional | per-product col + fallback |
| B7 | Cost-alert % | `models.py:221` | `5%` | Strategy | CV `business.cost_alert_pct` (+ col override) | `config_values` | Optional | Optional | col + fallback |
| B8 | Min margin % | `models.py:222`; `price_history_service.py:189` | `10%` | Strategy/pricing | CV `business.min_margin_pct` (+ col override) | `config_values` | Optional | Recommended | col + fallback |
| B9 | Price-tier ordering rule | `product_service.py:108` `floor≤b2b≤b2c≤mrp` | rule | Strategy | CV `business.price_tier_rule` (json) | `config_values` | Optional | Optional | fallback literal |
| B10 | Customer credit limit | `models.py:588 default=0` | `0` | Strategy | per-customer col (already) + CV default | `config_values` | Optional | Optional | unchanged |
| B11 | IST timezone for price activation | `price_history_service.py` `+05:30` | `+05:30` | None (India) | document only | n/a | n/a | n/a | leave |
| B12 | Default user role | `models.py:120` | `sales` | Policy | CV `company.default_user_role` | `config_values` | Optional | Optional | fallback literal |
| B13 | Notification toggles / SMTP | `bank_service.py:243-250` | gmail:587, flags true | Ops policy | CV `company.notifications` (json) | `config_values` | Optional | Optional | fallback literal |

---

## 5. Migration plan (phased)

Each phase = **(a)** Alembic migration(s) for new tables + idempotent seed/backfill, **(b)** `ConfigService`/master-service additions, **(c)** call-site swaps (literal → resolver with current value as `default`). No API contract changes; all routes keep request/response shapes. After every phase the app behaves identically until an admin seeds a new value.

> Auto-migrate caveat: `_auto_migrate()` in `main.py` silently patches schema on boot. Each migration below must `inspect()` for table/column existence first (matching the existing Alembic style in `20260607_add_bank_reconciliation.py`) so it is safe whether or not auto-migrate already added anything.

### Phase 0 — Foundation (no behaviour change)
- **Migration** `20260612_add_config_core.py` (down_revision `c5d6e7f8a9b0`): create `config_definitions`, `config_values` + indexes.
- **Service** `app/services/config_service.py`: `get_decimal/int/bool/string/json(key, as_of, scope, default)`, in-request memoized, falls back to `default`. Maker-checker write methods (`propose`, `approve`, `expire`, `revoke`) implementing the lifecycle in §3.2.
- **Seed** current `config.py` constants as `active`, `effective_from` = FY start, `regulatory_reference` = "baseline".
- **Acceptance:** all existing smoke scripts pass unchanged; resolver returns defaults everywhere.

### Phase 1 — GST/E-Invoice (G1–G16)
- **Migrations:** `gst_rate_master`, `hsn_gst_mapping`, `cess_master`, `state_master`, `uqc_master`; seed from current literals (`irp_validation.py`, `settings.py`). Add `config_values` rows for G4–G8, G12, G13, G16.
- **Swaps:** `gst_service.py`, `irp_validation.py`, `billing_service.py`, `settings.py` gst-rates/states endpoints read from masters/resolver with `as_of = invoice_date`.
- **New capability (additive, default-off):** cess columns on invoice/line, RCM flag, dealer_type — calculate only when data present.
- **Acceptance:** reprint a pre-seed invoice → identical totals (temporal correctness test).

### Phase 2 — Income Tax / Accounting (I1–I9)
- **Migrations:** `tds_section_master`, `tcs_section_master`, `aging_bucket_master`, `chart_of_account_map`; seed from `helpers.py`/`seed.py`/`accounting_service.py`. `config_values` for I3, I4.
- **Swaps:** TDS default + rate validation from master; aging buckets from master; COA auto-create reads `chart_of_account_map`; FY helpers read `company.fy_start_month`.
- **Acceptance:** FY stamping, aging report, expense-approval routing unchanged with seeded values.

### Phase 3 — RBI / Banking (R1–R9)
- **Migrations:** `config_values` for R1–R6, R9; new R7 cash-limit + R8 overdue-interest definitions.
- **Swaps:** `bank_service.py`, `bank_recon_service.py`, `accounting_service.py` read resolver with `as_of`.
- **Acceptance:** drawing-power, reconciliation auto-match unchanged with seeded values.

### Phase 4 — DPDP / Security (D1–D12)
- **Migrations:** `config_values` for D1–D8; new `data_retention_policy`, `consent_master`, `consent_record`, `erasure_request`. Add scheduled purge worker (config-driven; off until a policy row exists).
- **Swaps:** `security.py`, `auth.py`, `security_service.py` read resolver. New consent capture + erasure endpoints (additive routes; existing routes untouched).
- **Acceptance:** auth/lockout behaviour identical with seeded values; retention job no-op until configured.

### Phase 5 — Company / Business / Workflow (B1–B13)
- **Migrations:** `document_number_format`, `workflow_status_master`, `workflow_transition_master`; `config_values` for B6–B9, B12, B13. Seed from current enums/literals.
- **Swaps:** numbering, product defaults, notification config read from masters/resolver. Transitions: **advisory** (log violations) before enforcing.
- **Acceptance:** numbering sequences continue unbroken; status flows unchanged.

### Phase 6 — Governance & Admin UI
- Admin screens (super-admin) to add/modify/schedule/expire/revoke values with `validation_json`-driven validation, maker-checker approval, effective-date picker, and a full change-audit (reuse `audit.py`). Read-only "effective on date X" preview.

---

## 6. Cross-cutting requirements

**Effective-date support (6):** every resolver call passes the **transaction's own date** (`invoice_date`, `purchase_date`, `entry_date`) — never `today` — so historical documents recompute correctly. Reports pass the report's as-of date. This is mandatory for G1–G6, I1–I3, R1, and any value that affects posted financials.

**Versioning (7):** `version` increments per (`config_key`,`scope`); supersession sets the prior row's `effective_to` and `status='superseded'`. Full history is queryable; nothing is overwritten in place. Regulatory rows require `regulatory_reference`.

**Backward compatibility (8):**
- Every consuming call site keeps the **current value as `default`** — empty tables ⇒ identical behaviour.
- No API request/response shape changes; new endpoints (consent, erasure, config admin) are **additive**.
- `config.py` constants and `models.py` column defaults are **retained** as the last-resort fallback; the resolver layers on top. (`_auto_migrate()` is **not** expanded — all new schema goes through Alembic, per CLAUDE.md.)
- Per-entity override columns (product `gst_percent`, `min_margin_pct`; per-statement `margin_percent`; per-customer `credit_limit`) are preserved and take precedence over global config.

**Resolution precedence (highest → lowest):** per-record column override → scoped `config_value` (e.g. state) → global `config_value` → `config.py` / model default literal.

---

## 7. Risk register (top items to act on first)

| Priority | Item | Why now |
|---|---|---|
| P0 | G1/G2/G3 GST rates & cess | Highest change frequency; temporal incorrectness already a latent bug on any past rate change |
| P0 | D9/D10/D11 DPDP retention, consent, erasure | Legal non-compliance (capability absent, not just hardcoded) |
| P1 | I1/I2 TDS rates & TCS 206C(1H) | Wrong/absent deduction = statutory exposure |
| P1 | G4/G5/G6/G13 e-way, B2CL, HSN digits, JSON version | Filing/portal rejection risk on notification |
| P2 | R1/R7/R8 bank margin, cash 269ST limit, penal interest | Banking covenant + 269ST exposure |
| P3 | B-series numbering, statuses, product strategy | Operational, low legal risk |

---

## 8. Out of scope / leave hardcoded (documented, low risk)
- Decimal scales `(12,2)/(14,2)/(12,3)` — structural, statutory precision (I8).
- IST `+05:30`, April-FY arithmetic shape, GSTIN structural regex — India-fixed (B11, G12 optional).
- Rupee-rounding mechanism — statutory under GST (G16 optional).

---

## 9. Addendum — post-implementation scan findings (Phases 0–2 complete)

A fresh full-codebase scan after Phases 0–2 confirmed the register above is
comprehensive. Two items to fold in:

| ID | Item | Location | Phase | Note |
|---|---|---|---|---|
| B14 | **Cost-averaging window** `90 days` | `product_service.py:813` `timedelta(days=90)` | 5 | "Average 3-month vendor cost" window — a business-policy lever not previously catalogued. New key `business.cost_avg_window_days`. |
| R3/R4 dup | **Duplicate reconciliation thresholds** | `bank_service.py:202` (legacy `reconcile`) — a second hardcoded `Decimal("1")` + `<= 2` days, in addition to `bank_recon_service.py:17,153` | 3 | Both recon engines must be wired together or they drift. |

Also confirmed during implementation: `CREDIT_DAYS_DEFAULT` (R2) is a **dormant
constant** — defined in `config.py` but never read; the live due-date path
(`reports_service.py:154`) uses the per-customer `credit_days or 0`. Wiring a
default there would change behaviour, so R2 is left as-is (the
`company.credit_days_default` config key remains a new-customer UI default only).

---
*Plan document. Implementation tracked per-phase; see git history / working tree.*
