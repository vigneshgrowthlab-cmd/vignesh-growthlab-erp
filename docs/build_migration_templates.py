"""Generate ready-to-fill data-migration templates (Excel workbook + stock CSV).

Headers match the live API/import field names verified in:
  - schemas/products.py (ProductCreate, CategoryCreate)
  - schemas/billing.py  (CustomerCreate, CustomerAddressCreate)
  - schemas/purchase.py (VendorCreate, VendorAddressCreate)
  - schemas/warehouse.py (WarehouseCreate, Opening* schemas)
  - services/warehouse_service.py::get_stock_csv_template (opening-stock CSV importer)
"""
import csv
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(OUT_DIR, "data-migration-templates")
os.makedirs(TPL_DIR, exist_ok=True)

FONT = "Calibri"
HDR_FILL = PatternFill("solid", fgColor="1F4E78")     # dark blue
REQ_FILL = PatternFill("solid", fgColor="FCE4D6")     # light orange = required
OPT_FILL = PatternFill("solid", fgColor="E2EFDA")     # light green = optional
SAMPLE_FONT = Font(name=FONT, italic=True, color="808080")
HDR_FONT = Font(name=FONT, bold=True, color="FFFFFF")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def make_sheet(wb, title, columns, samples):
    """columns: list of (header, 'R'|'O', note). samples: list of row lists."""
    ws = wb.create_sheet(title)
    # Row 1: headers
    for c, (hdr, req, _note) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=c, value=hdr)
        cell.font = HDR_FONT
        cell.fill = HDR_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    # Row 2: Required / Optional marker
    for c, (_hdr, req, _note) in enumerate(columns, start=1):
        label = "REQUIRED" if req == "R" else "optional"
        cell = ws.cell(row=2, column=c, value=label)
        cell.fill = REQ_FILL if req == "R" else OPT_FILL
        cell.font = Font(name=FONT, bold=(req == "R"), size=9)
        cell.alignment = Alignment(horizontal="center")
        cell.border = BORDER
    # Row 3: note / format hint
    for c, (_hdr, _req, note) in enumerate(columns, start=1):
        cell = ws.cell(row=3, column=c, value=note)
        cell.font = Font(name=FONT, size=8, color="808080", italic=True)
        cell.alignment = Alignment(horizontal="left", wrap_text=True, vertical="top")
        cell.border = BORDER
    # Sample rows (italic grey — delete before / leave; loaders skip blank rows)
    for r, row in enumerate(samples, start=4):
        for c, val in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = SAMPLE_FONT
            cell.border = BORDER
    # widths
    for c, (hdr, _r, _n) in enumerate(columns, start=1):
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = max(14, min(28, len(hdr) + 6))
    ws.freeze_panes = "A4"
    ws.row_dimensions[3].height = 42
    return ws


wb = Workbook()

