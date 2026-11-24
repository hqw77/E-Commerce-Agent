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

export async function shipOrder(
  orderNo: string,
  payload: { shipping_carrier: string; tracking_no: string },
): Promise<Order> {
  const response = await api.post<Order>(`/admin/orders/${orderNo}/ship`, payload);
  return response.data;
}

export async function deliverOrder(orderNo: string): Promise<Order> {
  const response = await api.post<Order>(`/admin/orders/${orderNo}/deliver`);
  return response.data;
}

export async function completeOrder(orderNo: string): Promise<Order> {
  const response = await api.post<Order>(`/admin/orders/${orderNo}/complete`);
  return response.data;
}
