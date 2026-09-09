import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { auditAPI } from '@/api/audit'
import { Badge, Input, Select, Field, Spinner, Empty, Pagination } from '@/components/ui'
import { ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react'
import { format } from 'date-fns'

const ACTION_COLORS = {
  create: 'green', update: 'blue', delete: 'red', cancel: 'red',
  void: 'red', reject: 'red', transfer: 'purple', adjustment: 'amber',
  writeoff: 'amber', approve: 'teal', payment: 'teal',
}

const MODULES = ['products', 'warehouse', 'purchase', 'billing', 'accounting', 'bank', 'gst']
const ACTIONS = ['create', 'update', 'delete', 'transfer', 'adjustment',
  'writeoff', 'approve', 'cancel', 'payment', 'void']

function parseJSON(s) {
  if (!s) return null
  try { return typeof s === 'string' ? JSON.parse(s) : s } catch { return null }
}

function fmtVal(v) {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  return String(v)
}

function ChangeDetail({ oldVals, newVals }) {
  const o = parseJSON(oldVals) || {}
  const n = parseJSON(newVals) || {}
  const keys = Array.from(new Set([...Object.keys(o), ...Object.keys(n)]))
  if (keys.length === 0) {
    return <div className="text-xs text-gray-400 italic px-2 py-1">No field-level detail recorded.</div>
  }
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-gray-400">
          <th className="text-left font-medium py-1 pr-4">Field</th>
          <th className="text-left font-medium py-1 pr-4">Old</th>
          <th className="text-left font-medium py-1">New</th>
        </tr>
      </thead>
      <tbody>
        {keys.map(k => (
          <tr key={k} className="border-t border-gray-100">
            <td className="py-1 pr-4 font-mono text-gray-600">{k}</td>
            <td className="py-1 pr-4 text-red-600">{fmtVal(o[k])}</td>
            <td className="py-1 text-green-700">{fmtVal(n[k])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Row({ log }) {
  const [open, setOpen] = useState(false)
  const hasDetail = !!(log.old_values || log.new_values)
  return (
    <>
      <tr className={hasDetail ? 'cursor-pointer hover:bg-gray-50' : ''} onClick={() => hasDetail && setOpen(o => !o)}>
        <td className="w-6 text-gray-300">
          {hasDetail && (open ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
        </td>
        <td className="text-gray-400 text-xs whitespace-nowrap">
          {log.created_at ? format(new Date(log.created_at), 'dd MMM yyyy HH:mm:ss') : '—'}
        </td>
        <td>
          <div className="text-sm font-medium">{log.full_name || '—'}</div>
          <div className="text-xs text-gray-400 font-mono">@{log.username || '—'}</div>
        </td>
        <td><Badge color={ACTION_COLORS[log.action] || 'gray'}>{log.action?.replace(/_/g, ' ')}</Badge></td>
        <td className="text-xs text-gray-500">{log.module || '—'}</td>
        <td className="text-sm text-gray-700">{log.details}</td>
      </tr>
      {open && hasDetail && (
        <tr>
          <td></td>
          <td colSpan={5} className="bg-gray-50 px-3 py-2">
            <ChangeDetail oldVals={log.old_values} newVals={log.new_values} />
          </td>
        </tr>
      )}
    </>
  )
}

export default function AuditLogPage() {
  const [page, setPage] = useState(1)
  const [module, setModule] = useState('')
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['audit-log', page, module, action, search, dateFrom, dateTo],
    queryFn: () => auditAPI.list({
      page, page_size: 30,
      module: module || undefined,
      action: action || undefined,
      search: search || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const reset = () => { setPage(1) }

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck size={20} className="text-blue-600" />
        <h1 className="text-xl font-bold text-gray-900">Audit Log</h1>
      </div>
      <p className="text-sm text-gray-400 mb-4">
        Every create, update, transfer and delete across the system — who did it and when.
      </p>

      <div className="flex items-end gap-3 mb-4 flex-wrap">
        <Field label="Module" className="mb-0">
          <Select value={module} onChange={e => { setModule(e.target.value); reset() }} className="w-40">
            <option value="">All modules</option>
            {MODULES.map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
        </Field>
        <Field label="Action" className="mb-0">
          <Select value={action} onChange={e => { setAction(e.target.value); reset() }} className="w-40">
            <option value="">All actions</option>
            {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
          </Select>
        </Field>
        <Field label="Search description" className="mb-0">
          <Input placeholder="e.g. price, vendor name…" value={search}
            onChange={e => { setSearch(e.target.value); reset() }} className="w-56" />
        </Field>
        <Field label="From" className="mb-0"><Input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); reset() }} className="w-40" /></Field>
        <Field label="To" className="mb-0"><Input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); reset() }} className="w-40" /></Field>
      </div>

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
        data?.items?.length === 0 ? <Empty message="No audit entries match these filters" /> : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th></th><th>Time</th><th>User</th><th>Action</th><th>Module</th><th>Description</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map(log => <Row key={log.id} log={log} />)}
              </tbody>
            </table>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={30} onChange={setPage} />}
          </>
        )}
    </div>
  )
}
