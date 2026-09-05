import axios from 'axios';
import { clearAuth } from '../auth';
import { translations, DEFAULT_LANGUAGE } from '../i18n/translations';
import { isTokenSpendingRequest, refreshTokenBalance } from './tokens';

// Turn ANY API error into a safe, renderable string for toasts / inline states.
// FastAPI 422 validation errors return `detail` as an ARRAY of objects
// (e.g. [{type, loc, msg, input, ctx}]); passing that array straight into a
// toast crashes React ("Objects are not valid as a React child"). This always
// extracts a plain string.
export function extractApiError(err, fallback = 'Something went wrong. Please try again.') {
  try {
    if (!err) return fallback;
    if (typeof err === 'string') return err;
    const detail = err?.response?.data?.detail;
    if (detail != null && detail !== '') {
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        const first = detail[0];
        if (first && typeof first === 'object' && typeof first.msg === 'string' && first.msg) {
          return first.msg;
        }
        return fallback;
      }
      if (typeof detail === 'object') {
        if (typeof detail.message === 'string' && detail.message) return detail.message;
        if (typeof detail.detail === 'string' && detail.detail) return detail.detail;
      }
    }
    if (typeof err.message === 'string' && err.message) return err.message;
    return fallback;
  } catch {
    return fallback;
  }
}

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
    // If this was a token-spending action, refresh the Navbar counter
    // immediately (fire-and-forget; never block the request on it).
    if (isTokenSpendingRequest(response.config.method, response.config.url)) {
      refreshTokenBalance();
    }
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

