import api from './index'

// Super-admin-only audit trail. Backed by GET /api/v1/activity-log/audit
export const auditAPI = {
  list: (params) => api.get('/api/v1/activity-log/audit', { params }),
}
