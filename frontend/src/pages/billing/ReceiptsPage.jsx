import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { receiptAPI, customerAPI, invoiceAPI } from '@/api/billing'
import { Button, Badge, Pagination, Empty, Spinner } from '@/components/ui'
import { Plus, X } from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'

const PAYMENT_MODES = [
  { value: 'cash', label: 'Cash' },
  { value: 'bank', label: 'Bank Transfer' },
  { value: 'upi', label: 'UPI' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'neft', label: 'NEFT' },
  { value: 'rtgs', label: 'RTGS' },
]

const MODE_COLORS = {
  cash: 'green', bank: 'blue', upi: 'teal',
  cheque: 'amber', neft: 'blue', rtgs: 'blue',
}

function NewReceiptModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    customer_id: '', invoice_id: '',
    payment_date: format(new Date(), 'yyyy-MM-dd'),
    amount: '', payment_mode: 'bank',
    reference_number: '', tds_amount: '0',
    is_advance: false, notes: '',
  })
  const [errors, setErrors] = useState({})

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }

  const { data: customers } = useQuery({
    queryKey: ['customers-all'],
    queryFn: () => customerAPI.list({ page_size: 500, is_active: true }).then(r => r.data.items),
  })

  const { data: invoices } = useQuery({
    queryKey: ['customer-invoices-outstanding', form.customer_id],
    queryFn: () => invoiceAPI.list({ customer_id: form.customer_id, page_size: 100 })
      .then(r => r.data.items?.filter(i => !i.is_cancelled && Number(i.outstanding_amount) > 0)),
    enabled: Boolean(form.customer_id),
  })

  const validate = () => {
    const errs = {}
    if (!form.customer_id) errs.customer_id = 'Select a customer'
    if (!form.amount || Number(form.amount) <= 0) errs.amount = 'Enter valid amount'
    if (!form.payment_date) errs.payment_date = 'Required'
    if (form.payment_mode !== 'cash' && !form.reference_number.trim())
      errs.reference_number = 'Reference no. required for non-cash payments'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const mutation = useMutation({
    mutationFn: (d) => receiptAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['receipts'])
      qc.invalidateQueries(['invoices'])
      toast.success('Receipt recorded successfully')
      onClose()
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const handleSubmit = () => {
    if (!validate()) return
    mutation.mutate({
      customer_id: Number(form.customer_id),
      invoice_id: form.invoice_id ? Number(form.invoice_id) : null,
      payment_date: form.payment_date,
      amount: Number(form.amount),
      payment_mode: form.payment_mode,
      reference_number: form.reference_number || null,
      tds_amount: Number(form.tds_amount) || 0,
      is_advance: Boolean(form.is_advance),
      notes: form.notes || null,
    })
  }

  const ic = (f) => clsx('w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
    errors[f] ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500')

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">New Receipt</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Customer <span className="text-red-500">*</span></label>
            <select value={form.customer_id}
              onChange={e => { handleChange('customer_id', e.target.value); handleChange('invoice_id', '') }}
              className={ic('customer_id')}>
              <option value="">Select customer...</option>
              {customers?.map(c => <option key={c.id} value={c.id}>{c.trade_name}</option>)}
            </select>
            {errors.customer_id && <p className="text-xs text-red-500 mt-1">{errors.customer_id}</p>}
          </div>
          {form.customer_id && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Apply Against Invoice <span className="text-gray-400">(optional)</span></label>
              <select value={form.invoice_id}
                onChange={e => {
                  handleChange('invoice_id', e.target.value)
                  if (e.target.value) {
                    const inv = invoices?.find(i => i.id === Number(e.target.value))
                    if (inv) handleChange('amount', Number(inv.outstanding_amount).toFixed(2))
                  }
                }}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                <option value="">Advance / Not linked</option>
                {invoices?.map(inv => (
                  <option key={inv.id} value={inv.id}>
                    {inv.invoice_number} — ₹{Number(inv.outstanding_amount).toFixed(2)} outstanding
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Payment Date <span className="text-red-500">*</span></label>
              <input type="date" value={form.payment_date} onChange={e => handleChange('payment_date', e.target.value)} className={ic('payment_date')} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) <span className="text-red-500">*</span></label>
              <input type="number" step="0.01" min="0.01" value={form.amount}
                onChange={e => handleChange('amount', e.target.value)} placeholder="0.00" className={ic('amount')} />
              {errors.amount && <p className="text-xs text-red-500 mt-1">{errors.amount}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Payment Mode <span className="text-red-500">*</span></label>
              <select value={form.payment_mode} onChange={e => handleChange('payment_mode', e.target.value)} className={ic('payment_mode')}>
                {PAYMENT_MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Reference No. {form.payment_mode !== 'cash' && <span className="text-red-500">*</span>}
              </label>
              <input type="text" value={form.reference_number} onChange={e => handleChange('reference_number', e.target.value)} placeholder="UTR/Cheque no." className={ic('reference_number')} />
              {errors.reference_number && <p className="text-xs text-red-500 mt-1">{errors.reference_number}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">TDS Amount (₹)</label>
              <input type="number" step="0.01" min="0" value={form.tds_amount} onChange={e => handleChange('tds_amount', e.target.value)} placeholder="0.00" className={ic('tds_amount')} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
              <input type="text" value={form.notes} onChange={e => handleChange('notes', e.target.value)} placeholder="Optional" className={ic('notes')} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={form.is_advance} onChange={e => handleChange('is_advance', e.target.checked)} className="rounded" />
            <span className="text-gray-700">Mark as advance payment</span>
          </label>
        </div>
        <div className="flex gap-3 justify-end px-5 pb-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>Record Receipt</Button>
        </div>
      </div>
    </div>
  )
}

export default function ReceiptsPage() {
  const [page, setPage] = useState(1)
  const [showNew, setShowNew] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ['receipts', page],
    queryFn: () => receiptAPI.list({ page, page_size: 20 }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <div className="page-header">
        <div><div className="breadcrumb">Billing › Receipts</div><h1 className="page-title">Customer Receipts</h1></div>
        <Button variant="primary" onClick={() => setShowNew(true)}><Plus size={14} /> New Receipt</Button>
      </div>
      <div className="card">
        {isLoading ? <div className="flex justify-center py-16"><Spinner size={24} /></div>
          : data?.items?.length === 0 ? <Empty message="No receipts found" action={<Button variant="primary" onClick={() => setShowNew(true)}><Plus size={14} />New Receipt</Button>} />
          : (<>
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr><th>Receipt No.</th><th>Customer</th><th>Date</th><th>Mode</th><th>Reference</th><th className="text-right">Amount (₹)</th><th>Type</th></tr></thead>
                <tbody>
                  {data?.items?.map(r => (
                    <tr key={r.id}>
                      <td className="font-mono text-xs font-semibold">{r.payment_number}</td>
                      <td className="font-medium">{r.customer_name}</td>
                      <td className="text-gray-500 text-xs">{r.payment_date ? format(new Date(r.payment_date), 'dd MMM yyyy') : '—'}</td>
                      <td><Badge color={MODE_COLORS[r.payment_mode] || 'gray'}>{r.payment_mode?.replace('_', ' ').toUpperCase()}</Badge></td>
                      <td className="text-xs font-mono text-gray-500">{r.reference_number || '—'}</td>
                      <td className="text-right font-semibold text-green-600">₹{Number(r.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      <td><Badge color={r.is_advance ? 'amber' : 'blue'}>{r.is_advance ? 'Advance' : 'Invoice'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={20} onChange={setPage} />}
          </>)}
      </div>
      {showNew && <NewReceiptModal onClose={() => setShowNew(false)} />}
    </div>
  )
}
