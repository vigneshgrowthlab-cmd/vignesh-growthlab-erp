import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { dashboardAPI } from '@/api/reports'
import { Spinner, Badge } from '@/components/ui'
import { useAuthStore } from '@/store/authStore'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import {
  TrendingUp, TrendingDown, ShoppingCart, Users, AlertTriangle,
  Package, IndianRupee, Clock, ArrowRight, BarChart2, RefreshCw
} from 'lucide-react'

// ── Current FY helper ─────────────────────────────────────────
function getCurrentFY() {
  const today = new Date()
  const month = today.getMonth() + 1 // 1-12
  const year = today.getFullYear()
  if (month >= 4) {
    return `${year}-${String(year + 1).slice(2)}`
  }
  return `${year - 1}-${String(year).slice(2)}`
}

const CURRENT_FY = getCurrentFY()

// ── Metric Card ───────────────────────────────────────────────
function MetricCard({ label, value, sub, icon: Icon, color = 'blue', trend, onClick }) {
  const colors = {
    blue:   'bg-blue-50 text-blue-600',
    green:  'bg-green-50 text-green-600',
    amber:  'bg-amber-50 text-amber-600',
    red:    'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
    gray:   'bg-gray-50 text-gray-500',
  }
  return (
    <div onClick={onClick}
      className={clsx('card p-4 flex gap-4 items-start',
        onClick && 'cursor-pointer hover:shadow-md transition-shadow')}>
      <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0', colors[color])}>
        <Icon size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-gray-500 mb-0.5">{label}</div>
        <div className="text-xl font-bold text-gray-900 truncate">{value}</div>
        {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
      </div>
      {trend !== undefined && (
        <div className={clsx('flex items-center gap-0.5 text-xs font-medium mt-1',
          trend >= 0 ? 'text-green-600' : 'text-red-500')}>
          {trend >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {Math.abs(trend)}%
        </div>
      )}
    </div>
  )
}

// ── Mini Bar Chart ────────────────────────────────────────────
function MiniBarChart({ data }) {
  if (!data?.length) return null
  const max = Math.max(...data.map(d => d.sales), 1)
  return (
    <div className="flex items-end gap-1.5 h-20">
      {data.map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1">
          <div className="w-full rounded-sm bg-blue-500 transition-all"
            style={{ height: `${(d.sales / max) * 64}px`, opacity: i === data.length - 1 ? 1 : 0.5 }} />
          <span className="text-xs text-gray-400 whitespace-nowrap" style={{ fontSize: 9 }}>
            {d.month.split(' ')[0]}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Currency formatter ────────────────────────────────────────
function fmt(n) {
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(1)}Cr`
  if (n >= 1_00_000)    return `₹${(n / 1_00_000).toFixed(1)}L`
  if (n >= 1_000)       return `₹${(n / 1_000).toFixed(1)}K`
  return `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`
}

function fmtFull(n) {
  return `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

// ── Main Dashboard ────────────────────────────────────────────
// ── Reduced (warehouse-scoped) Dashboard ──────────────────────
// Shown to every role except super-admin / accountant: only the mapped
// warehouse's previous-month, current-month and today's sales.
function ReducedDashboard({ d, refetch, isFetching }) {
  const now = new Date()
  const today = format(now, 'EEEE, dd MMMM yyyy')
  const thisMonthLabel = format(now, 'MMMM yyyy')
  const prevMonthLabel = format(new Date(now.getFullYear(), now.getMonth() - 1, 1), 'MMMM yyyy')
  const hasWarehouse = !!d.warehouse_id

  return (
    <div>
      <div className="page-header mb-6">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-gray-400">{today}</span>
            <span className="text-gray-300">·</span>
            <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
              {hasWarehouse ? d.warehouse_name || `Warehouse #${d.warehouse_id}` : 'No warehouse assigned'}
            </span>
          </div>
        </div>
        <button onClick={() => refetch()}
          className={clsx('flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 px-3 h-8 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors',
            isFetching && 'opacity-50 pointer-events-none')}>
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          {isFetching ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {!hasWarehouse && (
        <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-sm text-amber-700 flex items-center gap-2">
          <AlertTriangle size={16} />
          No warehouse is mapped to your account, so no sales figures can be shown. Contact an administrator.
        </div>
      )}

      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Sales {hasWarehouse && `· ${d.warehouse_name || 'your warehouse'}`}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <MetricCard label={`Previous Month (${prevMonthLabel})`} value={fmt(d.prev_month_sales || 0)} icon={BarChart2} color="purple" />
        <MetricCard label={`This Month (${thisMonthLabel})`} value={fmt(d.month_sales || 0)} icon={TrendingUp} color="green" />
        <MetricCard label="Today's Sales" value={fmt(d.today_sales || 0)} icon={IndianRupee} color="blue" />
      </div>

      <div className="mt-4 text-center text-xs text-gray-400">
        Data as of {today} &nbsp;·&nbsp; Auto-refreshes every 5 minutes
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const fullView = ['super_admin', 'accountant'].includes(user?.role)
  const [fy] = useState(CURRENT_FY)

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['dashboard', fy],
    queryFn: () => dashboardAPI.get({ financial_year: fy }).then(r => r.data),
    refetchInterval: 5 * 60 * 1000, // auto-refresh every 5 min
  })

  if (isLoading) return (
    <div className="flex flex-col items-center justify-center py-32 gap-3">
      <Spinner size={28} />
      <span className="text-sm text-gray-400">Loading dashboard...</span>
    </div>
  )

  const d = data || {}
  const today = format(new Date(), 'EEEE, dd MMMM yyyy')

  if (!fullView) return <ReducedDashboard d={d} refetch={refetch} isFetching={isFetching} />

  return (
    <div>
      {/* Header */}
      <div className="page-header mb-6">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-gray-400">{today}</span>
            <span className="text-gray-300">·</span>
            <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
              FY {fy}
            </span>
          </div>
        </div>
        <button onClick={() => refetch()}
          className={clsx('flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 px-3 h-8 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors',
            isFetching && 'opacity-50 pointer-events-none')}>
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          {isFetching ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Sales KPIs (FY-scoped) — gross with net taxable shown alongside */}
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Sales · FY {fy}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <MetricCard
          label="Today's Sales"
          value={fmt(d.today_sales || 0)}
          sub={`Net ${fmt(d.today_sales_net || 0)} · Coll ${fmt(d.today_collections || 0)}`}
          icon={IndianRupee}
          color="blue"
          onClick={() => navigate('/billing')}
        />
        <MetricCard
          label="This Month"
          value={fmt(d.month_sales || 0)}
          sub={`Net taxable: ${fmt(d.month_sales_net || 0)}`}
          icon={TrendingUp}
          color="green"
          onClick={() => navigate('/billing')}
        />
        <MetricCard
          label={`FY ${fy} Sales`}
          value={fmt(d.fy_sales || 0)}
          sub={`Net taxable: ${fmt(d.fy_sales_net || 0)}`}
          icon={BarChart2}
          color="purple"
          onClick={() => navigate('/reports')}
        />
        <MetricCard
          label="Purchases"
          value={fmt(d.fy_purchases || 0)}
          sub={`This month: ${fmt(d.month_purchases || 0)}`}
          icon={ShoppingCart}
          color="amber"
          onClick={() => navigate('/purchase')}
        />
      </div>

      {/* Live position — current balances, NOT scoped to the financial year */}
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Live position · current, not FY-bound
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <MetricCard
          label="Outstanding Receivables"
          value={fmt(d.total_outstanding || 0)}
          sub={d.overdue_amount > 0 ? `Overdue: ${fmt(d.overdue_amount)}` : 'No overdue'}
          icon={Clock}
          color={d.overdue_amount > 0 ? 'red' : 'amber'}
          onClick={() => navigate('/reports')}
        />
        <MetricCard
          label="Total Payables"
          value={fmt(d.total_payables || 0)}
          sub="Owed to vendors"
          icon={IndianRupee}
          color="purple"
          onClick={() => navigate('/purchase/vendors')}
        />
        <MetricCard
          label="Stock Value"
          value={fmt(d.stock_value || 0)}
          sub="FIFO valuation"
          icon={Package}
          color="blue"
          onClick={() => navigate('/warehouse')}
        />
        <MetricCard
          label="Cash Balance"
          value={fmt(d.cash_balance || 0)}
          sub="As of last cash closing"
          icon={IndianRupee}
          color="gray"
          onClick={() => navigate('/accounting')}
        />
      </div>

      {/* Operations */}
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Operations · live
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
        <MetricCard
          label="Low Stock Items"
          value={d.low_stock_count || 0}
          sub={d.low_stock_count > 0 ? 'Products below threshold' : 'All stock levels OK'}
          icon={Package}
          color={d.low_stock_count > 0 ? 'amber' : 'green'}
          onClick={() => navigate('/warehouse')}
        />
        <MetricCard
          label="Pending Deliveries"
          value={d.pending_deliveries || 0}
          sub="DCs awaiting warehouse transfer"
          icon={ShoppingCart}
          color={d.pending_deliveries > 0 ? 'amber' : 'gray'}
          onClick={() => navigate('/warehouse')}
        />
        <MetricCard
          label="Today's Collections"
          value={fmt(d.today_collections || 0)}
          sub="Received today"
          icon={IndianRupee}
          color="green"
          onClick={() => navigate('/accounting')}
        />
      </div>

      {/* Charts + Tables row */}
      <div className="grid grid-cols-2 gap-4 mb-4">

        {/* Sales trend */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-gray-800">Sales Trend</h3>
              <p className="text-xs text-gray-400">Last 6 months</p>
            </div>
            <button onClick={() => navigate('/reports')}
              className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
              View Report <ArrowRight size={11} />
            </button>
          </div>
          <MiniBarChart data={d.monthly_trend} />
          {d.monthly_trend?.length > 0 && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              {d.monthly_trend.slice(-3).map((m, i) => (
                <div key={i}>
                  <div className="text-xs text-gray-400">{m.month}</div>
                  <div className="text-sm font-semibold text-gray-700">{fmt(m.sales)}</div>
                  <div className="text-xs text-gray-400">Net {fmt(m.sales_net || 0)}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top customers */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-gray-800">Top Customers</h3>
              <p className="text-xs text-gray-400">This month by sales</p>
            </div>
            <button onClick={() => navigate('/billing')}
              className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
              All Invoices <ArrowRight size={11} />
            </button>
          </div>
          {!d.top_customers?.length ? (
            <div className="flex flex-col items-center justify-center py-8 text-gray-300">
              <Users size={28} />
              <span className="text-xs mt-2">No sales this month</span>
            </div>
          ) : (
            <div className="space-y-3">
              {d.top_customers.map((c, i) => {
                const max = d.top_customers[0]?.total || 1
                return (
                  <div key={i}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-700 font-medium truncate flex-1 mr-2">
                        {i + 1}. {c.name}
                      </span>
                      <span className="text-gray-600 font-semibold flex-shrink-0">{fmt(c.total)}</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full">
                      <div className="h-1.5 bg-blue-400 rounded-full"
                        style={{ width: `${(c.total / max) * 100}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Recent Invoices */}
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h3 className="font-semibold text-gray-800">Recent Invoices</h3>
          <button onClick={() => navigate('/billing')}
            className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
            View All <ArrowRight size={11} />
          </button>
        </div>
        {!d.recent_invoices?.length ? (
          <div className="p-8 text-center text-gray-400 text-sm">No invoices yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Invoice No.</th>
                  <th>Customer</th>
                  <th>Date</th>
                  <th className="text-right">Amount</th>
                  <th className="text-right">Outstanding</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {d.recent_invoices.map(inv => (
                  <tr key={inv.id} className="cursor-pointer hover:bg-gray-50"
                    onClick={() => navigate(`/billing/${inv.id}`)}>
                    <td className="font-mono text-xs font-medium text-blue-600">
                      {inv.invoice_number || `INV-${inv.id}`}
                    </td>
                    <td className="font-medium text-gray-900">{inv.customer_name}</td>
                    <td className="text-gray-500 text-sm">
                      {inv.invoice_date ? format(new Date(inv.invoice_date), 'dd MMM yyyy') : '—'}
                    </td>
                    <td className="text-right font-medium">
                      {fmtFull(inv.total_amount)}
                    </td>
                    <td className="text-right">
                      <span className={Number(inv.outstanding_amount) > 0 ? 'text-red-600 font-medium' : 'text-gray-400'}>
                        {fmtFull(inv.outstanding_amount)}
                      </span>
                    </td>
                    <td>
                      <Badge color={Number(inv.outstanding_amount) <= 0 ? 'green' : 'amber'}>
                        {Number(inv.outstanding_amount) <= 0 ? 'Paid' : 'Pending'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Footer note */}
      <div className="mt-4 text-center text-xs text-gray-400">
        Financial Year: {fy} &nbsp;·&nbsp; Data as of {today} &nbsp;·&nbsp; Auto-refreshes every 5 minutes
      </div>
    </div>
  )
}
