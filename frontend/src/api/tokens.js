import api from './axios';

// Core actions that spend a token (1 per successful call). We auto-refresh the
// token balance after any of these succeed so the Navbar counter stays in sync
// without a page reload.
const TOKEN_SPENDING_URLS = [
  '/content/generate',
  '/content/generate-image',
  '/content/publish',
  '/schedule',
  '/calendar/post',
  '/calendar/bulk',
];

export function isTokenSpendingRequest(method, url) {
  const u = url || '';
  return method === 'post' && TOKEN_SPENDING_URLS.some((p) => u.includes(p));
}

// Persist a fresh token count to localStorage and notify the app to re-render.
export function publishTokenBalance(tokens, isUnlimited) {
  try {
    const raw = localStorage.getItem('brandora_user');
    const u = raw ? JSON.parse(raw) : {};
    u.free_tokens = tokens;
    if (typeof isUnlimited === 'boolean') u.is_unlimited = isUnlimited;
    localStorage.setItem('brandora_user', JSON.stringify(u));
  } catch {
    /* ignore storage errors */
  }
  window.dispatchEvent(new CustomEvent('brandora:tokens-updated', { detail: { tokens, isUnlimited } }));
}

// Read the current token state straight from the synced profile.
export function currentTokenState() {
  try {
    const raw = localStorage.getItem('brandora_user');
    const u = raw ? JSON.parse(raw) : {};
    return {
      isUnlimited: !!u.is_unlimited,
      tokens: Number.isFinite(u.free_tokens) ? u.free_tokens : 0,
    };
  } catch {
    return { isUnlimited: false, tokens: 0 };
  }
}

// Return true if the caller may perform a token-consuming action. If not (and
// not unlimited), instantly opens the Pricing Paywall Modal and returns false
// so the button handler bails out BEFORE firing the API request.
export function ensureToken() {
  const { isUnlimited, tokens } = currentTokenState();
  if (isUnlimited || tokens > 0) return true;
  window.dispatchEvent(new CustomEvent('brandora:upgrade-required'));
  return false;
}

// Fetch the latest token balance from /auth/me and publish it.
export async function refreshTokenBalance() {
  try {
    const { data } = await api.get('/auth/me');
    if (data && typeof data.free_tokens === 'number') {
      publishTokenBalance(data.free_tokens, !!data.is_unlimited);
      return data.free_tokens;
    }
  } catch {
    /* ignore */
  }
  return null;
}
