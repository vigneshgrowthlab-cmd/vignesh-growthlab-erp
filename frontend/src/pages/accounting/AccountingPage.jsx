import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { chequeAPI, cashAPI, expenseAPI, tdsAPI, ageingAPI, journalAPI, vendorDueAPI } from '@/api/accounting'
import { customerAPI, invoiceAPI } from '@/api/billing'
import { vendorAPI } from '@/api/purchase'
import { Button, Badge, Spinner, Empty, Pagination, AlertBox } from '@/components/ui'
import { Plus, X, Check, AlertTriangle, ChevronDown } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'

const TABS = ['Cheque Register', 'Cash Closing', 'Expenses', 'TDS', 'Customer Ageing', 'Journal', 'Trial Balance', 'Vendor Dues']

const ic = (err) => clsx(
  'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
  err ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
)

// ─── Cheque Register ─────────────────────────────────────────
function ChequeTab() {
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [form, setForm] = useState({
    cheque_number: '', cheque_date: format(new Date(), 'yyyy-MM-dd'),
    bank_name: '', amount: '', customer_id: '', is_pdc: false, deposit_date: '',
  })
  const [errors, setErrors] = useState({})

  const { data: customers } = useQuery({
    queryKey: ['customers-all'],
    queryFn: () => customerAPI.list({ page_size: 500 }).then(r => r.data.items),
  })

  const { data: cheques, isLoading } = useQuery({
    queryKey: ['cheques', statusFilter],
    queryFn: () => chequeAPI.list({ status: statusFilter || undefined, page_size: 50 }).then(r => r.data),
  })

  const { data: pdcAlerts } = useQuery({
    queryKey: ['pdc-alerts'],
    queryFn: () => chequeAPI.pdcAlerts().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (d) => chequeAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['cheques'])
      toast.success('Cheque added to register')
      setShowNew(false)
      setForm({ cheque_number: '', cheque_date: format(new Date(), 'yyyy-MM-dd'), bank_name: '', amount: '', customer_id: '', is_pdc: false, deposit_date: '' })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const actionMutation = useMutation({
    mutationFn: ({ action, id, data }) => {
      if (action === 'deposit') return chequeAPI.deposit(id, data)
      if (action === 'clear') return chequeAPI.clear(id, data)
      if (action === 'bounce') return chequeAPI.bounce(id, data)
    },
    onSuccess: () => { qc.invalidateQueries(['cheques']); toast.success('Updated') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.cheque_number) errs.cheque_number = 'Required'
    if (!form.bank_name) errs.bank_name = 'Required'
    if (!form.amount || Number(form.amount) <= 0) errs.amount = 'Enter valid amount'
    if (!form.cheque_date) errs.cheque_date = 'Required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    createMutation.mutate({
      cheque_number: form.cheque_number,
      cheque_date: form.cheque_date,
      bank_name: form.bank_name,
      amount: Number(form.amount),
      customer_id: form.customer_id ? Number(form.customer_id) : null,
      is_pdc: Boolean(form.is_pdc),
      deposit_date: form.deposit_date || null,
    })
  }

  const STATUS_COLORS = { received: 'blue', deposited: 'amber', cleared: 'green', bounced: 'red', pdc_pending: 'purple' }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-2">
          {['', 'received', 'deposited', 'cleared', 'bounced', 'pdc_pending'].map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                statusFilter === s ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
              {s || 'All'}
            </button>
          ))}
        </div>
        <Button variant="primary" size="sm" onClick={() => setShowNew(true)}><Plus size={14} /> Add Cheque</Button>
      </div>

      {pdcAlerts?.length > 0 && (
        <AlertBox type="warning" className="mb-4">
          <AlertTriangle size={14} className="inline mr-1" />
          {pdcAlerts.length} PDC cheque{pdcAlerts.length > 1 ? 's' : ''} due for deposit in the next 7 days
        </AlertBox>
      )}

      {showNew && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between items-center">
            <h3 className="font-semibold">Add Cheque to Register</h3>
            <button onClick={() => { setShowNew(false); setErrors({}) }} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Cheque Number <span className="text-red-500">*</span></label>
                <input value={form.cheque_number} onChange={e => hc('cheque_number', e.target.value)} placeholder="123456" className={ic(errors.cheque_number)} />
                {errors.cheque_number && <p className="text-xs text-red-500 mt-1">{errors.cheque_number}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Cheque Date <span className="text-red-500">*</span></label>
                <input type="date" value={form.cheque_date} onChange={e => hc('cheque_date', e.target.value)} className={ic(errors.cheque_date)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Bank Name <span className="text-red-500">*</span></label>
                <input value={form.bank_name} onChange={e => hc('bank_name', e.target.value)} placeholder="HDFC Bank" className={ic(errors.bank_name)} />
                {errors.bank_name && <p className="text-xs text-red-500 mt-1">{errors.bank_name}</p>}
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) <span className="text-red-500">*</span></label>
                <input type="number" step="0.01" min="0.01" value={form.amount} onChange={e => hc('amount', e.target.value)} placeholder="0.00" className={ic(errors.amount)} />
                {errors.amount && <p className="text-xs text-red-500 mt-1">{errors.amount}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Customer</label>
                <select value={form.customer_id} onChange={e => hc('customer_id', e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select customer...</option>
                  {customers?.map(c => <option key={c.id} value={c.id}>{c.trade_name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Deposit Date (PDC)</label>
                <input type="date" value={form.deposit_date} onChange={e => hc('deposit_date', e.target.value)} className={ic()} />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.is_pdc} onChange={e => hc('is_pdc', e.target.checked)} className="rounded" />
              <span className="text-gray-700">Post-dated cheque (PDC)</span>
            </label>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowNew(false); setErrors({}) }}>Cancel</Button>
              <Button variant="primary" loading={createMutation.isPending} onClick={handleSubmit}>Add to Register</Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : cheques?.items?.length === 0 ? <Empty message="No cheques found" />
        : (
          <div className="overflow-x-auto">
            <table className="table min-w-[700px]">
              <thead><tr><th>Cheque No.</th><th>Bank</th><th>Customer</th><th>Cheque Date</th><th className="text-right">Amount (₹)</th><th>Type</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {cheques?.items?.map(ch => (
                  <tr key={ch.id}>
                    <td className="font-mono text-xs font-semibold">{ch.cheque_number}</td>
                    <td className="text-sm text-gray-600">{ch.bank_name}</td>
                    <td className="text-sm">{ch.customer_name || '—'}</td>
                    <td className="text-xs text-gray-500">{ch.cheque_date ? format(new Date(ch.cheque_date), 'dd MMM yyyy') : '—'}</td>
                    <td className="text-right font-semibold">₹{Number(ch.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td><Badge color={ch.is_pdc ? 'purple' : 'blue'}>{ch.is_pdc ? 'PDC' : 'Regular'}</Badge></td>
                    <td><Badge color={STATUS_COLORS[ch.status] || 'gray'}>{ch.status}</Badge></td>
                    <td>
                      <div className="flex gap-1">
                        {ch.status === 'received' && (
                          <button onClick={() => actionMutation.mutate({ action: 'deposit', id: ch.id, data: { deposit_date: format(new Date(), 'yyyy-MM-dd') } })}
                            className="px-2 py-1 text-xs bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200">Deposit</button>
                        )}
                        {ch.status === 'deposited' && (
                          <>
                            <button onClick={() => actionMutation.mutate({ action: 'clear', id: ch.id, data: { clearance_date: format(new Date(), 'yyyy-MM-dd') } })}
                              className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded-lg hover:bg-green-200">Clear</button>
                            <button onClick={() => actionMutation.mutate({ action: 'bounce', id: ch.id, data: { bounce_date: format(new Date(), 'yyyy-MM-dd'), bounce_reason: 'Insufficient funds' } })}
                              className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded-lg hover:bg-red-200">Bounce</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// ─── Cash Closing ─────────────────────────────────────────────
function CashClosingTab() {
  const qc = useQueryClient()
  const { isAdmin } = useAuthStore()
  const today = format(new Date(), 'yyyy-MM-dd')
  const [form, setForm] = useState({ closing_date: today, total_deposits: '0', notes: '' })

  const { data: closing } = useQuery({
    queryKey: ['cash-closing', today],
    queryFn: () => cashAPI.getClosing(today).then(r => r.data).catch(() => null),
  })

  useEffect(() => {
    if (closing && closing.total_deposits != null) {
      setForm(p => ({ ...p, total_deposits: String(closing.total_deposits) }))
    }
  }, [closing?.id, closing?.total_deposits])

  const mutation = useMutation({
    mutationFn: (d) => cashAPI.createClosing(d),
    onSuccess: () => { qc.invalidateQueries(['cash-closing']); toast.success('Cash closing saved') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const approveMutation = useMutation({
    mutationFn: (id) => cashAPI.approveClosing(id),
    onSuccess: () => { qc.invalidateQueries(['cash-closing']); toast.success('Closing approved') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const handleSubmit = () => {
    mutation.mutate({
      closing_date: form.closing_date,
      total_deposits: Number(form.total_deposits) || 0,
    })
  }

  return (
    <div className="max-w-lg">
      <h3 className="font-semibold text-gray-800 mb-4">Today's Cash Closing — {format(new Date(), 'dd MMM yyyy')}</h3>
      {closing ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Opening Balance', val: closing.opening_balance, color: 'text-gray-700' },
              { label: 'Total Cash Receipts', val: closing.total_receipts, color: 'text-green-600' },
              { label: 'Cash Payments', val: closing.total_payments, color: 'text-red-600' },
              { label: 'Cash Expenses', val: closing.total_expenses, color: 'text-red-600' },
              { label: 'Bank Deposits', val: closing.total_deposits, color: 'text-blue-600' },
              { label: 'Closing Balance', val: closing.closing_balance, color: 'text-primary font-semibold' },
            ].map(c => (
              <div key={c.label} className="stat-card">
                <div className="stat-label">{c.label}</div>
                <div className={clsx('text-lg font-semibold mt-1', c.color)}>
                  ₹{Number(c.val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
            ))}
          </div>
          {isAdmin() && closing.status !== 'approved' && (
            <div className="p-3 rounded-lg border border-gray-200 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Bank Deposits Today (₹)</label>
                <input type="number" step="0.01" min="0" value={form.total_deposits}
                  onChange={e => setForm(p => ({ ...p, total_deposits: e.target.value }))}
                  placeholder="0.00" className={ic()} />
              </div>
              <Button variant="secondary" size="sm" loading={mutation.isPending} onClick={handleSubmit}>
                Save Draft
              </Button>
            </div>
          )}
          <div className="flex items-center justify-between p-3 rounded-lg border border-gray-200">
            <div>
              <div className="text-sm font-medium">Status</div>
              <Badge color={closing.status === 'approved' ? 'green' : 'amber'}>{closing.status}</Badge>
            </div>
            {isAdmin() && closing.status !== 'approved' && (
              <Button variant="success" size="sm" loading={approveMutation.isPending}
                onClick={() => approveMutation.mutate(closing.id)}>
                <Check size={14} /> Approve Closing
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <AlertBox type="info">No cash closing found for today. Create one to record the daily cash balance.</AlertBox>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Bank Deposits Today (₹)</label>
            <input type="number" step="0.01" min="0" value={form.total_deposits}
              onChange={e => setForm(p => ({ ...p, total_deposits: e.target.value }))}
              placeholder="0.00" className={ic()} />
          </div>
          <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
            Create Cash Closing
          </Button>
        </div>
      )}
    </div>
  )
}

// ─── Expenses ─────────────────────────────────────────────────
function ExpensesTab() {
  const qc = useQueryClient()
  const { isAdmin } = useAuthStore()
  const [showNew, setShowNew] = useState(false)
  const [showNewCategory, setShowNewCategory] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [newCatName, setNewCatName] = useState('')

  const DEFAULT_CATEGORIES = [
    'Rent', 'Electricity', 'Internet', 'Salaries', 'Fuel', 'Transport',
    'Office Supplies', 'Repairs & Maintenance', 'Marketing', 'Printing',
    'Telephone', 'Bank Charges', 'Professional Fees', 'Other',
  ]

  const [form, setForm] = useState({
    expense_date: format(new Date(), 'yyyy-MM-dd'),
    category: '', description: '', amount: '',
    payment_mode: 'cash', reference_number: '', notes: '',
  })
  const [errors, setErrors] = useState({})
  const [customCategories, setCustomCategories] = useState([])
  const allCategories = [...DEFAULT_CATEGORIES, ...customCategories]

  const { data: expenses, isLoading } = useQuery({
    queryKey: ['expenses', statusFilter],
    queryFn: () => expenseAPI.list({ status: statusFilter || undefined, page_size: 50 }).then(r => r.data),
  })

  const mutation = useMutation({
    mutationFn: (d) => expenseAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['expenses'])
      toast.success('Expense recorded')
      setShowNew(false)
      setForm({ expense_date: format(new Date(), 'yyyy-MM-dd'), category: '', description: '', amount: '', payment_mode: 'cash', reference_number: '', notes: '' })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const approveMutation = useMutation({
    mutationFn: ({ id, approved }) => expenseAPI.approve(id, { approved }),
    onSuccess: () => { qc.invalidateQueries(['expenses']); toast.success('Decision saved') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.category) errs.category = 'Select category'
    if (!form.description) errs.description = 'Required'
    if (!form.amount || Number(form.amount) <= 0) errs.amount = 'Enter valid amount'
    if (!form.expense_date) errs.expense_date = 'Required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    mutation.mutate({
      expense_date: form.expense_date,
      category: form.category,
      description: form.description,
      amount: Number(form.amount),
      payment_mode: form.payment_mode,
      reference_number: form.reference_number || null,
      notes: form.notes || null,
    })
  }

  const addCategory = () => {
    if (!newCatName.trim()) return
    if (allCategories.includes(newCatName.trim())) { toast.error('Category already exists'); return }
    setCustomCategories(p => [...p, newCatName.trim()])
    setForm(p => ({ ...p, category: newCatName.trim() }))
    setNewCatName('')
    setShowNewCategory(false)
    toast.success('Category added')
  }

  const STATUS_COLORS = { approved: 'green', pending_approval: 'amber', rejected: 'red' }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex gap-2 flex-wrap">
          {['', 'approved', 'pending_approval', 'rejected'].map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                statusFilter === s ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
              {s || 'All'}
            </button>
          ))}
        </div>
        <Button variant="primary" size="sm" onClick={() => setShowNew(true)} className="self-start sm:self-auto"><Plus size={14} /> New Expense</Button>
      </div>

      {showNew && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">Record Expense</h3>
            <button onClick={() => { setShowNew(false); setErrors({}) }} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Date <span className="text-red-500">*</span></label>
                <input type="date" value={form.expense_date} onChange={e => hc('expense_date', e.target.value)} className={ic(errors.expense_date)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Category <span className="text-red-500">*</span>
                  <button onClick={() => setShowNewCategory(true)}
                    className="ml-2 text-blue-600 hover:text-blue-700 text-xs font-normal">+ Add new</button>
                </label>
                {showNewCategory ? (
                  <div className="flex gap-2">
                    <input value={newCatName} onChange={e => setNewCatName(e.target.value)}
                      placeholder="New category name" onKeyDown={e => e.key === 'Enter' && addCategory()}
                      className="flex-1 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                    <button onClick={addCategory} className="px-3 h-9 bg-blue-600 text-white text-sm rounded-lg">Add</button>
                    <button onClick={() => setShowNewCategory(false)} className="px-2 h-9 text-gray-400"><X size={14} /></button>
                  </div>
                ) : (
                  <select value={form.category} onChange={e => hc('category', e.target.value)}
                    className={clsx('w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:border-blue-500', errors.category ? 'border-red-400' : 'border-gray-300')}>
                    <option value="">Select category...</option>
                    {allCategories.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                )}
                {errors.category && <p className="text-xs text-red-500 mt-1">{errors.category}</p>}
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Description <span className="text-red-500">*</span></label>
              <input value={form.description} onChange={e => hc('description', e.target.value)}
                placeholder="What was this expense for?" className={ic(errors.description)} />
              {errors.description && <p className="text-xs text-red-500 mt-1">{errors.description}</p>}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Amount (₹) <span className="text-red-500">*</span></label>
                <input type="number" step="0.01" min="0.01" value={form.amount} onChange={e => hc('amount', e.target.value)}
                  placeholder="0.00" className={ic(errors.amount)} />
                {errors.amount && <p className="text-xs text-red-500 mt-1">{errors.amount}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Payment Mode</label>
                <select value={form.payment_mode} onChange={e => hc('payment_mode', e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  {['cash', 'bank_transfer', 'upi', 'cheque', 'neft'].map(m => <option key={m} value={m}>{m.replace('_', ' ')}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Reference No.</label>
                <input value={form.reference_number} onChange={e => hc('reference_number', e.target.value)}
                  placeholder="Optional" className={ic()} />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowNew(false); setErrors({}) }}>Cancel</Button>
              <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>Record Expense</Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : expenses?.items?.length === 0 ? <Empty message="No expenses found" />
        : (
          <div className="overflow-x-auto">
            <table className="table min-w-[640px]">
              <thead><tr><th>No.</th><th>Date</th><th>Category</th><th>Description</th><th>Mode</th><th className="text-right">Amount (₹)</th><th>Status</th>{isAdmin() && <th>Actions</th>}</tr></thead>
              <tbody>
                {expenses?.items?.map(e => (
                  <tr key={e.id}>
                    <td className="font-mono text-xs">{e.expense_number}</td>
                    <td className="text-xs text-gray-500">{e.expense_date ? format(new Date(e.expense_date), 'dd MMM yyyy') : '—'}</td>
                    <td><Badge color="gray">{e.category}</Badge></td>
                    <td className="text-sm text-gray-700 max-w-xs truncate">{e.description}</td>
                    <td className="text-xs text-gray-500">{e.payment_mode}</td>
                    <td className="text-right font-medium">₹{Number(e.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td><Badge color={STATUS_COLORS[e.status] || 'gray'}>{e.status}</Badge></td>
                    {isAdmin() && e.status === 'pending_approval' && (
                      <td>
                        <div className="flex gap-1">
                          <button onClick={() => approveMutation.mutate({ id: e.id, approved: true })}
                            className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded">Approve</button>
                          <button onClick={() => approveMutation.mutate({ id: e.id, approved: false })}
                            className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded">Reject</button>
                        </div>
                      </td>
                    )}
                    {isAdmin() && e.status !== 'pending_approval' && <td />}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// ─── TDS ─────────────────────────────────────────────────────
function TDSTab() {
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [fy, setFy] = useState('2026-27')
  const [form, setForm] = useState({
    customer_id: '', tds_amount: '', tds_percent: '1',
    invoice_amount: '', deduction_date: format(new Date(), 'yyyy-MM-dd'),
    tan_number: '', section_code: '194C',
  })
  const [errors, setErrors] = useState({})

  const { data: customers } = useQuery({
    queryKey: ['customers-all'],
    queryFn: () => customerAPI.list({ page_size: 500 }).then(r => r.data.items),
  })

  const { data: tdsEntries, isLoading } = useQuery({
    queryKey: ['tds', fy],
    queryFn: () => tdsAPI.list({ financial_year: fy, page_size: 50 }).then(r => r.data),
  })

  const mutation = useMutation({
    mutationFn: (d) => tdsAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['tds'])
      toast.success('TDS entry recorded')
      setShowNew(false)
      setForm({ customer_id: '', tds_amount: '', tds_percent: '1', invoice_amount: '', deduction_date: format(new Date(), 'yyyy-MM-dd'), tan_number: '', section_code: '194C' })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const hc = (f, v) => {
    setForm(p => {
      const updated = { ...p, [f]: v }
      // Auto-calc TDS amount when percent or invoice amount changes
      if ((f === 'tds_percent' || f === 'invoice_amount') && updated.invoice_amount && updated.tds_percent) {
        updated.tds_amount = (Number(updated.invoice_amount) * Number(updated.tds_percent) / 100).toFixed(2)
      }
      return updated
    })
    if (errors[f]) setErrors(p => ({ ...p, [f]: '' }))
  }

  const validate = () => {
    const errs = {}
    if (!form.customer_id) errs.customer_id = 'Select customer'
    if (!form.tds_amount || Number(form.tds_amount) <= 0) errs.tds_amount = 'Enter valid amount'
    if (!form.invoice_amount || Number(form.invoice_amount) <= 0) errs.invoice_amount = 'Required'
    if (!form.deduction_date) errs.deduction_date = 'Required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    mutation.mutate({
      customer_id: Number(form.customer_id),
      tds_amount: Number(form.tds_amount),
      tds_percent: Number(form.tds_percent),
      invoice_amount: Number(form.invoice_amount),
      deduction_date: form.deduction_date,
      tan_number: form.tan_number || null,
      section_code: form.section_code,
      financial_year: fy,
    })
  }

  const totalTDS = tdsEntries?.items?.reduce((s, e) => s + Number(e.tds_amount), 0) || 0
  const reconciled = tdsEntries?.items?.filter(e => e.is_reconciled).length || 0

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <select value={fy} onChange={e => setFy(e.target.value)}
            className="h-8 px-3 rounded-lg border border-gray-300 text-sm">
            {['2026-27', '2025-26', '2024-25', '2023-24'].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <Button variant="primary" size="sm" onClick={() => setShowNew(true)} className="self-start sm:self-auto"><Plus size={14} /> New TDS Entry</Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <div className="stat-card"><div className="stat-label">Total TDS Receivable</div><div className="stat-value text-primary">₹{totalTDS.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</div></div>
        <div className="stat-card"><div className="stat-label">Reconciled</div><div className="stat-value text-success">{reconciled}</div></div>
        <div className="stat-card"><div className="stat-label">Unreconciled</div><div className="stat-value text-danger">{(tdsEntries?.items?.length || 0) - reconciled}</div></div>
      </div>

      {showNew && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">Record TDS Deduction</h3>
            <button onClick={() => { setShowNew(false); setErrors({}) }} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Customer <span className="text-red-500">*</span></label>
                <select value={form.customer_id} onChange={e => hc('customer_id', e.target.value)}
                  className={clsx('w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:border-blue-500', errors.customer_id ? 'border-red-400' : 'border-gray-300')}>
                  <option value="">Select customer...</option>
                  {customers?.map(c => <option key={c.id} value={c.id}>{c.trade_name}</option>)}
                </select>
                {errors.customer_id && <p className="text-xs text-red-500 mt-1">{errors.customer_id}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Deduction Date <span className="text-red-500">*</span></label>
                <input type="date" value={form.deduction_date} onChange={e => hc('deduction_date', e.target.value)} className={ic(errors.deduction_date)} />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Amount (₹) <span className="text-red-500">*</span></label>
                <input type="number" step="0.01" value={form.invoice_amount} onChange={e => hc('invoice_amount', e.target.value)}
                  placeholder="0.00" className={ic(errors.invoice_amount)} />
                {errors.invoice_amount && <p className="text-xs text-red-500 mt-1">{errors.invoice_amount}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">TDS % <span className="text-red-500">*</span></label>
                <input type="number" step="0.01" value={form.tds_percent} onChange={e => hc('tds_percent', e.target.value)} className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">TDS Amount (₹) <span className="text-red-500">*</span></label>
                <input type="number" step="0.01" value={form.tds_amount} onChange={e => hc('tds_amount', e.target.value)}
                  placeholder="Auto-calculated" className={ic(errors.tds_amount)} />
                {errors.tds_amount && <p className="text-xs text-red-500 mt-1">{errors.tds_amount}</p>}
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">TAN Number</label>
                <input value={form.tan_number} onChange={e => hc('tan_number', e.target.value.toUpperCase())}
                  placeholder="AAAA99999A" className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Section Code</label>
                <select value={form.section_code} onChange={e => hc('section_code', e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  {['194C', '194J', '194H', '194I', '194B', '194D'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowNew(false); setErrors({}) }}>Cancel</Button>
              <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>Record TDS</Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : tdsEntries?.items?.length === 0 ? <Empty message="No TDS entries for this FY" />
        : (
          <div className="overflow-x-auto">
            <table className="table min-w-[700px]">
              <thead><tr><th>TDS No.</th><th>Customer</th><th>Date</th><th>Section</th><th className="text-right">Invoice Amt</th><th className="text-right">TDS Amount</th><th>TAN</th><th>Reconciled</th></tr></thead>
              <tbody>
                {tdsEntries?.items?.map(e => (
                  <tr key={e.id}>
                    <td className="font-mono text-xs">{e.tds_number}</td>
                    <td className="text-sm">{e.customer_name}</td>
                    <td className="text-xs text-gray-500">{e.deduction_date ? format(new Date(e.deduction_date), 'dd MMM yyyy') : '—'}</td>
                    <td><Badge color="blue">{e.section_code}</Badge></td>
                    <td className="text-right text-sm">₹{Number(e.invoice_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="text-right font-semibold text-primary">₹{Number(e.tds_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="text-xs font-mono text-gray-500">{e.tan_number || '—'}</td>
                    <td><Badge color={e.is_reconciled ? 'green' : 'gray'}>{e.is_reconciled ? 'Yes' : 'No'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// ─── Customer Ageing ──────────────────────────────────────────
function AgeingTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['customer-ageing'],
    queryFn: () => ageingAPI.customerAgeing().then(r => r.data),
  })
  const total = data?.summary || {}
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-4">
        {[
          { label: 'Current (0-30)', val: total.bucket_0_30, color: 'text-success' },
          { label: '31-60 Days', val: total.bucket_31_60, color: 'text-amber-600' },
          { label: '61-90 Days', val: total.bucket_61_90, color: 'text-orange-600' },
          { label: '90+ Days', val: total.bucket_90_plus, color: 'text-danger' },
        ].map(c => (
          <div key={c.label} className="stat-card">
            <div className="stat-label">{c.label}</div>
            <div className={clsx('text-base font-semibold mt-1', c.color)}>
              ₹{Number(c.val || 0).toLocaleString('en-IN', { minimumFractionDigits: 0 })}
            </div>
          </div>
        ))}
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : data?.items?.length === 0 ? <Empty message="No outstanding amounts" />
        : (
          <div className="overflow-x-auto">
            <table className="table min-w-[600px]">
              <thead><tr><th>Customer</th><th className="text-right">Current</th><th className="text-right">31-60</th><th className="text-right">61-90</th><th className="text-right">90+</th><th className="text-right">Total</th></tr></thead>
              <tbody>
                {data?.items?.map((c, i) => (
                  <tr key={i}>
                    <td className="font-medium">{c.customer_name}</td>
                    {['bucket_0_30', 'bucket_31_60', 'bucket_61_90', 'bucket_90_plus'].map(k => (
                      <td key={k} className={clsx('text-right text-sm', c[k] > 0 ? 'font-medium' : 'text-gray-300')}>
                        {c[k] > 0 ? `₹${Number(c[k]).toLocaleString('en-IN', { minimumFractionDigits: 0 })}` : '—'}
                      </td>
                    ))}
                    <td className="text-right font-semibold text-primary">₹{Number(c.total_outstanding).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// ─── Journal ──────────────────────────────────────────────────
function JournalTab() {
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [form, setForm] = useState({ entry_date: format(new Date(), 'yyyy-MM-dd'), narration: '', lines: [{ account_code: '', transaction_type: 'debit', amount: '' }, { account_code: '', transaction_type: 'credit', amount: '' }] })
  const [errors, setErrors] = useState({})

  const { data: accounts } = useQuery({ queryKey: ['accounts'], queryFn: () => journalAPI.accounts().then(r => r.data) })
  const { data: entries, isLoading } = useQuery({ queryKey: ['journal-entries'], queryFn: () => journalAPI.list({ page_size: 50 }).then(r => r.data) })

  const mutation = useMutation({
    mutationFn: (d) => journalAPI.create(d),
    onSuccess: () => { qc.invalidateQueries(['journal-entries']); toast.success('Journal entry posted'); setShowNew(false) },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const totalDebit = form.lines.filter(l => l.transaction_type === 'debit').reduce((s, l) => s + (Number(l.amount) || 0), 0)
  const totalCredit = form.lines.filter(l => l.transaction_type === 'credit').reduce((s, l) => s + (Number(l.amount) || 0), 0)
  const balanced = Math.abs(totalDebit - totalCredit) < 0.01

  const handleSubmit = () => {
    if (!balanced) { toast.error('Debit and Credit must be equal'); return }
    if (!form.narration) { setErrors({ narration: 'Required' }); return }
    mutation.mutate({ entry_date: form.entry_date, narration: form.narration, lines: form.lines.filter(l => l.account_code && Number(l.amount) > 0).map(l => ({ account_code: l.account_code, transaction_type: l.transaction_type, amount: Number(l.amount) })) })
  }

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button variant="primary" size="sm" onClick={() => setShowNew(true)}><Plus size={14} /> New Entry</Button>
      </div>
      {showNew && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">New Journal Entry</h3>
            <button onClick={() => setShowNew(false)} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Date</label>
                <input type="date" value={form.entry_date} onChange={e => setForm(p => ({ ...p, entry_date: e.target.value }))} className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Narration <span className="text-red-500">*</span></label>
                <input value={form.narration} onChange={e => { setForm(p => ({ ...p, narration: e.target.value })); setErrors({}) }}
                  placeholder="Description of this entry" className={ic(errors.narration)} />
                {errors.narration && <p className="text-xs text-red-500 mt-1">{errors.narration}</p>}
              </div>
            </div>
            {form.lines.map((line, i) => (
              <div key={i} className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3 items-center">
                <select value={line.account_code} onChange={e => { const l = [...form.lines]; l[i].account_code = e.target.value; setForm(p => ({ ...p, lines: l })) }}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select account...</option>
                  {accounts?.map(a => <option key={a.account_code} value={a.account_code}>{a.account_code} — {a.account_name}</option>)}
                </select>
                <select value={line.transaction_type} onChange={e => { const l = [...form.lines]; l[i].transaction_type = e.target.value; setForm(p => ({ ...p, lines: l })) }}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="debit">Debit</option>
                  <option value="credit">Credit</option>
                </select>
                <input type="number" step="0.01" value={line.amount} onChange={e => { const l = [...form.lines]; l[i].amount = e.target.value; setForm(p => ({ ...p, lines: l })) }}
                  placeholder="0.00" className={ic()} />
              </div>
            ))}
            <button onClick={() => setForm(p => ({ ...p, lines: [...p.lines, { account_code: '', transaction_type: 'debit', amount: '' }] }))}
              className="text-xs text-blue-600 hover:text-blue-700">+ Add line</button>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="text-sm">
                Debit: <span className="font-semibold">₹{totalDebit.toFixed(2)}</span> &nbsp;|&nbsp;
                Credit: <span className="font-semibold">₹{totalCredit.toFixed(2)}</span>
                {balanced ? <span className="text-success ml-2">✓ Balanced</span> : <span className="text-danger ml-2">✗ Not balanced</span>}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setShowNew(false)}>Cancel</Button>
                <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit} disabled={!balanced}>Post Entry</Button>
              </div>
            </div>
          </div>
        </div>
      )}
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : entries?.items?.length === 0 ? <Empty message="No journal entries" />
        : (
          <div className="overflow-x-auto">
            <table className="table min-w-[500px]">
              <thead><tr><th>Entry No.</th><th>Date</th><th>Narration</th><th>Lines</th></tr></thead>
              <tbody>
                {entries?.items?.map(e => (
                  <tr key={e.id}>
                    <td className="font-mono text-xs">{e.entry_number}</td>
                    <td className="text-xs text-gray-500">{e.entry_date ? format(new Date(e.entry_date), 'dd MMM yyyy') : '—'}</td>
                    <td className="text-sm text-gray-700">{e.narration}</td>
                    <td className="text-xs text-gray-400">{e.lines?.length || 0} lines</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// ─── Trial Balance ────────────────────────────────────────────
function TrialBalanceTab() {
  const now = new Date()
  const fyStartYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
  const curFy = `${fyStartYear}-${String(fyStartYear + 1).slice(2)}`
  const fyOptions = [0, 1, 2].map(n => { const y = fyStartYear - n; return `${y}-${String(y + 1).slice(2)}` })
  const [fy, setFy] = useState(curFy)
  const { data, isLoading } = useQuery({ queryKey: ['trial-balance', fy], queryFn: () => journalAPI.trialBalance({ financial_year: fy }).then(r => r.data) })
  return (
    <div>
      <div className="flex justify-end mb-4">
        <select value={fy} onChange={e => setFy(e.target.value)}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
          {fyOptions.map(f => <option key={f} value={f}>FY {f}</option>)}
        </select>
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : !data?.items?.length ? <Empty message="No data available" />
        : (
          <>
            <div className="overflow-x-auto">
              <table className="table min-w-[500px]">
                <thead><tr><th>Account Code</th><th>Account Name</th><th>Type</th><th className="text-right">Debit (₹)</th><th className="text-right">Credit (₹)</th></tr></thead>
                <tbody>
                  {data.items.map((a, i) => (
                    <tr key={i}>
                      <td className="font-mono text-xs">{a.account_code}</td>
                      <td className="font-medium text-sm">{a.account_name}</td>
                      <td><Badge color="gray">{a.account_type}</Badge></td>
                      <td className="text-right text-sm">{a.debit_total > 0 ? `₹${Number(a.debit_total).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}</td>
                      <td className="text-right text-sm text-success">{a.credit_total > 0 ? `₹${Number(a.credit_total).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}</td>
                    </tr>
                  ))}
                  <tr className="bg-gray-50 font-semibold">
                    <td colSpan={3}>Total</td>
                    <td className="text-right">₹{Number(data.total_debit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="text-right text-success">₹{Number(data.total_credit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            {Math.abs((data.total_debit || 0) - (data.total_credit || 0)) < 0.01
              ? <div className="text-center text-success text-sm mt-4 font-medium">✓ Trial Balance is balanced</div>
              : <div className="text-center text-danger text-sm mt-4">✗ Difference: ₹{Math.abs((data.total_debit || 0) - (data.total_credit || 0)).toFixed(2)}</div>}
          </>
        )}
    </div>
  )
}

// ─── Vendor Dues ──────────────────────────────────────────────
function VendorDuesTab() {
  const { data, isLoading } = useQuery({ queryKey: ['vendor-dues'], queryFn: () => vendorDueAPI.list().then(r => r.data) })
  return (
    <div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : data?.length === 0 ? <Empty message="No vendor dues" />
        : (
          <div className="overflow-x-auto">
            <table className="table min-w-[700px]">
              <thead><tr><th>Vendor</th><th>Purchase No.</th><th>Invoice Date</th><th>Due Date</th><th className="text-right">Total (₹)</th><th className="text-right">Paid (₹)</th><th className="text-right">Outstanding (₹)</th><th>Overdue</th></tr></thead>
              <tbody>
                {data?.map((d, i) => (
                  <tr key={i}>
                    <td className="font-medium">{d.vendor_name}</td>
                    <td className="font-mono text-xs">{d.purchase_number}</td>
                    <td className="text-xs text-gray-500">{d.invoice_date ? format(new Date(d.invoice_date), 'dd MMM yyyy') : '—'}</td>
                    <td className="text-xs text-gray-500">{d.payment_due_date ? format(new Date(d.payment_due_date), 'dd MMM yyyy') : '—'}</td>
                    <td className="text-right font-medium">₹{Number(d.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="text-right text-success">₹{Number(d.paid_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="text-right font-semibold text-danger">₹{Number(d.outstanding_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td><Badge color={d.is_overdue ? 'red' : d.payment_due_date ? 'green' : 'gray'}>{d.is_overdue ? `${d.overdue_days}d` : d.payment_due_date ? 'On time' : 'No due date'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────
export default function AccountingPage() {
  const [activeTab, setActiveTab] = useState('Cheque Register')
  return (
    <div>
      <div className="page-header">
        <div><div className="breadcrumb">Finance</div><h1 className="page-title">Accounting</h1></div>
      </div>
      <div className="flex border-b border-gray-200 mb-4 overflow-x-auto">
        {TABS.map(tab => (
          <button key={tab}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === tab ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700')}
            onClick={() => setActiveTab(tab)}>{tab}</button>
        ))}
      </div>
      <div className="card"><div className="p-4">
        {activeTab === 'Cheque Register' && <ChequeTab />}
        {activeTab === 'Cash Closing' && <CashClosingTab />}
        {activeTab === 'Expenses' && <ExpensesTab />}
        {activeTab === 'TDS' && <TDSTab />}
        {activeTab === 'Customer Ageing' && <AgeingTab />}
        {activeTab === 'Journal' && <JournalTab />}
        {activeTab === 'Trial Balance' && <TrialBalanceTab />}
        {activeTab === 'Vendor Dues' && <VendorDuesTab />}
      </div></div>
    </div>
  )
}
