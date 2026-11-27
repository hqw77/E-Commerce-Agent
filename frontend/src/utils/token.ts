const ACCESS_KEY = 'ecommerce_agent_access_token';

// sessionStorage 按标签页隔离, 便于演示多角色同时登录.
export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY);
}

export function saveAccessToken(accessToken: string): void {
  sessionStorage.setItem(ACCESS_KEY, accessToken);
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY);
}
