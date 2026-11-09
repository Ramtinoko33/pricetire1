import axios from 'axios';
import { getToken, clearSession } from './session';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || '';
    if (status === 401 && !url.includes('/auth/login')) {
      // Sessão inválida/expirada: limpar; o AuthProvider redirecciona para /login.
      clearSession();
    }
    return Promise.reject(error);
  },
);

// Remove parâmetros vazios para não enviar "brand=" etc.
export function cleanParams(params = {}) {
  const out = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    out[k] = v;
  });
  return out;
}

export const authAPI = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  me: () => api.get('/auth/me'),
  changePassword: (current_password, new_password) =>
    api.post('/auth/change-password', { current_password, new_password }),
};

export const usersAPI = {
  getAll: () => api.get('/users'),
  create: (data) => api.post('/users', data),
  update: (id, data) => api.put(`/users/${id}`, data),
};

export const apiKeysAPI = {
  getAll: () => api.get('/api-keys'),
  create: (data) => api.post('/api-keys', data),
  delete: (id) => api.delete(`/api-keys/${id}`),
};

export const searchAPI = {
  brands: () => api.get('/v1/brands'),
  recent: (params) => api.get('/v1/searches/recent', { params: cleanParams(params || {}) }),
  offers: (params) => api.get('/v1/offers', { params: cleanParams({ limit: 5000, ...params }) }),
  search: (body) => api.post('/v1/search', body),
  refresh: (sizes, supplier_ids) =>
    api.post('/v1/refresh', supplier_ids?.length ? { sizes, supplier_ids } : { sizes }),
  refreshStatus: (requestId) => api.get(`/v1/refresh/${encodeURIComponent(requestId)}`),
};

export const suppliersAPI = {
  getAll: () => api.get('/suppliers'),
  create: (data) => api.post('/suppliers', data),
  update: (id, data) => api.put(`/suppliers/${id}`, data),
  delete: (id) => api.delete(`/suppliers/${id}`),
  // DELETE desactiva o fornecedor (não apaga dados).
  testLogin: (id, size = '205/55R16') => api.post(`/suppliers/${id}/test`, {}, { params: { size } }),
  adapters: () => api.get('/suppliers/adapters'),
};

export const opsAPI = {
  status: () => api.get('/ops/status'),
  jobs: (params) => api.get('/ops/jobs', { params: cleanParams(params) }),
  retryJob: (id) => api.post(`/ops/jobs/${id}/retry`),
  cancelJob: (id) => api.post(`/ops/jobs/${id}/cancel`),
  failures: (params) => api.get('/ops/failures', { params: cleanParams(params) }),
  runs: (params) => api.get('/ops/runs', { params: cleanParams(params) }),
  runScheduledNow: () => api.post('/ops/run-scheduled-now'),
};

export const scheduledTargetsAPI = {
  getAll: () => api.get('/scheduled-targets'),
  create: (data) => api.post('/scheduled-targets', data),
  delete: (id) => api.delete(`/scheduled-targets/${encodeURIComponent(id)}`),
};

export const catalogAPI = {
  getAll: (params) => api.get('/catalog', { params: cleanParams(params) }),
  create: (data) => api.post('/catalog', data),
  update: (id, data) => api.put(`/catalog/${id}`, data),
  delete: (id) => api.delete(`/catalog/${id}`),
  import: (file, mode = 'upsert') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('mode', mode);
    return api.post('/catalog/import', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { mode },
      timeout: 120000,
    });
  },
  template: () => api.get('/catalog/template', { responseType: 'blob' }),
  comparison: (onlySavings = false) =>
    api.get('/catalog/comparison', { params: { only_savings: onlySavings } }),
};

export const alertsAPI = {
  getRules: () => api.get('/alerts/rules'),
  createRule: (data) => api.post('/alerts/rules', data),
  updateRule: (id, data) => api.put(`/alerts/rules/${id}`, data),
  deleteRule: (id) => api.delete(`/alerts/rules/${id}`),
  events: (limit = 200) => api.get('/alerts/events', { params: { limit } }),
  testEmail: (email_to) => api.post('/alerts/test-email', { email_to }),
  evaluate: () => api.post('/alerts/evaluate'),
  getBrandCategories: () => api.get('/brand-categories'),
};

export const monitorAPI = {
  categories: () => api.get('/monitor/categories'),
  updateCategory: (id, data) => api.put(`/monitor/categories/${encodeURIComponent(id)}`, data),
  addSizes: (id, sizes) => api.post(`/monitor/categories/${encodeURIComponent(id)}/sizes`, { sizes }),
  deleteSize: (id) => api.delete(`/monitor/sizes/${encodeURIComponent(id)}`),
  runNow: (id) => api.post(`/monitor/categories/${encodeURIComponent(id)}/run-now`),
};

export const brandsAPI = {
  overview: () => api.get('/brands/overview'),
  setTier: (brand, category, note) => api.put(`/brand-categories/${encodeURIComponent(brand)}`, { category: category || null, note: note || undefined }),
};

export const jobsAPI = {
  upload: (formData) => api.post('/jobs/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  getAll: () => api.get('/jobs'),
  getOne: (id) => api.get(`/jobs/${id}`),
  compare: (id) => api.post(`/jobs/${id}/compare`, {}, { timeout: 30000 }),
  forceCompare: (id) => api.post(`/jobs/${id}/compare`, {}, { params: { force: true }, timeout: 30000 }),
  cancel: (id) => api.post(`/jobs/${id}/cancel`, {}, { timeout: 30000 }),
  getProgress: (id) => api.get(`/jobs/${id}/progress`),
  getResults: (id) => api.get(`/jobs/${id}/results`),
  export: (id) => api.get(`/jobs/${id}/export`, { responseType: 'blob' }),
  save: (id) => api.post(`/jobs/${id}/save`),
  delete: (id) => api.delete(`/jobs/${id}`),
};

export function downloadBlob(data, filename, type) {
  const blob = data instanceof Blob ? data : new Blob([data], type ? { type } : undefined);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

export default api;
