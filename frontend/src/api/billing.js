import api from './index'

export const customerAPI = {
  list: (params) => api.get('/api/v1/customers/', { params }),
  get: (id) => api.get(`/api/v1/customers/${id}`),
  create: (d) => api.post('/api/v1/customers/', d),
  update: (id, d) => api.put(`/api/v1/customers/${id}`, d),
  addAddress: (id, d) => api.post(`/api/v1/customers/${id}/addresses`, d),
  updateAddress: (id, addressId, d) => api.put(`/api/v1/customers/${id}/addresses/${addressId}`, d),
  bulkStatus: (d) => api.post('/api/v1/customers/bulk-status', d),
  ledger: (id, params) => api.get(`/api/v1/customers/${id}/ledger`, { params }),
  statement: (id, params) => api.get(`/api/v1/customers/${id}/statement`, { params }),
  lastPrice: (customerId, productId) => api.get(`/api/v1/customers/${customerId}/last-price/${productId}`),
  gstinLookup: (gstin) => api.get(`/api/v1/customers/gstin-lookup/${gstin}`),
  importTemplate: () => api.get('/api/v1/customers/import/template', { responseType: 'blob' }),
  bulkImport: (file) => { const fd = new FormData(); fd.append('file', file); return api.post('/api/v1/customers/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } }) },
}

export const invoiceAPI = {
  list: (params) => api.get('/api/v1/invoices/', { params }),
  get: (id) => api.get(`/api/v1/invoices/${id}`),
  create: (d) => api.post('/api/v1/invoices/', d),
  cancel: (id, reason) => api.post(`/api/v1/invoices/${id}/cancel`, { reason }),
  creditNote: (d) => api.post('/api/v1/invoices/credit-note', d),
  whatsapp: (id) => api.get(`/api/v1/invoices/${id}/whatsapp`),
  convertToInvoice: (id) => api.post(`/api/v1/invoices/${id}/convert-to-invoice`),
  markQuotationInvoiced: (quotId, invId) => api.post(`/api/v1/invoices/${quotId}/mark-invoiced`, { invoice_id: invId }),
  listDCs: (params) => api.get('/api/v1/invoices/list/delivery-challans', { params }),
  cancelDC: (id) => api.post(`/api/v1/invoices/${id}/cancel-dc`),
  updateEwayBill: (id, eway_bill_number) => api.patch(`/api/v1/invoices/${id}/eway-bill`, { eway_bill_number }),
  setEwayManual: (id, data) => api.patch(`/api/v1/invoices/${id}/eway-bill`, data),
  setEinvoiceManual: (id, data) => api.patch(`/api/v1/invoices/${id}/einvoice`, data),
  updateEwayVehicle: (id, data) => api.patch(`/api/v1/invoices/${id}/eway-bill/vehicle`, data),
  cancelEwayBill: (id, data) => api.post(`/api/v1/invoices/${id}/eway-bill/cancel`, data),
}

export const receiptAPI = {
  list: (params) => api.get('/api/v1/receipts/', { params }),
  create: (d) => api.post('/api/v1/receipts/', d),
}