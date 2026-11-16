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
