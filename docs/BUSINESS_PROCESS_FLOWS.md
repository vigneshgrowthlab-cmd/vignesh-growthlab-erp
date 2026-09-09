# Wholesale ERP — Business Process Flow Diagrams

End-to-end **business processes** that flow *across* modules, organised by department/role
(swimlanes). Unlike the per-module technical flowcharts in
[MODULE_WORKFLOWS.md](MODULE_WORKFLOWS.md), these show how a single business transaction travels
through Purchase, Warehouse, Sales, Accounts and Compliance.

Diagrams use [Mermaid](https://mermaid.js.org/) and render on GitHub / VS Code. For a rendered
picture view, open [business-process-flows.html](business-process-flows.html) in a browser.

---

## 1. ERP Business Process Landscape

The big picture: master data feeds the core operating processes, which post into finance &
compliance, which surface in management reporting.

```mermaid
flowchart LR
    subgraph MD[Master Data Setup]
        direction TB
        MD1[Company and Tax Settings]
        MD2[Products and Pricing]
        MD3[Vendors and Customers]
        MD4[Users and Roles]
    end
    subgraph OP[Core Operating Processes]
        direction TB
        OP1[Procure to Pay]
        OP2[Inventory and Warehouse]
        OP3[Order to Cash]
    end
    subgraph FC[Finance and Compliance]
        direction TB
        FC1[Record to Report]
        FC2[GST Compliance]
        FC3[Banking and Treasury]
    end
    subgraph MG[Management]
        direction TB
        MG1[Dashboard and Reports]
    end
    MD --> OP
    OP --> FC
    FC --> MG
```

---

## 2. Procure-to-Pay (P2P)

A vendor purchase from need to payment, crossing four departments.

```mermaid
flowchart LR
    subgraph PUR[Purchase Dept]
        direction TB
        A1[Identify purchase need]
        A2[Onboard or select vendor]
        A3[Record vendor purchase bill]
    end
    subgraph INV[Warehouse and Inventory]
        direction TB
        B1[Receive goods into warehouse]
        B2[Create FIFO stock layer]
        B3[Update product cost and prices]
    end
    subgraph ACC[Accounts]
        direction TB
        C1[Post journal Stock and GST ITC vs Creditors]
        C2[Vendor payable in ledger]
        C3[Make vendor payment]
        C4[Post journal Creditors vs Cash or Bank]
    end
    subgraph CMP[Compliance]
        direction TB
        D1[Capture GST input credit]
        D2[Reconcile GSTR-2B vs purchases]
    end
    A1 --> A2 --> A3
    A3 --> B1 --> B2 --> B3
    A3 --> C1 --> C2
    C2 --> C3 --> C4
    C1 --> D1 --> D2
```

---

## 3. Order-to-Cash (O2C)

A customer sale from enquiry to collection, with statutory e-invoice / e-way steps.

```mermaid
flowchart LR
    subgraph SAL[Sales Dept]
        direction TB
        A1[Onboard customer with credit limit]
        A2[Create quotation]
        A3[Confirm and create sales invoice]
        A4[Credit limit and stock check]
    end
    subgraph WH[Warehouse]
        direction TB
        B1[Consume FIFO stock and capture COGS]
        B2[Generate delivery challan]
        B3[Dispatch goods]
    end
    subgraph CMP[Compliance]
        direction TB
        C1[Generate E-Invoice IRN and QR]
        C2[Generate E-Way Bill]
        C3[Report in GSTR-1]
    end
    subgraph ACC[Accounts]
        direction TB
        D1[Post journal Debtors vs Sales and GST]
        D2[Receivable in ledger]
        D3[Record customer receipt]
        D4[Post journal Cash or Bank vs Debtors]
    end
    A1 --> A2 --> A3 --> A4
    A4 --> B1 --> B2 --> B3
    A3 --> C1 --> C2 --> C3
    A3 --> D1 --> D2
    D2 --> D3 --> D4
```

---

## 4. Record-to-Report & GST Compliance

Every posted transaction rolls up into the books, statutory returns, bank reconciliation and
management reports.

```mermaid
flowchart TD
    T[All transactions Purchase Sales Expense Receipt Payment] --> J[Double-entry journal_entries and journal_lines]
    P[Purchases] --> G2[GSTR-2B reconcile vs purchases]
    INV[FIFO stock value and Debtors] --> BSS[Bank Stock Statement and Drawing Power]
    J --> TB[Trial Balance]
    J --> PL[Profit and Loss]
    J --> G1[GSTR-1 outward supplies]
    J --> G3[GSTR-3B summary]
    J --> BR[Bank Reconciliation vs LedgerEntry]
    TB --> DASH[Dashboard and Management Reports]
    PL --> DASH
    G1 --> DASH
    G3 --> DASH
    BR --> DASH
    BSS --> DASH
    G2 --> DASH
```
