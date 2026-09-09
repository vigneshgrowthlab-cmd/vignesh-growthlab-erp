import { useState, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { einvoiceAPI, ewayAPI, gstr1API, gstr2bAPI, gstr3bAPI, transporterAPI, vehicleAPI } from '@/api/gst'
import { Button, Badge, Select, Field, AlertBox, Spinner, Empty } from '@/components/ui'
import { Plus, Zap, AlertTriangle, CheckCircle, X, Pencil, Trash2 } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

const TABS = ['E-Invoice', 'E-Way Bill', 'GSTR-1', 'GSTR-2B', 'GSTR-3B', 'Masters']

// Indian FY runs Apr → Mar. For fy "2025-26" → Apr 2025 .. Mar 2026.
const fyLabel = (startYear) => `${startYear}-${String((startYear + 1) % 100).padStart(2, '0')}`

function currentFy() {
  const now = new Date()
  return fyLabel(now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1)
}

const FY_OPTIONS = Array.from({ length: 4 }, (_, i) =>
  fyLabel(Number(currentFy().split('-')[0]) - i))

function periodsForFy(fy) {
  const startYear = Number(String(fy).split('-')[0])
  const months = []
  for (let m = 4; m <= 12; m++) months.push({ y: startYear, m })
  for (let m = 1; m <= 3; m++) months.push({ y: startYear + 1, m })
  return months.map(({ y, m }) => {
    const mm = String(m).padStart(2, '0')
    return { value: `${mm}-${y}`, label: new Date(y, m - 1, 1).toLocaleString('en-IN', { month: 'long', year: 'numeric' }) }
  })
}

const ic = (err) => clsx(
  'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
  err ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
)

// ─── E-Invoice Tab ────────────────────────────────────────────
function EInvoiceTab() {
  const qc = useQueryClient()
  const [form, setForm] = useState({ invoice_id: '', invoice_number_search: '', invoice_number_resolved: '' })
  const [errors, setErrors] = useState({})
  const [showCancel, setShowCancel] = useState(null)
  const [cancelReason, setCancelReason] = useState('')

  const { data: logs, isLoading } = useQuery({
    queryKey: ['einvoice-logs'],
    queryFn: () => einvoiceAPI.logs({ page_size: 50 }).then(r => r.data),
  })

  const generateMutation = useMutation({
    mutationFn: (d) => einvoiceAPI.generate(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['einvoice-logs'])
      if (res.data.irn) toast.success(`IRN generated: ${res.data.irn.substring(0, 20)}...`)
      else toast.error(res.data.error_message || 'Failed to generate IRN')
      setForm({ invoice_id: '', invoice_number_search: '', invoice_number_resolved: '' })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const cancelMutation = useMutation({
    mutationFn: (d) => einvoiceAPI.cancel(d),
    onSuccess: () => {
      qc.invalidateQueries(['einvoice-logs'])
      toast.success('IRN cancelled successfully')
      setShowCancel(null); setCancelReason('')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const STATUS_COLORS = { generated: 'green', pending: 'amber', failed: 'red', cancelled: 'gray' }

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const resolveInvoice = async () => {
    const val = form.invoice_number_search?.trim()
    if (!val) return
    try {
      const { invoiceAPI } = await import('@/api/billing')
      const res = await invoiceAPI.list({ search: val, page_size: 5 })
      const match = res.data?.items?.find(i => i.invoice_number === val)
      if (match) {
        setForm(p => ({ ...p, invoice_id: String(match.id), invoice_number_resolved: match.invoice_number }))
        setErrors(p => ({ ...p, invoice_id: '' }))
      } else {
        setForm(p => ({ ...p, invoice_id: '', invoice_number_resolved: '' }))
        toast.error(`Invoice "${val}" not found`)
      }
    } catch { toast.error('Failed to lookup invoice') }
  }

  const handleGenerate = () => {
    if (!form.invoice_id || isNaN(Number(form.invoice_id))) {
      setErrors({ invoice_id: 'Enter a valid invoice number' })
      toast.error('Enter a valid invoice number')
      return
    }
    generateMutation.mutate({ invoice_id: Number(form.invoice_id) })
  }

  return (
    <div>
      <AlertBox type="info" className="mb-4">
        E-Invoice (IRN) generation is via Cleartax API. Set CLEARTAX_SANDBOX=true in .env for testing without real API calls.
      </AlertBox>

      <div className="card mb-4">
        <div className="card-header"><h3 className="font-semibold">Generate IRN</h3></div>
        <div className="card-body">
          <div className="flex gap-3 items-end">
            <div className="w-64">
              <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Number <span className="text-red-500">*</span></label>
              <input
                type="text"
                value={form.invoice_number_search}
                onChange={e => hc('invoice_number_search', e.target.value)}
                onBlur={resolveInvoice}
                placeholder="e.g. GLB/26-27/001"
                className={ic(errors.invoice_id)}
              />
              {form.invoice_number_resolved
                ? <p className="text-xs text-green-600 mt-1">✓ ID: {form.invoice_id} — {form.invoice_number_resolved}</p>
                : <p className="text-xs text-gray-400 mt-1">Enter the invoice number from the Billing module</p>}
              {errors.invoice_id && <p className="text-xs text-red-500 mt-1">{errors.invoice_id}</p>}
            </div>
            <Button variant="primary" loading={generateMutation.isPending}
              disabled={!form.invoice_id} onClick={handleGenerate}>
              <Zap size={14} /> Generate IRN
            </Button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3 className="font-semibold">E-Invoice Log</h3></div>
        {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
          logs?.items?.length === 0 ? <Empty message="No E-Invoice logs yet" /> : (
            <table className="table">
              <thead><tr><th>Invoice No.</th><th>Status</th><th>IRN</th><th>Date</th><th>Action</th></tr></thead>
              <tbody>
                {logs?.items?.map(log => (
                  <tr key={log.id}>
                    <td className="font-mono text-xs font-medium">{log.invoice_number}</td>
                    <td><Badge color={STATUS_COLORS[log.status] || 'gray'}>{log.status}</Badge></td>
                    <td className="font-mono text-xs text-gray-500 max-w-xs truncate">{log.irn || log.error_message || '—'}</td>
                    <td className="text-gray-500 text-xs">{log.created_at ? format(new Date(log.created_at), 'dd MMM yyyy HH:mm') : '—'}</td>
                    <td>
                      {log.status === 'generated' && log.irn && (
                        <button onClick={() => { setShowCancel(log); setCancelReason('') }}
                          className="text-xs px-2 py-1 rounded bg-red-50 text-red-600 hover:bg-red-100">
                          Cancel IRN
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>

      {showCancel && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="font-semibold mb-2">Cancel IRN — {showCancel.invoice_number}</h3>
            <p className="text-sm text-gray-500 mb-4 font-mono text-xs">{showCancel.irn}</p>
            <div className="mb-4">
              <label className="block text-xs font-medium text-gray-600 mb-1">Cancellation Reason <span className="text-red-500">*</span></label>
              <input value={cancelReason} onChange={e => setCancelReason(e.target.value)}
                placeholder="Reason for cancellation..." className={ic(!cancelReason)} />
            </div>
            <div className="flex gap-3 justify-end">
              <Button variant="secondary" onClick={() => setShowCancel(null)}>Close</Button>
              <Button variant="danger" loading={cancelMutation.isPending}
                disabled={!cancelReason}
                onClick={() => cancelMutation.mutate({ invoice_id: showCancel.invoice_id, cancel_reason: cancelReason })}>
                Cancel IRN
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── E-Way Bill Tab ───────────────────────────────────────────
function EWayBillTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    invoice_id: '', invoice_number_search: '', invoice_number_resolved: '',
    transporter_id: '', vehicle_id: '',
    vehicle_number: '', transporter_name: '',
    transport_mode: 'road', distance_km: '',
  })
  const [errors, setErrors] = useState({})

  const { data: transporters } = useQuery({ queryKey: ['transporters'], queryFn: () => transporterAPI.list().then(r => r.data) })
  const { data: vehicles } = useQuery({ queryKey: ['vehicles'], queryFn: () => vehicleAPI.list().then(r => r.data) })
  const { data: logs, isLoading } = useQuery({
    queryKey: ['eway-logs'],
    queryFn: () => ewayAPI.logs({ page_size: 50 }).then(r => r.data),
  })

  const generateMutation = useMutation({
    mutationFn: (d) => ewayAPI.generate(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['eway-logs'])
      if (res.data.eway_bill_number) {
        toast.success(`E-Way Bill: ${res.data.eway_bill_number}`)
        setShowForm(false)
        setForm({ invoice_id: '', invoice_number_search: '', invoice_number_resolved: '', transporter_id: '', vehicle_id: '', vehicle_number: '', transporter_name: '', transport_mode: 'road', distance_km: '' })
      } else {
        toast.error(res.data.error_message || 'Failed to generate E-Way Bill')
      }
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.invoice_id || isNaN(Number(form.invoice_id))) errs.invoice_id = 'Enter valid invoice ID'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    generateMutation.mutate({
      invoice_id: Number(form.invoice_id),
      transporter_id: form.transporter_id ? Number(form.transporter_id) : null,
      vehicle_id: form.vehicle_id ? Number(form.vehicle_id) : null,
      vehicle_number: form.vehicle_number || null,
      transporter_name: form.transporter_name || null,
      transport_mode: form.transport_mode,
      distance_km: form.distance_km ? Number(form.distance_km) : null,
    })
  }

  return (
    <div>
      <AlertBox type="info" className="mb-4">
        E-Way Bill is required for invoices above ₹50,000. Distance is auto-calculated from company pincode to shipping address pincode.
      </AlertBox>

      <div className="flex justify-end mb-4">
        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}><Plus size={14} /> Generate E-Way Bill</Button>
      </div>

      {showForm && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">Generate E-Way Bill</h3>
            <button onClick={() => { setShowForm(false); setErrors({}) }} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Number <span className="text-red-500">*</span></label>
                <input type="text" value={form.invoice_number_search} onChange={e => hc('invoice_number_search', e.target.value)}
                  placeholder="e.g. GLB/26-27/001" className={ic(errors.invoice_id)}
                  onBlur={async () => {
                    const val = form.invoice_number_search?.trim()
                    if (!val) return
                    try {
                      const { invoiceAPI } = await import('@/api/billing')
                      const res = await invoiceAPI.list({ search: val, page_size: 5 })
                      const match = res.data?.items?.find(i => i.invoice_number === val)
                      if (match) {
                        hc('invoice_id', String(match.id))
                        hc('invoice_number_resolved', match.invoice_number)
                      } else {
                        hc('invoice_id', '')
                        hc('invoice_number_resolved', '')
                        toast.error(`Invoice "${val}" not found`)
                      }
                    } catch { toast.error('Failed to lookup invoice') }
                  }}
                />
                {form.invoice_number_resolved && (
                  <p className="text-xs text-green-600 mt-1">✓ ID: {form.invoice_id} — {form.invoice_number_resolved}</p>
                )}
                {errors.invoice_id && <p className="text-xs text-red-500 mt-1">{errors.invoice_id}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Transport Mode</label>
                <select value={form.transport_mode} onChange={e => hc('transport_mode', e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="road">Road</option>
                  <option value="rail">Rail</option>
                  <option value="air">Air</option>
                  <option value="ship">Ship</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Transporter</label>
                <select value={form.transporter_id} onChange={e => hc('transporter_id', e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select transporter...</option>
                  {transporters?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Vehicle</label>
                <select value={form.vehicle_id} onChange={e => hc('vehicle_id', e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select vehicle...</option>
                  {vehicles?.map(v => <option key={v.id} value={v.id}>{v.vehicle_number} ({v.vehicle_type})</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Manual Transporter Name</label>
                <input value={form.transporter_name} onChange={e => hc('transporter_name', e.target.value)}
                  placeholder="If not in master" className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Manual Vehicle Number</label>
                <input value={form.vehicle_number} onChange={e => hc('vehicle_number', e.target.value.toUpperCase())}
                  placeholder="KA01AB1234" className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Distance (km)</label>
                <input type="number" min="1" value={form.distance_km} onChange={e => hc('distance_km', e.target.value)}
                  placeholder="Auto-calculated" className={ic()} />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowForm(false); setErrors({}) }}>Cancel</Button>
              <Button variant="primary" loading={generateMutation.isPending} onClick={handleSubmit}>
                Generate E-Way Bill
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header"><h3 className="font-semibold">E-Way Bill Log</h3></div>
        {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
          logs?.items?.length === 0 ? <Empty message="No E-Way Bills generated yet" /> : (
            <table className="table">
              <thead><tr><th>Invoice No.</th><th>E-Way Bill No.</th><th>Vehicle</th><th>Transporter</th><th>Distance</th><th>Date</th></tr></thead>
              <tbody>
                {logs?.items?.map(log => (
                  <tr key={log.id}>
                    <td className="font-mono text-xs font-medium">{log.invoice_number}</td>
                    <td className="font-mono text-xs font-semibold text-blue-600">{log.eway_bill_number}</td>
                    <td className="text-gray-600 text-sm">{log.vehicle_number || '—'}</td>
                    <td className="text-gray-600 text-sm">{log.transporter_name || '—'}</td>
                    <td className="text-gray-500 text-sm">{log.distance_km ? `${log.distance_km} km` : '—'}</td>
                    <td className="text-gray-500 text-xs">{log.created_at ? format(new Date(log.created_at), 'dd MMM yyyy') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </div>
  )
}

// ─── GSTR-1 Tab ───────────────────────────────────────────────
function GSTR1Tab() {
  const [fy, setFy] = useState(currentFy)
  const [period, setPeriod] = useState(() => periodsForFy(currentFy())[0].value)
  const periods = periodsForFy(fy)
  const { data: gstr1, isLoading, refetch } = useQuery({
    queryKey: ['gstr1', period, fy],
    queryFn: () => gstr1API.get({ period, financial_year: fy }).then(r => r.data),
    enabled: false,
  })

  const exportFile = async (fmt) => {
    try {
      const call = fmt === 'json' ? gstr1API.exportJson : gstr1API.exportExcel
      const res = await call({ period, financial_year: fy })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `GSTR1_${period}.${fmt === 'json' ? 'json' : 'xlsx'}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Export failed')
    }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={period} onChange={e => setPeriod(e.target.value)}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm w-48 focus:outline-none focus:border-blue-500">
          {periods.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={fy} onChange={e => { setFy(e.target.value); setPeriod(periodsForFy(e.target.value)[0].value) }}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm w-32 focus:outline-none focus:border-blue-500">
          {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        <Button variant="primary" onClick={() => refetch()}>Generate GSTR-1</Button>
        <Button variant="secondary" onClick={() => exportFile('excel')}>Export Excel</Button>
        <Button variant="secondary" onClick={() => exportFile('json')}>Portal JSON</Button>
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {gstr1 && (
        <>
          <div className="grid grid-cols-6 gap-3 mb-6">
            {[
              { label: 'Total Invoices', val: gstr1.invoice_count, fmt: 'count' },
              { label: 'Taxable Value', val: gstr1.total_taxable, fmt: 'currency' },
              { label: 'IGST', val: gstr1.total_igst, fmt: 'currency' },
              { label: 'CGST', val: gstr1.total_cgst, fmt: 'currency' },
              { label: 'SGST', val: gstr1.total_sgst, fmt: 'currency' },
              { label: 'Total Tax', val: gstr1.total_tax, fmt: 'currency', highlight: true },
            ].map(card => (
              <div key={card.label} className={clsx('stat-card', card.highlight && 'border-blue-200 border')}>
                <div className="stat-label">{card.label}</div>
                <div className={clsx('stat-value', card.highlight && 'text-blue-600')}>
                  {card.fmt === 'currency' ? `₹${Number(card.val).toLocaleString('en-IN', { minimumFractionDigits: 0 })}` : card.val}
                </div>
              </div>
            ))}
          </div>
          <h3 className="font-semibold text-gray-700 mb-3">B2B Invoices ({gstr1.b2b_count})</h3>
          {gstr1.b2b_invoices?.length === 0 ? <div className="text-sm text-gray-400 py-4">No B2B invoices for this period</div> : (
            <table className="table">
              <thead><tr><th>Invoice No.</th><th>Date</th><th>Customer GSTIN</th><th>Customer</th><th className="text-right">Value</th><th className="text-right">IGST</th><th className="text-right">CGST</th><th className="text-right">SGST</th><th>IRN</th></tr></thead>
              <tbody>
                {gstr1.b2b_invoices?.map((inv, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs">{inv.invoice_number}</td>
                    <td className="text-gray-500 text-xs">{inv.invoice_date ? format(new Date(inv.invoice_date), 'dd/MM/yyyy') : '—'}</td>
                    <td className="font-mono text-xs">{inv.customer_gstin}</td>
                    <td className="text-sm">{inv.customer_name}</td>
                    <td className="text-right text-sm">₹{Number(inv.invoice_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(inv.igst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(inv.cgst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(inv.sgst).toFixed(0)}</td>
                    <td>{inv.irn ? <Badge color="green">IRN ✓</Badge> : <Badge color="amber">No IRN</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3 className="font-semibold text-gray-700 mb-3 mt-6">
            B2C Large — inter-state &gt; ₹{Number(gstr1.b2cl_threshold || 250000).toLocaleString('en-IN', { minimumFractionDigits: 0 })} ({gstr1.b2cl_count || 0})
          </h3>
          {(!gstr1.b2cl_invoices || gstr1.b2cl_invoices.length === 0) ? <div className="text-sm text-gray-400 py-4">No B2CL invoices for this period</div> : (
            <table className="table">
              <thead><tr><th>Invoice No.</th><th>Date</th><th>POS (State)</th><th className="text-right">Value</th><th className="text-right">Taxable</th><th className="text-right">IGST</th></tr></thead>
              <tbody>
                {gstr1.b2cl_invoices?.map((inv, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs">{inv.invoice_number}</td>
                    <td className="text-gray-500 text-xs">{inv.invoice_date ? format(new Date(inv.invoice_date), 'dd/MM/yyyy') : '—'}</td>
                    <td className="text-sm">{inv.state || '—'}{inv.state_code ? ` (${inv.state_code})` : ''}</td>
                    <td className="text-right text-sm">₹{Number(inv.invoice_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(inv.taxable_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(inv.igst).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3 className="font-semibold text-gray-700 mb-3 mt-6">B2C Small — summary by POS &amp; rate ({gstr1.b2cs_count || 0})</h3>
          {(!gstr1.b2cs_summary || gstr1.b2cs_summary.length === 0) ? <div className="text-sm text-gray-400 py-4">No B2CS supplies for this period</div> : (
            <table className="table">
              <thead><tr><th>POS (State)</th><th>Supply</th><th className="text-right">Rate %</th><th className="text-right">Taxable</th><th className="text-right">IGST</th><th className="text-right">CGST</th><th className="text-right">SGST</th></tr></thead>
              <tbody>
                {gstr1.b2cs_summary?.map((s, i) => (
                  <tr key={i}>
                    <td className="text-sm">{s.state || '—'}{s.state_code ? ` (${s.state_code})` : ''}</td>
                    <td><Badge color={s.supply_type === 'inter' ? 'amber' : 'gray'}>{s.supply_type === 'inter' ? 'Inter' : 'Intra'}</Badge></td>
                    <td className="text-right text-sm text-gray-500">{Number(s.gst_rate).toFixed(0)}%</td>
                    <td className="text-right text-sm">₹{Number(s.taxable_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(s.igst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(s.cgst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(s.sgst).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3 className="font-semibold text-gray-700 mb-3 mt-6">HSN Summary ({gstr1.hsn_summary?.length || 0})</h3>
          {gstr1.hsn_summary?.length === 0 ? <div className="text-sm text-gray-400 py-4">No HSN data for this period</div> : (
            <table className="table">
              <thead><tr><th>HSN</th><th>Description</th><th>UOM</th><th className="text-right">Qty</th><th className="text-right">Rate %</th><th className="text-right">Taxable</th><th className="text-right">IGST</th><th className="text-right">CGST</th><th className="text-right">SGST</th></tr></thead>
              <tbody>
                {gstr1.hsn_summary?.map((h, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs">{h.hsn_code}</td>
                    <td className="text-sm">{h.description || '—'}</td>
                    <td className="text-xs text-gray-500">{h.uom}</td>
                    <td className="text-right text-sm">{Number(h.total_quantity).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">{Number(h.gst_rate).toFixed(0)}%</td>
                    <td className="text-right text-sm">₹{Number(h.taxable_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(h.igst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(h.cgst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(h.sgst).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3 className="font-semibold text-gray-700 mb-3 mt-6">Credit Notes ({gstr1.credit_note_count || 0})</h3>
          {(!gstr1.credit_notes || gstr1.credit_notes.length === 0) ? <div className="text-sm text-gray-400 py-4">No credit notes for this period</div> : (
            <table className="table">
              <thead><tr><th>Note No.</th><th>Date</th><th>Against Invoice</th><th>Customer GSTIN</th><th>Customer</th><th>Type</th><th className="text-right">Value</th><th className="text-right">IGST</th><th className="text-right">CGST</th><th className="text-right">SGST</th></tr></thead>
              <tbody>
                {gstr1.credit_notes?.map((cn, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs">{cn.note_number}</td>
                    <td className="text-gray-500 text-xs">{cn.note_date ? format(new Date(cn.note_date), 'dd/MM/yyyy') : '—'}</td>
                    <td className="font-mono text-xs">{cn.original_invoice_number || '—'}</td>
                    <td className="font-mono text-xs">{cn.customer_gstin || '—'}</td>
                    <td className="text-sm">{cn.customer_name}</td>
                    <td><Badge color={cn.registered ? 'blue' : 'gray'}>{cn.registered ? 'CDNR' : 'CDNUR'}</Badge></td>
                    <td className="text-right text-sm text-red-600">−₹{Number(cn.note_value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(cn.igst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(cn.cgst).toFixed(0)}</td>
                    <td className="text-right text-sm text-gray-500">₹{Number(cn.sgst).toFixed(0)}</td>
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

// ─── GSTR-2B Tab ──────────────────────────────────────────────
function GSTR2BTab() {
  const [fy, setFy] = useState(currentFy)
  const [period, setPeriod] = useState(() => periodsForFy(currentFy())[0].value)
  const periods = periodsForFy(fy)
  const [result, setResult] = useState(null)
  const sampleEntries = [{ supplier_gstin: '29AAAAA0000A1Z5', supplier_name: 'Sample Supplier', invoice_number: 'INV-001', invoice_date: '2026-01-15', invoice_value: 11800, taxable_value: 10000, igst: 0, cgst: 900, sgst: 900 }]
  const reconcileMutation = useMutation({
    mutationFn: (d) => gstr2bAPI.reconcile(d),
    onSuccess: (res) => { setResult(res.data); toast.success('GSTR-2B reconciliation complete') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })
  return (
    <div>
      <AlertBox type="info" className="mb-4">Import your GSTR-2B data from the GST portal to match against your purchase entries and flag ITC mismatches.</AlertBox>
      <div className="card mb-4">
        <div className="card-header"><h3 className="font-semibold">Import & Reconcile GSTR-2B</h3></div>
        <div className="card-body space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Period"><Select value={period} onChange={e => setPeriod(e.target.value)}>{periods.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}</Select></Field>
            <Field label="Financial Year"><Select value={fy} onChange={e => { setFy(e.target.value); setPeriod(periodsForFy(e.target.value)[0].value) }}>{FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}</Select></Field>
          </div>
          <AlertBox type="warning">Demo mode — click Reconcile to run against sample data.</AlertBox>
          <Button variant="primary" loading={reconcileMutation.isPending}
            onClick={() => reconcileMutation.mutate({ financial_year: fy, period, entries: sampleEntries })}>
            Run Reconciliation
          </Button>
        </div>
      </div>
      {result && (
        <div className="grid grid-cols-4 gap-3">
          <div className="stat-card"><div className="stat-label">Matched</div><div className="stat-value text-green-600">{result.matched_count}</div></div>
          <div className="stat-card"><div className="stat-label">Unmatched in GSTR-2B</div><div className="stat-value text-red-600">{result.unmatched_gstr2b_count}</div></div>
          <div className="stat-card"><div className="stat-label">Not in GSTR-2B</div><div className="stat-value text-amber-600">{result.unmatched_books_count}</div></div>
          <div className="stat-card"><div className="stat-label">ITC at Risk</div><div className="stat-value text-red-600">₹{Number(result.itc_at_risk || 0).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</div></div>
        </div>
      )}
    </div>
  )
}

// ─── GSTR-3B Tab ──────────────────────────────────────────────
function GSTR3BTab() {
  const [fy, setFy] = useState(currentFy)
  const [period, setPeriod] = useState(() => periodsForFy(currentFy())[0].value)
  const periods = periodsForFy(fy)
  const { data: gstr3b, isLoading, refetch } = useQuery({
    queryKey: ['gstr3b', period, fy],
    queryFn: () => gstr3bAPI.get({ period, financial_year: fy }).then(r => r.data),
    enabled: false,
  })
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={period} onChange={e => setPeriod(e.target.value)}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm w-48 focus:outline-none focus:border-blue-500">
          {periods.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={fy} onChange={e => { setFy(e.target.value); setPeriod(periodsForFy(e.target.value)[0].value) }}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm w-32 focus:outline-none focus:border-blue-500">
          {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        <Button variant="primary" onClick={() => refetch()}>Generate GSTR-3B</Button>
      </div>
      {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}
      {gstr3b && (
        <div className="max-w-2xl space-y-4">
          <div className="card">
            <div className="card-header"><h3 className="font-semibold">3.1 — Output Tax Liability</h3></div>
            <div className="card-body">
              <table className="table">
                <thead><tr><th>Tax Type</th><th className="text-right">IGST</th><th className="text-right">CGST</th><th className="text-right">SGST</th></tr></thead>
                <tbody>
                  <tr><td className="font-medium">Outward Supplies</td><td className="text-right">₹{Number(gstr3b.output_igst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td><td className="text-right">₹{Number(gstr3b.output_cgst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td><td className="text-right">₹{Number(gstr3b.output_sgst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td></tr>
                  <tr className="font-semibold bg-gray-50"><td>Total Output Tax</td><td colSpan={3} className="text-right text-red-600">₹{Number(gstr3b.total_output_tax).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="card border-2 border-blue-200">
            <div className="card-header bg-blue-50"><h3 className="font-semibold text-blue-700">6.1 — Net Tax Payable</h3></div>
            <div className="card-body">
              <div className="text-2xl font-bold text-blue-600">₹{Number(gstr3b.net_tax_payable).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
              <div className="text-sm text-gray-500 mt-1">Output Tax ₹{Number(gstr3b.total_output_tax).toFixed(2)} — ITC ₹{Number(gstr3b.total_itc).toFixed(2)}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Masters Tab ──────────────────────────────────────────────
function MastersTab() {
  const qc = useQueryClient()
  const EMPTY_T = { name: '', gstin: '', phone: '', email: '', contact_person: '' }
  const EMPTY_V = { vehicle_number: '', vehicle_type: 'truck', owner_name: '', transporter_id: '' }

  const [showTransporter, setShowTransporter] = useState(false)
  const [showVehicle, setShowVehicle] = useState(false)
  const [editingT, setEditingT] = useState(null)  // transporter row being edited
  const [editingV, setEditingV] = useState(null)  // vehicle row being edited

  const [tForm, setTForm] = useState(EMPTY_T)
  const [tErrors, setTErrors] = useState({})
  const [vForm, setVForm] = useState(EMPTY_V)
  const [vErrors, setVErrors] = useState({})
  const [editTForm, setEditTForm] = useState(EMPTY_T)
  const [editVForm, setEditVForm] = useState(EMPTY_V)

  const { data: transporters } = useQuery({ queryKey: ['transporters'], queryFn: () => transporterAPI.list().then(r => r.data) })
  const { data: vehicles } = useQuery({ queryKey: ['vehicles'], queryFn: () => vehicleAPI.list().then(r => r.data) })

  const tCreateM = useMutation({
    mutationFn: (d) => transporterAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['transporters'])
      toast.success('Transporter added')
      setShowTransporter(false)
      setTForm(EMPTY_T)
      setTErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const tUpdateM = useMutation({
    mutationFn: ({ id, data }) => transporterAPI.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries(['transporters'])
      toast.success('Transporter updated')
      setEditingT(null)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const tDeleteM = useMutation({
    mutationFn: (id) => transporterAPI.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['transporters'])
      qc.invalidateQueries(['vehicles'])
      toast.success('Transporter removed')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const vCreateM = useMutation({
    mutationFn: (d) => vehicleAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['vehicles'])
      toast.success('Vehicle added')
      setShowVehicle(false)
      setVForm(EMPTY_V)
      setVErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const vUpdateM = useMutation({
    mutationFn: ({ id, data }) => vehicleAPI.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries(['vehicles'])
      toast.success('Vehicle updated')
      setEditingV(null)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const vDeleteM = useMutation({
    mutationFn: (id) => vehicleAPI.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['vehicles'])
      toast.success('Vehicle removed')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const startEditT = (t) => {
    setEditingT(t.id)
    setEditTForm({ name: t.name, gstin: t.gstin || '', phone: t.phone || '', email: t.email || '', contact_person: t.contact_person || '' })
    setShowTransporter(false)
  }

  const startEditV = (v) => {
    setEditingV(v.id)
    setEditVForm({ vehicle_number: v.vehicle_number, vehicle_type: v.vehicle_type, owner_name: v.owner_name || '', transporter_id: v.transporter_id ? String(v.transporter_id) : '' })
    setShowVehicle(false)
  }

  const sel = 'w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500'

  return (
    <div className="space-y-6">
      {/* Transporters */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-700">Transporters</h3>
          <Button variant="secondary" size="sm" onClick={() => { setShowTransporter(v => !v); setEditingT(null) }}><Plus size={12} /> Add Transporter</Button>
        </div>
        {showTransporter && (
          <div className="card mb-3 border-2 border-blue-200">
            <div className="card-header flex justify-between">
              <h4 className="font-medium text-gray-700">New Transporter</h4>
              <button onClick={() => { setShowTransporter(false); setTErrors({}) }} className="text-gray-400"><X size={14} /></button>
            </div>
            <div className="card-body space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-red-500">*</span></label>
                  <input value={tForm.name} onChange={e => { setTForm(p => ({ ...p, name: e.target.value })); setTErrors({}) }}
                    placeholder="ABC Logistics" className={ic(tErrors.name)} />
                  {tErrors.name && <p className="text-xs text-red-500 mt-1">{tErrors.name}</p>}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">GSTIN</label>
                  <input value={tForm.gstin} onChange={e => setTForm(p => ({ ...p, gstin: e.target.value.toUpperCase() }))}
                    placeholder="29AAAAA0000A1Z5" maxLength={15} className={ic()} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
                  <input value={tForm.phone} onChange={e => setTForm(p => ({ ...p, phone: e.target.value }))}
                    placeholder="+91 98765 43210" className={ic()} />
                </div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="secondary" onClick={() => { setShowTransporter(false); setTErrors({}) }}>Cancel</Button>
                <Button variant="primary" loading={tCreateM.isPending} onClick={() => { if (!tForm.name) { setTErrors({ name: 'Required' }); return } tCreateM.mutate(tForm) }}>Add Transporter</Button>
              </div>
            </div>
          </div>
        )}
        {!transporters?.length ? <div className="text-sm text-gray-400 py-4">No transporters added yet</div> : (
          <table className="table">
            <thead><tr><th>Name</th><th>GSTIN</th><th>Phone</th></tr></thead>
            <tbody>
              {transporters?.map(t => (
                <Fragment key={t.id}>
                  <tr>
                    <td className="font-medium">{t.name}</td>
                    <td className="font-mono text-xs text-gray-500">{t.gstin || '—'}</td>
                    <td>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-gray-500">{t.phone || '—'}</span>
                        <div className="flex items-center gap-0.5 flex-shrink-0">
                          <button onClick={() => editingT === t.id ? setEditingT(null) : startEditT(t)}
                            className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600">
                            <Pencil size={13} />
                          </button>
                          <button onClick={() => { if (window.confirm(`Remove transporter "${t.name}"?`)) tDeleteM.mutate(t.id) }}
                            disabled={tDeleteM.isPending}
                            className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 disabled:opacity-50">
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                  {editingT === t.id && (
                    <tr>
                      <td colSpan={3} className="bg-blue-50 px-3 py-3">
                        <div className="grid grid-cols-3 gap-3 mb-2">
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-red-500">*</span></label>
                            <input value={editTForm.name} onChange={e => setEditTForm(p => ({ ...p, name: e.target.value }))} className={ic()} />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">GSTIN</label>
                            <input value={editTForm.gstin} onChange={e => setEditTForm(p => ({ ...p, gstin: e.target.value.toUpperCase() }))} maxLength={15} className={ic()} />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
                            <input value={editTForm.phone} onChange={e => setEditTForm(p => ({ ...p, phone: e.target.value }))} className={ic()} />
                          </div>
                        </div>
                        <div className="flex gap-2 justify-end">
                          <Button variant="secondary" size="sm" onClick={() => setEditingT(null)}>Cancel</Button>
                          <Button variant="primary" size="sm" loading={tUpdateM.isPending}
                            onClick={() => { if (!editTForm.name) return; tUpdateM.mutate({ id: t.id, data: editTForm }) }}>
                            Save
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Vehicles */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-700">Vehicles</h3>
          <Button variant="secondary" size="sm" onClick={() => { setShowVehicle(v => !v); setEditingV(null) }}><Plus size={12} /> Add Vehicle</Button>
        </div>
        {showVehicle && (
          <div className="card mb-3 border-2 border-blue-200">
            <div className="card-header flex justify-between">
              <h4 className="font-medium text-gray-700">New Vehicle</h4>
              <button onClick={() => { setShowVehicle(false); setVErrors({}) }} className="text-gray-400"><X size={14} /></button>
            </div>
            <div className="card-body space-y-3">
              <div className="grid grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Vehicle Number <span className="text-red-500">*</span></label>
                  <input value={vForm.vehicle_number} onChange={e => { setVForm(p => ({ ...p, vehicle_number: e.target.value.toUpperCase() })); setVErrors({}) }}
                    placeholder="KA01AB1234" className={ic(vErrors.vehicle_number)} />
                  {vErrors.vehicle_number && <p className="text-xs text-red-500 mt-1">{vErrors.vehicle_number}</p>}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                  <select value={vForm.vehicle_type} onChange={e => setVForm(p => ({ ...p, vehicle_type: e.target.value }))} className={sel}>
                    <option value="truck">Truck</option><option value="tempo">Tempo</option>
                    <option value="bike">Bike</option><option value="other">Other</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Owner Name</label>
                  <input value={vForm.owner_name} onChange={e => setVForm(p => ({ ...p, owner_name: e.target.value }))} placeholder="Owner" className={ic()} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Transporter</label>
                  <select value={vForm.transporter_id} onChange={e => setVForm(p => ({ ...p, transporter_id: e.target.value }))} className={sel}>
                    <option value="">None</option>
                    {transporters?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="secondary" onClick={() => { setShowVehicle(false); setVErrors({}) }}>Cancel</Button>
                <Button variant="primary" loading={vCreateM.isPending} onClick={() => { if (!vForm.vehicle_number) { setVErrors({ vehicle_number: 'Required' }); return } vCreateM.mutate({ ...vForm, transporter_id: vForm.transporter_id ? Number(vForm.transporter_id) : null }) }}>Add Vehicle</Button>
              </div>
            </div>
          </div>
        )}
        {!vehicles?.length ? <div className="text-sm text-gray-400 py-4">No vehicles added yet</div> : (
          <table className="table">
            <thead><tr><th>Vehicle No.</th><th>Type</th><th>Owner</th><th>Transporter</th></tr></thead>
            <tbody>
              {vehicles?.map(v => (
                <Fragment key={v.id}>
                  <tr>
                    <td className="font-mono font-semibold text-sm">{v.vehicle_number}</td>
                    <td><Badge color="gray">{v.vehicle_type}</Badge></td>
                    <td className="text-gray-600">{v.owner_name || '—'}</td>
                    <td>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-gray-500">{v.transporter_name || '—'}</span>
                        <div className="flex items-center gap-0.5 flex-shrink-0">
                          <button onClick={() => editingV === v.id ? setEditingV(null) : startEditV(v)}
                            className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600">
                            <Pencil size={13} />
                          </button>
                          <button onClick={() => { if (window.confirm(`Remove vehicle "${v.vehicle_number}"?`)) vDeleteM.mutate(v.id) }}
                            disabled={vDeleteM.isPending}
                            className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 disabled:opacity-50">
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                  {editingV === v.id && (
                    <tr>
                      <td colSpan={4} className="bg-blue-50 px-3 py-3">
                        <div className="grid grid-cols-4 gap-3 mb-2">
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Vehicle Number</label>
                            <input value={editVForm.vehicle_number} onChange={e => setEditVForm(p => ({ ...p, vehicle_number: e.target.value.toUpperCase() }))} className={ic()} />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                            <select value={editVForm.vehicle_type} onChange={e => setEditVForm(p => ({ ...p, vehicle_type: e.target.value }))} className={sel}>
                              <option value="truck">Truck</option><option value="tempo">Tempo</option>
                              <option value="bike">Bike</option><option value="other">Other</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Owner Name</label>
                            <input value={editVForm.owner_name} onChange={e => setEditVForm(p => ({ ...p, owner_name: e.target.value }))} className={ic()} />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Transporter</label>
                            <select value={editVForm.transporter_id} onChange={e => setEditVForm(p => ({ ...p, transporter_id: e.target.value }))} className={sel}>
                              <option value="">None</option>
                              {transporters?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                            </select>
                          </div>
                        </div>
                        <div className="flex gap-2 justify-end">
                          <Button variant="secondary" size="sm" onClick={() => setEditingV(null)}>Cancel</Button>
                          <Button variant="primary" size="sm" loading={vUpdateM.isPending}
                            onClick={() => vUpdateM.mutate({ id: v.id, data: { ...editVForm, transporter_id: editVForm.transporter_id ? Number(editVForm.transporter_id) : null } })}>
                            Save
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Main GST Page ────────────────────────────────────────────
export default function GSTPage() {
  const [activeTab, setActiveTab] = useState('E-Invoice')
  return (
    <div>
      <div className="page-header">
        <div><div className="breadcrumb">GST</div><h1 className="page-title">GST / E-Invoice / E-Way Bill</h1></div>
      </div>
      <div className="flex border-b border-gray-200 mb-4 overflow-x-auto">
        {TABS.map(tab => (
          <button key={tab}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === tab ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700')}
            onClick={() => setActiveTab(tab)}>{tab}</button>
        ))}
      </div>
      <div className="card"><div className="p-4">
        {activeTab === 'E-Invoice' && <EInvoiceTab />}
        {activeTab === 'E-Way Bill' && <EWayBillTab />}
        {activeTab === 'GSTR-1' && <GSTR1Tab />}
        {activeTab === 'GSTR-2B' && <GSTR2BTab />}
        {activeTab === 'GSTR-3B' && <GSTR3BTab />}
        {activeTab === 'Masters' && <MastersTab />}
      </div></div>
    </div>
  )
}
