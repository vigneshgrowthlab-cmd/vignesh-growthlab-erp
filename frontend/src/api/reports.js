import api from './index'

export const dashboardAPI = {
  get: (params) => api.get('/api/v1/dashboard/', { params }),
}

export const reportsAPI = {
  sales: (params) => api.get('/api/v1/reports/sales', { params }),
  purchases: (params) => api.get('/api/v1/reports/purchases', { params }),
  stock: (params) => api.get('/api/v1/reports/stock', { params }),
  stockClearance: (params) => api.get('/api/v1/reports/stock-clearance', { params }),
  pnl: (params) => api.get('/api/v1/reports/pnl', { params }),
  dayBook: (params) => api.get('/api/v1/reports/day-book', { params }),
  customerLedger: (params) => api.get('/api/v1/reports/customer-ledger', { params }),
  vendorLedger: (params) => api.get('/api/v1/reports/vendor-ledger', { params }),
}
