import axios, { AxiosError } from 'axios';
import { clearTokens, getAccessToken } from '../utils/token';

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

export const api = axios.create({
  baseURL,
  timeout: 30000,
});

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
    const status = error.response?.status;

    if (status === 401) {
      clearTokens();
      window.dispatchEvent(new Event('auth:expired'));
      if (window.location.pathname !== '/login') {
        window.location.assign('/login');
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
