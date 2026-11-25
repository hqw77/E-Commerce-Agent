import { CheckOutlined, CloseOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import {
  approveAgentApproval,
  getAgentApproval,
  listAgentApprovals,
  rejectAgentApproval,
} from '../../api/agentApprovals';
import { PageHeader } from '../../components/Common';
import type { AgentApproval, AgentApprovalStatus } from '../../types/agent';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';

const statusOptions: Array<{ value: AgentApprovalStatus; label: string }> = [
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已批准' },
  { value: 'executed', label: '已执行' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'failed', label: '执行失败' },
  { value: 'expired', label: '已过期' },
];

function statusColor(status: string): string {
  if (status === 'executed') return 'green';
  if (status === 'approved') return 'blue';
  if (status === 'rejected' || status === 'failed') return 'red';
  if (status === 'expired') return 'default';
  return 'orange';
}

function jsonBlock(value: unknown) {
  return (
    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function AgentApprovalsPage() {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AgentApprovalStatus>('pending');
  const [detailId, setDetailId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectForm] = Form.useForm<{ review_note: string }>();

  const listQuery = useQuery({
    queryKey: ['agent-approvals', status],
    queryFn: () => listAgentApprovals({ status, page: 1, page_size: 50 }),
  });
  const detailQuery = useQuery({
    queryKey: ['agent-approval', detailId],
    queryFn: () => getAgentApproval(detailId!),
    enabled: Boolean(detailId),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['agent-approvals'] });
    if (detailId) {
      await queryClient.invalidateQueries({ queryKey: ['agent-approval', detailId] });
    }
  };
  const approveMutation = useMutation({
    mutationFn: (approvalId: string) => approveAgentApproval(approvalId),
    onSuccess: async () => {
      message.success('审批已通过，库存调整已执行');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const rejectMutation = useMutation({
    mutationFn: (values: { approval_id: string; review_note: string }) =>
      rejectAgentApproval(values.approval_id, values.review_note),
    onSuccess: async () => {
      message.success('审批已拒绝');
      setRejectId(null);
      rejectForm.resetFields();
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const detail = detailQuery.data ?? null;
  const items = listQuery.data?.items ?? [];

  function confirmApprove(item: AgentApproval) {
    modal.confirm({
      title: `批准库存调整 ${item.resource_no}？`,
      content: (
        <div>
          <p>批准后会立即调用库存 Service 执行调整。</p>
          <p>
            库存 {String(item.before_data.total_quantity)} →{' '}
            {String(item.planned_data.total_quantity)}
          </p>
          <Alert
            type="warning"
            showIcon
            message="执行前会重新校验库存；如果数据已变化，审批会失败而不会覆盖。"
          />
        </div>
      ),
      okText: '批准并执行',
      cancelText: '取消',
      onOk: () => approveMutation.mutateAsync(item.approval_id),
    });
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Agent 审批中心"
        subtitle="高风险 Agent 操作先进入待审批，管理员批准后才由 Business Service 执行"
        extra={<Tag icon={<SafetyCertificateOutlined />} color="blue">HITL</Tag>}
      />
      <Card className="soft-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Typography.Text type="secondary">状态</Typography.Text>
            <Select
              value={status}
              options={statusOptions}
              style={{ width: 140 }}
              onChange={(value) => setStatus(value)}
            />
            <Typography.Text type="secondary">
              待审批记录不会直接修改库存。
            </Typography.Text>
          </Space>
          {listQuery.error ? (
            <Alert type="error" showIcon message={errorMessage(listQuery.error)} />
          ) : null}
          <Table<AgentApproval>
            rowKey="approval_id"
            loading={listQuery.isLoading}
            dataSource={items}
            pagination={false}
            columns={[
              {
                title: '创建时间',
                dataIndex: 'created_at',
                width: 180,
                render: (value: string) => formatDate(value),
              },
              { title: '操作', dataIndex: 'operation', width: 160 },
              { title: '对象', dataIndex: 'resource_no', width: 120 },
              {
                title: '变更',
                render: (_, record) => (
                  <Typography.Text>
                    {String(record.before_data.total_quantity)} →{' '}
                    {String(record.planned_data.total_quantity)}
                  </Typography.Text>
                ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 110,
                render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
              },
              {
                title: '操作',
                width: 230,
                render: (_, record) => (
                  <Space>
                    <Button size="small" onClick={() => setDetailId(record.approval_id)}>
                      详情
                    </Button>
                    {record.status === 'pending' ? (
                      <>
                        <Button
                          size="small"
                          type="primary"
                          icon={<CheckOutlined />}
                          loading={approveMutation.isPending}
                          onClick={() => confirmApprove(record)}
                        >
                          批准
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<CloseOutlined />}
                          onClick={() => setRejectId(record.approval_id)}
                        >
                          拒绝
                        </Button>
                      </>
                    ) : null}
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      </Card>

      <Modal
        title={detail ? `审批详情 ${detail.approval_id}` : '审批详情'}
        open={Boolean(detailId)}
        onCancel={() => setDetailId(null)}
        footer={[
          <Button key="close" onClick={() => setDetailId(null)}>关闭</Button>,
        ]}
        width={760}
      >
        {detail ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="状态">
                <Tag color={statusColor(detail.status)}>{detail.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="操作">{detail.operation}</Descriptions.Item>
              <Descriptions.Item label="SKU">{detail.resource_no}</Descriptions.Item>
              <Descriptions.Item label="发起人">{detail.requester_id}</Descriptions.Item>
              <Descriptions.Item label="过期时间">{formatDate(detail.expires_at)}</Descriptions.Item>
              <Descriptions.Item label="审核时间">{formatDate(detail.reviewed_at)}</Descriptions.Item>
              <Descriptions.Item label="审核意见" span={2}>
                {detail.review_note ?? '-'}
              </Descriptions.Item>
            </Descriptions>
            <Card size="small" title="审批参数">
              {jsonBlock(detail.arguments)}
            </Card>
            <Card size="small" title="操作前数据">
              {jsonBlock(detail.before_data)}
            </Card>
            <Card size="small" title="计划后数据">
              {jsonBlock(detail.planned_data)}
            </Card>
          </Space>
        ) : (
          <Card loading />
        )}
      </Modal>

      <Modal
        title="拒绝审批"
        open={Boolean(rejectId)}
        onCancel={() => setRejectId(null)}
        onOk={() => rejectForm.submit()}
        confirmLoading={rejectMutation.isPending}
        okText="确认拒绝"
        okButtonProps={{ danger: true }}
        destroyOnHidden
      >
        <Form
          form={rejectForm}
          layout="vertical"
          onFinish={(values) => {
            if (!rejectId) return;
            rejectMutation.mutate({ approval_id: rejectId, review_note: values.review_note });
          }}
        >
          <Form.Item
            name="review_note"
            label="拒绝原因"
            rules={[{ required: true, message: '请输入拒绝原因' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
