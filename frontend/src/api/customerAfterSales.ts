import { api } from './client';
import type { AfterSale, AfterSaleList } from '../types/afterSales';

export interface ApplyAfterSalePayload {
  sku_code: string;
  type: 'EXCHANGE';
  reason: string;
  description?: string | null;
  idempotency_key: string;
}

export async function listMyAfterSales(params: {
  page?: number;
  page_size?: number;
}): Promise<AfterSaleList> {
  const response = await api.get<AfterSaleList>('/after-sales', { params });
  return response.data;
}

export async function getMyAfterSale(afterSalesNo: string): Promise<AfterSale> {
  const response = await api.get<AfterSale>(`/after-sales/${encodeURIComponent(afterSalesNo)}`);
  return response.data;
}

export async function listOrderAfterSales(orderNo: string): Promise<AfterSaleList> {
  const response = await api.get<AfterSaleList>(
    `/orders/${encodeURIComponent(orderNo)}/after-sales`,
  );
  return response.data;
}

export async function applyOrderAfterSale(
  orderNo: string,
  payload: ApplyAfterSalePayload,
): Promise<AfterSale> {
  const response = await api.post<AfterSale>(
    `/orders/${encodeURIComponent(orderNo)}/after-sales`,
    payload,
  );
  return response.data;
}

export async function submitAfterSaleReturn(
  afterSalesNo: string,
  payload: { return_carrier: string; return_tracking_no: string },
): Promise<AfterSale> {
  const response = await api.post<AfterSale>(
    `/after-sales/${encodeURIComponent(afterSalesNo)}/return-shipment`,
    payload,
  );
  return response.data;
}
