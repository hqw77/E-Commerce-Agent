import axios, { AxiosError, type AxiosRequestConfig } from 'axios';
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  saveTokens,
} from '../utils/token';

export interface ApiErrorBody {
  detail?: unknown;
  message?: string;
  code?: string;
  details?: unknown;
}

export class ApiError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor(message: string, status?: number, code?: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const rawClient = axios.create({
  baseURL,
  timeout: 30000,
});

export const api = axios.create({
  baseURL,
  timeout: 30000,
});

interface RetryConfig extends AxiosRequestConfig {
  _retry?: boolean;
}

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new ApiError('登录状态已失效，请重新登录', 401, 'AUTH_REQUIRED');
  }
  const response = await rawClient.post('/auth/refresh', {
    refresh_token: refreshToken,
  });
  saveTokens(response.data.access_token, response.data.refresh_token);
  return response.data.access_token as string;
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as RetryConfig | undefined;
    const status = error.response?.status;
    const isAuthRequest = config?.url?.includes('/auth/login') ||
      config?.url?.includes('/auth/refresh');

    if (status === 401 && config && !config._retry && !isAuthRequest) {
      config._retry = true;
      try {
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
        const token = await refreshPromise;
        config.headers = {
          ...(config.headers ?? {}),
          Authorization: `Bearer ${token}`,
        };
        return api.request(config);
      } catch {
        clearTokens();
        window.dispatchEvent(new Event('auth:expired'));
        if (window.location.pathname !== '/login') {
          window.location.assign('/login');
        }
      }
    }

    const data = error.response?.data;
    const message =
      data?.message ??
      (typeof data?.detail === 'string' ? data.detail : undefined) ??
      (error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '网络请求失败');
    return Promise.reject(
      new ApiError(message, status, data?.code, data?.details),
    );
  },
);
