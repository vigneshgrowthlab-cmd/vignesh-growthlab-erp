import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { useState } from 'react'
import { clsx } from 'clsx'
import {
  LayoutDashboard, Package, ShoppingCart, FileText, Warehouse,
  Calculator, Receipt, BarChart2, Landmark, Users, Settings, BookOpen,
  LogOut, ChevronDown, ChevronRight, Menu, X, Bell, Building2, UserCircle,
  ShieldCheck, Sliders
} from 'lucide-react'

const NAV = [
  { label: 'Dashboard',  icon: LayoutDashboard, path: '/' },
  { label: 'Products',   icon: Package,         path: '/products',
	children: [
	{ label: 'Products', path: '/products' },
	{ label: 'Price Trend', path: '/products/price-trend' },
	]
  },
  {
    label: 'Purchase', icon: ShoppingCart, path: '/purchase',
    children: [
      { label: 'Purchase Entry', path: '/purchase' },
      { label: 'Vendors',         path: '/purchase/vendors' },
    ]
  },
  {
    label: 'Billing', icon: FileText, path: '/billing',
    children: [
      { label: 'Invoices',  path: '/billing' },
      { label: 'Customers', path: '/billing/customers' },
      { label: 'Receipts',  path: '/billing/receipts' },
    ]
  },
  { label: 'Warehouse',   icon: Warehouse,    path: '/warehouse' },
  { label: 'Accounting',  icon: Calculator,   path: '/accounting' },
  { label: 'GST',         icon: Receipt,      path: '/gst' },
  { label: 'Reports',     icon: BarChart2,    path: '/reports' },
  { label: 'Bank',        icon: Landmark,     path: '/bank-statement' },
  { label: 'Users',       icon: Users,        path: '/users', roles: ['super_admin', 'admin', 'accountant'] },
  { label: 'Audit Log',   icon: ShieldCheck,  path: '/audit-log', superAdminOnly: true },
  { label: 'Settings',    icon: Settings,     path: '/settings', roles: ['super_admin', 'admin'] },
  { label: 'Configuration', icon: Sliders,    path: '/settings/config', superAdminOnly: true },
  { label: 'Opening Balances',    icon: BookOpen,     path: '/settings/opening-balance', superAdminOnly: true },
]

const ROLE_COLORS = {
  super_admin: 'bg-pink-100 text-pink-700',
  admin: 'bg-red-100 text-red-700',
  accountant: 'bg-blue-100 text-blue-700',
  sales: 'bg-green-100 text-green-700',
}

function NavItem({ item, collapsed }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  const active = item.children
    ? item.children.some(c => isActive(c.path))
    : isActive(item.path)

  if (item.children) {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className={clsx(
            'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all',
            active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
          )}>
          <item.icon size={18} className="flex-shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">{item.label}</span>
              {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </>
          )}
        </button>
        {open && !collapsed && (
          <div className="ml-4 mt-1 pl-4 border-l-2 border-gray-200 space-y-0.5">
            {item.children.map(child => (
              <button key={child.path}
                onClick={() => navigate(child.path)}
                className={clsx(
                  'w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                  isActive(child.path)
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-800'
                )}>
                {child.label}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <button
      onClick={() => navigate(item.path)}
      className={clsx(
        'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all',
        active ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      )}>
      <item.icon size={18} className="flex-shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </button>
  )
}

export default function AppLayout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Sidebar */}
      <aside className={clsx(
        'flex flex-col bg-white border-r border-gray-200 transition-all duration-300 flex-shrink-0',
        collapsed ? 'w-16' : 'w-60'
      )}>
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-gray-100">
          <div className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <Building2 size={16} className="text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="font-bold text-gray-900 text-sm truncate">Vignesh GrowthLab</div>
              <div className="text-xs text-gray-400">Wholesale Enterprise ERP</div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {NAV.filter(item =>
            (!item.superAdminOnly || user?.role === 'super_admin') &&
            (!item.roles || item.roles.includes(user?.role))
          ).map(item => (
            <NavItem key={item.path} item={item} collapsed={collapsed} />
          ))}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-gray-100">
          {!collapsed ? (
            <div className="flex items-center gap-2 p-2 rounded-xl hover:bg-gray-50">
              <button onClick={() => navigate('/profile')}
                className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 hover:ring-2 hover:ring-blue-200 transition-all"
                title="My Profile">
                <span className="text-white text-xs font-bold">
                  {user?.full_name?.charAt(0)?.toUpperCase() || 'A'}
                </span>
              </button>
              <button onClick={() => navigate('/profile')} className="flex-1 min-w-0 text-left">
                <div className="text-xs font-semibold text-gray-800 truncate hover:text-blue-600">{user?.full_name}</div>
                <span className={clsx('text-xs px-1.5 py-0.5 rounded-full font-medium', ROLE_COLORS[user?.role])}>
                  {user?.role}
                </span>
              </button>
              <button onClick={() => navigate('/profile')}
                className="p-1.5 rounded-lg hover:bg-blue-50 text-gray-400 hover:text-blue-500 transition-colors"
                title="My Profile">
                <UserCircle size={14} />
              </button>
              <button onClick={handleLogout}
                className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                title="Logout">
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <button onClick={() => navigate('/profile')}
                className="w-full flex items-center justify-center p-2 rounded-xl hover:bg-blue-50 text-gray-400 hover:text-blue-500"
                title="My Profile">
                <UserCircle size={16} />
              </button>
              <button onClick={handleLogout}
                className="w-full flex items-center justify-center p-2 rounded-xl hover:bg-red-50 text-gray-400 hover:text-red-500"
                title="Logout">
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 flex-shrink-0">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors">
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 relative">
              <Bell size={18} />
            </button>
            <button onClick={() => navigate('/profile')}
              className="flex items-center gap-2 pl-2 border-l border-gray-200 hover:bg-gray-50 rounded-r-lg pr-2 py-1 transition-colors"
              title="My Profile">
              <div className="w-7 h-7 bg-blue-600 rounded-full flex items-center justify-center">
                <span className="text-white text-xs font-bold">
                  {user?.full_name?.charAt(0)?.toUpperCase() || 'A'}
                </span>
              </div>
              <span className="text-sm font-medium text-gray-700">{user?.full_name}</span>
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}