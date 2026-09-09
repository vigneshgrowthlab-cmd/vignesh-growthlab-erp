import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { productAPI, categoryAPI } from '@/api'
import { useAuthStore } from '@/store/authStore'
import {
  Button, Badge, Pagination, Empty, Spinner, Input, Select, ConfirmDialog
} from '@/components/ui'
import { Plus, Upload, Download, Search, Filter, TrendingUp, Package2, Eye, IndianRupee } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'

export default function ProductsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { isAdmin, isSuperAdmin, canSee } = useAuthStore()

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [isActive, setIsActive] = useState(true)
  const [uploadModal, setUploadModal] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [bulkModal, setBulkModal] = useState(false)

  const { data: cats } = useQuery({
    queryKey: ['categories'],
    queryFn: () => categoryAPI.list().then(r => r.data),
  })

  const { data, isLoading } = useQuery({
    queryKey: ['products', page, search, categoryId, lowStockOnly, isActive],
    queryFn: () => productAPI.list({
      page, page_size: 20, search: search || undefined,
      category_id: categoryId || undefined,
      low_stock_only: lowStockOnly, is_active: isActive,
    }).then(r => r.data),
    // React Query v5: keepPreviousData was renamed to placeholderData
    // helper. Keeps the previous page visible while a new query is in flight.
    placeholderData: keepPreviousData,
  })

  const { data: alerts } = useQuery({
    queryKey: ['cost-alerts'],
    queryFn: () => productAPI.pendingAlerts().then(r => r.data),
    enabled: isSuperAdmin(),
  })

  const pageIds = data?.items?.map(p => p.id) || []
  const allOnPageSelected = pageIds.length > 0 && pageIds.every(id => selected.has(id))
  const toggleOne = (id) => setSelected(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  })
  const toggleAll = () => setSelected(prev => {
    const n = new Set(prev)
    if (allOnPageSelected) pageIds.forEach(id => n.delete(id))
    else pageIds.forEach(id => n.add(id))
    return n
  })

  const downloadTemplate = async () => {
    const res = await productAPI.downloadTemplate()
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a'); a.href = url; a.download = 'product_template.csv'; a.click()
  }

  const exportCsv = async () => {
    try {
      const res = await productAPI.exportCsv({
        category_id: categoryId || undefined,
        search: search || undefined,
        is_active: isActive,
      })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const a = document.createElement('a'); a.href = url; a.download = 'products_export.csv'; a.click()
    } catch {
      toast.error('Export failed')
    }
  }

  const gstColor = (gst) => {
    if (gst >= 28) return 'red'
    if (gst >= 18) return 'amber'
    if (gst >= 12) return 'blue'
    return 'green'
  }

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="breadcrumb">Products & Inventory</div>
          <h1 className="page-title">Products</h1>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin() && (
            <>
              {selected.size > 0 && (
                <Button variant="secondary" size="sm" onClick={() => setBulkModal(true)}>
                  <IndianRupee size={14} /> Update Prices ({selected.size})
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={exportCsv}>
                <Download size={14} /> Export CSV
              </Button>
              <Button variant="secondary" size="sm" onClick={downloadTemplate}>
                <Download size={14} /> Template
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setUploadModal(true)}>
                <Upload size={14} /> Bulk Upload
              </Button>
              <Button variant="primary" onClick={() => navigate('/products/new')}>
                <Plus size={14} /> New Product
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Cost alerts banner */}
      {alerts?.length > 0 && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2 text-amber-700 text-sm">
          <TrendingUp size={16} />
          <span><strong>{alerts.length}</strong> cost or margin alert{alerts.length > 1 ? 's' : ''} need attention</span>
        </div>
      )}

      {/* Filters */}
      <div className="card mb-4">
        <div className="p-4 flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input
              placeholder="Search by name or part code..."
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              className="pl-8"
            />
          </div>
          <Select value={categoryId} onChange={e => { setCategoryId(e.target.value); setPage(1) }} className="w-44">
            <option value="">All categories</option>
            {cats?.map(c => <option key={c.id} value={c.id}>{c.name}{c.prefix ? ` (${c.prefix})` : ''}</option>)}
          </Select>
          <Select value={String(isActive)} onChange={e => { setIsActive(e.target.value === 'true'); setPage(1) }} className="w-32">
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </Select>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" checked={lowStockOnly} onChange={e => setLowStockOnly(e.target.checked)}
              className="rounded border-gray-300" />
            Low stock only
          </label>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        {isLoading || !data ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : data.items?.length === 0 ? (
          <Empty message="No products found" action={
            isAdmin() && <Button variant="primary" onClick={() => navigate('/products/new')}><Plus size={14} />New Product</Button>
          } />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    {isAdmin() && (
                      <th className="w-8">
                        <input type="checkbox" checked={allOnPageSelected} onChange={toggleAll}
                          className="rounded border-gray-300" />
                      </th>
                    )}
                    <th>Part Code</th>
                    <th>Product Name</th>
                    <th>Category</th>
                    <th>HSN</th>
                    <th>GST %</th>
                    {canSee('purchase_cost') && <th className="text-right">Cost (₹)</th>}
                    <th className="text-right">Price (₹)</th>
                    <th className="text-right">Stock</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.map(p => (
                    <tr key={p.id} className="cursor-pointer" onClick={() => navigate(`/products/${p.id}`)}>
                      {isAdmin() && (
                        <td onClick={e => e.stopPropagation()}>
                          <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleOne(p.id)}
                            className="rounded border-gray-300" />
                        </td>
                      )}
                      <td>
                        <span className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-700">
                          {p.part_code}
                        </span>
                      </td>
                      <td className="font-medium text-gray-900">{p.part_name}</td>
                      <td className="text-gray-500">{p.category_name}</td>
                      <td className="font-mono text-xs text-gray-500">{p.hsn_code}</td>
                      <td><Badge color={gstColor(p.gst_percent)}>{p.gst_percent}%</Badge></td>
                      {canSee('purchase_cost') && (
                        <td className="text-right text-gray-700">₹{Number(p.purchase_cost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      )}
                      <td className="text-right font-medium">₹{Number(p.b2b_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      <td className="text-right">
                        <span className={clsx('font-medium', Number(p.total_stock) === 0 && 'text-danger')}>
                          {Number(p.total_stock).toFixed(0)} {p.unit_of_measure}
                        </span>
                      </td>
                      <td>
                        <Badge color={p.is_active ? 'green' : 'gray'}>
                          {p.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <button onClick={() => navigate(`/products/${p.id}`)}
                            className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                            <Eye size={14} />
                          </button>
                          {isAdmin() && (
                            <button onClick={() => navigate(`/products/${p.id}/cost-trend`)}
                              className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-amber-600"
                              title="Cost trend">
                              <TrendingUp size={14} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={data.page} pages={data.pages} total={data.total}
              pageSize={20} onChange={setPage} />
          </>
        )}
      </div>

      {/* Stats */}
      {data && (
        <div className="mt-4 grid grid-cols-4 gap-3">
          <div className="stat-card">
            <div className="stat-label">Total products</div>
            <div className="stat-value">{data.total}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Out of stock (this page)</div>
            <div className="stat-value text-danger">{data.items?.filter(p => Number(p.total_stock) === 0).length}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Categories</div>
            <div className="stat-value">{cats?.length || 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Pending alerts</div>
            <div className="stat-value text-amber-600">{alerts?.length || 0}</div>
          </div>
        </div>
      )}

      {/* Bulk upload modal */}
      {uploadModal && <BulkUploadModal onClose={() => setUploadModal(false)} />}

      {/* Bulk price update modal */}
      {bulkModal && (
        <BulkPriceModal
          productIds={[...selected]}
          onClose={() => setBulkModal(false)}
          onDone={() => { setSelected(new Set()); setBulkModal(false) }}
        />
      )}
    </div>
  )
}

const PRICE_TYPE_OPTIONS = [
  { value: 'b2b_price',    label: 'B2B Price' },
  { value: 'b2c_price',    label: 'B2C Price' },
  { value: 'mrp',          label: 'MRP' },
  { value: 'floor_price',  label: 'Floor Price' },
  { value: 'purchase_cost', label: 'Purchase Cost' },
]

function BulkPriceModal({ productIds, onClose, onDone }) {
  const qc = useQueryClient()
  const [priceType, setPriceType] = useState('b2b_price')
  const [price, setPrice] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const submit = async () => {
    const p = Number(price)
    if (!p || p <= 0) { toast.error('Enter a price greater than 0'); return }
    setLoading(true)
    try {
      const { data } = await productAPI.bulkPriceUpdate({
        product_ids: productIds,
        price_type: priceType,
        price: p,
        effective_from: effectiveFrom || undefined,
        change_reason: reason || undefined,
      })
      setResult(data)
      qc.invalidateQueries(['products'])
      const msg = data.is_scheduled ? `${data.scheduled} scheduled` : `${data.updated} updated`
      if (data.skipped > 0) toast(`${msg}, ${data.skipped} skipped`, { icon: '⚠️' })
      else toast.success(msg)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Bulk update failed')
    } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="bg-white rounded-xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold">Update Prices — {productIds.length} product{productIds.length > 1 ? 's' : ''}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-400"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Price type</label>
              <Select value={priceType} onChange={e => setPriceType(e.target.value)}>
                {PRICE_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">New price (₹)</label>
              <Input type="number" step="0.01" min="0" value={price}
                onChange={e => setPrice(e.target.value)} placeholder="0.00" />
            </div>
          </div>
          {!['purchase_cost'].includes(priceType) && (
            <p className="text-xs text-gray-400 -mt-1">
              Products where this price would break the tier order (cost ≤ floor ≤ B2B ≤ B2C ≤ MRP) will be skipped and listed below.
            </p>
          )}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Effective from <span className="text-gray-400 font-normal">(blank = today; a future date schedules it)</span>
            </label>
            <Input type="date" value={effectiveFrom} onChange={e => setEffectiveFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Reason <span className="text-gray-400 font-normal">(optional)</span></label>
            <Input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Q2 price revision" />
          </div>

          {result && (
            <div className={clsx(
              'p-3 rounded-lg text-sm',
              result.skipped === 0 ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'
            )}>
              <div className="font-medium mb-1">
                {result.is_scheduled
                  ? `${result.scheduled} scheduled for ${result.effective_from}`
                  : `${result.updated} updated`}
                {result.skipped > 0 && ` · ${result.skipped} skipped`}
              </div>
              {result.errors?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {result.errors.slice(0, 5).map((e, i) => (
                    <div key={i} className="text-xs bg-white/60 rounded px-2 py-1">
                      <span className="font-mono font-medium">{e.part_code || `#${e.product_id}`}</span>
                      <span className="text-gray-500 ml-1">— {e.error}</span>
                    </div>
                  ))}
                  {result.errors.length > 5 && (
                    <div className="text-xs opacity-70">…and {result.errors.length - 5} more</div>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3 justify-end">
            {result ? (
              <>
                {result.skipped > 0 && (
                  <Button variant="secondary" onClick={() => setResult(null)}>Try again</Button>
                )}
                <Button variant="primary" onClick={onDone}>Done</Button>
              </>
            ) : (
              <>
                <Button variant="secondary" onClick={onClose}>Cancel</Button>
                <Button variant="primary" loading={loading} onClick={submit} disabled={loading}>
                  Apply to {productIds.length}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Keep this in sync with backend settings.MAX_UPLOAD_SIZE_MB
const MAX_UPLOAD_MB = 10

function BulkUploadModal({ onClose }) {
  const qc = useQueryClient()
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const onFileSelect = (f) => {
    if (!f) { setFile(null); setResult(null); return }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast.error(`File too large (${(f.size / 1024 / 1024).toFixed(1)} MB). Max ${MAX_UPLOAD_MB} MB.`)
      return
    }
    setFile(f)
    setResult(null)
  }

  const upload = async () => {
    if (!file) return
    setLoading(true)
    try {
      const { data } = await productAPI.bulkUpload(file)
      setResult(data)
      if (data.success_count > 0) {
        qc.invalidateQueries(['products'])
      }
      const skipped = data.skipped_count || 0
      if (data.error_count === 0 && skipped === 0) {
        toast.success(`${data.success_count} products imported successfully`)
      } else if (data.success_count > 0 || (skipped > 0 && data.error_count === 0)) {
        toast(`${data.success_count} imported, ${skipped} skipped, ${data.error_count} failed`, { icon: '⚠️' })
      } else {
        toast.error(`All ${data.error_count} rows failed — see details`)
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="bg-white rounded-xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold">Bulk Upload Products</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-400"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="p-4 border-2 border-dashed border-gray-200 rounded-lg text-center">
            <Upload size={24} className="mx-auto text-gray-300 mb-2" />
            <label className="cursor-pointer">
              <span className="text-sm text-primary underline">Choose CSV file</span>
              <input type="file" accept=".csv" className="hidden"
                onChange={e => onFileSelect(e.target.files[0])} />
            </label>
            {file && <div className="mt-2 text-xs text-gray-500">{file.name} ({(file.size / 1024).toFixed(1)} KB)</div>}
            <div className="mt-1 text-xs text-gray-400">Max file size {MAX_UPLOAD_MB} MB</div>
          </div>

          {result && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2 text-xs font-medium">
                <span className="px-2.5 py-1 rounded-full bg-green-100 text-green-700">
                  {result.success_count} imported
                </span>
                {result.skipped_count > 0 && (
                  <span className="px-2.5 py-1 rounded-full bg-amber-100 text-amber-800">
                    {result.skipped_count} skipped
                  </span>
                )}
                {result.error_count > 0 && (
                  <span className="px-2.5 py-1 rounded-full bg-red-100 text-red-700">
                    {result.error_count} failed
                  </span>
                )}
              </div>

              {result.skipped?.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 overflow-hidden">
                  <div className="px-3 py-2 bg-amber-100 text-amber-800 text-xs font-semibold">
                    Skipped rows (already exist — not imported)
                  </div>
                  <div className="max-h-44 overflow-y-auto divide-y divide-amber-100">
                    {result.skipped.map((s, i) => (
                      <div key={`s${i}`} className="px-3 py-1.5 text-xs text-amber-900 flex gap-2">
                        <span className="font-mono text-amber-500 shrink-0">Row {s.row}</span>
                        <span className="font-medium shrink-0">{s.data}</span>
                        <span className="text-amber-700">— {s.reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.errors?.length > 0 && (
                <div className="rounded-lg border border-red-200 bg-red-50 overflow-hidden">
                  <div className="px-3 py-2 bg-red-100 text-red-700 text-xs font-semibold">
                    Failed rows (fix and re-upload)
                  </div>
                  <div className="max-h-44 overflow-y-auto divide-y divide-red-100">
                    {result.errors.map((e, i) => (
                      <div key={`e${i}`} className="px-3 py-1.5 text-xs text-red-900 flex gap-2">
                        <span className="font-mono text-red-400 shrink-0">Row {e.row}</span>
                        {e.data && <span className="font-medium shrink-0">{e.data}</span>}
                        <span className="text-red-700">— {e.errors.join(', ')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3 justify-end">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="primary" loading={loading} onClick={upload} disabled={!file || loading}>
              Upload & Import
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function X({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  )
}
