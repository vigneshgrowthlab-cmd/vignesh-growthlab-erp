import { clsx } from 'clsx'
import { Loader2, AlertCircle, Info, CheckCircle, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react'

// ── Button ────────────────────────────────────────────────────
export function Button({
  children, variant = 'primary', size = 'md',
  loading = false, disabled = false, onClick,
  type = 'button', className = ''
}) {
  const base = 'inline-flex items-center justify-center gap-1.5 font-medium rounded-lg transition-all duration-150 cursor-pointer select-none disabled:opacity-50 disabled:cursor-not-allowed'
  const sizes = {
    xs: 'h-6 px-2 text-xs',
    sm: 'h-8 px-3 text-xs',
    md: 'h-9 px-4 text-sm',
    lg: 'h-11 px-6 text-base',
  }
  const variants = {
    primary:   'bg-blue-600 text-white hover:bg-blue-700 shadow-sm',
    secondary: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 shadow-sm',
    danger:    'bg-red-600 text-white hover:bg-red-700 shadow-sm',
    warning:   'bg-amber-500 text-white hover:bg-amber-600 shadow-sm',
    success:   'bg-green-600 text-white hover:bg-green-700 shadow-sm',
    ghost:     'text-gray-600 hover:bg-gray-100',
  }
  return (
    <button type={type} onClick={onClick}
      disabled={disabled || loading}
      className={clsx(base, sizes[size], variants[variant], className)}>
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  )
}

// ── Input ─────────────────────────────────────────────────────
export function Input({ className = '', error, ...props }) {
  return (
    <input
      className={clsx(
        'w-full h-9 px-3 rounded-lg border text-sm text-gray-800 bg-white placeholder-gray-400',
        'focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors',
        error ? 'border-red-400 focus:ring-red-500/20 focus:border-red-500' : 'border-gray-300',
        className
      )}
      {...props}
    />
  )
}

// ── Select ────────────────────────────────────────────────────
export function Select({ className = '', error, children, ...props }) {
  return (
    <select
      className={clsx(
        'w-full h-9 px-3 rounded-lg border text-sm text-gray-800 bg-white',
        'focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors cursor-pointer',
        error ? 'border-red-400' : 'border-gray-300',
        className
      )}
      {...props}>
      {children}
    </select>
  )
}

// ── Field ─────────────────────────────────────────────────────
export function Field({ label, children, error, hint, required, className = '' }) {
  return (
    <div className={clsx('flex flex-col gap-1', className)}>
      {label && (
        <label className="text-xs font-medium text-gray-600">
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
      )}
      {children}
      {hint && !error && <p className="text-xs text-gray-400">{hint}</p>}
      {error && <p className="text-xs text-red-500">{typeof error === 'string' ? error : error?.message}</p>}
    </div>
  )
}

// ── Badge ─────────────────────────────────────────────────────
export function Badge({ children, color = 'gray', className = '' }) {
  const colors = {
    gray:   'bg-gray-100 text-gray-600',
    blue:   'bg-blue-100 text-blue-700',
    green:  'bg-green-100 text-green-700',
    red:    'bg-red-100 text-red-700',
    amber:  'bg-amber-100 text-amber-700',
    teal:   'bg-teal-100 text-teal-700',
    purple: 'bg-purple-100 text-purple-700',
    orange: 'bg-orange-100 text-orange-700',
  }
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
      colors[color] || colors.gray, className
    )}>
      {children}
    </span>
  )
}

// ── Spinner ───────────────────────────────────────────────────
export function Spinner({ size = 20, className = '' }) {
  return (
    <Loader2
      size={size}
      className={clsx('animate-spin text-blue-600', className)}
    />
  )
}

// ── Empty ─────────────────────────────────────────────────────
export function Empty({ message = 'No data found', action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0H4"/>
        </svg>
      </div>
      <p className="text-sm font-medium text-gray-500 mb-1">{message}</p>
      <p className="text-xs text-gray-400 mb-4">No records to display</p>
      {action && <div>{action}</div>}
    </div>
  )
}