# ── Instructions sheet ────────────────────────────────────────
ws = wb.active
ws.title = "READ ME FIRST"
ws.column_dimensions["A"].width = 110
lines = [
    ("Wholesale ERP — Initial Data Migration Templates", "title"),
    ("", ""),
    ("Fill the sheets IN ORDER. Each sheet's data depends on the ones before it.", "b"),
    ("", ""),
    ("LOAD ORDER", "h"),
    ("1. Categories        -> create product categories (gives each a prefix used in auto part codes)", ""),
    ("2. Warehouses        -> physical stock locations", ""),
    ("3. Products          -> item master (references a Category by name)", ""),
    ("4. Customers         -> customer master + their address", ""),
    ("5. Vendors           -> vendor master + their address", ""),
    ("6. Opening Stock     -> qty on hand per product per warehouse (THE main stock import)", ""),
    ("7. Opening Cust Bal  -> outstanding customers owe you, as on cutover date", ""),
    ("8. Opening Vend Bal  -> outstanding you owe vendors, as on cutover date", ""),
    ("9. Opening Cash/Bank -> cash in hand + bank balances on cutover date", ""),
    ("", ""),
    ("COLUMN COLOURS", "h"),
    ("   Orange 'REQUIRED' = must be filled.   Green 'optional' = leave blank to use the system default.", ""),
    ("   Row 3 of each sheet shows the format / allowed values. The grey italic rows are EXAMPLES — overwrite or delete them.", ""),
    ("", ""),
    ("KEY RULES", "h"),
    ("• Pick ONE cutover date (e.g. 2025-04-01, your FY start) and use it as opening_date everywhere.", ""),
    ("• Dates are always YYYY-MM-DD.", ""),
    ("• Money uses plain numbers, max 2 decimals (250.00). Quantity allows up to 3 decimals (12.500).", ""),
    ("• GSTIN is 15 chars (2-digit state + 10-char PAN + entity + 'Z' + checksum). Leave blank if unregistered.", ""),
    ("• HSN code must be 4, 6, or 8 digits.", ""),
    ("• Selling prices must be ordered:  floor_price <= b2b_price <= b2c_price <= mrp,  and floor_price >= purchase_cost.", ""),
    ("", ""),
    ("WHAT CAN BE BULK-UPLOADED via CSV", "h"),
    ("• Products  (sheet 3) -> Products page > 'Import CSV'. Auto-creates a missing category from", ""),
    ("    category_prefix; skips rows whose product already exists in that category.", ""),
    ("• Customers (sheet 4) -> Customers page > 'Import CSV'. Skips rows whose GSTIN already exists;", ""),
    ("    creates a billing address when address_line1 is filled.", ""),
    ("• Vendors   (sheet 5) -> Vendors page > 'Import CSV'. Same GSTIN-skip + address behaviour.", ""),
    ("• Opening Stock (sheet 6) -> Opening Balance page. A ready 'opening_stock.csv' is generated", ""),
    ("    alongside this workbook. Matches products by part_code, warehouses by name.", ""),
    ("• Still UI-only: Categories, Warehouses (few of them), and the cash/bank/customer/vendor", ""),
    ("    OPENING BALANCES (sheets 7-9) -> entered on the Opening Balance page.", ""),
    ("", ""),
    ("THE part_code CHICKEN-AND-EGG (important)", "h"),
    ("• Products get a part_code auto-generated from the category prefix (e.g. GTY1, GTY2...).", ""),
    ("• The Opening Stock importer matches rows by part_code. So load Products FIRST, then use the", ""),
    ("    Products page 'Export CSV' to read back each generated part_code, then fill sheet 6.", ""),
    ("", ""),
    ("Generated by Claude Code. Verify a few rows against the app before a full production load.", "i"),
]
r = 1
for text, style in lines:
    cell = ws.cell(row=r, column=1, value=text)
    if style == "title":
        cell.font = Font(name=FONT, bold=True, size=15, color="1F4E78")
    elif style == "h":
        cell.font = Font(name=FONT, bold=True, size=11, color="C0504D")
    elif style == "b":
        cell.font = Font(name=FONT, bold=True, size=11)
    elif style == "i":
        cell.font = Font(name=FONT, italic=True, size=9, color="808080")
    else:
        cell.font = Font(name=FONT, size=10)
    cell.alignment = Alignment(horizontal="left", vertical="center")
    r += 1

# ── 1. Categories ─────────────────────────────────────────────
make_sheet(wb, "1_Categories", [
    ("name", "R", "Category display name"),
    ("prefix", "R", "1-10 chars, UPPERCASE; used to build auto part codes"),
    ("default_hsn", "O", "4/6/8 digits; inherited by new products"),
    ("default_gst_percent", "O", "0-100; default 18"),
    ("description", "O", "free text"),
], [
    ["Toys", "GTY", "95030090", "18", "General toys"],
    ["Stationery", "STN", "4820", "12", "Notebooks, pens"],
])

