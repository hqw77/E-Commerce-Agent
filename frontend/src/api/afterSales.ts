import { api } from './client';
import type { AfterSale, AfterSaleList } from '../types/afterSales';

export async function listAfterSales(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<AfterSaleList> {
  const response = await api.get<AfterSaleList>('/admin/after-sales', { params });
  return response.data;
}

export async function getAfterSale(afterSalesNo: string): Promise<AfterSale> {
  const response = await api.get<AfterSale>(`/admin/after-sales/${afterSalesNo}`);
  return response.data;
}

export async function approveAfterSale(
  afterSalesNo: string,
  reviewNote?: string | null,
): Promise<AfterSale> {
  const response = await api.post<AfterSale>(
    `/admin/after-sales/${afterSalesNo}/approve`,
    { review_note: reviewNote },
  );
  return response.data;
}

export async function rejectAfterSale(
  afterSalesNo: string,
  reviewNote: string,
): Promise<AfterSale> {
  const response = await api.post<AfterSale>(
    `/admin/after-sales/${afterSalesNo}/reject`,
    { review_note: reviewNote },
  );
  return response.data;
}

export async function receiveAfterSale(afterSalesNo: string): Promise<AfterSale> {
  const response = await api.post<AfterSale>(
    `/admin/after-sales/${afterSalesNo}/receive`,
  );
  return response.data;
}

export async function completeExchange(
  afterSalesNo: string,
  payload: { replacement_carrier: string; replacement_tracking_no: string },
): Promise<AfterSale> {
  const response = await api.post<AfterSale>(
    `/admin/after-sales/${afterSalesNo}/complete-exchange`,
    payload,
  );
  return response.data;
}
