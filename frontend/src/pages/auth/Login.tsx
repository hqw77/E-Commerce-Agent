import { LockOutlined, MailOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthLayout } from '../../layouts/AuthLayout';
import { useAuthStore, login } from '../../stores/authStore';

interface LoginValues {
  email: string;
  password: string;
}

function destination(user: { is_admin: boolean; is_debugger: boolean }): string {
  if (user.is_admin) return '/dashboard';
  if (user.is_debugger) return '/agent/debug';
  return '/shop';
}

export function LoginPage() {
  const navigate = useNavigate();
  const { status, error, user } = useAuthStore();
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<LoginValues>();

  useEffect(() => {
    if (status === 'authenticated' && user) {
      navigate(destination(user), { replace: true });
    }
  }, [navigate, status, user]);

  async function handleSubmit(values: LoginValues) {
    setSubmitting(true);
    try {
      const authenticatedUser = await login(values);
      navigate(destination(authenticatedUser), { replace: true });
    } catch {
      // The auth store exposes the normalized error above the form.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <Typography.Title level={3}>登录清风数码</Typography.Title>
      <Typography.Paragraph type="secondary">
        消费者进入商城，管理员进入运营后台，调试人员进入 Agent 观察台。
      </Typography.Paragraph>
      {error ? <Alert type="error" showIcon message={error} className="form-alert" /> : null}
      <Form form={form} layout="vertical" onFinish={handleSubmit} requiredMark={false}>
        <Form.Item
          name="email"
          label="邮箱"
          rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}
        >
          <Input prefix={<MailOutlined />} autoComplete="email" placeholder="name@qingfeng.com" />
        </Form.Item>
        <Form.Item
          name="password"
          label="密码"
          rules={[{ required: true, message: '请输入密码' }]}
        >
          <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={submitting || status === 'loading'}>
          登录
        </Button>
      </Form>
      <Typography.Paragraph className="auth-switch">
        <Typography.Text type="secondary">内部账号由管理员开通</Typography.Text>
      </Typography.Paragraph>
      <Typography.Paragraph type="secondary" style={{ textAlign: 'center', fontSize: 12, marginBottom: 0 }}>
        同一浏览器的不同标签页可分别登录消费者、管理员和调试人员；关闭标签页后需重新登录。
      </Typography.Paragraph>
    </AuthLayout>
  );
}
