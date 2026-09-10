import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { purchaseAPI } from '@/api/purchase'
import { Button, Badge, Pagination, Empty, Spinner, Input, Select } from '@/components/ui'
import { Plus, Search, Eye, XCircle } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'

const FY_OPTIONS = ['2026-27', '2025-26', '2024-25', '2023-24']

export default function PurchasePage() {
  const navigate = useNavigate()
  const { isAdmin, isAccountant } = useAuthStore()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [fy, setFy] = useState('2026-27')

  const { data, isLoading } = useQuery({
    queryKey: ['purchases', page, search, fy],
    queryFn: () => purchaseAPI.list({
      page, page_size: 20,
      search: search || undefined,
      financial_year: fy,
    }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const canAccess = isAdmin() || isAccountant()

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Purchase</div>
          <h1 className="page-title">Purchase Entries</h1>
        </div>
        {canAccess && (
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="secondary" size="sm" onClick={() => navigate('/purchase/vendors')}>
              Vendors
            </Button>
            <Button variant="secondary" size="sm" onClick={() => navigate('/purchase/payments')}>
              Vendor Payments
            </Button>
            <Button variant="primary" onClick={() => navigate('/purchase/new')}>
              <Plus size={14} /> New Purchase
            </Button>
          </div>
        )}
      </div>

      <div className="card mb-4">
        <div className="p-4 flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input placeholder="Search by vendor invoice number..." value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }} className="pl-8" />
          </div>
          <Select value={fy} onChange={e => { setFy(e.target.value); setPage(1) }} className="w-full sm:w-32">
            {FY_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
          </Select>
        </div>
      </div>

      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : data?.items?.length === 0 ? (
          <Empty message="No purchase entries found"
            action={canAccess && <Button variant="primary" onClick={() => navigate('/purchase/new')}><Plus size={14} />New Purchase Entry</Button>} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Vendor Invoice No.</th>
                    <th>Vendor</th>
                    <th>Invoice Date</th>
                    <th>GST Type</th>
                    <th className="text-right">Total (₹)</th>
                    <th className="text-right">Outstanding (₹)</th>
                    <th>Payment</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.map(p => (
                    <tr key={p.id} className="cursor-pointer" onClick={() => navigate(`/purchase/${p.id}`)}>
                      <td className="font-mono text-xs font-medium">{p.vendor_invoice_number}</td>
                      <td className="font-medium text-gray-900">{p.vendor_name}</td>
                      <td className="text-gray-500">{p.invoice_date ? format(new Date(p.invoice_date), 'dd MMM yyyy') : '—'}</td>
                      <td>
                        <Badge color={p.gst_type === 'cgst_sgst' ? 'blue' : 'amber'}>
                          {p.gst_type === 'cgst_sgst' ? 'CGST+SGST' : 'IGST'}
                        </Badge>
                      </td>
                      <td className="text-right font-medium">
                        ₹{Number(p.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="text-right">
                        {p.is_cancelled ? (
                          <span className="text-gray-400 text-xs">—</span>
                        ) : (
                          <span className={Number(p.outstanding_amount) > 0 ? 'font-semibold text-red-600' : 'text-green-600'}>
                            ₹{Number(p.outstanding_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        )}
                      </td>
                      <td>
                        {p.is_cancelled ? (
                          <span className="text-gray-400 text-xs">—</span>
                        ) : (
                          <Badge color={
                            p.payment_status === 'paid' ? 'green' :
                            p.payment_status === 'partial' ? 'amber' : 'red'
                          }>
                            {p.payment_status === 'paid' ? 'Paid' :
                             p.payment_status === 'partial' ? 'Partial' : 'Outstanding'}
                          </Badge>
                        )}
                      </td>
                      <td>
                        <Badge color={p.is_cancelled ? 'red' : 'green'}>
                          {p.is_cancelled ? 'Cancelled' : 'Active'}
                        </Badge>
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        <button onClick={() => navigate(`/purchase/${p.id}`)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                          <Eye size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={20} onChange={setPage} />}
          </>
        )}
      </div>

      {data && (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
          <div className="stat-card">
            <div className="stat-label">Total entries</div>
            <div className="stat-value">{data.total}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Paid</div>
            <div className="stat-value text-green-600">
              {data.items?.filter(p => p.payment_status === 'paid').length}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Pending / Partial</div>
            <div className="stat-value text-red-600">
              {data.items?.filter(p => ['pending','partial'].includes(p.payment_status)).length}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Outstanding</div>
            <div className="stat-value text-red-600" style={{fontSize:'1rem'}}>
              ₹{data.items?.reduce((s,p) => s + Number(p.outstanding_amount||0), 0)
                .toLocaleString('en-IN', {minimumFractionDigits:2})}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}