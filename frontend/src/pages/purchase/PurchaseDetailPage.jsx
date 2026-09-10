import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { purchaseAPI, vendorPaymentAPI } from '@/api/purchase'
import { Button, Badge, AlertBox } from '@/components/ui'
import { ArrowLeft, XCircle, Plus, CreditCard, Printer } from 'lucide-react'
import { format } from 'date-fns'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'
import { clsx } from 'clsx'

const PAYMENT_MODES = ['cash','bank','cheque','upi','neft','rtgs']

export default function PurchaseDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { isAdmin, isAccountant } = useAuthStore()
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [showPayment, setShowPayment] = useState(false)
  const [payForm, setPayForm] = useState({
    payment_date: format(new Date(), 'yyyy-MM-dd'),
    amount: '',
    payment_mode: 'bank',
    reference_number: '',
    notes: '',
  })

  const { data: purchase, isLoading } = useQuery({
    queryKey: ['purchase', id],
    queryFn: () => purchaseAPI.get(id).then(r => r.data),
  })

  const { data: payments } = useQuery({
    queryKey: ['vendor-payments', id],
    queryFn: () => vendorPaymentAPI.list({ purchase_id: id, page_size: 50 }).then(r => r.data),
    enabled: Boolean(id),
  })

  const cancelMutation = useMutation({
    mutationFn: () => purchaseAPI.cancel(id),
    onSuccess: () => {
      qc.invalidateQueries(['purchases'])
      qc.invalidateQueries(['purchase', id])
      toast.success('Purchase cancelled')
      setConfirmCancel(false)
    },
    onError: (e) => {
      toast.error(e.response?.data?.detail || 'Failed to cancel')
      setConfirmCancel(false)
    },
  })

  const payMutation = useMutation({
    mutationFn: (d) => vendorPaymentAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['vendor-payments', id])
      qc.invalidateQueries(['purchase', id])
      toast.success('Payment recorded successfully')
      setShowPayment(false)
      setPayForm({ payment_date: format(new Date(), 'yyyy-MM-dd'), amount: '', payment_mode: 'bank', reference_number: '', notes: '' })
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to record payment'),
  })

  const handlePay = () => {
    if (!payForm.amount || Number(payForm.amount) <= 0) {
      toast.error('Enter a valid amount')
      return
    }
    payMutation.mutate({
      vendor_id: purchase.vendor_id,
      purchase_id: Number(id),
      payment_date: payForm.payment_date,
      amount: Number(payForm.amount),
      payment_mode: payForm.payment_mode,
      reference_number: payForm.reference_number || null,
      notes: payForm.notes || null,
      is_advance: false,
    })
  }

  const handlePrint = () => {
    window.print()
  }

  if (isLoading) return (
    <div className="flex justify-center py-16">
      <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  )
  if (!purchase) return null

  const totalPaid = payments?.items?.reduce((s, p) => s + Number(p.amount), 0) || 0
  const outstanding = Number(purchase.total_amount) - totalPaid
  const canPay = (isAdmin() || isAccountant()) && !purchase.is_cancelled

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/purchase')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Purchase
          </button>
          <h1 className="page-title">
            {purchase.purchase_number || `PO-${id}`}
            <span className="ml-2 text-sm font-normal text-gray-400">
              {purchase.vendor_invoice_number && `(Vendor: ${purchase.vendor_invoice_number})`}
            </span>
          </h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="secondary" size="sm" onClick={handlePrint}>
            <Printer size={14} /> Print
          </Button>
          {canPay && outstanding > 0 && (
            <Button variant="primary" size="sm" onClick={() => setShowPayment(true)}>
              <CreditCard size={14} /> Record Payment
            </Button>
          )}
          {isAdmin() && !purchase.is_cancelled && (
            <Button variant="danger" size="sm" onClick={() => setConfirmCancel(true)}>
              <XCircle size={14} /> Cancel
            </Button>
          )}
        </div>
      </div>

      {purchase.is_cancelled && (
        <AlertBox type="danger" className="mb-4">This purchase has been cancelled.</AlertBox>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3 mb-4">
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Total Amount</div>
          <div className="text-xl font-bold text-gray-900">
            ₹{Number(purchase.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Total Paid</div>
          <div className="text-xl font-bold text-green-600">
            ₹{totalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-gray-500 mb-1">Outstanding</div>
          <div className={clsx('text-xl font-bold', outstanding > 0 ? 'text-red-600' : 'text-green-600')}>
            ₹{outstanding.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* Purchase Details */}
      <div className="card mb-4">
        <div className="card-header flex items-center justify-between">
          <h3 className="font-semibold text-gray-800">Purchase Details</h3>
          <Badge color={purchase.is_cancelled ? 'red' : outstanding > 0 ? 'amber' : 'green'}>
            {purchase.is_cancelled ? 'Cancelled' : outstanding > 0 ? 'Partially Paid' : 'Paid'}
          </Badge>
        </div>
        <div className="card-body">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 text-sm">
            {[
              ['Vendor', purchase.vendor_name],
              ['Warehouse', purchase.warehouse_name || 'Main Warehouse'],
              ['Purchase No.', purchase.purchase_number],
              ['Vendor Invoice', purchase.vendor_invoice_number],
              ['Invoice Date', purchase.invoice_date ? format(new Date(purchase.invoice_date), 'dd MMM yyyy') : '—'],
              ['Received Date', purchase.received_date ? format(new Date(purchase.received_date), 'dd MMM yyyy') : '—'],
              ['Payment Due', purchase.payment_due_date ? format(new Date(purchase.payment_due_date), 'dd MMM yyyy') : '—'],
              ['GST Type', purchase.gst_type === 'cgst_sgst' ? 'CGST + SGST' : 'IGST'],
              ['Financial Year', purchase.financial_year],
            ].map(([label, value]) => (
              <div key={label}>
                <div className="text-xs text-gray-500 mb-0.5">{label}</div>
                <div className="font-medium text-gray-800">{value || '—'}</div>
              </div>
            ))}
          </div>
          {purchase.notes && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              <div className="text-xs text-gray-400 mb-1">Notes</div>
              {purchase.notes}
            </div>
          )}
        </div>
      </div>

      {/* Line Items */}
      <div className="card mb-4">
        <div className="card-header">
          <h3 className="font-semibold text-gray-800">Line Items</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Part Code</th>
                <th>Product</th>
                <th>HSN</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Unit Cost</th>
                <th className="text-right">GST %</th>
                <th className="text-right">GST Amt</th>
                <th className="text-right">Line Total</th>
              </tr>
            </thead>
            <tbody>
              {purchase.items?.map(item => (
                <tr key={item.id}>
                  <td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{item.part_code}</span></td>
                  <td className="font-medium">{item.part_name}</td>
                  <td className="font-mono text-xs text-gray-500">{item.hsn_code || '—'}</td>
                  <td className="text-right">{Number(item.quantity || 0).toFixed(3)}</td>
                  <td className="text-right">₹{Number(item.unit_cost || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  <td className="text-right">{item.gst_percent || 0}%</td>
                  <td className="text-right text-gray-500">
                    ₹{(Number(item.cgst_amount || 0) + Number(item.sgst_amount || 0) + Number(item.igst_amount || 0)).toFixed(2)}
                  </td>
                  <td className="text-right font-semibold">₹{Number(item.line_total || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="p-4 border-t border-gray-100 flex justify-end">
          <div className="w-64 space-y-2 text-sm">
            <div className="flex justify-between text-gray-500">
              <span>Subtotal</span>
              <span>₹{Number(purchase.subtotal || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>
            {Number(purchase.total_cgst) > 0 && (
              <div className="flex justify-between text-gray-500">
                <span>CGST</span>
                <span>₹{Number(purchase.total_cgst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            {Number(purchase.total_sgst) > 0 && (
              <div className="flex justify-between text-gray-500">
                <span>SGST</span>
                <span>₹{Number(purchase.total_sgst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            {Number(purchase.total_igst) > 0 && (
              <div className="flex justify-between text-gray-500">
                <span>IGST</span>
                <span>₹{Number(purchase.total_igst).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            <div className="flex justify-between font-bold text-base pt-2 border-t border-gray-200">
              <span>Total</span>
              <span className="text-blue-600">₹{Number(purchase.total_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Payment History */}
      <div className="card mb-4">
        <div className="card-header flex items-center justify-between">
          <h3 className="font-semibold text-gray-800">Payment History</h3>
          {canPay && outstanding > 0 && (
            <button onClick={() => setShowPayment(true)}
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700">
              <Plus size={12} /> Record Payment
            </button>
          )}
        </div>
        <div className="card-body">
          {!payments?.items?.length ? (
            <div className="text-center py-6 text-sm text-gray-400">No payments recorded yet</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table min-w-[500px]">
                <thead>
                  <tr>
                    <th>Payment No.</th>
                    <th>Date</th>
                    <th>Mode</th>
                    <th>Reference</th>
                    <th className="text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.items.map(p => (
                    <tr key={p.id}>
                      <td className="font-mono text-xs">{p.payment_number}</td>
                      <td>{p.payment_date ? format(new Date(p.payment_date), 'dd MMM yyyy') : '—'}</td>
                      <td>
                        <span className="px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700 capitalize">
                          {p.payment_mode}
                        </span>
                      </td>
                      <td className="text-gray-500 text-xs">{p.reference_number || '—'}</td>
                      <td className="text-right font-semibold text-green-600">
                        ₹{Number(p.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-gray-200">
                    <td colSpan={4} className="text-right text-sm font-medium text-gray-600 py-2">Total Paid</td>
                    <td className="text-right font-bold text-green-600 py-2">
                      ₹{totalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                  {outstanding > 0 && (
                    <tr>
                      <td colSpan={4} className="text-right text-sm font-medium text-gray-600 pb-2">Outstanding</td>
                      <td className="text-right font-bold text-red-600 pb-2">
                        ₹{outstanding.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  )}
                </tfoot>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Record Payment Modal */}
      {showPayment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setShowPayment(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-xl"
            onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center">
              <h2 className="font-semibold text-gray-900">Record Vendor Payment</h2>
              <button onClick={() => setShowPayment(false)} className="text-gray-400 hover:text-gray-600 text-lg">×</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="p-3 bg-blue-50 rounded-lg text-sm">
                <div className="flex justify-between text-gray-600">
                  <span>Invoice Total</span>
                  <span className="font-medium">₹{Number(purchase.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between text-gray-600 mt-1">
                  <span>Already Paid</span>
                  <span className="font-medium text-green-600">₹{totalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between font-semibold mt-1 pt-1 border-t border-blue-200">
                  <span>Outstanding</span>
                  <span className="text-red-600">₹{outstanding.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Payment Date *</label>
                  <input type="date" value={payForm.payment_date}
                    onChange={e => setPayForm(p => ({ ...p, payment_date: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) *</label>
                  <input type="number" step="0.01" min="0.01"
                    value={payForm.amount}
                    onChange={e => setPayForm(p => ({ ...p, amount: e.target.value }))}
                    placeholder={outstanding.toFixed(2)}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Payment Mode *</label>
                  <select value={payForm.payment_mode}
                    onChange={e => setPayForm(p => ({ ...p, payment_mode: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                    {PAYMENT_MODES.map(m => (
                      <option key={m} value={m}>{m.toUpperCase()}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Reference No.</label>
                  <input value={payForm.reference_number}
                    onChange={e => setPayForm(p => ({ ...p, reference_number: e.target.value }))}
                    placeholder="UTR / Cheque no."
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <input value={payForm.notes}
                  onChange={e => setPayForm(p => ({ ...p, notes: e.target.value }))}
                  placeholder="Optional"
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button onClick={() => setShowPayment(false)}
                  className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button onClick={handlePay} disabled={payMutation.isPending}
                  className="px-4 h-9 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-60">
                  {payMutation.isPending ? 'Saving...' : 'Record Payment'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Confirm */}
      {confirmCancel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setConfirmCancel(false)}>
          <div className="bg-white rounded-xl w-full max-w-md shadow-xl"
            onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Cancel Purchase</h2>
            </div>
            <div className="p-5">
              <p className="text-sm text-gray-600 mb-5">
                Are you sure you want to cancel this purchase? This cannot be undone.
              </p>
              <div className="flex gap-3 justify-end">
                <button onClick={() => setConfirmCancel(false)}
                  className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                  No, Keep
                </button>
                <button onClick={() => { if (!cancelMutation.isPending) cancelMutation.mutate() }}
                  disabled={cancelMutation.isPending}
                  className="px-4 h-9 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-60">
                  {cancelMutation.isPending ? 'Cancelling...' : 'Yes, Cancel'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
