import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { usersAdminAPI, sessionsAPI, activityAPI, loginHistoryAPI } from '@/api/security'
import { Button, Badge, Input, Select, Field, AlertBox, Spinner, Empty, Pagination } from '@/components/ui'
import { Plus, LogOut, Ban, Unlock, RotateCcw, AlertTriangle, X, Monitor, Activity, Pencil, Search } from 'lucide-react'
import { format, formatDistanceToNow } from 'date-fns'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import api from '@/api'
import { useAuthStore } from '@/store/authStore'

const TABS = ['Users', 'Live Sessions', 'Activity Log', 'Login History', 'Security Alerts']
// The 4 security feeds are super-admin only; the Users management tab is shared.
const SUPER_ADMIN_TABS = ['Live Sessions', 'Activity Log', 'Login History', 'Security Alerts']

function formatDuration(seconds) {
  if (seconds == null) return null
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}
const ROLE_COLORS = {
  super_admin: 'pink',
  admin: 'red', accountant: 'blue', sales: 'green',
  manager: 'purple', viewer: 'gray', warehouse: 'amber', hr: 'teal',
}
const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin', accountant: 'Accountant', sales: 'Sales',
  manager: 'Manager', viewer: 'Viewer', warehouse: 'Warehouse', hr: 'HR',
}
const getRoleColor = (role) => ROLE_COLORS[role] || 'gray'
const getRoleLabel = (role) => ROLE_LABELS[role] || (role ? role.charAt(0).toUpperCase() + role.slice(1) : '—')

const SYSTEM_ROLES = [
  { value: 'super_admin', label: 'Super Admin', deletable: false },
  { value: 'admin',      label: 'Admin',      deletable: false },
  { value: 'accountant', label: 'Accountant', deletable: false },
  { value: 'manager',    label: 'Manager',    deletable: true  },
  { value: 'sales',      label: 'Sales',      deletable: false },
  { value: 'warehouse',  label: 'Warehouse',  deletable: true  },
  { value: 'viewer',     label: 'Viewer',     deletable: true  },
  { value: 'hr',         label: 'HR',         deletable: true  },
]

function loadCustomRoles() {
  try { return JSON.parse(localStorage.getItem('erp_custom_roles') || '[]') } catch { return [] }
}
function saveCustomRoles(roles) {
  localStorage.setItem('erp_custom_roles', JSON.stringify(roles))
}
const ACTION_COLORS = {
  login: 'green', logout: 'gray', login_failed: 'red',
  user_created: 'blue', user_updated: 'blue', password_reset: 'amber',
  force_logout: 'red', account_suspended: 'red', account_unsuspended: 'green',
  account_unlocked: 'green', export: 'amber',
}


// ── Warehouse Select (single — for warehouse role) ───────────
function WarehouseSelect({ value, onChange }) {
  const { data: rawWh } = useQuery({
    queryKey: ['warehouses-list'],
    queryFn: () => api.get('/api/v1/warehouses/').then(r => r.data),
  })
  const warehouses = Array.isArray(rawWh) ? rawWh : (rawWh?.items || [])
  return (
    <select value={value || ''} onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
      className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:border-blue-500">
      <option value="">— select warehouse —</option>
      {warehouses.map(w => (
        <option key={w.id} value={w.id}>{w.name}</option>
      ))}
    </select>
  )
}

