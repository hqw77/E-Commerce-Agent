import { api } from './client';
import type { ChatResponse, ConfirmActionResponse } from '../types/agent';

export async function chat(payload: {
  message: string;
  conversation_id?: string | null;
}): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>('/agent/chat', payload, {
    timeout: 60000,
  });
  return response.data;
}

export async function confirmAction(
  confirmationId: string,
  payload: { conversation_id: string; nonce: string },
): Promise<ConfirmActionResponse> {
  const response = await api.post<ConfirmActionResponse>(
    `/agent/actions/${confirmationId}/confirm`,
    payload,
    { timeout: 60000 },
  );
  return response.data;
}
