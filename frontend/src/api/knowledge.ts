import { api } from './client';
import type {
  KnowledgeDocumentDetail,
  KnowledgeList,
  KnowledgeVersion,
  RetrievalResponse,
} from '../types/knowledge';

export async function listDocuments(params: {
  keyword?: string;
  status?: string;
  visibility?: string;
  page?: number;
  page_size?: number;
}): Promise<KnowledgeList> {
  const response = await api.get<KnowledgeList>('/knowledge/documents', { params });
  return response.data;
}

export async function getDocument(documentId: number): Promise<KnowledgeDocumentDetail> {
  const response = await api.get<KnowledgeDocumentDetail>(
    `/knowledge/documents/${documentId}`,
  );
  return response.data;
}

export async function uploadDocument(payload: {
  file: File;
  title: string;
  description?: string;
  visibility: 'PUBLIC' | 'ADMIN_ONLY';
}): Promise<KnowledgeDocumentDetail> {
  const form = new FormData();
  form.append('file', payload.file);
  form.append('title', payload.title);
  if (payload.description) form.append('description', payload.description);
  form.append('visibility', payload.visibility);
  const response = await api.post<KnowledgeDocumentDetail>('/knowledge/documents', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
  return response.data;
}

export async function uploadVersion(
  documentId: number,
  file: File,
): Promise<KnowledgeDocumentDetail> {
  const form = new FormData();
  form.append('file', file);
  const response = await api.post<KnowledgeDocumentDetail>(
    `/knowledge/documents/${documentId}/versions`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 },
  );
  return response.data;
}

export async function publishVersion(
  documentId: number,
  versionId: number,
): Promise<KnowledgeVersion> {
  const response = await api.post<KnowledgeVersion>(
    `/knowledge/documents/${documentId}/versions/${versionId}/publish`,
  );
  return response.data;
}

export async function retryVersion(
  documentId: number,
  versionId: number,
): Promise<KnowledgeVersion> {
  const response = await api.post<KnowledgeVersion>(
    `/knowledge/documents/${documentId}/versions/${versionId}/retry`,
  );
  return response.data;
}

export async function deleteDocument(documentId: number): Promise<void> {
  await api.delete(`/knowledge/documents/${documentId}`);
}

export async function retrieve(query: string, topK = 5): Promise<RetrievalResponse> {
  const response = await api.post<RetrievalResponse>('/knowledge/retrieve', {
    query,
    top_k: topK,
  });
  return response.data;
}
