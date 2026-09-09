import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { invoiceAPI, receiptAPI } from '@/api/billing'
import { Button, Badge, Pagination, Empty, Spinner, Input, Select } from '@/components/ui'
import { Plus, Search, Eye, FileText, MessageSquare, CreditCard, FilePlus, X } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

const DOC_TYPE_LABELS = {
  b2b_invoice: 'B2B Invoice',
  b2c_invoice: 'B2C Invoice',
  quotation: 'Quotation',
  delivery_challan: 'Delivery Challan',
  credit_note: 'Credit Note',
  proforma: 'Proforma',
}

const DOC_TYPE_COLORS = {
  b2b_invoice: 'blue',
  b2c_invoice: 'teal',
  quotation: 'amber',
  delivery_challan: 'gray',
  credit_note: 'red',
  proforma: 'gray',
}

const FY_OPTIONS = ['2026-27', '2025-26', '2024-25', '2023-24']


// ── Tooltip ───────────────────────────────────────────────────
function Tip({ label, children }) {
  return (
    <div className="relative group">
      {children}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1
        rounded bg-gray-800 text-white text-xs whitespace-nowrap pointer-events-none
        opacity-0 group-hover:opacity-100 transition-opacity z-50">
        {label}
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4
          border-transparent border-t-gray-800" />
      </div>
    </div>
  )
}

