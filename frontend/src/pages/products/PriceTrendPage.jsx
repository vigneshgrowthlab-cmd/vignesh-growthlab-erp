import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { Search, TrendingUp, TrendingDown, Minus, Bell, BellOff, Calendar, AlertTriangle } from 'lucide-react'
import api, { productAPI } from '@/api'
import { Spinner, Button } from '@/components/ui'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'

const fmt = (v) => `₹${Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
const pct = (v) => `${v > 0 ? '+' : ''}${Number(v || 0).toFixed(2)}%`

const PRICE_TYPES = [
  { key: 'purchase_cost', label: 'Purchase Cost', color: '#ef4444' },
  { key: 'floor_price',   label: 'Floor Price',   color: '#10b981' },
  { key: 'b2b_price',     label: 'B2B Price',     color: '#3b82f6' },
  { key: 'b2c_price',     label: 'B2C Price',     color: '#8b5cf6' },
  { key: 'mrp',           label: 'MRP',            color: '#f59e0b' },
]

const SEVERITY_COLORS = {
  critical: 'bg-red-50 border-red-200 text-red-700',
  warning:  'bg-amber-50 border-amber-200 text-amber-700',
  info:     'bg-blue-50 border-blue-200 text-blue-700',
}

// ── Product Search ────────────────────────────────────────────
function ProductSearch({ onSelect }) {
  const [q, setQ] = useState('')
  const { data, isLoading, isError } = useQuery({
    queryKey: ['product-search-trend', q],
    queryFn: () => productAPI.list({ search: q, page_size: 10 }).then(r => r.data),
    enabled: q.length >= 2,
    retry: 1,
  })
  const products = data?.items || []

  return (
    <div className="relative">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input value={q} onChange={e => setQ(e.target.value)}
          placeholder="Search product by name or code..."
          className="w-full h-10 pl-9 pr-4 rounded-xl border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
      </div>
      {q.length >= 2 && (isError || products.length > 0) && (
        <div className="absolute top-12 left-0 right-0 bg-white border border-gray-200 rounded-xl shadow-xl max-h-60 overflow-y-auto"
          style={{ zIndex: 9999 }}>
          {isError ? (
            <div className="px-4 py-3 text-sm text-red-500">Search failed — please try again</div>
          ) : products.map(p => (
            <button key={p.id} onClick={() => { onSelect(p); setQ('') }}
              className="w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-gray-100 last:border-0">
              <div className="text-sm font-medium text-gray-900">{p.part_name}</div>
              <div className="text-xs text-gray-400">{p.part_code}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Price Update Form ─────────────────────────────────────────
function PriceUpdateForm({ productId, currentPrices, onSuccess }) {
  const [form, setForm] = useState({
    price_type: 'b2b_price',
    price: '',
    effective_from: new Date().toISOString().split('T')[0],
    change_reason: '',
  })

  const mutation = useMutation({
    mutationFn: (d) => api.post(`/api/v1/price-history/${productId}/update`, d),
    onSuccess: () => { toast.success('Price updated'); onSuccess() },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to update price'),
  })

  const isScheduled = form.effective_from > new Date().toISOString().split('T')[0]

  return (
    <div className="bg-gray-50 rounded-xl p-4 border border-gray-200 space-y-3">
      <div className="text-sm font-semibold text-gray-700 flex items-center gap-2">
        {isScheduled ? <><Calendar size={14} className="text-blue-500" /> Schedule Future Price</> : 'Update Price'}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Price Type</label>
          <select value={form.price_type} onChange={e => setForm(p => ({ ...p, price_type: e.target.value }))}
            className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
            {PRICE_TYPES.map(pt => (
              <option key={pt.key} value={pt.key}>{pt.label}
                {currentPrices[pt.key] ? ` (current: ${fmt(currentPrices[pt.key])})` : ''}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">New Price (₹)</label>
          <input type="number" step="0.01" min="0" value={form.price}
            onChange={e => setForm(p => ({ ...p, price: e.target.value }))}
            placeholder="0.00"
            className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Effective From</label>
          <input type="date" value={form.effective_from}
            onChange={e => setForm(p => ({ ...p, effective_from: e.target.value }))}
            className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Reason (optional)</label>
          <input type="text" value={form.change_reason}
            onChange={e => setForm(p => ({ ...p, change_reason: e.target.value }))}
            placeholder="e.g. Supplier rate revision"
            className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
        </div>
      </div>
      {isScheduled && (
        <div className="text-xs text-blue-600 bg-blue-50 rounded-lg px-3 py-2">
          ⏰ This price will activate automatically on next invoice/purchase after {form.effective_from}
        </div>
      )}
      <Button variant="primary" size="sm" loading={mutation.isPending}
        onClick={() => {
          if (!form.price || Number(form.price) <= 0) { toast.error('Enter valid price'); return }
          mutation.mutate({ price_type: form.price_type, price: Number(form.price),
            effective_from: form.effective_from, change_reason: form.change_reason || null })
        }}>
        {isScheduled ? 'Schedule Price' : 'Update Price'}
      </Button>
    </div>
  )
}

// ── Trend Card ────────────────────────────────────────────────
function TrendCard({ label, trend, color }) {
  if (!trend) return null
  const dir = trend.direction
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="text-xs font-medium text-gray-500 mb-1" style={{ color }}>{label}</div>
      <div className="text-xl font-bold text-gray-900">{fmt(trend.latest)}</div>
      <div className={clsx('text-xs mt-1 flex items-center gap-1',
        dir === 'up' ? 'text-red-500' : dir === 'down' ? 'text-green-500' : 'text-gray-400')}>
        {dir === 'up' ? <TrendingUp size={12} /> : dir === 'down' ? <TrendingDown size={12} /> : <Minus size={12} />}
        {trend.previous ? pct(trend.change_pct) : 'No previous data'}
      </div>
      <div className="text-xs text-gray-400 mt-2">
        Min: {fmt(trend.min)} · Max: {fmt(trend.max)} · Avg: {fmt(trend.avg)}
      </div>
    </div>
  )
}


// ── Scheduled Tab ─────────────────────────────────────────────
function ScheduledTab() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')  // debounced
  const [page, setPage] = useState(1)
  const [cancelTarget, setCancelTarget] = useState(null)  // {id, part_name, price_type_label, new_price, effective_from}

  // Debounce search
  const debounceRef = useRef(null)
  const handleSearch = (val) => {
    setSearch(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => { setQ(val); setPage(1) }, 350)
  }

  const { data, isLoading } = useQuery({
    queryKey: ['scheduled-prices', q, page],
    queryFn: () => {
      const params = new URLSearchParams({ page, page_size: 20 })
      if (q) params.append('search', q)
      return api.get(`/api/v1/price-history/scheduled/all?${params}`).then(r => r.data)
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (id) => api.delete(`/api/v1/price-history/scheduled/${id}`),
    onSuccess: () => {
      toast.success('Scheduled price cancelled')
      setCancelTarget(null)
      qc.invalidateQueries(['scheduled-prices'])
      qc.invalidateQueries(['price-history'])
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to cancel'),
  })

  const PRICE_COLORS = {
    purchase_cost: '#ef4444',
    b2b_price: '#3b82f6',
    b2c_price: '#8b5cf6',
    mrp: '#f59e0b',
  }

  return (
    <div className="space-y-3">
      {/* Header + Search */}
      <div className="card">
        <div className="card-body">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-sm font-semibold text-gray-800">All Scheduled Price Changes</div>
              <div className="text-xs text-gray-400 mt-0.5">
                Auto-activates on first invoice/purchase on or after effective date
              </div>
            </div>
            {data?.total > 0 && (
              <div className="text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1">
                {data.total} pending
              </div>
            )}
          </div>
          {/* Search */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input value={search} onChange={e => handleSearch(e.target.value)}
              placeholder="Search by product name or code..."
              className="w-full h-9 pl-9 pr-4 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            {search && (
              <button onClick={() => { setSearch(''); setQ(''); setPage(1) }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs">✕</button>
            )}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-10"><Spinner size={20} /></div>
        ) : !data?.items?.length ? (
          <div className="flex flex-col items-center py-12 text-gray-400 gap-2">
            <Calendar size={28} />
            <span className="text-sm">{q ? `No scheduled prices for "${q}"` : 'No scheduled price changes'}</span>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="py-2.5 px-4 text-left font-semibold text-gray-600">Product</th>
                    <th className="py-2.5 px-4 text-left font-semibold text-gray-600">Price Type</th>
                    <th className="py-2.5 px-4 text-right font-semibold text-gray-600">Current</th>
                    <th className="py-2.5 px-4 text-right font-semibold text-gray-600">New Price</th>
                    <th className="py-2.5 px-4 text-right font-semibold text-gray-600">Change</th>
                    <th className="py-2.5 px-4 text-left font-semibold text-gray-600">Effective</th>
                    <th className="py-2.5 px-4 text-left font-semibold text-gray-600">Reason</th>
                    <th className="py-2.5 px-4 text-left font-semibold text-gray-600">Scheduled by</th>
                    <th className="py-2.5 px-4 text-center font-semibold text-gray-600">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.items || []).map(item => (
                    <tr key={item.id} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="py-2.5 px-4">
                        <div className="font-medium text-gray-900">{item.part_name}</div>
                        <div className="text-gray-400 font-mono">{item.part_code}</div>
                      </td>
                      <td className="py-2.5 px-4">
                        <span className="font-medium" style={{ color: PRICE_COLORS[item.price_type] || '#666' }}>
                          {item.price_type_label}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-right font-mono text-gray-500">
                        {item.current_price ? fmt(item.current_price) : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-right font-mono font-semibold text-gray-900">
                        {fmt(item.new_price)}
                      </td>
                      <td className={clsx('py-2.5 px-4 text-right font-semibold',
                        item.change_pct == null ? 'text-gray-400'
                        : item.change_pct > 0 ? 'text-red-500'
                        : item.change_pct < 0 ? 'text-green-600'
                        : 'text-gray-400')}>
                        {item.change_pct != null
                          ? `${item.change_pct > 0 ? '+' : ''}${item.change_pct.toFixed(2)}%`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-4">
                        <div className="flex items-center gap-1.5">
                          <Calendar size={11} className="text-blue-400 shrink-0" />
                          <span className="text-blue-600 font-medium">{item.effective_from}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-gray-400 max-w-32 truncate">
                        {item.change_reason || '—'}
                      </td>
                      <td className="py-2.5 px-4 text-gray-500">
                        {item.scheduled_by || '—'}
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <button
                          onClick={() => setCancelTarget(item)}
                          className="text-xs px-2.5 py-1 rounded-lg border border-red-200 text-red-500 hover:bg-red-50 transition-colors">
                          Cancel
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {data.pages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
                <span className="text-xs text-gray-400">
                  Page {data.page} of {data.pages} · {data.total} total
                </span>
                <div className="flex gap-2">
                  <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                    className="text-xs px-3 py-1 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
                    ← Prev
                  </button>
                  <button disabled={page === data.pages} onClick={() => setPage(p => p + 1)}
                    className="text-xs px-3 py-1 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
                    Next →
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Cancel Confirmation Dialog */}
      {cancelTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl flex flex-col">
            <div className="flex items-center justify-between p-5 border-b flex-shrink-0">
              <h3 className="font-semibold text-gray-900">Cancel Scheduled Price</h3>
              <button onClick={() => setCancelTarget(null)} className="text-gray-400 hover:text-gray-600">✕</button>
            </div>
            <div className="p-5 space-y-3">
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-700">
                Are you sure you want to cancel this scheduled price change?
              </div>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Product</span>
                  <span className="font-medium">{cancelTarget.part_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Price Type</span>
                  <span className="font-medium" style={{ color: PRICE_COLORS[cancelTarget.price_type] }}>
                    {cancelTarget.price_type_label}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Scheduled Price</span>
                  <span className="font-medium">{fmt(cancelTarget.new_price)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Effective Date</span>
                  <span className="font-medium text-blue-600">{cancelTarget.effective_from}</span>
                </div>
              </div>
              <div className="text-xs text-gray-400">
                Current price will remain unchanged after cancellation.
              </div>
            </div>
            <div className="flex gap-3 p-5 border-t flex-shrink-0">
              <button onClick={() => setCancelTarget(null)}
                className="flex-1 h-9 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50">
                Keep it
              </button>
              <button
                onClick={() => cancelMutation.mutate(cancelTarget.id)}
                disabled={cancelMutation.isPending}
                className="flex-1 h-9 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-60 font-medium">
                {cancelMutation.isPending ? 'Cancelling...' : 'Yes, Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Recent Changes (super-admin) ──────────────────────────────
const RECENT_COLORS = {
  purchase_cost: '#ef4444', floor_price: '#10b981',
  b2b_price: '#3b82f6', b2c_price: '#8b5cf6', mrp: '#f59e0b',
}

function RecentChangesTab() {
  const monthStart = format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd')
  const today = format(new Date(), 'yyyy-MM-dd')
  const [fromDate, setFromDate] = useState(monthStart)
  const [toDate, setToDate] = useState(today)
  const [page, setPage] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['recent-price-changes', fromDate, toDate, page],
    queryFn: () => api.get('/api/v1/price-history/recent', {
      params: { from_date: fromDate, to_date: toDate, page, page_size: 20 },
    }).then(r => r.data),
    retry: 1,
  })

  const setRange = (from, to) => { setFromDate(from); setToDate(to); setPage(1) }

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="card">
        <div className="card-body">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-sm font-semibold text-gray-800">Recent Price Changes</div>
              <div className="text-xs text-gray-400 mt-0.5">
                Every product whose prices changed in the selected range — all entry points, scheduled included
              </div>
            </div>
            {data?.total > 0 && (
              <div className="text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1">
                {data.total} product{data.total > 1 ? 's' : ''}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500">From</label>
              <input type="date" value={fromDate} max={toDate}
                onChange={e => { setFromDate(e.target.value); setPage(1) }}
                className="h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500">To</label>
              <input type="date" value={toDate} min={fromDate} max={today}
                onChange={e => { setToDate(e.target.value); setPage(1) }}
                className="h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <button onClick={() => setRange(monthStart, today)}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">
              This month
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-10"><Spinner size={20} /></div>
        ) : isError ? (
          <div className="flex flex-col items-center py-12 text-red-400 gap-2">
            <AlertTriangle size={28} /><span className="text-sm">Failed to load recent changes</span>
          </div>
        ) : !data?.items?.length ? (
          <div className="flex flex-col items-center py-12 text-gray-400 gap-2">
            <TrendingUp size={28} /><span className="text-sm">No price changes in this range</span>
          </div>
        ) : (
          <>
            <div className="divide-y divide-gray-100">
              {data.items.map(prod => (
                <div key={prod.product_id} className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="font-medium text-gray-900">{prod.part_name}</span>
                      <span className="text-gray-400 font-mono text-xs ml-2">{prod.part_code}</span>
                    </div>
                    <span className="text-xs text-gray-400">last changed {prod.last_changed_at?.slice(0, 10)}</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="py-2 px-3 text-left font-semibold text-gray-600">Price Type</th>
                          <th className="py-2 px-3 text-right font-semibold text-gray-600">Old</th>
                          <th className="py-2 px-3 text-right font-semibold text-gray-600">New</th>
                          <th className="py-2 px-3 text-right font-semibold text-gray-600">Change</th>
                          <th className="py-2 px-3 text-left font-semibold text-gray-600">Effective</th>
                          <th className="py-2 px-3 text-left font-semibold text-gray-600">Reason</th>
                          <th className="py-2 px-3 text-left font-semibold text-gray-600">By</th>
                        </tr>
                      </thead>
                      <tbody>
                        {prod.changes.map((c, i) => (
                          <tr key={i} className="border-t border-gray-100">
                            <td className="py-2 px-3">
                              <span className="font-medium" style={{ color: RECENT_COLORS[c.price_type] || '#666' }}>
                                {c.price_type_label}
                              </span>
                              {c.is_scheduled && (
                                <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-200">
                                  Scheduled
                                </span>
                              )}
                            </td>
                            <td className="py-2 px-3 text-right font-mono text-gray-500">
                              {c.old_price != null ? fmt(c.old_price) : '—'}
                            </td>
                            <td className="py-2 px-3 text-right font-mono font-semibold text-gray-900">{fmt(c.new_price)}</td>
                            <td className={clsx('py-2 px-3 text-right font-semibold',
                              c.change_pct == null ? 'text-gray-400'
                              : c.change_pct > 0 ? 'text-red-500'
                              : c.change_pct < 0 ? 'text-green-600' : 'text-gray-400')}>
                              {c.change_pct != null ? `${c.change_pct > 0 ? '+' : ''}${c.change_pct.toFixed(2)}%` : '—'}
                            </td>
                            <td className="py-2 px-3 text-blue-600">{c.effective_from}</td>
                            <td className="py-2 px-3 text-gray-400 max-w-40 truncate">{c.change_reason || '—'}</td>
                            <td className="py-2 px-3 text-gray-500">{c.changed_by || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>

            {data.pages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
                <span className="text-xs text-gray-400">Page {data.page} of {data.pages} · {data.total} products</span>
                <div className="flex gap-2">
                  <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                    className="text-xs px-3 py-1 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">← Prev</button>
                  <button disabled={page === data.pages} onClick={() => setPage(p => p + 1)}
                    className="text-xs px-3 py-1 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">Next →</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────
export default function PriceTrendPage() {
  const { user, isSuperAdmin: _isSuper, isAdmin: _isAdmin } = useAuthStore()
  const isSuperAdmin = _isSuper()
  const isAdmin = _isAdmin()
  const qc = useQueryClient()
  const [selectedProduct, setSelectedProduct] = useState(null)
  const [showUpdateForm, setShowUpdateForm] = useState(false)
  const [activeView, setActiveView] = useState('trend')  // trend | history | scheduled | valuation | alerts
  const [alertFilter, setAlertFilter] = useState('all')  // all | unread | read
  const [alertType, setAlertType] = useState('all')      // all | gst_mismatch | low_margin | ...

  const { data, isLoading } = useQuery({
    queryKey: ['price-history', selectedProduct?.id],
    queryFn: () => api.get(`/api/v1/price-history/${selectedProduct.id}`).then(r => r.data),
    enabled: Boolean(selectedProduct?.id),
  })

  const { data: valuation, isLoading: valLoading } = useQuery({
    queryKey: ['stock-valuation'],
    queryFn: () => api.get('/api/v1/price-history/valuation/stock').then(r => r.data),
    enabled: activeView === 'valuation' && isAdmin,
  })

  const { data: alerts, isLoading: alertsLoading } = useQuery({
    queryKey: ['price-alerts'],
    queryFn: () => api.get('/api/v1/price-history/alerts').then(r => r.data),
    enabled: isAdmin,
    refetchInterval: 60000,
  })

  const markReadMutation = useMutation({
    mutationFn: (id) => id === 'all'
      ? api.post('/api/v1/price-history/alerts/read-all')
      : api.post(`/api/v1/price-history/alerts/${id}/read`),
    onSuccess: () => qc.invalidateQueries(['price-alerts']),
  })

  const toggleReadMutation = useMutation({
    mutationFn: ({ id, read }) => api.post(`/api/v1/price-history/alerts/${id}/${read ? 'read' : 'unread'}`),
    onSuccess: () => qc.invalidateQueries(['price-alerts']),
  })

  // Build chart data from history
  const chartData = (() => {
    if (!data?.history) return []
    const byDate = {}
    for (const h of data.history) {
      if (h.is_scheduled) continue
      const d = h.effective_from
      if (!byDate[d]) byDate[d] = { date: d }
      byDate[d][h.price_type] = h.price
    }
    return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date))
  })()

  const unreadCount = alerts?.filter(a => !a.is_read).length || 0
  const alertTypes = Array.from(new Set((alerts || []).map(a => a.alert_type)))
  const filteredAlerts = (alerts || []).filter(a =>
    (alertFilter === 'all' || (alertFilter === 'unread' ? !a.is_read : a.is_read)) &&
    (alertType === 'all' || a.alert_type === alertType)
  )

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Price Trend</h1>
          <p className="text-xs text-gray-400 mt-0.5">Multi-type pricing with effective date and FIFO valuation</p>
        </div>
        {isAdmin && unreadCount > 0 && (
          <button onClick={() => setActiveView('alerts')}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-50 border border-red-200 text-red-600 text-xs font-medium hover:bg-red-100">
            <Bell size={14} /> {unreadCount} Alert{unreadCount > 1 ? 's' : ''}
          </button>
        )}
      </div>

      {/* View Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {[
          { id: 'trend', label: 'Trend Chart' },
          { id: 'history', label: 'Price History' },
          { id: 'scheduled', label: 'Scheduled' },
          ...(isSuperAdmin ? [{ id: 'recent', label: 'Recent Changes' }] : []),
          ...(isAdmin ? [{ id: 'valuation', label: 'Stock Valuation' }] : []),
          ...(isAdmin ? [{ id: 'alerts', label: `Alerts${unreadCount > 0 ? ` (${unreadCount})` : ''}` }] : []),
        ].map(tab => (
          <button key={tab.id} onClick={() => setActiveView(tab.id)}
            className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              activeView === tab.id ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Scheduled Prices — standalone, no product needed */}
      {activeView === 'scheduled' && <ScheduledTab />}

      {/* Recent Changes — super-admin, all products, date-range filtered */}
      {activeView === 'recent' && isSuperAdmin && <RecentChangesTab />}

      {/* Stock Valuation view (no product needed) */}
      {activeView === 'valuation' && (
        <div className="card">
          <div className="card-header">
            <div className="text-sm font-semibold">Stock Valuation — FIFO vs Latest Cost</div>
          </div>
          <div className="card-body">
            {valLoading ? <Spinner /> : valuation ? (
              <>
                {/* Summary */}
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="bg-blue-50 rounded-xl p-3 text-center">
                    <div className="text-xs text-blue-500 font-medium">FIFO Value</div>
                    <div className="text-lg font-bold text-blue-700">{fmt(valuation.summary?.total_fifo_value)}</div>
                  </div>
                  <div className="bg-purple-50 rounded-xl p-3 text-center">
                    <div className="text-xs text-purple-500 font-medium">Latest Cost Value</div>
                    <div className="text-lg font-bold text-purple-700">{fmt(valuation.summary?.total_latest_value)}</div>
                  </div>
                  <div className={clsx('rounded-xl p-3 text-center',
                    (valuation.summary?.difference || 0) >= 0 ? 'bg-green-50' : 'bg-red-50')}>
                    <div className="text-xs font-medium text-gray-500">Difference</div>
                    <div className={clsx('text-lg font-bold',
                      (valuation.summary?.difference || 0) >= 0 ? 'text-green-700' : 'text-red-700')}>
                      {fmt(valuation.summary?.difference)}
                    </div>
                  </div>
                </div>
                {/* Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        {['Product', 'Qty', 'FIFO Unit Cost', 'FIFO Value', 'Latest Cost', 'Latest Value', 'B2B Price',
                          ...(isSuperAdmin ? ['FIFO Margin', 'Latest Margin'] : [])].map(h => (
                          <th key={h} className="py-2 px-3 text-left font-semibold text-gray-600">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {valuation.items?.map(item => (
                        <tr key={item.product_id} className="border-t border-gray-100 hover:bg-gray-50">
                          <td className="py-2 px-3">
                            <div className="font-medium">{item.part_name}</div>
                            <div className="text-gray-400">{item.part_code}</div>
                          </td>
                          <td className="py-2 px-3">{item.qty}</td>
                          <td className="py-2 px-3 font-mono">{fmt(item.fifo_unit_cost)}</td>
                          <td className="py-2 px-3 font-mono font-semibold">{fmt(item.fifo_value)}</td>
                          <td className="py-2 px-3 font-mono">{fmt(item.latest_cost)}</td>
                          <td className="py-2 px-3 font-mono">{fmt(item.latest_value)}</td>
                          <td className="py-2 px-3 font-mono">{fmt(item.b2b_price)}</td>
                          {isSuperAdmin && (
                            <>
                              <td className={clsx('py-2 px-3 font-semibold',
                                (item.fifo_margin_pct || 0) < 0 ? 'text-red-600' : 'text-green-600')}>
                                {item.fifo_margin_pct != null ? `${item.fifo_margin_pct}%` : '—'}
                              </td>
                              <td className={clsx('py-2 px-3 font-semibold',
                                (item.latest_margin_pct || 0) < 0 ? 'text-red-600' : 'text-green-600')}>
                                {item.latest_margin_pct != null ? `${item.latest_margin_pct}%` : '—'}
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : <div className="text-center text-gray-400 py-8">No stock data</div>}
          </div>
        </div>
      )}

      {/* Alerts view */}
      {activeView === 'alerts' && isAdmin && (
        <div className="card">
          <div className="card-header flex items-center justify-between gap-2 flex-wrap">
            <div className="text-sm font-semibold">Price Alerts</div>
            <div className="flex items-center gap-2">
              <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
                {['all', 'unread', 'read'].map(f => (
                  <button key={f} onClick={() => setAlertFilter(f)}
                    className={clsx('px-2.5 py-1 rounded-md text-xs font-medium capitalize transition-colors',
                      alertFilter === f ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
                    {f}{f === 'unread' && unreadCount ? ` (${unreadCount})` : ''}
                  </button>
                ))}
              </div>
              {alertTypes.length > 1 && (
                <select value={alertType} onChange={e => setAlertType(e.target.value)}
                  className="h-7 px-2 rounded-md border border-gray-300 text-xs text-gray-600 focus:outline-none focus:border-blue-500">
                  <option value="all">All types</option>
                  {alertTypes.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
                </select>
              )}
              {unreadCount > 0 && (
                <Button variant="secondary" size="sm" onClick={() => markReadMutation.mutate('all')}>
                  Mark all read
                </Button>
              )}
            </div>
          </div>
          <div className="card-body">
            {alertsLoading ? <Spinner /> : filteredAlerts.length ? (
              <div className="space-y-2">
                {filteredAlerts.map(a => (
                  <div key={a.id} className={clsx('rounded-lg border px-4 py-3 flex items-start justify-between',
                    SEVERITY_COLORS[a.severity] || SEVERITY_COLORS.warning,
                    a.is_read && 'opacity-50')}>
                    <div>
                      <div className="text-xs font-semibold flex items-center gap-2">
                        <span>{a.part_name} · {a.part_code}</span>
                        {a.is_read
                          ? <span className="px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 text-[10px] font-medium">Read</span>
                          : <span className="px-1.5 py-0.5 rounded bg-red-500 text-white text-[10px] font-medium">Unread</span>}
                      </div>
                      <div className="text-xs mt-0.5">{a.message}</div>
                      <div className="text-xs opacity-60 mt-1">{a.created_at?.slice(0, 16)}</div>
                    </div>
                    <button onClick={() => toggleReadMutation.mutate({ id: a.id, read: !a.is_read })}
                      disabled={toggleReadMutation.isPending}
                      className="ml-3 text-xs font-medium opacity-70 hover:opacity-100 hover:underline shrink-0 whitespace-nowrap">
                      {a.is_read ? 'Mark unread' : 'Mark read'}
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-400 flex flex-col items-center gap-2">
                <BellOff size={24} />
                <span>{alertFilter === 'all' && alertType === 'all' ? 'No alerts' : 'No matching alerts'}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Product-specific views */}
      {(activeView === 'trend' || activeView === 'history') && (
        <>
          {/* Product Search */}
          <div className="card" style={{ overflow: 'visible' }}>
            <div className="card-body" style={{ overflow: 'visible' }}>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-medium text-gray-600">Select Product</label>
                {selectedProduct && isAdmin && (
                  <button onClick={() => setShowUpdateForm(p => !p)}
                    className="text-xs text-blue-600 hover:underline">
                    {showUpdateForm ? 'Hide' : '+ Update Price'}
                  </button>
                )}
              </div>
              <ProductSearch onSelect={(p) => { setSelectedProduct(p); setShowUpdateForm(false) }} />
              {selectedProduct && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-800">{selectedProduct.part_name}</span>
                  <span className="text-xs text-gray-400">{selectedProduct.part_code}</span>
                  <button onClick={() => setSelectedProduct(null)} className="text-xs text-gray-400 hover:text-gray-600">✕</button>
                </div>
              )}
            </div>
          </div>

          {/* Price Update Form */}
          {showUpdateForm && selectedProduct && isAdmin && (
            <PriceUpdateForm
              productId={selectedProduct.id}
              currentPrices={data?.current || {}}
              onSuccess={() => { qc.invalidateQueries(['price-history', selectedProduct.id]); setShowUpdateForm(false) }}
            />
          )}

          {isLoading && <div className="flex justify-center py-8"><Spinner size={24} /></div>}

          {data && (
            <>
              {/* Current Prices */}
              <div className="grid grid-cols-4 gap-3">
                {PRICE_TYPES.map(pt => (
                  <TrendCard key={pt.key} label={pt.label} trend={data.trends?.[pt.key]} color={pt.color} />
                ))}
              </div>

              {/* Scheduled prices banner */}
              {data.scheduled?.length > 0 && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
                  <div className="text-xs font-semibold text-blue-700 mb-2 flex items-center gap-1.5">
                    <Calendar size={12} /> {data.scheduled.length} Scheduled Price Change(s)
                  </div>
                  <div className="space-y-1">
                    {data.scheduled.map((s, i) => (
                      <div key={i} className="text-xs text-blue-600">
                        {PRICE_TYPES.find(p => p.key === s.price_type)?.label || s.price_type}: {fmt(s.price)} — effective {s.effective_from}
                        {s.reason && <span className="text-blue-400 ml-1">({s.reason})</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Trend Chart */}
              {activeView === 'trend' && (
                <div className="card">
                  <div className="card-header">
                    <div className="text-sm font-semibold">Price Trend — {data.part_name}</div>
                  </div>
                  <div className="card-body">
                    {chartData.length < 2 ? (
                      <div className="text-center text-gray-400 py-8">
                        {chartData.length === 0 ? 'No price history yet. Prices are recorded when purchases are created.' : 'Need at least 2 data points for trend chart.'}
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height={320}>
                        <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `₹${v}`} />
                          <Tooltip formatter={(v, name) => [fmt(v), PRICE_TYPES.find(p => p.key === name)?.label || name]} />
                          <Legend formatter={name => PRICE_TYPES.find(p => p.key === name)?.label || name} />
                          {PRICE_TYPES.map(pt => (
                            <Line key={pt.key} type="monotone" dataKey={pt.key}
                              stroke={pt.color} strokeWidth={2} dot={{ r: 4 }}
                              connectNulls activeDot={{ r: 6 }} />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>
              )}

              {/* History Table */}
              {activeView === 'history' && (
                <div className="card">
                  <div className="card-header">
                    <div className="text-sm font-semibold">Price Change History</div>
                    {!isSuperAdmin && <div className="text-xs text-gray-400">Full audit trail visible to super-admin only</div>}
                  </div>
                  <div className="card-body p-0">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr>
                          {['Price Type', 'New Price', 'Previous', 'Change%', 'Effective From', 'Status',
                            ...(isSuperAdmin ? ['Changed By', 'Reason'] : [])
                          ].map(h => (
                            <th key={h} className="py-2 px-3 text-left font-semibold text-gray-600">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.history?.filter(h => !h.is_scheduled || isSuperAdmin).map(h => (
                          <tr key={h.id} className={clsx('border-t border-gray-100',
                            h.is_scheduled ? 'bg-blue-50/50' : '')}>
                            <td className="py-2 px-3">
                              <span className="font-medium" style={{
                                color: PRICE_TYPES.find(p => p.key === h.price_type)?.color || '#666'
                              }}>{h.price_type_label}</span>
                            </td>
                            <td className="py-2 px-3 font-mono font-semibold">{fmt(h.price)}</td>
                            <td className="py-2 px-3 font-mono text-gray-400">{h.previous_price ? fmt(h.previous_price) : '—'}</td>
                            <td className={clsx('py-2 px-3 font-semibold',
                              h.change_pct > 0 ? 'text-red-500' : h.change_pct < 0 ? 'text-green-500' : 'text-gray-400')}>
                              {h.change_pct != null ? pct(h.change_pct) : '—'}
                            </td>
                            <td className="py-2 px-3">{h.effective_from}</td>
                            <td className="py-2 px-3">
                              {h.is_scheduled
                                ? <span className="text-blue-600 font-medium">Scheduled</span>
                                : h.is_active
                                  ? <span className="text-green-600 font-medium">Active</span>
                                  : <span className="text-gray-400">Expired</span>}
                            </td>
                            {isSuperAdmin && <>
                              <td className="py-2 px-3 text-gray-500">{h.changed_by || '—'}</td>
                              <td className="py-2 px-3 text-gray-400">{h.change_reason || '—'}</td>
                            </>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}


            </>
          )}
        </>
      )}
    </div>
  )
}