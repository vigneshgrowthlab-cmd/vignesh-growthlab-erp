import { createPortal } from 'react-dom'
import { useState, useEffect, useRef, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { purchaseAPI, vendorAPI } from '@/api/purchase'
import { settingsAPI } from '@/api/settings'
import { productAPI } from '@/api'
import { warehouseAPI } from '@/api/warehouse'
import { Button, Spinner } from '@/components/ui'
import { Save, ArrowLeft, Plus, Trash2, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import { clsx } from 'clsx'

const FALLBACK_GST_RATES = [0, 5, 12, 18, 28]

const ic = (err) => clsx(
  'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
  err ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
)

// ── Portal dropdown ────────────────────────────────────────────
function PortalDropdown({ anchorRef, children, visible }) {
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0 })
  useEffect(() => {
    if (visible && anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect()
      setPos({ top: rect.bottom + window.scrollY + 4, left: rect.left + window.scrollX, width: Math.max(rect.width, 340) })
    }
  }, [visible, anchorRef])
  if (!visible) return null
  return createPortal(
    <div style={{ position: 'absolute', top: pos.top, left: pos.left, width: pos.width, zIndex: 9999 }}>
      {children}
    </div>,
    document.body
  )
}

function ProductSearchCell({ value, onSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const inputRef = useRef(null)
  const wrapRef = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const search = async (q) => {
    setQuery(q)
    if (q.length < 2) { setResults([]); setOpen(false); return }
    try {
      const { data } = await productAPI.list({ search: q, page_size: 10 })
      const items = data.items || []
      setResults(items); setOpen(items.length > 0)
    } catch {}
  }

  if (value) {
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-gray-800 truncate">{value.part_name}</div>
          <div className="text-xs text-gray-400 font-mono">{value.part_code}</div>
        </div>
        <button onClick={() => onSelect(null)} className="text-gray-400 hover:text-red-500 flex-shrink-0">
          <Trash2 size={12} />
        </button>
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="relative">
      <div ref={inputRef} className="relative">
        <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={query}
          onChange={e => search(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search product..."
          className="w-full h-9 pl-6 pr-2 rounded border border-blue-400 text-xs focus:outline-none"
        />
      </div>
      <PortalDropdown anchorRef={inputRef} visible={open}>
        <div className="bg-white border border-gray-200 rounded-lg shadow-2xl overflow-y-auto"
          style={{ maxHeight: 210 }}>
          {results.map(p => (
            <button key={p.id} type="button"
              className="w-full text-left px-3 hover:bg-blue-50 border-b border-gray-50 flex items-center justify-between"
              style={{ height: 40 }}
              onMouseDown={e => { e.preventDefault(); onSelect(p); setQuery(''); setResults([]); setOpen(false) }}>
              <span className="flex items-center gap-2 min-w-0 flex-1">
                <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-xs flex-shrink-0">{p.part_code}</span>
                <span className="text-xs text-gray-800 truncate">{p.part_name}</span>
              </span>
              <span className="text-xs text-blue-600 flex-shrink-0 ml-3 font-semibold">
                ₹{Number(p.purchase_cost || p.selling_price || 0).toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      </PortalDropdown>
    </div>
  )
}

const emptyItem = () => ({
  _key: Math.random(),
  product: null,
  hsn_code: '',
  quantity: '',
  unit_cost: '',
  gst_percent: '18',
})

export default function PurchaseFormPage() {
  const navigate = useNavigate()
  const { isAdmin, getUserWarehouse, user } = useAuthStore()
  const isSales = user?.role === 'sales'
  const isAdminUser = isAdmin()
  const userWarehouse = getUserWarehouse()

  // Auto-set warehouse for sales users
  useEffect(() => {
    if (isSales && userWarehouse) {
      hc('warehouse_id', String(userWarehouse))
    }
  }, [isSales, userWarehouse])
  const qc = useQueryClient()

  const { data: gstRates = FALLBACK_GST_RATES } = useQuery({
    queryKey: ['gst-rates'],
    queryFn: () => settingsAPI.getGstRates().then(r => r.data.map(x => x.rate)),
    staleTime: 5 * 60 * 1000,
  })

  const [form, setForm] = useState({
    vendor_id: '',
    warehouse_id: '',
    vendor_invoice_number: '',
    invoice_date: format(new Date(), 'yyyy-MM-dd'),
    received_date: '',
    payment_due_date: '',
    notes: '',
  })
  const [items, setItems] = useState([emptyItem()])
  const [errors, setErrors] = useState({})

  const { data: vendors } = useQuery({
    queryKey: ['vendors-list'],
    queryFn: () => vendorAPI.list({ page_size: 200 }).then(r => r.data.items || r.data),
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseAPI.list().then(r => r.data),
  })

  const mutation = useMutation({
    mutationFn: (d) => purchaseAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['purchases'])
      toast.success('Purchase entry saved successfully')
      navigate('/purchase')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to save purchase'),
  })

  const hc = (f, v) => {
    setForm(p => ({ ...p, [f]: v }))
    if (errors[f]) setErrors(p => ({ ...p, [f]: '' }))
  }

  const updateItem = (idx, field, value) => {
    setItems(prev => {
      const updated = [...prev]
      updated[idx] = { ...updated[idx], [field]: value }
      // Auto-fill HSN and GST from product
      if (field === 'product' && value) {
        updated[idx].hsn_code = value.hsn_code || ''
        updated[idx].gst_percent = String(value.gst_percent || '18')
        updated[idx].unit_cost = String(value.purchase_cost || '')
      }
      return updated
    })
    if (errors[`item_${idx}`]) setErrors(p => ({ ...p, [`item_${idx}`]: '' }))
  }

  const addItem = () => setItems(p => [...p, emptyItem()])
  const removeItem = (idx) => { if (items.length > 1) setItems(p => p.filter((_, i) => i !== idx)) }

  // Totals
  const totals = items.reduce((acc, item) => {
    const qty = Number(item.quantity) || 0
    const cost = Number(item.unit_cost) || 0
    const gst = Number(item.gst_percent) || 0
    const taxable = qty * cost
    const tax = taxable * gst / 100
    return { taxable: acc.taxable + taxable, tax: acc.tax + tax, total: acc.total + taxable + tax }
  }, { taxable: 0, tax: 0, total: 0 })

  const validate = () => {
    const errs = {}
    if (!form.vendor_id) errs.vendor_id = 'Select vendor'
    if (!form.warehouse_id) errs.warehouse_id = 'Select warehouse'
    if (!form.vendor_invoice_number) errs.vendor_invoice_number = 'Required'
    if (!form.invoice_date) errs.invoice_date = 'Required'
    items.forEach((item, idx) => {
      if (!item.product) errs[`item_${idx}`] = 'Select product'
      else if (!item.quantity || Number(item.quantity) <= 0) errs[`item_${idx}`] = 'Enter quantity'
      else if (!item.unit_cost || Number(item.unit_cost) <= 0) errs[`item_${idx}`] = 'Enter cost'
      else if (!item.hsn_code || item.hsn_code.length < 4) errs[`item_${idx}`] = 'Enter valid HSN (min 4 digits)'
    })
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) {
      toast.error('Please fill all required fields')
      return
    }
    mutation.mutate({
      vendor_id: Number(form.vendor_id),
      warehouse_id: Number(form.warehouse_id),
      vendor_invoice_number: form.vendor_invoice_number,
      invoice_date: form.invoice_date,
      received_date: form.received_date || null,
      payment_due_date: form.payment_due_date || null,
      notes: form.notes || null,
      items: items.map(item => ({
        product_id: item.product.id,
        quantity: Number(item.quantity),
        unit_cost: Number(item.unit_cost),
        gst_percent: Number(item.gst_percent),
        hsn_code: item.hsn_code,
      })),
    })
  }

  return (
    <div className="max-w-4xl">
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/purchase')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Purchase
          </button>
          <h1 className="page-title">New Purchase Entry</h1>
        </div>
        <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
          <Save size={14} /> Save Purchase
        </Button>
      </div>

      <div className="space-y-4">

        {/* Header */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Vendor & Warehouse</div></div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Vendor <span className="text-red-500">*</span></label>
                <select value={form.vendor_id} onChange={e => hc('vendor_id', e.target.value)} className={ic(errors.vendor_id)}>
                  <option value="">Select vendor...</option>
                  {vendors?.map(v => <option key={v.id} value={v.id}>{v.trade_name}</option>)}
                </select>
                {errors.vendor_id && <p className="text-xs text-red-500 mt-1">{errors.vendor_id}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Warehouse <span className="text-red-500">*</span></label>
                {isSales ? (
                  <div className="h-9 px-3 flex items-center rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-700">
                    {(warehouses || []).find(w => Number(w.id) === Number(userWarehouse))?.name || userWarehouse ? 'Loading...' : 'No warehouse assigned'}
                  </div>
                ) : (
                  <select value={form.warehouse_id}
                    onChange={e => hc('warehouse_id', e.target.value)}
                    className={ic(errors.warehouse_id)}>
                    <option value="">Select warehouse...</option>
                    {isAdminUser
                      ? (warehouses || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)
                      : (warehouses || []).filter(w => !userWarehouse || Number(w.id) === Number(userWarehouse)).map(w => <option key={w.id} value={w.id}>{w.name}</option>)
                    }
                  </select>
                )}
                {errors.warehouse_id && <p className="text-xs text-red-500 mt-1">{errors.warehouse_id}</p>}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Vendor Invoice No. <span className="text-red-500">*</span></label>
                <input value={form.vendor_invoice_number} onChange={e => hc('vendor_invoice_number', e.target.value)}
                  placeholder="e.g. VND-INV-001" className={ic(errors.vendor_invoice_number)} />
                {errors.vendor_invoice_number && <p className="text-xs text-red-500 mt-1">{errors.vendor_invoice_number}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Date <span className="text-red-500">*</span></label>
                <input type="date" value={form.invoice_date} onChange={e => hc('invoice_date', e.target.value)} className={ic(errors.invoice_date)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Received Date</label>
                <input type="date" value={form.received_date} onChange={e => hc('received_date', e.target.value)} className={ic()} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Payment Due Date</label>
                <input type="date" value={form.payment_due_date} onChange={e => hc('payment_due_date', e.target.value)} className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <input value={form.notes} onChange={e => hc('notes', e.target.value)} placeholder="Optional notes" className={ic()} />
              </div>
            </div>
          </div>
        </div>

        {/* Items */}
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-700">Purchase Items</div>
            <button onClick={addItem}
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700">
              <Plus size={12} /> Add Item
            </button>
          </div>
          <div className="card-body">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left text-xs font-medium text-gray-500 pb-2 w-64">Product</th>
                  <th className="text-left text-xs font-medium text-gray-500 pb-2 w-28">HSN Code</th>
                  <th className="text-left text-xs font-medium text-gray-500 pb-2 w-24">Qty</th>
                  <th className="text-left text-xs font-medium text-gray-500 pb-2 w-28">Unit Cost (₹)</th>
                  <th className="text-left text-xs font-medium text-gray-500 pb-2 w-20">GST %</th>
                  <th className="text-left text-xs font-medium text-gray-500 pb-2 w-28">Serial No.</th>
                  <th className="text-right text-xs font-medium text-gray-500 pb-2 w-28">Total (₹)</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {items.map((item, idx) => {
                  const lineTotal = (Number(item.quantity) || 0) * (Number(item.unit_cost) || 0) * (1 + (Number(item.gst_percent) || 0) / 100)
                  return (
                    <Fragment key={item._key}>
                    <tr className={clsx('py-2', errors[`item_${idx}`] ? 'bg-red-50/30' : '')}>
                      <td className="py-2 pr-3">
                        <ProductSearchCell value={item.product} onSelect={p => updateItem(idx, 'product', p)} />
                        {errors[`item_${idx}`] && <p className="text-xs text-red-500 mt-1">{errors[`item_${idx}`]}</p>}
                      </td>
                      <td className="py-2 pr-3">
                        <input value={item.hsn_code} onChange={e => updateItem(idx, 'hsn_code', e.target.value)}
                          placeholder="85171200" maxLength={8}
                          className="w-full h-9 px-2 rounded border border-gray-300 text-xs font-mono focus:outline-none focus:border-blue-500" />
                      </td>
                      <td className="py-2 pr-3">
                        <input type="number" step="0.001" min="0.001" value={item.quantity}
                          onChange={e => updateItem(idx, 'quantity', e.target.value)}
                          placeholder="0"
                          className="w-full h-9 px-2 rounded border border-gray-300 text-xs focus:outline-none focus:border-blue-500" />
                      </td>
                      <td className="py-2 pr-3">
                        <input type="number" step="0.01" min="0.01" value={item.unit_cost}
                          onChange={e => updateItem(idx, 'unit_cost', e.target.value)}
                          placeholder="0.00"
                          className="w-full h-9 px-2 rounded border border-gray-300 text-xs focus:outline-none focus:border-blue-500" />
                      </td>
                      <td className="py-2 pr-3">
                        <select value={item.gst_percent} onChange={e => updateItem(idx, 'gst_percent', e.target.value)}
                          className="w-full h-8 px-1 rounded border border-gray-300 text-xs focus:outline-none focus:border-blue-500">
                          {gstRates.map(r => <option key={r} value={r}>{r}%</option>)}
                        </select>
                      </td>
                      
                      <td className="py-2 pr-3 text-right text-xs font-medium text-gray-700">
                        ₹{lineTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-2">
                        <button onClick={() => removeItem(idx)} className="text-gray-300 hover:text-red-500">
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                    {/* Serial number inputs for serial-tracked products */}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>

            {/* Totals */}
            <div className="mt-4 pt-4 border-t border-gray-100 flex justify-end">
              <div className="w-64 space-y-1.5">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>Taxable Amount</span>
                  <span>₹{totals.taxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between text-sm text-gray-600">
                  <span>GST</span>
                  <span>₹{totals.tax.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between text-base font-bold text-gray-800 pt-1 border-t border-gray-200">
                  <span>Grand Total</span>
                  <span>₹{totals.total.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between pb-6">
          <Button variant="secondary" onClick={() => navigate('/purchase')}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
            <Save size={14} /> Save Purchase
          </Button>
        </div>
      </div>
    </div>
  )
}
