import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsAPI } from '@/api/settings'
import { useAuthStore, ALL_PAGES } from '@/store/authStore'
import { Button, Spinner } from '@/components/ui'
import { Building2, FileText, Hash, ChevronRight, Save, CheckCircle, Upload, X, Shield, Truck, Pencil, Trash2, Plus, Percent, AlertTriangle, Eye, Play, Database } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'

const TABS = [
  { id: 'company',     label: 'Company Info',       icon: Building2 },
  { id: 'sequences',   label: 'Invoice Numbering',  icon: Hash },
  { id: 'terms',       label: 'Terms & Conditions', icon: FileText },
  { id: 'permissions', label: 'Page Permissions',   icon: Shield, superAdminOnly: true },
  { id: 'vehicles',    label: 'Vehicles',           icon: Hash },
  { id: 'gst-rates',   label: 'GST Rates',          icon: Percent },
  { id: 'tds',         label: 'TDS Sections',       icon: FileText },
  { id: 'dpdp',        label: 'Data Privacy',       icon: Database },
]

// ── Input components ──────────────────────────────────────────
function Field({ label, children, required }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}

function TextInput({ value, onChange, placeholder, maxLength, disabled }) {
  return (
    <input value={value || ''} onChange={onChange} placeholder={placeholder}
      maxLength={maxLength} disabled={disabled}
      className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm
        focus:outline-none focus:border-blue-500 disabled:bg-gray-50 disabled:text-gray-400" />
  )
}

