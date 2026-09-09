import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { openingAPI, warehouseAPI } from '@/api/warehouse'
import { customerAPI } from '@/api/billing'
import { vendorAPI } from '@/api/purchase'
import { productAPI } from '@/api'
import { Button, Field, Input, Select, AlertBox } from '@/components/ui'
import { Plus, Trash2, Save, ArrowLeft, CheckCircle, Download, Upload } from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'

const FY_OPTIONS = ['2025-26', '2024-25', '2023-24']

export default function OpeningBalancePage() {
  const navigate = useNavigate()
  const [fy, setFy] = useState('2025-26')
  const [openingDate, setOpeningDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [stockItems, setStockItems] = useState([{ product_id: '', warehouse_id: '', quantity: '', unit_cost: '' }])
  const [customerBalances, setCustomerBalances] = useState([{ customer_id: '', opening_balance: '' }])
  const [vendorBalances, setVendorBalances] = useState([{ vendor_id: '', opening_balance: '' }])
  const [cashBalance, setCashBalance] = useState('')
  const [bankBalances, setBankBalances] = useState([{ account_code: '', bank_name: '', account_number: '', amount: '' }])
  const [done, setDone] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [uploading, setUploading] = useState(false)

  const { data: warehouses } = useQuery({ queryKey: ['warehouses'], queryFn: () => warehouseAPI.list().then(r => r.data) })
  const { data: products } = useQuery({ queryKey: ['products-list'], queryFn: () => productAPI.list({ page_size: 500 }).then(r => r.data.items) })
  const { data: customers } = useQuery({ queryKey: ['customers-list'], queryFn: () => customerAPI.list({ page_size: 500 }).then(r => r.data.items) })
  const { data: vendors } = useQuery({ queryKey: ['vendors-list'], queryFn: () => vendorAPI.list({ page_size: 500 }).then(r => r.data.items) })

  const mutation = useMutation({
    mutationFn: (d) => openingAPI.create(d),
    onSuccess: (res) => {
      toast.success('Opening balances saved successfully')
      setDone(true)
    },
    onError: e => toast.error(e.response?.data?.detail || 'Failed to save opening balances'),
  })

  const handleSave = () => {
    const payload = {
      financial_year: fy,
      opening_date: openingDate,
      stock_items: stockItems
        .filter(i => i.product_id && i.warehouse_id && i.quantity && i.unit_cost)
        .map(i => ({
          product_id: Number(i.product_id),
          warehouse_id: Number(i.warehouse_id),
          quantity: Number(i.quantity),
          unit_cost: Number(i.unit_cost),
          opening_date: openingDate,
        })),
      customer_balances: customerBalances
        .filter(c => c.customer_id && c.opening_balance)
        .map(c => ({
          customer_id: Number(c.customer_id),
          opening_balance: Number(c.opening_balance),
          opening_date: openingDate,
        })),
      vendor_balances: vendorBalances
        .filter(v => v.vendor_id && v.opening_balance)
        .map(v => ({
          vendor_id: Number(v.vendor_id),
          opening_balance: Number(v.opening_balance),
          opening_date: openingDate,
        })),
      cash_balance: cashBalance ? { amount: Number(cashBalance), opening_date: openingDate } : null,
      bank_balances: bankBalances
        .filter(b => b.account_code && b.amount)
        .map(b => ({
          account_code: b.account_code,
          bank_name: b.bank_name,
          account_number: b.account_number,
          amount: Number(b.amount),
          opening_date: openingDate,
        })),
    }
    mutation.mutate(payload)
  }

  const downloadStockTemplate = async () => {
    const res = await openingAPI.downloadStockTemplate()
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url; a.download = 'opening_stock_template.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  const handleStockUpload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    setUploadResult(null)
    try {
      const { data } = await openingAPI.bulkUploadStock(file, openingDate)
      setUploadResult(data)
      if (data.error_count === 0) {
        toast.success(`${data.success_count} opening stock rows imported`)
      } else if (data.success_count > 0) {
        toast(`${data.success_count} imported, ${data.error_count} failed`, { icon: '⚠️' })
      } else {
        toast.error(`All ${data.error_count} rows failed — see details`)
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const updateList = (setter, index, field, value) => {
    setter(prev => prev.map((item, i) => i === index ? { ...item, [field]: value } : item))
  }

  const removeItem = (setter, index) => {
    setter(prev => prev.filter((_, i) => i !== index))
  }

  if (done) {
    return (
      <div className="max-w-lg mx-auto text-center py-16">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle size={32} className="text-success" />
        </div>
        <h2 className="text-xl font-semibold text-gray-800 mb-2">Opening Balances Saved</h2>
        <p className="text-gray-500 mb-6 text-sm">Your system is now ready for live transactions. All opening stock, customer balances, vendor balances, and bank balances have been recorded.</p>
        <div className="flex gap-3 justify-center">
          <Button variant="secondary" onClick={() => { setDone(false) }}>Add More</Button>
          <Button variant="primary" onClick={() => navigate('/')}>Go to Dashboard</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl">
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/warehouse')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Warehouse
          </button>
          <h1 className="page-title">Opening Balance Entry</h1>
        </div>
        <Button variant="primary" loading={mutation.isPending} onClick={handleSave}>
          <Save size={14} /> Save Opening Balances
        </Button>
      </div>

      <AlertBox type="info" className="mb-4">
        Enter opening balances before recording any live transactions. This is done once at go-live. All entries will be dated as of the opening date selected.
      </AlertBox>

      {/* FY and Date */}
      <div className="form-section mb-4">
        <div className="form-section-header"><div className="form-section-title">Go-live settings</div></div>
        <div className="form-section-body">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Financial Year" required>
              <Select value={fy} onChange={e => setFy(e.target.value)}>
                {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
              </Select>
            </Field>
            <Field label="Opening Date" required hint="All balances will be as of this date">
              <Input type="date" value={openingDate} onChange={e => setOpeningDate(e.target.value)} />
            </Field>
          </div>
        </div>
      </div>

      {/* Opening Stock */}
      <div className="form-section mb-4">
        <div className="form-section-header flex items-center justify-between">
          <div className="form-section-title">Opening Stock</div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" type="button" onClick={downloadStockTemplate}>
              <Download size={12} /> Template
            </Button>
            <Button variant="secondary" size="sm" type="button" loading={uploading}
              onClick={() => document.getElementById('opening-stock-csv').click()}>
              <Upload size={12} /> Import CSV
            </Button>
            <input id="opening-stock-csv" type="file" accept=".csv" className="hidden"
              onChange={handleStockUpload} />
            <Button variant="secondary" size="sm" type="button"
              onClick={() => setStockItems(prev => [...prev, { product_id: '', warehouse_id: '', quantity: '', unit_cost: '' }])}>
              <Plus size={12} /> Add Product
            </Button>
          </div>
        </div>
        <div className="form-section-body space-y-3">
          <AlertBox type="info">
            Bulk import: download the template, fill in <strong>part_code, warehouse_name, quantity, unit_cost</strong> (and optionally <strong>opening_date</strong>), then import. Rows without a date use the Opening Date above. Imported stock is saved immediately and adds to existing stock.
          </AlertBox>
          {uploadResult && (
            <div className={
              uploadResult.error_count === 0
                ? 'p-3 rounded-lg text-sm bg-green-50 text-success'
                : uploadResult.success_count > 0
                  ? 'p-3 rounded-lg text-sm bg-amber-50 text-amber-700'
                  : 'p-3 rounded-lg text-sm bg-red-50 text-danger'
            }>
              <div className="font-medium mb-1">
                {uploadResult.error_count === 0
                  ? `✓ ${uploadResult.success_count} rows imported successfully`
                  : uploadResult.success_count > 0
                    ? `${uploadResult.success_count} imported, ${uploadResult.error_count} failed — see row errors below`
                    : `${uploadResult.error_count} rows failed — nothing imported`}
              </div>
              {uploadResult.errors?.slice(0, 8).map((er, i) => (
                <div key={i} className="text-xs">Row {er.row} ({er.data}): {er.errors.join('; ')}</div>
              ))}
              {uploadResult.errors?.length > 8 && (
                <div className="text-xs">…and {uploadResult.errors.length - 8} more</div>
              )}
            </div>
          )}
          {stockItems.map((item, i) => (
            <div key={i} className="grid grid-cols-5 gap-3 items-end">
              <Field label={i === 0 ? "Product" : undefined}>
                <Select value={item.product_id} onChange={e => updateList(setStockItems, i, 'product_id', e.target.value)}>
                  <option value="">Select product...</option>
                  {products?.map(p => <option key={p.id} value={p.id}>{p.part_code} — {p.part_name}</option>)}
                </Select>
              </Field>
              <Field label={i === 0 ? "Warehouse" : undefined}>
                <Select value={item.warehouse_id} onChange={e => updateList(setStockItems, i, 'warehouse_id', e.target.value)}>
                  <option value="">Select WH...</option>
                  {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </Select>
              </Field>
              <Field label={i === 0 ? "Quantity" : undefined}>
                <Input type="number" step="0.001" min="0" value={item.quantity}
                  onChange={e => updateList(setStockItems, i, 'quantity', e.target.value)} placeholder="0" />
              </Field>
              <Field label={i === 0 ? "Unit Cost (₹)" : undefined}>
                <Input type="number" step="0.01" min="0" value={item.unit_cost}
                  onChange={e => updateList(setStockItems, i, 'unit_cost', e.target.value)} placeholder="0.00" />
              </Field>
              <button onClick={() => removeItem(setStockItems, i)}
                className="h-9 px-2 text-gray-400 hover:text-danger"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </div>

      {/* Customer Balances */}
      <div className="form-section mb-4">
        <div className="form-section-header flex items-center justify-between">
          <div className="form-section-title">Customer Opening Balances</div>
          <Button variant="secondary" size="sm" type="button"
            onClick={() => setCustomerBalances(prev => [...prev, { customer_id: '', opening_balance: '' }])}>
            <Plus size={12} /> Add Customer
          </Button>
        </div>
        <div className="form-section-body space-y-3">
          {customerBalances.map((cb, i) => (
            <div key={i} className="grid grid-cols-3 gap-3 items-end">
              <Field label={i === 0 ? "Customer" : undefined} className="col-span-2">
                <Select value={cb.customer_id} onChange={e => updateList(setCustomerBalances, i, 'customer_id', e.target.value)}>
                  <option value="">Select customer...</option>
                  {customers?.map(c => <option key={c.id} value={c.id}>{c.trade_name}</option>)}
                </Select>
              </Field>
              <div className="flex gap-2 items-end">
                <Field label={i === 0 ? "Opening Balance (₹)" : undefined} className="flex-1">
                  <Input type="number" step="0.01" min="0" value={cb.opening_balance}
                    onChange={e => updateList(setCustomerBalances, i, 'opening_balance', e.target.value)} placeholder="0.00" />
                </Field>
                <button onClick={() => removeItem(setCustomerBalances, i)}
                  className="h-9 px-2 text-gray-400 hover:text-danger"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Vendor Balances */}
      <div className="form-section mb-4">
        <div className="form-section-header flex items-center justify-between">
          <div className="form-section-title">Vendor Opening Balances</div>
          <Button variant="secondary" size="sm" type="button"
            onClick={() => setVendorBalances(prev => [...prev, { vendor_id: '', opening_balance: '' }])}>
            <Plus size={12} /> Add Vendor
          </Button>
        </div>
        <div className="form-section-body space-y-3">
          {vendorBalances.map((vb, i) => (
            <div key={i} className="grid grid-cols-3 gap-3 items-end">
              <Field label={i === 0 ? "Vendor" : undefined} className="col-span-2">
                <Select value={vb.vendor_id} onChange={e => updateList(setVendorBalances, i, 'vendor_id', e.target.value)}>
                  <option value="">Select vendor...</option>
                  {vendors?.map(v => <option key={v.id} value={v.id}>{v.trade_name}</option>)}
                </Select>
              </Field>
              <div className="flex gap-2 items-end">
                <Field label={i === 0 ? "Opening Balance (₹)" : undefined} className="flex-1">
                  <Input type="number" step="0.01" min="0" value={vb.opening_balance}
                    onChange={e => updateList(setVendorBalances, i, 'opening_balance', e.target.value)} placeholder="0.00" />
                </Field>
                <button onClick={() => removeItem(setVendorBalances, i)}
                  className="h-9 px-2 text-gray-400 hover:text-danger"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Cash & Bank Balances */}
      <div className="form-section mb-4">
        <div className="form-section-header flex items-center justify-between">
          <div className="form-section-title">Cash & Bank Opening Balances</div>
          <Button variant="secondary" size="sm" type="button"
            onClick={() => setBankBalances(prev => [...prev, { account_code: '', bank_name: '', account_number: '', amount: '' }])}>
            <Plus size={12} /> Add Bank Account
          </Button>
        </div>
        <div className="form-section-body space-y-4">
          <Field label="Cash in Hand (₹)">
            <div className="relative w-48">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-sm">₹</span>
              <Input type="number" step="0.01" min="0" value={cashBalance}
                onChange={e => setCashBalance(e.target.value)} className="pl-5" placeholder="0.00" />
            </div>
          </Field>
          {bankBalances.map((bb, i) => (
            <div key={i} className="grid grid-cols-5 gap-3 items-end">
              <Field label={i === 0 ? "Account Code" : undefined}>
                <Input value={bb.account_code} placeholder="BANK_01"
                  onChange={e => updateList(setBankBalances, i, 'account_code', e.target.value)} />
              </Field>
              <Field label={i === 0 ? "Bank Name" : undefined}>
                <Input value={bb.bank_name} placeholder="HDFC Bank"
                  onChange={e => updateList(setBankBalances, i, 'bank_name', e.target.value)} />
              </Field>
              <Field label={i === 0 ? "Account Number" : undefined}>
                <Input value={bb.account_number} placeholder="XXXX1234"
                  onChange={e => updateList(setBankBalances, i, 'account_number', e.target.value)} />
              </Field>
              <Field label={i === 0 ? "Opening Balance (₹)" : undefined}>
                <Input type="number" step="0.01" min="0" value={bb.amount}
                  onChange={e => updateList(setBankBalances, i, 'amount', e.target.value)} placeholder="0.00" />
              </Field>
              <button onClick={() => removeItem(setBankBalances, i)}
                className="h-9 px-2 text-gray-400 hover:text-danger"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-between pb-6">
        <Button variant="secondary" onClick={() => navigate('/warehouse')}>Cancel</Button>
        <Button variant="primary" loading={mutation.isPending} onClick={handleSave}>
          <Save size={14} /> Save All Opening Balances
        </Button>
      </div>
    </div>
  )
}
