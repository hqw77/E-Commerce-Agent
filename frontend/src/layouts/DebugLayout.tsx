import {
  BugOutlined,
  LogoutOutlined,
  MessageOutlined,
  ShopOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Breadcrumb, Button, Layout, Menu, Space, Tag, Typography } from 'antd';
import type { ReactNode } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { logout, useAuthStore } from '../stores/authStore';

const items = [
  {
    key: '/agent/debug',
    icon: <BugOutlined />,
    label: <Link to="/agent/debug">执行轨迹</Link>,
  },
  {
    key: '/agent/debug/chat',
    icon: <MessageOutlined />,
    label: <Link to="/agent/debug/chat">调试对话</Link>,
  },
];

function selectedKey(pathname: string): string {
  if (pathname.startsWith('/agent/debug/chat')) return '/agent/debug/chat';
  return '/agent/debug';
}

export function DebugLayout({ children }: { children?: ReactNode }) {
  const { user } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();
  const selected = selectedKey(location.pathname);

  return (
    <Layout className="admin-shell">
      <Layout.Sider width={232} className="admin-sider" breakpoint="lg" collapsedWidth={0}>
        <div className="sider-brand">
          <BugOutlined />
          <div className="sider-brand-text">
            <span>Agent 调试台</span>
            <small>清风数码 · 观察端</small>
          </div>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={items} />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="admin-header">
          <Breadcrumb
            items={[
              { title: <Link to="/agent/debug">Agent 调试台</Link> },
              { title: selected === '/agent/debug/chat' ? '调试对话' : '执行轨迹' },
            ]}
          />
          <Space>
            <Tag color="geekblue">DEBUG</Tag>
            <Avatar icon={<UserOutlined />} />
            <Typography.Text>{user?.email ?? '未登录'}</Typography.Text>
            <Button type="link" icon={<ShopOutlined />} onClick={() => navigate('/shop')}>
              返回商城
            </Button>
            <Button type="link" icon={<LogoutOutlined />} onClick={() => void logout()}>
              退出
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content className="page-content">
          {children ?? <Outlet />}
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
