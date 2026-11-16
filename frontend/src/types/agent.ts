export interface Source {
  document_id: number;
  version_id: number;
  chunk_id: number;
  title: string;
  section_title: string | null;
  page_number: number | null;
}

export interface PendingAction {
  confirmation_id: string;
  nonce: string;
  conversation_id: string;
  action_type: string;
  title: string;
  resource_no: string;
  effect: string;
  summary: string;
  expires_at: string;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  sources: Source[];
  pending_action: PendingAction | null;
  created_at: string;
}

export interface ConfirmActionResponse {
  success: boolean;
  action_type: string;
  resource_no: string;
  status: string;
  message: string;
  after_sales_no: string | null;
}
