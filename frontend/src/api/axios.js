import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('brandora_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  console.log(`[AXIOS] ${config.method.toUpperCase()} ${config.baseURL}${config.url}`);
  return config;
});

api.interceptors.response.use(
  (response) => {
    console.log(`[AXIOS] ${response.config.method.toUpperCase()} ${response.config.url} -> ${response.status}`);
    return response;
  },
  (error) => {
    console.error(`[AXIOS] ERROR:`, error.code, error.response?.status, error.message);
    if (error.response?.status === 503 || error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('Brandora backend (http://localhost:8000) is not running. Start it first, then try again.'));
    }
    return Promise.reject(error);
  }
);

export default api;
