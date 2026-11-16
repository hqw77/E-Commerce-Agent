import { api } from './client';
import type {
  Category,
  CategoryCreateRequest,
  CategoryUpdateRequest,
  ProductCreateRequest,
  ProductDetail,
  ProductListResponse,
  ProductUpdateRequest,
  Sku,
  SkuCreateRequest,
} from '../types/product';

export async function listProducts(params: {
  status?: string;
  category_id?: number;
  keyword?: string;
  page?: number;
  page_size?: number;
}): Promise<ProductListResponse> {
  const response = await api.get<ProductListResponse>('/admin/products', { params });
  return response.data;
}

export async function getProduct(productId: number): Promise<ProductDetail> {
  const response = await api.get<ProductDetail>(`/admin/products/${productId}`);
  return response.data;
}

export async function createProduct(payload: ProductCreateRequest): Promise<ProductDetail> {
  const response = await api.post<ProductDetail>('/admin/products', payload);
  return response.data;
}

export async function updateProduct(
  productId: number,
  payload: ProductUpdateRequest,
): Promise<ProductDetail> {
  const response = await api.patch<ProductDetail>(`/admin/products/${productId}`, payload);
  return response.data;
}

export async function changeProductStatus(
  productId: number,
  action: 'activate' | 'deactivate' | 'archive',
): Promise<ProductDetail> {
  const response = await api.post<ProductDetail>(
    `/admin/products/${productId}/${action}`,
  );
  return response.data;
}

export async function createSku(
  productId: number,
  payload: SkuCreateRequest,
): Promise<Sku> {
  const response = await api.post<Sku>(`/admin/products/${productId}/skus`, payload);
  return response.data;
}

export async function updateSku(
  skuId: number,
  payload: { price?: number; status?: 'ACTIVE' | 'INACTIVE' },
): Promise<Sku> {
  const response = await api.patch<Sku>(`/admin/skus/${skuId}`, payload);
  return response.data;
}

export async function listCategories(): Promise<Category[]> {
  const response = await api.get<Category[]>('/admin/categories');
  return response.data;
}

export async function createCategory(payload: CategoryCreateRequest): Promise<Category> {
  const response = await api.post<Category>('/admin/categories', payload);
  return response.data;
}

export async function updateCategory(
  categoryId: number,
  payload: CategoryUpdateRequest,
): Promise<Category> {
  const response = await api.patch<Category>(`/admin/categories/${categoryId}`, payload);
  return response.data;
}
