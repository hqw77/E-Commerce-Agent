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
  trace_id: string | null;
}

export interface TraceEvent {
  trace_id: string;
  request_id: string;
  conversation_id: string;
  user_id: number;
  node_name: string | null;
  event_type: string;
  intent: string | null;
  route: string | null;
  tool_name: string | null;
  arguments_summary: Record<string, unknown> | null;
  risk_level: string | null;
  execution_status: string;
  duration_ms: number | null;
  result_summary: Record<string, unknown> | null;
  error_code: string | null;
  timestamp: string;
}

export interface TraceRun {
  trace_id: string;
  events: TraceEvent[];
}

export interface ConfirmActionResponse {
  success: boolean;
  action_type: string;
  resource_no: string;
  status: string;
  message: string;
  after_sales_no: string | null;
}
