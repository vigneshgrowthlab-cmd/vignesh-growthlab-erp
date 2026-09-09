import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { customerAPI } from '@/api/billing'
import { settingsAPI } from '@/api/settings'
import { Button, Spinner } from '@/components/ui'
import { Save, ArrowLeft, Search, Lock } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { useAuthStore } from '@/store/authStore'

// Indian GSTIN format: 2-digit state code, 5 letters (PAN holder type),
// 4 digits, 1 letter (PAN check), 1 digit (entity), Z, 1 alphanumeric checksum.
const GSTIN_REGEX = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9]{1}[A-Z]{1}[0-9A-Z]{1}$/
// Indian phone: 10 digits, optionally with +91 / 0 / spaces / dashes.
const PHONE_REGEX = /^(\+?91[\s-]?|0)?[6-9]\d{9}$/
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const emptyForm = {
  trade_name: '', gstin: '', is_b2b: true,
  business_type: '', gst_status: 'Active',
  phone: '', email: '',
  credit_limit: '0', credit_days: '0',
  is_active: true,
}

const emptyAddr = {
  address_line1: '', address_line2: '', city: '',
  state: '', state_code: '', pincode: '', contact_person: '',
  label: 'Main', address_type: 'both',
  is_preferred_billing: true, is_preferred_shipping: true,
}