// ── Warehouse Multi-Select (admin role — min 1, max all) ─────
function WarehouseMultiSelect({ value = [], onChange, error }) {
  const { data: rawWh } = useQuery({
    queryKey: ['warehouses-list'],
    queryFn: () => api.get('/api/v1/warehouses/').then(r => r.data),
  })
  const warehouses = Array.isArray(rawWh) ? rawWh : (rawWh?.items || [])
  const selected = new Set(value.map(Number))

  const toggle = (id) => {
    const numId = Number(id)
    const next = selected.has(numId) ? value.filter(x => Number(x) !== numId) : [...value, numId]
    onChange(next)
  }
  const selectAll = () => onChange(warehouses.map(w => w.id))
  const clearAll  = () => onChange([])

  return (
    <div>
      <div className={`border rounded-lg p-2 space-y-1 max-h-40 overflow-y-auto ${error ? 'border-red-400' : 'border-gray-300'}`}>
        {warehouses.length === 0
          ? <p className="text-xs text-gray-400 px-1">No warehouses found</p>
          : warehouses.map(w => (
            <label key={w.id} className="flex items-center gap-2 px-1 py-0.5 rounded hover:bg-gray-50 cursor-pointer">
              <input type="checkbox" checked={selected.has(w.id)} onChange={() => toggle(w.id)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
              <span className="text-sm text-gray-700">{w.name}</span>
            </label>
          ))
        }
      </div>
      <div className="flex gap-3 mt-1">
        <button type="button" onClick={selectAll} className="text-xs text-blue-600 hover:underline">Select all</button>
        <button type="button" onClick={clearAll}  className="text-xs text-gray-400 hover:underline">Clear</button>
        <span className="text-xs text-gray-400 ml-auto">{value.length} of {warehouses.length} selected</span>
      </div>
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  )
}

function UsersTab() {
  const qc = useQueryClient()
  const { user: currentUser, isSuperAdmin: _isSuper } = useAuthStore()
  const isSuperAdmin = _isSuper()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [extraRoles, setExtraRoles] = useState(loadCustomRoles)
  const [selectedRole, setSelectedRole] = useState('sales')   // controls select + custom input
  const [customRoleText, setCustomRoleText] = useState('')    // text in custom input
  const [showNew, setShowNew] = useState(false)
  const [editTarget, setEditTarget] = useState(null)

  const PRIVILEGED = ['admin', 'super_admin']
  // Non-super-admins cannot pick admin / super_admin when creating users,
  // and cannot create new custom roles (the "+ Add custom role..." option).
  const allRoles = [
    ...SYSTEM_ROLES.filter(r => isSuperAdmin || !PRIVILEGED.includes(r.value)),
    ...extraRoles
      .filter(r => isSuperAdmin || !PRIVILEGED.includes(r))
      .map(r => ({ value: r, label: r.charAt(0).toUpperCase() + r.slice(1).replace(/_/g,' '), deletable: true })),
    ...(isSuperAdmin ? [{ value: '__custom__', label: '+ Add custom role...', deletable: false }] : []),
  ]

  const deleteRole = (roleValue) => {
    const updated = extraRoles.filter(r => r !== roleValue)
    setExtraRoles(updated)
    saveCustomRoles(updated)
  }
  const [resetTarget, setResetTarget] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [newUserWarehouseId, setNewUserWarehouseId] = useState(null)   // warehouse role
  const [newUserWarehouseIds, setNewUserWarehouseIds] = useState([])   // admin role

  const { register, handleSubmit, reset, watch, setValue, formState: { errors } } = useForm({
    defaultValues: { username: '', full_name: '', email: '', password: '', role: 'sales' }
  })

  const { data: rawAllWh = [] } = useQuery({
    queryKey: ['warehouses-list'],
    queryFn: () => api.get('/api/v1/warehouses/').then(r => r.data),
  })
  const allWarehouses = Array.isArray(rawAllWh) ? rawAllWh : (rawAllWh?.items || [])

  const whBadge = (id) => {
    const whs = Array.isArray(allWarehouses) ? allWarehouses : (allWarehouses?.items || [])
    const wh = whs.find(w => Number(w.id) === Number(id))
    return wh
      ? <span key={id} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full border border-blue-200">{wh.name}</span>
      : <span key={id} className="text-xs text-gray-400">{id}</span>
  }
  const getWarehouseDisplay = (user) => {
    // admin: show warehouse_ids badges (multi)
    if (user.role === 'admin' || user.role?.value === 'admin') {
      const ids = user.warehouse_ids || []
      if (!ids.length) return <span className="text-xs text-amber-500">No WH assigned</span>
      return <div className="flex flex-wrap gap-1">{ids.map(id => whBadge(id))}</div>
    }
    // warehouse role: single warehouse_id
    if (!user.warehouse_id) return <span className="text-gray-300 text-xs">—</span>
    return whBadge(user.warehouse_id)
  }

  const { data, isLoading } = useQuery({
    queryKey: ['users-admin', page, search, roleFilter],
    queryFn: () => usersAdminAPI.list({ page, page_size: 15, search: search || undefined, role: roleFilter || undefined }).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const createMutation = useMutation({
    mutationFn: (d) => usersAdminAPI.create(d),
    onSuccess: () => { qc.invalidateQueries(['users-admin']); toast.success('User created'); setShowNew(false); reset(); setNewUserWarehouseId(null); setNewUserWarehouseIds([]) },
    onError: e => {
      const d = e.response?.data?.detail
      if (Array.isArray(d)) toast.error(d.map(x => x.msg || JSON.stringify(x)).join(', '))
      else toast.error(typeof d === 'string' ? d : 'Failed to create user')
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, data }) => usersAdminAPI.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries(['users-admin'])
      toast.success('User updated successfully')
      setEditTarget(null)
    },
    onError: (e) => {
      const d = e.response?.data?.detail
      if (Array.isArray(d)) toast.error(d.map(x => x.msg || JSON.stringify(x)).join(', '))
      else toast.error(typeof d === 'string' ? d : 'Failed to update user')
    },
  })

  const actionMutation = useMutation({
    mutationFn: ({ action, id, data }) => {
      if (action === 'suspend') return usersAdminAPI.suspend(id)
      if (action === 'unsuspend') return usersAdminAPI.unsuspend(id)
      if (action === 'force-logout') return usersAdminAPI.forceLogout(id)
      if (action === 'unlock') return usersAdminAPI.unlock(id)
      if (action === 'reset-password') return usersAdminAPI.resetPassword(id, data)
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries(['users-admin'])
      const msgs = { suspend: 'Suspended', unsuspend: 'Unsuspended', 'force-logout': 'Logged out', unlock: 'Unlocked', 'reset-password': 'Password reset' }
      toast.success(msgs[vars.action] || 'Done')
      setResetTarget(null); setNewPassword('')
    },
    onError: e => {
      const d = e.response?.data?.detail
      if (Array.isArray(d)) toast.error(d.map(x => x.msg || JSON.stringify(x)).join(', '))
      else toast.error(typeof d === 'string' ? d : 'Action failed')
    },
  })

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <Input placeholder="Search users..." value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }} className="flex-1" />
        <Select value={roleFilter} onChange={e => { setRoleFilter(e.target.value); setPage(1) }} className="w-36">
          <option value="">All roles</option>
          {[...SYSTEM_ROLES, ...extraRoles.map(r => ({value:r, label:r.charAt(0).toUpperCase()+r.slice(1)}))].map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </Select>
        <Button variant="primary" size="sm" onClick={() => setShowNew(true)}><Plus size={14} /> New User</Button>
      </div>

      {showNew && (
        <div className="card mb-4 border-2 border-primary/20">
          <div className="card-header flex justify-between">
            <h3 className="font-semibold">Create New User</h3>
            <button onClick={() => setShowNew(false)} className="text-gray-400"><X size={16} /></button>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Username <span className="text-red-500">*</span></label>
                <input {...register('username', { required: 'Required', minLength: { value: 3, message: 'Min 3 chars' } })}
                  placeholder="jsmith"
                  className={clsx("w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-blue-500", errors.username ? 'border-red-400' : 'border-gray-300')} />
                {errors.username && <p className="text-xs text-red-500 mt-1">{errors.username.message}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Full Name <span className="text-red-500">*</span></label>
                <input {...register('full_name', { required: 'Required' })}
                  placeholder="John Smith"
                  className={clsx("w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-blue-500", errors.full_name ? 'border-red-400' : 'border-gray-300')} />
                {errors.full_name && <p className="text-xs text-red-500 mt-1">{errors.full_name.message}</p>}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                <input type="email" {...register('email')}
                  placeholder="john@example.com"
                  className="w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 border-gray-300" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Role <span className="text-red-500">*</span></label>
                <div className="space-y-1">
                  {/* Hidden input for react-hook-form registration */}
                  <input type="hidden" {...register('role', { required: true })} />
                  <select
                    value={selectedRole}
                    onChange={e => {
                      setSelectedRole(e.target.value)
                      setCustomRoleText('')
                      if (e.target.value !== '__custom__') setValue('role', e.target.value)
                    }}
                    className="w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 border-gray-300">
                    {allRoles.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                  {selectedRole === '__custom__' && (
                    <input
                      value={customRoleText}
                      onChange={e => {
                        const v = e.target.value.toLowerCase().replace(/\s+/g, '_')
                        setCustomRoleText(v)
                        setValue('role', v || '__custom__')
                      }}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && customRoleText) {
                          e.preventDefault()
                          const newRole = customRoleText.trim()
                          if (newRole && !extraRoles.includes(newRole)) {
                            const updated = [...extraRoles, newRole]
                            setExtraRoles(updated)
                            saveCustomRoles(updated)
                          }
                          setSelectedRole(customRoleText)
                          setValue('role', customRoleText)
                          setCustomRoleText('')
                        }
                      }}
                      placeholder="Type role name, press Enter to add & select"
                      className="mt-1 w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 border-blue-400"
                      autoFocus
                    />
                  )}
                  {/* Deletable role tags */}
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {allRoles.filter(r => r.deletable && r.value !== '__custom__').map(r => (
                      <span key={r.value}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-gray-200 bg-gray-50 text-gray-600">
                        {r.label}
                        <button type="button"
                          onClick={() => {
                            deleteRole(r.value)
                            if (selectedRole === r.value) {
                              setSelectedRole('sales')
                              setValue('role', 'sales')
                            }
                          }}
                          className="text-gray-400 hover:text-red-500 leading-none font-medium">
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Password <span className="text-red-500">*</span></label>
                <input type="password" {...register('password', { required: 'Required', minLength: { value: 8, message: 'Min 8 chars' } })}
                  placeholder="Min 8 chars"
                  className={clsx("w-full h-9 px-3 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-blue-500", errors.password ? 'border-red-400' : 'border-gray-300')} />
                {errors.password && <p className="text-xs text-red-500 mt-1">{errors.password.message}</p>}
              </div>
            </div>
            <AlertBox type="info">
              <strong>Admin</strong> — full access + user management &nbsp;|&nbsp;
              <strong>Accountant</strong> — all modules except user management &nbsp;|&nbsp;
              <strong>Manager</strong> — view all, edit billing &amp; purchase &nbsp;|&nbsp;
              <strong>Sales</strong> — billing, products, customers only &nbsp;|&nbsp;
              <strong>Warehouse</strong> — warehouse &amp; products only &nbsp;|&nbsp;
              <strong>Viewer</strong> — read-only access &nbsp;|&nbsp;
              <strong>Custom</strong> — assign page permissions in Settings
            </AlertBox>
            {selectedRole === 'admin' ? (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Assign Warehouses <span className="text-red-500">*</span>
                  <span className="text-gray-400 font-normal ml-1">(admin must have at least 1)</span>
                </label>
                <WarehouseMultiSelect
                  value={newUserWarehouseIds}
                  onChange={setNewUserWarehouseIds}
                  error={newUserWarehouseIds.length === 0 && createMutation.isError ? 'Select at least one warehouse' : null}
                />
              </div>
            ) : selectedRole === 'warehouse' ? (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Assign Warehouse <span className="text-red-500">*</span>
                </label>
                <WarehouseSelect value={newUserWarehouseId} onChange={setNewUserWarehouseId} />
              </div>
            ) : null}
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => { setShowNew(false); reset() }}>Cancel</Button>
              <Button variant="primary" loading={createMutation.isPending} onClick={handleSubmit(d => {
                if (selectedRole === 'admin' && newUserWarehouseIds.length === 0) {
                  toast.error('Admin must be assigned to at least one warehouse')
                  return
                }
                const payload = { ...d }
                if (selectedRole === 'admin') payload.warehouse_ids = newUserWarehouseIds
                else if (selectedRole === 'warehouse') payload.warehouse_id = newUserWarehouseId
                createMutation.mutate(payload)
              })}>Create User</Button>
            </div>
          </div>
        </div>
      )}

      {resetTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full mx-4 shadow-xl">
            <h3 className="font-semibold mb-1">Reset Password — {resetTarget.username}</h3>
            <p className="text-sm text-gray-500 mb-4">User will be logged out from all sessions after reset.</p>
            <Field label="New Password"><Input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Min 8 characters" /></Field>
            <div className="flex gap-3 justify-end mt-4">
              <Button variant="secondary" onClick={() => { setResetTarget(null); setNewPassword('') }}>Cancel</Button>
              <Button variant="warning" loading={actionMutation.isPending} disabled={newPassword.length < 8}
                onClick={() => actionMutation.mutate({ action: 'reset-password', id: resetTarget.id, data: { new_password: newPassword } })}>
                Reset Password
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {editTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg shadow-xl">
            <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center">
              <h3 className="font-semibold text-gray-900">Edit User — {editTarget.username}</h3>
              <button onClick={() => setEditTarget(null)} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Full Name <span className="text-red-500">*</span></label>
                  <input value={editTarget.full_name || ''}
                    onChange={e => setEditTarget(p => ({ ...p, full_name: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                  <input type="email" value={editTarget.email || ''}
                    onChange={e => setEditTarget(p => ({ ...p, email: e.target.value }))}
                    className="w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Role
                    {!isSuperAdmin && <span className="text-gray-400 font-normal"> (super-admin only)</span>}
                  </label>
                  <select value={editTarget.role || 'sales'}
                    onChange={e => setEditTarget(p => ({ ...p, role: e.target.value }))}
                    disabled={!isSuperAdmin}
                    className={clsx(
                      "w-full h-9 px-3 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500",
                      !isSuperAdmin && "bg-gray-50 text-gray-400 cursor-not-allowed"
                    )}>
                    {allRoles.filter(r => r.value !== '__custom__').map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Username <span className="text-gray-400 font-normal">(read-only)</span></label>
                  <input value={editTarget.username} readOnly
                    className="w-full h-9 px-3 rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-400 cursor-not-allowed" />
                </div>
                <div className="col-span-2">
                  {editTarget.role === 'admin' ? (
                    <>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        Assigned Warehouses <span className="text-red-500">*</span>
                        <span className="text-gray-400 font-normal ml-1">(admin must have at least 1)</span>
                      </label>
                      <WarehouseMultiSelect
                        value={editTarget.warehouse_ids || []}
                        onChange={ids => setEditTarget(p => ({ ...p, warehouse_ids: ids }))}
                        error={!(editTarget.warehouse_ids?.length) ? 'Select at least one warehouse' : null}
                      />
                    </>
                  ) : editTarget.role === 'warehouse' ? (
                    <>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Assigned Warehouse <span className="text-red-500">*</span></label>
                      <WarehouseSelect
                        value={editTarget.warehouse_id}
                        onChange={id => setEditTarget(p => ({ ...p, warehouse_id: id }))}
                      />
                    </>
                  ) : (
                    <p className="text-xs text-gray-400 italic">Warehouse assignment not applicable for this role.</p>
                  )}
                </div>
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <button onClick={() => setEditTarget(null)}
                  className="px-4 h-9 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button
                  onClick={() => {
                    if (!editTarget.full_name?.trim()) { toast.error('Full name is required'); return }
                    if (editTarget.role === 'admin' && !(editTarget.warehouse_ids?.length)) {
                      toast.error('Admin must be assigned to at least one warehouse'); return
                    }
                    const data = {
                      full_name: editTarget.full_name.trim(),
                      email: editTarget.email?.trim() || null,
                      role: editTarget.role,
                    }
                    if (editTarget.role === 'admin') {
                      data.warehouse_ids = editTarget.warehouse_ids || []
                    } else if (editTarget.role === 'warehouse') {
                      data.warehouse_id = editTarget.warehouse_id ? Number(editTarget.warehouse_id) : null
                    }
                    editMutation.mutate({ id: editTarget.id, data })
                  }}
                  disabled={editMutation.isPending}
                  className="px-4 h-9 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-60">
                  {editMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
        data?.items?.length === 0 ? <Empty message="No users found" /> : (
          <>
            <table className="table">
              <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last Login</th><th>Failed</th><th>Actions</th></tr></thead>
              <tbody>
                {data?.items?.map(u => (
                  <tr key={u.id}>
                    <td>
                      <div className="font-medium text-gray-800">{u.full_name}</div>
                      <div className="text-xs text-gray-400 font-mono">@{u.username}</div>
                      {u.email && <div className="text-xs text-gray-400">{u.email}</div>}
                    </td>
                    <td><Badge color={getRoleColor(u.role)}>{getRoleLabel(u.role)}</Badge></td>
                    <td>{getWarehouseDisplay(u)}</td>
                    <td>
                      {u.is_locked ? (() => {
                        const lu = u.locked_until ? new Date(u.locked_until) : null
                        if (lu && lu > new Date()) {
                          return <Badge color="red" title={format(lu, 'dd MMM yyyy HH:mm')}>Locked until {format(lu, 'HH:mm')}</Badge>
                        }
                        return <Badge color="red">Locked</Badge>
                      })() :
                        u.is_active ? <Badge color="green">Active</Badge> :
                          <Badge color="gray">Suspended</Badge>}
                    </td>
                    <td className="text-gray-500 text-xs">
                      {u.last_login ? formatDistanceToNow(new Date(u.last_login), { addSuffix: true }) : 'Never'}
                    </td>
                    <td className="text-center">
                      <span className={clsx('font-medium text-sm', (u.failed_login_count || 0) >= 3 ? 'text-danger' : 'text-gray-400')}>
                        {u.failed_login_count || 0}
                      </span>
                    </td>
                    <td>
                      {u.id === currentUser?.id ? (
                        <span className="text-xs text-gray-300 italic">You</span>
                      ) : (u.role === 'super_admin' && !isSuperAdmin) ? (
                        <span className="text-xs text-gray-400 italic" title="Only a super-admin can manage another super-admin">Protected</span>
                      ) : (
                        <div className="flex items-center gap-1">
                          {u.is_locked && (
                            <button title="Unlock" onClick={() => actionMutation.mutate({ action: 'unlock', id: u.id })}
                              className="p-1.5 rounded hover:bg-green-50 text-gray-400 hover:text-success"><Unlock size={13} /></button>
                          )}
                          <button title="Edit user" onClick={() => setEditTarget({ ...u, warehouse_ids: u.warehouse_ids || [] })}
                            className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600"><Pencil size={13} /></button>
                          <button title="Force logout" onClick={() => actionMutation.mutate({ action: 'force-logout', id: u.id })}
                            className="p-1.5 rounded hover:bg-amber-50 text-gray-400 hover:text-amber-600"><LogOut size={13} /></button>
                          <button title="Reset password" onClick={() => setResetTarget(u)}
                            className="p-1.5 rounded hover:bg-blue-50 text-gray-400 hover:text-primary"><RotateCcw size={13} /></button>
                          {u.is_active ? (
                            <button title="Suspend" onClick={() => actionMutation.mutate({ action: 'suspend', id: u.id })}
                              className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-danger"><Ban size={13} /></button>
                          ) : (
                            <button title="Unsuspend" onClick={() => actionMutation.mutate({ action: 'unsuspend', id: u.id })}
                              className="p-1.5 rounded hover:bg-green-50 text-gray-400 hover:text-success"><Unlock size={13} /></button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={15} onChange={setPage} />}
          </>
        )}
    </div>
  )
}

function SessionsTab() {
  const { user: currentUser } = useAuthStore()
  const qc = useQueryClient()
  const { data: sessions, isLoading } = useQuery({
    queryKey: ['active-sessions'],
    queryFn: () => sessionsAPI.active().then(r => r.data),
    refetchInterval: 30000,
  })
  const logoutMutation = useMutation({
    mutationFn: (uid) => usersAdminAPI.forceLogout(uid),
    onSuccess: () => { qc.invalidateQueries(['active-sessions']); toast.success('User logged out') },
    onError: e => toast.error(e.response?.data?.detail || 'Failed'),
  })
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-gray-500">{sessions?.length || 0} active session(s) — auto-refreshes every 30s</div>
        <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-success animate-pulse" /><span className="text-xs text-success">Live</span></div>
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
        sessions?.length === 0 ? <Empty message="No active sessions" /> : (
          <div className="space-y-3">
            {sessions?.map(s => (
              <div key={s.id} className={clsx('p-4 rounded-xl border flex items-center gap-4',
                s.user_id === currentUser?.id ? 'border-primary/30 bg-blue-50/30' : 'border-gray-200')}>
                <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                  <Monitor size={18} className="text-gray-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-medium text-gray-800">{s.full_name}</span>
                    <span className="text-xs text-gray-400 font-mono">@{s.username}</span>
                    <Badge color={getRoleColor(s.role)}>{getRoleLabel(s.role)}</Badge>
                    {s.user_id === currentUser?.id && <Badge color="blue">You</Badge>}
                  </div>
                  <div className="text-xs text-gray-500 flex gap-3 flex-wrap">
                    <span>📍 {s.ip_address || 'Unknown IP'}</span>
                    <span>⏱ {s.last_seen ? formatDistanceToNow(new Date(s.last_seen), { addSuffix: true }) : '—'}</span>
                    <span>🔑 {s.login_time ? format(new Date(s.login_time), 'dd MMM HH:mm') : '—'}</span>
                  </div>
                </div>
                {s.user_id !== currentUser?.id && (
                  <Button variant="danger" size="sm" loading={logoutMutation.isPending}
                    onClick={() => logoutMutation.mutate(s.user_id)}>
                    <LogOut size={13} /> Logout
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  )
}

function ActivityLogTab() {
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['activity-log', page, action, dateFrom, dateTo],
    queryFn: () => activityAPI.list({ page, page_size: 30, action: action || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <Select value={action} onChange={e => { setAction(e.target.value); setPage(1) }} className="w-48">
          <option value="">All actions</option>
          {['login', 'logout', 'login_failed', 'user_created', 'user_updated', 'password_reset', 'force_logout', 'account_suspended', 'export'].map(a => (
            <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
          ))}
        </Select>
        <Field label="From" className="mb-0"><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-40" /></Field>
        <Field label="To" className="mb-0"><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-40" /></Field>
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
        data?.items?.length === 0 ? <Empty message="No activity logs" /> : (
          <>
            <table className="table">
              <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Details</th><th>IP</th></tr></thead>
              <tbody>
                {data?.items?.map(log => (
                  <tr key={log.id}>
                    <td className="text-gray-400 text-xs whitespace-nowrap">{log.created_at ? format(new Date(log.created_at), 'dd MMM HH:mm:ss') : '—'}</td>
                    <td>
                      <div className="text-sm font-medium">{log.full_name}</div>
                      <div className="text-xs text-gray-400 font-mono">@{log.username}</div>
                    </td>
                    <td><Badge color={ACTION_COLORS[log.action] || 'gray'}>{log.action?.replace(/_/g, ' ')}</Badge></td>
                    <td className="text-sm text-gray-600 max-w-xs truncate">{log.details}</td>
                    <td className="text-xs font-mono text-gray-400">{log.ip_address || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={30} onChange={setPage} />}
          </>
        )}
    </div>
  )
}

function LoginHistoryTab() {
  const [page, setPage] = useState(1)
  const [username, setUsername] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['login-history', page, username, dateFrom, dateTo],
    queryFn: () => loginHistoryAPI.list({
      page, page_size: 30,
      username: username || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <Input
          placeholder="Filter by username..."
          value={username}
          onChange={e => { setUsername(e.target.value); setPage(1) }}
          className="w-56"
        />
        <Field label="From" className="mb-0"><Input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1) }} className="w-40" /></Field>
        <Field label="To" className="mb-0"><Input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1) }} className="w-40" /></Field>
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
        data?.items?.length === 0 ? <Empty message="No login history" /> : (
          <>
            <table className="table">
              <thead><tr><th>User</th><th>Login At</th><th>Logout At</th><th>Duration</th></tr></thead>
              <tbody>
                {data?.items?.map(row => (
                  <tr key={row.id}>
                    <td>
                      <div className="text-sm font-medium">{row.full_name || '—'}</div>
                      <div className="text-xs text-gray-400 font-mono">@{row.username}</div>
                    </td>
                    <td className="text-xs text-gray-500 whitespace-nowrap">
                      {row.login_at ? format(new Date(row.login_at), 'dd MMM yyyy HH:mm:ss') : '—'}
                    </td>
                    <td className="text-xs text-gray-500 whitespace-nowrap">
                      {row.logout_at ? format(new Date(row.logout_at), 'dd MMM yyyy HH:mm:ss') :
                        <Badge color="green">Active</Badge>}
                    </td>
                    <td className="text-xs text-gray-600 whitespace-nowrap">
                      {row.session_duration_seconds != null ? formatDuration(row.session_duration_seconds) :
                        row.logout_at ? '—' : <span className="text-gray-300">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={30} onChange={setPage} />}
          </>
        )}
    </div>
  )
}

function SecurityAlertsTab() {
  const { data: suspicious, isLoading } = useQuery({
    queryKey: ['suspicious'],
    queryFn: () => activityAPI.suspicious().then(r => r.data),
    refetchInterval: 300000,
  })
  const SEVERITY_COLORS = { high: 'red', medium: 'amber', low: 'blue' }
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-gray-500">Last 24 hours — refreshes every 5 minutes</div>
        {suspicious?.length > 0 && <Badge color="red"><AlertTriangle size={12} className="inline mr-1" />{suspicious.length} alert(s)</Badge>}
      </div>
      {isLoading ? <div className="flex justify-center py-8"><Spinner size={24} /></div> :
        suspicious?.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mb-3">
              <Activity size={24} className="text-success" />
            </div>
            <div className="text-sm font-medium text-gray-500">No suspicious activity in the last 24 hours</div>
          </div>
        ) : (
          <div className="space-y-3">
            {suspicious?.map((alert, i) => (
              <div key={i} className={clsx('p-4 rounded-xl border-l-4 flex items-start gap-3',
                alert.severity === 'high' ? 'border-danger bg-red-50/40' : 'border-amber-500 bg-amber-50/40')}>
                <AlertTriangle size={18} className={clsx('flex-shrink-0 mt-0.5', alert.severity === 'high' ? 'text-danger' : 'text-amber-600')} />
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Badge color={SEVERITY_COLORS[alert.severity] || 'gray'}>{alert.severity?.toUpperCase()}</Badge>
                    <span className="text-sm font-medium">{alert.type?.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="text-sm text-gray-600">{alert.description}</div>
                  {alert.user && <div className="text-xs text-gray-400 mt-1 font-mono">@{alert.user}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  )
}

export default function UsersPage() {
  const { isSuperAdmin } = useAuthStore()
  const visibleTabs = isSuperAdmin() ? TABS : TABS.filter(t => !SUPER_ADMIN_TABS.includes(t))
  const [activeTab, setActiveTab] = useState('Users')
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Administration</div>
          <h1 className="page-title">Users & Security</h1>
        </div>
      </div>
      <div className="flex border-b border-gray-200 mb-4">
        {visibleTabs.map(tab => (
          <button key={tab}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700')}
            onClick={() => setActiveTab(tab)}>{tab}</button>
        ))}
      </div>
      <div className="card"><div className="p-4">
        {activeTab === 'Users' && <UsersTab />}
        {activeTab === 'Live Sessions' && <SessionsTab />}
        {activeTab === 'Activity Log' && <ActivityLogTab />}
        {activeTab === 'Login History' && <LoginHistoryTab />}
        {activeTab === 'Security Alerts' && <SecurityAlertsTab />}
      </div></div>
    </div>
  )
}