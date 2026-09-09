import api from './index'

// Config governance API (Phase 6). Super-admin only on the backend.
export const configAPI = {
  listDefinitions: (domain)              => api.get('/api/v1/config/definitions', { params: domain ? { domain } : {} }),
  listValues:      (key, includeHistory = true) => api.get('/api/v1/config/values', { params: { key, include_history: includeHistory } }),
  effective:       (key, asOf)           => api.get('/api/v1/config/effective', { params: { key, ...(asOf ? { as_of: asOf } : {}) } }),
  propose:         (d)                   => api.post('/api/v1/config/values', d),
  activate:        (id)                  => api.post(`/api/v1/config/values/${id}/activate`),
  expire:          (id, effective_to)    => api.post(`/api/v1/config/values/${id}/expire`, { effective_to }),
  revoke:          (id)                  => api.post(`/api/v1/config/values/${id}/revoke`),
  runScheduler:    ()                    => api.post('/api/v1/config/run-scheduler'),
}
