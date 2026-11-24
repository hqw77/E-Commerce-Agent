// Legacy types are accepted for reading historical records; new applications
// are EXCHANGE only.
export type AfterSaleType = 'REFUND_ONLY' | 'RETURN_REFUND' | 'EXCHANGE';

export interface AfterSale {
  after_sales_no: string;
  order_no: string;
  sku_code: string;
  type: AfterSaleType;
  status: string;
  quantity: number;
  requested_amount: string;
  approved_amount: string | null;
  reason: string;
  description: string | null;
  evidence_urls: string[] | null;
  review_note: string | null;
  reviewed_at: string | null;
  return_carrier: string | null;
  return_tracking_no: string | null;
  returned_at: string | null;
  received_at: string | null;
  replacement_carrier: string | null;
  replacement_tracking_no: string | null;
  replacement_shipped_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
}

export interface AfterSaleList {
  items: AfterSale[];
  total: number;
  page: number;
  page_size: number;
}
