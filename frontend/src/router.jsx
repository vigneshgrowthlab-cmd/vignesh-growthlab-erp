import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import AppLayout from '@/components/layout/AppLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import ProductsPage from '@/pages/products/ProductsPage'
import ProductFormPage from '@/pages/products/ProductFormPage'
import CostTrendPage from '@/pages/products/CostTrendPage'
import PurchasePage from '@/pages/purchase/PurchasePage'
import PurchaseFormPage from '@/pages/purchase/PurchaseFormPage'
import PurchaseDetailPage from '@/pages/purchase/PurchaseDetailPage'
import VendorsPage from '@/pages/vendors/VendorsPage'
import VendorListPage from '@/pages/purchase/VendorListPage'
import VendorPaymentsPage from '@/pages/purchase/VendorPaymentsPage'
import BillingPage from '@/pages/billing/BillingPage'
import InvoiceFormPage from '@/pages/billing/InvoiceFormPage'
import InvoiceDetailPage from '@/pages/billing/InvoiceDetailPage'
import ReceiptsPage from '@/pages/billing/ReceiptsPage'
import CustomersPage from '@/pages/customers/CustomersPage'
import CustomerFormPage from '@/pages/customers/CustomerFormPage'
import WarehousePage from '@/pages/warehouse/WarehousePage'
import AccountingPage from '@/pages/accounting/AccountingPage'
import GSTPage from '@/pages/gst/GSTPage'
import ReportsPage from '@/pages/reports/ReportsPage'
import BankPage from '@/pages/bank/BankPage'
import UsersPage from '@/pages/users/UsersPage'
import ProfilePage from '@/pages/profile/ProfilePage'
import SettingsPage from '@/pages/settings/SettingsPage'
import OpeningBalancePage from '@/pages/settings/OpeningBalancePage'
import ConfigAdminPage from '@/pages/settings/ConfigAdminPage'
import { Navigate as Nav } from 'react-router-dom'
import PriceTrendPage from '@/pages/products/PriceTrendPage'
import AuditLogPage from '@/pages/audit/AuditLogPage'

function RequireAuth({ children }) {
  const { user, isLoading } = useAuthStore()
  if (isLoading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full" />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  return children
}

function RequireSuperAdmin({ children }) {
  const { user } = useAuthStore()
  if (user?.role !== 'super_admin') return <Navigate to="/" replace />
  return children
}

function RequireAdmin({ children }) {
  const { user } = useAuthStore()
  if (!['super_admin', 'admin'].includes(user?.role)) return <Navigate to="/" replace />
  return children
}

function RequireRoles({ roles, children }) {
  const { user } = useAuthStore()
  if (!roles.includes(user?.role)) return <Navigate to="/" replace />
  return children
}

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      // Dashboard
      { index: true, element: <DashboardPage /> },

      // Products
      { path: 'products',              element: <ProductsPage /> },
      { path: 'products/new',          element: <ProductFormPage /> },
      { path: 'products/:id',          element: <ProductFormPage /> },
      { path: 'products/:id/cost-trend', element: <CostTrendPage /> },

      // Purchase
      { path: 'purchase',              element: <PurchasePage /> },
      { path: 'purchase/new',          element: <PurchaseFormPage /> },
      { path: 'purchase/:id',          element: <PurchaseDetailPage /> },
      { path: 'purchase/vendors',      element: <VendorListPage /> },
      { path: 'purchase/vendors/new',  element: <VendorsPage /> },
      { path: 'purchase/vendors/:id',  element: <VendorsPage /> },
      { path: 'purchase/payments',     element: <VendorPaymentsPage /> },
	  

      // Billing
      { path: 'billing',               element: <BillingPage /> },
      { path: 'billing/new',           element: <InvoiceFormPage /> },
      { path: 'billing/:id',           element: <InvoiceDetailPage /> },
      { path: 'billing/receipts',      element: <ReceiptsPage /> },
      { path: 'billing/customers',     element: <CustomersPage /> },
      { path: 'billing/customers/new', element: <CustomerFormPage /> },
      { path: 'billing/customers/:id', element: <CustomerFormPage /> },
      { path: 'billing/customers/:id/ledger', element: <ReportsPage /> },

      // Warehouse
      { path: 'warehouse',                      element: <WarehousePage /> },
      //{ path: 'warehouse/opening-balances',     element: <OpeningBalancePage /> },

      // Accounting
      { path: 'accounting',            element: <AccountingPage /> },

      // GST
      { path: 'gst',                   element: <GSTPage /> },

      // Reports
      { path: 'reports',               element: <ReportsPage /> },

      // Bank
      { path: 'bank-statement',        element: <BankPage /> },

      // Users & Security
      { path: 'users',                 element: <RequireRoles roles={['super_admin', 'admin', 'accountant']}><UsersPage /></RequireRoles> },

      // Audit Log (super-admin only)
      { path: 'audit-log',             element: <RequireSuperAdmin><AuditLogPage /></RequireSuperAdmin> },

      // Profile (self-edit)
      { path: 'profile',               element: <ProfilePage /> },

      // Settings
      { path: 'settings',              element: <RequireAdmin><SettingsPage /></RequireAdmin> },
      { path: 'settings/opening-balance', element: <RequireSuperAdmin><OpeningBalancePage /></RequireSuperAdmin> },
      { path: 'settings/config',       element: <RequireSuperAdmin><ConfigAdminPage /></RequireSuperAdmin> },

      // Catch all — redirect to dashboard
      { path: '*',                     element: <Navigate to="/" replace /> },
	  
	  // Price Trend
      { path: 'products/price-trend',  element: <PriceTrendPage /> },
    ],
  },
])

export default function AppRouter() {
  return <RouterProvider router={router} />
}