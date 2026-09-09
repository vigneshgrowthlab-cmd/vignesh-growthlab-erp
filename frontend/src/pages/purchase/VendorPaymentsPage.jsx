import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { vendorAPI, vendorPaymentAPI } from '@/api/purchase'
import { Button, Badge, Input, Spinner, Empty, Pagination, Select } from '@/components/ui'
import { Plus, Search } from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'
import { clsx } from 'clsx'

const FY_OPTIONS = ['2026-27', '2025-26', '2024-25']
const PAYMENT_MODES = ['cash','bank','cheque','upi','neft','rtgs']

export default function VendorPaymentsPage() {
  const { isAdmin, isAccountant } = useAuthStore()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [fy, setFy] = useState('2026-27')
  const location = useLocation()
  const preVendor = location.state?.vendor_id
  const preVendorName = location.state?.vendor_name

  const [form, setForm] = useState({
    vendor_id: preVendor ? String(preVendor) : '',
    payment_date: format(new Date(), 'yyyy-MM-dd'),
    amount: '',
    payment_mode: 'bank',
    reference_number: '',
    notes: '',
    is_advance: false,
  })

  // Auto-open form if navigated from vendor row
  const [showForm, setShowForm] = useState(Boolean(preVendor))

  const { data: payments, isLoading } = useQuery({
    queryKey: ['vendor-payments-all', page, fy],
    queryFn: () => vendorPaymentAPI.list({ page, page_size: 20, financial_year: fy }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const { data: vendors } = useQuery({
    queryKey: ['vendors-list'],
    queryFn: () => vendorAPI.list({ page_size: 500 }).then(r => r.data.items || r.data),
  })

  const mutation = useMutation({
    mutationFn: (d) => vendorPaymentAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['vendor-payments-all'])
      toast.success('Payment recorded')
      setShowForm(false)
      setForm({ vendor_id: '', payment_date: format(new Date(), 'yyyy-MM-dd'), amount: '', payment_mode: 'bank', reference_number: '', notes: '', is_advance: false })
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const handleSubmit = () => {
    if (!form.vendor_id) { toast.error('Select a vendor'); return }
    if (!form.amount || Number(form.amount) <= 0) { toast.error('Enter a valid amount'); return }
    mutation.mutate({
      vendor_id: Number(form.vendor_id),
      payment_date: form.payment_date,
      amount: Number(form.amount),
      payment_mode: form.payment_mode,
      reference_number: form.reference_number || null,
      notes: form.notes || null,
      is_advance: form.is_advance,
    })
  }

  const canManage = isAdmin() || isAccountant()

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Purchase</div>
          <h1 className="page-title">Vendor Payments</h1>
        </div>
        {canManage && (
          <Button variant="primary" onClick={() => setShowForm(true)}>
            <Plus size={14} /> Record Payment
          </Button>
        )}
      </div>

      <div className="card mb-4">
        <div className="p-4 flex gap-3">
          <Select value={fy} onChange={e => { setFy(e.target.value); setPage(1) }} className="w-32">
            {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
          </Select>
        </div>
      </div>

      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : payments?.items?.length === 0 ? (
          <Empty message="No payments found" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Payment No.</th>
                    <th>Vendor</th>
                    <th>Date</th>
                    <th>Mode</th>
                    <th>Reference</th>
                    <th>Type</th>
                    <th className="text-right">Amount (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {payments?.items?.map(p => (
                    <tr key={p.id}>
                      <td className="font-mono text-xs font-medium">{p.payment_number}</td>
                      <td className="font-medium">{p.vendor_name}</td>
                      <td className="text-gray-500">
                        {p.payment_date ? format(new Date(p.payment_date), 'dd MMM yyyy') : '—'}
                      </td>
                      <td>
                        <span className="px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700 capitalize">
                          {p.payment_mode}
                        </span>
                      </td>
                      <td className="text-gray-500 text-xs">{p.reference_number || '—'}</td>
                      <td>
                        <Badge color={p.is_advance ? 'amber' : 'green'}>
                          {p.is_advance ? 'Advance' : 'Against PO'}
                        </Badge>
                      </td>
                      <td className="text-right font-semibold text-green-600">
                        ₹{Number(p.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {payments && (
              <Pagination page={payments.page} pages={payments.pages}
                total={payments.total} pageSize={20} onChange={setPage} />
            )}
          </>
        )}
      </div>

      {payments && (
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="stat-card">
            <div className="stat-label">Total Payments ({fy})</div>
            <div className="stat-value">{payments.total}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Amount Paid</div>
            <div className="stat-value text-green-600">
              ₹{payments.items?.reduce((s, p) => s + Number(p.amount), 0)
                .toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>
        </div>
      )}

      {/* Record Payment Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-xl"
            onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-gray-100 flex justify-between">
              <h2 className="font-semibold text-gray-900">Record Vendor Payment</h2>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600 text-lg">×</button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Vendor *</label>
                <select value={form.vendor_id}
                  onChange={e => setForm(p => ({ ...p, vendor_id: e.target.value }))}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select vendor...</option>
                  {vendors?.map(v => <option key={v.id} value={v.id}>{v.trade_name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Date *</label>
                  <input type="date" value={form.payment_date}
                    onChange={e => setForm(p => ({ ...p, payment_date: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) *</label>
                  <input type="number" step="0.01" value={form.amount}
                    onChange={e => setForm(p => ({ ...p, amount: e.target.value }))}
                    placeholder="0.00"
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Mode *</label>
                  <select value={form.payment_mode}
                    onChange={e => setForm(p => ({ ...p, payment_mode: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                    {PAYMENT_MODES.map(m => <option key={m} value={m}>{m.toUpperCase()}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Reference</label>
                  <input value={form.reference_number}
                    onChange={e => setForm(p => ({ ...p, reference_number: e.target.value }))}
                    placeholder="UTR / Cheque no."
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <input value={form.notes}
                  onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                  placeholder="Optional"
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer"
                onClick={() => setForm(p => ({ ...p, is_advance: !p.is_advance }))}>
                <div className={clsx('w-4 h-4 rounded border-2 flex items-center justify-center',
                  form.is_advance ? 'bg-blue-600 border-blue-600' : 'border-gray-300')}>
                  {form.is_advance && <div className="w-2 h-2 bg-white rounded-sm" />}
                </div>
                <span className="text-sm text-gray-700">Mark as advance payment</span>
              </label>
              <div className="flex gap-3 justify-end pt-2">
                <button onClick={() => setShowForm(false)}
                  className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button onClick={handleSubmit} disabled={mutation.isPending}
                  className="px-4 h-9 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-60">
                  {mutation.isPending ? 'Saving...' : 'Record Payment'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
