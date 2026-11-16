export type DocumentVisibility = 'PUBLIC' | 'ADMIN_ONLY';
export type DocumentStatus = 'ACTIVE' | 'ARCHIVED' | 'DELETED';
export type VersionStatus =
  | 'UPLOADED'
  | 'PROCESSING'
  | 'INDEXED'
  | 'PUBLISHED'
  | 'SUPERSEDED'
  | 'FAILED';

export interface KnowledgeDocument {
  id: number;
  title: string;
  description: string | null;
  visibility: DocumentVisibility;
  status: DocumentStatus;
  current_published_version_id: number | null;
  created_by: number;
  updated_by: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeVersion {
  id: number;
  document_id: number;
  version_no: number;
  original_filename: string;
  mime_type: string;
  file_size: number;
  file_sha256: string;
  status: VersionStatus;
  parser_version: string | null;
  chunking_version: string | null;
  embedding_model: string | null;
  embedding_dimension: number | null;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  published_at: string | null;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  versions: KnowledgeVersion[];
}

export interface KnowledgeList {
  items: KnowledgeDocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface RetrievalItem {
  chunk_id: number;
  document_id: number;
  version_id: number;
  document_title: string;
  content: string;
  score: number;
  page_number: number | null;
  section_title: string | null;
  original_filename: string;
}

export interface RetrievalResponse {
  items: RetrievalItem[];
  total: number;
}