// ── AlertBox ──────────────────────────────────────────────────
export function AlertBox({ type = 'info', children, className = '' }) {
  const styles = {
    info:    { cls: 'bg-blue-50 border-blue-200 text-blue-800',   Icon: Info },
    success: { cls: 'bg-green-50 border-green-200 text-green-800', Icon: CheckCircle },
    warning: { cls: 'bg-amber-50 border-amber-200 text-amber-800', Icon: AlertTriangle },
    danger:  { cls: 'bg-red-50 border-red-200 text-red-800',      Icon: AlertCircle },
  }
  const { cls, Icon } = styles[type] || styles.info
  return (
    <div className={clsx('flex items-start gap-2.5 p-3 rounded-lg border text-sm', cls, className)}>
      <Icon size={16} className="flex-shrink-0 mt-0.5" />
      <div>{children}</div>
    </div>
  )
}

// ── Pagination ────────────────────────────────────────────────
export function Pagination({ page, pages, total, pageSize, onChange }) {
  if (!pages || pages <= 1) return null
  const from = ((page - 1) * pageSize) + 1
  const to = Math.min(page * pageSize, total)
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
      <p className="text-xs text-gray-500">
        Showing <span className="font-medium">{from}</span> to <span className="font-medium">{to}</span> of <span className="font-medium">{total}</span> results
      </p>
      <div className="flex items-center gap-1">
        <button onClick={() => onChange(page - 1)} disabled={page === 1}
          className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">
          <ChevronLeft size={14} />
        </button>
        {Array.from({ length: Math.min(5, pages) }, (_, i) => {
          let pageNum
          if (pages <= 5) pageNum = i + 1
          else if (page <= 3) pageNum = i + 1
          else if (page >= pages - 2) pageNum = pages - 4 + i
          else pageNum = page - 2 + i
          return (
            <button key={pageNum} onClick={() => onChange(pageNum)}
              className={clsx(
                'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                page === pageNum
                  ? 'bg-blue-600 text-white'
                  : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
              )}>
              {pageNum}
            </button>
          )
        })}
        <button onClick={() => onChange(page + 1)} disabled={page === pages}
          className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────
export function Modal({ title, children, onClose, width = 'max-w-lg' }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className={clsx('bg-white rounded-2xl shadow-2xl w-full max-h-[90vh] overflow-hidden flex flex-col', width)}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800 text-base">{title}</h3>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto flex-1 p-5">
          {children}
        </div>
      </div>
    </div>
  )
}

// ── Textarea ──────────────────────────────────────────────────
export function Textarea({ className = '', error, ...props }) {
  return (
    <textarea
      className={clsx(
        'w-full px-3 py-2 rounded-lg border text-sm text-gray-800 bg-white placeholder-gray-400 resize-none',
        'focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors',
        error ? 'border-red-400' : 'border-gray-300',
        className
      )}
      rows={3}
      {...props}
    />
  )
}

// ── Toggle ────────────────────────────────────────────────────
export function Toggle({ checked, onChange, label, disabled = false }) {
  return (
    <label className={clsx(
      'flex items-center gap-3 cursor-pointer select-none',
      disabled && 'opacity-50 cursor-not-allowed'
    )}>
      <div className="relative">
        <input
          type="checkbox"
          className="sr-only"
          checked={checked}
          onChange={onChange}
          disabled={disabled}
        />
        <div className={clsx(
          'w-10 h-6 rounded-full transition-colors duration-200',
          checked ? 'bg-blue-600' : 'bg-gray-300'
        )} />
        <div className={clsx(
          'absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200',
          checked ? 'translate-x-5' : 'translate-x-1'
        )} />
      </div>
      {label && <span className="text-sm text-gray-700">{label}</span>}
    </label>
  )
}

// ── ReadonlyField ─────────────────────────────────────────────
export function ReadonlyField({ label, value, className = '' }) {
  return (
    <div className={clsx('flex flex-col gap-1', className)}>
      {label && (
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          {label}
        </label>
      )}
      <div className="h-9 px-3 flex items-center rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-700">
        {value || <span className="text-gray-400">—</span>}
      </div>
    </div>
  )
}

