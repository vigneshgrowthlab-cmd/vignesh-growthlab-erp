import api from './index'

export const warehouseAPI = {
  list: (params) => api.get('/api/v1/warehouses/', { params }),
  get: (id) => api.get(`/api/v1/warehouses/${id}`),
  create: (d) => api.post('/api/v1/warehouses/', d),
  update: (id, d) => api.put(`/api/v1/warehouses/${id}`, d),
  rename: (id, d) => api.put(`/api/v1/warehouses/${id}/rename`, d),
  validateObsolete: (id) => api.get(`/api/v1/warehouses/${id}/validate-obsolete`),
  obsolete: (id) => api.post(`/api/v1/warehouses/${id}/obsolete`),
  validateDelete: (id) => api.get(`/api/v1/warehouses/${id}/validate-delete`),
  delete: (id) => api.delete(`/api/v1/warehouses/${id}`),
  stock: (params) => api.get('/api/v1/warehouses/stock', { params }),
  consolidatedStock: (productId, warehouseId) =>
    api.get(`/api/v1/warehouses/stock/consolidated/${productId}`, { params: { warehouse_id: warehouseId } }),
  ageing: (params) => api.get('/api/v1/warehouses/stock/ageing', { params }),
}

export const transferAPI = {
  list: (params) => api.get('/api/v1/stock-transfers/', { params }),
  get: (id) => api.get(`/api/v1/stock-transfers/${id}`),
  create: (d) => api.post('/api/v1/stock-transfers/', d),
  linkDC: (id, dc_id) => api.put(`/api/v1/stock-transfers/${id}/link-dc`, { dc_id }),
  unlinkDC: (id, dc_id) => api.put(`/api/v1/stock-transfers/${id}/unlink-dc`, { dc_id }),
  confirmDC: (id, dc_id) => api.post(`/api/v1/stock-transfers/${id}/confirm-dc`, { dc_id }),
  rejectDC: (id, dc_id, reason) =>
    api.post(`/api/v1/stock-transfers/${id}/reject-dc`, { dc_id, reason }),
}

export const adjustmentAPI = {
  list: (params) => api.get('/api/v1/stock-adjustments/', { params }),
  create: (d) => api.post('/api/v1/stock-adjustments/', d),
}

export const writeoffAPI = {
  list: (params) => api.get('/api/v1/stock-writeoffs/', { params }),
  create: (d) => api.post('/api/v1/stock-writeoffs/', d),
  approve: (id, d) => api.post(`/api/v1/stock-writeoffs/${id}/approve`, d),
}

export const openingAPI = {
  create: (d) => api.post('/api/v1/opening-balances/', d),
  downloadStockTemplate: () =>
    api.get('/api/v1/opening-balances/stock-template/csv', { responseType: 'blob' }),
  bulkUploadStock: (file, openingDate) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/api/v1/opening-balances/stock/bulk-upload', fd, {
      params: { opening_date: openingDate },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
