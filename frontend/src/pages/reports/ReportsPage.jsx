import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { reportsAPI } from '@/api/reports'
import { customerAPI } from '@/api/billing'
import { vendorAPI } from '@/api/purchase'
import { useAuthStore } from '@/store/authStore'
import { Button, Field, Input, Select, Spinner, Empty, Badge } from '@/components/ui'
import { Download } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

const TABS = ['Sales', 'Purchase', 'Stock', 'Clearance', 'P&L', 'Day Book', 'Customer Ledger', 'Vendor Ledger']
// Profit/margin reports — visible to super-admin only
const PROFIT_TABS = ['Clearance', 'P&L']
const FY_OPTIONS = ['2026-27', '2025-26', '2024-25', '2023-24']

// ── Download helpers ──────────────────────────────────────────
function downloadCSV(rows, cols, filename) {
  if (!rows?.length) { toast.error('No data to download'); return }
  const header = cols.map(c => c.label).join(',')
  const body = rows.map(r => cols.map(c => {
    const v = r[c.key] ?? ''
    return typeof v === 'string' && v.includes(',') ? `"${v}"` : v
  }).join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + header + '\n' + body], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = filename + '.csv'; a.click()
  URL.revokeObjectURL(url)
}

function downloadPDF(title, cols, rows, summary = '') {
  if (!rows?.length) { toast.error('No data to download'); return }
  const ths = cols.map(c => `<th>${c.label}</th>`).join('')
  const trs = rows.map(r =>
    `<tr>${cols.map(c => `<td style="text-align:${c.right ? 'right' : 'left'}">${r[c.key] ?? ''}</td>`).join('')}</tr>`
  ).join('')
  const win = window.open('', '_blank')
  win.document.write(`<!DOCTYPE html><html><head><title>${title}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:20px;font-size:12px}
      h2{margin-bottom:6px;font-size:16px}
      p.summary{margin-bottom:12px;color:#555}
      table{width:100%;border-collapse:collapse;margin-top:8px}
      th{background:#2c3e50;color:#fff;padding:7px 8px;text-align:left;font-size:11px}
      td{padding:5px 8px;border-bottom:1px solid #eee;font-size:11px}
      tr:nth-child(even){background:#f9f9f9}
      .btn{margin-top:14px;padding:8px 20px;background:#2c3e50;color:#fff;border:none;cursor:pointer;border-radius:4px;font-size:13px}
      @media print{.btn{display:none}}
    </style></head><body>
    <h2>${title}</h2>
    ${summary ? `<p class="summary">${summary}</p>` : ''}
    <table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>
    <button class="btn" onclick="window.print()">🖨 Print / Save as PDF</button>
    </body></html>`)
  win.document.close()
}

function downloadLedgerPDF(data, title) {
  if (!data?.rows?.length) { toast.error('No data to download'); return }
  const trs = data.rows.map(r => `
    <tr>
      <td>${r.date ? r.date.split('T')[0] : ''}</td>
      <td>${r.narration || ''}</td>
      <td style="text-align:right">${r.debit > 0 ? fmtNum(r.debit) : '—'}</td>
      <td style="text-align:right;color:#1a7a4a">${r.credit > 0 ? fmtNum(r.credit) : '—'}</td>
      <td style="text-align:right;font-weight:600">${r.balance != null ? fmtNum(r.balance) : '—'}</td>
    </tr>`).join('')
  const win = window.open('', '_blank')
  win.document.write(`<!DOCTYPE html><html><head><title>${title}</title>
    <style>
      body{font-family:Arial;padding:20px;font-size:12px}
      h2{font-size:16px;margin-bottom:4px}p{margin:2px 0;color:#555;font-size:11px}
      table{width:100%;border-collapse:collapse;margin-top:12px}
      th{background:#2c3e50;color:#fff;padding:7px 8px;text-align:left;font-size:11px}
      td{padding:5px 8px;border-bottom:1px solid #eee;font-size:11px}
      tr:nth-child(even){background:#f9f9f9}
      .btn{margin-top:14px;padding:8px 20px;background:#2c3e50;color:#fff;border:none;cursor:pointer;border-radius:4px}
      @media print{.btn{display:none}}
    </style></head><body>
    <h2>${title}</h2>
    <p>Name: <strong>${data.customer_name || data.vendor_name || ''}</strong></p>
    <p>Opening Balance: <strong>${fmtNum(data.opening_balance)}</strong> &nbsp;|&nbsp;
       Closing Balance: <strong>${fmtNum(data.closing_balance)}</strong></p>
    <table>
      <thead><tr><th>Date</th><th>Narration</th><th>Debit (₹)</th><th>Credit (₹)</th><th>Balance (₹)</th></tr></thead>
      <tbody>${trs}</tbody>
    </table>
    <button class="btn" onclick="window.print()">🖨 Print / Save as PDF</button>
    </body></html>`)
  win.document.close()
}

