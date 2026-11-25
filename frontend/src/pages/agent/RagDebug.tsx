import { FileSearchOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Input, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { retrieve } from '../../api/knowledge';
import { errorMessage } from '../../utils/error';
import type { RetrievalItem } from '../../types/knowledge';

export function RagDebugPage() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<RetrievalItem[]>([]);
  const [searched, setSearched] = useState(false);

  async function run() {
    const value = query.trim();
    if (!value) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const result = await retrieve(value, 5);
      setItems(result.items);
    } catch (requestError) {
      setItems([]);
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <Card className="soft-card" title="RAG 检索诊断">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary">
            只读检索诊断：调用真实知识检索 API，展示 Query、Top-K、Chunk 分数和来源。
            不提供上传、发布或删除知识库文档的权限。
          </Typography.Paragraph>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              prefix={<FileSearchOutlined />}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入一个知识库问题，例如：换货需要什么条件？"
              onPressEnter={() => void run()}
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={loading}
              onClick={() => void run()}
            >
              检索
            </Button>
          </Space.Compact>
          {error ? <Alert type="error" showIcon message={error} /> : null}
          {searched && !loading && !error && !items.length ? (
            <Alert
              type="info"
              showIcon
              message="没有检索到知识片段"
              description="当前 Query 没有命中已发布且对当前调试账号可见的知识 Chunk。"
            />
          ) : null}
          {items.length ? (
            <Table<RetrievalItem>
              rowKey="chunk_id"
              dataSource={items}
              pagination={false}
              columns={[
                {
                  title: '分数',
                  dataIndex: 'score',
                  width: 100,
                  render: (value: number) => <Tag color="blue">{value.toFixed(4)}</Tag>,
                },
                {
                  title: '文档',
                  dataIndex: 'document_title',
                  width: 220,
                },
                {
                  title: '章节',
                  dataIndex: 'section_title',
                  width: 180,
                  render: (value: string | null) => value ?? '-',
                },
                {
                  title: '页',
                  dataIndex: 'page_number',
                  width: 70,
                  render: (value: number | null) => value ?? '-',
                },
                {
                  title: 'Chunk 内容',
                  dataIndex: 'content',
                  render: (value: string) => (
                    <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }}>
                      {value}
                    </Typography.Paragraph>
                  ),
                },
              ]}
              expandable={{
                expandedRowRender: (record) => (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {JSON.stringify(record, null, 2)}
                  </pre>
                ),
              }}
            />
          ) : null}
        </Space>
      </Card>
    </div>
  );
}
