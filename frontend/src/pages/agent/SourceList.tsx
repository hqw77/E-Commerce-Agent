import { Space, Tag, Typography } from 'antd';
import type { Source } from '../../types/agent';

export function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <div className="source-block">
      <Typography.Text type="secondary">RAG 来源（由后端检索生成）</Typography.Text>
      <Space wrap>
        {sources.map((source) => (
          <Tag key={`${source.document_id}-${source.chunk_id}`}>
            {source.title}
            {source.section_title ? ` · ${source.section_title}` : ''}
          </Tag>
        ))}
      </Space>
    </div>
  );
}
