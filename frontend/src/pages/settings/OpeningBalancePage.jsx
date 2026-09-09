import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Spinner, Badge, Button } from '@/components/ui'
import { AlertTriangle, CheckCircle, Save } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '@/api/index'
import { clsx } from 'clsx'

const FY_OPTIONS = ['2026-27', '2025-26', '2024-25']

function Section({ title, children }) {
  return (
    <div className="card mb-4">
      <div className="card-header">
        <h3 className="font-semibold text-gray-800">{title}</h3>
      </div>
      <div className="card-body">{children}</div>
    </div>
  )
}

function AmountRow({ label, sub, value, onChange }) {
  return (
    <div className="flex items-center gap-4 py-2 border-b border-gray-50 last:border-0">
      <div className="flex-1">
        <div className="text-sm text-gray-800">{label}</div>
        {sub && <div className="text-xs text-gray-400">{sub}</div>}
      </div>
      <div className="w-36">
        <input type="number" step="0.01" min="0" value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full h-8 px-3 rounded border border-gray-300 text-sm text-right
            focus:outline-none focus:border-blue-500" />
      </div>
    </div>
  )
}

export default function OpeningBalancePage() {
  const [fy, setFy] = useState('2026-27')
  const [saving, setSaving] = useState(false)

  // Opening balances form state
  const [balances, setBalances] = useState({
    cash: '0',
    bank: '0',
    stock: '0',
    debtors: '0',
    creditors: '0',
    other_assets: '0',
    other_liabilities: '0',
  })

  const setB = (key) => (val) => setBalances(p => ({ ...p, [key]: val }))
  const num = (k) => Number(balances[k]) || 0

  const totalAssets = num('cash') + num('bank') + num('stock') + num('debtors') + num('other_assets')
  const totalLiabilities = num('creditors') + num('other_liabilities')
  const netWorth = totalAssets - totalLiabilities
  const isBalanced = Math.abs(netWorth) < 0.01

  // Vendor opening balances
  const { data: vendors } = useQuery({
    queryKey: ['vendors-ob'],
    queryFn: () => api.get('/api/v1/vendors/', { params: { page_size: 200 } }).then(r => r.data.items || []),
  })

  const { data: customers } = useQuery({
    queryKey: ['customers-ob'],
    queryFn: () => api.get('/api/v1/customers/', { params: { page_size: 200 } }).then(r => r.data.items || []),
  })

  const [vendorOB, setVendorOB] = useState({})
  const [customerOB, setCustomerOB] = useState({})

  const handleSaveGeneral = async () => {
    setSaving(true)
    try {
      // Post to journal entries for opening balances
      const entries = [
        { account: 'CASH',    amount: num('cash'),    type: 'debit'  },
        { account: 'BANK',    amount: num('bank'),    type: 'debit'  },
        { account: 'STOCK',   amount: num('stock'),   type: 'debit'  },
        { account: 'DEBTORS', amount: num('debtors'), type: 'debit'  },
        { account: 'CREDITORS', amount: num('creditors'), type: 'credit' },
      ].filter(e => e.amount > 0)

      if (!entries.length) {
        toast.error('Enter at least one opening balance')
        return
      }

      await api.post('/api/v1/journal-entries/', {
        entry_date: `${fy.split('-')[0]}-04-01`,
        reference_type: 'opening_balance',
        narration: `Opening Balance — ${fy}`,
        financial_year: fy,
        lines: entries,
      })

      toast.success('Opening balances saved to journal')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveParties = async () => {
    setSaving(true)
    let count = 0
    try {
      // Save vendor opening balances
      for (const [vid, amt] of Object.entries(vendorOB)) {
        if (!Number(amt)) continue
        await api.post('/api/v1/vendor-payments/', {
          vendor_id: Number(vid),
          payment_date: `${fy.split('-')[0]}-04-01`,
          amount: Number(amt),
          payment_mode: 'bank',
          notes: `Opening balance — ${fy}`,
          is_advance: false,
        })
        count++
      }
      // Save customer opening balances
      for (const [cid, amt] of Object.entries(customerOB)) {
        if (!Number(amt)) continue
        await api.post('/api/v1/customer-payments/', {
          customer_id: Number(cid),
          payment_date: `${fy.split('-')[0]}-04-01`,
          amount: Number(amt),
          payment_mode: 'bank',
          notes: `Opening balance — ${fy}`,
          is_advance: true,
        })
        count++
      }
      toast.success(`${count} party opening balance(s) saved`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Partially failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="page-header">
        <div>
          <div className="breadcrumb">Masters</div>
          <h1 className="page-title">Opening Balances</h1>
        </div>
        <select value={fy} onChange={e => setFy(e.target.value)}
          className="h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
          {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>

      <div className="card mb-4 p-4 bg-amber-50 border border-amber-200">
        <div className="flex gap-2 items-start">
          <AlertTriangle size={16} className="text-amber-500 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-amber-700">
            Enter opening balances for the start of financial year {fy} (1st April {fy.split('-')[0]}).
            These will be posted as journal entries. Enter each amount once only.
          </div>
        </div>
      </div>

      {/* General Balances */}
      <Section title="General Opening Balances">
        <div className="mb-3">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Assets</div>
          <AmountRow label="Cash in Hand" sub="Physical cash balance" value={balances.cash} onChange={setB('cash')} />
          <AmountRow label="Bank Balance" sub="Total bank account balance" value={balances.bank} onChange={setB('bank')} />
          <AmountRow label="Opening Stock" sub="Stock value as of start date" value={balances.stock} onChange={setB('stock')} />
          <AmountRow label="Debtors (Receivables)" sub="Total amount customers owe" value={balances.debtors} onChange={setB('debtors')} />
          <AmountRow label="Other Assets" sub="Any other asset balances" value={balances.other_assets} onChange={setB('other_assets')} />
        </div>
        <div className="mb-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Liabilities</div>
          <AmountRow label="Creditors (Payables)" sub="Total amount owed to vendors" value={balances.creditors} onChange={setB('creditors')} />
          <AmountRow label="Other Liabilities" sub="Loans, advances etc." value={balances.other_liabilities} onChange={setB('other_liabilities')} />
        </div>

        {/* Summary */}
        <div className="bg-gray-50 rounded-lg p-4 space-y-2 text-sm mb-4">
          <div className="flex justify-between text-gray-600">
            <span>Total Assets</span>
            <span className="font-medium">₹{totalAssets.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Total Liabilities</span>
            <span className="font-medium">₹{totalLiabilities.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
          </div>
          <div className={clsx('flex justify-between font-semibold pt-2 border-t border-gray-200',
            netWorth >= 0 ? 'text-green-700' : 'text-red-600')}>
            <span>Net Worth (Capital)</span>
            <span>₹{netWorth.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="primary" onClick={handleSaveGeneral} disabled={saving}>
            <Save size={14} /> {saving ? 'Saving...' : 'Post Opening Balances'}
          </Button>
        </div>
      </Section>

      {/* Vendor Opening Balances */}
      <Section title="Vendor Wise Outstanding (Payables)">
        <p className="text-xs text-gray-500 mb-4">
          Enter amount outstanding to each vendor as of start of {fy}.
          Only fill vendors with pending balances.
        </p>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {vendors?.map(v => (
            <div key={v.id} className="flex items-center gap-4">
              <div className="flex-1 text-sm text-gray-800">{v.trade_name}
                {v.gstin && <span className="text-xs text-gray-400 ml-2">{v.gstin}</span>}
              </div>
              <input type="number" step="0.01" min="0"
                value={vendorOB[v.id] || ''}
                onChange={e => setVendorOB(p => ({ ...p, [v.id]: e.target.value }))}
                placeholder="0.00"
                className="w-32 h-8 px-3 rounded border border-gray-300 text-sm text-right
                  focus:outline-none focus:border-blue-500" />
            </div>
          ))}
        </div>
        {vendors?.length > 0 && (
          <div className="flex justify-between items-center mt-4 pt-3 border-t border-gray-100">
            <span className="text-sm text-gray-600">
              Total: ₹{Object.values(vendorOB).reduce((s, v) => s + (Number(v) || 0), 0)
                .toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <Button variant="secondary" onClick={handleSaveParties} disabled={saving}>
              <Save size={14} /> Save Vendor Balances
            </Button>
          </div>
        )}
      </Section>

      {/* Customer Opening Balances */}
      <Section title="Customer Wise Outstanding (Receivables)">
        <p className="text-xs text-gray-500 mb-4">
          Enter amount outstanding from each customer as of start of {fy}.
          Only fill customers with pending balances.
        </p>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {customers?.map(c => (
            <div key={c.id} className="flex items-center gap-4">
              <div className="flex-1 text-sm text-gray-800">{c.trade_name}
                {c.gstin && <span className="text-xs text-gray-400 ml-2">{c.gstin}</span>}
              </div>
              <input type="number" step="0.01" min="0"
                value={customerOB[c.id] || ''}
                onChange={e => setCustomerOB(p => ({ ...p, [c.id]: e.target.value }))}
                placeholder="0.00"
                className="w-32 h-8 px-3 rounded border border-gray-300 text-sm text-right
                  focus:outline-none focus:border-blue-500" />
            </div>
          ))}
        </div>
        {customers?.length > 0 && (
          <div className="flex justify-between items-center mt-4 pt-3 border-t border-gray-100">
            <span className="text-sm text-gray-600">
              Total: ₹{Object.values(customerOB).reduce((s, v) => s + (Number(v) || 0), 0)
                .toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <Button variant="secondary" onClick={handleSaveParties} disabled={saving}>
              <Save size={14} /> Save Customer Balances
            </Button>
          </div>
        )}
      </Section>
    </div>
  )
}
