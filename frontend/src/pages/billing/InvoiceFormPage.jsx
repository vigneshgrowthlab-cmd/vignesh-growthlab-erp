import { useState, useEffect, useRef, Fragment } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { invoiceAPI, customerAPI, receiptAPI } from '@/api/billing'
import { transporterAPI } from '@/api/gst'
import { productAPI } from '@/api'
import { triggerDailyPriceActivation } from '@/utils/priceActivation'
import { warehouseAPI } from '@/api/warehouse'
import { useAuthStore } from '@/store/authStore'
import { settingsAPI } from '@/api/settings'
import { Button, AlertBox } from '@/components/ui'
import { Save, ArrowLeft, Plus, Trash2, Search, X, UserPlus, CreditCard } from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import { clsx } from 'clsx'

const DOC_TYPES = [
  { value: 'b2b_invoice', label: 'B2B Invoice' },
  { value: 'b2c_invoice', label: 'B2C Invoice' },
  { value: 'quotation',   label: 'Quotation' },
  { value: 'delivery_challan', label: 'Delivery Challan' },
]

// Delivery challans are valued at 10% of the product's B2B price (not a real sale).
const DC_VALUE_FACTOR = 0.1

// Mirror the validation used on the dedicated Customer form (CustomerFormPage.jsx).
const GSTIN_REGEX = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9]{1}[A-Z]{1}[0-9A-Z]{1}$/
const PHONE_REGEX = /^(\+?91[\s-]?|0)?[6-9]\d{9}$/
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// Resolve the line unit price for a product given the doc type / customer type.
// DC always uses 10% of b2b_price regardless of the B2B/B2C toggle.
const priceForDoc = (product, docType, isB2B, fallback = '') => {
  if (!product) return fallback
  if (docType === 'delivery_challan') {
    return Number(product.b2b_price || 0) * DC_VALUE_FACTOR
  }
  if (docType === 'b2c_invoice') {
    return product.b2c_price || product.b2b_price || product.mrp || fallback
  }
  if (docType === 'b2b_invoice') {
    return product.b2b_price || product.b2c_price || product.mrp || fallback
  }
  // quotation: follow customer type
  return isB2B
    ? (product.b2b_price || product.b2c_price || product.mrp || fallback)
    : (product.b2c_price || product.b2b_price || product.mrp || fallback)
}

const ic = (err) => clsx(
  'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
  err ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
)

// ── Portal dropdown — renders outside any overflow:hidden parent ──
function PortalDropdown({ anchorRef, children, visible }) {
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0 })

  useEffect(() => {
    if (visible && anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect()
      setPos({
        top: rect.bottom + window.scrollY + 4,
        left: rect.left + window.scrollX,
        width: Math.max(rect.width, 340),
      })
    }
  }, [visible, anchorRef])

  if (!visible) return null

  return createPortal(
    <div style={{
      position: 'absolute',
      top: pos.top,
      left: pos.left,
      width: pos.width,
      zIndex: 9999,
    }}>
      {children}
    </div>,
    document.body
  )
}

