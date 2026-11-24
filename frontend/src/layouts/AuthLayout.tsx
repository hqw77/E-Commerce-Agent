import { Layout } from 'antd';
import type { ReactNode } from 'react';

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-shell">
      <div className="auth-card">{children}</div>
    </div>
  );
}

export function PageContainer({ children }: { children: ReactNode }) {
  return <Layout.Content className="page-content">{children}</Layout.Content>;
}
