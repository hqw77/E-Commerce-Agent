export type ProductStatus = 'DRAFT' | 'ACTIVE' | 'INACTIVE' | 'ARCHIVED';

export interface Sku {
  id: number;
  product_id: number;
  sku_code: string;
  attributes: Record<string, string>;
  price: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface InventorySummary {
  sku_id: number;
  total_quantity: number;
  reserved_quantity: number;
  available_quantity: number;
}

export interface SkuDetail extends Sku {
  inventory: InventorySummary | null;
}

export interface Product {
  id: number;
  product_no: string;
  category_id: number;
  name: string;
  description: string | null;
  image_url: string | null;
  status: ProductStatus;
  published_at: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductDetail extends Product {
  skus: SkuDetail[];
}

export interface ProductListResponse {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProductCreateRequest {
  product_no: string;
  category_id: number;
  name: string;
  description?: string | null;
  image_url?: string | null;
  skus?: Array<{
    sku_code: string;
    attributes: Record<string, string>;
    price: number;
  }>;
}

export interface ProductUpdateRequest {
  product_no?: string;
  name?: string;
  description?: string | null;
  category_id?: number;
  image_url?: string | null;
}

export interface SkuCreateRequest {
  sku_code: string;
  attributes: Record<string, string>;
  price: number;
  status?: 'ACTIVE' | 'INACTIVE';
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  sort_order: number;
  status: 'ENABLED' | 'DISABLED';
  created_at: string;
  updated_at: string;
}
