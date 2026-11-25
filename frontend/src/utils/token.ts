const ACCESS_KEY = 'ecommerce_agent_access_token';
const REFRESH_KEY = 'ecommerce_agent_refresh_token';

// sessionStorage is scoped to one browser tab. This lets the demo keep a
// consumer, an administrator and a debugger logged in simultaneously without
// changing the backend authentication contract.
export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY);
}

export function saveTokens(accessToken: string, refreshToken: string): void {
  sessionStorage.setItem(ACCESS_KEY, accessToken);
  sessionStorage.setItem(REFRESH_KEY, refreshToken);
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}
