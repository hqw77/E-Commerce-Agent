import {
  AppstoreOutlined,
  BarcodeOutlined,
  DashboardOutlined,
  FileTextOutlined,
  LogoutOutlined,
  MessageOutlined,
  ProfileOutlined,
  SafetyCertificateOutlined,
  ShoppingCartOutlined,
  TagsOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Breadcrumb, Layout, Menu, Space, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { logout, useAuthStore } from '../stores/authStore';

const items = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: <Link to="/dashboard">首页概览</Link> },
  { key: '/products', icon: <AppstoreOutlined />, label: <Link to="/products">商品管理</Link> },
  { key: '/inventory', icon: <TagsOutlined />, label: <Link to="/inventory">库存管理</Link> },
  { key: '/orders', icon: <ShoppingCartOutlined />, label: <Link to="/orders">订单管理</Link> },
  { key: '/after-sales', icon: <ProfileOutlined />, label: <Link to="/after-sales">售后管理</Link> },
  { key: '/knowledge', icon: <FileTextOutlined />, label: <Link to="/knowledge">知识库</Link> },
  { key: '/agent/approvals', icon: <SafetyCertificateOutlined />, label: <Link to="/agent/approvals">Agent 审批中心</Link> },
  { key: '/agent', icon: <MessageOutlined />, label: <Link to="/agent">AI 助手</Link> },
];

function selectedKey(pathname: string): string {
  if (pathname.startsWith('/inventory')) return '/inventory';
  if (pathname.startsWith('/products')) return '/products';
  if (pathname.startsWith('/orders')) return '/orders';
  if (pathname.startsWith('/after-sales')) return '/after-sales';
  if (pathname.startsWith('/knowledge')) return '/knowledge';
  if (pathname.startsWith('/agent/approvals')) return '/agent/approvals';
  if (pathname.startsWith('/agent')) return '/agent';
  return '/dashboard';
}

export function AdminLayout({ children }: { children?: ReactNode }) {
  const { user } = useAuthStore();
  const location = useLocation();
  const selected = selectedKey(location.pathname);
  const breadcrumb = useMemo(() => {
    const item = items.find((entry) => entry.key === selected);
    return [
      { title: <Link to="/dashboard">清风数码</Link> },
      { title: item ? item.label : '工作台' },
    ];
  }, [selected]);

  return (
    <Layout className="admin-shell">
      <Layout.Sider width={232} className="admin-sider" breakpoint="lg" collapsedWidth={0}>
        <div className="sider-brand">
          <BarcodeOutlined />
          <div className="sider-brand-text">
            <span>清风数码</span>
            <small>运营后台</small>
          </div>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={items} />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="admin-header">
          <Breadcrumb items={breadcrumb} />
          <Space>
            <Avatar icon={<UserOutlined />} />
            <Typography.Text>{user?.email ?? '未登录'}</Typography.Text>
            <a className="logout-link" onClick={() => void logout()}>
              <LogoutOutlined /> 退出
            </a>
          </Space>
        </Layout.Header>
        <Layout.Content className="page-content">
          {children ?? <Outlet />}
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
