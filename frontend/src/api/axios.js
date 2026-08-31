import axios from 'axios';
import { clearAuth } from '../auth';
import { translations, DEFAULT_LANGUAGE } from '../i18n/translations';

function tr(key) {
  try {
    const lang = (typeof localStorage !== 'undefined' && localStorage.getItem('brandora_lang')) || DEFAULT_LANGUAGE;
    const lookup = (obj, k) => k.split('.').reduce((o, p) => (o && o[p] != null ? o[p] : undefined), obj);
    return lookup(translations[lang], key) || lookup(translations[DEFAULT_LANGUAGE], key) || key;
  } catch {
    return key;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
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
    if (error.response?.status === 401) {
      // Session is invalid/expired: clear local credentials and send the
      // user back to login instead of leaving a silently broken UI.
      clearAuth();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(new Error(tr('auth.sessionExpired')));
    }
    if (error.response?.status === 402) {
      window.dispatchEvent(new CustomEvent('brandora:upgrade-required'));
      return Promise.reject(new Error(tr('auth.upgradeRequired')));
    }
    if (error.response?.status === 503 || error.code === 'ECONNABORTED') {
      return Promise.reject(new Error(tr('auth.backendDown')));
    }
    return Promise.reject(error);
  }
);

export default api;

