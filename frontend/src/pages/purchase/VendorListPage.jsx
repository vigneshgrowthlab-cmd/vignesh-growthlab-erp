import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { vendorAPI } from '@/api/purchase'
import { Button, Badge, Input, Spinner, Empty, Pagination } from '@/components/ui'
import { Plus, Search, Eye, Building2, CreditCard, Upload } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import BulkImportModal from '@/components/BulkImportModal'

export default function VendorListPage() {
  const navigate = useNavigate()
  const { isAdmin, isAccountant } = useAuthStore()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [statusActive, setStatusActive] = useState(true)
  const [importOpen, setImportOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['vendors', page, search, statusActive],
    queryFn: () => vendorAPI.list({ page, page_size: 20, search: search || undefined, is_active: statusActive }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const canManage = isAdmin() || isAccountant()

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Purchase</div>
          <h1 className="page-title">Vendors</h1>
        </div>
        {canManage && (
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              <Upload size={14} /> Import CSV
            </Button>
            <Button variant="primary" onClick={() => navigate('/purchase/vendors/new')}>
              <Plus size={14} /> New Vendor
            </Button>
          </div>
        )}
      </div>

      {importOpen && (
        <BulkImportModal
          title="Import Vendors from CSV"
          entityLabel="vendors"
          uploadFn={vendorAPI.bulkImport}
          templateFn={vendorAPI.importTemplate}
          templateName="vendor_import_template.csv"
          invalidateKey="vendors"
          columns={['trade_name (required)', 'gstin', 'phone', 'state', 'address_line1', 'city', 'addr_state', 'pincode']}
          onClose={() => setImportOpen(false)}
        />
      )}

      <div className="card mb-4">
        <div className="p-4 flex items-center gap-3">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input placeholder="Search by name or GSTIN..."
              value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
              className="pl-8" />
          </div>
          <select
            value={String(statusActive)}
            onChange={e => { setStatusActive(e.target.value === 'true'); setPage(1) }}
            className="w-32 h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </div>

      <div className="card">
        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={24} /></div>
        ) : data?.items?.length === 0 ? (
          <Empty message="No vendors found"
            action={canManage && (
              <Button variant="primary" onClick={() => navigate('/purchase/vendors/new')}>
                <Plus size={14} /> Add Vendor
              </Button>
            )} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Vendor Name</th>
                    <th>GSTIN</th>
                    <th>Phone</th>
                    <th>State</th>
                    <th className="text-right">Outstanding (₹)</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.map(v => (
                    <tr key={v.id} className="cursor-pointer"
                      onClick={() => navigate(`/purchase/vendors/${v.id}`)}>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                            <Building2 size={12} className="text-blue-600" />
                          </div>
                          <div>
                            <div className="font-medium text-gray-900">{v.trade_name}</div>
                            {v.legal_name && v.legal_name !== v.trade_name && (
                              <div className="text-xs text-gray-400">{v.legal_name}</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="font-mono text-xs text-gray-600">{v.gstin || '—'}</td>
                      <td className="text-gray-600">{v.phone || '—'}</td>
                      <td className="text-gray-600 text-sm">{v.state || '—'}</td>
                      <td className="text-right">
                        <span className={Number(v.outstanding_balance) > 0 ? 'font-semibold text-red-600' : 'text-gray-400'}>
                          ₹{Number(v.outstanding_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </td>
                      <td>
                        <Badge color={v.is_active ? 'green' : 'gray'}>
                          {v.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => navigate(`/purchase/vendors/${v.id}`)}
                            title="View vendor"
                            className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                            <Eye size={14} />
                          </button>
                          <button
                            onClick={() => navigate('/purchase/payments', { state: { vendor_id: v.id, vendor_name: v.trade_name } })}
                            title="Record payment"
                            className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600">
                            <CreditCard size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data && (
              <Pagination page={data.page} pages={data.pages} total={data.total}
                pageSize={20} onChange={setPage} />
            )}
          </>
        )}
      </div>

      {data && (
        <div className="mt-4 grid grid-cols-4 gap-3">
          <div className="stat-card">
            <div className="stat-label">Total Vendors</div>
            <div className="stat-value">{data.total}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Active</div>
            <div className="stat-value text-green-600">{data.items?.filter(v => v.is_active).length}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Outstanding (this page)</div>
            <div className="stat-value text-red-600">
              ₹{data.items?.reduce((s, v) => s + Number(v.outstanding_balance || 0), 0)
                .toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Outstanding (all vendors)</div>
            <div className="stat-value text-red-600">
              ₹{Number(data.total_outstanding_all || 0)
                .toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
