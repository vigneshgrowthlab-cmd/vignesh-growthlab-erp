import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configAPI } from '@/api/config'
import {
  Button, Input, Field, Badge, Spinner, Empty, Modal, Textarea,
  Table, Thead, Th, Tbody, Tr, Td,
} from '@/components/ui'
import { Sliders, Clock, History, Plus, CheckCircle, Ban, CalendarX } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'

const DOMAINS = ['GST', 'INCOME_TAX', 'RBI', 'DPDP', 'COMPANY', 'BUSINESS']

const STATUS_COLOR = {
  active: 'green', draft: 'gray', scheduled: 'blue',
  superseded: 'amber', expired: 'gray', revoked: 'red',
}

function fmtDate(d) { return d ? String(d).slice(0, 10) : '—' }

export default function ConfigAdminPage() {
  const qc = useQueryClient()
  const [domain, setDomain] = useState('GST')
  const [selected, setSelected] = useState(null)   // definition object
  const [showPropose, setShowPropose] = useState(false)

  const defsQ = useQuery({
    queryKey: ['config-defs', domain],
    queryFn: () => configAPI.listDefinitions(domain).then(r => r.data),
  })

  const valuesQ = useQuery({
    queryKey: ['config-values', selected?.config_key],
    queryFn: () => configAPI.listValues(selected.config_key).then(r => r.data),
    enabled: !!selected,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['config-values', selected?.config_key] })
    qc.invalidateQueries({ queryKey: ['config-defs'] })
  }

  const act = (fn, label) => useMutation({
    mutationFn: fn,
    onSuccess: () => { toast.success(label); invalidate() },
    onError: (e) => toast.error(e.response?.data?.detail || `${label} failed`),
  })

  const activateM = act((id) => configAPI.activate(id), 'Activated')
  const revokeM   = act((id) => configAPI.revoke(id), 'Revoked')
  const expireM   = act(({ id, to }) => configAPI.expire(id, to), 'Expired')

  const schedulerM = useMutation({
    mutationFn: () => configAPI.runScheduler(),
    onSuccess: (r) => { toast.success(`Scheduler: ${r.data.activated} activated`); invalidate() },
    onError: (e) => toast.error(e.response?.data?.detail || 'Scheduler failed'),
  })

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sliders className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-semibold text-gray-800">Configuration</h1>
        </div>
        <Button variant="secondary" onClick={() => schedulerM.mutate()} disabled={schedulerM.isPending}>
          <Clock className="w-4 h-4 mr-1" /> Run scheduler
        </Button>
      </div>

      {/* Domain pills */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {DOMAINS.map(d => (
          <button key={d} onClick={() => { setDomain(d); setSelected(null) }}
            className={clsx('px-3 py-1 rounded-full text-xs font-medium',
              domain === d ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
            {d}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Definitions list */}
        <div className="bg-white rounded-xl border border-gray-200 p-2 lg:col-span-1 h-fit">
          {defsQ.isLoading ? <div className="p-6 flex justify-center"><Spinner /></div>
            : !defsQ.data?.length ? <Empty message="No parameters in this domain" />
            : defsQ.data.map(d => (
              <button key={d.config_key} onClick={() => setSelected(d)}
                className={clsx('w-full text-left px-3 py-2 rounded-lg mb-0.5',
                  selected?.config_key === d.config_key ? 'bg-blue-50 ring-1 ring-blue-200' : 'hover:bg-gray-50')}>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-gray-800">{d.config_key}</span>
                  {d.is_regulatory && <Badge color="amber">regulatory</Badge>}
                </div>
                <div className="text-xs text-gray-500 truncate">{d.description}</div>
              </button>
            ))}
        </div>

        {/* Detail + history */}
        <div className="lg:col-span-2">
          {!selected ? (
            <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400 text-sm">
              Select a parameter to view its value history.
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h2 className="text-base font-semibold text-gray-800">{selected.config_key}</h2>
                  <p className="text-xs text-gray-500">{selected.description}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    type: <b>{selected.data_type}</b>{selected.unit ? ` · unit: ${selected.unit}` : ''} · domain: {selected.domain}
                  </p>
                </div>
                <Button onClick={() => setShowPropose(true)}>
                  <Plus className="w-4 h-4 mr-1" /> Propose change
                </Button>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
                <History className="w-3.5 h-3.5" /> Value history
              </div>
              {valuesQ.isLoading ? <div className="p-6 flex justify-center"><Spinner /></div>
                : !valuesQ.data?.length ? <Empty message="No values yet" />
                : (
                  <Table>
                    <Thead><Tr>
                      <Th>Value</Th><Th>Effective</Th><Th>Status</Th><Th>v</Th><Th>Reference</Th><Th className="text-right">Actions</Th>
                    </Tr></Thead>
                    <Tbody>
                      {valuesQ.data.map(v => (
                        <Tr key={v.id}>
                          <Td className="font-medium">{String(v.value)}</Td>
                          <Td className="text-xs">{fmtDate(v.effective_from)} → {fmtDate(v.effective_to)}</Td>
                          <Td><Badge color={STATUS_COLOR[v.status] || 'gray'}>{v.status}</Badge></Td>
                          <Td className="text-xs text-gray-500">{v.version}</Td>
                          <Td className="text-xs text-gray-500">{v.regulatory_reference || '—'}</Td>
                          <Td className="text-right whitespace-nowrap">
                            {(v.status === 'draft' || v.status === 'scheduled') && (
                              <button title="Activate" onClick={() => activateM.mutate(v.id)}
                                className="text-green-600 hover:text-green-800 p-1"><CheckCircle className="w-4 h-4" /></button>
                            )}
                            {v.status === 'active' && (
                              <button title="Expire today" onClick={() => {
                                const to = new Date().toISOString().slice(0, 10)
                                expireM.mutate({ id: v.id, to })
                              }} className="text-amber-600 hover:text-amber-800 p-1"><CalendarX className="w-4 h-4" /></button>
                            )}
                            {v.status !== 'revoked' && (
                              <button title="Revoke" onClick={() => revokeM.mutate(v.id)}
                                className="text-red-500 hover:text-red-700 p-1"><Ban className="w-4 h-4" /></button>
                            )}
                          </Td>
                        </Tr>
                      ))}
                    </Tbody>
                  </Table>
                )}
            </div>
          )}
        </div>
      </div>

      {showPropose && selected && (
        <ProposeModal definition={selected} onClose={() => setShowPropose(false)}
          onDone={() => { setShowPropose(false); invalidate() }} />
      )}
    </div>
  )
}

function ProposeModal({ definition, onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10)
  const [value, setValue] = useState('')
  const [effFrom, setEffFrom] = useState(today)
  const [ref, setRef] = useState('')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('draft')

  const m = useMutation({
    mutationFn: () => configAPI.propose({
      config_key: definition.config_key, value, effective_from: effFrom,
      status, regulatory_reference: ref || null, note: note || null,
    }),
    onSuccess: () => { toast.success('Proposed (draft) — activate it to apply'); onDone() },
    onError: (e) => toast.error(e.response?.data?.detail || 'Propose failed'),
  })

  return (
    <Modal title={`Propose change — ${definition.config_key}`} onClose={onClose}>
      <div className="space-y-3">
        <Field label={`New value (${definition.data_type}${definition.unit ? ', ' + definition.unit : ''})`} required>
          <Input value={value} onChange={e => setValue(e.target.value)} placeholder="e.g. 75000" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Effective from" required>
            <Input type="date" value={effFrom} onChange={e => setEffFrom(e.target.value)} />
          </Field>
          <Field label="Stage as">
            <select value={status} onChange={e => setStatus(e.target.value)}
              className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm">
              <option value="draft">Draft (activate manually)</option>
              <option value="scheduled">Scheduled (auto-activate on date)</option>
            </select>
          </Field>
        </div>
        <Field label="Regulatory reference">
          <Input value={ref} onChange={e => setRef(e.target.value)} placeholder="Notification / circular no." />
        </Field>
        <Field label="Note">
          <Textarea rows={2} value={note} onChange={e => setNote(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => m.mutate()} disabled={!value || m.isPending}>Propose</Button>
        </div>
      </div>
    </Modal>
  )
}
