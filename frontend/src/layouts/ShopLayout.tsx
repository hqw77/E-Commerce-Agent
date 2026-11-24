import { Button, Layout, Space, Typography } from 'antd';
import { Link, Outlet } from 'react-router-dom';
import { logout, useAuthStore } from '../stores/authStore';

export function ShopLayout() {
  const { user, status } = useAuthStore();

  return (
    <Layout className="shop-shell">
      <Layout.Header className="shop-header">
        <Link className="shop-brand" to="/shop">
          <span className="shop-brand-mark">QF</span>
          <span>
            <strong>清风数码</strong>
            <small>品质数码商城</small>
          </span>
        </Link>
        <Space wrap className="shop-nav">
          <Link to="/shop">商城</Link>
          <Link to="/shop/assistant">AI 导购</Link>
          {status === 'authenticated' ? (
            <>
              <Link to="/shop/orders">我的订单</Link>
              <Link to="/shop/after-sales">我的售后</Link>
            </>
          ) : null}
          {status === 'authenticated' && user?.is_admin ? (
            <Link to="/dashboard">运营后台</Link>
          ) : null}
        </Space>
        <Space wrap>
          {status === 'authenticated' && user ? (
            <>
              <Typography.Text type="secondary">{user.email}</Typography.Text>
              <Button type="link" onClick={() => void logout()}>
                退出
              </Button>
            </>
          ) : (
            <>
              <Link to="/login">登录</Link>
              <Link to="/register">注册</Link>
            </>
          )}
        </Space>
      </Layout.Header>
      <Layout.Content className="shop-content">
        <Outlet />
      </Layout.Content>
    </Layout>
  );
}