# ── 2. Warehouses ─────────────────────────────────────────────
make_sheet(wb, "2_Warehouses", [
    ("name", "R", "Warehouse name (used to match opening-stock rows)"),
    ("code", "R", "1-20 chars, unique"),
    ("address", "O", "street address"),
    ("city", "O", ""),
    ("state", "O", "state name"),
    ("pincode", "O", "6 digits"),
    ("contact_person", "O", ""),
    ("phone", "O", ""),
    ("is_default", "O", "TRUE / FALSE; one default warehouse"),
], [
    ["Main Warehouse", "WH-MAIN", "12 MG Road", "Bengaluru", "Karnataka", "560001", "Ramesh", "9876543210", "TRUE"],
    ["Branch Store", "WH-BR1", "5 Park St", "Chennai", "Tamil Nadu", "600002", "Suresh", "9876500011", "FALSE"],
])

# ── 3. Products (matches the /products/bulk-upload importer) ───
make_sheet(wb, "3_Products", [
    ("part_name", "R", "item name"),
    ("category_prefix", "R", "matches a category prefix (e.g. GTY); auto-created if new"),
    ("category_name", "O", "name used only when the prefix is auto-created"),
    ("hsn_code", "R", "4/6/8 digits"),
    ("gst_percent", "R", "0-100"),
    ("purchase_cost", "R", "money"),
    ("b2b_price", "R", ">= floor_price"),
    ("b2c_price", "O", ">= b2b_price"),
    ("mrp", "O", ">= b2c_price"),
    ("floor_price", "R", ">= purchase_cost"),
    ("unit_of_measure", "O", "e.g. Nos, Kg, Box; default Nos"),
    ("low_stock_threshold", "O", "qty; alert level"),
    ("description", "O", ""),
], [
    ["Wooden Car", "GTY", "Toys", "95030090", "18", "120.00", "150.00", "180.00", "220.00", "140.00", "Nos", "10", "Small wooden toy car"],
    ["Stuffed Bear", "GTY", "Toys", "95030041", "18", "200.00", "240.00", "300.00", "400.00", "220.00", "Nos", "5", ""],
])

# ── 4. Customers ──────────────────────────────────────────────
make_sheet(wb, "4_Customers", [
    ("trade_name", "R", "operating name"),
    ("legal_name", "O", ""),
    ("gstin", "O", "15 chars; blank if unregistered"),
    ("gst_status", "O", "Registered / Unregistered / Composition"),
    ("is_b2b", "O", "TRUE / FALSE; default TRUE"),
    ("phone", "O", ""),
    ("email", "O", ""),
    ("contact_person", "O", ""),
    ("credit_limit", "O", "money; default 0"),
    ("credit_days", "O", "integer; default 0"),
    ("state", "O", "state name"),
    ("addr_label", "O", "e.g. Billing"),
    ("address_line1", "O", "required IF adding an address"),
    ("address_line2", "O", ""),
    ("city", "O", "required IF adding an address"),
    ("addr_state", "O", "required IF adding an address"),
    ("pincode", "O", "4-6 digits; required IF adding an address"),
], [
    ["Kumar Traders", "Kumar Traders Pvt Ltd", "29ABCDE1234F1Z5", "Registered", "TRUE", "9845012345",
     "kumar@example.com", "Anil Kumar", "100000.00", "30", "Karnataka",
     "Billing", "23 Market Rd", "", "Bengaluru", "Karnataka", "560002"],
    ["Walk-in Retail", "", "", "Unregistered", "FALSE", "", "", "", "0", "0", "Tamil Nadu",
     "", "", "", "", "", ""],
])

