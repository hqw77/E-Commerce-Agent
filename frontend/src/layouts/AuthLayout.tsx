import { Layout, Typography } from 'antd';
import type { ReactNode } from 'react';

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-shell">
      <div className="auth-brand">
        <div className="brand-mark">EA</div>
        <Typography.Title level={1}>E-Commerce Agent</Typography.Title>
        <Typography.Paragraph>
          电商业务、RAG 知识库与 LangGraph Agent 的统一管理入口
        </Typography.Paragraph>
      </div>
      <div className="auth-card">{children}</div>
    </div>
  );
}

export function PageContainer({ children }: { children: ReactNode }) {
  return <Layout.Content className="page-content">{children}</Layout.Content>;
}
