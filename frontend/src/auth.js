// Centralized client-side auth helpers.
// NOTE: This only validates token *presence* and *expiry* (JWT `exp`).
// Real authorization is always enforced by the backend via the
// Authorization header. This guard exists purely to prevent
// unauthenticated users from seeing authenticated UI.

export function getToken() {
  try {
    return localStorage.getItem('brandora_token');
  } catch {
    return null;
  }
}

export function isTokenValid(token) {
  if (!token || typeof token !== 'string') return false;
  const parts = token.split('.');
  if (parts.length !== 3) return false;
  try {
    const payload = JSON.parse(atob(parts[1]));
    if (payload.exp && Date.now() / 1000 > payload.exp) return false;
    return true;
  } catch {
    return false;
  }
}

export function isAuthenticated() {
  return isTokenValid(getToken());
}

export function clearAuth() {
  localStorage.removeItem('brandora_token');
  localStorage.removeItem('brandora_user');
}