// ── Product Search for billing line items ─────────────────────
function ProductSearchCell({ value, warehouseId, onSelect, documentType }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const inputRef = useRef(null)
  const wrapRef = useRef(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const search = async (q) => {
    setQuery(q)
    if (q.length < 2) { setResults([]); setOpen(false); return }
    try {
      const { data } = await productAPI.searchBilling(q, warehouseId)
      const items = data || []
      setResults(items)
      setOpen(items.length > 0)
    } catch {
      try {
        const { data } = await productAPI.list({ search: q, page_size: 10 })
        const items = data.items || []
        setResults(items)
        setOpen(items.length > 0)
      } catch {}
    }
  }

  if (value) {
    return (
      <div className="flex items-center gap-1">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-gray-800 truncate">{value.part_name}</div>
          <div className="text-xs text-gray-400 font-mono">{value.part_code}</div>
        </div>
        <button onClick={() => onSelect(null)} className="text-gray-300 hover:text-red-500 flex-shrink-0">
          <X size={11} />
        </button>
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="relative">
      <div ref={inputRef} className="relative">
        <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
        <input value={query} onChange={e => search(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search product..." autoFocus
          className="w-full h-9 pl-6 pr-2 rounded border border-blue-400 text-xs focus:outline-none" />
      </div>
      <PortalDropdown anchorRef={inputRef} visible={open}>
        <div className="bg-white border border-gray-200 rounded-lg shadow-2xl overflow-y-auto"
          style={{ maxHeight: 210 }}>
          {results.map(p => (
            <button key={p.id} type="button"
              className="w-full text-left px-3 hover:bg-blue-50 border-b border-gray-50 flex items-center justify-between"
              style={{ height: 40 }}
              onMouseDown={e => {
                e.preventDefault() // prevent blur before click
                onSelect(p)
                setQuery('')
                setResults([])
                setOpen(false)
              }}>
              <span className="flex items-center gap-2 min-w-0 flex-1">
                <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-xs flex-shrink-0">{p.part_code}</span>
                <span className="text-xs text-gray-800 truncate">{p.part_name}</span>
              </span>
              <span className="text-xs text-blue-600 flex-shrink-0 ml-3 font-semibold">
  ₹{Number(priceForDoc(p, documentType, true, 0)).toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      </PortalDropdown>
    </div>
  )
}

// ── Inline Customer Creator ───────────────────────────────────
function NewCustomerInline({ onCreated, onCancel, states = [] }) {
  const [form, setForm] = useState({
    trade_name: '', gstin: '', phone: '', email: '',
    business_type: 'proprietorship', gst_status: 'Active',
    state: 'Tamil Nadu', is_b2b: true, is_active: true,
    credit_days: 0, credit_limit: 0,
  })
  const [addr, setAddr] = useState({
    address_line1: '', address_line2: '', city: '',
    state: 'Tamil Nadu', pincode: '', contact_person: '', phone: '',
    label: 'Main', address_type: 'both',
    is_preferred_billing: true, is_preferred_shipping: true,
  })
  const [errors, setErrors] = useState({})
  const [gstinLoading, setGstinLoading] = useState(false)

  const validate = () => {
    const errs = {}
    if (!form.trade_name.trim()) errs.trade_name = 'Required'
    // GSTIN: full Indian format check (matches dedicated Customer form).
    if (form.gstin && !GSTIN_REGEX.test(form.gstin)) {
      errs.gstin = 'Invalid GSTIN format (e.g. 22AAAAA0000A1Z5)'
    }
    // Phone optional, but if provided must look like an Indian mobile.
    if (form.phone) {
      const cleaned = form.phone.replace(/[\s-]/g, '')
      if (!PHONE_REGEX.test(cleaned)) errs.phone = 'Invalid phone (10-digit Indian mobile)'
    }
    // Email optional, but if provided must be valid.
    if (form.email && !EMAIL_REGEX.test(form.email)) errs.email = 'Invalid email format'
    if (!addr.address_line1.trim()) errs.address_line1 = 'Required'
    if (!addr.city.trim()) errs.city = 'Required'
    if (!addr.pincode || addr.pincode.length !== 6) errs.pincode = '6 digits'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const lookupGstin = async () => {
    const gstin = form.gstin?.trim().toUpperCase()
    if (!gstin || gstin.length !== 15) {
      toast.error('GSTIN must be exactly 15 characters')
      return
    }
    setGstinLoading(true)
    try {
      const { data } = await customerAPI.gstinLookup(gstin)
      if (data.error) {
        toast.error(data.error)
        return
      }
      setForm(p => ({
        ...p,
        ...(data.trade_name ? { trade_name: data.trade_name } : {}),
        ...(data.business_type ? { business_type: data.business_type } : {}),
        ...(data.gst_status ? { gst_status: data.gst_status } : {}),
        ...(data.state ? { state: data.state } : {}),
      }))
      if (data.state) {
        const sel = states.find(s => s.name === data.state)
        setAddr(p => ({ ...p, state: data.state, state_code: sel?.code ?? data.state_code ?? null }))
      }
      toast.success('GSTIN details fetched. State auto-filled.')
    } catch {
      toast.error('GSTIN lookup failed')
    } finally {
      setGstinLoading(false)
    }
  }

  const mutation = useMutation({
    mutationFn: async (d) => {
      // Step 1: create customer
      const res = await customerAPI.create(d.customer)
      const customerId = res.data.id
      // Step 2: add address
      try {
        await customerAPI.addAddress(customerId, d.addr)
      } catch {}
      // Step 3: return fresh customer with addresses
      try {
        const detail = await customerAPI.get(customerId)
        return detail
      } catch {
        return res
      }
    },
    onSuccess: (res) => {
      toast.success(`Customer "${res.data.trade_name}" created`)
      onCreated(res.data)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to create customer'),
  })

  const setF = (f) => (e) => {
    setForm(p => ({ ...p, [f]: e.target.value }))
    if (errors[f]) setErrors(p => ({ ...p, [f]: '' }))
  }
  const setA = (f) => (e) => {
    setAddr(p => ({ ...p, [f]: e.target.value }))
    if (errors[f]) setErrors(p => ({ ...p, [f]: '' }))
  }

  const inp = (err) => clsx(
    'w-full h-8 px-2 rounded border text-sm focus:outline-none',
    err ? 'border-red-400' : 'border-gray-300 focus:border-blue-400'
  )

  return (
    <div className="mt-2 p-3 bg-green-50 border border-green-200 rounded-lg space-y-3">
      <div className="flex justify-between items-center">
        <span className="text-xs font-semibold text-green-800 flex items-center gap-1.5">
          <UserPlus size={13} /> Quick Add Customer
        </span>
        <button onClick={onCancel} className="text-green-400 hover:text-green-600"><X size={12} /></button>
      </div>

      {/* Customer Info */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Business Details</p>
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Business Name <span className="text-red-500">*</span>
            </label>
            <input value={form.trade_name} onChange={setF('trade_name')}
              placeholder="e.g. ABC Traders" className={inp(errors.trade_name)} />
            {errors.trade_name && <p className="text-xs text-red-500 mt-0.5">{errors.trade_name}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
            <input value={form.phone} onChange={setF('phone')}
              placeholder="9999999999" maxLength={15} className={inp(errors.phone)} />
            {errors.phone && <p className="text-xs text-red-500 mt-0.5">{errors.phone}</p>}
          </div>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">GSTIN</label>
            <div className="flex gap-2">
              <input value={form.gstin}
                onChange={e => setF('gstin')({ target: { value: e.target.value.toUpperCase() } })}
                placeholder="29AAAAA0000A1Z5" maxLength={15}
                className={clsx(inp(errors.gstin), 'uppercase font-mono')} />
              <button type="button" onClick={lookupGstin} disabled={gstinLoading}
                className="px-2.5 h-8 shrink-0 rounded border border-gray-300 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-60 flex items-center gap-1">
                <Search size={12} /> {gstinLoading ? '...' : 'Fetch'}
              </button>
            </div>
            {errors.gstin && <p className="text-xs text-red-500 mt-0.5">{errors.gstin}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
            <input value={form.email} onChange={setF('email')}
              placeholder="customer@email.com" className={inp(errors.email)} />
            {errors.email && <p className="text-xs text-red-500 mt-0.5">{errors.email}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
            <select value={form.is_b2b}
              onChange={e => setForm(p => ({ ...p, is_b2b: e.target.value === 'true' }))}
              className="w-full h-8 px-2 rounded border border-gray-300 text-sm focus:outline-none focus:border-blue-400">
              <option value="true">B2B (Business)</option>
              <option value="false">B2C (Consumer)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Address */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Address</p>
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Street / Area <span className="text-red-500">*</span>
            </label>
            <input value={addr.address_line1} onChange={setA('address_line1')}
              placeholder="Door no., Street name" className={inp(errors.address_line1)} />
            {errors.address_line1 && <p className="text-xs text-red-500 mt-0.5">{errors.address_line1}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Landmark / Area</label>
            <input value={addr.address_line2} onChange={setA('address_line2')}
              placeholder="Near..." className={inp()} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              City <span className="text-red-500">*</span>
            </label>
            <input value={addr.city} onChange={setA('city')}
              placeholder="Chennai" className={inp(errors.city)} />
            {errors.city && <p className="text-xs text-red-500 mt-0.5">{errors.city}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">State</label>
            <select value={form.state}
              onChange={e => {
                const sel = states.find(s => s.name === e.target.value)
                setF('state')(e)
                setAddr(p => ({ ...p, state: e.target.value, state_code: sel?.code || null }))
              }}
              className={inp()}>
              <option value="">Select state...</option>
                  {states.map(s => (
                    <option key={s.code} value={s.name}>{s.code} — {s.name}</option>
                  ))}</select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Pincode <span className="text-red-500">*</span>
            </label>
            <input value={addr.pincode} onChange={setA('pincode')}
              placeholder="600001" maxLength={6} className={clsx(inp(errors.pincode), 'font-mono')} />
            {errors.pincode && <p className="text-xs text-red-500 mt-0.5">{errors.pincode}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Contact Person</label>
            <input value={addr.contact_person} onChange={setA('contact_person')}
              placeholder="Name" className={inp()} />
          </div>
        </div>
      </div>

      <div className="flex gap-2 justify-end pt-1">
        <button onClick={onCancel}
          className="px-3 h-7 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50">
          Cancel
        </button>
        <button onClick={() => { if (validate()) mutation.mutate({ customer: form, addr }) }}
          disabled={mutation.isPending}
          className="px-3 h-7 text-xs rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-60">
          {mutation.isPending ? 'Creating...' : 'Create & Select'}
        </button>
      </div>
    </div>
  )
}

// ── Inline Address Creator ────────────────────────────────────
function AddressCreator({ customerId, onCreated, onCancel, states = [] }) {
  const [form, setForm] = useState({
    label: 'Main', address_line1: '', address_line2: '',
    city: '', state: '', state_code: null, pincode: '', contact_person: '', phone: '',
    address_type: 'both', is_preferred_billing: true, is_preferred_shipping: true,
  })
  const [errors, setErrors] = useState({})

  const mutation = useMutation({
    mutationFn: (d) => customerAPI.addAddress(customerId, d),
    onSuccess: (res) => { toast.success('Address added'); onCreated(res.data) },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to add address'),
  })

  const validate = () => {
    const errs = {}
    if (!form.address_line1) errs.address_line1 = 'Required'
    if (!form.city) errs.city = 'Required'
    if (!form.state) errs.state = 'Required'
    if (!form.pincode || form.pincode.length !== 6) errs.pincode = '6 digits required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handle = () => { if (validate()) mutation.mutate(form) }

  return (
    <div className="mt-2 p-3 bg-blue-50 border border-blue-200 rounded-lg space-y-3">
      <div className="flex justify-between items-center">
        <span className="text-xs font-semibold text-blue-800">Add Customer Address</span>
        <button onClick={onCancel} className="text-blue-400"><X size={12} /></button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Address <span className="text-red-500">*</span></label>
          <input value={form.address_line1} onChange={e => { setForm(p => ({ ...p, address_line1: e.target.value })); setErrors(p => ({ ...p, address_line1: '' })) }}
            placeholder="Street / Area" className={clsx('w-full h-8 px-2 rounded border text-sm focus:outline-none', errors.address_line1 ? 'border-red-400' : 'border-gray-300')} />
          {errors.address_line1 && <p className="text-xs text-red-500 mt-0.5">{errors.address_line1}</p>}
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">City <span className="text-red-500">*</span></label>
          <input value={form.city} onChange={e => { setForm(p => ({ ...p, city: e.target.value })); setErrors(p => ({ ...p, city: '' })) }}
            placeholder="City" className={clsx('w-full h-8 px-2 rounded border text-sm focus:outline-none', errors.city ? 'border-red-400' : 'border-gray-300')} />
          {errors.city && <p className="text-xs text-red-500 mt-0.5">{errors.city}</p>}
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">State <span className="text-red-500">*</span></label>
          <select value={form.state} onChange={e => {
                const sel = states.find(s => s.name === e.target.value)
                setForm(p => ({ ...p, state: e.target.value, state_code: sel?.code || null }))
                setErrors(p => ({ ...p, state: '' }))
              }}
            className={clsx('w-full h-8 px-2 rounded border text-sm focus:outline-none', errors.state ? 'border-red-400' : 'border-gray-300')}>
            <option value="">Select state...</option>
                  {states.map(s => (
                    <option key={s.code} value={s.name}>{s.code} — {s.name}</option>
                  ))}</select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Pincode <span className="text-red-500">*</span></label>
          <input value={form.pincode} onChange={e => { setForm(p => ({ ...p, pincode: e.target.value })); setErrors(p => ({ ...p, pincode: '' })) }}
            placeholder="600001" maxLength={6} className={clsx('w-full h-8 px-2 rounded border text-sm font-mono focus:outline-none', errors.pincode ? 'border-red-400' : 'border-gray-300')} />
          {errors.pincode && <p className="text-xs text-red-500 mt-0.5">{errors.pincode}</p>}
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={onCancel} className="px-3 h-7 text-xs rounded border border-gray-300 text-gray-600">Cancel</button>
        <button onClick={handle} disabled={mutation.isPending}
          className="px-3 h-7 text-xs rounded bg-blue-600 text-white disabled:opacity-60">
          {mutation.isPending ? 'Saving...' : 'Add Address'}
        </button>
      </div>
    </div>
  )
}

// ── Empty line item ───────────────────────────────────────────
const emptyItem = () => ({
  _key: Math.random(),
  product: null,
  notes: '',
  hsn_code: '',
  quantity: '1',
  unit_price: '',
  discount_percent: '0',
  gst_percent: '18',
})


// ── Main Form ─────────────────────────────────────────────────


// ── DC Warehouse Card ────────────────────────────────────────
// For Delivery Challan: show destination warehouse + inline create instead of customer
function DCWarehouseCard({ warehouses, form, errors, onChange }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')
  const [newCode, setNewCode] = useState('')

  const createMutation = useMutation({
    mutationFn: (d) => warehouseAPI.create(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['warehouses'])
      onChange('dc_destination_warehouse_id', String(res.data.id))
      setShowAdd(false); setNewName(''); setNewCode('')
      toast.success('Warehouse created')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const allWarehouses = warehouses?.items || (Array.isArray(warehouses) ? warehouses : [])

  return (
    <div className="card">
      <div className="card-header">
        <div className="text-sm font-semibold text-gray-700">Delivery Details</div>
      </div>
      <div className="card-body space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              From Warehouse <span className="text-gray-400 text-xs font-normal">(source)</span>
            </label>
            <select value={form.warehouse_id || ''}
              onChange={e => onChange('warehouse_id', e.target.value)}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
              <option value="">Select warehouse...</option>
              {allWarehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              To Warehouse / Location <span className="text-gray-400 text-xs font-normal">(destination)</span>
            </label>
            <div className="flex gap-2">
              <select value={form.dc_destination_warehouse_id || ''}
                onChange={e => {
                  if (e.target.value === '__add__') { setShowAdd(true); return }
                  onChange('dc_destination_warehouse_id', e.target.value)
                }}
                className={clsx("flex-1 h-9 px-3 rounded-lg border text-sm focus:outline-none focus:border-blue-500",
                  errors?.dc_destination_warehouse_id ? 'border-red-400' : 'border-gray-300')}>
                <option value="">Select destination...</option>
                {allWarehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                <option value="__add__">+ Add new warehouse...</option>
              </select>
              {errors?.dc_destination_warehouse_id && (
                <p className="text-xs text-red-500 mt-1">{errors.dc_destination_warehouse_id}</p>
              )}
            </div>
          </div>
        </div>
        {showAdd && (
          <div className="p-3 bg-green-50 border border-green-200 rounded-lg space-y-2">
            <p className="text-xs font-semibold text-green-800">Add New Warehouse</p>
            <div className="grid grid-cols-2 gap-2">
              <input value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="Warehouse name *"
                className="h-8 px-2 rounded border border-gray-300 text-xs focus:outline-none" />
              <input value={newCode} onChange={e => setNewCode(e.target.value.toUpperCase())}
                placeholder="Code e.g. WH-02 *" maxLength={10}
                className="h-8 px-2 rounded border border-gray-300 text-xs font-mono focus:outline-none" />
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowAdd(false)}
                className="px-3 h-7 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50">Cancel</button>
              <button
                onClick={() => {
                  if (!newName.trim() || !newCode.trim()) { toast.error('Fill name and code'); return }
                  createMutation.mutate({ name: newName.trim(), code: newCode.trim(), is_active: true })
                }}
                disabled={createMutation.isPending}
                className="px-3 h-7 text-xs rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-60">
                {createMutation.isPending ? 'Creating...' : 'Create & Select'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Transport Details Section (Invoice + DC) ──────────────────
function TransportSection({ transporters, vehicles, form, onChange, requireVehicle, vehicleError }) {
  const [useFreetextTransporter, setUseFreetextTransporter] = useState(false)

  const filteredVehicles = form.transporter_id
    ? (vehicles || []).filter(v => v.transporter_id === Number(form.transporter_id))
    : (vehicles || [])

  const printOptions = [
    { value: '', label: 'Follow company setting' },
    { value: 'true', label: 'Always show on print' },
    { value: 'false', label: 'Always hide on print' },
  ]
  const printValue = form.show_transport_on_print === true ? 'true'
    : form.show_transport_on_print === false ? 'false' : ''

  return (
    <div className="card">
      <div className="card-header">
        <span className="text-sm font-semibold text-gray-700">
          Transport Details {requireVehicle && <span className="text-red-500">*</span>}
        </span>
      </div>
      <div className="card-body space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {/* Transporter */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Transporter</label>
            {!useFreetextTransporter ? (
              <div className="flex gap-1">
                <select
                  value={form.transporter_id || ''}
                  onChange={e => onChange('transporter_id', e.target.value ? Number(e.target.value) : null)}
                  className="flex-1 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select transporter...</option>
                  {transporters.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <button
                  type="button"
                  onClick={() => { setUseFreetextTransporter(true); onChange('transporter_id', null) }}
                  className="px-2 h-9 text-xs rounded border border-gray-300 text-gray-500 hover:bg-gray-50 whitespace-nowrap">
                  Free text
                </button>
              </div>
            ) : (
              <div className="flex gap-1">
                <input
                  value={form.transporter_name || ''}
                  onChange={e => onChange('transporter_name', e.target.value)}
                  placeholder="Transporter name"
                  className="flex-1 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                <button
                  type="button"
                  onClick={() => { setUseFreetextTransporter(false); onChange('transporter_name', '') }}
                  className="px-2 h-9 text-xs rounded border border-gray-300 text-gray-500 hover:bg-gray-50">
                  Master
                </button>
              </div>
            )}
          </div>
          {/* Vehicle */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Vehicle {requireVehicle && <span className="text-red-500">*</span>}
            </label>
            <div className="flex gap-1">
              <select
                value={form.vehicle_id || ''}
                onChange={e => {
                  const v = (vehicles || []).find(x => x.id === Number(e.target.value))
                  onChange('vehicle_id', e.target.value ? Number(e.target.value) : null)
                  onChange('vehicle_number', v?.vehicle_number || '')
                }}
                className={clsx('flex-1 h-9 px-3 rounded-lg border text-sm focus:outline-none',
                  vehicleError ? 'border-red-400' : 'border-gray-300 focus:border-blue-500')}>
                <option value="">
                  {filteredVehicles.length === 0 && form.transporter_id
                    ? 'No vehicles for this transporter'
                    : 'Select vehicle...'}
                </option>
                {filteredVehicles.map(v => (
                  <option key={v.id} value={v.id}>{v.vehicle_type} — {v.vehicle_number}</option>
                ))}
              </select>
              <input
                value={form.vehicle_id ? '' : (form.vehicle_number || '')}
                onChange={e => { onChange('vehicle_id', null); onChange('vehicle_number', e.target.value.toUpperCase()) }}
                placeholder="or type no."
                maxLength={15}
                className="w-28 h-9 px-2 rounded-lg border border-gray-300 text-xs font-mono focus:outline-none focus:border-blue-500" />
            </div>
            {vehicleError && <p className="text-xs text-red-500 mt-1">{vehicleError}</p>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {/* LR Number */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">LR / Transport No.</label>
            <input
              value={form.lr_number || ''}
              onChange={e => onChange('lr_number', e.target.value)}
              placeholder="LR number"
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
          </div>
          {/* Print toggle */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Show on print</label>
            <select
              value={printValue}
              onChange={e => {
                const v = e.target.value === 'true' ? true : e.target.value === 'false' ? false : null
                onChange('show_transport_on_print', v)
              }}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
              {printOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function InvoiceFormPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAdmin: _isAdmin, getUserWarehouse } = useAuthStore()
  const isAdminUser = _isAdmin()
  const { user } = useAuthStore()
  const isSales = user?.role === 'sales'
  const userWarehouse = getUserWarehouse()
  const qc = useQueryClient()

  // Check if opened from quotation conversion
  const quotation = location.state?.quotation || null

  const [form, setForm] = useState({
    document_type: quotation?.document_type === 'quotation'
      ? (quotation?.customer_gstin ? 'b2b_invoice' : 'b2c_invoice')
      : 'b2b_invoice',
    customer_id: quotation?.customer_id ? String(quotation.customer_id) : '',
    warehouse_id: quotation?.warehouse_id ? String(quotation.warehouse_id) : '',
    billing_address_id: quotation?.billing_address_id ? String(quotation.billing_address_id) : '',
    shipping_address_id: quotation?.shipping_address_id ? String(quotation.shipping_address_id) : '',
    invoice_date: format(new Date(), 'yyyy-MM-dd'),
    due_date: '',
    invoice_discount: quotation?.invoice_discount ? String(quotation.invoice_discount) : '0',
    notes: quotation ? `Converted from Quotation ${quotation.invoice_number || ''}` : '',
    terms_conditions: quotation?.terms_conditions || '',
    dc_destination_warehouse_id: '',
    vehicle_number: '',
    vehicle_id: null,
    driver_name: '',
    lr_number: '',
    transporter_id: null,
    transporter_name: '',
    show_transport_on_print: null,
  })

  // Pre-fill line items from quotation
  const [items, setItems] = useState(
    quotation?.items?.length
      ? quotation.items.map(item => ({
          _key: Math.random(),
          product: item.product_id ? {
            id: item.product_id,
            part_code: item.part_code,
            part_name: item.part_name,
            hsn_code: item.hsn_code,
            gst_percent: item.gst_percent,
            // Quotation lines carry the previously-quoted unit price; we feed
            // it back as the price tier matching the active document type.
            b2b_price: item.unit_price,
            b2c_price: item.unit_price,
          } : null,
          hsn_code: item.hsn_code || '',
          quantity: String(item.quantity || 1),
          unit_price: String(item.unit_price || ''),
          discount_percent: String(item.discount_percent || '0'),
          gst_percent: String(item.gst_percent || '18'),
        }))
      : [emptyItem()]
  )
  const [errors, setErrors] = useState({})
  const [showAddAddress, setShowAddAddress] = useState(false)
  const [showNewCustomer, setShowNewCustomer] = useState(false)

  // Payment state
  const [showConfirm, setShowConfirm] = useState(false)
  const [creditError, setCreditError] = useState(null)

  const [payment, setPayment] = useState({
    collect: true,  // always ON — card is hidden for quotation/DC doc types
    is_advance: false,   // true = advance (skips mandatory check)
    amount: '',
    payment_mode: 'cash',
    reference_number: '',
    payment_date: new Date().toISOString().split('T')[0],
  })
  const setP = (f) => (val) => setPayment(p => ({ ...p, [f]: val }))
  // Auto-fill payment amount with the grand total until the user edits it.
  const [amountTouched, setAmountTouched] = useState(false)
  const [customerAddresses, setCustomerAddresses] = useState([])
  const [creditInfo, setCreditInfo] = useState(null) // { limit, outstanding, available }

  // Activate any scheduled prices whose effective_from <= today (IST).
  // Throttled by localStorage to the first invoice-page load per IST day —
  // subsequent loads same day skip the network call entirely.
  useEffect(() => {
    triggerDailyPriceActivation(qc)
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const { data: customers } = useQuery({
    queryKey: ['customers-list'],
    queryFn: () => customerAPI.list({ page_size: 500 }).then(r => r.data.items || r.data),
  })

  const { data: vehicles } = useQuery({
    queryKey: ['vehicles'],
    queryFn: () => settingsAPI.getVehicles().then(r => r.data?.filter(v => v.is_active) || []),
  })

  const { data: transporters = [] } = useQuery({
    queryKey: ['transporters'],
    queryFn: () => transporterAPI.list().then(r => r.data?.filter(t => t.is_active) || []),
  })

  const { data: states = [] } = useQuery({
    queryKey: ['states'],
    queryFn: () => settingsAPI.getStates().then(r => r.data),
  })

  const { data: companySettings } = useQuery({
    queryKey: ['company-settings'],
    queryFn: () => settingsAPI.getCompany().then(r => r.data),
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseAPI.list().then(r => r.data),
    onSuccess: (data) => {
      if (!form.warehouse_id && data?.items?.length) {
        const def = data.items.find(w => w.is_default) || data.items[0]
        if (def) hc('warehouse_id', String(def.id))
      }
    },
  })

  // Auto-populate T&C from company settings when doc type changes (skip if from quotation)
  useEffect(() => {
    if (!companySettings || quotation) return
    const fieldMap = {
      b2b_invoice:      'terms_b2b_invoice',
      b2c_invoice:      'terms_b2c_invoice',
      quotation:        'terms_quotation',
      delivery_challan: 'terms_delivery_challan',
    }
    const field = fieldMap[form.document_type]
    const defaultText = field ? (companySettings[field] || '') : ''
    setForm(p => ({ ...p, terms_conditions: defaultText }))
  }, [form.document_type, companySettings])

  // Auto-select default warehouse on mount if not set
  useEffect(() => {
    if (isSales && userWarehouse) {
      hc('warehouse_id', String(userWarehouse))
      return
    }
    if (warehouses && !form.warehouse_id) {
      const items = warehouses.items || warehouses
      if (items?.length) {
        const def = items.find(w => w.is_default) || items[0]
        if (def) hc('warehouse_id', String(def.id))
      }
    }
  }, [warehouses])

  const { data: customerDetail } = useQuery({
    queryKey: ['customer-detail', form.customer_id],
    queryFn: () => customerAPI.get(form.customer_id).then(r => r.data),
    enabled: Boolean(form.customer_id),
  })

  // When customer changes, update addresses and credit info
  useEffect(() => {
    if (!customerDetail) return
    const addrs = customerDetail.addresses || []
    setCustomerAddresses(addrs)
    const bill = addrs.find(a => a.is_preferred_billing) || addrs[0]
    const ship = addrs.find(a => a.is_preferred_shipping) || addrs[0]
    setForm(p => ({
      ...p,
      billing_address_id: bill ? String(bill.id) : '',
      shipping_address_id: ship ? String(ship.id) : '',
    }))
    // Set credit info
    const limit = Number(customerDetail.credit_limit || 0)
    const outstanding = Number(customerDetail.outstanding_balance || 0)
    setCreditInfo({ limit, outstanding, available: Math.max(0, limit - outstanding) })
  }, [customerDetail])

  const hc = (f, v) => {
    setForm(p => ({ ...p, [f]: v }))
    if (errors[f]) setErrors(p => ({ ...p, [f]: '' }))
  }

  const updateItem = (idx, field, value) => {
    setItems(prev => {
      const updated = [...prev]
      updated[idx] = { ...updated[idx], [field]: value }
      if (field === 'product' && value) {
        updated[idx].hsn_code = value.hsn_code || ''
        updated[idx].gst_percent = value.gst_percent != null ? String(value.gst_percent) : ''
        // selling_price isn't returned by the backend; priceForDoc falls back
        // across the real price tiers (b2c/b2b/mrp) instead of writing NaN.
        updated[idx].unit_price = String(
          priceForDoc(value, form.document_type, form.is_b2b)
        )
      }
      return updated
    })
    if (errors[`item_${idx}`]) setErrors(p => ({ ...p, [`item_${idx}`]: '' }))
  }

  const addItem = () => setItems(p => [...p, emptyItem()])
  const removeItem = (idx) => { if (items.length > 1) setItems(p => p.filter((_, i) => i !== idx)) }

  // Totals
  const invoiceDiscount = Number(form.invoice_discount) || 0
  const totals = items.reduce((acc, item) => {
    const qty = Number(item.quantity) || 0
    const price = Number(item.unit_price) || 0
    const disc = Number(item.discount_percent) || 0
    const gst = Number(item.gst_percent) || 0
    const taxable = qty * price * (1 - disc / 100)
    const tax = taxable * gst / 100
    return { taxable: acc.taxable + taxable, tax: acc.tax + tax }
  }, { taxable: 0, tax: 0 })
  const grandTotal = totals.taxable + totals.tax - invoiceDiscount
  // Tax invoices are rounded to the nearest rupee (matches backend); preview only.
  const isTaxInvoice = ['b2b_invoice', 'b2c_invoice'].includes(form.document_type)
  const roundOff = isTaxInvoice ? Math.round(grandTotal) - grandTotal : 0
  const displayTotal = isTaxInvoice ? Math.round(grandTotal) : grandTotal

  // Default the payment amount to the grand total until the user edits it.
  useEffect(() => {
    if (!payment.collect || amountTouched) return
    setPayment(p => ({ ...p, amount: displayTotal ? String(displayTotal) : '' }))
  }, [displayTotal, payment.collect, amountTouched])

  const validate = () => {
    const errs = {}
    const isDC = form.document_type === 'delivery_challan'

    // Customer required for all except DC
    if (!isDC && !form.customer_id) errs.customer_id = 'Select customer'

    // Source warehouse always required
    if (!form.warehouse_id) errs.warehouse_id = 'Select source warehouse'
    if (!form.invoice_date) errs.invoice_date = 'Required'

    // DC-specific: destination warehouse required
    if (isDC && !form.dc_destination_warehouse_id) {
      errs.dc_destination_warehouse_id = 'Select destination warehouse'
    }

    // Addresses required only for actual invoices, not DC/quotation
    const needsAddress = ['b2b_invoice', 'b2c_invoice'].includes(form.document_type)
    if (needsAddress && !form.billing_address_id) errs.billing_address_id = 'Select billing address'
    if (needsAddress && !form.shipping_address_id) errs.shipping_address_id = 'Select shipping address'

    items.forEach((item, idx) => {
      if (!item.product) errs[`item_${idx}`] = 'Select product'
      else if (!item.quantity || Number(item.quantity) <= 0) errs[`item_${idx}`] = 'Enter quantity'
      else if (!item.unit_price || Number(item.unit_price) < 0) errs[`item_${idx}`] = 'Enter price'
      else if (!item.hsn_code || item.hsn_code.length < 4) errs[`item_${idx}`] = 'Enter valid HSN (min 4 digits)'
    })

    // DC: vehicle required (either from dropdown or legacy text)
    if (isDC && !form.vehicle_id && !form.vehicle_number?.trim()) {
      errs.vehicle_number = 'Select a vehicle for Delivery Challan'
    }

    // Payment validation — skip for quotation and DC (no payment section shown)
    const hasPaymentSection = !['quotation', 'delivery_challan'].includes(form.document_type)
    if (hasPaymentSection && payment.collect) {
      if (!payment.is_advance && (!payment.amount || Number(payment.amount) <= 0))
        errs.payment_amount = 'Enter payment amount'
      if (payment.payment_mode !== 'cash' && !payment.reference_number?.trim())
        errs.payment_reference = 'Reference no. required for non-cash payments'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  // Credit limit check (only for b2b/b2c invoices, not quotations/DC)
  const checkCreditLimit = () => {
    if (!creditInfo) return true
    const docType = form.document_type
    if (!['b2b_invoice','b2c_invoice'].includes(docType)) return true
    const { limit, outstanding, available } = creditInfo

    // Use the grand total shown on the invoice — after invoice-level discount
    // and round-off — so the credit check matches what the customer is billed.
    const invoiceTotal = displayTotal
    const paid = payment.collect && payment.amount ? Number(payment.amount) : 0

    if (limit === 0) {
      // Zero credit — must collect FULL payment
      if (paid < invoiceTotal - 0.01) {
        toast.error(
          `⚠️ ${customerDetail?.trade_name || 'Customer'} has NO credit limit. ` +
          `Full payment of ₹${invoiceTotal.toLocaleString('en-IN',{minimumFractionDigits:2})} required before saving.`,
          { duration: 6000 }
        )
        return false
      }
    } else {
      // Credit customer — block if available credit < invoice total (after payment)
      const netNew = invoiceTotal - paid
      if (netNew > available) {
        toast.error(
          `❌ Insufficient credit balance! ` +
          `Available: ₹${available.toLocaleString('en-IN',{minimumFractionDigits:2})} · ` +
          `Invoice needs: ₹${netNew.toLocaleString('en-IN',{minimumFractionDigits:2})}. ` +
          `Invoice blocked.`,
          { duration: 8000 }
        )
        return false
      }
    }
    return true
  }

  const receiptMutation = useMutation({
    mutationFn: (d) => receiptAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['invoices'])
      qc.invalidateQueries(['receipts'])
      toast.success('Invoice created and payment recorded')
      navigate('/billing')
    },
    onError: (e) => {
      const msg = e?.response?.data?.detail || e?.message || 'Unknown error'
      toast.error('Invoice saved but payment failed: ' + msg)
      navigate('/billing')
    },
  })

  const mutation = useMutation({
    mutationFn: (d) => invoiceAPI.create(d),
    onSuccess: async (res) => {
      qc.invalidateQueries(['invoices'])
      // If converted from quotation, mark it as invoiced
      if (quotation?.id) {
        try {
          await invoiceAPI.markQuotationInvoiced(quotation.id, res.data.id)
        } catch { /* best effort */ }
        qc.invalidateQueries(['invoice', String(quotation.id)])
      }
      // Post payment using same mutation pattern as ReceiptsPage
      if (payment.collect && payment.amount && Number(payment.amount) > 0) {
        receiptMutation.mutate({
          customer_id: Number(form.customer_id),
          invoice_id: payment.is_advance ? null : res.data.id,
          payment_date: payment.payment_date,
          amount: Number(payment.amount),
          payment_mode: payment.payment_mode,
          reference_number: payment.reference_number || null,
          tds_amount: 0,
          is_advance: false,
          notes: payment.is_advance ? 'Advance payment' : 'Payment at invoice creation',
        })
      } else {
        toast.success('Invoice created successfully')
        navigate('/billing')
      }
    },
    onError: (e) => {
      const detail = e.response?.data?.detail
      if (detail && typeof detail === 'object' && detail.code === 'CREDIT_LIMIT_EXCEEDED') {
        setCreditError(detail)
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Failed to create invoice')
      }
    },
  })


  const handleSubmit = () => {
    setCreditError(null)
    // Validate first, then show confirmation
    if (!validate()) {
      // Surface the first validation error visibly and scroll to the top
      // so the highlighted field is in view.
      const errs = {}
      const isDC = form.document_type === 'delivery_challan'
      if (!isDC && !form.customer_id) errs.customer_id = 'Select customer'
      if (!form.warehouse_id) errs.warehouse_id = 'Select source warehouse'
      if (!form.invoice_date) errs.invoice_date = 'Required'
      if (isDC && !form.dc_destination_warehouse_id) errs.dc_destination_warehouse_id = 'Select destination warehouse'
      const needsAddr = ['b2b_invoice', 'b2c_invoice'].includes(form.document_type)
      if (needsAddr && !form.billing_address_id) errs.billing_address_id = 'Select billing address'
      if (needsAddr && !form.shipping_address_id) errs.shipping_address_id = 'Select shipping address'
      items.forEach((item, idx) => {
        if (!item.product) errs[`item_${idx}`] = 'Select product'
        else if (!item.quantity || Number(item.quantity) <= 0) errs[`item_${idx}`] = 'Enter quantity'
        else if (!item.unit_price || Number(item.unit_price) < 0) errs[`item_${idx}`] = 'Enter price'
        else if (!item.hsn_code || item.hsn_code.length < 4) errs[`item_${idx}`] = 'Enter valid HSN (min 4 digits)'
      })
      if (isDC && !form.vehicle_id && !form.vehicle_number?.trim()) errs.vehicle_number = 'Select a vehicle for Delivery Challan'
      const hasPaymentSection = !['quotation', 'delivery_challan'].includes(form.document_type)
      if (hasPaymentSection && payment.collect) {
        if (!payment.is_advance && (!payment.amount || Number(payment.amount) <= 0)) errs.payment_amount = 'Enter payment amount'
        if (payment.payment_mode !== 'cash' && !payment.reference_number?.trim()) errs.payment_reference = 'Reference no. required for non-cash payments'
      }
      const firstError = Object.values(errs)[0] || 'Please fix the highlighted errors before saving'
      toast.error(firstError)
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
    setShowConfirm(true)
  }

  const handleConfirmedSubmit = () => {
    setShowConfirm(false)
    if (!checkCreditLimit()) return
    const errsCheck = {}
    const isDCCheck = form.document_type === 'delivery_challan'
    if (!isDCCheck && !form.customer_id) errsCheck.customer_id = 'Select customer'
    if (!form.warehouse_id) errsCheck.warehouse_id = 'Select source warehouse'
    if (!form.invoice_date) errsCheck.invoice_date = 'Required'
    if (isDCCheck && !form.dc_destination_warehouse_id) errsCheck.dc_destination_warehouse_id = 'Select destination'
    if (!isDCCheck && ['b2b_invoice','b2c_invoice'].includes(form.document_type) && !form.billing_address_id) errsCheck.billing_address_id = 'Required'
    if (isDCCheck && !form.vehicle_id && !form.vehicle_number?.trim()) errsCheck.vehicle_number = 'Select vehicle'
    items.forEach((item, idx) => {
      if (!item.product) errsCheck[`item_${idx}`] = 'Select product'
      else if (!item.hsn_code || item.hsn_code.length < 4) errsCheck[`item_${idx}`] = 'HSN min 4 digits'
    })
    console.log('[DC DEBUG] form.document_type:', form.document_type)
    console.log('[DC DEBUG] form.warehouse_id:', form.warehouse_id)
    console.log('[DC DEBUG] form.dc_destination_warehouse_id:', form.dc_destination_warehouse_id)
    console.log('[DC DEBUG] form.vehicle_id:', form.vehicle_id, 'vehicle_number:', form.vehicle_number)
    console.log('[DC DEBUG] items:', items.map(i => ({ product: i.product?.part_name, hsn: i.hsn_code, qty: i.quantity })))
    console.log('[DC DEBUG] validation errors:', errsCheck)
    // validation already passed in handleSubmit
    const isDC = form.document_type === 'delivery_challan'
    mutation.mutate({
      document_type: form.document_type,
      customer_id: form.customer_id ? Number(form.customer_id) : (isDC ? null : 0),
      warehouse_id: Number(form.warehouse_id),
      billing_address_id: form.billing_address_id ? Number(form.billing_address_id) : null,
      shipping_address_id: form.shipping_address_id ? Number(form.shipping_address_id) : null,
      invoice_date: form.invoice_date,
      due_date: form.due_date || null,
      invoice_discount: Number(form.invoice_discount) || 0,
      notes: form.notes || null,
      dc_destination_warehouse_id: form.dc_destination_warehouse_id ? Number(form.dc_destination_warehouse_id) : null,
      vehicle_number: form.vehicle_number || null,
      vehicle_id: form.vehicle_id ? Number(form.vehicle_id) : null,
      driver_name: form.driver_name || null,
      lr_number: form.lr_number || null,
      transporter_id: form.transporter_id ? Number(form.transporter_id) : null,
      transporter_name: form.transporter_name || null,
      show_transport_on_print: form.show_transport_on_print,
      terms_conditions: form.terms_conditions || null,
      items: items.map(item => ({
        product_id: item.product.id,
        quantity: Number(item.quantity),
        unit_price: Number(item.unit_price),
        discount_percent: Number(item.discount_percent) || 0,
        gst_percent: Number(item.gst_percent),
        hsn_code: item.hsn_code,
        notes: item.notes || null,
      })),
    })
  }

  const needsAddress = ['b2b_invoice', 'b2c_invoice'].includes(form.document_type)

  return (
    <>
    <div className="max-w-5xl">
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/billing')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Billing
          </button>
          <h1 className="page-title">New Invoice</h1>
        </div>
        <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
          <Save size={14} /> Save Invoice
        </Button>
      </div>

      <div className="space-y-4">

        {/* Header */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Invoice Details</div></div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Document Type</label>
                <select value={form.document_type} onChange={e => {
                    hc('document_type', e.target.value)
                    // Re-price line items based on new doc type
                    const _newDocType = e.target.value
                    setItems(prev => prev.map(item => {
                      if (!item.product) return item
                      const price = priceForDoc(item.product, _newDocType, form.is_b2b, item.unit_price)
                      return { ...item, unit_price: String(price) }
                    }))
                  }} className={ic()}>
                  {DOC_TYPES.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Date <span className="text-red-500">*</span></label>
                <input type="date" value={form.invoice_date} onChange={e => hc('invoice_date', e.target.value)} className={ic(errors.invoice_date)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Due Date</label>
                <input type="date" value={form.due_date} onChange={e => hc('due_date', e.target.value)} className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Warehouse <span className="text-red-500">*</span></label>
                {isSales ? (
                  // Sales users: show their warehouse as read-only text
                  <div className="h-9 px-3 flex items-center rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-700">
                    {(warehouses || []).find(w => Number(w.id) === Number(userWarehouse))?.name || userWarehouse ? 'Loading...' : 'No warehouse assigned'}
                  </div>
                ) : isAdminUser ? (
                  <select value={form.warehouse_id} onChange={e => hc('warehouse_id', e.target.value)}
                    className={ic(errors.warehouse_id)}>
                    <option value="">Select...</option>
                    {(warehouses || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                ) : (
                  <select value={form.warehouse_id} onChange={e => hc('warehouse_id', e.target.value)}
                    className={ic(errors.warehouse_id)}>
                    <option value="">Select warehouse...</option>
                    {(warehouses || [])
                      .filter(w => !userWarehouse || Number(w.id) === Number(userWarehouse))
                      .map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                )}
                {errors.warehouse_id && <p className="text-xs text-red-500 mt-1">{errors.warehouse_id}</p>}
              </div>
            </div>
          </div>
        </div>

        {/* Customer — hidden for DC; DC uses destination warehouse instead */}
        {form.document_type === 'delivery_challan' && (
          <DCWarehouseCard
            warehouses={warehouses?.items || warehouses || []}
            form={form}
            errors={errors}
            onChange={hc}
          />
        )}
        {form.document_type !== 'delivery_challan' && (
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Customer</div></div>
          <div className="card-body space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Customer <span className="text-red-500">*</span></label>
              <div className="flex gap-2">
                <select value={form.customer_id}
                  onChange={e => { hc('customer_id', e.target.value); setCustomerAddresses([]); setShowAddAddress(false); setShowNewCustomer(false) }}
                  className={clsx(ic(errors.customer_id), 'flex-1')}>
                  <option value="">Select customer...</option>
                  {customers?.map(c => <option key={c.id} value={c.id}>{c.trade_name}</option>)}
                </select>
                <button type="button"
                  onClick={() => setShowNewCustomer(p => !p)}
                  title="Add new customer"
                  className={clsx(
                    'flex items-center gap-1.5 px-3 h-9 rounded-lg border text-xs font-medium transition-colors whitespace-nowrap',
                    showNewCustomer
                      ? 'bg-green-600 border-green-600 text-white'
                      : 'border-gray-300 text-gray-600 hover:border-green-400 hover:text-green-600'
                  )}>
                  <UserPlus size={13} /> New
                </button>
              </div>
              {showNewCustomer && (
                <NewCustomerInline
                  states={states}
                  onCreated={(c) => {
                    // Add new customer directly to query cache so dropdown shows it immediately
                    qc.setQueryData(['customers-list'], (old) => {
                      const list = Array.isArray(old) ? old : (old?.items || [])
                      return [...list, c]
                    })
                    qc.invalidateQueries(['customers-list'])
                    hc('customer_id', String(c.id))
                    setShowNewCustomer(false)
                  }}
                  onCancel={() => setShowNewCustomer(false)}
                />
              )}
              {errors.customer_id && <p className="text-xs text-red-500 mt-1">{errors.customer_id}</p>}
              {creditInfo && form.customer_id && ['b2b_invoice','b2c_invoice'].includes(form.document_type) && (
                <div className={clsx(
                  'mt-2 p-2.5 rounded-lg text-xs flex items-start gap-2 border',
                  creditInfo.limit === 0
                    ? 'bg-red-50 border-red-200 text-red-700'
                    : creditInfo.available <= 0
                      ? 'bg-red-50 border-red-200 text-red-700'
                      : 'bg-blue-50 border-blue-200 text-blue-700'
                )}>
                  <div className="flex-1">
                    {creditInfo.limit === 0 ? (
                      <span className="font-semibold">⚠ No credit limit — full payment required before saving</span>
                    ) : (
                      <span>
                        Credit Limit: <strong>₹{creditInfo.limit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
                        {' · '}Outstanding: <strong>₹{creditInfo.outstanding.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
                        {' · '}Available: <strong className={creditInfo.available <= 0 ? 'text-red-600' : 'text-green-700'}>
                          ₹{creditInfo.available.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </strong>
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>

            {form.customer_id && needsAddress && (
              <>
                {customerAddresses.length === 0 ? (
                  <AlertBox type="warning">
                    This customer has no addresses.
                    <button onClick={() => setShowAddAddress(true)} className="ml-2 text-blue-600 hover:text-blue-700 underline text-xs">Add address now</button>
                  </AlertBox>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Billing Address <span className="text-red-500">*</span></label>
                      <select value={form.billing_address_id} onChange={e => hc('billing_address_id', e.target.value)} className={ic(errors.billing_address_id)}>
                        <option value="">Select billing address...</option>
                        {customerAddresses.map(a => <option key={a.id} value={a.id}>{a.label} — {a.address_line1}, {a.city}</option>)}
                      </select>
                      {errors.billing_address_id && <p className="text-xs text-red-500 mt-1">{errors.billing_address_id}</p>}
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Shipping Address <span className="text-red-500">*</span></label>
                      <select value={form.shipping_address_id} onChange={e => hc('shipping_address_id', e.target.value)} className={ic(errors.shipping_address_id)}>
                        <option value="">Select shipping address...</option>
                        {customerAddresses.map(a => <option key={a.id} value={a.id}>{a.label} — {a.address_line1}, {a.city}</option>)}
                      </select>
                      {errors.shipping_address_id && <p className="text-xs text-red-500 mt-1">{errors.shipping_address_id}</p>}
                    </div>
                  </div>
                )}
                <div>
                  <button onClick={() => setShowAddAddress(!showAddAddress)}
                    className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
                    <Plus size={11} /> Add new address
                  </button>
                  {showAddAddress && (
                    <AddressCreator
                      customerId={form.customer_id}
                      states={states}
                      onCreated={(addr) => {
                        setCustomerAddresses(p => [...p, addr])
                        setForm(f => ({ ...f, billing_address_id: String(addr.id), shipping_address_id: String(addr.id) }))
                        setShowAddAddress(false)
                      }}
                      onCancel={() => setShowAddAddress(false)}
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
        )}

        {/* Items */}
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-700">Line Items</div>
            <button onClick={addItem} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700">
              <Plus size={12} /> Add Item
            </button>
          </div>
          <div className="card-body">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[800px]">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left text-xs font-medium text-gray-500 pb-2 w-72">Product</th>
                    <th className="text-left text-xs font-medium text-gray-500 pb-2 w-24">HSN</th>
                    <th className="text-left text-xs font-medium text-gray-500 pb-2 w-24">Qty</th>
                    <th className="text-left text-xs font-medium text-gray-500 pb-2 w-32">Price (₹)</th>
                    <th className="text-left text-xs font-medium text-gray-500 pb-2 w-20">Disc %</th>
                    <th className="text-left text-xs font-medium text-gray-500 pb-2 w-20">GST %</th>
                    <th className="text-right text-xs font-medium text-gray-500 pb-2 w-28">Total (₹)</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {items.map((item, idx) => {
                    const qty = Number(item.quantity) || 0
                    const price = Number(item.unit_price) || 0
                    const disc = Number(item.discount_percent) || 0
                    const gst = Number(item.gst_percent) || 0
                    const taxable = qty * price * (1 - disc / 100)
                    const lineTotal = taxable * (1 + gst / 100)
                    return (
                      <Fragment key={item._key}>
                      <tr className={clsx('', errors[`item_${idx}`] ? 'bg-red-50/30' : '')}>
                        <td className="py-2 pr-2">
                          <ProductSearchCell value={item.product} warehouseId={form.warehouse_id} documentType={form.document_type} onSelect={p => updateItem(idx, 'product', p)} />
                          {errors[`item_${idx}`] && <p className="text-xs text-red-500 mt-1">{errors[`item_${idx}`]}</p>}
                          <input
                            value={item.notes || ''}
                            onChange={e => updateItem(idx, 'notes', e.target.value)}
                            placeholder="Notes (optional)"
                            className="w-full mt-1 px-1.5 py-0.5 text-xs border-0 border-b border-gray-200 bg-transparent focus:outline-none focus:border-blue-400 text-gray-500 placeholder-gray-300"
                          />
                      </td>
                        <td className="py-2 pr-2">
                          <input value={item.hsn_code} onChange={e => updateItem(idx, 'hsn_code', e.target.value)}
                            placeholder="85171200" maxLength={8}
                            className="w-full h-9 px-2 rounded border border-gray-300 text-xs font-mono focus:outline-none focus:border-blue-500" />
                        </td>
                        <td className="py-2 pr-2">
                          <input type="number" min="1" step="1" pattern="[0-9]*" inputMode="numeric" value={item.quantity}
                            onChange={e => updateItem(idx, 'quantity', e.target.value)}
                            className="w-full h-9 px-2 rounded border border-gray-300 text-xs focus:outline-none focus:border-blue-500" />
                        </td>
                        <td className="py-2 pr-2">
                          <input type="number" step="0.01" min="0" value={item.unit_price}
                            onChange={e => updateItem(idx, 'unit_price', e.target.value)}
                            className="w-full h-9 px-2 rounded border border-gray-300 text-xs focus:outline-none focus:border-blue-500" />
                        </td>
                        <td className="py-2 pr-2">
                          <input type="number" step="0.01" min="0" max="100" value={item.discount_percent}
                            onChange={e => updateItem(idx, 'discount_percent', e.target.value)}
                            className="w-full h-9 px-2 rounded border border-gray-300 text-xs focus:outline-none focus:border-blue-500" />
                        </td>
                        <td className="py-2 pr-2">
                          <input type="text" readOnly tabIndex={-1}
                            value={item.product ? `${item.gst_percent || 0}%` : '—'}
                            title="GST % is set from the product master and cannot be changed on the invoice"
                            className="w-full h-8 px-1 rounded border border-gray-200 bg-gray-100 text-xs text-gray-600 text-center cursor-not-allowed focus:outline-none" />
                        </td>
                        
                        <td className="py-2 pr-2 text-right text-xs font-medium text-gray-700">
                          ₹{lineTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2">
                          <button onClick={() => removeItem(idx)} className="text-gray-300 hover:text-red-500">
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Totals */}
            <div className="mt-4 pt-4 border-t border-gray-100 flex justify-between items-end">
              <div className="w-64">
                <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Discount (₹)</label>
                <input type="number" step="0.01" min="0" value={form.invoice_discount}
                  onChange={e => hc('invoice_discount', e.target.value)}
                  className="w-40 h-8 px-2 rounded border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div className="w-64 space-y-1.5">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>Taxable Amount</span>
                  <span>₹{totals.taxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between text-sm text-gray-600">
                  <span>GST</span>
                  <span>₹{totals.tax.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                {invoiceDiscount > 0 && (
                  <div className="flex justify-between text-sm text-red-500">
                    <span>Invoice Discount</span>
                    <span>−₹{invoiceDiscount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </div>
                )}
                {Math.abs(roundOff) >= 0.005 && (
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>Round Off</span>
                    <span>{roundOff < 0 ? '−' : '+'}₹{Math.abs(roundOff).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold text-gray-800 pt-1 border-t border-gray-200">
                  <span>Grand Total</span>
                  <span>₹{displayTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Payment — hidden for quotations and delivery challans */}
        {!['quotation','delivery_challan'].includes(form.document_type) && (
        <div className="card">
          <div className="card-header">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <CreditCard size={15} className="text-blue-500" />
                Payment Collection
              </div>
              {/* Collect payment toggle */}
              <label className="flex items-center gap-2 cursor-pointer"
                onClick={() => setPayment(p => ({ ...p, collect: !p.collect }))}>
                <div className={clsx(
                  'w-10 h-5 rounded-full transition-colors relative',
                  payment.collect ? 'bg-blue-600' : 'bg-gray-300'
                )}>
                  <div className={clsx(
                    'absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                    payment.collect ? 'translate-x-5' : 'translate-x-0.5'
                  )} />
                </div>
                <span className="text-xs font-medium text-gray-600">
                  {payment.collect ? 'Collecting payment' : 'No payment now'}
                </span>
              </label>
            </div>
          </div>
          {payment.collect && (
            <div className="card-body space-y-3">


              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Amount (₹) {!payment.is_advance && <span className="text-red-500">*</span>}
                  </label>
                  <input
                    type="number" step="0.01" min="0"
                    value={payment.amount}
                    onChange={e => { setAmountTouched(true); setP('amount')(e.target.value) }}
                    placeholder="Enter amount"
                    className={clsx(
                      'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none',
                      errors.payment_amount ? 'border-red-400' : 'border-gray-300 focus:border-blue-500'
                    )}
                  />
                  {errors.payment_amount && (
                    <p className="text-xs text-red-500 mt-0.5">{errors.payment_amount}</p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Payment Date</label>
                  <input
                    type="date"
                    value={payment.payment_date}
                    onChange={e => setP('payment_date')(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Payment Mode</label>
                  <select
                    value={payment.payment_mode}
                    onChange={e => setP('payment_mode')(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                    {['cash','bank','cheque','upi','neft','rtgs'].map(m => (
                      <option key={m} value={m}>{m.toUpperCase()}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Reference No. {payment.payment_mode !== 'cash' && <span className="text-red-500">*</span>}
                  </label>
                  <input
                    value={payment.reference_number}
                    onChange={e => setP('reference_number')(e.target.value)}
                    placeholder="UTR / Cheque / UPI Ref"
                    className={clsx(
                      'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none',
                      errors.payment_reference ? 'border-red-400' : 'border-gray-300 focus:border-blue-500'
                    )}
                  />
                  {errors.payment_reference && (
                    <p className="text-xs text-red-500 mt-0.5">{errors.payment_reference}</p>
                  )}
                </div>
              </div>

              {/* Payment summary */}
              {payment.amount && Number(payment.amount) > 0 && (
                <div className="p-3 bg-green-50 rounded-lg text-sm border border-green-200">
                  <div className="flex justify-between text-gray-600">
                    <span>Invoice Total</span>
                    <span className="font-medium">
                      ₹{displayTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="flex justify-between mt-1 font-semibold text-green-700">
                    <span>{payment.is_advance ? 'Advance Amount' : 'Amount Paid Now'}</span>
                    <span>₹{Number(payment.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              )}
            </div>
          )}
          {!payment.collect && (
            <div className="px-4 pb-4 text-xs text-gray-400">
              Toggle on to collect payment at time of invoicing.
            </div>
          )}
        </div>
        )}

        {/* Transport Details — required for DC, optional for Invoice */}
        {(form.document_type === 'delivery_challan' || form.document_type === 'b2b_invoice' || form.document_type === 'b2c_invoice') && (
          <TransportSection
            transporters={transporters}
            vehicles={vehicles || []}
            form={form}
            onChange={(field, val) => hc(field, val)}
            requireVehicle={form.document_type === 'delivery_challan'}
            vehicleError={errors.vehicle_number}
          />
        )}

        {/* Notes */}
        <div className="card">
          <div className="card-body">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <textarea value={form.notes} onChange={e => hc('notes', e.target.value)}
                  rows={2} placeholder="Internal notes..."
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500 resize-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Terms & Conditions</label>
                <textarea value={form.terms_conditions} onChange={e => hc('terms_conditions', e.target.value)}
                  rows={2} placeholder="Payment terms, delivery terms..."
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500 resize-none" />
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between pb-6">
          <Button variant="secondary" onClick={() => navigate('/billing')}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
            <Save size={14} /> Save Invoice
          </Button>
        </div>
      </div>
    </div>

      {/* Save Confirmation Dialog */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-sm shadow-2xl p-6 space-y-4">
            <div className="text-center">
              <div className="text-3xl mb-2">📄</div>
              <h3 className="text-lg font-semibold text-gray-900">Confirm Save</h3>
              <p className="text-sm text-gray-600 mt-1">
                Are you sure you want to save this{' '}
                <span className="font-semibold text-blue-700">
                  {form.document_type === 'b2b_invoice' ? 'B2B Invoice' :
                   form.document_type === 'b2c_invoice' ? 'B2C Invoice' :
                   form.document_type === 'quotation' ? 'Quotation' :
                   form.document_type === 'delivery_challan' ? 'Delivery Challan' :
                   form.document_type === 'credit_note' ? 'Credit Note' : 'Invoice'}
                </span>?
              </p>
              {form.document_type === 'delivery_challan' && (
                <p className="text-xs text-amber-600 mt-2 bg-amber-50 rounded-lg p-2">
                  Stock will be validated but <strong>not reduced</strong> until DC is delivered.
                </p>
              )}
            </div>
            {creditError && (
              <div className="rounded-xl bg-red-50 border border-red-200 p-3 text-xs space-y-1 mb-2">
                <div className="font-semibold text-red-700 mb-1">&#x26A0; Credit Limit Exceeded</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-red-600">
                  <span>Credit Limit</span><span className="text-right font-mono">&#x20B9;{Number(creditError.credit_limit||0).toLocaleString('en-IN',{minimumFractionDigits:2})}</span>
                  <span>Outstanding</span><span className="text-right font-mono">&#x20B9;{Number(creditError.current_outstanding||0).toLocaleString('en-IN',{minimumFractionDigits:2})}</span>
                  <span>Available Credit</span><span className="text-right font-mono">&#x20B9;{Number(creditError.available_credit||0).toLocaleString('en-IN',{minimumFractionDigits:2})}</span>
                  <span>This Invoice</span><span className="text-right font-mono">&#x20B9;{Number(creditError.this_invoice||0).toLocaleString('en-IN',{minimumFractionDigits:2})}</span>
                  <span className="font-bold pt-1 border-t border-red-200">Shortfall</span><span className="text-right font-mono font-bold pt-1 border-t border-red-200 text-red-800">&#x20B9;{Number(creditError.shortfall||0).toLocaleString('en-IN',{minimumFractionDigits:2})}</span>
                </div>
              </div>
            )}
            <div className="flex gap-3">
              <button onClick={() => { setShowConfirm(false); setCreditError(null) }}
                className="flex-1 h-10 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleConfirmedSubmit}
                disabled={mutation.isPending}
                className="flex-1 h-10 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-60 font-medium">
                {mutation.isPending ? 'Saving...' : 'Yes, Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
