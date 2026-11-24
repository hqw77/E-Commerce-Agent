import { api } from './client';
import type { Order, OrderListResponse } from '../types/order';

export interface CreateOrderPayload {
  items: Array<{ sku_code: string; quantity: number }>;
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
  customer_remark?: string | null;
  idempotency_key: string;
}

export async function createMyOrder(payload: CreateOrderPayload): Promise<Order> {
  const response = await api.post<Order>('/orders', payload);
  return response.data;
}

export async function listMyOrders(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<OrderListResponse> {
  const response = await api.get<OrderListResponse>('/orders', { params });
  return response.data;
}

export async function getMyOrder(orderNo: string): Promise<Order> {
  const response = await api.get<Order>(`/orders/${encodeURIComponent(orderNo)}`);
  return response.data;
}

export async function cancelMyOrder(orderNo: string, reason?: string): Promise<Order> {
  const response = await api.post<Order>(
    `/orders/${encodeURIComponent(orderNo)}/cancel`,
    null,
    { params: { reason } },
  );
  return response.data;
}
