import { api } from './client';
import type {
  CatalogProductDetail,
  CatalogProductList,
} from '../types/catalog';
import type { Category } from '../types/product';

export async function listCatalogProducts(params: {
  category_id?: number;
  keyword?: string;
  page?: number;
  page_size?: number;
}): Promise<CatalogProductList> {
  const response = await api.get<CatalogProductList>('/catalog/products', { params });
  return response.data;
}

export async function getCatalogProduct(productNo: string): Promise<CatalogProductDetail> {
  const response = await api.get<CatalogProductDetail>(
    `/catalog/products/${encodeURIComponent(productNo)}`,
  );
  return response.data;
}

export async function listCatalogCategories(): Promise<Category[]> {
  const response = await api.get<Category[]>('/catalog/categories');
  return response.data;
}
