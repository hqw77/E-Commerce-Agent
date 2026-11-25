import { SafetyCertificateOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Card,
  Descriptions,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import { getMyAgentApproval, listMyAgentApprovals } from '../../api/agentApprovals';
import { PageHeader } from '../../components/Common';
import type { AgentApproval, AgentApprovalStatus } from '../../types/agent';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';

const statusLabel: Record<AgentApprovalStatus, string> = {
  pending: '待审批',
  approved: '已批准',
  executed: '已执行',
  rejected: '已拒绝',
  failed: '执行失败',
  expired: '已过期',
};

function statusColor(status: AgentApprovalStatus): string {
  if (status === 'executed') return 'green';
  if (status === 'approved') return 'blue';
  if (status === 'rejected' || status === 'failed') return 'red';
  if (status === 'expired') return 'default';
  return 'orange';
}

export function ShopApprovalsPage() {
  const [detailId, setDetailId] = useState<string | null>(null);
  const listQuery = useQuery({
    queryKey: ['my-agent-approvals'],
    queryFn: () => listMyAgentApprovals({ page: 1, page_size: 50 }),
  });
  const detailQuery = useQuery({
    queryKey: ['my-agent-approval', detailId],
    queryFn: () => getMyAgentApproval(detailId!),
    enabled: Boolean(detailId),
  });
  const detail = detailQuery.data ?? null;

  return (
    <div className="shop-page">
      <PageHeader
        title="我的审批申请"
        subtitle="由我发起的 Agent 高风险操作申请及审批结果"
        extra={<Tag icon={<SafetyCertificateOutlined />} color="blue">HITL</Tag>}
      />
      <Card className="shop-detail-card">
        {listQuery.error ? (
          <Alert type="error" showIcon message={errorMessage(listQuery.error)} />
        ) : null}
        <Table<AgentApproval>
          rowKey="approval_id"
          loading={listQuery.isLoading}
          dataSource={listQuery.data?.items ?? []}
          locale={{ emptyText: '暂无审批申请' }}
          pagination={false}
          columns={[
            {
              title: '申请时间',
              dataIndex: 'created_at',
              width: 180,
              render: (value: string) => formatDate(value),
            },
            { title: '操作类型', dataIndex: 'operation', width: 160 },
            { title: '操作对象', dataIndex: 'resource_no', width: 160 },
            {
              title: '申请原因',
              dataIndex: 'arguments',
              render: (value: Record<string, unknown>) => String(value.reason ?? '-'),
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 110,
              render: (value: AgentApprovalStatus) => (
                <Tag color={statusColor(value)}>{statusLabel[value] ?? value}</Tag>
              ),
            },
            {
              title: '操作',
              width: 90,
              render: (_, record) => (
                <Typography.Link onClick={() => setDetailId(record.approval_id)}>
                  详情
                </Typography.Link>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="审批申请详情"
        open={Boolean(detailId)}
        onCancel={() => setDetailId(null)}
        footer={null}
        width={720}
      >
        {detail ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="审批编号" span={2}>
                {detail.approval_id}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(detail.status)}>
                  {statusLabel[detail.status] ?? detail.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="操作对象">{detail.resource_no}</Descriptions.Item>
              <Descriptions.Item label="申请时间">{formatDate(detail.created_at)}</Descriptions.Item>
              <Descriptions.Item label="过期时间">{formatDate(detail.expires_at)}</Descriptions.Item>
              <Descriptions.Item label="操作前">
                <pre style={{ margin: 0 }}>{JSON.stringify(detail.before_data, null, 2)}</pre>
              </Descriptions.Item>
              <Descriptions.Item label="计划后">
                <pre style={{ margin: 0 }}>{JSON.stringify(detail.planned_data, null, 2)}</pre>
              </Descriptions.Item>
              <Descriptions.Item label="审批意见" span={2}>
                {detail.review_note ?? '-'}
              </Descriptions.Item>
            </Descriptions>
            {detail.status === 'pending' ? (
              <Alert
                type="info"
                showIcon
                message="等待管理员审批"
                description="审批通过前不会修改业务数据。"
              />
            ) : null}
            {detail.status === 'rejected' ? (
              <Alert
                type="warning"
                showIcon
                message="申请已被拒绝"
                description={detail.review_note ?? '管理员未填写拒绝原因。'}
              />
            ) : null}
            {detail.status === 'failed' ? (
              <Alert
                type="error"
                showIcon
                message="审批执行失败"
                description={detail.error_code ?? '请重新发起申请或联系管理员。'}
              />
            ) : null}
          </Space>
        ) : (
          <Card loading />
        )}
      </Modal>
    </div>
  );
}
