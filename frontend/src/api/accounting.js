import api from './index'

export const chequeAPI = {
  list:       (params) => api.get('/api/v1/cheques/', { params }),
  create:     (d)      => api.post('/api/v1/cheques/', d),
  pdcAlerts:  ()       => api.get('/api/v1/cheques/pdc-alerts'),
  deposit:    (id, d)  => api.post(`/api/v1/cheques/${id}/deposit`, d),
  clear:      (id, d)  => api.post(`/api/v1/cheques/${id}/clear`, d),
  bounce:     (id, d)  => api.post(`/api/v1/cheques/${id}/bounce`, d),
}

export const cashAPI = {
  list:         (params) => api.get('/api/v1/cash-closing/', { params }),
  getClosing:   (date)   => api.get('/api/v1/cash-closing/today', { params: { closing_date: date } }),
  today:        (params) => api.get('/api/v1/cash-closing/today', { params }),
  createClosing:(d)      => api.post('/api/v1/cash-closing/', d),
  approveClosing:(id)    => api.post('/api/v1/cash-closing/approve', {}, { params: id ? { closing_id: id } : {} }),
  approve:      (params, d) => api.post('/api/v1/cash-closing/approve', d, { params }),
}

export const expenseAPI = {
  list:       (params) => api.get('/api/v1/expenses/', { params }),
  categories: ()       => api.get('/api/v1/expenses/categories'),
  create:     (d)      => api.post('/api/v1/expenses/', d),
  approve:    (id, d)  => api.post(`/api/v1/expenses/${id}/approve`, d),
}

export const tdsAPI = {
  list:       (params) => api.get('/api/v1/tds/', { params }),
  create:     (d)      => api.post('/api/v1/tds/', d),
  import26as: (d)      => api.post('/api/v1/tds/import-26as', d),
}

export const ageingAPI = {
  get:            (params) => api.get('/api/v1/customer-ageing/', { params }),
  customerAgeing: (params) => api.get('/api/v1/customer-ageing/', { params }),
}

export const journalAPI = {
  list:         (params) => api.get('/api/v1/journal/', { params }),
  create:       (d)      => api.post('/api/v1/journal/', d),
  accounts:     ()       => api.get('/api/v1/journal/accounts'),
  trialBalance: (params) => api.get('/api/v1/journal/trial-balance', { params }),
}

export const vendorDueAPI = {
  get:  (params) => api.get('/api/v1/vendor-due-alerts/', { params }),
  list: (params) => api.get('/api/v1/vendor-due-alerts/', { params }),
}
