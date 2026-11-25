import { BugOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Input, Space, Table, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getTraceRun } from '../../api/agent';
import { errorMessage } from '../../utils/error';
import type { TraceEvent, TraceRun } from '../../types/agent';

export function TraceConsolePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [traceId, setTraceId] = useState(searchParams.get('trace_id') ?? '');
  const [run, setRun] = useState<TraceRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function query(value: string) {
    const id = value.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setRun(null);
    try {
      const result = await getTraceRun(id);
      setRun(result);
      setSearchParams({ trace_id: id });
    } catch (queryError) {
      setError(errorMessage(queryError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const initial = searchParams.get('trace_id');
    if (initial && !run && !error) {
      void query(initial);
    }
    // Only auto-query the initial URL once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page-stack">
      <Card className="soft-card" title="Agent 调试观察台">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary">
            面向调试人员的只读观察台。可查看一次 Agent 请求的 Intent、Router、RAG、
            Tool、Workflow、HITL 与输出校验事件；敏感字段已由后端脱敏。
          </Typography.Paragraph>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              prefix={<BugOutlined />}
              value={traceId}
              onChange={(event) => setTraceId(event.target.value)}
              placeholder="输入 chat 响应中的 trace_id"
              onPressEnter={() => void query(traceId)}
            />
            <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => void query(traceId)}>
              查询
            </Button>
          </Space.Compact>
          {error ? <Alert type="error" showIcon message={error} /> : null}
          {run ? (
            <Table<TraceEvent>
              rowKey={(record) => `${record.timestamp}-${record.event_type}-${record.node_name ?? ''}`}
              dataSource={run.events}
              pagination={{ pageSize: 20, showSizeChanger: false }}
              columns={[
                {
                  title: '时间',
                  dataIndex: 'timestamp',
                  width: 190,
                  render: (value: string) => value.replace('T', ' ').slice(0, 23),
                },
                {
                  title: '事件',
                  dataIndex: 'event_type',
                  width: 150,
                  render: (value: string) => <Tag color="blue">{value}</Tag>,
                },
                { title: '节点', dataIndex: 'node_name', width: 150, render: (value: string | null) => value ?? '-' },
                { title: '路由', dataIndex: 'route', width: 110, render: (value: string | null) => value ?? '-' },
                { title: 'Tool', dataIndex: 'tool_name', width: 160, render: (value: string | null) => value ?? '-' },
                {
                  title: '状态',
                  dataIndex: 'execution_status',
                  width: 100,
                  render: (value: string) => (
                    <Tag color={value === 'SUCCESS' || value === 'ACCEPTED' ? 'green' : value === 'ERROR' ? 'red' : 'default'}>
                      {value}
                    </Tag>
                  ),
                },
                { title: '耗时(ms)', dataIndex: 'duration_ms', width: 90, render: (value: number | null) => value ?? '-' },
                { title: '错误码', dataIndex: 'error_code', width: 220, render: (value: string | null) => value ?? '-' },
              ]}
              expandable={{
                expandedRowRender: (record) => (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {JSON.stringify(
                      {
                        arguments: record.arguments_summary,
                        result: record.result_summary,
                        risk: record.risk_level,
                        intent: record.intent,
                        conversation_id: record.conversation_id,
                      },
                      null,
                      2,
                    )}
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
