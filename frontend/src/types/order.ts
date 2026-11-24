export type OrderStatus =
  | 'CREATED'
  | 'PENDING_PAYMENT'
  | 'PAID'
  | 'CANCELLED'
  | 'CLOSED'
  | 'COMPLETED';

export type FulfillmentStatus = 'UNSHIPPED' | 'SHIPPED' | 'DELIVERED' | 'COMPLETED';

export interface OrderItem {
  sku_code: string;
  product_no: string;
  product_name: string;
  sku_attributes: Record<string, string>;
  currency: string;
  unit_price: string;
  quantity: number;
  line_amount: string;
}

export interface Order {
  order_no: string;
  status: OrderStatus;
  fulfillment_status: FulfillmentStatus;
  total_amount: string;
  currency: string;
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
  customer_remark: string | null;
  shipping_carrier: string | null;
  tracking_no: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  items: OrderItem[];
}

export interface OrderListResponse {
  items: Order[];
  total: number;
  page: number;
  page_size: number;
}