# ── 5. Vendors ────────────────────────────────────────────────
make_sheet(wb, "5_Vendors", [
    ("trade_name", "R", "vendor name"),
    ("legal_name", "O", ""),
    ("gstin", "O", "15 chars; blank if unregistered"),
    ("gst_status", "O", "Registered / Unregistered / Composition"),
    ("phone", "O", ""),
    ("email", "O", ""),
    ("contact_person", "O", ""),
    ("credit_days", "O", "integer; default 0"),
    ("bank_name", "O", ""),
    ("bank_account", "O", ""),
    ("bank_ifsc", "O", "11 chars"),
    ("state", "O", "state name"),
    ("addr_label", "O", "e.g. Office"),
    ("address_line1", "O", "required IF adding an address"),
    ("address_line2", "O", ""),
    ("city", "O", "required IF adding an address"),
    ("addr_state", "O", "required IF adding an address"),
    ("pincode", "O", "4-6 digits; required IF adding an address"),
], [
    ["Sunrise Imports", "Sunrise Imports LLP", "27FGHIJ5678K1Z2", "Registered", "9820011223",
     "sales@sunrise.com", "Meera", "45", "HDFC Bank", "50100123456789", "HDFC0000123", "Maharashtra",
     "Office", "8 Industrial Estate", "", "Mumbai", "Maharashtra", "400001"],
])

# ── 6. Opening Stock (EXACT importer format) ──────────────────
make_sheet(wb, "6_Opening_Stock", [
    ("part_code", "R", "must match an existing product's part_code (case-sensitive)"),
    ("warehouse_name", "R", "must match an active warehouse name (case-insensitive)"),
    ("quantity", "R", "> 0; up to 3 decimals"),
    ("unit_cost", "R", "> 0; landed cost per unit (sets FIFO value)"),
    ("opening_date", "O", "YYYY-MM-DD; blank = the date chosen at upload"),
], [
    ["GTY00001", "Main Warehouse", "100", "120.00", "2025-04-01"],
    ["GTY00002", "Main Warehouse", "50", "200.00", "2025-04-01"],
    ["GTY00002", "Branch Store", "15", "200.00", "2025-04-01"],
])

# ── 7. Opening Customer Balances ──────────────────────────────
make_sheet(wb, "7_Opening_Cust_Bal", [
    ("customer_trade_name", "R", "must match a customer in 4_Customers"),
    ("opening_balance", "R", "> 0; amount the customer owes you on cutover"),
    ("opening_date", "R", "YYYY-MM-DD"),
    ("notes", "O", ""),
], [
    ["Kumar Traders", "45000.00", "2025-04-01", "Carried forward from old books"],
])

# ── 8. Opening Vendor Balances ────────────────────────────────
make_sheet(wb, "8_Opening_Vend_Bal", [
    ("vendor_trade_name", "R", "must match a vendor in 5_Vendors"),
    ("opening_balance", "R", "> 0; amount you owe the vendor on cutover"),
    ("opening_date", "R", "YYYY-MM-DD"),
    ("notes", "O", ""),
], [
    ["Sunrise Imports", "78000.00", "2025-04-01", "Carried forward from old books"],
])

# ── 9. Opening Cash & Bank ────────────────────────────────────
ws_cb = make_sheet(wb, "9_Opening_Cash_Bank", [
    ("type", "R", "CASH or BANK"),
    ("account_code", "O", "BANK only: unique code e.g. HDFC_01"),
    ("bank_name", "O", "BANK only"),
    ("account_number", "O", "BANK only"),
    ("amount", "R", ">= 0"),
    ("opening_date", "R", "YYYY-MM-DD"),
    ("notes", "O", ""),
], [
    ["CASH", "", "", "", "25000.00", "2025-04-01", "Cash in hand"],
    ["BANK", "HDFC_01", "HDFC Bank", "50100123456789", "560000.00", "2025-04-01", "Current account"],
])

XLSX_PATH = os.path.join(TPL_DIR, "ERP_Initial_Data_Templates.xlsx")
wb.save(XLSX_PATH)

# ── Standalone, directly-uploadable opening-stock CSV ─────────
CSV_PATH = os.path.join(TPL_DIR, "opening_stock.csv")
with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["part_code", "warehouse_name", "quantity", "unit_cost", "opening_date"])
    w.writerow(["GTY00001", "Main Warehouse", "100", "120.00", "2025-04-01"])
    w.writerow(["GTY00002", "Main Warehouse", "50", "200.00", "2025-04-01"])

print("WROTE:", XLSX_PATH)
print("WROTE:", CSV_PATH)
