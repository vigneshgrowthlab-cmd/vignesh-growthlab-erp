import api from './index'

export const usersAdminAPI = {
  list: (params) => api.get('/api/v1/users-admin/', { params }),
  get: (id) => api.get(`/api/v1/users-admin/${id}`),
  create: (d) => api.post('/api/v1/users-admin/', d),
  update: (id, d) => api.put(`/api/v1/users-admin/${id}`, d),
  resetPassword: (id, d) => api.post(`/api/v1/users-admin/${id}/reset-password`, d),
  forceLogout: (id) => api.post(`/api/v1/users-admin/${id}/force-logout`),
  suspend: (id) => api.post(`/api/v1/users-admin/${id}/suspend`),
  unsuspend: (id) => api.post(`/api/v1/users-admin/${id}/unsuspend`),
  unlock: (id) => api.post(`/api/v1/users-admin/${id}/unlock`),
}

export const sessionsAPI = {
  active: () => api.get('/api/v1/sessions/active'),
}

export const activityAPI = {
  list: (params) => api.get('/api/v1/activity-log/', { params }),
  suspicious: () => api.get('/api/v1/activity-log/suspicious'),
}

export const loginHistoryAPI = {
  list: (params) => api.get('/api/v1/login-history/', { params }),
}
