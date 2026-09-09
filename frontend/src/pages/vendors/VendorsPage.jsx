import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { vendorAPI } from '@/api/purchase'
import { settingsAPI } from '@/api/settings'
import { Button, Badge, Spinner, Empty, Pagination } from '@/components/ui'
import { Plus, X, Search, Edit2, Eye } from 'lucide-react'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'

const emptyForm = {
  trade_name: '', legal_name: '', gstin: '', phone: '',
  email: '', contact_person: '', state: '', state_code: '', credit_days: 0,
  pan_number: '', bank_name: '', bank_account_number: '', bank_ifsc: '',
  is_active: true,
}

function VendorForm({ initial = emptyForm, onSubmit, onCancel, loading, title }) {
  const [form, setForm] = useState({ ...emptyForm, ...initial })
  const [errors, setErrors] = useState({})
  const [gstinLoading, setGstinLoading] = useState(false)
  const { isAdmin } = useAuthStore()
  const isEditMode = title !== 'New Vendor'
  // Only admins/super-admins may flip active status, and only when editing.
  const canEditActive = isAdmin() && isEditMode

  const { data: states = [] } = useQuery({
    queryKey: ['states'],
    queryFn: () => settingsAPI.getStates().then(r => r.data),
    staleTime: Infinity,
  })

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }

  const validate = () => {
    const errs = {}
    if (!form.trade_name) errs.trade_name = 'Required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    // Strip is_active from the base payload; only re-add it when the current
    // user is allowed to change it (the backend rejects it otherwise).
    const { is_active, ...rest } = form
    const payload = { ...rest, credit_days: Number(form.credit_days) || 0 }
    if (canEditActive) payload.is_active = Boolean(is_active)
    onSubmit(payload)
  }

  const lookupGSTIN = async () => {
    if (!form.gstin || form.gstin.length !== 15) {
      toast.error('Enter a valid 15-character GSTIN')
      return
    }
    setGstinLoading(true)
    try {
      const { data } = await vendorAPI.gstinLookup(form.gstin)
      if (data.error) { toast.error(data.error); return }
      const matchedState = states.find(s => s.name === data.state)
      setForm(prev => ({
        ...prev,
        trade_name: data.trade_name || prev.trade_name,
        legal_name: data.legal_name || prev.legal_name,
        state: data.state || prev.state,
        state_code: matchedState ? matchedState.code : prev.state_code,
      }))
      toast.success('GSTIN details fetched')
    } catch {
      toast.error('GSTIN lookup failed')
    } finally {
      setGstinLoading(false)
    }
  }

  const inputClass = (field) => clsx(
    'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
    errors[field]
      ? 'border-red-400 focus:ring-red-500/20'
      : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
  )

  return (
    <div className="card mb-4 border-2 border-blue-200">
      <div className="card-header flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">{title}</h3>
        <button onClick={onCancel}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
          <X size={16} />
        </button>
      </div>
      <div className="card-body space-y-4">

        {/* GSTIN lookup */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            GSTIN <span className="text-gray-400">(auto-fills state)</span>
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={form.gstin}
              onChange={e => handleChange('gstin', e.target.value.toUpperCase())}
              placeholder="22AAAAA0000A1Z5"
              maxLength={15}
              className="flex-1 h-9 px-3 rounded-lg border border-gray-300 text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
            <Button variant="secondary" size="sm"
              loading={gstinLoading} onClick={lookupGSTIN}>
              <Search size={14} /> Fetch
            </Button>
          </div>
        </div>

        {/* Basic info */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Trade Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={form.trade_name}
              onChange={e => handleChange('trade_name', e.target.value)}
              placeholder="Vendor trading name"
              className={inputClass('trade_name')}
            />
            {errors.trade_name && (
              <p className="text-xs text-red-500 mt-1">{errors.trade_name}</p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Legal Name</label>
            <input
              type="text"
              value={form.legal_name}
              onChange={e => handleChange('legal_name', e.target.value)}
              placeholder="Registered legal name"
              className={inputClass('legal_name')}
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
            <input
              type="text"
              value={form.phone}
              onChange={e => handleChange('phone', e.target.value)}
              placeholder="+91 98765 43210"
              className={inputClass('phone')}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={e => handleChange('email', e.target.value)}
              placeholder="vendor@example.com"
              className={inputClass('email')}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Contact Person</label>
            <input
              type="text"
              value={form.contact_person}
              onChange={e => handleChange('contact_person', e.target.value)}
              placeholder="Primary contact"
              className={inputClass('contact_person')}
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">State</label>
            <select
              value={form.state}
              onChange={e => {
                const sel = states.find(s => s.name === e.target.value)
                handleChange('state', e.target.value)
                handleChange('state_code', sel?.code ?? '')
              }}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
              <option value="">Select state...</option>
              {states.map(s => (
                <option key={s.code} value={s.name}>{s.code} — {s.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Credit Days</label>
            <input
              type="number"
              min="0"
              value={form.credit_days}
              onChange={e => handleChange('credit_days', e.target.value)}
              placeholder="0"
              className={inputClass('credit_days')}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">PAN Number</label>
            <input
              type="text"
              value={form.pan_number}
              onChange={e => handleChange('pan_number', e.target.value.toUpperCase())}
              placeholder="AAAAA0000A"
              maxLength={10}
              className={inputClass('pan_number')}
            />
          </div>
        </div>

        {/* Bank details */}
        <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Bank Details
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Bank Name</label>
              <input
                type="text"
                value={form.bank_name}
                onChange={e => handleChange('bank_name', e.target.value)}
                placeholder="HDFC Bank"
                className={inputClass('bank_name')}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Account Number</label>
              <input
                type="text"
                value={form.bank_account_number}
                onChange={e => handleChange('bank_account_number', e.target.value)}
                placeholder="XXXX1234"
                className={inputClass('bank_account_number')}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">IFSC Code</label>
              <input
                type="text"
                value={form.bank_ifsc}
                onChange={e => handleChange('bank_ifsc', e.target.value.toUpperCase())}
                placeholder="HDFC0001234"
                className={inputClass('bank_ifsc')}
              />
            </div>
          </div>
        </div>

        {/* Active status — admin/super-admin only, edit mode only */}
        {canEditActive && (
          <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100">
            <div>
              <div className="text-sm font-medium text-gray-700">Vendor Status</div>
              <div className="text-xs text-gray-400">
                Inactive vendors are hidden from selection lists.
              </div>
            </div>
            <label className="flex items-center gap-3 cursor-pointer"
              onClick={() => handleChange('is_active', !form.is_active)}>
              <div className="relative">
                <div className={clsx('w-10 h-6 rounded-full transition-colors', form.is_active ? 'bg-blue-600' : 'bg-gray-300')} />
                <div className={clsx('absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform', form.is_active ? 'translate-x-5' : 'translate-x-1')} />
              </div>
              <span className="text-sm text-gray-700">{form.is_active ? 'Active' : 'Inactive'}</span>
            </label>
          </div>
        )}

        <div className="flex gap-2 justify-end pt-2">
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          <Button variant="primary" loading={loading} onClick={handleSubmit}>
            {title === 'New Vendor' ? 'Create Vendor' : 'Save Changes'}
          </Button>
        </div>
      </div>
    </div>
  )
}

function VendorDetailModal({ vendor, onClose, onEdit }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">{vendor.trade_name}</h3>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => onEdit(vendor)}>
              <Edit2 size={13} /> Edit
            </Button>
            <button onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Trade Name', value: vendor.trade_name },
              { label: 'Legal Name', value: vendor.legal_name },
              { label: 'GSTIN', value: vendor.gstin, mono: true },
              { label: 'PAN Number', value: vendor.pan_number, mono: true },
              { label: 'Phone', value: vendor.phone },
              { label: 'Email', value: vendor.email },
              { label: 'Contact Person', value: vendor.contact_person },
              { label: 'State', value: vendor.state },
              { label: 'Credit Days', value: vendor.credit_days ? `${vendor.credit_days} days` : null },
              { label: 'GST Status', value: vendor.gst_status },
            ].map(row => row.value ? (
              <div key={row.label}>
                <div className="text-xs text-gray-400 mb-0.5">{row.label}</div>
                <div className={clsx('text-sm font-medium text-gray-800', row.mono && 'font-mono')}>
                  {row.value}
                </div>
              </div>
            ) : null)}
          </div>

          {(vendor.bank_name || vendor.bank_account_number || vendor.bank_ifsc) && (
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Bank Details
              </div>
              <div className="grid grid-cols-3 gap-3">
                {vendor.bank_name && (
                  <div>
                    <div className="text-xs text-gray-400">Bank</div>
                    <div className="text-sm font-medium">{vendor.bank_name}</div>
                  </div>
                )}
                {vendor.bank_account_number && (
                  <div>
                    <div className="text-xs text-gray-400">Account</div>
                    <div className="text-sm font-mono">{vendor.bank_account_number}</div>
                  </div>
                )}
                {vendor.bank_ifsc && (
                  <div>
                    <div className="text-xs text-gray-400">IFSC</div>
                    <div className="text-sm font-mono">{vendor.bank_ifsc}</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function VendorsPage() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [statusActive, setStatusActive] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [editVendor, setEditVendor] = useState(null)
  const [viewVendor, setViewVendor] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['vendors', page, search, statusActive],
    queryFn: () => vendorAPI.list({
      page, page_size: 15,
      search: search || undefined,
      is_active: statusActive,
    }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const createMutation = useMutation({
    mutationFn: (d) => vendorAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['vendors'])
      toast.success('Vendor created successfully')
      setShowNew(false)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to create vendor'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => vendorAPI.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries(['vendors'])
      toast.success('Vendor updated successfully')
      setEditVendor(null)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to update vendor'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Purchase › Vendors</div>
          <h1 className="page-title">Vendors</h1>
        </div>
        <Button variant="primary" onClick={() => { setShowNew(true); setEditVendor(null) }}>
          <Plus size={14} /> New Vendor
        </Button>
      </div>

      {/* New Vendor Form */}
      {showNew && (
        <VendorForm
          title="New Vendor"
          loading={createMutation.isPending}
          onSubmit={(data) => createMutation.mutate(data)}
          onCancel={() => setShowNew(false)}
        />
      )}

      {/* Edit Vendor Form */}
      {editVendor && (
        <VendorForm
          title="Edit Vendor"
          initial={editVendor}
          loading={updateMutation.isPending}
          onSubmit={(data) => updateMutation.mutate({ id: editVendor.id, data })}
          onCancel={() => setEditVendor(null)}
        />
      )}

      {/* Vendor Detail Modal */}
      {viewVendor && (
        <VendorDetailModal
          vendor={viewVendor}
          onClose={() => setViewVendor(null)}
          onEdit={(v) => { setViewVendor(null); setEditVendor(v) }}
        />
      )}

      {/* Search */}
      <div className="card mb-4">
        <div className="p-4 flex items-center gap-3">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              placeholder="Search by name, GSTIN or phone..."
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              className="w-full h-9 pl-9 pr-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
          <select
            value={String(statusActive)}
            onChange={e => { setStatusActive(e.target.value === 'true'); setPage(1) }}
            className="w-32 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </div>

      {/* Vendor List */}
      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : data?.items?.length === 0 ? (
          <Empty message="No vendors found"
            action={
              <Button variant="primary" onClick={() => setShowNew(true)}>
                <Plus size={14} /> New Vendor
              </Button>
            }
          />
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>GSTIN</th>
                  <th>State</th>
                  <th>Phone</th>
                  <th>Credit Days</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map(v => (
                  <tr key={v.id} className="cursor-pointer"
                    onClick={() => setViewVendor(v)}>
                    <td>
                      <div className="font-medium text-gray-800">{v.trade_name}</div>
                      {v.legal_name && v.legal_name !== v.trade_name && (
                        <div className="text-xs text-gray-400">{v.legal_name}</div>
                      )}
                      {v.contact_person && (
                        <div className="text-xs text-gray-400">{v.contact_person}</div>
                      )}
                    </td>
                    <td className="font-mono text-xs text-gray-500">
                      {v.gstin || '—'}
                    </td>
                    <td className="text-gray-500 text-sm">{v.state || '—'}</td>
                    <td className="text-gray-500 text-sm">{v.phone || '—'}</td>
                    <td className="text-center">
                      {v.credit_days > 0
                        ? <Badge color="blue">{v.credit_days} days</Badge>
                        : <span className="text-gray-400 text-xs">—</span>}
                    </td>
                    <td>
                      <Badge color={v.is_active ? 'green' : 'gray'}>
                        {v.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setViewVendor(v)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                          title="View details">
                          <Eye size={14} />
                        </button>
                        <button
                          onClick={() => { setEditVendor(v); setShowNew(false) }}
                          className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600"
                          title="Edit vendor">
                          <Edit2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && (
              <Pagination
                page={data.page}
                pages={data.pages}
                total={data.total}
                pageSize={15}
                onChange={setPage}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}