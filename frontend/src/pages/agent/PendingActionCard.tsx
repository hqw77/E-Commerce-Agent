import { CheckCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Space, Typography } from 'antd';
import type { PendingAction } from '../../types/agent';
import { formatDate } from '../../utils/format';

export function PendingActionCard({
  action,
  confirming,
  onConfirm,
  onDismiss,
}: {
  action: PendingAction;
  confirming: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  return (
    <Card className="pending-card" size="small">
      <Space direction="vertical" size={6}>
        <Typography.Text strong>{action.title}</Typography.Text>
        <Typography.Text>业务编号：{action.resource_no}</Typography.Text>
        <Typography.Text type="secondary">{action.summary}</Typography.Text>
        <Typography.Text type="secondary">影响：{action.effect}</Typography.Text>
        <Typography.Text type="secondary">有效期至：{formatDate(action.expires_at)}</Typography.Text>
        {action.approval_required ? (
          <Alert
            type="info"
            showIcon
            icon={<SafetyCertificateOutlined />}
            message="已提交管理员审批"
            description="审批通过前不会修改业务数据。你可以在「我的审批」查看进度，管理员在审批中心处理。"
          />
        ) : (
          <Space>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={confirming}
              onClick={onConfirm}
            >
              确认执行
            </Button>
            <Button onClick={onDismiss}>暂不操作</Button>
          </Space>
        )}
      </Space>
    </Card>
  );
}
