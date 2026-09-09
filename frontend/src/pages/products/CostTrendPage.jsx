import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { productAPI, categoryAPI } from '@/api'
import { useAuthStore } from '@/store/authStore'
import { Button, Badge, Spinner } from '@/components/ui'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ComposedChart, Area
} from 'recharts'
import { ArrowLeft, AlertTriangle, X } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'

export default function CostTrendPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const isSuperAdmin = useAuthStore(s => s.isSuperAdmin())
  const [vendorId, setVendorId] = useState('')
  const [activeTab, setActiveTab] = useState('timeline')
  const { data: trend, isLoading } = useQuery({
    queryKey: ['cost-trend', id, vendorId],
    queryFn: () => productAPI.costTrend(id, { vendor_id: vendorId || undefined }).then(r => r.data),
  })

  const { data: alerts } = useQuery({
    queryKey: ['product-alerts', id],
    queryFn: () => productAPI.pendingAlerts().then(r => r.data.filter(a => String(a.product_id) === String(id))),
  })

  const dismissMutation = useMutation({
    mutationFn: (alertId) => productAPI.resolveAlert(alertId, { approve: false }),
    onSuccess: () => {
      qc.invalidateQueries(['product-alerts'])
      qc.invalidateQueries(['cost-alerts'])
    },
  })

  if (isLoading) return <div className="flex justify-center py-20"><Spinner size={28} /></div>
  if (!trend) return null

  // Prepare timeline chart data — show B2B and B2C separately
  const b2b = parseFloat(trend.current_b2b_price || 0)
  const b2c = parseFloat(trend.current_b2c_price || 0)
  const timelineData = trend.cost_history.map(h => {
    const c = parseFloat(h.unit_cost) || 0
    return {
      date: format(new Date(h.recorded_at), 'dd MMM yy'),
      cost: c,
      b2b_price: b2b,
      b2c_price: b2c,
      b2b_margin: c > 0 ? Number(((b2b - c) / c * 100).toFixed(1)) : 0,
      b2c_margin: c > 0 ? Number(((b2c - c) / c * 100).toFixed(1)) : 0,
      vendor: h.vendor_name || 'Direct',
    }
  })

  const tabs = [
    { id: 'timeline', label: 'Cost over time' },
    { id: 'vendors', label: 'Vendor comparison' },
    { id: 'volume', label: 'Price vs volume' },
    // Margin trend is a profit/margin view — super-admin only
    ...(isSuperAdmin ? [{ id: 'margin', label: 'Margin trend' }] : []),
  ]

  return (
    <div className="max-w-5xl">
      {/* Header */}
      <div className="page-header">
        <div>
          <button onClick={() => navigate('/products')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1">
            <ArrowLeft size={12} /> Products
          </button>
          <h1 className="page-title">Cost Trend — {trend.part_code}</h1>
          <div className="text-sm text-gray-500 mt-0.5">{trend.part_name}</div>
        </div>
      </div>

      {/* Alerts — informational only, no approval action */}
      {alerts?.length > 0 && (
        <div className="mb-4 space-y-2">
          {alerts.map(alert => (
            <div key={alert.id} className={clsx(
              'flex items-center justify-between p-3.5 rounded-lg border',
              alert.alert_type === 'cost_rise' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'
            )}>
              <div className="flex items-center gap-2.5">
                <AlertTriangle size={16} className={alert.alert_type === 'cost_rise' ? 'text-danger' : 'text-warning'} />
                <div className="text-sm font-medium text-gray-800">{alert.message}</div>
              </div>
              <button
                onClick={() => dismissMutation.mutate(alert.id)}
                className="ml-4 shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
                title="Dismiss"
              >
                <X size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="stat-card">
          <div className="stat-label">Current cost</div>
          <div className="stat-value">₹{Number(trend.current_cost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">B2B price</div>
          <div className="stat-value">₹{Number(trend.current_b2b_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">B2C price</div>
          <div className="stat-value">₹{Number(trend.current_b2c_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
        </div>
        {isSuperAdmin && (
          <div className="stat-card">
            <div className="stat-label">B2B margin</div>
            <div className={clsx('stat-value', trend.current_margin_pct < 10 ? 'text-warning' : 'text-success')}>
              {Number(trend.current_margin_pct).toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="card">
        <div className="flex border-b border-gray-100">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={clsx('px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                activeTab === t.id ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700')}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-5">
          {/* Timeline */}
          {activeTab === 'timeline' && (
            <div>
              <div className="text-xs text-gray-500 mb-4">Purchase cost over all time vs current B2B and B2C selling prices</div>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={timelineData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `₹${v}`} />
                  <Tooltip formatter={v => `₹${v}`} />
                  <Legend />
                  <Area type="monotone" dataKey="b2b_price" fill="#E6F1FB" stroke="#185FA5" strokeWidth={1.5} dot={false} name="B2B price" />
                  <Line type="monotone" dataKey="b2c_price" stroke="#8b5cf6" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="B2C price" />
                  <Line type="monotone" dataKey="cost" stroke="#E24B4A" strokeWidth={2} dot={{ r: 3, fill: '#E24B4A' }} name="Purchase cost" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Vendor comparison */}
          {activeTab === 'vendors' && (
            <div>
              <div className="text-xs text-gray-500 mb-4">Price history across all vendors for this product</div>
              {trend.vendor_summary.length === 0 ? (
                <div className="text-center py-10 text-gray-400 text-sm">No vendor-linked purchases recorded</div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={trend.vendor_summary}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="vendor_name" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `₹${v}`} />
                      <Tooltip formatter={v => `₹${Number(v).toFixed(2)}`} />
                      <Legend />
                      <Bar dataKey="min_cost" fill="#E1F5EE" name="Min cost" />
                      <Bar dataKey="avg_cost" fill="#1D9E75" name="Avg cost" />
                      <Bar dataKey="max_cost" fill="#FAEEDA" name="Max cost" />
                    </BarChart>
                  </ResponsiveContainer>
                  <table className="table mt-4">
                    <thead>
                      <tr>
                        <th>Vendor</th><th className="text-right">Min</th>
                        <th className="text-right">Avg</th><th className="text-right">Max</th>
                        <th className="text-right">Last Price</th><th>Flag</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trend.vendor_summary.map(v => (
                        <tr key={v.vendor_id}>
                          <td className="font-medium">{v.vendor_name}</td>
                          <td className="text-right">₹{v.min_cost.toFixed(2)}</td>
                          <td className="text-right">₹{v.avg_cost.toFixed(2)}</td>
                          <td className="text-right">₹{v.max_cost.toFixed(2)}</td>
                          <td className="text-right font-medium">₹{v.last_price.toFixed(2)}</td>
                          <td>
                            {v.is_above_avg
                              ? <Badge color="red">Above avg</Badge>
                              : <Badge color="green">Normal</Badge>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          )}

          {/* Price vs volume */}
          {activeTab === 'volume' && (
            <div>
              <div className="text-xs text-gray-500 mb-4">Total quantity purchased at each price point</div>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={trend.price_volume_data}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="unit_cost" tickFormatter={v => `₹${v}`} tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v, n) => [v, n === 'total_quantity' ? 'Qty purchased' : 'Transactions']} />
                  <Bar dataKey="total_quantity" fill="#185FA5" name="Total quantity" />
                  <Bar dataKey="purchase_count" fill="#B5D4F4" name="No. of purchases" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Margin trend — super-admin only */}
          {activeTab === 'margin' && isSuperAdmin && (
            <div>
              <div className="text-xs text-gray-500 mb-4">Gross margin % at each purchase cost vs current B2B and B2C selling prices</div>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={timelineData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${v}%`} />
                  <Tooltip formatter={v => `${v}%`} />
                  <Legend />
                  <Line type="monotone" dataKey="b2b_margin" stroke="#1D9E75" strokeWidth={2}
                    dot={{ r: 3, fill: '#1D9E75' }} name="B2B margin %" />
                  <Line type="monotone" dataKey="b2c_margin" stroke="#8b5cf6" strokeWidth={2} strokeDasharray="4 2"
                    dot={{ r: 3, fill: '#8b5cf6' }} name="B2C margin %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

    </div>
  )
}
