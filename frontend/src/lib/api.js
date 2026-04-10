import axios from 'axios';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const suppliersAPI = {
  getAll: () => api.get('/suppliers'),
  create: (data) => api.post('/suppliers', data),
  update: (id, data) => api.put(`/suppliers/${id}`, data),
  delete: (id) => api.delete(`/suppliers/${id}`),
  testLogin: (id) => api.post(`/suppliers/${id}/test`),
  getSelectors: (id) => api.get(`/suppliers/${id}/selectors`),
  updateSelectors: (id, selectors) => api.put(`/suppliers/${id}/selectors`, selectors),
};

export const jobsAPI = {
  upload: (formData) => api.post('/jobs/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  getAll: () => api.get('/jobs'),
  getOne: (id) => api.get(`/jobs/${id}`),
  run: (id) => api.post(`/jobs/${id}/run`),
  compare: (id) => api.post(`/jobs/${id}/compare`, {}, { timeout: 660000 }),
  forceCompare: (id) => api.post(`/jobs/${id}/compare?force=true`, {}, { timeout: 660000 }),
  getProgress: (id) => api.get(`/jobs/${id}/progress`),
  getResults: (id) => api.get(`/jobs/${id}/results`),
  export: (id) => api.get(`/jobs/${id}/export`, { responseType: 'blob' }),
  delete: (id) => api.delete(`/jobs/${id}`),
};

export const statsAPI = {
  getDashboard: () => api.get('/stats'),
};

export const logsAPI = {
  getAll: (jobId = null, limit = 100) => api.get('/logs', { params: { job_id: jobId, limit } }),
};

export const scrapedPricesAPI = {
  getAll: (medida = null, marca = null, modelo = null, load_index = null) => {
    const params = {};
    if (medida) params.medida = medida;
    if (marca) params.marca = marca;
    if (modelo) params.modelo = modelo;
    if (load_index) params.load_index = load_index;
    return api.get('/scraped-prices', { params });
  },
  getBest: (medida) => api.get(`/scraped-prices/best/${medida}`),
};

export const scrapeAPI = {
  enqueue: (supplier_id, sizes) => api.post('/scrape/enqueue', { supplier_id, sizes }),
  enqueueBatch: (sizes, supplier_ids = null) => api.post('/scrape/enqueue-batch', { sizes, supplier_ids }),
  getJobs: (status = null, limit = 20) => api.get('/scrape/jobs', { params: { status, limit } }),
  getJob: (jobId) => api.get(`/scrape/jobs/${jobId}`),
};

export const workerAPI = {
  getStatus: () => api.get('/worker/status'),
  start: () => api.post('/worker/start'),
};

export default api;
