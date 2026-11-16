import { useSyncExternalStore } from 'react';
import * as authApi from '../api/auth';
import type { LoginRequest, RegisterRequest, User } from '../types/auth';
import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from '../utils/token';

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'anonymous';

export interface AuthSnapshot {
  status: AuthStatus;
  user: User | null;
  error: string | null;
}

let snapshot: AuthSnapshot = {
  status: 'idle',
  user: null,
  error: null,
};

const listeners = new Set<() => void>();

function emit(next: AuthSnapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): AuthSnapshot {
  return snapshot;
}

export function useAuthStore<T = AuthSnapshot>(
  selector?: (state: AuthSnapshot) => T,
): T {
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return selector ? selector(state) : (state as T);
}

export async function bootstrapAuth(): Promise<void> {
  if (!getAccessToken()) {
    emit({ status: 'anonymous', user: null, error: null });
    return;
  }
  emit({ ...snapshot, status: 'loading', error: null });
  try {
    const user = await authApi.me();
    emit({ status: 'authenticated', user, error: null });
  } catch {
    clearTokens();
    emit({ status: 'anonymous', user: null, error: null });
  }
}

export async function login(payload: LoginRequest): Promise<void> {
  emit({ ...snapshot, status: 'loading', error: null });
  try {
    const tokens = await authApi.login(payload);
    saveTokens(tokens.access_token, tokens.refresh_token);
    const user = await authApi.me();
    emit({ status: 'authenticated', user, error: null });
  } catch (error) {
    clearTokens();
    emit({
      status: 'anonymous',
      user: null,
      error: error instanceof Error ? error.message : '登录失败',
    });
    throw error;
  }
}

export async function register(payload: RegisterRequest): Promise<User> {
  return authApi.register(payload);
}

export async function logout(): Promise<void> {
  const refreshToken = getRefreshToken();
  try {
    if (refreshToken) await authApi.logout(refreshToken);
  } catch {
    // Local logout must still succeed when the server token is already invalid.
  } finally {
    clearTokens();
    emit({ status: 'anonymous', user: null, error: null });
  }
}

window.addEventListener('auth:expired', () => {
  emit({ status: 'anonymous', user: null, error: null });
});