// ── ConfirmDialog ─────────────────────────────────────────────
export function ConfirmDialog({
  title = 'Confirm Action',
  message = 'Are you sure you want to proceed?',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
  loading = false,
}) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        <div className="p-6">
          <div className={clsx(
            'w-12 h-12 rounded-2xl flex items-center justify-center mb-4',
            variant === 'danger' ? 'bg-red-100' : 'bg-amber-100'
          )}>
            <AlertCircle
              size={24}
              className={variant === 'danger' ? 'text-red-600' : 'text-amber-600'}
            />
          </div>
          <h3 className="font-semibold text-gray-900 text-lg mb-2">{title}</h3>
          <p className="text-sm text-gray-500">{message}</p>
        </div>
        <div className="flex gap-3 px-6 pb-6">
          <button
            onClick={onCancel}
            className="flex-1 h-10 rounded-xl border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={clsx(
              'flex-1 h-10 rounded-xl text-sm font-medium text-white transition-colors flex items-center justify-center gap-2 disabled:opacity-60',
              variant === 'danger' ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-500 hover:bg-amber-600'
            )}>
            {loading && <Loader2 size={14} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── StatCard ──────────────────────────────────────────────────
export function StatCard({ label, value, sub, icon: Icon, color = 'blue', onClick }) {
  const colors = {
    blue:   'bg-blue-50 text-blue-600',
    green:  'bg-green-50 text-green-600',
    red:    'bg-red-50 text-red-600',
    amber:  'bg-amber-50 text-amber-600',
    gray:   'bg-gray-100 text-gray-500',
    purple: 'bg-purple-50 text-purple-600',
  }
  return (
    <div
      onClick={onClick}
      className={clsx(
        'bg-white rounded-xl border border-gray-200 shadow-sm p-4',
        onClick && 'cursor-pointer hover:shadow-md transition-shadow'
      )}>
      {Icon && (
        <div className={clsx(
          'w-10 h-10 rounded-xl flex items-center justify-center mb-3',
          colors[color]
        )}>
          <Icon size={20} />
        </div>
      )}
      <div className="text-2xl font-bold text-gray-900">{value}</div>
      <div className="text-xs font-medium text-gray-500 mt-1 uppercase tracking-wide">{label}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  )
}

// ── Table ─────────────────────────────────────────────────────
export function Table({ children, className = '' }) {
  return (
    <div className={clsx('overflow-x-auto', className)}>
      <table className="w-full text-sm">
        {children}
      </table>
    </div>
  )
}

export function Thead({ children }) {
  return (
    <thead className="border-b border-gray-200 bg-gray-50">
      {children}
    </thead>
  )
}

export function Th({ children, className = '' }) {
  return (
    <th className={clsx(
      'px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide',
      className
    )}>
      {children}
    </th>
  )
}

export function Tbody({ children }) {
  return <tbody className="divide-y divide-gray-100">{children}</tbody>
}

export function Tr({ children, onClick, className = '' }) {
  return (
    <tr
      onClick={onClick}
      className={clsx(
        'hover:bg-gray-50 transition-colors',
        onClick && 'cursor-pointer',
        className
      )}>
      {children}
    </tr>
  )
}

export function Td({ children, className = '' }) {
  return (
    <td className={clsx('px-4 py-3 text-gray-700', className)}>
      {children}
    </td>
  )
}

// ── Tabs ──────────────────────────────────────────────────────
export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex border-b border-gray-200 overflow-x-auto">
      {tabs.map(tab => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={clsx(
            'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
            active === tab
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          )}>
          {tab}
        </button>
      ))}
    </div>
  )
}

// ── SearchInput ───────────────────────────────────────────────
export function SearchInput({ value, onChange, placeholder = 'Search...', className = '' }) {
  return (
    <div className={clsx('relative', className)}>
      <svg
        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
        width="14" height="14" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="m21 21-4.35-4.35"/>
      </svg>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full h-9 pl-9 pr-3 rounded-lg border border-gray-300 text-sm text-gray-800 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
      />
    </div>
  )
}