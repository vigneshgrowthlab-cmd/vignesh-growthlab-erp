import api from './index'

export const settingsAPI = {
  getCompany:           ()        => api.get('/api/v1/settings/company'),
  updateCompany:        (d)       => api.put('/api/v1/settings/company', d),
  getSequences:         ()        => api.get('/api/v1/settings/invoice-sequences'),
  updateSequence:       (id, d)   => api.put(`/api/v1/settings/invoice-sequences/${id}`, d),
  getStates:            ()        => api.get('/api/v1/settings/states'),
  getTdsSections:       ()        => api.get('/api/v1/settings/tds-sections'),
  createTdsSection:     (d)       => api.post('/api/v1/settings/tds-sections', d),
  deleteTdsSection:     (id)      => api.delete(`/api/v1/settings/tds-sections/${id}`),
  getGstRates:          ()        => api.get('/api/v1/settings/gst-rates'),
  createGstRate:        (d)       => api.post('/api/v1/settings/gst-rates', d),
  deleteGstRate:        (id)      => api.delete(`/api/v1/settings/gst-rates/${id}`),
  getUsersPermissions: ()        => api.get('/api/v1/settings/users-permissions'),
  updateUserPermissions: (id, d)  => api.put(`/api/v1/settings/users-permissions/${id}`, d),
  // Vehicles live under /api/v1/vehicles/ (gst module), not under /settings/.
  // The /settings/vehicles routes don't exist — calling them returned 404.
  getVehicles:           ()        => api.get('/api/v1/vehicles/'),
  createVehicle:         (d)       => api.post('/api/v1/vehicles/', d),
  updateVehicle:         (id, d)   => api.put(`/api/v1/vehicles/${id}`, d),
  deleteVehicle:         (id)      => api.delete(`/api/v1/vehicles/${id}`),
  uploadLogo:           (formData) => api.post('/api/v1/settings/company/logo', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  // DPDP
  getDpdpRetentionPolicies: ()          => api.get('/api/v1/dpdp/retention-policies'),
  getDpdpRetentionPreview:  ()          => api.get('/api/v1/dpdp/retention-preview'),
  enforceDpdpRetention:     (dryRun)    => api.post(`/api/v1/dpdp/retention-enforce?dry_run=${dryRun}`),
  getErasureRequests:       (status)    => api.get('/api/v1/dpdp/erasure-requests', { params: status ? { status } : {} }),
  createErasureRequest:     (d)         => api.post('/api/v1/dpdp/erasure-requests', d),
  processErasureRequest:    (id)        => api.post(`/api/v1/dpdp/erasure-requests/${id}/process`),
}
