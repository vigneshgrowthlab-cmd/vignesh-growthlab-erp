import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { authAPI } from '@/api'
import { useAuthStore } from '@/store/authStore'
import { Button, Input, Field, AlertBox } from '@/components/ui'
import { User, Lock } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'

const ROLE_COLORS = {
  super_admin: 'bg-pink-100 text-pink-700',
  admin: 'bg-red-100 text-red-700',
  accountant: 'bg-blue-100 text-blue-700',
  sales: 'bg-green-100 text-green-700',
  manager: 'bg-purple-100 text-purple-700',
  viewer: 'bg-gray-100 text-gray-700',
  warehouse: 'bg-amber-100 text-amber-700',
  hr: 'bg-teal-100 text-teal-700',
}

function ProfileInfoCard() {
  const { user, updateUser } = useAuthStore()
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [email, setEmail] = useState(user?.email || '')

  const dirty = fullName !== (user?.full_name || '') || email !== (user?.email || '')

  const mutation = useMutation({
    mutationFn: (d) => authAPI.updateProfile(d).then(r => r.data),
    onSuccess: (data) => {
      updateUser({ full_name: data.full_name, email: data.email })
      toast.success('Profile updated')
    },
    onError: e => {
      const d = e.response?.data?.detail
      toast.error(typeof d === 'string' ? d : 'Failed to update profile')
    },
  })

  const handleSave = () => {
    if (!fullName.trim()) { toast.error('Full name is required'); return }
    if (!email.trim()) { toast.error('Email is required'); return }
    mutation.mutate({ full_name: fullName.trim(), email: email.trim() })
  }

  return (
    <div className="card">
      <div className="card-header flex items-center gap-2">
        <User size={16} className="text-gray-500" />
        <h3 className="font-semibold">Account Information</h3>
      </div>
      <div className="card-body space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Username">
            <Input value={user?.username || ''} readOnly className="bg-gray-50 text-gray-500 cursor-not-allowed" />
          </Field>
          <Field label="Role">
            <div className="h-9 flex items-center">
              <span className={clsx('text-xs px-2 py-1 rounded-full font-medium capitalize', ROLE_COLORS[user?.role] || 'bg-gray-100 text-gray-700')}>
                {user?.role || '—'}
              </span>
            </div>
          </Field>
          <Field label="Full Name">
            <Input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Your name" />
          </Field>
          <Field label="Email">
            <Input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
          </Field>
        </div>
        <div className="flex justify-end">
          <Button variant="primary" loading={mutation.isPending} disabled={!dirty} onClick={handleSave}>
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  )
}

function ChangePasswordCard() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const mutation = useMutation({
    mutationFn: (d) => authAPI.changePassword(d),
    onSuccess: () => {
      toast.success('Password changed')
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('')
    },
    onError: e => {
      const d = e.response?.data?.detail
      toast.error(typeof d === 'string' ? d : 'Failed to change password')
    },
  })

  const handleSave = () => {
    if (!currentPassword) { toast.error('Enter your current password'); return }
    if (newPassword.length < 8) { toast.error('New password must be at least 8 characters'); return }
    if (newPassword !== confirmPassword) { toast.error('Passwords do not match'); return }
    if (newPassword === currentPassword) { toast.error('New password must differ from current'); return }
    mutation.mutate({ current_password: currentPassword, new_password: newPassword })
  }

  return (
    <div className="card">
      <div className="card-header flex items-center gap-2">
        <Lock size={16} className="text-gray-500" />
        <h3 className="font-semibold">Change Password</h3>
      </div>
      <div className="card-body space-y-4">
        <AlertBox type="info">
          After changing your password you can keep using your current session — only future logins will require the new password.
        </AlertBox>
        <div className="grid grid-cols-1 gap-3 max-w-md">
          <Field label="Current Password">
            <Input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Enter current password" />
          </Field>
          <Field label="New Password">
            <Input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Min 8 characters" />
          </Field>
          <Field label="Confirm New Password">
            <Input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="Repeat new password" />
          </Field>
        </div>
        <div className="flex justify-end">
          <Button variant="primary" loading={mutation.isPending}
            disabled={!currentPassword || !newPassword || !confirmPassword}
            onClick={handleSave}>
            Change Password
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ProfilePage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="breadcrumb">Account</div>
          <h1 className="page-title">My Profile</h1>
        </div>
      </div>
      <div className="space-y-4 max-w-3xl">
        <ProfileInfoCard />
        <ChangePasswordCard />
      </div>
    </div>
  )
}
