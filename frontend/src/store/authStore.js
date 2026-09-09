import { create } from 'zustand'
import { authAPI } from '@/api'

// All pages with their display labels
export const ALL_PAGES = [
  { key: 'dashboard',   label: 'Dashboard' },
  { key: 'products',    label: 'Products' },
  { key: 'purchase',    label: 'Purchase' },
  { key: 'billing',     label: 'Billing / Invoices' },
  { key: 'customers',   label: 'Customers' },
  { key: 'warehouse',   label: 'Warehouse' },
  { key: 'accounting',  label: 'Accounting' },
  { key: 'gst',         label: 'GST' },
  { key: 'reports',     label: 'Reports' },
  { key: 'bank',        label: 'Bank' },
  { key: 'security',    label: 'Security' },
  { key: 'users',       label: 'Users' },
  { key: 'settings',    label: 'Settings' },
]

export const useAuthStore = create((set, get) => ({
  user: null,
  isLoading: true,
  warehouse_id: null,

  init: async () => {
    const token = sessionStorage.getItem('access_token')
    if (!token) { set({ isLoading: false }); return }
    try {
      const { data } = await authAPI.me()
      set({ user: data, warehouse_id: data.warehouse_id || null, isLoading: false })
    } catch {
      sessionStorage.clear()
      set({ user: null, isLoading: false })
    }
  },

  login: async (username, password) => {
    const { data } = await authAPI.login({ username, password })
    sessionStorage.setItem('access_token', data.access_token)
    sessionStorage.setItem('refresh_token', data.refresh_token)
    set({ user: data.user })
    return data.user
  },

  logout: async () => {
    try { await authAPI.logout() } catch {}
    sessionStorage.clear()
    set({ user: null })
  },

  updateUser: (updates) => set(state => ({ user: { ...(state.user || {}), ...updates } })),

  // Super-admin inherits all admin powers — isAdmin returns true for both
  isAdmin:      () => ['admin', 'super_admin'].includes(get().user?.role),
  isSuperAdmin: () => get().user?.role === 'super_admin',
  isWarehouseRole: () => get().user?.role === 'warehouse',
  isSalesRole:  () => get().user?.role === 'sales',
  getUserWarehouse: () => get().warehouse_id || null,
  hasWarehouseAccess: (warehouseId) => {
    const wid = get().warehouse_id
    if (!wid) return true  // no restriction = all access
    return Number(wid) === Number(warehouseId)
  },
  isAccountant: () => get().user?.role === 'accountant',
  isSales:      () => get().user?.role === 'sales',

  // Check if user can access a page
  // Admin always has access. Others: if page_permissions is null → full access, else check list
  hasPageAccess: (pageKey) => {
    const user = get().user
    if (!user) return false
    if (user.role === 'admin' || user.role === 'super_admin') return true
    const perms = user.page_permissions
    if (perms === null || perms === undefined) return true // no restriction
    return Array.isArray(perms) && perms.includes(pageKey)
  },

  canSee: (field) => {
    const role = get().user?.role
    if (field === 'purchase_cost') return ['admin', 'super_admin', 'accountant'].includes(role)
    if (field === 'profit')        return role === 'super_admin'
    return true
  },
}))
