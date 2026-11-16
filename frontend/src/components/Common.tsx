import { Button, Result, Spin, Tag, Typography } from 'antd';
import type { ReactNode } from 'react';
import { statusColor } from '../utils/format';

export function AppLoading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="centered-state">
      <Spin />
      <Typography.Text type="secondary">{text}</Typography.Text>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Result
      status="warning"
      title="页面加载失败"
      subTitle={message}
      extra={onRetry ? <Button onClick={onRetry}>重试</Button> : undefined}
    />
  );
}

export function EmptyState({ description = '暂无数据' }: { description?: string }) {
  return <Result status="info" title={description} />;
}

export function StatusTag({ status }: { status: string }) {
  return <Tag color={statusColor(status)}>{status}</Tag>;
}

export function PageHeader({
  title,
  subtitle,
  extra,
}: {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <Typography.Title level={3}>{title}</Typography.Title>
        {subtitle ? <Typography.Text type="secondary">{subtitle}</Typography.Text> : null}
      </div>
      {extra ? <div className="page-header-extra">{extra}</div> : null}
    </div>
  );
}
