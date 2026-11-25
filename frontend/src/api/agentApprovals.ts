import { api } from './client';
import type {
  AgentApproval,
  AgentApprovalList,
  AgentApprovalStatus,
} from '../types/agent';

export async function listAgentApprovals(params: {
  status?: AgentApprovalStatus;
  page?: number;
  page_size?: number;
}): Promise<AgentApprovalList> {
  const response = await api.get<AgentApprovalList>('/admin/agent/approvals', {
    params,
  });
  return response.data;
}

export async function getAgentApproval(
  approvalId: string,
): Promise<AgentApproval> {
  const response = await api.get<AgentApproval>(
    `/admin/agent/approvals/${encodeURIComponent(approvalId)}`,
  );
  return response.data;
}

export async function approveAgentApproval(
  approvalId: string,
  reviewNote?: string | null,
): Promise<AgentApproval> {
  const response = await api.post<AgentApproval>(
    `/admin/agent/approvals/${encodeURIComponent(approvalId)}/approve`,
    { review_note: reviewNote },
  );
  return response.data;
}

export async function rejectAgentApproval(
  approvalId: string,
  reviewNote: string,
): Promise<AgentApproval> {
  const response = await api.post<AgentApproval>(
    `/admin/agent/approvals/${encodeURIComponent(approvalId)}/reject`,
    { review_note: reviewNote },
  );
  return response.data;
}
