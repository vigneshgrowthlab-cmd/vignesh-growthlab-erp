import api from './index'

export const transporterAPI = {
  list:   ()        => api.get('/api/v1/transporters/'),
  create: (d)       => api.post('/api/v1/transporters/', d),
  update: (id, d)   => api.put(`/api/v1/transporters/${id}`, d),
  delete: (id)      => api.delete(`/api/v1/transporters/${id}`),
}

export const vehicleAPI = {
  list:   (params)  => api.get('/api/v1/vehicles/', { params }),
  create: (d)       => api.post('/api/v1/vehicles/', d),
  update: (id, d)   => api.put(`/api/v1/vehicles/${id}`, d),
  delete: (id)      => api.delete(`/api/v1/vehicles/${id}`),
}

export const einvoiceAPI = {
  generate: (d) => api.post('/api/v1/einvoice/generate', d),
  cancel: (d) => api.post('/api/v1/einvoice/cancel', d),
  logs: (params) => api.get('/api/v1/einvoice/logs', { params }),
}

export const ewayAPI = {
  generate: (d) => api.post('/api/v1/ewaybill/generate', d),
  logs: (params) => api.get('/api/v1/ewaybill/logs', { params }),
}

export const gstr1API = {
  get: (params) => api.get('/api/v1/gstr1/', { params }),
  exportExcel: (params) => api.get('/api/v1/gstr1/export/excel', { params, responseType: 'blob' }),
  exportJson: (params) => api.get('/api/v1/gstr1/export/json', { params, responseType: 'blob' }),
}

export const gstr2bAPI = {
  reconcile: (d) => api.post('/api/v1/gstr2b/reconcile', d),
}

export const gstr3bAPI = {
  get: (params) => api.get('/api/v1/gstr3b/', { params }),
}