export default function CustomerFormPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const isEdit = Boolean(id)
  const qc = useQueryClient()
  // Match the backend's B-6 guard list: only admins can edit credit_limit,
  // credit_days, gst_status, is_active. Other roles save without those fields.
  const { isAdmin } = useAuthStore()
  const canEditAdminFields = isAdmin()

  const [form, setForm] = useState(emptyForm)
  const [addr, setAddr] = useState(emptyAddr)
  const [addressId, setAddressId] = useState(null)
  const [errors, setErrors] = useState({})
  const [gstinLoading, setGstinLoading] = useState(false)

  const { data: existing, isLoading } = useQuery({
    queryKey: ['customer', id],
    queryFn: () => customerAPI.get(id).then(r => r.data),
    enabled: isEdit,
  })

  const { data: states = [] } = useQuery({
    queryKey: ['states'],
    queryFn: () => settingsAPI.getStates().then(r => r.data),
  })

  useEffect(() => {
    if (!existing) return
    setForm({
      trade_name: existing.trade_name || '',
      gstin: existing.gstin || '',
      is_b2b: existing.is_b2b !== false,
      business_type: existing.business_type || '',
      gst_status: existing.gst_status || 'Active',
      phone: existing.phone || '',
      email: existing.email || '',
      credit_limit: existing.credit_limit ?? '0',
      credit_days: existing.credit_days ?? '0',
      is_active: existing.is_active !== false,
    })
    // Load the preferred-billing address (fallback to the first) for inline edit.
    const addrs = existing.addresses || []
    const primary = addrs.find(a => a.is_preferred_billing) || addrs[0]
    if (primary) {
      setAddressId(primary.id)
      setAddr({
        address_line1: primary.address_line1 || '',
        address_line2: primary.address_line2 || '',
        city: primary.city || '',
        state: primary.state || existing.state || '',
        state_code: primary.state_code ?? existing.state_code ?? '',
        pincode: primary.pincode || '',
        contact_person: primary.contact_person || existing.contact_person || '',
        label: primary.label || 'Main',
        address_type: primary.address_type || 'both',
        is_preferred_billing: primary.is_preferred_billing ?? true,
        is_preferred_shipping: primary.is_preferred_shipping ?? true,
      })
    } else {
      setAddressId(null)
      setAddr(a => ({ ...a, state: existing.state || '', contact_person: existing.contact_person || '' }))
    }
  }, [existing])

  const hc = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }
  const hca = (field, value) => {
    setAddr(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }

  const validate = () => {
    const errs = {}
    if (!form.trade_name.trim()) errs.trade_name = 'Required'
    if (form.gstin && !GSTIN_REGEX.test(form.gstin)) {
      errs.gstin = 'Invalid GSTIN format (e.g. 22AAAAA0000A1Z5)'
    }
    if (form.phone) {
      const cleaned = form.phone.replace(/[\s-]/g, '')
      if (!PHONE_REGEX.test(cleaned)) errs.phone = 'Invalid phone (10-digit Indian mobile)'
    }
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
      }))
      if (data.state) {
        const sel = states.find(s => s.name === data.state)
        setAddr(p => ({ ...p, state: data.state, state_code: sel?.code ?? data.state_code ?? '' }))
      }
      toast.success('GSTIN details fetched. State auto-filled.')
    } catch {
      toast.error('GSTIN lookup failed')
    } finally {
      setGstinLoading(false)
    }
  }

  const buildCustomerPayload = () => {
    const payload = {
      trade_name: form.trade_name,
      gstin: form.gstin || null,
      is_b2b: Boolean(form.is_b2b),
      business_type: form.business_type || null,
      // Customer state mirrors the (single) address for GST determination.
      state: addr.state || null,
      state_code: addr.state_code ? Number(addr.state_code) : null,
      phone: form.phone || null,
      email: form.email || null,
    }
    if (canEditAdminFields) {
      payload.gst_status = form.gst_status || 'Active'
      if (form.is_b2b) {
        payload.credit_limit = Number(form.credit_limit) || 0
        payload.credit_days = Number(form.credit_days) || 0
      }
      if (isEdit) payload.is_active = Boolean(form.is_active)
    }
    return payload
  }

  const buildAddressPayload = () => ({
    label: addr.label || 'Main',
    address_line1: addr.address_line1,
    address_line2: addr.address_line2 || null,
    city: addr.city,
    state: addr.state || '',
    state_code: addr.state_code ? Number(addr.state_code) : null,
    pincode: addr.pincode,
    contact_person: addr.contact_person || null,
    address_type: addr.address_type || 'both',
    is_preferred_billing: true,
    is_preferred_shipping: true,
  })

  const mutation = useMutation({
    mutationFn: async () => {
      const customerPayload = buildCustomerPayload()
      const addrPayload = buildAddressPayload()
      if (isEdit) {
        await customerAPI.update(id, customerPayload)
        if (addressId) await customerAPI.updateAddress(id, addressId, addrPayload)
        else await customerAPI.addAddress(id, addrPayload)
        return id
      }
      const res = await customerAPI.create(customerPayload)
      const newId = res.data.id
      try { await customerAPI.addAddress(newId, addrPayload) } catch {}
      return newId
    },
    onSuccess: () => {
      qc.invalidateQueries(['customers'])
      qc.invalidateQueries(['customer', id])
      toast.success(isEdit ? 'Customer updated' : 'Customer created')
      navigate('/billing/customers')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to save'),
  })

  const handleSubmit = () => { if (validate()) mutation.mutate() }

  const ic = (f) => clsx(
    'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
    errors[f] ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
  )

  if (isEdit && isLoading) return <div className="flex justify-center py-16"><Spinner size={24} /></div>

  return (
    <div className="max-w-2xl">
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/billing/customers')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Customers
          </button>
          <h1 className="page-title">{isEdit ? 'Edit Customer' : 'New Customer'}</h1>
        </div>
        <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
          <Save size={14} /> {isEdit ? 'Update' : 'Create Customer'}
        </Button>
      </div>

      <div className="space-y-4">
        {/* Customer Type */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Customer Type</div></div>
          <div className="card-body">
            <div className="flex gap-3">
              {[
                { val: true, label: 'B2B — Business', desc: 'Registered business (credit terms)' },
                { val: false, label: 'B2C — Consumer', desc: 'Individual or unregistered' },
              ].map(opt => (
                <label key={String(opt.val)}
                  className={clsx('flex-1 p-3 rounded-lg border-2 cursor-pointer transition-colors',
                    form.is_b2b === opt.val ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300')}>
                  <input type="radio" className="sr-only"
                    checked={form.is_b2b === opt.val}
                    onChange={() => hc('is_b2b', opt.val)} />
                  <div className="font-medium text-sm text-gray-800">{opt.label}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{opt.desc}</div>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Business Details */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Business Details</div></div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-red-500">*</span></label>
                <input type="text" value={form.trade_name} onChange={e => hc('trade_name', e.target.value)}
                  placeholder="e.g. ABC Traders" className={ic('trade_name')} />
                {errors.trade_name && <p className="text-xs text-red-500 mt-1">{errors.trade_name}</p>}
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-600 mb-1">GSTIN</label>
                <div className="flex gap-2">
                  <input type="text" value={form.gstin}
                    onChange={e => hc('gstin', e.target.value.toUpperCase())}
                    placeholder="22AAAAA0000A1Z5" maxLength={15}
                    className={clsx(ic('gstin'), 'font-mono uppercase')} />
                  {form.is_b2b && (
                    <Button variant="secondary" size="sm" loading={gstinLoading} onClick={lookupGstin}>
                      <Search size={14} /> Fetch
                    </Button>
                  )}
                </div>
                {errors.gstin && <p className="text-xs text-red-500 mt-1">{errors.gstin}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
                <input type="text" value={form.phone} onChange={e => hc('phone', e.target.value)}
                  placeholder="9876543210" maxLength={15} className={ic('phone')} />
                {errors.phone && <p className="text-xs text-red-500 mt-1">{errors.phone}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                <input type="email" value={form.email} onChange={e => hc('email', e.target.value)}
                  placeholder="customer@example.com" className={ic('email')} />
                {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email}</p>}
              </div>
            </div>

            {/* Credit terms — B2B only, admin only */}
            {form.is_b2b && (
              canEditAdminFields ? (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Credit Limit (₹)</label>
                    <input type="number" step="0.01" min="0" value={form.credit_limit}
                      onChange={e => hc('credit_limit', e.target.value)} placeholder="0" className={ic('credit_limit')} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Credit Days</label>
                    <input type="number" min="0" value={form.credit_days}
                      onChange={e => hc('credit_days', e.target.value)} placeholder="0" className={ic('credit_days')} />
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs text-gray-400 italic">
                  <Lock size={11} /> Credit limit &amp; days are admin-only fields.
                </div>
              )
            )}
          </div>
        </div>

        {/* Address */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Address</div></div>
          <div className="card-body">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-600 mb-1">Street / Area <span className="text-red-500">*</span></label>
                <input type="text" value={addr.address_line1} onChange={e => hca('address_line1', e.target.value)}
                  placeholder="Door no., Street name" className={ic('address_line1')} />
                {errors.address_line1 && <p className="text-xs text-red-500 mt-1">{errors.address_line1}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Landmark / Area</label>
                <input type="text" value={addr.address_line2} onChange={e => hca('address_line2', e.target.value)}
                  placeholder="Near..." className={ic('address_line2')} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">City <span className="text-red-500">*</span></label>
                <input type="text" value={addr.city} onChange={e => hca('city', e.target.value)}
                  placeholder="Chennai" className={ic('city')} />
                {errors.city && <p className="text-xs text-red-500 mt-1">{errors.city}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">State</label>
                <select value={addr.state}
                  onChange={e => {
                    const sel = states.find(s => s.name === e.target.value)
                    setAddr(p => ({ ...p, state: e.target.value, state_code: sel?.code || '' }))
                  }}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select state...</option>
                  {states.map(s => (
                    <option key={s.code} value={s.name}>{s.code} — {s.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Pincode <span className="text-red-500">*</span></label>
                <input type="text" value={addr.pincode} onChange={e => hca('pincode', e.target.value)}
                  placeholder="600001" maxLength={6} className={clsx(ic('pincode'), 'font-mono')} />
                {errors.pincode && <p className="text-xs text-red-500 mt-1">{errors.pincode}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Contact Person</label>
                <input type="text" value={addr.contact_person} onChange={e => hca('contact_person', e.target.value)}
                  placeholder="Primary contact" className={ic('contact_person')} />
              </div>
            </div>
          </div>
        </div>

        {/* Active status — admin only, edit mode only */}
        {canEditAdminFields && isEdit && (
          <div className="card">
            <div className="card-header"><div className="text-sm font-semibold text-gray-700">Status</div></div>
            <div className="card-body flex items-center justify-between">
              <div className="text-xs text-gray-400">
                Inactive customers are hidden from the customer picker on new invoices.
              </div>
              <label className="flex items-center gap-3 cursor-pointer"
                onClick={() => hc('is_active', !form.is_active)}>
                <div className="relative">
                  <div className={clsx('w-10 h-6 rounded-full transition-colors', form.is_active ? 'bg-blue-600' : 'bg-gray-300')} />
                  <div className={clsx('absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform', form.is_active ? 'translate-x-5' : 'translate-x-1')} />
                </div>
                <span className="text-sm text-gray-700">{form.is_active ? 'Active' : 'Inactive'}</span>
              </label>
            </div>
          </div>
        )}

        <div className="flex justify-between pb-6">
          <Button variant="secondary" onClick={() => navigate('/billing/customers')}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
            <Save size={14} /> {isEdit ? 'Update Customer' : 'Create Customer'}
          </Button>
        </div>
      </div>
    </div>
  )
}
