import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { productAPI, categoryAPI } from '@/api'
import { settingsAPI } from '@/api/settings'
import { Button, Spinner } from '@/components/ui'
import { Save, ArrowLeft, Plus, X, Upload, Trash2, Image as ImageIcon, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'

const FALLBACK_GST_RATES = [0, 5, 12, 18, 28]
const UOM_OPTIONS = ['Nos', 'Kg', 'Gm', 'Ltr', 'Mtr', 'Box', 'Pcs', 'Set', 'Pair', 'Roll', 'Bag']

const ic = (err) => clsx(
  'w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-2 transition-colors',
  err ? 'border-red-400 focus:ring-red-500/20' : 'border-gray-300 focus:ring-blue-500/20 focus:border-blue-500'
)

function NewCategoryInline({ onCreated }) {
  const qc = useQueryClient()
  const [show, setShow] = useState(false)
  const { data: gstRates = FALLBACK_GST_RATES } = useQuery({
    queryKey: ['gst-rates'],
    queryFn: () => settingsAPI.getGstRates().then(r => r.data.map(x => x.rate)),
    staleTime: 5 * 60 * 1000,
  })
  const [form, setForm] = useState({ name: '', prefix: '', default_hsn: '', default_gst_percent: '18' })
  const [errors, setErrors] = useState({})

  const mutation = useMutation({
    mutationFn: (d) => categoryAPI.create(d),
    onSuccess: (res) => {
      qc.setQueryData(['categories'], (old) => old ? [...old, res.data] : [res.data])
      qc.invalidateQueries(['categories'])
      toast.success(`Category created`)
      setShow(false)
      setForm({ name: '', prefix: '', default_hsn: '', default_gst_percent: '18' })
      onCreated(res.data)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const handle = () => {
    const errs = {}
    if (!form.name.trim()) errs.name = 'Required'
    if (!form.prefix.trim()) errs.prefix = 'Required'
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    mutation.mutate({
      name: form.name.trim(),
      prefix: form.prefix.trim().toUpperCase(),
      default_hsn: form.default_hsn || null,
      default_gst_percent: Number(form.default_gst_percent) || 18,
    })
  }

  return (
    <div>
      <button type="button" onClick={() => setShow(!show)}
        className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1 mt-1">
        <Plus size={11} /> Create new category
      </button>
      {show && (
        <div className="mt-2 p-3 bg-blue-50 border border-blue-200 rounded-lg space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs font-semibold text-blue-800">New Category</span>
            <button onClick={() => setShow(false)} className="text-blue-400"><X size={12} /></button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-red-500">*</span></label>
              <input value={form.name}
                onChange={e => { setForm(p => ({ ...p, name: e.target.value })); setErrors(p => ({ ...p, name: '' })) }}
                placeholder="Electronics"
                className={clsx('w-full h-8 px-2 rounded border text-sm', errors.name ? 'border-red-400' : 'border-gray-300')} />
              {errors.name && <p className="text-xs text-red-500">{errors.name}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Prefix <span className="text-red-500">*</span></label>
              <input value={form.prefix}
                onChange={e => { setForm(p => ({ ...p, prefix: e.target.value.toUpperCase() })); setErrors(p => ({ ...p, prefix: '' })) }}
                placeholder="ELEC" maxLength={4}
                className={clsx('w-full h-8 px-2 rounded border text-sm font-mono', errors.prefix ? 'border-red-400' : 'border-gray-300')} />
              {errors.prefix && <p className="text-xs text-red-500">{errors.prefix}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Default HSN</label>
              <input value={form.default_hsn} onChange={e => setForm(p => ({ ...p, default_hsn: e.target.value }))}
                placeholder="85171200" maxLength={8}
                className="w-full h-8 px-2 rounded border border-gray-300 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Default GST %</label>
              <select value={form.default_gst_percent} onChange={e => setForm(p => ({ ...p, default_gst_percent: e.target.value }))}
                className="w-full h-8 px-2 rounded border border-gray-300 text-sm">
                {gstRates.map(r => <option key={r} value={String(r)}>{r}%</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShow(false)} className="px-3 h-7 text-xs rounded border border-gray-300 text-gray-600">Cancel</button>
            <button onClick={handle} disabled={mutation.isPending}
              className="px-3 h-7 text-xs rounded bg-blue-600 text-white disabled:opacity-60">
              {mutation.isPending ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ProductFormPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const { canSee, isAdmin, isSuperAdmin } = useAuthStore()
  const showProfit = isAdmin()
  // Profit/margin figures (profit value, margin %, min-margin, floor price)
  // are restricted to super-admin only.
  const showProfitFigures = isSuperAdmin()
  const isEdit = Boolean(id)
  const qc = useQueryClient()

  const { data: gstRates = FALLBACK_GST_RATES } = useQuery({
    queryKey: ['gst-rates'],
    queryFn: () => settingsAPI.getGstRates().then(r => r.data.map(x => x.rate)),
    staleTime: 5 * 60 * 1000,
  })

  const [form, setForm] = useState({
    part_name: '', category_id: '', unit_of_measure: 'Nos',
    hsn_code: '', gst_percent: '18',
    purchase_cost: '0', b2b_price: '0', b2c_price: '0', mrp: '0', floor_price: '0',
    low_stock_threshold: '10', cost_alert_threshold_pct: '5',
    min_margin_pct: '10',
    description: '', is_active: true,
  })
  const [errors, setErrors] = useState({})
  const [partCodePreview, setPartCodePreview] = useState('')
  const [imgBusy, setImgBusy] = useState(false)
  // Loaded-product price anchor — edit-mode cost changes re-scale from this
  // baseline (not the live values), so repeated edits don't compound.
  const [priceBaseline, setPriceBaseline] = useState(null)
  const [autoScaled, setAutoScaled] = useState(false)
  const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  const onImageSelect = async (file) => {
    if (!file) return
    if (!['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'].includes(file.type)) {
      toast.error('Please choose a PNG, JPG, WebP or GIF image'); return
    }
    if (file.size > 10 * 1024 * 1024) { toast.error('Image too large (max 10 MB)'); return }
    setImgBusy(true)
    try {
      await productAPI.uploadImage(id, file)
      await qc.invalidateQueries(['product', id])
      qc.invalidateQueries(['products'])
      toast.success('Image uploaded')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Upload failed')
    } finally { setImgBusy(false) }
  }

  const onImageRemove = async () => {
    setImgBusy(true)
    try {
      await productAPI.deleteImage(id)
      await qc.invalidateQueries(['product', id])
      qc.invalidateQueries(['products'])
      toast.success('Image removed')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to remove image')
    } finally { setImgBusy(false) }
  }

  const { data: categories } = useQuery({
    queryKey: ['categories'],
    queryFn: () => categoryAPI.list().then(r => r.data),
  })

  const { data: companySettings } = useQuery({
    queryKey: ['company-settings'],
    queryFn: () => settingsAPI.getCompany().then(r => r.data),
  })
  const defaultMinMargin = Number(companySettings?.default_min_margin_pct) || 10

  // New-product form seeds its min margin from the company default (once, so a
  // settings refetch on window focus never clobbers what the user has typed).
  const marginSeeded = useRef(false)
  useEffect(() => {
    if (isEdit || marginSeeded.current || companySettings?.default_min_margin_pct == null) return
    marginSeeded.current = true
    setForm(p => ({ ...p, min_margin_pct: String(companySettings.default_min_margin_pct) }))
  }, [isEdit, companySettings])

  const { data: product, isLoading } = useQuery({
    queryKey: ['product', id],
    queryFn: () => productAPI.get(id).then(r => r.data),
    enabled: isEdit,
  })

  const { data: allAlerts } = useQuery({
    queryKey: ['cost-alerts'],
    queryFn: () => productAPI.pendingAlerts().then(r => r.data),
    enabled: isEdit && isAdmin(),
  })
  const productAlerts = (allAlerts || []).filter(a => a.product_id === Number(id))

  useEffect(() => {
    if (!product) return
    setForm({
      part_name: product.part_name || '',
      category_id: String(product.category_id || ''),
      unit_of_measure: product.unit_of_measure || 'Nos',
      hsn_code: product.hsn_code || '',
      gst_percent: String(product.gst_percent ?? '18'),
      purchase_cost: String(product.purchase_cost ?? '0'),
      b2b_price: String(product.b2b_price ?? '0'),
      b2c_price: String(product.b2c_price ?? '0'),
      mrp: String(product.mrp ?? '0'),
      floor_price: String(product.floor_price ?? '0'),
      low_stock_threshold: String(product.low_stock_threshold ?? '10'),
      cost_alert_threshold_pct: String(product.cost_alert_threshold_pct ?? '5'),
      min_margin_pct: String(product.min_margin_pct ?? '10'),
      description: product.description || '',
      is_active: product.is_active !== false,
    })
    setPriceBaseline({
      purchase_cost: Number(product.purchase_cost) || 0,
      floor_price: Number(product.floor_price) || 0,
      b2b_price: Number(product.b2b_price) || 0,
      b2c_price: Number(product.b2c_price) || 0,
      mrp: Number(product.mrp) || 0,
    })
    setAutoScaled(false)
  }, [product])

  useEffect(() => {
    if (!form.category_id || isEdit) return
    const cat = categories?.find(c => String(c.id) === String(form.category_id))
    if (!cat) return
    if (cat.default_hsn) setForm(p => ({ ...p, hsn_code: cat.default_hsn }))
    if (cat.default_gst_percent) setForm(p => ({ ...p, gst_percent: String(cat.default_gst_percent) }))
    if (cat.prefix) setPartCodePreview(`${cat.prefix}${(cat.sequence_counter ?? 0) + 1}`)
  }, [form.category_id, categories])

  const hc = (f, v) => { setForm(p => ({ ...p, [f]: v })); if (errors[f]) setErrors(p => ({ ...p, [f]: '' })) }

  const validate = () => {
    const errs = {}
    if (!form.part_name.trim()) errs.part_name = 'Required'
    if (!form.category_id) errs.category_id = 'Select a category'
    // HSN is mandatory — must be 4, 6, or 8 digits (numeric only)
    const hsn = (form.hsn_code || '').trim()
    if (!hsn) {
      errs.hsn_code = 'Required'
    } else if (!/^\d+$/.test(hsn) || ![4, 6, 8].includes(hsn.length)) {
      errs.hsn_code = 'HSN must be 4, 6, or 8 digits'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const mutation = useMutation({
    mutationFn: (d) => isEdit ? productAPI.update(id, d) : productAPI.create(d),
    onSuccess: () => {
      qc.invalidateQueries(['products'])
      toast.success(isEdit ? 'Product updated' : 'Product created successfully')
      navigate('/products')
    },
    onError: e => {
      const detail = e.response?.data?.detail
      if (typeof detail === 'string') toast.error(detail)
      else if (Array.isArray(detail)) toast.error(detail.map(d => d.msg).join(', '))
      else toast.error('Failed to save product')
    },
  })

  const handleSubmit = () => {
    if (!validate()) { toast.error('Please fill required fields'); return }
    // Floor price must be >= purchase cost
    const floorVal = Number(form.floor_price) || 0
    const costVal = Number(form.purchase_cost) || 0
    if (floorVal > 0 && costVal > 0 && floorVal < costVal) {
      toast.error(`Floor price (₹${floorVal.toFixed(2)}) cannot be below purchase cost (₹${costVal.toFixed(2)})`)
      return
    }

    // Price ordering: floor <= b2b <= b2c <= mrp (ignoring 0/unset tiers)
    const tiers = [
      ['Floor', Number(form.floor_price) || 0],
      ['B2B', Number(form.b2b_price) || 0],
      ['B2C', Number(form.b2c_price) || 0],
      ['MRP', Number(form.mrp) || 0],
    ].filter(([, v]) => v > 0)
    for (let i = 1; i < tiers.length; i++) {
      if (tiers[i - 1][1] > tiers[i][1]) {
        toast.error(`${tiers[i - 1][0]} price cannot exceed ${tiers[i][0]} price`)
        return
      }
    }
    mutation.mutate({
      part_name: form.part_name.trim(),
      // Category is immutable after creation; only send it when creating.
      ...(isEdit ? {} : { category_id: Number(form.category_id) }),
      unit_of_measure: form.unit_of_measure,
      hsn_code: form.hsn_code.trim(),
      gst_percent: Number(form.gst_percent) || 18,
      purchase_cost: Number(form.purchase_cost) || 0,

      b2b_price: Number(form.b2b_price) || 0,
      b2c_price: Number(form.b2c_price) || 0,
      mrp: Number(form.mrp) || 0,
      floor_price: Number(form.floor_price) || 0,
      low_stock_threshold: Number(form.low_stock_threshold) || 0,
      cost_alert_threshold_pct: Number(form.cost_alert_threshold_pct) || 5,
      min_margin_pct: Number(form.min_margin_pct) || defaultMinMargin,
      description: form.description || null,
      is_active: Boolean(form.is_active),
    })
  }

  if (isEdit && isLoading) return <div className="flex justify-center py-16"><Spinner size={24} /></div>

  return (
    <div className="max-w-2xl">
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/products')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Products
          </button>
          <h1 className="page-title">{isEdit ? 'Edit Product' : 'New Product'}</h1>
        </div>
        <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
          <Save size={14} /> {isEdit ? 'Update' : 'Create Product'}
        </Button>
      </div>

      {productAlerts.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1">
          <div className="flex items-center gap-2 text-amber-700 font-medium text-sm">
            <AlertTriangle size={15} />
            {productAlerts.length} unresolved alert{productAlerts.length > 1 ? 's' : ''} on this product
          </div>
          {productAlerts.map(a => (
            <div key={a.id} className="text-xs text-amber-700 ml-5">{a.message}</div>
          ))}
        </div>
      )}

      <div className="space-y-4">
        {/* Category */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Category</div></div>
          <div className="card-body">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Category <span className="text-red-500">*</span></label>
                <select value={form.category_id} onChange={e => hc('category_id', e.target.value)}
                  disabled={isEdit}
                  className={clsx('w-full h-9 px-3 rounded-lg border text-sm focus:outline-none transition-colors',
                    errors.category_id ? 'border-red-400' : 'border-gray-300 focus:border-blue-500',
                    isEdit && 'bg-gray-50 cursor-not-allowed')}>
                  <option value="">Select category...</option>
                  {categories?.map(c => <option key={c.id} value={c.id}>{c.name}{c.prefix ? ` (${c.prefix})` : ''}</option>)}
                </select>
                {errors.category_id && <p className="text-xs text-red-500 mt-1">{errors.category_id}</p>}
                {isEdit
                  ? <p className="text-xs text-gray-400 mt-1">Cannot change after creation</p>
                  : <NewCategoryInline onCreated={(cat) => hc('category_id', String(cat.id))} />
                }
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Part Code {!isEdit && '(preview)'}</label>
                <div className="h-9 px-3 flex items-center rounded-lg bg-gray-50 border border-gray-200 text-sm font-mono text-gray-600">
                  {isEdit ? (product?.part_code || '—') : (partCodePreview || '— select category —')}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Product Details</div></div>
          <div className="card-body space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Product Name <span className="text-red-500">*</span></label>
              <input value={form.part_name} onChange={e => hc('part_name', e.target.value)}
                placeholder="Full product name" className={ic(errors.part_name)} />
              {errors.part_name && <p className="text-xs text-red-500 mt-1">{errors.part_name}</p>}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Unit of Measure</label>
                <select value={form.unit_of_measure} onChange={e => hc('unit_of_measure', e.target.value)} className={ic()}>
                  {UOM_OPTIONS.map(u => <option key={u} value={u}>{u}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  HSN Code <span className="text-red-500">*</span> <span className="text-gray-400 font-normal">(4, 6, or 8 digits)</span>
                </label>
                <input value={form.hsn_code}
                  onChange={e => hc('hsn_code', e.target.value.replace(/\D/g, ''))}
                  placeholder="85162000" maxLength={8}
                  className={clsx(ic(), errors.hsn_code && 'border-red-400')} />
                {errors.hsn_code && <p className="text-xs text-red-500 mt-1">{errors.hsn_code}</p>}
                {!errors.hsn_code && form.hsn_code.length > 0 && form.hsn_code.length < 6 && (
                  <p className="text-xs text-amber-600 mt-1">E-invoice requires 6-digit HSN. 4-digit codes are valid for non-e-invoice sales only.</p>
                )}
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <textarea value={form.description} onChange={e => hc('description', e.target.value)}
                placeholder="Optional" rows={2}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500 resize-none" />
            </div>
          </div>
        </div>

        {/* Image (optional) */}
        {isEdit ? (
          <div className="card">
            <div className="card-header"><div className="text-sm font-semibold text-gray-700">Product Image <span className="text-gray-400 font-normal">(optional)</span></div></div>
            <div className="card-body">
              <div className="flex items-center gap-4">
                <div className="w-24 h-24 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center overflow-hidden shrink-0">
                  {product?.image_path
                    ? <img src={`${API_BASE}${product.image_path}`} alt={product.part_name} className="w-full h-full object-cover" />
                    : <ImageIcon size={28} className="text-gray-300" />}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <label className={clsx('inline-flex items-center gap-1.5 px-3 h-8 rounded-lg border border-gray-300 text-sm cursor-pointer hover:bg-gray-50', imgBusy && 'opacity-60 pointer-events-none')}>
                      <Upload size={14} /> {product?.image_path ? 'Replace' : 'Upload image'}
                      <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden"
                        onChange={e => { onImageSelect(e.target.files[0]); e.target.value = '' }} />
                    </label>
                    {product?.image_path && (
                      <button type="button" onClick={onImageRemove} disabled={imgBusy}
                        className="inline-flex items-center gap-1.5 px-3 h-8 rounded-lg border border-red-200 text-sm text-red-600 hover:bg-red-50 disabled:opacity-60">
                        <Trash2 size={14} /> Remove
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-2">PNG, JPG, WebP or GIF · max 10 MB</p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="card-body text-xs text-gray-400">
              Create the product first, then edit it to add an image (optional).
            </div>
          </div>
        )}

        {/* Pricing */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Pricing & Tax</div></div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Purchase Cost (₹)</label>
                <input type="number" step="0.01" min="0" value={form.purchase_cost}
                  onChange={e => {
                    const cost = Number(e.target.value) || 0
                    const base = priceBaseline
                    // Edit mode: re-scale every set tier from the loaded baseline
                    // so each tier keeps its margin ratio. Fields stay editable.
                    if (isEdit && base && base.purchase_cost > 0 && cost > 0) {
                      const ratio = cost / base.purchase_cost
                      const scale = (v) => v > 0 ? (v * ratio).toFixed(2) : ''
                      setForm(p => ({
                        ...p,
                        purchase_cost: e.target.value,
                        floor_price: base.floor_price > 0 ? scale(base.floor_price) : p.floor_price,
                        b2b_price:   base.b2b_price   > 0 ? scale(base.b2b_price)   : p.b2b_price,
                        b2c_price:   base.b2c_price   > 0 ? scale(base.b2c_price)   : p.b2c_price,
                        mrp:         base.mrp         > 0 ? scale(base.mrp)         : p.mrp,
                      }))
                      setAutoScaled(cost !== base.purchase_cost)
                    } else {
                      // New product: fill defaults on first entry; re-scale on subsequent changes.
                      setForm(p => {
                        const prevCost = Number(p.purchase_cost) || 0
                        const next = { ...p, purchase_cost: e.target.value }
                        if (cost > 0) {
                          if (prevCost > 0) {
                            const ratio = cost / prevCost
                            if (Number(p.b2b_price))   next.b2b_price   = (Number(p.b2b_price)   * ratio).toFixed(2)
                            if (Number(p.b2c_price))   next.b2c_price   = (Number(p.b2c_price)   * ratio).toFixed(2)
                            if (Number(p.floor_price)) next.floor_price = (Number(p.floor_price) * ratio).toFixed(2)
                          } else {
                            if (!Number(p.b2b_price))   next.b2b_price   = (cost * 1.05).toFixed(2)
                            if (!Number(p.b2c_price))   next.b2c_price   = (cost * 1.10).toFixed(2)
                            if (!Number(p.floor_price)) next.floor_price = (cost * 1.05).toFixed(2)
                          }
                        } else {
                          next.b2b_price   = '0'
                          next.b2c_price   = '0'
                          next.floor_price = '0'
                        }
                        return next
                      })
                    }
                    if (errors.purchase_cost) setErrors(p => ({ ...p, purchase_cost: '' }))
                  }} placeholder="0.00" className={ic()} />
              </div>
              <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    B2B Price (₹) <span className="text-gray-400 font-normal text-xs">— 5% of cost</span>
                  </label>
                  {showProfit ? (
                    <input type="number" step="0.01" min="0" value={form.b2b_price}
                      onChange={e => { hc('b2b_price', e.target.value) }}
                      placeholder="0.00" className={ic()} />
                  ) : (
                    <input value={form.b2b_price} readOnly className={ic() + ' bg-gray-50 cursor-not-allowed'} />
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    B2C Price (₹) <span className="text-gray-400 font-normal text-xs">— 10% of cost</span>
                  </label>
                  {showProfit ? (
                    <input type="number" step="0.01" min="0" value={form.b2c_price}
                      onChange={e => hc('b2c_price', e.target.value)}
                      placeholder="0.00" className={ic()} />
                  ) : (
                    <input value={form.b2c_price} readOnly className={ic() + ' bg-gray-50 cursor-not-allowed'} />
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    MRP (₹) <span className="text-gray-400 font-normal text-xs">— max retail price</span>
                  </label>
                  {showProfit ? (
                    <input type="number" step="0.01" min="0" value={form.mrp}
                      onChange={e => hc('mrp', e.target.value)}
                      placeholder="0.00" className={ic()} />
                  ) : (
                    <input value={form.mrp} readOnly className={ic() + ' bg-gray-50 cursor-not-allowed'} />
                  )}
                </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Floor Price (₹)</label>
                <input type="number" step="0.01" min="0" value={form.floor_price}
                  onChange={e => showProfitFigures && hc('floor_price', e.target.value)}
                  readOnly={!showProfitFigures} placeholder="0.00"
                  className={ic() + (!showProfitFigures ? ' bg-gray-50 cursor-not-allowed text-gray-500' : '')} />
              </div>
            </div>

            {autoScaled && showProfit && (
              <p className="text-xs text-blue-600 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                Selling prices were auto-scaled to preserve each tier's margin. Edit any field to override before saving.
              </p>
            )}

            {/* Auto-calculated Profit — super-admin only */}
            {showProfitFigures && (() => {
              const cost = Number(form.purchase_cost) || 0
              const price = Number(form.b2b_price) || 0
              const profitVal = price - cost
              const profitPct = cost > 0 ? (profitVal / cost) * 100 : 0
              const marginPct = price > 0 ? (profitVal / price) * 100 : 0
              const isProfit = profitVal >= 0
              const minMargin = Number(form.min_margin_pct) || defaultMinMargin
              const belowMin = cost > 0 && price > 0 && marginPct < minMargin
              const gstMult = 1 + (Number(form.gst_percent) || 0) / 100
              const b2cPrice = Number(form.b2c_price) || 0
              if (cost === 0 && price === 0) return null
              return (
                <div className={clsx(
                  'flex items-center justify-between px-4 py-3 rounded-lg border text-sm',
                  belowMin
                    ? 'bg-red-50 border-red-200'
                    : isProfit
                    ? 'bg-green-50 border-green-200'
                    : 'bg-red-50 border-red-200'
                )}>
                  <div className="flex items-center gap-6">
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Profit Value</div>
                      <div className={clsx('font-bold text-base', isProfit ? 'text-green-700' : 'text-red-600')}>
                        {isProfit ? '+' : ''}₹{profitVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Profit % <span className="text-gray-400 font-normal">(on cost)</span></div>
                      <div className={clsx('font-bold text-base', isProfit ? 'text-green-700' : 'text-red-600')}>
                        {isProfit ? '+' : ''}{profitPct.toFixed(2)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">Margin % <span className="text-gray-400 font-normal">(on price)</span></div>
                      <div className={clsx('font-bold text-base', belowMin ? 'text-red-600' : isProfit ? 'text-green-700' : 'text-red-600')}>
                        {marginPct.toFixed(2)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">B2B Price <span className="text-gray-400 font-normal">(incl. GST)</span></div>
                      <div className="font-semibold text-gray-700">
                        ₹{(price * gstMult).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-0.5">B2C Price <span className="text-gray-400 font-normal">(incl. GST)</span></div>
                      <div className="font-semibold text-gray-700">
                        ₹{(b2cPrice * gstMult).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                  </div>
                  {belowMin && (
                    <div className="text-xs text-red-600 font-medium text-right">
                      ⚠ Below min margin ({minMargin}%)
                    </div>
                  )}
                </div>
              )
            })()}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">GST %</label>
                <select value={form.gst_percent} onChange={e => hc('gst_percent', e.target.value)} className={ic()}>
                  {gstRates.map(r => <option key={r} value={r}>{r}%</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Low Stock Threshold</label>
                <input type="number" min="0" value={form.low_stock_threshold}
                  onChange={e => hc('low_stock_threshold', e.target.value)} placeholder="10" className={ic()} />
              </div>
            </div>
          </div>
        </div>

        {/* Advanced */}
        <div className="card">
          <div className="card-header"><div className="text-sm font-semibold text-gray-700">Advanced</div></div>
          <div className="card-body space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Cost Alert Threshold %</label>
                <input type="number" step="0.1" min="0" max="100" value={form.cost_alert_threshold_pct}
                  onChange={e => hc('cost_alert_threshold_pct', e.target.value)} className={ic()} />
              </div>
              {showProfitFigures && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Min Margin %</label>
                  <input type="number" step="0.1" min="0" max="100" value={form.min_margin_pct}
                    onChange={e => hc('min_margin_pct', e.target.value)} className={ic()} />
                </div>
              )}
            </div>
            {isEdit && (
              <label className="flex items-center gap-3 cursor-pointer" onClick={() => hc('is_active', !form.is_active)}>
                <div className="relative">
                  <div className={clsx('w-10 h-6 rounded-full transition-colors', form.is_active ? 'bg-blue-600' : 'bg-gray-300')} />
                  <div className={clsx('absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform', form.is_active ? 'translate-x-5' : 'translate-x-1')} />
                </div>
                <span className="text-sm text-gray-700">{form.is_active ? 'Active' : 'Inactive'}</span>
              </label>
            )}
          </div>
        </div>

        <div className="flex justify-between pb-6">
          <Button variant="secondary" onClick={() => navigate('/products')}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} onClick={handleSubmit}>
            <Save size={14} /> {isEdit ? 'Update Product' : 'Create Product'}
          </Button>
        </div>
      </div>
    </div>
  )
}