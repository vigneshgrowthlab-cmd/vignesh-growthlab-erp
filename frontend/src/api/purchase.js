import api from './index'

export const vendorAPI = {
  list: (params) => api.get('/api/v1/vendors/', { params }),
  get: (id) => api.get(`/api/v1/vendors/${id}`),
  create: (d) => api.post('/api/v1/vendors/', d),
  update: (id, d) => api.put(`/api/v1/vendors/${id}`, d),
  addAddress: (id, d) => api.post(`/api/v1/vendors/${id}/addresses`, d),
  ledger: (id, params) => api.get(`/api/v1/vendors/${id}/ledger`, { params }),
  gstinLookup: (gstin) => api.get(`/api/v1/vendors/gstin-lookup/${gstin}`),
  importTemplate: () => api.get('/api/v1/vendors/import/template', { responseType: 'blob' }),
  bulkImport: (file) => { const fd = new FormData(); fd.append('file', file); return api.post('/api/v1/vendors/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } }) },
}

export const purchaseAPI = {
  list: (params) => api.get('/api/v1/purchases/', { params }),
  get: (id) => api.get(`/api/v1/purchases/${id}`),
  create: (d) => api.post('/api/v1/purchases/', d),
  cancel: (id) => api.post(`/api/v1/purchases/${id}/cancel`),
}

export const vendorPaymentAPI = {
  list: (params) => api.get('/api/v1/vendor-payments/', { params }),
  create: (d) => api.post('/api/v1/vendor-payments/', d),
}
