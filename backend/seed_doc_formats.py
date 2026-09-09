"""
seed_doc_formats.py - Phase 5b seed for document_number_format.
See docs/CONFIG_MIGRATION_PLAN.md.

Mirrors the CURRENT in-code prefixes/padding exactly, so generated numbers are
byte-identical (e.g. JE-202526-00001, PO-202526-0001). Invoice numbering is NOT
included here — it stays on CompanySettings prefixes + invoice_sequences.

Safe to re-run: only seeds doc_types not already present.

Run (backend venv active, DB migrated to head):
    python seed_doc_formats.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.models import DocumentNumberFormat

# doc_type, prefix, padding, description
FORMATS = [
    ("JE",  "JE",  5, "Journal entry"),
    ("PO",  "PO",  4, "Purchase order"),
    ("VP",  "VP",  4, "Vendor payment"),
    ("ADJ", "ADJ", 4, "Stock adjustment"),
    ("WO",  "WO",  4, "Stock write-off"),
    ("EXP", "EXP", 4, "Expense"),
    ("TDS", "TDS", 4, "TDS entry"),
    ("BSS", "BSS", 4, "Bank stock statement"),
]


def main():
    db = SessionLocal()
    created, skipped = 0, 0
    try:
        existing = {r.doc_type for r in db.query(DocumentNumberFormat.doc_type).all()}
        for doc_type, prefix, pad, desc in FORMATS:
            if doc_type in existing:
                skipped += 1
                print(f"  SKIP (exists): {doc_type}")
                continue
            db.add(DocumentNumberFormat(doc_type=doc_type, prefix=prefix,
                                        padding=pad, separator="-", description=desc))
            created += 1
            print(f"  OK  {doc_type}  -> {prefix}-<FY>-{{seq:0{pad}d}}")
        db.commit()
        print(f"\nDone. {created} created, {skipped} skipped.\n")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding document_number_format (Phase 5b baseline)...\n")
    main()