// ── Company Info Tab ──────────────────────────────────────────
function CompanyTab({ data, states }) {
  const qc = useQueryClient()
  const [form, setForm] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => { if (data) setForm({ ...data }) }, [data])

  const mutation = useMutation({
    mutationFn: (d) => settingsAPI.updateCompany(d),
    onSuccess: () => {
      qc.invalidateQueries(['company-settings'])
      setSaved(true)
      toast.success('Company settings saved')
      setTimeout(() => setSaved(false), 3000)
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Save failed'),
  })

  if (!form) return <div className="flex justify-center py-10"><Spinner size={20} /></div>

  const set = (field) => (e) => setForm(p => ({ ...p, [field]: e.target.value }))

  return (
    <div className="space-y-6">
      {/* Logo Upload */}
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
          Company Logo
        </h3>
        <div className="flex items-center gap-4">
          {form.logo_path ? (
            <div className="relative group">
              <img
                src={form.logo_path}
                alt="Company Logo"
                className="h-16 w-auto max-w-48 object-contain rounded-lg border border-gray-200 bg-gray-50 p-1"
              />
              <button
                onClick={() => setForm(p => ({ ...p, logo_path: null }))}
                className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-500 text-white
                  flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <X size={10} />
              </button>
            </div>
          ) : (
            <div className="h-16 w-32 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50
              flex items-center justify-center text-gray-400">
              <Building2 size={24} />
            </div>
          )}
          <div>
            <label className="cursor-pointer">
              <input type="file" accept="image/png,image/jpeg,image/jpg,image/webp"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files[0]
                  if (!file) return
                  if (file.size > 2 * 1024 * 1024) { toast.error('File must be under 2MB'); return }
                  const fd = new FormData()
                  fd.append('file', file)
                  try {
                    const res = await settingsAPI.uploadLogo(fd)
                    setForm(p => ({ ...p, logo_path: res.data.logo_path }))
                    qc.invalidateQueries(['company-settings'])
                    toast.success('Logo uploaded')
                  } catch (e) {
                    toast.error(e.response?.data?.detail || 'Upload failed')
                  }
                }} />
              <div className="flex items-center gap-2 px-3 h-9 rounded-lg border border-gray-300
                text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600 cursor-pointer transition-colors">
                <Upload size={14} /> Upload Logo
              </div>
            </label>
            <p className="text-xs text-gray-400 mt-1.5">PNG, JPG or WebP · Max 2MB</p>
            <p className="text-xs text-gray-400">Recommended: 200×80px transparent PNG</p>
          </div>
        </div>
      </div>

      {/* Basic Info */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
          Business Information
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Company Name" required>
            <TextInput value={form.company_name} onChange={set('company_name')}
              placeholder="ABC Traders Pvt. Ltd." />
          </Field>
          <Field label="GSTIN" required>
            <TextInput value={form.gstin} onChange={set('gstin')}
              placeholder="29AAAAA0000A1Z5" maxLength={15} />
          </Field>
          <Field label="State" required>
            <select value={form.state_code || ''}
              onChange={e => {
                const s = states?.find(s => s.code === Number(e.target.value))
                setForm(p => ({ ...p, state_code: Number(e.target.value), state: s?.name || '' }))
              }}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm
                focus:outline-none focus:border-blue-500">
              <option value="">Select state...</option>
              {states?.map(s => (
                <option key={s.code} value={s.code}>{s.code} — {s.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Phone">
            <TextInput value={form.phone} onChange={set('phone')}
              placeholder="9999999999" maxLength={15} />
          </Field>
          <Field label="Email">
            <TextInput value={form.email} onChange={set('email')}
              placeholder="info@company.com" />
          </Field>
        </div>
      </div>

      {/* Address */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
          Address
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Field label="Address Line 1" required>
              <TextInput value={form.address_line1} onChange={set('address_line1')}
                placeholder="Door No., Street Name" />
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Address Line 2">
              <TextInput value={form.address_line2} onChange={set('address_line2')}
                placeholder="Area, Landmark" />
            </Field>
          </div>
          <Field label="City" required>
            <TextInput value={form.city} onChange={set('city')} placeholder="City" />
          </Field>
          <Field label="Pincode" required>
            <TextInput value={form.pincode} onChange={set('pincode')}
              placeholder="600001" maxLength={6} />
          </Field>
        </div>
      </div>

      {/* Business Config */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
          Business Configuration
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <Field label="E-Way Bill Threshold (₹)">
            <TextInput value={form.eway_threshold} onChange={set('eway_threshold')}
              placeholder="50000" />
          </Field>
          <Field label="Bank Stock Margin (%)">
            <TextInput value={form.bank_stock_margin} onChange={set('bank_stock_margin')}
              placeholder="25" />
          </Field>
          <Field label="Default Min Margin (%)">
            <TextInput value={form.default_min_margin_pct} onChange={set('default_min_margin_pct')}
              placeholder="10" />
          </Field>
          <Field label="Financial Year Start Month">
            <select value={form.financial_year_start || 4}
              onChange={e => setForm(p => ({ ...p, financial_year_start: Number(e.target.value) }))}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
              {[
                [1,'January'],[2,'February'],[3,'March'],[4,'April'],
                [7,'July'],[10,'October']
              ].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div className="mt-3">
          <p className="text-xs font-medium text-gray-600 mb-2">Transport Details on Print</p>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input type="checkbox"
                checked={form.show_transport_on_invoice !== false}
                onChange={e => setForm(p => ({ ...p, show_transport_on_invoice: e.target.checked }))}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
              Show on Invoice
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input type="checkbox"
                checked={form.show_transport_on_challan !== false}
                onChange={e => setForm(p => ({ ...p, show_transport_on_challan: e.target.checked }))}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
              Show on Delivery Challan
            </label>
          </div>
        </div>
      </div>

      {/* Bank Details Section */}
      <div className="border-t pt-4 mt-2">
        <div className="text-sm font-semibold text-gray-700 mb-3">Bank Details</div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Account Name">
            <TextInput value={form.bank_account_name || ''} onChange={set('bank_account_name')}
              placeholder="Account holder name" />
          </Field>
          <Field label="Bank Name">
            <TextInput value={form.bank_name || ''} onChange={set('bank_name')}
              placeholder="Bank name" />
          </Field>
          <Field label="Account Number">
            <TextInput value={form.bank_account_number || ''} onChange={set('bank_account_number')}
              placeholder="Account number" />
          </Field>
          <Field label="IFSC Code">
            <TextInput value={form.bank_ifsc || ''} onChange={set('bank_ifsc')}
              placeholder="IFSC code" />
          </Field>
          <Field label="Branch">
            <TextInput value={form.bank_branch || ''} onChange={set('bank_branch')}
              placeholder="Branch name" />
          </Field>
          <Field label="UPI ID">
            <TextInput value={form.upi_id || ''} onChange={set('upi_id')}
              placeholder="UPI ID (optional)" />
          </Field>
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <Button variant="primary" onClick={() => mutation.mutate(form)}
          disabled={mutation.isPending}>
          {saved
            ? <><CheckCircle size={14} className="text-green-300" /> Saved</>
            : <><Save size={14} /> {mutation.isPending ? 'Saving...' : 'Save Settings'}</>
          }
        </Button>
      </div>
    </div>
  )
}

// ── Invoice Sequences Tab ─────────────────────────────────────
// ── Current FY helper ────────────────────────────────────────
function getCurrentFY() {
  const m = new Date().getMonth() + 1
  const y = new Date().getFullYear()
  return m >= 4 ? `${y}-${String(y+1).slice(2)}` : `${y-1}-${String(y).slice(2)}`
}
const CURRENT_FY = getCurrentFY()
const FY_LIST = [CURRENT_FY, ...['2025-26','2024-25','2023-24'].filter(f => f !== CURRENT_FY)]

function SequencesTab({ sequences }) {
  const qc = useQueryClient()
  const [edits, setEdits] = useState({})
  const [saving, setSaving] = useState({})

  const DOC_LABELS = {
    b2b_invoice: 'B2B Invoice',
    b2c_invoice: 'B2C Invoice',
    quotation: 'Quotation',
    delivery_challan: 'Delivery Challan',
    credit_note: 'Credit Note',
  }

  const handleSave = async (seq) => {
    const edit = edits[seq.id]
    if (!edit) return
    setSaving(p => ({ ...p, [seq.id]: true }))
    try {
      await settingsAPI.updateSequence(seq.id, edit)
      qc.invalidateQueries(['invoice-sequences'])
      toast.success(`${DOC_LABELS[seq.document_type] || seq.document_type} sequence updated`)
      setEdits(p => { const n = { ...p }; delete n[seq.id]; return n })
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to update')
    } finally {
      setSaving(p => ({ ...p, [seq.id]: false }))
    }
  }

  // Show only one row per document_type — prefer current FY, else latest
  const seqMap = {}
  for (const s of (sequences || [])) {
    if (!seqMap[s.document_type] || s.financial_year === CURRENT_FY) {
      seqMap[s.document_type] = s
    }
  }
  const orderedSeqs = Object.values(seqMap)

  if (!sequences?.length) return (
    <div className="text-center py-10 text-gray-400 text-sm">
      No invoice sequences configured. Run seed.py to initialize.
    </div>
  )

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-gray-500">
          Configure prefix, financial year and numbering for each document type.
          The next document number will be Last Number + 1.
        </p>
        <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-1 rounded-full">
          Current FY: {CURRENT_FY}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left text-xs font-medium text-gray-500 pb-2 w-36">Document Type</th>
              <th className="text-left text-xs font-medium text-gray-500 pb-2 w-28">Financial Year</th>
              <th className="text-left text-xs font-medium text-gray-500 pb-2 w-24">Prefix</th>
              <th className="text-left text-xs font-medium text-gray-500 pb-2 w-24">Last No.</th>
              <th className="text-left text-xs font-medium text-gray-500 pb-2">Next Number Preview</th>
              <th className="w-16"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {orderedSeqs.map(seq => {
              const isCurrent = seq.financial_year === CURRENT_FY
              const edit = edits[seq.id] || {
                prefix: seq.prefix,
                last_number: seq.last_number,
                financial_year: seq.financial_year || CURRENT_FY,
              }
              const changed = edits[seq.id] !== undefined
              const nextNum = (Number(edit.last_number) || 0) + 1
              const fyParts = (edit.financial_year || CURRENT_FY).split('-')
              const fyShort = fyParts.length === 2
                ? `${fyParts[0].slice(-2)}-${fyParts[1]}`
                : (edit.financial_year || CURRENT_FY).slice(-5)
              const preview = `${edit.prefix || 'INV'}/${fyShort}/${String(nextNum).padStart(4,'0')}`

              return (
                <tr key={seq.id} className={clsx(
                  'py-2',
                  changed && 'bg-blue-50/50',
                  isCurrent && !changed && 'bg-green-50/30'
                )}>
                  <td className="py-3">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-gray-800">
                        {DOC_LABELS[seq.document_type] || seq.document_type}
                      </span>
                      {isCurrent && (
                        <span className="text-xs px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                          Current
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3">
                    <select
                      value={edit.financial_year || CURRENT_FY}
                      onChange={e => setEdits(p => ({
                        ...p, [seq.id]: { ...edit, financial_year: e.target.value }
                      }))}
                      className="w-24 h-8 px-1.5 rounded border border-gray-300 text-xs font-mono
                        focus:outline-none focus:border-blue-500">
                      {FY_LIST.map(f => (
                        <option key={f} value={f}>{f}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-3">
                    <input value={edit.prefix}
                      onChange={e => setEdits(p => ({
                        ...p, [seq.id]: { ...edit, prefix: e.target.value.toUpperCase() }
                      }))}
                      maxLength={10}
                      className="w-20 h-8 px-2 rounded border border-gray-300 text-xs font-mono
                        focus:outline-none focus:border-blue-500 uppercase" />
                  </td>
                  <td className="py-3">
                    <input type="number" min="0" value={edit.last_number}
                      onChange={e => setEdits(p => ({
                        ...p, [seq.id]: { ...edit, last_number: Number(e.target.value) }
                      }))}
                      className="w-20 h-8 px-2 rounded border border-gray-300 text-xs
                        focus:outline-none focus:border-blue-500" />
                  </td>
                  <td className="py-3">
                    <span className={clsx(
                      'font-mono text-xs px-2 py-1 rounded',
                      changed ? 'text-blue-700 bg-blue-100' : 'text-blue-600 bg-blue-50'
                    )}>
                      {preview}
                    </span>
                  </td>
                  <td className="py-3">
                    {changed && (
                      <button onClick={() => handleSave(seq)}
                        disabled={saving[seq.id]}
                        className="px-3 h-7 rounded bg-blue-600 text-white text-xs hover:bg-blue-700 disabled:opacity-60">
                        {saving[seq.id] ? '...' : 'Save'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Terms & Conditions Tab ────────────────────────────────────
const TERMS_DOC_TYPES = [
  { key: 'terms_b2b_invoice',      label: 'B2B Invoice' },
  { key: 'terms_b2c_invoice',      label: 'B2C Invoice' },
  { key: 'terms_quotation',        label: 'Quotation' },
  { key: 'terms_delivery_challan', label: 'Delivery Challan' },
]

const TERMS_TEMPLATES = {
  terms_b2b_invoice: [
    { label: 'Standard Wholesale', text: `1. Goods once sold will not be taken back or exchanged.\n2. All disputes are subject to local jurisdiction only.\n3. Payment due within 30 days from invoice date.\n4. Interest @18% p.a. will be charged on overdue amounts.\n5. E. & O.E.` },
    { label: 'Credit Terms',       text: `1. Payment terms: 30 days net from invoice date.\n2. A late payment charge of 2% per month will apply on overdue balances.\n3. Goods remain property of seller until full payment is received.\n4. All disputes subject to local jurisdiction only.\n5. E. & O.E.` },
  ],
  terms_b2c_invoice: [
    { label: 'Cash & Carry', text: `1. Payment to be made at time of delivery.\n2. No credit will be extended.\n3. Goods once sold will not be taken back.\n4. All disputes subject to local jurisdiction.\n5. E. & O.E.` },
    { label: 'Retail',       text: `1. No returns or exchanges without original invoice.\n2. Warranty claims as per manufacturer policy.\n3. All disputes subject to local jurisdiction.\n4. E. & O.E.` },
  ],
  terms_quotation: [
    { label: 'Standard Quote', text: `1. This quotation is valid for 15 days from the date of issue.\n2. Prices are subject to change without prior notice after validity period.\n3. Taxes as applicable at the time of invoicing.\n4. Delivery timeline to be confirmed at the time of order.\n5. E. & O.E.` },
  ],
  terms_delivery_challan: [
    { label: 'Standard DC', text: `1. This is a delivery challan and not a tax invoice.\n2. Goods are sent on approval / job work basis.\n3. Return of goods within 7 days if not accepted.\n4. All disputes subject to local jurisdiction.\n5. E. & O.E.` },
  ],
}

function TermsTab({ data }) {
  const qc = useQueryClient()
  const [activeType, setActiveType] = useState('terms_b2b_invoice')
  const [values, setValues] = useState({
    terms_b2b_invoice: '',
    terms_b2c_invoice: '',
    terms_quotation: '',
    terms_delivery_challan: '',
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!data) return
    setValues({
      terms_b2b_invoice:      data.terms_b2b_invoice      || '',
      terms_b2c_invoice:      data.terms_b2c_invoice      || '',
      terms_quotation:        data.terms_quotation        || '',
      terms_delivery_challan: data.terms_delivery_challan || '',
    })
  }, [data])

  const mutation = useMutation({
    mutationFn: () => settingsAPI.updateCompany(values),
    onSuccess: () => {
      qc.invalidateQueries(['company-settings'])
      setSaved(true)
      toast.success('Terms & Conditions saved')
      setTimeout(() => setSaved(false), 3000)
    },
    onError: () => toast.error('Save failed'),
  })

  const currentText = values[activeType] || ''
  const templates = TERMS_TEMPLATES[activeType] || []

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Define default Terms &amp; Conditions per document type. These are auto-filled when creating a new document and can be edited per-invoice.
      </p>

      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {TERMS_DOC_TYPES.map(dt => (
          <button key={dt.key} onClick={() => setActiveType(dt.key)}
            className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
              activeType === dt.key
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            {dt.label}
            {values[dt.key] && <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-blue-400 inline-block align-middle" />}
          </button>
        ))}
      </div>

      {/* Templates */}
      <div className="flex gap-2 flex-wrap">
        {templates.map(t => (
          <button key={t.label} onClick={() => setValues(v => ({ ...v, [activeType]: t.text }))}
            className="px-3 h-7 rounded-full border border-gray-300 text-xs text-gray-600
              hover:border-blue-400 hover:text-blue-600 transition-colors">
            {t.label}
          </button>
        ))}
        <button onClick={() => setValues(v => ({ ...v, [activeType]: '' }))}
          className="px-3 h-7 rounded-full border border-red-200 text-xs text-red-500
            hover:bg-red-50 transition-colors">
          Clear
        </button>
      </div>

      <textarea value={currentText}
        onChange={e => setValues(v => ({ ...v, [activeType]: e.target.value }))}
        rows={10} placeholder={`Enter Terms & Conditions for ${TERMS_DOC_TYPES.find(d => d.key === activeType)?.label}...`}
        className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm
          focus:outline-none focus:border-blue-500 font-mono resize-none" />

      <div className="flex justify-between items-center">
        <span className="text-xs text-gray-400">{currentText.length} characters</span>
        <Button variant="primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {saved
            ? <><CheckCircle size={14} className="text-green-300" /> Saved</>
            : <><Save size={14} /> {mutation.isPending ? 'Saving...' : 'Save All Terms'}</>
          }
        </Button>
      </div>
    </div>
  )
}



// ── Vehicles Tab ──────────────────────────────────────────────
function VehiclesTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editVehicle, setEditVehicle] = useState(null)
  const [form, setForm] = useState({ vehicle_type: '', vehicle_number: '' })

  const { data: vehicles = [], isLoading } = useQuery({
    queryKey: ['vehicles'],
    queryFn: () => settingsAPI.getVehicles().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (d) => settingsAPI.createVehicle(d),
    onSuccess: () => { qc.invalidateQueries(['vehicles']); setShowForm(false); setForm({ vehicle_type: '', vehicle_number: '' }); toast.success('Vehicle added') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, d }) => settingsAPI.updateVehicle(id, d),
    onSuccess: () => { qc.invalidateQueries(['vehicles']); setEditVehicle(null); toast.success('Vehicle updated') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => settingsAPI.deleteVehicle(id),
    onSuccess: () => { qc.invalidateQueries(['vehicles']); toast.success('Vehicle deactivated') },
  })

  const VEHICLE_TYPES = ['Truck', 'Mini Truck', 'Van', 'Tempo', 'Bike', 'Auto', 'Car', 'Other']

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-xs text-gray-500">Manage vehicles used for Delivery Challans and stock transfers.</p>
        <button onClick={() => { setShowForm(true); setEditVehicle(null); setForm({ vehicle_type: '', vehicle_number: '' }) }}
          className="flex items-center gap-1.5 px-3 h-8 rounded-lg bg-blue-600 text-white text-xs hover:bg-blue-700">
          <Plus size={12} /> Add Vehicle
        </button>
      </div>

      {(showForm || editVehicle) && (
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl space-y-3">
          <h3 className="text-sm font-semibold text-blue-800">{editVehicle ? 'Edit Vehicle' : 'Add New Vehicle'}</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Vehicle Type *</label>
              <select value={form.vehicle_type}
                onChange={e => setForm(p => ({ ...p, vehicle_type: e.target.value }))}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                <option value="">Select type...</option>
                {VEHICLE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Vehicle Number *</label>
              <input value={form.vehicle_number}
                onChange={e => setForm(p => ({ ...p, vehicle_number: e.target.value.toUpperCase() }))}
                placeholder="e.g. TN01AB1234" maxLength={15}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500 font-mono" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowForm(false); setEditVehicle(null) }}
              className="px-3 h-8 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50">Cancel</button>
            <button
              onClick={() => {
                if (!form.vehicle_type || !form.vehicle_number.trim()) { toast.error('Fill all fields'); return }
                if (editVehicle) updateMutation.mutate({ id: editVehicle.id, d: form })
                else createMutation.mutate(form)
              }}
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-3 h-8 rounded-lg bg-blue-600 text-white text-xs hover:bg-blue-700 disabled:opacity-60">
              {editVehicle ? 'Update' : 'Add Vehicle'}
            </button>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" /></div> :
        vehicles.length === 0 ? <div className="text-center py-8 text-gray-400 text-sm">No vehicles added yet.</div> : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left text-xs font-medium text-gray-500 pb-2">Type</th>
                <th className="text-left text-xs font-medium text-gray-500 pb-2">Vehicle Number</th>
                <th className="text-left text-xs font-medium text-gray-500 pb-2">Status</th>
                <th className="w-20"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {vehicles.map(v => (
                <tr key={v.id} className={clsx(!v.is_active && 'opacity-50')}>
                  <td className="py-2.5 text-gray-700">{v.vehicle_type}</td>
                  <td className="py-2.5 font-mono font-medium">{v.vehicle_number}</td>
                  <td className="py-2.5">
                    <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium',
                      v.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500')}>
                      {v.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="py-2.5">
                    <div className="flex gap-1 justify-end">
                      <button onClick={() => { setEditVehicle(v); setForm({ vehicle_type: v.vehicle_type, vehicle_number: v.vehicle_number }); setShowForm(false) }}
                        className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600"><Pencil size={13} /></button>
                      <button onClick={() => deleteMutation.mutate(v.id)}
                        className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      }
    </div>
  )
}

// ── Page Permissions Tab ──────────────────────────────────────
function PermissionsTab() {
  const qc = useQueryClient()
  // localPerms: { [userId]: string[] | null }  null=full access
  const [localPerms, setLocalPerms] = useState({})
  const [saving, setSaving] = useState({})

  const { data: users, isLoading, error } = useQuery({
    queryKey: ['users-permissions'],
    queryFn: () => settingsAPI.getUsersPermissions().then(r => r.data),
    retry: false,
    onSuccess: (data) => {
      // Seed local state from server
      const seed = {}
      data?.forEach(u => { seed[u.id] = u.page_permissions ?? null })
      setLocalPerms(seed)
    }
  })

  // Get effective perms for a user (local override or server value)
  const getPerms = (user) => {
    if (user.id in localPerms) return localPerms[user.id]
    return user.page_permissions ?? null
  }

  const saveToServer = async (userId, newPerms) => {
    setSaving(p => ({ ...p, [userId]: true }))
    try {
      await settingsAPI.updateUserPermissions(userId, { page_permissions: newPerms })
      await qc.invalidateQueries(['users-permissions'])
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save')
      // Revert local state on error
      setLocalPerms(p => ({ ...p, [userId]: users?.find(u => u.id === userId)?.page_permissions ?? null }))
    } finally {
      setSaving(p => ({ ...p, [userId]: false }))
    }
  }

  const handleToggle = (userId, pageKey) => {
    const current = getPerms(users?.find(u => u.id === userId))
    const allAllowed = current === null
    let newPerms

    if (allAllowed) {
      // Full access → remove just this one page
      newPerms = ALL_PAGES.map(p => p.key).filter(k => k !== pageKey)
    } else {
      const arr = current || []
      newPerms = arr.includes(pageKey)
        ? arr.filter(k => k !== pageKey)
        : [...arr, pageKey]
    }

    // Optimistic update immediately
    setLocalPerms(p => ({ ...p, [userId]: newPerms }))
    saveToServer(userId, newPerms)
  }

  const handleGrantAll = (userId) => {
    setLocalPerms(p => ({ ...p, [userId]: null }))
    saveToServer(userId, null)
  }

  const handleSetRestrictions = (userId) => {
    const allKeys = ALL_PAGES.map(p => p.key)
    setLocalPerms(p => ({ ...p, [userId]: allKeys }))
    saveToServer(userId, allKeys)
  }

  if (isLoading) return (
    <div className="flex justify-center py-10">
      <div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  )

  if (error) {
    const status = error.response?.status
    return (
      <div className="flex flex-col items-center text-center py-10 gap-2">
        <Shield size={22} className="text-amber-500" />
        {status === 403 || status === 401 ? (
          <>
            <p className="text-sm font-medium text-gray-700">Super-admin access required</p>
            <p className="text-xs text-gray-500 max-w-sm">
              Only a super-admin can view and manage page permissions.
              Log in with a super-admin account to use this tab.
            </p>
          </>
        ) : (
          <p className="text-sm text-red-500">
            {error.response?.data?.detail || 'Failed to load users. Please try again.'}
          </p>
        )}
      </div>
    )
  }

  const nonAdmins = users?.filter(u => u.role !== 'admin') || []

  if (!nonAdmins.length) return (
    <div className="text-center py-10 text-gray-400 text-sm">
      No non-admin users found. Add users first.
    </div>
  )

  return (
    <div className="space-y-6">
      <p className="text-xs text-gray-500">
        Control which pages each user can access. Admin users always have full access.
        Toggles update instantly — changes are saved to the server in the background.
      </p>
      {nonAdmins.map(user => {
        const effectivePerms = getPerms(user)
        const allAllowed = effectivePerms === null
        const perms = allAllowed ? ALL_PAGES.map(p => p.key) : (effectivePerms || [])
        const isSaving = saving[user.id]

        return (
          <div key={user.id} className="border border-gray-200 rounded-xl overflow-hidden">
            {/* User header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
              <div>
                <div className="font-medium text-gray-900 text-sm flex items-center gap-2">
                  {user.full_name || user.username}
                  {isSaving && <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />}
                </div>
                <div className="text-xs text-gray-500">
                  <span className="font-mono">@{user.username}</span>
                  {' · '}
                  <span className="capitalize">{user.role}</span>
                  {' · '}
                  {allAllowed
                    ? <span className="text-green-600 font-medium">Full Access</span>
                    : <span className="text-blue-600 font-medium">{perms.length}/{ALL_PAGES.length} pages</span>
                  }
                </div>
              </div>
              <div className="flex gap-2">
                {!allAllowed && (
                  <button onClick={() => handleGrantAll(user.id)} disabled={isSaving}
                    className="px-3 h-7 rounded-lg border border-green-300 text-xs text-green-700 hover:bg-green-50 disabled:opacity-50">
                    Grant Full Access
                  </button>
                )}
                {allAllowed && (
                  <button onClick={() => handleSetRestrictions(user.id)} disabled={isSaving}
                    className="px-3 h-7 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50">
                    Set Restrictions
                  </button>
                )}
              </div>
            </div>

            {/* Page toggles */}
            <div className="grid grid-cols-2 gap-0">
              {ALL_PAGES.map((page, idx) => {
                const allowed = perms.includes(page.key)
                return (
                  <div key={page.key}
                    className={clsx(
                      'flex items-center justify-between px-4 py-2.5 border-b border-gray-100',
                      idx % 2 === 0 ? 'border-r border-gray-100' : '',
                      !allowed ? 'bg-red-50/30' : ''
                    )}>
                    <span className="text-sm text-gray-700">{page.label}</span>
                    <button type="button"
                      onClick={() => handleToggle(user.id, page.key)}
                      className={clsx(
                        'relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none',
                        allowed ? 'bg-green-500' : 'bg-gray-300'
                      )}>
                      <div className={clsx(
                        'absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200',
                        allowed ? 'translate-x-5' : 'translate-x-0.5'
                      )} />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── DPDP Tab ──────────────────────────────────────────────────
function DpdpTab() {
  const qc = useQueryClient()
  const { user } = useAuthStore()
  const superAdmin = user?.role === 'super_admin' || user?.role === 'system_administrator'
  const [statusFilter, setStatusFilter] = useState('')
  const [previewResult, setPreviewResult] = useState(null)
  const [enforceResult, setEnforceResult] = useState(null)
  const [erasureForm, setErasureForm] = useState({ subject_type: 'customer', subject_id: '', reason: '' })
  const [showErasureForm, setShowErasureForm] = useState(false)

  const { data: policies = [], isLoading: loadingPolicies } = useQuery({
    queryKey: ['dpdp-retention-policies'],
    queryFn: () => settingsAPI.getDpdpRetentionPolicies().then(r => r.data),
  })

  const { data: erasureRequests = [], isLoading: loadingErasure, refetch: refetchErasure } = useQuery({
    queryKey: ['dpdp-erasure-requests', statusFilter],
    queryFn: () => settingsAPI.getErasureRequests(statusFilter || undefined).then(r => r.data),
  })

  const previewM = useMutation({
    mutationFn: () => settingsAPI.getDpdpRetentionPreview().then(r => r.data),
    onSuccess: (data) => { setPreviewResult(data); setEnforceResult(null) },
    onError: (e) => toast.error(e.response?.data?.detail || 'Preview failed'),
  })

  const enforceM = useMutation({
    mutationFn: (dryRun) => settingsAPI.enforceDpdpRetention(dryRun).then(r => r.data),
    onSuccess: (data, dryRun) => {
      setEnforceResult({ data, dryRun })
      if (!dryRun) toast.success('Retention enforced')
      qc.invalidateQueries({ queryKey: ['dpdp-retention-policies'] })
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Enforce failed'),
  })

  const createErasureM = useMutation({
    mutationFn: () => settingsAPI.createErasureRequest({
      subject_type: erasureForm.subject_type,
      subject_id: Number(erasureForm.subject_id),
      reason: erasureForm.reason || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dpdp-erasure-requests'] })
      toast.success('Erasure request submitted')
      setErasureForm({ subject_type: 'customer', subject_id: '', reason: '' })
      setShowErasureForm(false)
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to submit request'),
  })

  const processErasureM = useMutation({
    mutationFn: (id) => settingsAPI.processErasureRequest(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dpdp-erasure-requests'] })
      toast.success('Erasure processed — PII anonymised')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to process erasure'),
  })

  const statusBadge = (s) => {
    const map = { pending: 'bg-yellow-50 text-yellow-700', completed: 'bg-green-50 text-green-700', rejected: 'bg-red-50 text-red-700' }
    return <span className={`text-xs font-medium px-2 py-0.5 rounded ${map[s] || 'bg-gray-100 text-gray-600'}`}>{s}</span>
  }

  const inp = 'w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500'

  return (
    <div className="space-y-8">

      {/* Retention Policies */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Data retention policies</h3>
        <p className="text-xs text-gray-500 mb-3">Configured retention windows for system logs and sessions. Only active policies are enforced.</p>
        {loadingPolicies
          ? <div className="flex justify-center py-6"><Spinner size={20} /></div>
          : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 mb-3">
              {policies.length === 0 && <div className="px-4 py-4 text-sm text-gray-400 text-center">No policies configured</div>}
              {policies.map(p => (
                <div key={p.id} className="flex items-center justify-between px-4 py-3 gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800">{p.entity}</span>
                      <span className="text-xs text-gray-500">{p.retention_days}d · {p.action}</span>
                      {p.is_active
                        ? <span className="text-xs text-green-700 bg-green-50 px-1.5 py-0.5 rounded">active</span>
                        : <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">inactive</span>
                      }
                    </div>
                    {p.legal_basis && <p className="text-xs text-gray-400 mt-0.5">{p.legal_basis}</p>}
                  </div>
                </div>
              ))}
            </div>
          )
        }
        <div className="flex gap-2 flex-wrap">
          {superAdmin && (
            <button
              onClick={() => previewM.mutate()}
              disabled={previewM.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-50">
              <Eye size={14} /> {previewM.isPending ? 'Loading…' : 'Preview purge'}
            </button>
          )}
          {superAdmin && (
            <button
              onClick={() => {
                if (window.confirm('Run retention enforce in DRY RUN mode (no data deleted)?')) enforceM.mutate(true)
              }}
              disabled={enforceM.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-blue-300 text-blue-700 hover:bg-blue-50 disabled:opacity-50">
              <Play size={14} /> Dry run
            </button>
          )}
          {superAdmin && (
            <button
              onClick={() => {
                if (window.confirm('⚠️ LIVE enforce: this will permanently delete log rows beyond retention limits. Continue?')) enforceM.mutate(false)
              }}
              disabled={enforceM.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50">
              <AlertTriangle size={14} /> Enforce (live)
            </button>
          )}
          {!superAdmin && <p className="text-xs text-gray-400 italic">Preview and enforce actions require super-admin access.</p>}
        </div>

        {previewResult && (
          <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200 text-xs">
            <p className="font-medium text-gray-700 mb-2">Retention preview</p>
            {previewResult.map((r, i) => (
              <div key={i} className="flex justify-between py-0.5">
                <span className="text-gray-600">{r.entity}</span>
                <span className={r.would_purge > 0 ? 'text-orange-600 font-medium' : 'text-gray-400'}>{r.would_purge ?? r.error ?? 0} rows</span>
              </div>
            ))}
          </div>
        )}

        {enforceResult && (
          <div className={`mt-3 p-3 rounded-lg border text-xs ${enforceResult.dryRun ? 'bg-blue-50 border-blue-200' : 'bg-green-50 border-green-200'}`}>
            <p className="font-medium text-gray-700 mb-2">{enforceResult.dryRun ? 'Dry run result' : 'Enforce result'}</p>
            {enforceResult.data.map((r, i) => (
              <div key={i} className="flex justify-between py-0.5">
                <span className="text-gray-600">{r.entity}</span>
                <span>{r.would_purge ?? r.purged ?? r.error ?? 0} rows</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Erasure Requests */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-700">Right to erasure requests</h3>
            <p className="text-xs text-gray-500 mt-0.5">Processed requests anonymise PII while retaining statutory financial records.</p>
          </div>
          <button
            onClick={() => setShowErasureForm(v => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700">
            <Plus size={14} /> New request
          </button>
        </div>

        {showErasureForm && (
          <div className="mb-4 p-4 border border-blue-200 bg-blue-50 rounded-lg space-y-3">
            <h4 className="text-xs font-semibold text-gray-700">Submit erasure request</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Subject type <span className="text-red-500">*</span></label>
                <select value={erasureForm.subject_type} onChange={e => setErasureForm(p => ({ ...p, subject_type: e.target.value }))} className={inp}>
                  <option value="customer">Customer</option>
                  <option value="vendor">Vendor</option>
                  <option value="user">User</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Subject ID <span className="text-red-500">*</span></label>
                <input type="number" min="1" value={erasureForm.subject_id} onChange={e => setErasureForm(p => ({ ...p, subject_id: e.target.value }))} placeholder="e.g. 42" className={inp} />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-600 mb-1">Reason</label>
                <input value={erasureForm.reason} onChange={e => setErasureForm(p => ({ ...p, reason: e.target.value }))} placeholder="Data subject request under DPDP Act 2023" className={inp} />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowErasureForm(false)} className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
              <Button
                onClick={() => createErasureM.mutate()}
                disabled={!erasureForm.subject_id || createErasureM.isPending}>
                {createErasureM.isPending ? 'Submitting…' : 'Submit request'}
              </Button>
            </div>
          </div>
        )}

        <div className="flex gap-2 mb-3">
          {['', 'pending', 'completed', 'rejected'].map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1 text-xs rounded-full border transition-colors ${statusFilter === s ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}>
              {s || 'All'}
            </button>
          ))}
        </div>

        {loadingErasure
          ? <div className="flex justify-center py-6"><Spinner size={20} /></div>
          : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
              {erasureRequests.length === 0 && <div className="px-4 py-6 text-sm text-gray-400 text-center">No erasure requests</div>}
              {erasureRequests.map(r => (
                <div key={r.id} className="px-4 py-3 space-y-1">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800">{r.subject_label || `${r.subject_type} #${r.subject_id}`}</span>
                      <span className="text-xs text-gray-400">({r.subject_type} #{r.subject_id})</span>
                      {statusBadge(r.status)}
                    </div>
                    {r.status === 'pending' && superAdmin && (
                      <button
                        onClick={() => {
                          if (window.confirm(`Process erasure for ${r.subject_label || r.subject_type + ' #' + r.subject_id}? PII will be anonymised.`))
                            processErasureM.mutate(r.id)
                        }}
                        disabled={processErasureM.isPending}
                        className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md text-red-600 border border-red-200 hover:bg-red-50 disabled:opacity-50 flex-shrink-0">
                        <AlertTriangle size={12} /> Process
                      </button>
                    )}
                  </div>
                  {r.reason && <p className="text-xs text-gray-500">{r.reason}</p>}
                  {r.result_note && <p className="text-xs text-green-700">{r.result_note}</p>}
                  <p className="text-xs text-gray-400">
                    Requested {r.requested_at ? new Date(r.requested_at).toLocaleDateString('en-IN') : '—'}
                    {r.processed_at && ` · Processed ${new Date(r.processed_at).toLocaleDateString('en-IN')}`}
                  </p>
                </div>
              ))}
            </div>
          )
        }
      </div>
    </div>
  )
}


// ── TDS Sections Tab ──────────────────────────────────────────
function TdsSectionsTab() {
  const qc = useQueryClient()
  const EMPTY = { section_code: '', description: '', rate: '', threshold_single: '', threshold_annual: '', deductee_type: '' }
  const [form, setForm] = useState(EMPTY)

  const { data: sections = [], isLoading } = useQuery({
    queryKey: ['tds-sections'],
    queryFn: () => settingsAPI.getTdsSections().then(r => r.data),
  })

  const addM = useMutation({
    mutationFn: () => settingsAPI.createTdsSection({
      section_code: form.section_code.trim(),
      description: form.description.trim() || undefined,
      rate: Number(form.rate),
      threshold_single: form.threshold_single !== '' ? Number(form.threshold_single) : undefined,
      threshold_annual: form.threshold_annual !== '' ? Number(form.threshold_annual) : undefined,
      deductee_type: form.deductee_type.trim() || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tds-sections'] })
      toast.success(`Section ${form.section_code.toUpperCase()} added`)
      setForm(EMPTY)
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to add section'),
  })

  const delM = useMutation({
    mutationFn: (id) => settingsAPI.deleteTdsSection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tds-sections'] })
      toast.success('TDS section removed')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to remove section'),
  })

  const canAdd = form.section_code.trim() && form.rate !== '' && !isNaN(Number(form.rate))
  const fi = (field) => (e) => setForm(p => ({ ...p, [field]: e.target.value }))
  const inp = 'w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500'

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Active TDS sections</h3>
        <p className="text-xs text-gray-500 mb-4">Sections available for TDS deduction on expenses and payments. Removed sections are soft-deleted and preserved for historical records.</p>
        {isLoading
          ? <div className="flex justify-center py-8"><Spinner size={20} /></div>
          : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
              {sections.length === 0 && (
                <div className="px-4 py-6 text-sm text-gray-400 text-center">No sections configured</div>
              )}
              {sections.map(s => (
                <div key={s.id ?? s.section_code} className="flex items-center justify-between px-4 py-3 gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800">{s.section_code}</span>
                      <span className="text-xs font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">{s.rate}%</span>
                    </div>
                    {s.description && <p className="text-xs text-gray-500 mt-0.5 truncate">{s.description}</p>}
                    <div className="flex gap-3 mt-0.5">
                      {s.threshold_single != null && <span className="text-xs text-gray-400">Single ≥ ₹{s.threshold_single.toLocaleString('en-IN')}</span>}
                      {s.threshold_annual != null && <span className="text-xs text-gray-400">Annual ≥ ₹{s.threshold_annual.toLocaleString('en-IN')}</span>}
                    </div>
                  </div>
                  {s.id
                    ? (
                      <button
                        onClick={() => delM.mutate(s.id)}
                        disabled={delM.isPending}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-colors disabled:opacity-50 flex-shrink-0">
                        <Trash2 size={13} />
                        Remove
                      </button>
                    )
                    : <span className="text-xs text-gray-400 flex-shrink-0">seeded</span>
                  }
                </div>
              ))}
            </div>
          )
        }
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Add new section</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Section code <span className="text-red-500">*</span></label>
            <input value={form.section_code} onChange={fi('section_code')} placeholder="e.g. 194Q" className={inp} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Rate % <span className="text-red-500">*</span></label>
            <input type="number" min="0" max="100" step="0.01" value={form.rate} onChange={fi('rate')} placeholder="e.g. 0.1" className={inp} />
          </div>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <input value={form.description} onChange={fi('description')} placeholder="e.g. Purchase of goods" className={inp} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Threshold per transaction (₹)</label>
            <input type="number" min="0" value={form.threshold_single} onChange={fi('threshold_single')} placeholder="e.g. 30000" className={inp} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Threshold annual (₹)</label>
            <input type="number" min="0" value={form.threshold_annual} onChange={fi('threshold_annual')} placeholder="e.g. 5000000" className={inp} />
          </div>
        </div>
        <div className="flex justify-end mt-3">
          <Button onClick={() => addM.mutate()} disabled={!canAdd || addM.isPending} className="flex items-center gap-1.5">
            <Plus size={15} />
            {addM.isPending ? 'Adding…' : 'Add section'}
          </Button>
        </div>
      </div>
    </div>
  )
}


// ── GST Rates Tab ─────────────────────────────────────────────
function GstRatesTab() {
  const qc = useQueryClient()
  const [rate, setRate] = useState('')
  const [label, setLabel] = useState('')

  const { data: rates = [], isLoading } = useQuery({
    queryKey: ['gst-rates'],
    queryFn: () => settingsAPI.getGstRates().then(r => r.data),
  })

  const addM = useMutation({
    mutationFn: () => settingsAPI.createGstRate({ rate: Number(rate), label: label.trim() || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gst-rates'] })
      toast.success(`${rate}% GST rate added`)
      setRate(''); setLabel('')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to add rate'),
  })

  const delM = useMutation({
    mutationFn: (id) => settingsAPI.deleteGstRate(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['gst-rates'] })
      toast.success('GST rate removed')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to remove rate'),
  })

  const canAdd = rate !== '' && !isNaN(Number(rate)) && Number(rate) >= 0

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Active GST rate slabs</h3>
        <p className="text-xs text-gray-500 mb-4">These appear in product and purchase form dropdowns. Removed rates are soft-deleted and preserved for historical documents.</p>
        {isLoading
          ? <div className="flex justify-center py-8"><Spinner size={20} /></div>
          : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
              {rates.length === 0 && (
                <div className="px-4 py-6 text-sm text-gray-400 text-center">No rates configured</div>
              )}
              {rates.map(r => (
                <div key={r.id ?? r.rate} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <span className="text-sm font-medium text-gray-800">{r.rate}%</span>
                    {r.label && r.label !== `${r.rate}%` && (
                      <span className="ml-2 text-xs text-gray-500">{r.label}</span>
                    )}
                  </div>
                  {r.id
                    ? (
                      <button
                        onClick={() => delM.mutate(r.id)}
                        disabled={delM.isPending}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-colors disabled:opacity-50">
                        <Trash2 size={13} />
                        Remove
                      </button>
                    )
                    : <span className="text-xs text-gray-400">system default</span>
                  }
                </div>
              ))}
            </div>
          )
        }
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Add new rate</h3>
        <div className="flex gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Rate %<span className="text-red-500 ml-0.5">*</span></label>
            <input
              type="number" min="0" max="100" step="0.01"
              value={rate} onChange={e => setRate(e.target.value)}
              placeholder="e.g. 3"
              className="w-28 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">Label (optional)</label>
            <input
              type="text" value={label} onChange={e => setLabel(e.target.value)}
              placeholder="e.g. 3% — Precious metals"
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <Button onClick={() => addM.mutate()} disabled={!canAdd || addM.isPending} className="flex items-center gap-1.5">
            <Plus size={15} />
            {addM.isPending ? 'Adding…' : 'Add rate'}
          </Button>
        </div>
      </div>
    </div>
  )
}


// ── Main Page ─────────────────────────────────────────────────
export default function SettingsPage() {
  const { isSuperAdmin } = useAuthStore()
  const visibleTabs = TABS.filter(t => !t.superAdminOnly || isSuperAdmin())
  const [tab, setTab] = useState('company')

  const { data: company, isLoading: loadingCompany } = useQuery({
    queryKey: ['company-settings'],
    queryFn: () => settingsAPI.getCompany().then(r => r.data),
  })

  const { data: sequences, isLoading: loadingSeq } = useQuery({
    queryKey: ['invoice-sequences'],
    queryFn: () => settingsAPI.getSequences().then(r => r.data),
  })

  const { data: states } = useQuery({
    queryKey: ['states'],
    queryFn: () => settingsAPI.getStates().then(r => r.data),
  })

  return (
    <div className="max-w-4xl">
      <div className="page-header">
        <div>
          <div className="breadcrumb">Masters</div>
          <h1 className="page-title">Settings</h1>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Sidebar */}
        <div className="w-48 flex-shrink-0">
          <div className="card p-2 space-y-0.5">
            {visibleTabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={clsx(
                  'w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-colors text-left',
                  tab === t.id
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-50'
                )}>
                <t.icon size={15} />
                {t.label}
                {tab === t.id && <ChevronRight size={12} className="ml-auto" />}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 card p-6">
          {tab === 'company' && (
            loadingCompany
              ? <div className="flex justify-center py-10"><Spinner size={20} /></div>
              : <CompanyTab data={company} states={states} />
          )}
          {tab === 'sequences' && (
            loadingSeq
              ? <div className="flex justify-center py-10"><Spinner size={20} /></div>
              : <SequencesTab sequences={sequences} />
          )}
          {tab === 'vehicles' && <VehiclesTab />}
          {tab === 'permissions' && (
            loadingCompany
              ? <div className="flex justify-center py-10"><div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" /></div>
              : <PermissionsTab />
          )}
          {tab === 'terms' && (
            loadingCompany
              ? <div className="flex justify-center py-10"><Spinner size={20} /></div>
              : <TermsTab data={company} />
          )}
          {tab === 'gst-rates' && <GstRatesTab />}
          {tab === 'tds' && <TdsSectionsTab />}
          {tab === 'dpdp' && <DpdpTab />}
        </div>
      </div>
    </div>
  )
}