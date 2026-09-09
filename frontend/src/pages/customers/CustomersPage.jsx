import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { customerAPI, receiptAPI, invoiceAPI } from '@/api/billing'
import { Button, Badge, Input, Spinner, Empty, Pagination } from '@/components/ui'
import { Plus, Search, Eye, UserPlus, CreditCard, FileText, X, Upload } from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { useAuthStore } from '@/store/authStore'
import BulkImportModal from '@/components/BulkImportModal'

const PAYMENT_MODES = ['cash','bank','cheque','upi','neft','rtgs']

// ── Tooltip wrapper ───────────────────────────────────────────
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

// ── Quick Payment Modal ───────────────────────────────────────
function PaymentModal({ customer, onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    invoice_id: '',
    payment_date: new Date().toISOString().split('T')[0],
    amount: '',
    payment_mode: 'cash',
    reference_number: '',
    notes: '',
    is_advance: false,
  })

  const { data: invoices } = useQuery({
    queryKey: ['customer-invoices-pending', customer.id],
    queryFn: () => invoiceAPI.list({ customer_id: customer.id, page_size: 100 })
      .then(r => r.data.items?.filter(i => !i.is_cancelled && Number(i.outstanding_amount) > 0)),
  })

  const mutation = useMutation({
    mutationFn: (d) => receiptAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['customers'])
      qc.invalidateQueries(['invoices'])
      qc.invalidateQueries(['receipts'])
      toast.success('Payment recorded')
      onClose()
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const handleSubmit = () => {
    if (!form.amount || Number(form.amount) <= 0) { toast.error('Enter amount'); return }
    if (form.payment_mode !== 'cash' && !form.reference_number.trim()) {
      toast.error('Reference no. required for non-cash payments'); return
    }
    mutation.mutate({
      customer_id: customer.id,
      invoice_id: form.invoice_id ? Number(form.invoice_id) : null,
      payment_date: form.payment_date,
      amount: Number(form.amount),
      payment_mode: form.payment_mode,
      reference_number: form.reference_number || null,
      tds_amount: 0,
      is_advance: form.is_advance || !form.invoice_id,
      notes: form.notes || null,
    })
  }

  const set = (f) => (e) => setForm(p => ({ ...p, [f]: e.target.value }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-md shadow-xl"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center">
          <div>
            <h2 className="font-semibold text-gray-900">Record Payment</h2>
            <p className="text-xs text-gray-400 mt-0.5">{customer.trade_name}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Apply to Invoice <span className="text-gray-400">(optional)</span>
            </label>
            <select value={form.invoice_id}
              onChange={e => {
                setForm(p => ({ ...p, invoice_id: e.target.value }))
                if (e.target.value) {
                  const inv = invoices?.find(i => i.id === Number(e.target.value))
                  if (inv) setForm(p => ({ ...p, invoice_id: e.target.value, amount: Number(inv.outstanding_amount).toFixed(2) }))
                }
              }}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
              <option value="">Advance / No specific invoice</option>
              {invoices?.map(inv => (
                <option key={inv.id} value={inv.id}>
                  {inv.invoice_number} — ₹{Number(inv.outstanding_amount).toFixed(2)} pending
                </option>
              ))}
            </select>
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
                placeholder="0.00"
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Mode *</label>
              <select value={form.payment_mode} onChange={set('payment_mode')}
                className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                {PAYMENT_MODES.map(m => <option key={m} value={m}>{m.toUpperCase()}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Reference No. {form.payment_mode !== 'cash' && <span className="text-red-500">*</span>}
              </label>
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
            <button onClick={handleSubmit} disabled={mutation.isPending}
              className="px-4 h-9 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700 disabled:opacity-60">
              {mutation.isPending ? 'Saving...' : 'Record Payment'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────
export default function CustomersPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { isAdmin, isAccountant } = useAuthStore()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [statusActive, setStatusActive] = useState(true)
  const [payCustomer, setPayCustomer] = useState(null)
  const [importOpen, setImportOpen] = useState(false)
  const [selected, setSelected] = useState([])

  const { data, isLoading } = useQuery({
    queryKey: ['customers', page, search, statusActive],
    queryFn: () => customerAPI.list({ page, page_size: 20, search: search || undefined, is_active: statusActive })
      .then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const canManage = isAdmin() || isAccountant()
  // Bulk activate/deactivate is admin-only (backend require_admin guard).
  const canBulk = isAdmin()

  const rows = data?.items || []
  const allSelected = rows.length > 0 && selected.length === rows.length
  const clearSelection = () => setSelected([])
  const toggleOne = (id) => setSelected(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])
  const toggleAll = () => setSelected(allSelected ? [] : rows.map(c => c.id))

  const bulkMutation = useMutation({
    mutationFn: () => customerAPI.bulkStatus({ customer_ids: selected, is_active: !statusActive }),
    onSuccess: (res) => {
      qc.invalidateQueries(['customers'])
      const n = res.data?.updated ?? selected.length
      toast.success(`${n} customer(s) marked ${statusActive ? 'inactive' : 'active'}`)
      clearSelection()
    },
    onError: e => toast.error(e.response?.data?.detail || 'Bulk update failed'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Billing</div>
          <h1 className="page-title">Customers</h1>
        </div>
        {canManage && (
          <div className="flex items-center gap-2">
            {isAdmin() && (
              <Button variant="secondary" onClick={() => setImportOpen(true)}>
                <Upload size={14} /> Import CSV
              </Button>
            )}
            <Button variant="primary" onClick={() => navigate('/billing/customers/new')}>
              <UserPlus size={14} /> New Customer
            </Button>
          </div>
        )}
      </div>

      {importOpen && (
        <BulkImportModal
          title="Import Customers from CSV"
          entityLabel="customers"
          uploadFn={customerAPI.bulkImport}
          templateFn={customerAPI.importTemplate}
          templateName="customer_import_template.csv"
          invalidateKey="customers"
          columns={['trade_name (required)', 'gstin', 'is_b2b', 'phone', 'credit_limit', 'address_line1', 'city', 'addr_state', 'pincode']}
          onClose={() => setImportOpen(false)}
        />
      )}

      <div className="card mb-4">
        <div className="p-4 flex items-center gap-3">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input placeholder="Search by name or GSTIN..."
              value={search} onChange={e => { setSearch(e.target.value); setPage(1); clearSelection() }}
              className="pl-8" />
          </div>
          <select
            value={String(statusActive)}
            onChange={e => { setStatusActive(e.target.value === 'true'); setPage(1); clearSelection() }}
            className="w-32 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </div>

      {canBulk && selected.length > 0 && (
        <div className="card mb-4 border-blue-200 bg-blue-50">
          <div className="p-3 flex items-center justify-between">
            <span className="text-sm text-blue-800 font-medium">{selected.length} selected</span>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={clearSelection}>Clear</Button>
              <Button variant="primary" loading={bulkMutation.isPending}
                onClick={() => bulkMutation.mutate()}>
                {statusActive ? 'Make Inactive' : 'Make Active'}
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : data?.items?.length === 0 ? (
          <Empty message="No customers found"
            action={canManage && (
              <Button variant="primary" onClick={() => navigate('/billing/customers/new')}>
                <UserPlus size={14} /> Add Customer
              </Button>
            )} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    {canBulk && (
                      <th className="w-10 text-center">
                        <input type="checkbox" checked={allSelected} onChange={toggleAll}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                      </th>
                    )}
                    <th>Customer</th>
                    <th>GSTIN</th>
                    <th>Phone</th>
                    <th>State</th>
                    <th className="text-right">Outstanding (₹)</th>
                    <th>Status</th>
                    <th className="text-center w-32">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.map(c => (
                    <tr key={c.id}>
                      {canBulk && (
                        <td className="text-center">
                          <input type="checkbox" checked={selected.includes(c.id)}
                            onChange={() => toggleOne(c.id)}
                            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                        </td>
                      )}
                      <td>
                        <div className="font-medium text-gray-900">{c.trade_name}</div>
                        {c.legal_name && c.legal_name !== c.trade_name && (
                          <div className="text-xs text-gray-400">{c.legal_name}</div>
                        )}
                      </td>
                      <td className="font-mono text-xs text-gray-600">{c.gstin || '—'}</td>
                      <td className="text-gray-600">{c.phone || '—'}</td>
                      <td className="text-gray-600 text-sm">{c.state || '—'}</td>
                      <td className="text-right">
                        <span className={clsx(
                          'font-semibold',
                          Number(c.outstanding_balance || 0) > 0 ? 'text-red-600' : 'text-gray-400'
                        )}>
                          ₹{Number(c.outstanding_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </td>
                      <td>
                        <Badge color={c.is_active ? 'green' : 'gray'}>
                          {c.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td>
                        <div className="flex items-center justify-center gap-1">
                          <Tip label="View customer">
                            <button
                              onClick={() => navigate(`/billing/customers/${c.id}`)}
                              className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors">
                              <Eye size={14} />
                            </button>
                          </Tip>
                          <Tip label="New invoice">
                            <button
                              onClick={() => navigate('/billing/new', { state: { customer_id: c.id } })}
                              className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600 transition-colors">
                              <FileText size={14} />
                            </button>
                          </Tip>
                          {canManage && (
                            <Tip label="Record payment">
                              <button
                                onClick={() => setPayCustomer(c)}
                                className="p-1.5 rounded hover:bg-green-50 text-gray-400 hover:text-green-600 transition-colors">
                                <CreditCard size={14} />
                              </button>
                            </Tip>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data && (
              <Pagination page={data.page} pages={data.pages}
                total={data.total} pageSize={20} onChange={(p) => { setPage(p); clearSelection() }} />
            )}
          </>
        )}
      </div>

      {data && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="stat-card">
            <div className="stat-label">Total Customers</div>
            <div className="stat-value">{data.total}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Active (this page)</div>
            <div className="stat-value text-green-600">
              {data.items?.filter(c => c.is_active).length}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Outstanding (this page)</div>
            <div className="stat-value text-red-600" style={{ fontSize: '1rem' }}>
              ₹{data.items?.reduce((s, c) => s + Number(c.outstanding_balance || 0), 0)
                .toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>
        </div>
      )}

      {payCustomer && (
        <PaymentModal customer={payCustomer} onClose={() => setPayCustomer(null)} />
      )}
    </div>
  )
}
