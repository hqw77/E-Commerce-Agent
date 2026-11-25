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
  approval_required?: boolean;
  approval_id?: string | null;
  approval_status?: string | null;
}

export type AgentApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'executed'
  | 'failed'
  | 'expired';

export interface AgentApproval {
  approval_id: string;
  operation: string;
  resource_no: string;
  status: AgentApprovalStatus;
  arguments: Record<string, unknown>;
  before_data: Record<string, unknown>;
  planned_data: Record<string, unknown>;
  action_hash: string;
  requester_id: number;
  approver_id: number | null;
  conversation_id: string;
  thread_id: string;
  review_note: string | null;
  error_code: string | null;
  expires_at: string;
  reviewed_at: string | null;
  executed_at: string | null;
  created_at: string;
}

export interface AgentApprovalList {
  items: AgentApproval[];
  total: number;
  page: number;
  page_size: number;
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