function fmtNum(v) {
  return '₹' + Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })
}

// ── Reusable download bar ─────────────────────────────────────
function DlBar({ onCSV, onPDF, disabled }) {
  return (
    <div className="flex gap-2">
      <button onClick={onCSV} disabled={disabled}
        className="flex items-center gap-1.5 px-3 h-8 rounded-lg bg-green-600 text-white text-xs hover:bg-green-700 disabled:opacity-40">
        <Download size={12} /> Excel
      </button>
      <button onClick={onPDF} disabled={disabled}
        className="flex items-center gap-1.5 px-3 h-8 rounded-lg bg-red-600 text-white text-xs hover:bg-red-700 disabled:opacity-40">
        <Download size={12} /> PDF
      </button>
    </div>
  )
}

function fmt(v) {
  return `₹${Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

function SummaryCard({ label, value, color = 'gray' }) {
  const cls = { gray: 'text-gray-700', blue: 'text-primary', green: 'text-success', red: 'text-danger', amber: 'text-amber-600' }
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className={clsx('text-lg font-semibold mt-1', cls[color])}>{value}</div>
    </div>
  )
}

// ── Sales Report ──────────────────────────────────────────────
function SalesReport() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const monthStart = format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd')
  const [params, setParams] = useState({ date_from: monthStart, date_to: today, financial_year: '2026-27' })
  const [run, setRun] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['report-sales', params],
    queryFn: () => reportsAPI.sales(params).then(r => r.data),
    enabled: run,
  })

  const COLS = [
    { key: 'invoice_number', label: 'Invoice No.' },
    { key: 'invoice_date',   label: 'Date' },
    { key: 'customer_name',  label: 'Customer' },
    { key: 'document_type',  label: 'Type' },
    { key: 'taxable_amount', label: 'Taxable (₹)', right: true },
    { key: 'total_amount',   label: 'Total (₹)', right: true },
    { key: 'outstanding_amount', label: 'Outstanding (₹)', right: true },
  ]

  return (
    <div>
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Field label="From"><Input type="date" value={params.date_from} onChange={e => setParams(p => ({ ...p, date_from: e.target.value }))} /></Field>
        <Field label="To"><Input type="date" value={params.date_to} onChange={e => setParams(p => ({ ...p, date_to: e.target.value }))} /></Field>
        <Field label="Financial Year">
          <Select value={params.financial_year} onChange={e => setParams(p => ({ ...p, financial_year: e.target.value }))}>
            {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
          </Select>
        </Field>
        <div className="flex items-end gap-2">
          <Button variant="primary" className="flex-1" onClick={() => setRun(true)}>Generate</Button>
          <DlBar disabled={!data?.rows?.length}
            onCSV={() => downloadCSV(data.rows, COLS, `sales_${params.date_from}_${params.date_to}`)}
            onPDF={() => downloadPDF('Sales Report', COLS, data.rows,
              `Period: ${params.date_from} to ${params.date_to} | Total: ${fmt(data.summary?.total_amount)} | Outstanding: ${fmt(data.summary?.total_outstanding)}`
            )} />
        </div>
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <SummaryCard label="Total Invoices" value={data.invoice_count} />
            <SummaryCard label="Taxable Value" value={fmt(data.summary?.total_taxable)} color="blue" />
            <SummaryCard label="Total Tax" value={fmt(data.summary?.total_tax)} />
            <SummaryCard label="Total Amount" value={fmt(data.summary?.total_amount)} color="green" />
          </div>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <SummaryCard label="Amount Collected" value={fmt(data.summary?.total_collected)} color="green" />
            <SummaryCard label="Outstanding" value={fmt(data.summary?.total_outstanding)} color="red" />
          </div>
          {data.rows.length === 0 ? <Empty message="No sales for this period" /> : (
            <table className="table">
              <thead><tr><th>Invoice No.</th><th>Date</th><th>Customer</th><th>Type</th><th className="text-right">Taxable</th><th className="text-right">Tax</th><th className="text-right">Total</th><th className="text-right">Outstanding</th><th>IRN</th></tr></thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs font-semibold">{row.invoice_number}</td>
                    <td className="text-gray-500 text-xs">{row.invoice_date ? format(new Date(row.invoice_date), 'dd/MM/yy') : '—'}</td>
                    <td className="font-medium text-sm">{row.customer_name}</td>
                    <td><Badge color={row.document_type === 'b2b_invoice' ? 'blue' : 'gray'}>{row.document_type === 'b2b_invoice' ? 'B2B' : 'B2C'}</Badge></td>
                    <td className="text-right text-sm">₹{Number(row.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{(Number(row.total_cgst) + Number(row.total_sgst) + Number(row.total_igst)).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right font-semibold">₹{Number(row.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right"><span className={Number(row.outstanding_amount) > 0 ? 'text-danger font-medium' : 'text-success'}>₹{Number(row.outstanding_amount).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span></td>
                    <td>{row.irn ? <Badge color="green">✓</Badge> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

// ── Purchase Report ───────────────────────────────────────────
function PurchaseReport() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const monthStart = format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd')
  const [params, setParams] = useState({ date_from: monthStart, date_to: today })
  const [run, setRun] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['report-purchases', params],
    queryFn: () => reportsAPI.purchases(params).then(r => r.data),
    enabled: run,
  })

  const COLS = [
    { key: 'vendor_invoice_number', label: 'Vendor Invoice No.' },
    { key: 'invoice_date',          label: 'Date' },
    { key: 'vendor_name',           label: 'Vendor' },
    { key: 'gst_type',              label: 'GST Type' },
    { key: 'subtotal',              label: 'Taxable (₹)', right: true },
    { key: 'total_amount',          label: 'Total (₹)', right: true },
  ]

  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Field label="From"><Input type="date" value={params.date_from} onChange={e => setParams(p => ({ ...p, date_from: e.target.value }))} /></Field>
        <Field label="To"><Input type="date" value={params.date_to} onChange={e => setParams(p => ({ ...p, date_to: e.target.value }))} /></Field>
        <div className="flex items-end gap-2">
          <Button variant="primary" className="flex-1" onClick={() => setRun(true)}>Generate</Button>
          <DlBar disabled={!data?.rows?.length}
            onCSV={() => downloadCSV(data.rows, COLS, `purchase_${params.date_from}_${params.date_to}`)}
            onPDF={() => downloadPDF('Purchase Entries Report', COLS, data.rows,
              `Period: ${params.date_from} to ${params.date_to} | Total: ${fmt(data.summary?.total_amount)}`
            )} />
        </div>
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <SummaryCard label="Total Entries" value={data.purchase_count} />
            <SummaryCard label="Taxable Value" value={fmt(data.summary?.total_taxable)} color="blue" />
            <SummaryCard label="Total Amount" value={fmt(data.summary?.total_amount)} color="green" />
          </div>
          {data.rows.length === 0 ? <Empty message="No purchases for this period" /> : (
            <table className="table">
              <thead><tr><th>Vendor Invoice No.</th><th>Date</th><th>Vendor</th><th>GST Type</th><th className="text-right">Taxable</th><th className="text-right">Tax</th><th className="text-right">Total</th></tr></thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs font-semibold">{row.vendor_invoice_number}</td>
                    <td className="text-gray-500 text-xs">{row.invoice_date ? format(new Date(row.invoice_date), 'dd/MM/yy') : '—'}</td>
                    <td className="font-medium text-sm">{row.vendor_name}</td>
                    <td><Badge color={row.gst_type === 'cgst_sgst' ? 'blue' : 'amber'}>{row.gst_type === 'cgst_sgst' ? 'CGST+SGST' : 'IGST'}</Badge></td>
                    <td className="text-right">₹{Number(row.subtotal).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-gray-500">₹{(Number(row.total_cgst) + Number(row.total_sgst) + Number(row.total_igst)).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right font-semibold">₹{Number(row.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

// ── Stock Report ──────────────────────────────────────────────
function StockReport() {
  const [lowStock, setLowStock] = useState(false)
  const [run, setRun] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['report-stock', lowStock],
    queryFn: () => reportsAPI.stock({ low_stock_only: lowStock }).then(r => r.data),
    enabled: run,
  })

  const COLS = [
    { key: 'part_code',       label: 'Part Code' },
    { key: 'part_name',       label: 'Product' },
    { key: 'category_name',   label: 'Category' },
    { key: 'unit_of_measure', label: 'UOM' },
    { key: 'total_quantity',  label: 'Total Qty', right: true },
    { key: 'total_fifo_value',label: 'FIFO Value (₹)', right: true },
    { key: 'is_low_stock',    label: 'Status' },
  ]

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={lowStock} onChange={e => setLowStock(e.target.checked)} className="rounded" />
          Low stock items only
        </label>
        <Button variant="primary" onClick={() => setRun(true)}>Generate</Button>
        <DlBar disabled={!data?.rows?.length}
          onCSV={() => downloadCSV(
            data.rows.map(r => ({ ...r, is_low_stock: r.is_low_stock ? 'Low Stock' : 'Normal' })),
            COLS, 'stock_report'
          )}
          onPDF={() => downloadPDF('Stock Report',
            COLS,
            data.rows.map(r => ({ ...r, is_low_stock: r.is_low_stock ? 'Low Stock' : 'Normal',
              total_fifo_value: fmtNum(r.total_fifo_value) })),
            `Total Products: ${data.product_count} | Low Stock: ${data.low_stock_count} | Total Value: ${fmt(data.total_stock_value)}`
          )} />
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <SummaryCard label="Total Products" value={data.product_count} />
            <SummaryCard label="Low Stock Items" value={data.low_stock_count} color="red" />
            <SummaryCard label="Total Stock Value (FIFO)" value={fmt(data.total_stock_value)} color="blue" />
          </div>
          <div className="text-xs text-gray-400 mb-2">As of {data.as_of_date ? format(new Date(data.as_of_date), 'dd MMM yyyy') : '—'}</div>
          {data.rows.length === 0 ? <Empty message="No stock records" /> : (
            <table className="table">
              <thead><tr><th>Part Code</th><th>Product</th><th>Category</th><th>UOM</th><th className="text-right">Total Qty</th><th className="text-right">FIFO Value</th><th>Status</th></tr></thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i} className={row.is_low_stock ? 'bg-red-50/30' : ''}>
                    <td className="font-mono text-xs">{row.part_code}</td>
                    <td className="font-medium text-sm">{row.part_name}</td>
                    <td className="text-gray-500 text-sm">{row.category_name || '—'}</td>
                    <td className="text-gray-500 text-xs">{row.unit_of_measure}</td>
                    <td className="text-right font-medium">{Number(row.total_quantity).toFixed(3)}</td>
                    <td className="text-right font-medium">₹{Number(row.total_fifo_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td>{row.is_low_stock ? <Badge color="red">Low Stock</Badge> : <Badge color="green">Normal</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

// ── Clearance Report ──────────────────────────────────────────
// Per-batch (FIFO layer) view for clearance-sale discounting. Discount is
// keyed manually at invoice time; this only shows which old/limited batches
// have the most profit cushion down to floor_price.
function ClearanceReport() {
  const [minAge, setMinAge] = useState(0)
  const [run, setRun] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['report-clearance', minAge],
    queryFn: () => reportsAPI.stockClearance({ min_age_days: minAge || 0 }).then(r => r.data),
    enabled: run,
  })

  const COLS = [
    { key: 'part_code',       label: 'Part Code' },
    { key: 'part_name',       label: 'Product' },
    { key: 'warehouse_name',  label: 'Warehouse' },
    { key: 'batch_date',      label: 'Batch Date' },
    { key: 'age_days',        label: 'Age (days)', right: true },
    { key: 'remaining_qty',   label: 'Qty Left', right: true },
    { key: 'unit_cost',       label: 'Batch Cost', right: true },
    { key: 'floor_price',     label: 'Floor Price', right: true },
    { key: 'b2b_price',       label: 'B2B', right: true },
    { key: 'b2c_price',       label: 'B2C', right: true },
    { key: 'mrp',             label: 'MRP', right: true },
    { key: 'profit_at_floor', label: 'Profit @ Floor', right: true },
    { key: 'margin_at_floor_pct', label: 'Margin @ Floor %', right: true },
  ]

  const csvRows = () => data.rows.map(r => ({
    ...r,
    batch_date: r.batch_date ? r.batch_date.split('T')[0] : '',
  }))

  return (
    <div>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          Older than
          <input type="number" min={0} value={minAge}
            onChange={e => setMinAge(Number(e.target.value))}
            className="w-20 h-8 px-2 border border-gray-300 rounded-lg text-sm" />
          days
        </label>
        <Button variant="primary" onClick={() => setRun(true)}>Generate</Button>
        <DlBar disabled={!data?.rows?.length}
          onCSV={() => downloadCSV(csvRows(), COLS, 'stock_clearance')}
          onPDF={() => downloadPDF('Stock Clearance — Batch Margins',
            COLS,
            csvRows().map(r => ({
              ...r,
              unit_cost: fmtNum(r.unit_cost), floor_price: fmtNum(r.floor_price),
              b2b_price: fmtNum(r.b2b_price), b2c_price: fmtNum(r.b2c_price), mrp: fmtNum(r.mrp),
              profit_at_floor: fmtNum(r.profit_at_floor),
            })),
            `Batches: ${data.batch_count} | Products: ${data.product_count} | Stock at Cost: ${fmt(data.total_stock_value)}`
          )} />
      </div>

      <p className="text-xs text-gray-500 mb-3">
        Older / cheaper batches carry a bigger <strong>Profit @ Floor</strong> — discount those hardest.
        A red value means the floor price is below that batch's cost (a loss even at floor). Enter the
        actual discount manually on the invoice.
      </p>

      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <SummaryCard label="Batches" value={data.batch_count} />
            <SummaryCard label="Products" value={data.product_count} color="blue" />
            <SummaryCard label="Stock at Cost" value={fmt(data.total_stock_value)} color="amber" />
          </div>
          <div className="text-xs text-gray-400 mb-2">As of {data.as_of_date ? format(new Date(data.as_of_date), 'dd MMM yyyy') : '—'}</div>
          {data.rows.length === 0 ? <Empty message="No stock batches found" /> : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th>Part Code</th><th>Product</th><th>Warehouse</th><th>Batch Date</th>
                  <th className="text-right">Age</th><th className="text-right">Qty Left</th>
                  <th className="text-right">Cost</th><th className="text-right">Floor</th>
                  <th className="text-right">B2C</th><th className="text-right">MRP</th>
                  <th className="text-right">Profit @ Floor</th><th className="text-right">Margin @ Floor</th>
                </tr></thead>
                <tbody>
                  {data.rows.map((row, i) => {
                    const prev = data.rows[i - 1]
                    const newProduct = !prev || prev.product_id !== row.product_id
                    const loss = row.profit_at_floor < 0
                    return (
                      <tr key={row.entry_id} className={clsx(newProduct && i > 0 && 'border-t-2 border-gray-200', row.age_days >= 90 && 'bg-amber-50/40')}>
                        <td className="font-mono text-xs">{newProduct ? row.part_code : ''}</td>
                        <td className="font-medium text-sm">{newProduct ? row.part_name : ''}</td>
                        <td className="text-gray-500 text-xs">{row.warehouse_name}</td>
                        <td className="text-xs">{row.batch_date ? format(new Date(row.batch_date), 'dd MMM yy') : '—'}</td>
                        <td className="text-right text-xs">{row.age_days}</td>
                        <td className="text-right font-medium">{Number(row.remaining_qty).toFixed(3)}</td>
                        <td className="text-right">{fmtNum(row.unit_cost)}</td>
                        <td className="text-right">{fmtNum(row.floor_price)}</td>
                        <td className="text-right text-gray-500">{fmtNum(row.b2c_price)}</td>
                        <td className="text-right text-gray-500">{fmtNum(row.mrp)}</td>
                        <td className={clsx('text-right font-semibold', loss ? 'text-danger' : 'text-success')}>{fmtNum(row.profit_at_floor)}</td>
                        <td className={clsx('text-right', loss ? 'text-danger' : 'text-gray-700')}>{row.margin_at_floor_pct}%</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── P&L Report ────────────────────────────────────────────────
function PnLReport() {
  const [fy, setFy] = useState('2026-27')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [run, setRun] = useState(false)

  const useRange = Boolean(dateFrom && dateTo)
  const params = useRange ? { date_from: dateFrom, date_to: dateTo } : { financial_year: fy }
  const periodLabel = useRange ? `${dateFrom} to ${dateTo}` : `FY ${fy}`

  const { data, isLoading } = useQuery({
    queryKey: ['report-pnl', params],
    queryFn: () => reportsAPI.pnl(params).then(r => r.data),
    enabled: run,
  })

  const handleGenerate = () => {
    if ((dateFrom && !dateTo) || (!dateFrom && dateTo)) {
      toast.error('Select both From and To dates, or clear both to use the financial year')
      return
    }
    setRun(true)
  }

  const downloadPnLPDF = () => {
    if (!data) { toast.error('Generate report first'); return }
    const rows = [
      { item: 'Revenue (Net of Discounts)', amount: fmtNum(data.revenue) },
      { item: 'Cost of Goods Sold (FIFO)',  amount: fmtNum(data.cogs) },
      { item: `Gross Profit (${data.gross_margin_pct}% margin)`, amount: fmtNum(data.gross_profit) },
      { item: 'Total Expenses',             amount: fmtNum(data.total_expenses) },
      { item: `Net Profit (${data.net_margin_pct}% margin)`,     amount: fmtNum(data.net_profit) },
      ...(data.expenses_by_category?.map(e => ({ item: `  Expense: ${e.category}`, amount: fmtNum(e.amount) })) || []),
    ]
    downloadPDF(`P&L Report — ${periodLabel}`,
      [{ key: 'item', label: 'Item' }, { key: 'amount', label: 'Amount', right: true }],
      rows, `Period: ${periodLabel}`)
  }

  const downloadPnLCSV = () => {
    if (!data) { toast.error('Generate report first'); return }
    const rows = [
      { item: 'Revenue', amount: data.revenue },
      { item: 'COGS',    amount: data.cogs },
      { item: 'Gross Profit', amount: data.gross_profit },
      { item: 'Gross Margin %', amount: data.gross_margin_pct },
      { item: 'Expenses', amount: data.total_expenses },
      { item: 'Net Profit', amount: data.net_profit },
      { item: 'Net Margin %', amount: data.net_margin_pct },
    ]
    downloadCSV(rows, [{ key: 'item', label: 'Item' }, { key: 'amount', label: 'Amount' }],
      `pnl_${useRange ? `${dateFrom}_${dateTo}` : fy}`)
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 mb-1">
        <Field label="Financial Year">
          <Select value={fy} onChange={e => setFy(e.target.value)} className="w-36" disabled={useRange}>
            {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
          </Select>
        </Field>
        <Field label="From"><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></Field>
        {useRange && (
          <button onClick={() => { setDateFrom(''); setDateTo('') }}
            className="h-8 px-3 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50">
            Clear dates
          </button>
        )}
        <Button variant="primary" onClick={handleGenerate}>Generate P&L</Button>
        {data && <DlBar onCSV={downloadPnLCSV} onPDF={downloadPnLPDF} />}
      </div>
      <p className="text-xs text-gray-400 mb-4">
        {useRange ? 'Reporting on the selected date range.' : 'Leave both dates empty to report on the full financial year.'}
      </p>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <div className="max-w-xl space-y-3">
          {[
            { label: 'Revenue (Net of Discounts)', val: data.revenue, color: 'blue', border: false },
            { label: 'Cost of Goods Sold (FIFO)', val: data.cogs, color: 'red', border: false },
            { label: `Gross Profit (${data.gross_margin_pct}% margin)`, val: data.gross_profit, color: data.gross_profit >= 0 ? 'green' : 'red', border: true },
            { label: 'Total Expenses', val: data.total_expenses, color: 'amber', border: false },
            { label: `Net Profit (${data.net_margin_pct}% margin)`, val: data.net_profit, color: data.net_profit >= 0 ? 'green' : 'red', border: true },
          ].map(row => (
            <div key={row.label} className={clsx('flex justify-between items-center py-2 text-sm', row.border && 'border-t-2 border-gray-200 mt-2 pt-3 font-semibold text-base')}>
              <span className={row.border ? 'text-gray-800' : 'text-gray-600'}>{row.label}</span>
              <span className={clsx(row.border ? 'text-lg' : '', {
                'text-primary': row.color === 'blue',
                'text-danger': row.color === 'red',
                'text-success': row.color === 'green',
                'text-amber-600': row.color === 'amber',
              })}>
                {row.val < 0 ? '-' : ''}₹{Math.abs(Number(row.val)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          ))}
          {data.expenses_by_category?.length > 0 && (
            <div className="mt-6">
              <h3 className="font-semibold text-gray-700 mb-3 text-sm">Expense Breakdown</h3>
              <table className="table">
                <thead><tr><th>Category</th><th className="text-right">Amount</th></tr></thead>
                <tbody>
                  {data.expenses_by_category.map((e, i) => (
                    <tr key={i}>
                      <td>{e.category}</td>
                      <td className="text-right text-amber-600 font-medium">₹{Number(e.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Day Book ──────────────────────────────────────────────────
function DayBookReport() {
  const [forDate, setForDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [run, setRun] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['report-daybook', forDate],
    queryFn: () => reportsAPI.dayBook({ for_date: forDate }).then(r => r.data),
    enabled: run,
  })

  const TYPE_COLORS = { sale: 'blue', purchase: 'amber', receipt: 'green', expense: 'red' }

  const COLS = [
    { key: 'type',      label: 'Type' },
    { key: 'reference', label: 'Reference' },
    { key: 'party',     label: 'Party' },
    { key: 'narration', label: 'Description' },
    { key: 'debit',     label: 'Debit (₹)', right: true },
    { key: 'credit',    label: 'Credit (₹)', right: true },
  ]

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Field label="Date"><Input type="date" value={forDate} onChange={e => setForDate(e.target.value)} className="w-48" /></Field>
        <div className="mt-5"><Button variant="primary" onClick={() => setRun(true)}>Generate Day Book</Button></div>
        {data && (
          <div className="mt-5">
            <DlBar
              onCSV={() => downloadCSV(data.entries, COLS, `daybook_${forDate}`)}
              onPDF={() => downloadPDF(`Day Book — ${forDate}`, COLS,
                data.entries.map(e => ({ ...e, debit: e.debit > 0 ? fmtNum(e.debit) : '—', credit: e.credit > 0 ? fmtNum(e.credit) : '—' })),
                `Date: ${forDate} | Total Debit: ${fmt(data.total_debit)} | Total Credit: ${fmt(data.total_credit)}`
              )} />
          </div>
        )}
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <SummaryCard label="Total Entries" value={data.entry_count} />
            <SummaryCard label="Total Debits" value={fmt(data.total_debit)} color="blue" />
            <SummaryCard label="Total Credits" value={fmt(data.total_credit)} color="green" />
          </div>
          {data.entries.length === 0 ? <Empty message="No entries for this date" /> : (
            <table className="table">
              <thead><tr><th>Type</th><th>Reference</th><th>Party</th><th>Description</th><th className="text-right">Debit (₹)</th><th className="text-right">Credit (₹)</th></tr></thead>
              <tbody>
                {data.entries.map((e, i) => (
                  <tr key={i}>
                    <td><Badge color={TYPE_COLORS[e.type] || 'gray'}>{e.type}</Badge></td>
                    <td className="font-mono text-xs">{e.reference}</td>
                    <td className="text-sm font-medium">{e.party}</td>
                    <td className="text-sm text-gray-600">{e.narration}</td>
                    <td className="text-right">{e.debit > 0 ? fmt(e.debit) : '—'}</td>
                    <td className="text-right">{e.credit > 0 ? fmt(e.credit) : '—'}</td>
                  </tr>
                ))}
                <tr className="font-semibold bg-gray-50">
                  <td colSpan={4} className="text-right text-gray-600">TOTAL</td>
                  <td className="text-right text-primary">{fmt(data.total_debit)}</td>
                  <td className="text-right text-success">{fmt(data.total_credit)}</td>
                </tr>
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

// ── Customer Ledger ───────────────────────────────────────────
function CustomerLedgerReport() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const fyStart = format(new Date(new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1, 3, 1), 'yyyy-MM-dd')
  const [customerId, setCustomerId] = useState('')
  const [dateFrom, setDateFrom] = useState(fyStart)
  const [dateTo, setDateTo] = useState(today)
  const [run, setRun] = useState(false)

  const { data: customers } = useQuery({ queryKey: ['customers-list'], queryFn: () => customerAPI.list({ page_size: 500 }).then(r => r.data.items) })

  const { data, isLoading } = useQuery({
    queryKey: ['report-customer-ledger', customerId, dateFrom, dateTo],
    queryFn: () => reportsAPI.customerLedger({ customer_id: customerId, date_from: dateFrom, date_to: dateTo }).then(r => r.data),
    enabled: run && Boolean(customerId),
  })

  return (
    <div>
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Field label="Customer" required>
          <Select value={customerId} onChange={e => setCustomerId(e.target.value)}>
            <option value="">Select customer...</option>
            {customers?.map(c => <option key={c.id} value={c.id}>{c.trade_name}</option>)}
          </Select>
        </Field>
        <Field label="From"><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></Field>
        <div className="flex items-end gap-2">
          <Button variant="primary" className="flex-1" onClick={() => setRun(true)} disabled={!customerId}>Generate</Button>
          <DlBar disabled={!data?.rows?.length}
            onCSV={() => downloadCSV(data.rows, [
              { key: 'date', label: 'Date' }, { key: 'narration', label: 'Narration' },
              { key: 'debit', label: 'Debit' }, { key: 'credit', label: 'Credit' }, { key: 'balance', label: 'Balance' }
            ], `customer_ledger_${data.customer_name}`)}
            onPDF={() => downloadLedgerPDF(data, `Customer Ledger — ${data.customer_name}`)}
          />
        </div>
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-semibold text-gray-800">{data.customer_name}</div>
              {data.customer_gstin && <div className="text-xs text-gray-400 font-mono">{data.customer_gstin}</div>}
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-400">Closing Balance</div>
              <div className={clsx('text-lg font-semibold', data.closing_balance > 0 ? 'text-danger' : 'text-success')}>
                {fmt(data.closing_balance)}
              </div>
            </div>
          </div>
          {data.rows.length === 0 ? <Empty message="No ledger entries for this period" /> : (
            <table className="table">
              <thead><tr><th>Date</th><th>Narration</th><th className="text-right">Debit (₹)</th><th className="text-right">Credit (₹)</th><th className="text-right">Balance (₹)</th></tr></thead>
              <tbody>
                <tr className="bg-gray-50 font-medium">
                  <td>{dateFrom ? format(new Date(dateFrom), 'dd MMM yyyy') : '—'}</td>
                  <td className="text-gray-500 italic">Opening Balance</td>
                  <td colSpan={2}></td>
                  <td className="text-right">{fmt(data.opening_balance)}</td>
                </tr>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    <td className="text-gray-500 text-xs">{row.date ? format(new Date(row.date), 'dd MMM yyyy') : '—'}</td>
                    <td className="text-sm">{row.narration}</td>
                    <td className="text-right text-sm">{row.debit > 0 ? fmt(row.debit) : '—'}</td>
                    <td className="text-right text-sm text-success">{row.credit > 0 ? fmt(row.credit) : '—'}</td>
                    <td className="text-right font-medium">{fmt(row.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

// ── Vendor Ledger ─────────────────────────────────────────────
function VendorLedgerReport() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const fyStart = format(new Date(new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1, 3, 1), 'yyyy-MM-dd')
  const [vendorId, setVendorId] = useState('')
  const [dateFrom, setDateFrom] = useState(fyStart)
  const [dateTo, setDateTo] = useState(today)
  const [run, setRun] = useState(false)

  const { data: vendors } = useQuery({ queryKey: ['vendors-list'], queryFn: () => vendorAPI.list({ page_size: 500 }).then(r => r.data.items) })

  const { data, isLoading } = useQuery({
    queryKey: ['report-vendor-ledger', vendorId, dateFrom, dateTo],
    queryFn: () => reportsAPI.vendorLedger({ vendor_id: vendorId, date_from: dateFrom, date_to: dateTo }).then(r => r.data),
    enabled: run && Boolean(vendorId),
  })

  return (
    <div>
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Field label="Vendor" required>
          <Select value={vendorId} onChange={e => setVendorId(e.target.value)}>
            <option value="">Select vendor...</option>
            {vendors?.map(v => <option key={v.id} value={v.id}>{v.trade_name}</option>)}
          </Select>
        </Field>
        <Field label="From"><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></Field>
        <div className="flex items-end gap-2">
          <Button variant="primary" className="flex-1" onClick={() => setRun(true)} disabled={!vendorId}>Generate</Button>
          <DlBar disabled={!data?.rows?.length}
            onCSV={() => downloadCSV(data.rows, [
              { key: 'date', label: 'Date' }, { key: 'narration', label: 'Narration' },
              { key: 'debit', label: 'Debit' }, { key: 'credit', label: 'Credit' }, { key: 'balance', label: 'Balance' }
            ], `vendor_ledger_${data.vendor_name}`)}
            onPDF={() => downloadLedgerPDF(data, `Vendor Ledger — ${data.vendor_name}`)}
          />
        </div>
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {data && (
        <>
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-semibold text-gray-800">{data.vendor_name}</div>
              {data.vendor_gstin && <div className="text-xs text-gray-400 font-mono">{data.vendor_gstin}</div>}
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-400">Closing Balance (Payable)</div>
              <div className={clsx('text-lg font-semibold', data.closing_balance > 0 ? 'text-danger' : 'text-success')}>
                {fmt(data.closing_balance)}
              </div>
            </div>
          </div>
          {data.rows.length === 0 ? <Empty message="No ledger entries for this period" /> : (
            <table className="table">
              <thead><tr><th>Date</th><th>Narration</th><th className="text-right">Debit (₹)</th><th className="text-right">Credit (₹)</th><th className="text-right">Balance (₹)</th></tr></thead>
              <tbody>
                <tr className="bg-gray-50 font-medium">
                  <td>{dateFrom ? format(new Date(dateFrom), 'dd MMM yyyy') : '—'}</td>
                  <td className="text-gray-500 italic">Opening Balance</td>
                  <td colSpan={2}></td>
                  <td className="text-right">{fmt(data.opening_balance)}</td>
                </tr>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    <td className="text-gray-500 text-xs">{row.date ? format(new Date(row.date), 'dd MMM yyyy') : '—'}</td>
                    <td className="text-sm">{row.narration}</td>
                    <td className="text-right text-sm">{row.debit > 0 ? fmt(row.debit) : '—'}</td>
                    <td className="text-right text-sm text-danger">{row.credit > 0 ? fmt(row.credit) : '—'}</td>
                    <td className="text-right font-medium">{fmt(row.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

// ── Main Reports Page ─────────────────────────────────────────
export default function ReportsPage() {
  const [searchParams] = useSearchParams()
  const isSuperAdmin = useAuthStore(s => s.isSuperAdmin())
  const visibleTabs = isSuperAdmin ? TABS : TABS.filter(t => !PROFIT_TABS.includes(t))
  const initialTab = searchParams.get('tab') || 'Sales'
  const [activeTab, setActiveTab] = useState(
    visibleTabs.find(t => t.toLowerCase() === initialTab.toLowerCase()) || 'Sales'
  )

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Reports</div>
          <h1 className="page-title">Reports & Analytics</h1>
        </div>
      </div>
      <div className="flex border-b border-gray-200 mb-4 overflow-x-auto">
        {visibleTabs.map(tab => (
          <button key={tab}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700')}
            onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
      </div>
      <div className="card"><div className="p-4">
        {activeTab === 'Sales' && <SalesReport />}
        {activeTab === 'Purchase' && <PurchaseReport />}
        {activeTab === 'Stock' && <StockReport />}
        {activeTab === 'Clearance' && <ClearanceReport />}
        {activeTab === 'P&L' && <PnLReport />}
        {activeTab === 'Day Book' && <DayBookReport />}
        {activeTab === 'Customer Ledger' && <CustomerLedgerReport />}
        {activeTab === 'Vendor Ledger' && <VendorLedgerReport />}
      </div></div>
    </div>
  )
}
