import type { ProductDetail } from './product';

export interface CatalogProduct {
  id: number;
  product_no: string;
  name: string;
  description: string | null;
  image_url: string | null;
  category_id: number;
  category_name: string;
  price_from: string | null;
  price_to: string | null;
  sku_count: number;
  available_stock: number;
  total_stock: number;
}

export interface CatalogProductList {
  items: CatalogProduct[];
  total: number;
  page: number;
  page_size: number;
}

export interface CatalogProductDetail extends ProductDetail {
  category_name: string;
}
