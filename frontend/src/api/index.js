import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use(config => {
  const token = sessionStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// FastAPI 422 validation errors put an ARRAY of {loc, msg, type} objects in
// detail; pages toast `detail` directly expecting a string, so flatten it
// here once instead of in every onError handler.
function normalizeDetail(err) {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string' || detail == null) return
  if (Array.isArray(detail)) {
    err.response.data.detail = detail
      .map(d => {
        if (typeof d === 'string') return d
        const loc = Array.isArray(d.loc) ? d.loc.filter(p => p !== 'body' && typeof p !== 'number').join('.') : ''
        const msg = (d.msg || JSON.stringify(d)).replace(/^Value error,\s*/, '')
        return loc ? `${loc}: ${msg}` : msg
      })
      .join('; ')
  } else {
    err.response.data.detail = JSON.stringify(detail)
  }
}

api.interceptors.response.use(
  res => res,
  async err => {
    normalizeDetail(err)
    const original = err.config
    const url = original?.url || ''
    // Auth endpoints handle their own errors — don't auto-refresh or redirect,
    // otherwise a failed login triggers a full-page reload that wipes the error message.
    const isAuthCall = url.includes('/auth/login') || url.includes('/auth/refresh')
    if (err.response?.status === 401 && !original._retry && !isAuthCall) {
      original._retry = true
      try {
        const refresh = sessionStorage.getItem('refresh_token')
        if (!refresh) throw new Error('No refresh token')
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_URL || ''}/api/v1/auth/refresh`,
          { refresh_token: refresh }
        )
        sessionStorage.setItem('access_token', data.access_token)
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        sessionStorage.clear()
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api

export const authAPI = {
  login:          (d) => api.post('/api/v1/auth/login', d),
  logout:         ()  => api.post('/api/v1/auth/logout', { refresh_token: sessionStorage.getItem('refresh_token') }),
  me:             ()  => api.get('/api/v1/auth/me'),
  changePassword: (d) => api.post('/api/v1/auth/change-password', d),
  updateProfile:  (d) => api.put('/api/v1/auth/profile', d),
}

export const categoryAPI = {
  list:   (params) => api.get('/api/v1/categories/', { params }),
  create: (d)      => api.post('/api/v1/categories/', d),
  update: (id, d)  => api.put(`/api/v1/categories/${id}`, d),
  delete: (id)     => api.delete(`/api/v1/categories/${id}`),
}

export const productAPI = {
  list:             (params)     => api.get('/api/v1/products/', { params }),
  get:              (id)         => api.get(`/api/v1/products/${id}`),
  create:           (d)          => api.post('/api/v1/products/', d),
  update:           (id, d)      => api.put(`/api/v1/products/${id}`, d),
  bulkUpload:       (file)       => { const fd = new FormData(); fd.append('file', file); return api.post('/api/v1/products/bulk-upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } }) },
  bulkPriceUpdate:  (d)          => api.post('/api/v1/products/bulk-price-update', d),
  uploadImage:      (id, file)   => { const fd = new FormData(); fd.append('file', file); return api.post(`/api/v1/products/${id}/image`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }) },
  deleteImage:      (id)         => api.delete(`/api/v1/products/${id}/image`),
  downloadTemplate: ()           => api.get('/api/v1/products/template/csv', { responseType: 'blob' }),
  exportCsv:        (params)     => api.get('/api/v1/products/export/csv', { params, responseType: 'blob' }),
  searchBilling:    (q, wid)     => api.get('/api/v1/products/search/billing', { params: { q, warehouse_id: wid } }),
  stock:            (id)         => api.get(`/api/v1/products/${id}/stock`),
  fifoLayers:       (id, wid)    => api.get(`/api/v1/products/${id}/fifo-layers`, { params: { warehouse_id: wid } }),
  adjustStock:      (d)          => api.post('/api/v1/products/stock/adjust', d),
  ageingReport:     (wid)        => api.get('/api/v1/products/stock/ageing', { params: { warehouse_id: wid } }),
  costTrend:        (id, params) => api.get(`/api/v1/products/${id}/cost-trend`, { params }),
  pendingAlerts:    ()           => api.get('/api/v1/products/alerts/pending'),
  resolveAlert:     (id, d)      => api.post(`/api/v1/products/alerts/${id}/resolve`, d),
}
