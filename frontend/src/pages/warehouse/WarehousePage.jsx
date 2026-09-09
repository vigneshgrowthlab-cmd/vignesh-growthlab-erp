import { useState, useEffect, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { warehouseAPI, transferAPI, adjustmentAPI, writeoffAPI } from '@/api/warehouse'
import { settingsAPI } from '@/api/settings'
import { invoiceAPI } from '@/api/billing'
import { productAPI } from '@/api'
import { Button, Badge, Input, Select, Field, AlertBox, Spinner, Empty } from '@/components/ui'
import { Plus, ArrowRightLeft, AlertTriangle, ChevronDown, ChevronRight, Search, X, CheckCircle, XCircle } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'

const TABS = ['Stock', 'Transfers', 'Adjustments', 'Write-offs', 'Ageing']

const ic = (err) => clsx(
  'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
  err ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
)

// ── Product Search Component ──────────────────────────────────
function ProductSearchInput({ value, onSelect, placeholder = 'Search product...' }) {
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [showResults, setShowResults] = useState(false)

  const doSearch = async (q) => {
    setSearch(q)
    if (q.length < 2) { setResults([]); return }
    try {
      const { data } = await productAPI.list({ search: q, page_size: 10 })
      setResults(data.items || [])
      setShowResults(true)
    } catch { }
  }

  const handleSelect = (p) => {
    setSearch(`${p.part_code} — ${p.part_name}`)
    setResults([])
    setShowResults(false)
    onSelect(p)
  }

  return (
    <div className="relative">
      <input
        value={value ? `${value.part_code} — ${value.part_name}` : search}
        onChange={e => { if (value) onSelect(null); doSearch(e.target.value) }}
        placeholder={placeholder}
        className={ic(!value && search.length > 0 && results.length === 0 ? false : false)}
      />
      {showResults && results.length > 0 && !value && (
        <div className="absolute z-20 left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-xl mt-1 max-h-48 overflow-y-auto">
          {results.map(p => (
            <button key={p.id} type="button"
              className="w-full text-left px-3 py-2 hover:bg-gray-50 text-sm"
              onClick={() => handleSelect(p)}>
              <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded mr-2">{p.part_code}</span>
              {p.part_name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Stock Tab ─────────────────────────────────────────────────
function StockTab({ warehouses }) {
  const [search, setSearch] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [expanded, setExpanded] = useState({})

  const { data: stock, isLoading } = useQuery({
    queryKey: ['warehouse-stock', search, warehouseId, lowStockOnly],
    queryFn: () => warehouseAPI.stock({ search: search || undefined, warehouse_id: warehouseId || undefined, low_stock_only: lowStockOnly || undefined }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const totalValue = stock?.reduce((s, i) => s + Number(i.fifo_value), 0) || 0

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input placeholder="Search products..." value={search} onChange={e => setSearch(e.target.value)} className="pl-8" />
        </div>
        <Select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="w-48">
          <option value="">All Warehouses</option>
          {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm cursor-pointer whitespace-nowrap">
          <input type="checkbox" checked={lowStockOnly} onChange={e => setLowStockOnly(e.target.checked)} className="rounded" />
          Low stock only
        </label>
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : stock?.length === 0 ? <Empty message="No stock records found" />
        : (
          <>
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="stat-card"><div className="stat-label">Total Products</div><div className="stat-value">{stock?.length}</div></div>
              <div className="stat-card"><div className="stat-label">Low Stock Items</div><div className="stat-value text-red-600">{stock?.filter(i => i.is_low_stock).length}</div></div>
              <div className="stat-card"><div className="stat-label">Total Stock Value (FIFO)</div><div className="stat-value text-blue-600">₹{totalValue.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</div></div>
            </div>
            <table className="table">
              <thead><tr><th style={{ width: '32px' }}></th><th>Part Code</th><th>Product</th><th>UOM</th><th className="text-right">Total Qty</th><th className="text-right">FIFO Value (₹)</th><th>Status</th></tr></thead>
              <tbody>
                {stock?.map(item => (
                  <Fragment key={item.product_id}>
                    <tr
                      className={clsx('cursor-pointer', item.is_low_stock ? 'bg-red-50/40' : '')}
                      onClick={() => setExpanded(p => ({ ...p, [item.product_id]: !p[item.product_id] }))}>
                      <td><button className="p-1 text-gray-400">{expanded[item.product_id] ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button></td>
                      <td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{item.part_code}</span></td>
                      <td className="font-medium text-gray-800">{item.part_name}</td>
                      <td className="text-gray-500 text-xs">{item.unit_of_measure}</td>
                      <td className="text-right font-semibold">{Number(item.total_quantity).toFixed(3)}</td>
                      <td className="text-right font-medium">₹{Number(item.fifo_value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      <td>{item.is_low_stock ? <Badge color="red"><AlertTriangle size={10} className="mr-1" />Low Stock</Badge> : <Badge color="green">Normal</Badge>}</td>
                    </tr>
                    {expanded[item.product_id] && item.warehouses?.map(wh => (
                      <tr key={`${item.product_id}-${wh.warehouse_id}`} className="bg-gray-50/60">
                        <td></td>
                        <td colSpan={2}><span className="text-xs text-gray-500 pl-4">↳ {wh.warehouse_name}</span></td>
                        <td></td>
                        <td className="text-right text-sm text-gray-600">{Number(wh.quantity).toFixed(3)}</td>
                        <td className="text-right text-sm text-gray-600">₹{Number(wh.fifo_value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td></td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </>
        )}
    </div>
  )
}


// -- DCLinkerPanel --
function DCLinkerPanel({ transfer, onLink, isPending }) {
  const [selectedDC, setSelectedDC] = useState('')

  const { data: availableDCs = [] } = useQuery({
    queryKey: ['available-dcs-link', transfer.source_warehouse_id, transfer.destination_warehouse_id],
    queryFn: () => invoiceAPI.listDCs({
      source_warehouse_id: transfer.source_warehouse_id,
      unlinked_only: true,
    }).then(r => r.data),
    enabled: Boolean(transfer.source_warehouse_id),
  })

  // Use Number() for type-safe comparison (JSON ids could be int or string)
  const linkedIds = (transfer.dc_ids || []).map(Number)
  // Show DCs that aren't already linked to THIS transfer and are pending/unlinked
  const unlinkedDCs = availableDCs.filter(dc =>
    !linkedIds.includes(Number(dc.id)) &&
    (!dc.dc_status || dc.dc_status === 'pending' || dc.dc_status === 'Pending')
  )

  return (
    <div className="pt-2 border-t border-gray-100">
      {unlinkedDCs.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          No pending DCs available for this warehouse.
          <span className="ml-1 text-blue-500">Create a Delivery Challan in Billing first.</span>
        </p>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 font-medium whitespace-nowrap">Add DC:</span>
          <select value={selectedDC} onChange={e => setSelectedDC(e.target.value)}
            className="flex-1 h-8 px-2 rounded-lg border border-gray-300 text-xs focus:outline-none focus:border-blue-500">
            <option value="">Select DC to link...</option>
            {unlinkedDCs.map(dc => (
              <option key={dc.id} value={dc.id}>
                {dc.invoice_number}
                {dc.destination_warehouse_name ? ` → ${dc.destination_warehouse_name}` : ''}
                {dc.vehicle_number ? ` | ${dc.vehicle_number}` : ''}
              </option>
            ))}
          </select>
          <button
            onClick={() => { if (selectedDC) { onLink(Number(selectedDC)); setSelectedDC('') } }}
            disabled={!selectedDC || isPending}
            className="px-3 h-8 rounded-lg bg-blue-600 text-white text-xs hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap">
            {isPending ? 'Linking...' : 'Link DC'}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Transfer Tab ──────────────────────────────────────────────
function TransferTab({ warehouses, isSuperAdminUser, userWarehouse: userWarehouseProp }) {
  const qc = useQueryClient()
  const { isAdmin, getUserWarehouse, isWarehouseRole, user } = useAuthStore()
  const isAdminUser = isAdmin()
  const isSales = user?.role === 'sales'
  const isWhRole = isWarehouseRole?.() || user?.role === 'warehouse'
  const userWarehouse = userWarehouseProp ?? getUserWarehouse()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    source_warehouse_id: '', destination_warehouse_id: '',
    transfer_date: format(new Date(), 'yyyy-MM-dd'), notes: '',
    dc_ids: [],
  })
  const [errors, setErrors] = useState({})
  const [statusView, setStatusView] = useState('pending')

  const { data: transfers, isLoading } = useQuery({
    queryKey: ['stock-transfers', statusView],
    queryFn: () => transferAPI.list({
      page_size: 50,
      pending_for_me: statusView === 'mine' || undefined,
    }).then(r => r.data),
  })

  const srcId = form.source_warehouse_id
  const dstId = form.destination_warehouse_id

  const { data: availableDCs = [] } = useQuery({
    queryKey: ['available-dcs', srcId, dstId],
    queryFn: () => invoiceAPI.listDCs({
      source_warehouse_id: srcId,
      unlinked_only: true,
    }).then(r => r.data),
    enabled: Boolean(srcId),
  })

  // Fetch full DC details for selected DCs to show line items
  const { data: dcDetails = [] } = useQuery({
    queryKey: ['dc-details', form.dc_ids],
    queryFn: async () => {
      const results = await Promise.all(
        form.dc_ids.map(id => invoiceAPI.get(id).then(r => r.data))
      )
      return results
    },
    enabled: form.dc_ids.length > 0,
  })

  // Aggregate line items from all selected DCs
  const dcLineItems = dcDetails.flatMap(dc =>
    (dc.items || []).map(item => ({
      ...item,
      dc_number: dc.invoice_number,
    }))
  )

  const toggleDC = (dcId) => {
    setForm(p => ({
      ...p,
      dc_ids: p.dc_ids.includes(dcId)
        ? p.dc_ids.filter(id => id !== dcId)
        : [...p.dc_ids, dcId]
    }))
    if (errors.dc_ids) setErrors(p => ({ ...p, dc_ids: '' }))
  }

  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    if (isSales && userWarehouse && !form.source_warehouse_id) {
      hc('source_warehouse_id', String(userWarehouse))
    }
  }, [isSales, userWarehouse])
  const [addingDCFor, setAddingDCFor] = useState(null) // transfer id being linked

  const mutation = useMutation({
    mutationFn: (d) => transferAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['stock-transfers'])
      qc.invalidateQueries(['warehouse-stock'])
      toast.success('Stock transfer completed')
      setShowForm(false)
      setForm({ source_warehouse_id: '', destination_warehouse_id: '', transfer_date: format(new Date(), 'yyyy-MM-dd'), notes: '', dc_ids: [] })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Transfer failed'),
  })

  const confirmDCMutation = useMutation({
    mutationFn: ({ transferId, dcId }) => transferAPI.confirmDC(transferId, dcId),
    onSuccess: () => {
      qc.invalidateQueries(['stock-transfers'])
      toast.success('DC approved — stock added to destination warehouse')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to approve'),
  })

  const rejectDCMutation = useMutation({
    mutationFn: ({ transferId, dcId, reason }) =>
      transferAPI.rejectDC(transferId, dcId, reason),
    onSuccess: () => {
      qc.invalidateQueries(['stock-transfers'])
      qc.invalidateQueries(['warehouse-stock'])
      qc.invalidateQueries(['available-dcs'])
      toast.success('DC rejected — stock returned to source warehouse')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to reject'),
  })

  const handleReject = (transferId, dcId, dcNumber) => {
    const reason = window.prompt(
      `Reject DC ${dcNumber}?\n\nEnter rejection reason (min 3 chars). ` +
      `Stock will be returned to the source warehouse.`
    )
    if (reason === null) return
    if (reason.trim().length < 3) {
      toast.error('Rejection reason must be at least 3 characters')
      return
    }
    rejectDCMutation.mutate({ transferId, dcId, reason: reason.trim() })
  }

  const cancelDCMutation = useMutation({
    mutationFn: (invId) => invoiceAPI.cancelDC(invId),
    onSuccess: () => {
      qc.invalidateQueries(['stock-transfers'])
      qc.invalidateQueries(['available-dcs'])
      toast.success('DC cancelled')
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to cancel'),
  })

  const linkMutation = useMutation({
    mutationFn: ({ transferId, dcId }) => transferAPI.linkDC(transferId, dcId),
    onSuccess: () => { qc.invalidateQueries(['stock-transfers']); toast.success('DC linked') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to link'),
  })

  const unlinkMutation = useMutation({
    mutationFn: ({ transferId, dcId }) => transferAPI.unlinkDC(transferId, dcId),
    onSuccess: () => { qc.invalidateQueries(['stock-transfers']); toast.success('DC unlinked') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to unlink'),
  })

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.source_warehouse_id) errs.source_warehouse_id = 'Required'
    if (!form.destination_warehouse_id) errs.destination_warehouse_id = 'Required'
    if (form.source_warehouse_id === form.destination_warehouse_id) errs.destination_warehouse_id = 'Cannot transfer to same warehouse'
    if (!form.dc_ids || form.dc_ids.length === 0) errs.dc_ids = 'Select at least one Delivery Challan'
    if (dcLineItems.length === 0) errs.dc_ids = 'Selected DCs have no line items'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    // Send one transfer per line item in selected DCs
    const transfers = dcLineItems.map(item => ({
      source_warehouse_id: Number(form.source_warehouse_id),
      destination_warehouse_id: Number(form.destination_warehouse_id),
      product_id: item.product_id,
      quantity: Number(item.quantity),
      transfer_date: form.transfer_date,
      notes: form.notes || null,
      dc_ids: form.dc_ids,
    }))
    // Create transfers sequentially
    mutation.mutate(transfers[0])
  }

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}><Plus size={14} /> New Transfer</Button>
      </div>

      {showForm && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between items-center">
            <h3 className="font-semibold text-gray-800">New Stock Transfer</h3>
            <button onClick={() => { setShowForm(false); setErrors({}) }} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Source Warehouse <span className="text-red-500">*</span></label>
                {isSuperAdminUser ? (
                  // super-admin: full dropdown, editable
                  <select value={form.source_warehouse_id}
                    onChange={e => hc('source_warehouse_id', e.target.value)}
                    className={ic(errors.source_warehouse_id)}>
                    <option value="">Select source...</option>
                    {(warehouses || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                ) : (
                  // Everyone else: auto-filled from assigned warehouse, locked
                  <div className="h-9 px-3 flex items-center rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-700 font-medium">
                    {userWarehouse
                      ? ((warehouses || []).find(w => Number(w.id) === Number(userWarehouse))?.name || `Warehouse #${userWarehouse}`)
                      : 'No warehouse assigned'}
                  </div>
                )}
                {errors.source_warehouse_id && <p className="text-xs text-red-500 mt-1">{errors.source_warehouse_id}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Destination Warehouse <span className="text-red-500">*</span></label>
                <select value={form.destination_warehouse_id} onChange={e => hc('destination_warehouse_id', e.target.value)}
                  className={ic(errors.destination_warehouse_id)}>
                  <option value="">Select destination...</option>
                  {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
                {errors.destination_warehouse_id && <p className="text-xs text-red-500 mt-1">{errors.destination_warehouse_id}</p>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Transfer Date</label>
                <input type="date" value={form.transfer_date} onChange={e => hc('transfer_date', e.target.value)} className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                <input value={form.notes} onChange={e => hc('notes', e.target.value)} placeholder="Optional" className={ic()} />
              </div>
            </div>

            {/* Line items preview from selected DCs */}
            {dcLineItems.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-2">
                  Items to Transfer <span className="text-gray-400">({dcLineItems.length} items from selected DCs)</span>
                </label>
                <div className="border border-gray-200 rounded-lg overflow-hidden">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-3 py-2 font-medium text-gray-500">DC No.</th>
                        <th className="text-left px-3 py-2 font-medium text-gray-500">Product</th>
                        <th className="text-right px-3 py-2 font-medium text-gray-500">Qty</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {dcLineItems.map((item, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono text-blue-600">{item.dc_number}</td>
                          <td className="px-3 py-2">
                            <div className="font-medium text-gray-800">{item.part_name}</div>
                            <div className="text-gray-400 font-mono">{item.part_code}</div>
                          </td>
                          <td className="px-3 py-2 text-right font-semibold">{Number(item.quantity).toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* DC Multi-select */}
            {form.source_warehouse_id && form.destination_warehouse_id && (
              <div className="mt-3">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Link Delivery Challans <span className="text-red-500">*</span>
                  <span className="text-xs font-normal text-gray-400 ml-1">(same route, unlinked only)</span>
                </label>
                {availableDCs.length === 0 ? (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
                    No unlinked DCs found for this warehouse pair. Create a Delivery Challan first in Billing.
                  </div>
                ) : (
                  <div className="border border-gray-200 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                    {availableDCs.map(dc => (
                      <label key={dc.id}
                        className={clsx('flex items-center gap-2 px-3 py-2 cursor-pointer border-b border-gray-50 last:border-0',
                          form.dc_ids.includes(dc.id) ? 'bg-blue-50' : 'hover:bg-gray-50')}>
                        <input type="checkbox"
                          checked={form.dc_ids.includes(dc.id)}
                          onChange={() => toggleDC(dc.id)}
                          className="rounded accent-blue-600" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium font-mono text-blue-700">{dc.invoice_number}</span>
                            <span className="text-xs text-gray-400">{dc.invoice_date}</span>
                          </div>
                          <div className="text-xs text-gray-500 mt-0.5">
                            <span className="font-medium">{dc.source_warehouse_name || 'Source'}</span>
                            <span className="mx-1 text-gray-300">→</span>
                            <span className="font-medium">{dc.destination_warehouse_name || 'Destination'}</span>
                            {dc.vehicle_number && <span className="ml-2 text-blue-500">🚛 {dc.vehicle_number}</span>}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                )}
                {form.dc_ids.length > 0 && (
                  <p className="text-xs text-green-600 mt-1 font-medium">✓ {form.dc_ids.length} DC(s) selected</p>
                )}
                {errors.dc_ids && <p className="text-xs text-red-500 mt-1">{errors.dc_ids}</p>}
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowForm(false); setErrors({}) }}>Cancel</Button>
              <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
                <ArrowRightLeft size={14} /> Execute Transfer
              </Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : transfers?.items?.length === 0 ? <Empty message="No transfers yet" />
        : (
          <div className="space-y-0">
          {/* Filter bar */}
          <div className="flex items-center gap-3 mb-3">
            <span className="text-xs text-gray-500">Show:</span>
            <button onClick={() => setStatusView('pending')}
              className={clsx('px-3 h-7 rounded-full text-xs font-medium',
                statusView === 'pending' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
              Pending
            </button>
            <button onClick={() => setStatusView('mine')}
              className={clsx('px-3 h-7 rounded-full text-xs font-medium',
                statusView === 'mine' ? 'bg-amber-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
              My Approvals
            </button>
            <button onClick={() => setStatusView('completed')}
              className={clsx('px-3 h-7 rounded-full text-xs font-medium',
                statusView === 'completed' ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
              Completed
            </button>
          </div>
          <div className="space-y-2">
            {transfers?.items?.filter(t => {
              if (statusView === 'completed') return t.transfer_status === 'completed'
              if (statusView === 'mine') return t.transfer_status !== 'completed' // backend already filtered to my dest
              return t.transfer_status !== 'completed' // 'pending'
            }).map(t => (
              <div key={t.id} className="border border-gray-200 rounded-xl overflow-hidden">
                <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 cursor-pointer hover:bg-gray-100"
                  onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}>
                  <div className="flex-1 grid grid-cols-5 gap-2 items-center text-sm">
                    <div className="font-mono text-xs font-semibold text-blue-700">{t.transfer_number}</div>
                    <div className="col-span-2">
                      <span className="font-medium">{t.source_warehouse_name}</span>
                      <span className="text-gray-400 mx-1">→</span>
                      <span className="font-medium">{t.destination_warehouse_name}</span>
                    </div>
                    <div className="text-xs text-gray-500">{t.transfer_date ? format(new Date(t.transfer_date), 'dd MMM yyyy') : '—'}</div>
                    <div>
                      {t.linked_dcs?.length > 0
                        ? <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">{t.linked_dcs.length} DC(s) linked</span>
                        : <span className="text-xs bg-amber-100 text-amber-600 px-2 py-0.5 rounded-full">No DCs</span>
                      }
                    </div>
                  </div>
                  <span className="text-gray-400 text-xs">{expandedId === t.id ? '▲' : '▼'}</span>
                </div>

                {expandedId === t.id && (
                  <div className="px-4 py-3 border-t border-gray-100 space-y-3">
                    <div className="text-xs font-semibold text-gray-600">Linked Delivery Challans</div>
                    {(!t.linked_dcs || t.linked_dcs.length === 0) && (
                      <div className="text-xs text-gray-400 italic py-1">No DCs linked yet</div>
                    )}
                    <div className="space-y-1.5">
                      {t.linked_dcs?.map(dc => (
                        <div key={dc.id} className="flex items-center justify-between px-3 py-2 bg-blue-50 rounded-lg border border-blue-100">
                          <div className="flex items-center gap-3 flex-wrap">
                            <span className="font-mono text-sm font-semibold text-blue-700">{dc.invoice_number}</span>
                            <span className="text-xs text-gray-500">{dc.invoice_date}</span>
                            {dc.vehicle_number && <span className="text-xs text-gray-500">🚛 {dc.vehicle_number}</span>}
                            <span className={clsx('text-xs px-1.5 py-0.5 rounded-full font-medium',
                              dc.dc_status === 'linked' ? 'bg-blue-200 text-blue-700' :
                              dc.dc_status === 'delivered' ? 'bg-green-100 text-green-700' :
                              dc.dc_status === 'rejected' ? 'bg-red-100 text-red-700' :
                              'bg-amber-100 text-amber-600')}>
                              {dc.dc_status}
                            </span>
                            {dc.dc_status === 'delivered' && dc.approved_at && (
                              <span className="text-xs text-green-700">
                                approved {dc.approved_at?.slice(0, 16)}
                              </span>
                            )}
                            {dc.dc_status === 'rejected' && (
                              <span className="text-xs text-red-700" title={dc.rejection_reason || ''}>
                                rejected {dc.rejected_at?.slice(0, 16)}
                                {dc.rejection_reason ? ` — ${dc.rejection_reason}` : ''}
                              </span>
                            )}
                          </div>
                          <div className="flex gap-1.5">
                            {/* Approve / Reject: destination-mapped user (or super-admin) only */}
                            {dc.dc_status === 'linked' && (
                              isSuperAdminUser ||
                              (userWarehouse && Number(userWarehouse) === Number(t.destination_warehouse_id))
                            ) ? (
                              <>
                                <button
                                  onClick={() => confirmDCMutation.mutate({ transferId: t.id, dcId: dc.id })}
                                  disabled={confirmDCMutation.isPending || rejectDCMutation.isPending}
                                  className="text-xs px-2.5 py-1 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
                                  ✓ Approve
                                </button>
                                <button
                                  onClick={() => handleReject(t.id, dc.id, dc.invoice_number)}
                                  disabled={confirmDCMutation.isPending || rejectDCMutation.isPending}
                                  className="text-xs px-2.5 py-1 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50">
                                  ✗ Reject
                                </button>
                              </>
                            ) : null}
                            {/* Unlink: source OR destination user (or super-admin) — only while pending */}
                            {dc.dc_status !== 'delivered' && dc.dc_status !== 'rejected' &&
                             t.transfer_status !== 'completed' &&
                              (isSuperAdminUser || (userWarehouse && (
                                Number(userWarehouse) === Number(t.source_warehouse_id) ||
                                Number(userWarehouse) === Number(t.destination_warehouse_id)
                              ))) && (
                              <button
                                onClick={() => unlinkMutation.mutate({ transferId: t.id, dcId: dc.id })}
                                disabled={unlinkMutation.isPending}
                                className="text-xs px-2.5 py-1 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50">
                                Unlink
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    {t.transfer_status !== 'completed' &&
                      (isSuperAdminUser || (userWarehouse && (
                        Number(userWarehouse) === Number(t.source_warehouse_id) ||
                        Number(userWarehouse) === Number(t.destination_warehouse_id)
                      ))) && (
                      <DCLinkerPanel
                        transfer={t}
                        onLink={(dcId) => linkMutation.mutate({ transferId: t.id, dcId })}
                        isPending={linkMutation.isPending}
                      />
                    )}
                    {t.transfer_status === 'completed' && (
                      <div className="text-xs text-green-600 font-medium pt-1 border-t border-gray-100">
                        ✓ Transfer completed — no further changes allowed
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          </div>
        )}
    </div>
  )
}

// ── Adjustment Tab ────────────────────────────────────────────
function AdjustmentTab({ warehouses }) {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState(null)
  const [form, setForm] = useState({
    warehouse_id: '', adjustment_type: 'in', quantity: '',
    reason: '', adjustment_date: format(new Date(), 'yyyy-MM-dd'),
    unit_cost: '', notes: '',
  })
  const [errors, setErrors] = useState({})

  const { data: adjustments, isLoading } = useQuery({
    queryKey: ['stock-adjustments'],
    queryFn: () => adjustmentAPI.list({ page_size: 50 }).then(r => r.data),
  })

  const mutation = useMutation({
    mutationFn: (d) => adjustmentAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['stock-adjustments'])
      qc.invalidateQueries(['warehouse-stock'])
      toast.success('Stock adjustment saved')
      setShowForm(false)
      setSelectedProduct(null)
      setForm({ warehouse_id: '', adjustment_type: 'in', quantity: '', reason: '', adjustment_date: format(new Date(), 'yyyy-MM-dd'), unit_cost: '', notes: '' })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Adjustment failed'),
  })

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.warehouse_id) errs.warehouse_id = 'Required'
    if (!selectedProduct) errs.product = 'Select a product'
    if (!form.quantity || Number(form.quantity) <= 0) errs.quantity = 'Enter valid quantity'
    if (!form.reason || form.reason.length < 3) errs.reason = 'Enter reason (min 3 chars)'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    mutation.mutate({
      warehouse_id: Number(form.warehouse_id),
      product_id: selectedProduct.id,
      adjustment_type: form.adjustment_type,
      quantity: Number(form.quantity),
      reason: form.reason,
      adjustment_date: form.adjustment_date,
      unit_cost: form.unit_cost ? Number(form.unit_cost) : null,
      notes: form.notes || null,
    })
  }

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}><Plus size={14} /> New Adjustment</Button>
      </div>

      {showForm && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between items-center">
            <h3 className="font-semibold text-gray-800">New Stock Adjustment</h3>
            <button onClick={() => { setShowForm(false); setErrors({}) }} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Warehouse <span className="text-red-500">*</span></label>
                <select value={form.warehouse_id} onChange={e => hc('warehouse_id', e.target.value)} className={ic(errors.warehouse_id)}>
                  <option value="">Select warehouse...</option>
                  {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
                {errors.warehouse_id && <p className="text-xs text-red-500 mt-1">{errors.warehouse_id}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Adjustment Type <span className="text-red-500">*</span></label>
                <select value={form.adjustment_type} onChange={e => hc('adjustment_type', e.target.value)} className={ic()}>
                  <option value="in">Stock In (increase)</option>
                  <option value="out">Stock Out (decrease)</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Product <span className="text-red-500">*</span></label>
              <ProductSearchInput value={selectedProduct} onSelect={p => { setSelectedProduct(p); if (errors.product) setErrors(prev => ({ ...prev, product: '' })) }} />
              {errors.product && <p className="text-xs text-red-500 mt-1">{errors.product}</p>}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Quantity <span className="text-red-500">*</span></label>
                <input type="number" step="0.001" min="0.001" value={form.quantity} onChange={e => hc('quantity', e.target.value)} className={ic(errors.quantity)} />
                {errors.quantity && <p className="text-xs text-red-500 mt-1">{errors.quantity}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Unit Cost (₹)</label>
                <input type="number" step="0.01" min="0" value={form.unit_cost} onChange={e => hc('unit_cost', e.target.value)} placeholder="0.00" className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Date</label>
                <input type="date" value={form.adjustment_date} onChange={e => hc('adjustment_date', e.target.value)} className={ic()} />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Reason <span className="text-red-500">*</span></label>
              <input value={form.reason} onChange={e => hc('reason', e.target.value)} placeholder="Reason for this adjustment (mandatory)" className={ic(errors.reason)} />
              {errors.reason && <p className="text-xs text-red-500 mt-1">{errors.reason}</p>}
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowForm(false); setErrors({}) }}>Cancel</Button>
              <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>Save Adjustment</Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : adjustments?.items?.length === 0 ? <Empty message="No adjustments yet" />
        : (
          <table className="table">
            <thead><tr><th>Adj. No.</th><th>Product</th><th>Warehouse</th><th>Type</th><th className="text-right">Qty</th><th>Reason</th><th>Date</th></tr></thead>
            <tbody>
              {adjustments?.items?.map(a => (
                <tr key={a.id}>
                  <td className="font-mono text-xs font-medium">{a.adjustment_number}</td>
                  <td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded mr-2">{a.part_code}</span>{a.part_name}</td>
                  <td className="text-gray-600">{a.warehouse_name}</td>
                  <td><Badge color={a.adjustment_type === 'in' ? 'green' : 'red'}>{a.adjustment_type === 'in' ? 'IN' : 'OUT'}</Badge></td>
                  <td className="text-right font-medium">{Number(a.quantity).toFixed(3)}</td>
                  <td className="text-gray-500 text-sm truncate max-w-xs">{a.reason}</td>
                  <td className="text-gray-500 text-xs">{a.adjustment_date ? format(new Date(a.adjustment_date), 'dd MMM yyyy') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  )
}

// ── Write-off Tab ─────────────────────────────────────────────
function WriteoffTab({ warehouses }) {
  const qc = useQueryClient()
  const { isAdmin } = useAuthStore()
  const [showForm, setShowForm] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [form, setForm] = useState({
    warehouse_id: '', quantity: '', reason_type: 'damaged',
    reason_detail: '', writeoff_date: format(new Date(), 'yyyy-MM-dd'), notes: '',
  })
  const [errors, setErrors] = useState({})

  const { data: writeoffs, isLoading } = useQuery({
    queryKey: ['stock-writeoffs', statusFilter],
    queryFn: () => writeoffAPI.list({ status: statusFilter || undefined, page_size: 50 }).then(r => r.data),
  })

  const approveMutation = useMutation({
    mutationFn: ({ id, approved }) => writeoffAPI.approve(id, { approved }),
    onSuccess: () => { qc.invalidateQueries(['stock-writeoffs']); qc.invalidateQueries(['warehouse-stock']); toast.success('Write-off decision saved') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const createMutation = useMutation({
    mutationFn: (d) => writeoffAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['stock-writeoffs'])
      toast.success('Write-off submitted for admin approval')
      setShowForm(false)
      setSelectedProduct(null)
      setForm({ warehouse_id: '', quantity: '', reason_type: 'damaged', reason_detail: '', writeoff_date: format(new Date(), 'yyyy-MM-dd'), notes: '' })
      setErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.warehouse_id) errs.warehouse_id = 'Required'
    if (!selectedProduct) errs.product = 'Select a product'
    if (!form.quantity || Number(form.quantity) <= 0) errs.quantity = 'Enter valid quantity'
    if (!form.reason_detail || form.reason_detail.length < 3) errs.reason_detail = 'Enter detailed reason (min 3 chars)'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    createMutation.mutate({
      warehouse_id: Number(form.warehouse_id),
      product_id: selectedProduct.id,
      quantity: Number(form.quantity),
      reason_type: form.reason_type,
      reason_detail: form.reason_detail,
      writeoff_date: form.writeoff_date,
      notes: form.notes || null,
    })
  }

  const STATUS_COLORS = { pending: 'amber', approved: 'green', rejected: 'red' }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm w-40 focus:outline-none focus:border-blue-500">
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <div className="flex-1" />
        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}><Plus size={14} /> New Write-off</Button>
      </div>

      {showForm && (
        <div className="card mb-4 border-2 border-amber-200">
          <div className="card-header flex justify-between items-center">
            <h3 className="font-semibold text-gray-800">New Stock Write-off</h3>
            <button onClick={() => { setShowForm(false); setErrors({}) }} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <AlertBox type="warning">Write-offs require admin approval before stock is deducted.</AlertBox>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Warehouse <span className="text-red-500">*</span></label>
                <select value={form.warehouse_id} onChange={e => hc('warehouse_id', e.target.value)} className={ic(errors.warehouse_id)}>
                  <option value="">Select warehouse...</option>
                  {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
                {errors.warehouse_id && <p className="text-xs text-red-500 mt-1">{errors.warehouse_id}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Reason Type</label>
                <select value={form.reason_type} onChange={e => hc('reason_type', e.target.value)} className={ic()}>
                  <option value="damaged">Damaged</option>
                  <option value="expired">Expired</option>
                  <option value="theft">Theft</option>
                  <option value="shortage">Shortage / Variance</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Product <span className="text-red-500">*</span></label>
              <ProductSearchInput value={selectedProduct} onSelect={p => { setSelectedProduct(p); if (errors.product) setErrors(prev => ({ ...prev, product: '' })) }} />
              {errors.product && <p className="text-xs text-red-500 mt-1">{errors.product}</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Quantity <span className="text-red-500">*</span></label>
                <input type="number" step="0.001" min="0.001" value={form.quantity} onChange={e => hc('quantity', e.target.value)} className={ic(errors.quantity)} />
                {errors.quantity && <p className="text-xs text-red-500 mt-1">{errors.quantity}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Write-off Date</label>
                <input type="date" value={form.writeoff_date} onChange={e => hc('writeoff_date', e.target.value)} className={ic()} />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Detailed Reason <span className="text-red-500">*</span></label>
              <textarea rows={2} value={form.reason_detail} onChange={e => hc('reason_detail', e.target.value)}
                placeholder="Describe why this stock is being written off..."
                className={clsx('w-full px-3 py-2 rounded-lg border text-sm focus:outline-none focus:ring-2 resize-none transition-colors',
                  errors.reason_detail ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500')} />
              {errors.reason_detail && <p className="text-xs text-red-500 mt-1">{errors.reason_detail}</p>}
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowForm(false); setErrors({}) }}>Cancel</Button>
              <Button variant="warning" loading={createMutation.isPending} onClick={handleSubmit}>Submit for Approval</Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : writeoffs?.items?.length === 0 ? <Empty message="No write-offs found" />
        : (
          <table className="table">
            <thead><tr><th>WO No.</th><th>Product</th><th>Warehouse</th><th>Reason</th><th className="text-right">Qty</th><th>Status</th>{isAdmin() && <th>Action</th>}</tr></thead>
            <tbody>
              {writeoffs?.items?.map(wo => (
                <tr key={wo.id}>
                  <td className="font-mono text-xs font-medium">{wo.writeoff_number}</td>
                  <td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded mr-2">{wo.part_code}</span>{wo.part_name}</td>
                  <td className="text-gray-600">{wo.warehouse_name}</td>
                  <td className="text-gray-500 text-xs capitalize">{wo.reason_type}</td>
                  <td className="text-right font-medium">{Number(wo.quantity).toFixed(3)}</td>
                  <td><Badge color={STATUS_COLORS[wo.status]}>{wo.status}</Badge></td>
                  {isAdmin() && (
                    <td>
                      {wo.status === 'pending' && (
                        <div className="flex gap-1">
                          <button onClick={() => approveMutation.mutate({ id: wo.id, approved: true })}
                            className="p-1.5 rounded hover:bg-green-50 text-gray-400 hover:text-green-600" title="Approve">
                            <CheckCircle size={14} />
                          </button>
                          <button onClick={() => approveMutation.mutate({ id: wo.id, approved: false })}
                            className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600" title="Reject">
                            <XCircle size={14} />
                          </button>
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  )
}

// ── Ageing Tab ────────────────────────────────────────────────
function AgeingTab({ warehouses }) {
  const [warehouseId, setWarehouseId] = useState('')
  const { data: ageing, isLoading } = useQuery({
    queryKey: ['stock-ageing', warehouseId],
    queryFn: () => warehouseAPI.ageing({ warehouse_id: warehouseId || undefined }).then(r => r.data),
  })
  const BUCKET_COLORS = { '0-30': 'green', '31-60': 'blue', '61-90': 'amber', '90+': 'red' }
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="w-48">
          <option value="">All Warehouses</option>
          {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </Select>
        {ageing?.as_of_date && <span className="text-sm text-gray-400">As of {format(new Date(ageing.as_of_date), 'dd MMM yyyy')}</span>}
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div>
        : ageing ? (
          <>
            <div className="grid grid-cols-4 gap-3 mb-6">
              {Object.entries(ageing.summary || {}).map(([bucket, value]) => (
                <div key={bucket} className="stat-card">
                  <div className="stat-label">{bucket} days</div>
                  <div className="stat-value">₹{Number(value).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</div>
                </div>
              ))}
            </div>
            {Object.entries(ageing.buckets || {}).map(([bucket, items]) => items.length > 0 && (
              <div key={bucket} className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <Badge color={BUCKET_COLORS[bucket]}>{bucket} days</Badge>
                  <span className="text-xs text-gray-400">{items.length} FIFO layers</span>
                </div>
                <table className="table">
                  <thead><tr><th>Part Code</th><th>Product</th><th>Warehouse</th><th>Batch Date</th><th className="text-right">Age</th><th className="text-right">Qty</th><th className="text-right">Value (₹)</th></tr></thead>
                  <tbody>
                    {items.map((item, i) => (
                      <tr key={i}>
                        <td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{item.part_code}</span></td>
                        <td className="font-medium">{item.part_name}</td>
                        <td className="text-gray-500">{item.warehouse_name}</td>
                        <td className="text-gray-500 text-xs">{format(new Date(item.batch_date), 'dd MMM yyyy')}</td>
                        <td className="text-right font-medium">{item.age_days}d</td>
                        <td className="text-right">{Number(item.quantity).toFixed(3)}</td>
                        <td className="text-right font-medium">₹{Number(item.value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </>
        ) : null}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────
export default function WarehousePage() {
  const qc = useQueryClient()
  const { isAdmin: _isAdminMain, getUserWarehouse: _getWH, user: _user, isSuperAdmin: _isSuper } = useAuthStore()
  const isAdminUser = _isAdminMain()
  const userWarehouse = _getWH()
  const isSuperAdminUser = _isSuper()
  // Adjustments / Write-offs / Ageing are limited to super-admin, admin and warehouse roles.
  const canWarehouseOps = ['super_admin', 'admin', 'warehouse'].includes(_user?.role)
  const visibleTabs = canWarehouseOps ? TABS : TABS.filter(t => !['Adjustments', 'Write-offs', 'Ageing'].includes(t))
  const [activeTab, setActiveTab] = useState('Stock')
  const [showNewWH, setShowNewWH] = useState(false)
  const [whForm, setWhForm] = useState({ name: '', address: '', city: '', state: '', pincode: '', contact_person: '', phone: '', is_default: false })
  const [whErrors, setWhErrors] = useState({})

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseAPI.list().then(r => r.data),
  })

  const { data: states = [] } = useQuery({
    queryKey: ['states'],
    queryFn: () => settingsAPI.getStates().then(r => r.data),
  })

  const createWHMutation = useMutation({
    mutationFn: (d) => warehouseAPI.create(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['warehouses'])
      toast.success(`Warehouse created — code ${res.data?.code || ''}`)
      setShowNewWH(false)
      setWhForm({ name: '', address: '', city: '', state: '', pincode: '', contact_person: '', phone: '', is_default: false })
      setWhErrors({})
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to create warehouse'),
  })

  const [editWH, setEditWH] = useState(null)
  const [validateResult, setValidateResult] = useState(null)
  const [showObsoleteConfirm, setShowObsoleteConfirm] = useState(null)
  const [validateDeleteResult, setValidateDeleteResult] = useState(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null)

  const editWHMutation = useMutation({
    mutationFn: ({ id, data }) => warehouseAPI.rename(id, data),
    onSuccess: () => {
      qc.invalidateQueries(['warehouses'])
      toast.success('Warehouse updated')
      setEditWH(null)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to update'),
  })

  const obsoleteMutation = useMutation({
    mutationFn: (id) => warehouseAPI.obsolete(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries(['warehouses'])
      toast.success('Warehouse marked as obsolete')
      setShowObsoleteConfirm(null)
      setValidateResult(null)
    },
    onError: (e) => {
      const d = e.response?.data?.detail
      if (d?.blocks) {
        setValidateResult(d)
      } else {
        toast.error(typeof d === 'string' ? d : 'Failed to obsolete warehouse')
      }
    },
  })

  const handleObsoleteClick = async (wh) => {
    try {
      const res = await warehouseAPI.validateObsolete(wh.id)
      if (res.data.can_obsolete) {
        setShowObsoleteConfirm(wh)
        setValidateResult(res.data)
      } else {
        setValidateResult(res.data)
        setShowObsoleteConfirm(wh)
      }
    } catch (e) {
      toast.error('Failed to validate')
    }
  }

  const deleteMutation = useMutation({
    mutationFn: (id) => warehouseAPI.delete(id),
    onSuccess: () => {
      qc.invalidateQueries(['warehouses'])
      toast.success('Warehouse deleted')
      setShowDeleteConfirm(null)
      setValidateDeleteResult(null)
    },
    onError: (e) => {
      const d = e.response?.data?.detail
      if (d?.blocks) {
        setValidateDeleteResult(d)
      } else {
        toast.error(typeof d === 'string' ? d : 'Failed to delete warehouse')
      }
    },
  })

  const handleDeleteClick = async (wh) => {
    try {
      const res = await warehouseAPI.validateDelete(wh.id)
      setValidateDeleteResult(res.data)
      setShowDeleteConfirm(wh)
    } catch (e) {
      const status = e.response?.status
      if (status === 403) {
        toast.error('Only system administrator can delete warehouses')
      } else {
        toast.error('Failed to validate')
      }
    }
  }

  const handleCreateWH = () => {
    const errs = {}
    if (!whForm.name) errs.name = 'Required'
    setWhErrors(errs)
    if (Object.keys(errs).length > 0) return
    createWHMutation.mutate(whForm)
  }

  return (
    <div>
     <div className="page-header">
        <div><div className="breadcrumb">Warehouse</div><h1 className="page-title">Inventory & Warehouse Management</h1></div>
        <Button variant="primary" size="sm" onClick={() => setShowNewWH(true)}><Plus size={14} /> New Warehouse</Button>
      </div>

      {showNewWH && (
        <div className="card mb-4 border-2 border-blue-200">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">New Warehouse</h3>
            <button onClick={() => setShowNewWH(false)} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-red-500">*</span> <span className="text-gray-400 font-normal">(code is auto-generated)</span></label>
              <input value={whForm.name} onChange={e => { setWhForm(p => ({ ...p, name: e.target.value })); setWhErrors(p => ({ ...p, name: '' })) }}
                placeholder="Main Warehouse" className={ic(whErrors.name)} />
              {whErrors.name && <p className="text-xs text-red-500 mt-1">{whErrors.name}</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">City</label>
                <input value={whForm.city} onChange={e => setWhForm(p => ({ ...p, city: e.target.value }))} placeholder="City" className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">State <span className="text-gray-400 font-normal">(sets GST state code)</span></label>
                <select value={whForm.state} onChange={e => setWhForm(p => ({ ...p, state: e.target.value }))} className={ic()}>
                  <option value="">Select state...</option>
                  {states.map(s => (
                    <option key={s.code} value={s.name}>{s.code} — {s.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Contact Person</label>
                <input value={whForm.contact_person} onChange={e => setWhForm(p => ({ ...p, contact_person: e.target.value }))} placeholder="Manager name" className={ic()} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
                <input value={whForm.phone} onChange={e => setWhForm(p => ({ ...p, phone: e.target.value }))} placeholder="+91 98765 43210" className={ic()} />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={whForm.is_default} onChange={e => setWhForm(p => ({ ...p, is_default: e.target.checked }))} className="rounded" />
              <span>Set as default warehouse</span>
            </label>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => setShowNewWH(false)}>Cancel</Button>
              <Button variant="primary" loading={createWHMutation.isPending} onClick={handleCreateWH}>Create Warehouse</Button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-3 mb-4 overflow-x-auto pb-1">
        {warehouses?.map(wh => (
          <div key={wh.id} className={clsx("stat-card min-w-48 flex-shrink-0", !wh.is_active && "opacity-50 border-dashed")}>
            <div className="flex items-center justify-between mb-1">
              <div className="stat-label">{wh.name}</div>
              <div className="flex items-center gap-1">
                {wh.is_default && <Badge color="blue">Default</Badge>}
                {!wh.is_active && <Badge color="gray">Obsolete</Badge>}
              </div>
            </div>
            <div className="text-sm font-semibold text-gray-700">₹{Number(wh.stock_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</div>
            <div className="text-xs text-gray-400 mt-0.5">{wh.city || wh.code}</div>
            <div className="flex gap-1.5 mt-2">
              {/* Edit: superadmin can edit any, admin can edit only their mapped warehouse */}
              {(isSuperAdminUser || (isAdminUser && !userWarehouse) || (isAdminUser && Number(userWarehouse) === Number(wh.id))) && (
                <button onClick={() => setEditWH({ ...wh })}
                  className="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-500 hover:bg-gray-50">
                  Edit
                </button>
              )}
              {/* Obsolete: only super-admin */}
              {isSuperAdminUser && wh.is_active && (
                <button onClick={() => handleObsoleteClick(wh)}
                  className="text-xs px-2 py-0.5 rounded border border-red-200 text-red-500 hover:bg-red-50">
                  Obsolete
                </button>
              )}
              {/* Delete: only super-admin, hard-delete if no references exist */}
              {isSuperAdminUser && (
                <button onClick={() => handleDeleteClick(wh)}
                  className="text-xs px-2 py-0.5 rounded border border-red-300 bg-red-50 text-red-600 hover:bg-red-100">
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex border-b border-gray-200 mb-4">
        {visibleTabs.map(tab => (
          <button key={tab}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
              activeTab === tab ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700')}
            onClick={() => setActiveTab(tab)}>{tab}</button>
        ))}
      </div>

      <div className="card"><div className="p-4">
        {activeTab === 'Stock' && <StockTab warehouses={warehouses} />}
        {activeTab === 'Transfers' && <TransferTab warehouses={warehouses} isSuperAdminUser={isSuperAdminUser} userWarehouse={userWarehouse} />}
        {activeTab === 'Adjustments' && <AdjustmentTab warehouses={warehouses} />}
        {activeTab === 'Write-offs' && <WriteoffTab warehouses={warehouses} />}
        {activeTab === 'Ageing' && <AgeingTab warehouses={warehouses} />}

      {/* Edit Warehouse Modal */}
      {editWH && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl flex flex-col" style={{ maxHeight: '90vh' }}>
            <div className="flex items-center justify-between p-5 border-b flex-shrink-0">
              <h3 className="font-semibold text-gray-900">Edit Warehouse</h3>
              <button onClick={() => setEditWH(null)} className="text-gray-400 hover:text-gray-600">✕</button>
            </div>
            <div className="p-5 space-y-3 overflow-y-auto flex-1">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Code (read-only)</label>
                <input value={editWH.code || ''} readOnly className="w-full h-9 px-3 rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-400 cursor-not-allowed" />
              </div>
              {[['name','Name',true],['address','Address',false],['city','City',false],['pincode','Pincode',false],['contact_person','Contact Person',false],['phone','Phone',false]].map(([field, label, req]) => (
                <div key={field}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{label}{req && <span className="text-red-500 ml-0.5">*</span>}</label>
                  <input value={editWH[field] || ''} onChange={e => setEditWH(p => ({ ...p, [field]: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              ))}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">State</label>
                <select value={editWH.state || ''}
                  onChange={e => setEditWH(p => ({ ...p, state: e.target.value }))}
                  className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
                  <option value="">Select state...</option>
                  {states.map(s => (
                    <option key={s.code} value={s.name}>{s.code} — {s.name}</option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={editWH.is_default || false}
                  onChange={e => setEditWH(p => ({ ...p, is_default: e.target.checked }))} className="rounded" />
                <span className="text-sm text-gray-700">Set as default warehouse</span>
              </label>

              {/* Bank Details */}
              <div className="border-t pt-3 mt-1">
                <label className="flex items-center gap-2 cursor-pointer mb-3">
                  <input type="checkbox" checked={editWH.use_company_bank !== false}
                    onChange={e => setEditWH(p => ({ ...p, use_company_bank: e.target.checked }))} className="rounded" />
                  <span className="text-sm font-medium text-gray-700">Use company bank details</span>
                </label>
                {editWH.use_company_bank === false && (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Warehouse Bank Details</div>
                    {[
                      ['bank_account_name','Account Name'],
                      ['bank_name','Bank Name'],
                      ['bank_account_number','Account Number'],
                      ['bank_ifsc','IFSC Code'],
                      ['bank_branch','Branch'],
                      ['upi_id','UPI ID'],
                    ].map(([field, label]) => (
                      <div key={field}>
                        <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                        <input value={editWH[field] || ''} onChange={e => setEditWH(p => ({ ...p, [field]: e.target.value }))}
                          className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="flex gap-3 p-5 border-t flex-shrink-0">
              <Button variant="secondary" className="flex-1" onClick={() => setEditWH(null)}>Cancel</Button>
              <Button variant="primary" className="flex-1" loading={editWHMutation.isPending}
                onClick={() => editWHMutation.mutate({ id: editWH.id, data: editWH })}>Save Changes</Button>
            </div>
          </div>
        </div>
      )}

      {/* Obsolete Confirmation Modal */}
      {showObsoleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl flex flex-col" style={{ maxHeight: '90vh' }}>
            <div className="flex items-center justify-between p-5 border-b flex-shrink-0">
              <h3 className="font-semibold text-gray-900">Obsolete: {showObsoleteConfirm.name}</h3>
              <button onClick={() => { setShowObsoleteConfirm(null); setValidateResult(null) }} className="text-gray-400 hover:text-gray-600">X</button>
            </div>
            <div className="p-5 space-y-3 overflow-y-auto" style={{ maxHeight: '65vh' }}>
              {validateResult?.can_obsolete ? (
                <div className="p-3 bg-green-50 rounded-xl border border-green-200 text-sm text-green-800">
                  All checks passed - this warehouse can be safely obsoleted.
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-red-700 mb-2">Resolve these issues before obsoleting:</div>
                  {validateResult?.blocks?.map((block, i) => (
                    <div key={i} className="border border-red-200 rounded-xl p-3 bg-red-50">
                      <div className="text-xs font-semibold text-red-700 mb-1">{block.message}</div>
                      {block.items?.slice(0,5).map((item,j) => (
                        <div key={j} className="text-xs text-red-600 pl-2">
                          - {item.invoice_number || item.transfer_number || item.username || item.name || item.part_name || '?'}
                          {item.qty != null && <span className="ml-1 text-gray-500">({item.qty} units)</span>}
                          {item.outstanding != null && <span className="ml-1 text-gray-500">(outstanding)</span>}
                        </div>
                      ))}
                      {block.items?.length > 5 && <div className="text-xs text-red-400 pl-2">...and {block.items.length-5} more</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-3 p-5 border-t flex-shrink-0">
              <Button variant="secondary" className="flex-1" onClick={() => { setShowObsoleteConfirm(null); setValidateResult(null) }}>Cancel</Button>
              {validateResult?.can_obsolete && (
                <button onClick={() => obsoleteMutation.mutate(showObsoleteConfirm.id)}
                  disabled={obsoleteMutation.isPending}
                  className="flex-1 h-10 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-60">
                  {obsoleteMutation.isPending ? 'Processing...' : 'Confirm Obsolete'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal — hard delete, only when no references exist */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl flex flex-col" style={{ maxHeight: '90vh' }}>
            <div className="flex items-center justify-between p-5 border-b flex-shrink-0">
              <h3 className="font-semibold text-red-700">Delete: {showDeleteConfirm.name}</h3>
              <button onClick={() => { setShowDeleteConfirm(null); setValidateDeleteResult(null) }} className="text-gray-400 hover:text-gray-600">X</button>
            </div>
            <div className="p-5 space-y-3 overflow-y-auto" style={{ maxHeight: '65vh' }}>
              {validateDeleteResult?.can_delete ? (
                <div className="p-3 bg-red-50 rounded-xl border border-red-200 text-sm text-red-800">
                  <div className="font-semibold mb-1">⚠ Permanent deletion</div>
                  This warehouse has no references and will be permanently removed.
                  This action cannot be undone.
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-red-700 mb-2">
                    Cannot delete — this warehouse has historical references. Use <span className="font-semibold">Obsolete</span> instead.
                  </div>
                  {validateDeleteResult?.blocks?.map((block, i) => (
                    <div key={i} className="border border-red-200 rounded-xl p-3 bg-red-50">
                      <div className="text-xs font-semibold text-red-700">{block.message}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-3 p-5 border-t flex-shrink-0">
              <Button variant="secondary" className="flex-1" onClick={() => { setShowDeleteConfirm(null); setValidateDeleteResult(null) }}>Cancel</Button>
              {validateDeleteResult?.can_delete && (
                <button onClick={() => deleteMutation.mutate(showDeleteConfirm.id)}
                  disabled={deleteMutation.isPending}
                  className="flex-1 h-10 rounded-xl bg-red-700 text-white text-sm font-medium hover:bg-red-800 disabled:opacity-60">
                  {deleteMutation.isPending ? 'Deleting...' : 'Permanently Delete'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      </div></div>
    </div>
  )
}