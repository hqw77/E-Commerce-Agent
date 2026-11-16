import { api } from './client';
import type {
  Inventory,
  InventoryOperationResponse,
  InventoryTransactionList,
} from '../types/inventory';

export async function getInventory(skuId: number): Promise<Inventory> {
  const response = await api.get<Inventory>(`/admin/inventory/${skuId}`);
  return response.data;
}

export async function stockIn(
  skuId: number,
  payload: { quantity: number; idempotency_key: string; remark?: string },
): Promise<InventoryOperationResponse> {
  const response = await api.post<InventoryOperationResponse>(
    `/admin/inventory/${skuId}/stock-in`,
    payload,
  );
  return response.data;
}

export async function adjustInventory(
  skuId: number,
  payload: { quantity_delta: number; idempotency_key: string; remark?: string },
): Promise<InventoryOperationResponse> {
  const response = await api.post<InventoryOperationResponse>(
    `/admin/inventory/${skuId}/adjust`,
    payload,
  );
  return response.data;
}

export async function listTransactions(
  skuId: number,
  params: { page?: number; page_size?: number },
): Promise<InventoryTransactionList> {
  const response = await api.get<InventoryTransactionList>(
    `/admin/inventory/${skuId}/transactions`,
    { params },
  );
  return response.data;
}