// ── Quick Payment Modal ──────────────────────────────────────
function PaymentModal({ invoice, onClose, onSuccess }) {
  const [form, setForm] = useState({
    payment_date: new Date().toISOString().split('T')[0],
    amount: Number(invoice.outstanding_amount).toFixed(2),
    payment_mode: 'cash',
    reference_number: '',
    notes: '',
  })

  const mutation = useMutation({
    mutationFn: (d) => receiptAPI.create(d),
    onSuccess: () => {
      toast.success('Payment recorded successfully')
      onSuccess()
      onClose()
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Payment failed'),
  })

  const set = (f) => (e) => setForm(p => ({ ...p, [f]: e.target.value }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-md shadow-xl"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center">
          <div>
            <h2 className="font-semibold text-gray-900">Record Payment</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {invoice.invoice_number} · {invoice.customer_name}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>
        <div className="p-5 space-y-3">
          {/* Summary */}
          <div className="p-3 bg-blue-50 rounded-lg text-sm border border-blue-100 grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-xs text-gray-500">Invoice Total</div>
              <div className="font-semibold text-gray-800">
                ₹{Number(invoice.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Paid</div>
              <div className="font-semibold text-green-600">
                ₹{Number(invoice.paid_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Outstanding</div>
              <div className="font-semibold text-red-600">
                ₹{Number(invoice.outstanding_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Date *</label>
              <input type="date" value={form.payment_date} onChange={set('payment_date')}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) *</label>
              <input type="number" step="0.01" min="0.01" value={form.amount} onChange={set('amount')}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Mode *</label>
              <select value={form.payment_mode} onChange={set('payment_mode')}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                {['cash','bank','cheque','upi','neft','rtgs'].map(m => (
                  <option key={m} value={m}>{m.toUpperCase()}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Reference No.</label>
              <input value={form.reference_number} onChange={set('reference_number')}
                placeholder="UTR / Cheque no."
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
            <input value={form.notes} onChange={set('notes')} placeholder="Optional"
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div className="flex gap-3 justify-end pt-2">
            <button onClick={onClose}
              className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
              Cancel
            </button>
            <button
              onClick={() => {
                if (!form.amount || Number(form.amount) <= 0) { toast.error('Enter amount'); return }
                mutation.mutate({
                  customer_id: invoice.customer_id,
                  invoice_id: invoice.id,
                  payment_date: form.payment_date,
                  amount: Number(form.amount),
                  payment_mode: form.payment_mode,
                  reference_number: form.reference_number || null,
                  tds_amount: 0,
                  is_advance: false,
                  notes: form.notes || null,
                })
              }}
              disabled={mutation.isPending}
              className="px-4 h-9 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700 disabled:opacity-60">
              {mutation.isPending ? 'Saving...' : 'Record Payment'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function BillingPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [converting, setConverting] = useState(null)
  const [payInvoice, setPayInvoice] = useState(null)  // invoice object for payment modal
  const [search, setSearch] = useState('')
  const [docType, setDocType] = useState('')
  const [fy, setFy] = useState('2026-27')

  const handleConvert = async (invId) => {
    setConverting(null)
    try {
      // Fetch full quotation details to pre-fill the invoice form
      const res = await invoiceAPI.get(invId)
      const quot = res.data
      navigate('/billing/new', { state: { quotation: quot } })
    } catch (e) {
      toast.error('Failed to load quotation details')
    }
  }

  const { data, isLoading } = useQuery({
    queryKey: ['invoices', page, search, docType, fy],
    queryFn: () => invoiceAPI.list({
      page, page_size: 20,
      search: search || undefined,
      document_type: docType || undefined,
      financial_year: fy,
    }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const openWhatsApp = async (e, id) => {
    e.stopPropagation()
    try {
      const { data } = await invoiceAPI.whatsapp(id)
      window.open(data.whatsapp_url, '_blank')
    } catch { }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Sales & Billing</div>
          <h1 className="page-title">Invoices & Documents</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => navigate('/billing/customers')}>
            Customers
          </Button>
          <Button variant="secondary" size="sm" onClick={() => navigate('/billing/receipts')}>
            Receipts
          </Button>
          <Button variant="primary" onClick={() => navigate('/billing/new')}>
            <Plus size={14} /> New Document
          </Button>
        </div>
      </div>

      <div className="card mb-4">
        <div className="p-4 flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input placeholder="Search by invoice number..." value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }} className="pl-8" />
          </div>
          <Select value={docType} onChange={e => { setDocType(e.target.value); setPage(1) }} className="w-40">
            <option value="">All types</option>
            {Object.entries(DOC_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select value={fy} onChange={e => { setFy(e.target.value); setPage(1) }} className="w-32">
            {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
          </Select>
        </div>
      </div>

      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : data?.items?.length === 0 ? (
          <Empty message="No documents found"
            action={<Button variant="primary" onClick={() => navigate('/billing/new')}><Plus size={14} />New Document</Button>} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Document No.</th>
                    <th>Type</th>
                    <th>Customer</th>
                    <th>Date</th>
                    <th>Due Date</th>
                    <th className="text-right">Amount (₹)</th>
                    <th className="text-right">Outstanding (₹)</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.map(inv => (
                    <tr key={inv.id} className="cursor-pointer" onClick={() => navigate(`/billing/${inv.id}`)}>
                      <td className="font-mono text-xs font-semibold text-gray-800">{inv.invoice_number}</td>
                      <td>
                        <Badge color={DOC_TYPE_COLORS[inv.document_type] || 'gray'}>
                          {DOC_TYPE_LABELS[inv.document_type] || inv.document_type}
                        </Badge>
                        {inv.document_type === 'delivery_challan' && inv.dc_status && (
                          <Badge color={
                            inv.dc_status === 'linked' ? 'blue' :
                            inv.dc_status === 'delivered' ? 'green' :
                            inv.dc_status === 'cancelled' ? 'red' : 'amber'
                          }>
                            {inv.dc_status.charAt(0).toUpperCase() + inv.dc_status.slice(1)}
                          </Badge>
                        )}
                      </td>
                      <td className="font-medium text-gray-800">
                        {inv.document_type === 'delivery_challan' ? (
                          <span className="text-sm">
                            <span>{inv.warehouse_name || '—'}</span>
                            <span className="text-gray-300 mx-1">→</span>
                            <span>{inv.destination_warehouse_name || '—'}</span>
                          </span>
                        ) : inv.customer_name || '—'}
                      </td>
                      <td className="text-gray-500 text-xs">{inv.invoice_date ? format(new Date(inv.invoice_date), 'dd MMM yyyy') : '—'}</td>
                      <td className="text-xs">
                        {inv.due_date ? (
                          <span className={clsx(new Date(inv.due_date) < new Date() && Number(inv.outstanding_amount) > 0 ? 'text-danger font-medium' : 'text-gray-500')}>
                            {format(new Date(inv.due_date), 'dd MMM yyyy')}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="text-right font-medium">₹{Number(inv.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      <td className="text-right">
                        {inv.document_type === 'quotation' || inv.document_type === 'delivery_challan' ? (
                          <span className="text-xs text-gray-400">—</span>
                        ) : (
                          <span className={clsx('font-medium', Number(inv.outstanding_amount) > 0 ? 'text-danger' : 'text-success')}>
                            ₹{Number(inv.outstanding_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        )}
                      </td>
                      <td>
                        {inv.is_cancelled ? (
                          <Badge color="red">Cancelled</Badge>
                        ) : inv.document_type === 'quotation' ? (
                          inv.quotation_status === 'invoiced'
                            ? <Badge color="green">Invoiced</Badge>
                            : <Badge color="blue">Pending Invoice</Badge>
                        ) : Number(inv.outstanding_amount) <= 0 ? (
                          <Badge color="green">Paid</Badge>
                        ) : Number(inv.paid_amount) > 0 ? (
                          <Badge color="amber">Partial</Badge>
                        ) : (
                          <Badge color="red">Pending</Badge>
                        )}
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <Tip label="View invoice">
                            <button onClick={() => navigate(`/billing/${inv.id}`)}
                              className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                              <Eye size={14} />
                            </button>
                          </Tip>
                          {inv.document_type === 'delivery_challan' && inv.dc_status === 'pending' && (
                            <button title="Cancel DC"
                              onClick={e => {
                                e.stopPropagation()
                                if (window.confirm('Cancel this Delivery Challan?')) {
                                  invoiceAPI.cancelDC(inv.id)
                                    .then(() => { qc.invalidateQueries(['invoices']); toast.success('DC cancelled') })
                                    .catch(e2 => toast.error(e2.response?.data?.detail || 'Failed'))
                                }
                              }}
                              className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 ml-1">
                              <X size={13} />
                            </button>
                          )}
                          {inv.document_type !== 'quotation' && !inv.is_cancelled && Number(inv.outstanding_amount) > 0 && (
                            <Tip label="Record payment">
                              <button
                                onClick={e => { e.stopPropagation(); setPayInvoice(inv) }}
                                className="p-1.5 rounded hover:bg-green-50 text-gray-400 hover:text-green-600">
                                <CreditCard size={14} />
                              </button>
                            </Tip>
                          )}
                          {inv.document_type === 'quotation' && !inv.is_cancelled && !inv.quotation_id && inv.quotation_status !== 'invoiced' && (
                            <Tip label="Convert to Invoice">
                              <button
                                onClick={e => { e.stopPropagation(); setConverting(inv.id) }}
                                className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600">
                                <FilePlus size={14} />
                              </button>
                            </Tip>
                          )}
                          <Tip label="Share on WhatsApp">
                            <button onClick={e => openWhatsApp(e, inv.id)}
                              className="p-1.5 rounded hover:bg-green-50 text-gray-400 hover:text-green-600">
                              <MessageSquare size={14} />
                            </button>
                          </Tip>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={20} onChange={setPage} />}
          </>
        )}
      </div>

      {payInvoice && (
        <PaymentModal
          invoice={payInvoice}
          onClose={() => setPayInvoice(null)}
          onSuccess={() => qc.invalidateQueries(['invoices'])}
        />
      )}

      {converting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={() => setConverting(null)}>
          <div className="bg-white rounded-xl w-full max-w-sm shadow-xl p-6"
            onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold text-gray-900 mb-2">Convert to Invoice?</h3>
            <p className="text-sm text-gray-600 mb-5">
              A new invoice will be created with all line items from this quotation.
              The quotation will be marked as <strong>Invoiced</strong>.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setConverting(null)}
                className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => handleConvert(converting)}
                
                className="px-4 h-9 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-60">
                Yes, Convert →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}