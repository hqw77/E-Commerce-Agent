import { api } from './client';
import type { Order, OrderListResponse, Payment } from '../types/order';

export async function listOrders(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<OrderListResponse> {
  const response = await api.get<OrderListResponse>('/admin/orders', { params });
  return response.data;
}

export async function getOrder(orderNo: string): Promise<Order> {
  const response = await api.get<Order>(`/admin/orders/${orderNo}`);
  return response.data;
}

export async function listPayments(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<{ items: Payment[]; total: number; page: number; page_size: number }> {
  const response = await api.get('/admin/payments', { params });
  return response.data;
}
