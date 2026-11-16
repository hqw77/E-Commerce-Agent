export interface Inventory {
  sku_id: number;
  total_quantity: number;
  reserved_quantity: number;
  available_quantity: number;
}

export interface InventoryTransaction {
  id: number;
  sku_id: number;
  transaction_type: string;
  total_delta: number;
  reserved_delta: number;
  total_after: number;
  reserved_after: number;
  business_type: string;
  business_id: number | null;
  business_item_id: number | null;
  operator_id: number | null;
  remark: string | null;
  created_at: string;
}

export interface InventoryTransactionList {
  items: InventoryTransaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface InventoryOperationResponse {
  transaction: InventoryTransaction;
  inventory: Inventory;
}
