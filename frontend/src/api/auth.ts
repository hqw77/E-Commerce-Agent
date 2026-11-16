import { api } from './client';
import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  User,
} from '../types/auth';

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>('/auth/login', payload);
  return response.data;
}

export async function register(payload: RegisterRequest): Promise<User> {
  const response = await api.post<User>('/auth/register', payload);
  return response.data;
}

export async function me(): Promise<User> {
  const response = await api.get<User>('/auth/me');
  return response.data;
}

export async function logout(refreshToken: string): Promise<void> {
  await api.post('/auth/logout', { refresh_token: refreshToken });
}
