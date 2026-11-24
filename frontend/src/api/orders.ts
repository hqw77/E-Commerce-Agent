import { api } from './client';
import type { Order, OrderListResponse } from '../types/order';

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
