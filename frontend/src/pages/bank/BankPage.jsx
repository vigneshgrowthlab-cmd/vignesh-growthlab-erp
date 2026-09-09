import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { bankStmtAPI, bankReconAPI, notificationAPI, scheduledAPI, backupAPI } from '@/api/bank'
import { settingsAPI } from '@/api/settings'
import { Button, Badge, Field, Input, Select, AlertBox, Spinner, Empty } from '@/components/ui'
import { Plus, Lock, CheckCircle, X, Mail, Bell, Clock, Database, Link2, Unlink, Trash2, Upload } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'

const TABS = ['Bank Stock Statement', 'Bank Reconciliation', 'Notifications', 'Scheduled Reports', 'Backup Status']

// ── Bank Stock Statement Tab ──────────────────────────────────
function BankStatementTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const { register, handleSubmit, reset } = useForm({
    defaultValues: {
      statement_date: format(new Date(), 'yyyy-MM-dd'),
      bank_name: '', account_number: '', cc_limit: '', margin_percent: 25, notes: '',
    }
  })

  const { data: companySettings } = useQuery({
    queryKey: ['company-settings'],
    queryFn: () => settingsAPI.getCompany().then(r => r.data),
  })
  const bankMargin = Number(companySettings?.bank_stock_margin) || 25

  const openForm = () => {
    reset({
      statement_date: format(new Date(), 'yyyy-MM-dd'),
      bank_name: '', account_number: '', cc_limit: '', margin_percent: bankMargin, notes: '',
    })
    setShowForm(true)
  }

  const { data: statements, isLoading } = useQuery({
    queryKey: ['bank-statements'],
    queryFn: () => bankStmtAPI.list({ page_size: 20 }).then(r => r.data),
  })

  const { data: detail } = useQuery({
    queryKey: ['bank-statement', selectedId],
    queryFn: () => bankStmtAPI.get(selectedId).then(r => r.data),
    enabled: Boolean(selectedId),
  })

  const generateMutation = useMutation({
    mutationFn: (d) => bankStmtAPI.generate(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['bank-statements'])
      toast.success(`Statement ${res.data.statement_number} generated and locked`)
      setShowForm(false)
      reset()
      setSelectedId(res.data.id)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to generate'),
  })

  const onSubmit = (d) => generateMutation.mutate({
    statement_date: d.statement_date,
    bank_name: d.bank_name,
    account_number: d.account_number,
    cc_limit: d.cc_limit ? Number(d.cc_limit) : null,
    margin_percent: Number(d.margin_percent),
    notes: d.notes || null,
  })

  return (
    <div>
      <AlertBox type="info" className="mb-4">
        Bank stock statement is generated from live FIFO stock value + customer outstanding receivables as of the selected date. Once generated, it is permanently locked and cannot be edited.
      </AlertBox>

      <div className="flex justify-end mb-4">
        <Button variant="primary" size="sm" onClick={openForm}>
          <Plus size={14} /> Generate New Statement
        </Button>
      </div>

      {showForm && (
        <div className="card mb-4 border-2 border-primary/20">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">Generate Bank Stock Statement</h3>
            <button onClick={() => setShowForm(false)} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Field label="Statement Date" required hint="Stock and debtors calculated as of this date">
                <Input type="date" {...register('statement_date', { required: true })} />
              </Field>
              <Field label="Bank Name" required>
                <Input {...register('bank_name', { required: true })} placeholder="HDFC Bank" />
              </Field>
              <Field label="Account Number" required>
                <Input {...register('account_number', { required: true })} placeholder="CC Account No." />
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="CC Limit (₹)" hint="Your current CC limit sanctioned by bank">
                <Input type="number" step="0.01" {...register('cc_limit')} placeholder="Optional" />
              </Field>
              <Field label="Margin %" hint={`Default ${bankMargin}% — bank keeps this, you get the rest as drawing power`}>
                <Input type="number" step="0.01" {...register('margin_percent')} />
              </Field>
              <Field label="Notes">
                <Input {...register('notes')} placeholder="Optional notes" />
              </Field>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button variant="primary" loading={generateMutation.isPending} onClick={handleSubmit(onSubmit)}>
                Generate & Lock Statement
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {/* Statement list */}
        <div className="card col-span-1">
          <div className="card-header"><h3 className="font-semibold text-sm">Statement History</h3></div>
          {isLoading ? <div className="flex justify-center py-8"><Spinner size={20} /></div> :
            statements?.items?.length === 0 ? <div className="p-4 text-sm text-gray-400">No statements yet</div> : (
              <div className="divide-y divide-gray-50">
                {statements?.items?.map(stmt => (
                  <button key={stmt.id}
                    className={clsx('w-full text-left p-3 hover:bg-gray-50 transition-colors',
                      selectedId === stmt.id && 'bg-blue-50')}
                    onClick={() => setSelectedId(stmt.id)}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-xs font-semibold text-gray-700">{stmt.statement_number}</span>
                      <Lock size={11} className="text-gray-400" />
                    </div>
                    <div className="text-xs text-gray-500">{stmt.bank_name}</div>
                    <div className="text-xs text-gray-400">{stmt.statement_date ? format(new Date(stmt.statement_date), 'dd MMM yyyy') : '—'}</div>
                    <div className="text-xs font-medium text-primary mt-1">
                      DP: ₹{Number(stmt.drawing_power).toLocaleString('en-IN', { minimumFractionDigits: 0 })}
                    </div>
                  </button>
                ))}
              </div>
            )}
        </div>

        {/* Statement detail */}
        <div className="card col-span-2">
          {!selectedId ? (
            <div className="flex items-center justify-center h-48 text-sm text-gray-400">
              Select a statement from the list or generate a new one
            </div>
          ) : detail ? (
            <>
              <div className="card-header flex items-center justify-between">
                <h3 className="font-semibold">{detail.statement_number}</h3>
                <Badge color="green"><Lock size={10} className="mr-1" />Locked</Badge>
              </div>
              <div className="card-body">
                <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
                  <div><div className="text-xs text-gray-400">Bank</div><div className="font-medium">{detail.bank_name}</div></div>
                  <div><div className="text-xs text-gray-400">Account</div><div className="font-medium">{detail.account_number}</div></div>
                  <div><div className="text-xs text-gray-400">Statement Date</div><div className="font-medium">{detail.statement_date ? format(new Date(detail.statement_date), 'dd MMM yyyy') : '—'}</div></div>
                  <div><div className="text-xs text-gray-400">Generated By</div><div className="font-medium">{detail.generated_by_name || '—'}</div></div>
                </div>

                {/* Calculation summary */}
                <div className="border border-gray-200 rounded-lg p-4 mb-4 space-y-2">
                  {[
                    { label: 'Stock Value (FIFO)', val: detail.stock_value, color: 'text-gray-700' },
                    { label: 'Debtors (Outstanding)', val: detail.debtors_value, color: 'text-gray-700' },
                    { label: 'Total Value', val: detail.total_value, color: 'text-gray-800 font-semibold', border: true },
                    { label: `Less: Margin (${detail.margin_percent}%)`, val: Number(detail.total_value) * Number(detail.margin_percent) / 100, color: 'text-danger' },
                    { label: 'Drawing Power', val: detail.drawing_power, color: 'text-primary text-lg font-bold', border: true },
                  ].map(row => (
                    <div key={row.label} className={clsx('flex justify-between text-sm py-1', row.border && 'border-t border-gray-200 mt-2 pt-2')}>
                      <span className="text-gray-500">{row.label}</span>
                      <span className={row.color}>
                        ₹{Number(row.val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  ))}
                  {detail.cc_limit && (
                    <div className="flex justify-between text-sm pt-1">
                      <span className="text-gray-500">CC Limit Sanctioned</span>
                      <span className="text-gray-700">₹{Number(detail.cc_limit).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
                    </div>
                  )}
                </div>

                {/* Declaration */}
                <div className="bg-gray-50 rounded-lg p-3 mb-4">
                  <div className="text-xs text-gray-500 mb-1 font-medium">Declaration</div>
                  <div className="text-xs text-gray-600 italic leading-relaxed">{detail.declaration}</div>
                </div>

                {/* Stock breakup summary */}
                {detail.stock_breakup?.length > 0 && (
                  <div>
                    <div className="text-xs font-medium text-gray-500 mb-2">Stock Breakup ({detail.stock_breakup.length} items)</div>
                    <div className="max-h-36 overflow-y-auto">
                      <table className="table">
                        <thead><tr><th>Part Code</th><th>Product</th><th>Warehouse</th><th className="text-right">Qty</th><th className="text-right">Value (₹)</th></tr></thead>
                        <tbody>
                          {detail.stock_breakup.slice(0, 10).map((item, i) => (
                            <tr key={i}>
                              <td className="font-mono text-xs">{item.part_code}</td>
                              <td className="text-xs">{item.part_name}</td>
                              <td className="text-xs text-gray-500">{item.warehouse_name}</td>
                              <td className="text-right text-xs">{Number(item.quantity).toFixed(3)}</td>
                              <td className="text-right text-xs font-medium">₹{Number(item.value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</td>
                            </tr>
                          ))}
                          {detail.stock_breakup.length > 10 && (
                            <tr><td colSpan={5} className="text-center text-xs text-gray-400 py-2">... and {detail.stock_breakup.length - 10} more items</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : <div className="flex justify-center py-8"><Spinner size={20} /></div>}
        </div>
      </div>
    </div>
  )
}

// ── Bank Reconciliation Tab ───────────────────────────────────
const inr = (v) => `₹${Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

function CreateReconForm({ onCreated, onCancel }) {
  const qc = useQueryClient()
  const [accountCode, setAccountCode] = useState('BANK')
  const [periodFrom, setPeriodFrom] = useState(format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd'))
  const [periodTo, setPeriodTo] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [rows, setRows] = useState([{ entry_date: format(new Date(), 'yyyy-MM-dd'), description: '', debit: '', credit: '', reference: '' }])
  const [uploading, setUploading] = useState(false)

  const addRow = () => setRows(r => [...r, { entry_date: periodTo, description: '', debit: '', credit: '', reference: '' }])
  const removeRow = (i) => setRows(r => r.filter((_, idx) => idx !== i))
  const setCell = (i, k, v) => setRows(r => r.map((row, idx) => idx === i ? { ...row, [k]: v } : row))

  const createMut = useMutation({
    mutationFn: (d) => bankReconAPI.create(d),
    onSuccess: (res) => { qc.invalidateQueries(['recons']); toast.success(`${res.data.reconciliation_number} created`); onCreated(res.data.id) },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to create'),
  })

  const onUpload = async (file) => {
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await bankReconAPI.importFile(fd)
      const parsed = (res.data?.entries || []).map(e => ({
        entry_date: e.entry_date || periodTo, description: e.description || '',
        debit: e.debit || '', credit: e.credit || '', reference: e.reference || '',
      }))
      if (parsed.length) { setRows(parsed); toast.success(`${parsed.length} rows imported`) }
      else toast.error('No rows found in file')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Import failed')
    } finally { setUploading(false) }
  }

  const submit = () => {
    const entries = rows
      .filter(r => (Number(r.debit) || 0) > 0 || (Number(r.credit) || 0) > 0)
      .map(r => ({ entry_date: r.entry_date, description: r.description, debit: Number(r.debit) || 0, credit: Number(r.credit) || 0, reference: r.reference || null }))
    if (!entries.length) { toast.error('Add at least one entry with a debit or credit'); return }
    createMut.mutate({ account_code: accountCode, period_from: periodFrom, period_to: periodTo, entries })
  }

  return (
    <div className="card mb-4 border-2 border-primary/20">
      <div className="card-header flex justify-between">
        <h3 className="font-semibold">New Reconciliation</h3>
        <button onClick={onCancel} className="text-gray-400"><X size={16} /></button>
      </div>
      <div className="card-body space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Bank Account Code"><Input value={accountCode} onChange={e => setAccountCode(e.target.value)} placeholder="BANK" /></Field>
          <Field label="Period From"><Input type="date" value={periodFrom} onChange={e => setPeriodFrom(e.target.value)} /></Field>
          <Field label="Period To"><Input type="date" value={periodTo} onChange={e => setPeriodTo(e.target.value)} /></Field>
        </div>

        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-gray-600">Bank Statement Entries <span className="text-xs text-gray-400">(debit = money out, credit = money in)</span></div>
          <div className="flex gap-2 items-center">
            <label className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer">
              <Upload size={14} /> {uploading ? 'Importing…' : 'Upload CSV/Excel'}
              <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={e => onUpload(e.target.files?.[0])} />
            </label>
            <Button variant="secondary" size="sm" onClick={addRow}><Plus size={14} /> Add Row</Button>
          </div>
        </div>

        <div className="max-h-64 overflow-y-auto">
          <table className="table">
            <thead><tr><th>Date</th><th>Description</th><th className="text-right">Debit (out)</th><th className="text-right">Credit (in)</th><th>Reference</th><th></th></tr></thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  <td><Input type="date" value={row.entry_date} onChange={e => setCell(i, 'entry_date', e.target.value)} className="w-36" /></td>
                  <td><Input value={row.description} onChange={e => setCell(i, 'description', e.target.value)} placeholder="Narration" /></td>
                  <td><Input type="number" step="0.01" value={row.debit} onChange={e => setCell(i, 'debit', e.target.value)} className="w-28 text-right" /></td>
                  <td><Input type="number" step="0.01" value={row.credit} onChange={e => setCell(i, 'credit', e.target.value)} className="w-28 text-right" /></td>
                  <td><Input value={row.reference} onChange={e => setCell(i, 'reference', e.target.value)} placeholder="UTR / Chq" className="w-32" /></td>
                  <td><button onClick={() => removeRow(i)} className="text-gray-400 hover:text-danger"><Trash2 size={14} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex gap-2 justify-end">
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          <Button variant="primary" loading={createMut.isPending} onClick={submit}>Create & Auto-Match</Button>
        </div>
      </div>
    </div>
  )
}

function BankReconTab() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [activeLineId, setActiveLineId] = useState(null)
  const [showAdj, setShowAdj] = useState(false)
  const [adj, setAdj] = useState({ kind: 'charge', amount: '', narration: '' })

  const { data: recons } = useQuery({ queryKey: ['recons'], queryFn: () => bankReconAPI.list({ page_size: 50 }).then(r => r.data) })
  const { data: detail, isLoading } = useQuery({
    queryKey: ['recon', selectedId],
    queryFn: () => bankReconAPI.get(selectedId).then(r => r.data),
    enabled: Boolean(selectedId),
  })

  const refresh = () => { qc.invalidateQueries(['recon', selectedId]); qc.invalidateQueries(['recons']) }

  const matchMut = useMutation({ mutationFn: (d) => bankReconAPI.match(selectedId, d), onSuccess: () => { refresh(); setActiveLineId(null); toast.success('Matched') }, onError: e => toast.error(e.response?.data?.detail || 'Match failed') })
  const unmatchMut = useMutation({ mutationFn: (d) => bankReconAPI.unmatch(selectedId, d), onSuccess: () => { refresh(); toast.success('Unmatched') }, onError: e => toast.error(e.response?.data?.detail || 'Failed') })
  const adjMut = useMutation({ mutationFn: (d) => bankReconAPI.adjustment(selectedId, d), onSuccess: () => { refresh(); setShowAdj(false); setAdj({ kind: 'charge', amount: '', narration: '' }); toast.success('Adjustment posted') }, onError: e => toast.error(e.response?.data?.detail || 'Failed') })
  const finalizeMut = useMutation({ mutationFn: () => bankReconAPI.finalize(selectedId), onSuccess: () => { refresh(); toast.success('Reconciliation finalized & locked') }, onError: e => toast.error(e.response?.data?.detail || 'Failed') })

  const isDraft = detail?.status === 'draft'
  const balanced = detail && Math.abs(Number(detail.difference)) < 1
  const unmatchedBank = (detail?.lines || []).filter(l => !l.journal_line_id)
  const matchedLines = (detail?.lines || []).filter(l => l.journal_line_id)

  const activeLine = unmatchedBank.find(l => l.id === activeLineId)
  const books = [...(detail?.unmatched_in_books || [])]
  if (activeLine) {
    const amt = activeLine.bank_credit > 0 ? activeLine.bank_credit : activeLine.bank_debit
    books.sort((a, b) => Math.abs(a.amount - amt) - Math.abs(b.amount - amt))
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4 gap-3">
        <AlertBox type="info" className="flex-1">
          Create a reconciliation for a period, auto-match against your bank-account books, then manually match or adjust the rest. Finalize to lock it with a full audit trail.
        </AlertBox>
        <Button variant="primary" size="sm" onClick={() => setShowCreate(true)}><Plus size={14} /> New Reconciliation</Button>
      </div>

      {showCreate && <CreateReconForm onCreated={(id) => { setShowCreate(false); setSelectedId(id); setActiveLineId(null) }} onCancel={() => setShowCreate(false)} />}

      <div className="grid grid-cols-4 gap-4">
        <div className="card col-span-1">
          <div className="card-header"><h3 className="font-semibold text-sm">History</h3></div>
          {recons?.items?.length ? (
            <div className="divide-y divide-gray-50">
              {recons.items.map(r => (
                <button key={r.id} onClick={() => { setSelectedId(r.id); setActiveLineId(null) }}
                  className={clsx('w-full text-left p-3 hover:bg-gray-50', selectedId === r.id && 'bg-blue-50')}>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold">{r.reconciliation_number}</span>
                    <Badge color={r.status === 'locked' ? 'gray' : 'green'}>{r.status}</Badge>
                  </div>
                  <div className="text-xs text-gray-500">{r.account_code} • {r.period_to ? format(new Date(r.period_to), 'dd MMM yyyy') : ''}</div>
                  <div className={clsx('text-xs font-medium mt-1', Math.abs(Number(r.difference)) < 1 ? 'text-success' : 'text-danger')}>Diff: {inr(r.difference)}</div>
                </button>
              ))}
            </div>
          ) : <div className="p-4 text-sm text-gray-400">No reconciliations yet</div>}
        </div>

        <div className="col-span-3">
          {!selectedId ? (
            <div className="card flex items-center justify-center h-48 text-sm text-gray-400">Select or create a reconciliation</div>
          ) : isLoading || !detail ? (
            <div className="card flex justify-center py-8"><Spinner size={20} /></div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                <div className="stat-card"><div className="stat-label">Statement (period)</div><div className="stat-value text-sm">{inr(detail.statement_closing_balance)}</div></div>
                <div className="stat-card"><div className="stat-label">Books (period)</div><div className="stat-value text-sm">{inr(detail.books_closing_balance)}</div></div>
                <div className="stat-card"><div className="stat-label">Difference</div><div className={clsx('stat-value text-sm', balanced ? 'text-success' : 'text-danger')}>{inr(detail.difference)}</div></div>
                <div className="stat-card"><div className="stat-label">Matched</div><div className="stat-value text-sm">{detail.matched_count}/{detail.lines.length}</div></div>
              </div>

              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-500 flex items-center gap-2">
                  <span>{detail.reconciliation_number}</span>
                  <Badge color={detail.status === 'locked' ? 'gray' : 'green'}>{detail.status}</Badge>
                  {detail.status === 'locked' && detail.finalized_by_name && <span className="text-xs">Locked by {detail.finalized_by_name}</span>}
                </div>
                {isDraft && (
                  <div className="flex gap-2">
                    <Button variant="secondary" size="sm" onClick={() => setShowAdj(s => !s)}>Add Charge / Interest</Button>
                    <Button variant="primary" size="sm" disabled={!balanced} loading={finalizeMut.isPending} onClick={() => finalizeMut.mutate()}>
                      <Lock size={14} /> Finalize &amp; Lock
                    </Button>
                  </div>
                )}
              </div>
              {isDraft && !balanced && <div className="text-xs text-amber-600">Difference must be ₹0 to finalize — match remaining entries or post adjustments for bank-only items.</div>}

              {showAdj && isDraft && (
                <div className="card border border-amber-200">
                  <div className="card-body grid grid-cols-4 gap-3 items-end">
                    <Field label="Type">
                      <Select value={adj.kind} onChange={e => setAdj({ ...adj, kind: e.target.value })}>
                        <option value="charge">Bank Charge (out)</option>
                        <option value="interest">Interest (in)</option>
                      </Select>
                    </Field>
                    <Field label="Amount"><Input type="number" step="0.01" value={adj.amount} onChange={e => setAdj({ ...adj, amount: e.target.value })} /></Field>
                    <Field label="Narration"><Input value={adj.narration} onChange={e => setAdj({ ...adj, narration: e.target.value })} placeholder="Optional" /></Field>
                    <Button variant="primary" loading={adjMut.isPending}
                      onClick={() => { if (!(Number(adj.amount) > 0)) { toast.error('Enter an amount'); return } adjMut.mutate({ kind: adj.kind, amount: Number(adj.amount), narration: adj.narration || null, line_id: activeLine?.id || null }) }}>
                      Post
                    </Button>
                  </div>
                  {activeLine && <div className="px-4 pb-3 text-xs text-gray-500">Will be linked to selected bank entry: “{activeLine.bank_description}”.</div>}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="card">
                  <div className="card-header"><h3 className="font-semibold text-sm text-danger">Bank — Unmatched ({unmatchedBank.length})</h3></div>
                  <div className="max-h-80 overflow-y-auto divide-y divide-gray-50">
                    {unmatchedBank.length === 0 ? <div className="p-3 text-xs text-gray-400">All bank entries matched</div> :
                      unmatchedBank.map(l => (
                        <button key={l.id} disabled={!isDraft} onClick={() => setActiveLineId(l.id)}
                          className={clsx('w-full text-left p-2.5 text-sm', activeLineId === l.id ? 'bg-blue-50 ring-1 ring-primary/40' : 'hover:bg-gray-50', !isDraft && 'cursor-default')}>
                          <div className="flex justify-between gap-2">
                            <span className="truncate">{l.bank_description}</span>
                            <span className={l.bank_credit > 0 ? 'text-success' : 'text-danger'}>{inr(l.bank_credit > 0 ? l.bank_credit : l.bank_debit)}</span>
                          </div>
                          <div className="text-xs text-gray-400">{l.bank_date}{l.bank_reference ? ` • ${l.bank_reference}` : ''}</div>
                        </button>
                      ))}
                  </div>
                </div>

                <div className="card">
                  <div className="card-header"><h3 className="font-semibold text-sm text-warning">Books — Unmatched ({books.length})</h3></div>
                  {isDraft && !activeLine && <div className="px-3 pt-2 text-xs text-gray-400">Select a bank entry on the left, then click a book entry here to match.</div>}
                  <div className="max-h-80 overflow-y-auto divide-y divide-gray-50">
                    {books.length === 0 ? <div className="p-3 text-xs text-gray-400">No unmatched book entries</div> :
                      books.map(be => (
                        <button key={be.journal_line_id} disabled={!isDraft || !activeLine}
                          onClick={() => matchMut.mutate({ line_id: activeLine.id, journal_line_id: be.journal_line_id })}
                          className={clsx('w-full text-left p-2.5 text-sm', (isDraft && activeLine) ? 'hover:bg-green-50' : 'cursor-default opacity-70')}>
                          <div className="flex justify-between gap-2">
                            <span className="truncate">{be.narration || be.entry_number}</span>
                            <span>{inr(be.amount)}</span>
                          </div>
                          <div className="text-xs text-gray-400">{be.date} • {be.direction === 'debit' ? 'in' : 'out'}{be.entry_number ? ` • ${be.entry_number}` : ''}</div>
                        </button>
                      ))}
                  </div>
                </div>
              </div>

              {matchedLines.length > 0 && (
                <div className="card">
                  <div className="card-header"><h3 className="font-semibold text-sm text-success">Matched ({matchedLines.length})</h3></div>
                  <table className="table">
                    <thead><tr><th>Bank Entry</th><th>Date</th><th className="text-right">Amount</th><th>Book Entry</th><th>Type</th><th>By</th>{isDraft && <th></th>}</tr></thead>
                    <tbody>
                      {matchedLines.map(l => (
                        <tr key={l.id}>
                          <td className="text-sm">{l.bank_description}</td>
                          <td className="text-xs text-gray-500">{l.bank_date}</td>
                          <td className="text-right font-medium">{inr(l.bank_credit > 0 ? l.bank_credit : l.bank_debit)}</td>
                          <td className="text-sm text-gray-600">{l.matched_book_entry?.narration || l.matched_book_entry?.entry_number || '—'}</td>
                          <td><Badge color={l.match_type === 'auto' ? 'green' : l.match_type === 'adjustment' ? 'amber' : 'blue'}>{l.match_type}</Badge></td>
                          <td className="text-xs text-gray-500">{l.matched_by_name || '—'}</td>
                          {isDraft && <td>{!l.is_adjustment && <button onClick={() => unmatchMut.mutate({ line_id: l.id })} className="text-gray-400 hover:text-danger" title="Unmatch"><Unlink size={14} /></button>}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Notifications Tab ─────────────────────────────────────────
function NotificationsTab() {
  const qc = useQueryClient()
  const [testEmail, setTestEmail] = useState('')
  const { data: settings, isLoading } = useQuery({ queryKey: ['notif-settings'], queryFn: () => notificationAPI.getSettings().then(r => r.data) })
  const { register, handleSubmit, reset } = useForm()

  const updateMutation = useMutation({
    mutationFn: (d) => notificationAPI.updateSettings(d),
    onSuccess: () => { qc.invalidateQueries(['notif-settings']); toast.success('Notification settings saved') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to save'),
  })

  const testMutation = useMutation({
    mutationFn: () => notificationAPI.testEmail(testEmail),
    onSuccess: (res) => {
      if (res.data.success) toast.success(res.data.message)
      else toast.error(res.data.message)
    },
  })

  if (isLoading) return <div className="flex justify-center py-8"><Spinner size={24} /></div>

  return (
    <div className="max-w-2xl space-y-6">
      <div className="card">
        <div className="card-header"><h3 className="font-semibold">SMTP Configuration</h3></div>
        <div className="card-body space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="SMTP Host"><Input defaultValue={settings?.smtp_host} {...register('smtp_host')} placeholder="smtp.gmail.com" /></Field>
            <Field label="SMTP Port"><Input type="number" defaultValue={settings?.smtp_port} {...register('smtp_port')} placeholder="587" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Username"><Input defaultValue={settings?.smtp_username} {...register('smtp_username')} placeholder="your@gmail.com" /></Field>
            <Field label="Password"><Input type="password" defaultValue={settings?.smtp_password} {...register('smtp_password')} placeholder="App password" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="From Email"><Input defaultValue={settings?.smtp_from_email} {...register('smtp_from_email')} placeholder="erp@company.com" /></Field>
            <Field label="Admin Email"><Input defaultValue={settings?.admin_email} {...register('admin_email')} placeholder="admin@company.com" /></Field>
          </div>
          <Field label="Accountant Email"><Input defaultValue={settings?.accountant_email} {...register('accountant_email')} placeholder="accountant@company.com" /></Field>
          <Button variant="primary" onClick={handleSubmit(d => updateMutation.mutate(d))}>Save SMTP Settings</Button>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3 className="font-semibold">Email Triggers</h3></div>
        <div className="card-body space-y-3">
          {[
            { key: 'notify_overdue', label: 'Customer payment overdue' },
            { key: 'notify_low_stock', label: 'Stock below reorder threshold' },
            { key: 'notify_large_invoice', label: 'Large invoice created (above threshold)' },
            { key: 'notify_einvoice_failure', label: 'E-Invoice generation failure' },
            { key: 'notify_cheque_bounce', label: 'Cheque bounced' },
            { key: 'notify_daily_summary', label: 'Daily sales summary (every morning)' },
            { key: 'notify_unknown_ip', label: 'Login from unknown device or IP' },
            { key: 'notify_vendor_due', label: 'Vendor payment due in 3 days' },
            { key: 'notify_backup', label: 'Backup success or failure' },
          ].map(item => (
            <label key={item.key} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
              <span className="text-sm text-gray-700">{item.label}</span>
              <input type="checkbox" defaultChecked={settings?.[item.key]} {...register(item.key)} className="rounded" />
            </label>
          ))}
          <Button variant="primary" onClick={handleSubmit(d => updateMutation.mutate(d))}>Save Trigger Settings</Button>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3 className="font-semibold">Test Email</h3></div>
        <div className="card-body">
          <div className="flex gap-2">
            <Input value={testEmail} onChange={e => setTestEmail(e.target.value)} placeholder="test@example.com" className="flex-1" />
            <Button variant="secondary" loading={testMutation.isPending} onClick={() => testMutation.mutate()}>
              <Mail size={14} /> Send Test
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Scheduled Reports Tab ─────────────────────────────────────
function ScheduledReportsTab() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({ queryKey: ['scheduled-settings'], queryFn: () => scheduledAPI.getSettings().then(r => r.data) })
  const { register, handleSubmit } = useForm()

  const updateMutation = useMutation({
    mutationFn: (d) => scheduledAPI.updateSettings(d),
    onSuccess: () => { qc.invalidateQueries(['scheduled-settings']); toast.success('Scheduled report settings saved') },
  })

  if (isLoading) return <div className="flex justify-center py-8"><Spinner size={24} /></div>

  const reports = [
    { key: 'daily_sales_enabled', label: 'Daily Sales Summary', freq: 'Every morning' },
    { key: 'weekly_outstanding_enabled', label: 'Weekly Outstanding Payments', freq: 'Every Monday' },
    { key: 'monthly_pnl_enabled', label: 'Monthly P&L Statement', freq: '1st of each month' },
    { key: 'monthly_stock_enabled', label: 'Monthly Stock Report', freq: '1st of each month' },
    { key: 'monthly_gst_enabled', label: 'Monthly GST Summary', freq: '1st of each month' },
    { key: 'monthly_bank_statement_reminder', label: 'Bank Statement Reminder', freq: '25th of each month' },
  ]

  return (
    <div className="max-w-2xl space-y-4">
      <div className="card">
        <div className="card-header"><h3 className="font-semibold">Scheduled Reports</h3></div>
        <div className="card-body space-y-3">
          {reports.map(r => (
            <div key={r.key} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
              <div>
                <div className="text-sm font-medium text-gray-700">{r.label}</div>
                <div className="text-xs text-gray-400"><Clock size={10} className="inline mr-1" />{r.freq}</div>
              </div>
              <input type="checkbox" defaultChecked={settings?.[r.key]} {...register(r.key)} className="rounded" />
            </div>
          ))}
          <Field label="Daily Report Time">
            <Input type="time" defaultValue={settings?.daily_sales_time || '08:00'} {...register('daily_sales_time')} className="w-36" />
          </Field>
          <Field label="Recipient Emails" hint="Comma-separated email addresses">
            <Input defaultValue={settings?.recipient_emails?.join(', ')} {...register('recipient_emails_raw')} placeholder="admin@company.com, manager@company.com" />
          </Field>
          <Button variant="primary" onClick={handleSubmit(d => {
            const emails = d.recipient_emails_raw ? d.recipient_emails_raw.split(',').map(e => e.trim()).filter(Boolean) : []
            const { recipient_emails_raw, ...rest } = d
            updateMutation.mutate({ ...rest, recipient_emails: emails })
          })}>
            Save Scheduled Report Settings
          </Button>
        </div>
      </div>
      <AlertBox type="info">
        Scheduled reports are sent via Celery background workers. Ensure Redis is running and the Celery worker is started with: <code className="bg-gray-100 px-1 rounded">celery -A app.celery worker --loglevel=info</code>
      </AlertBox>
    </div>
  )
}

// ── Backup Status Tab ─────────────────────────────────────────
function BackupStatusTab() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['backup-status'],
    queryFn: () => backupAPI.status().then(r => r.data),
  })

  return (
    <div className="max-w-2xl">
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> : status && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="stat-card">
              <div className="stat-label">Last Backup</div>
              <div className="stat-value text-sm">{status.last_backup_time ? format(new Date(status.last_backup_time), 'dd MMM HH:mm') : 'No backups'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Status</div>
              <Badge color={status.last_backup_status === 'success' ? 'green' : status.last_backup_status === 'no_backups_found' ? 'amber' : 'red'}>
                {status.last_backup_status}
              </Badge>
            </div>
            <div className="stat-card">
              <div className="stat-label">Backups (30 days)</div>
              <div className="stat-value">{status.backup_count_last_30_days}</div>
            </div>
          </div>

          <AlertBox type={status.backup_count_last_30_days === 0 ? 'warning' : 'info'} className="mb-4">
            {status.note}
          </AlertBox>

          <div className="card">
            <div className="card-header"><h3 className="font-semibold text-sm">Backup Script</h3></div>
            <div className="card-body">
              <div className="text-xs text-gray-500 mb-2">Add this to your crontab (Linux) to backup daily at 2am:</div>
              <code className="block bg-gray-900 text-green-400 text-xs p-3 rounded-lg whitespace-pre">
{`# Edit crontab: crontab -e
0 2 * * * /usr/bin/mysqldump -u erp_user -perp_password wholesale_erp | gzip > /var/backups/wholesale_erp/backup_$(date +\\%Y\\%m\\%d).sql.gz`}
              </code>
              <div className="text-xs text-gray-500 mt-3 mb-2">Windows Task Scheduler batch script:</div>
              <code className="block bg-gray-900 text-green-400 text-xs p-3 rounded-lg whitespace-pre">
{`REM backup.bat
"C:\\Program Files\\MariaDB 11.4\\bin\\mysqldump.exe" -u erp_user -perp_password wholesale_erp > C:\\backups\\backup_%date:~-4,4%%date:~-7,2%%date:~-10,2%.sql`}
              </code>
            </div>
          </div>

          {status.backups?.length > 0 && (
            <div className="card mt-4">
              <div className="card-header"><h3 className="font-semibold text-sm">Recent Backups</h3></div>
              <table className="table">
                <thead><tr><th>Filename</th><th>Size</th><th>Created</th><th>Status</th></tr></thead>
                <tbody>
                  {status.backups.slice(0, 10).map((b, i) => (
                    <tr key={i}>
                      <td className="font-mono text-xs">{b.filename}</td>
                      <td className="text-sm">{b.size_mb} MB</td>
                      <td className="text-gray-500 text-xs">{format(new Date(b.created_at), 'dd MMM yyyy HH:mm')}</td>
                      <td><Badge color="green">{b.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Main Bank Page ────────────────────────────────────────────
export default function BankPage() {
  const [activeTab, setActiveTab] = useState('Bank Stock Statement')
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Bank & Notifications</div>
          <h1 className="page-title">Bank Stock Statement & Settings</h1>
        </div>
      </div>
      <div className="flex border-b border-gray-200 mb-4 overflow-x-auto">
        {TABS.map(tab => (
          <button key={tab}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700')}
            onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
      </div>
      <div className="card"><div className="p-4">
        {activeTab === 'Bank Stock Statement' && <BankStatementTab />}
        {activeTab === 'Bank Reconciliation' && <BankReconTab />}
        {activeTab === 'Notifications' && <NotificationsTab />}
        {activeTab === 'Scheduled Reports' && <ScheduledReportsTab />}
        {activeTab === 'Backup Status' && <BackupStatusTab />}
      </div></div>
    </div>
  )
}
