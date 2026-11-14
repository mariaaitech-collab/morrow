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
    const numericTokens = Number(u.free_tokens);
    return {
      isUnlimited: !!u.is_unlimited,
      hasTokenBalance: u.free_tokens !== undefined && u.free_tokens !== null && u.free_tokens !== '',
      tokens: Number.isFinite(numericTokens) ? numericTokens : 0,
    };
  } catch {
    return { isUnlimited: false, hasTokenBalance: false, tokens: 0 };
  }
}

// Return true if the caller may perform a token-consuming action. The backend
// is the source of truth for credits; if a user is truly out, the API returns
// 402 and the global axios handler opens the Pricing Modal.
export function ensureToken() {
  const { isUnlimited, hasTokenBalance, tokens } = currentTokenState();
  // Right after login/register the stored user can briefly exist without a
  // balance until /auth/me syncs. Let the API decide instead of showing a
  // false paywall for users who still have credits.
  if (!hasTokenBalance) return true;
  if (isUnlimited || tokens > 0) return true;
  refreshTokenBalance();
  return true;
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
