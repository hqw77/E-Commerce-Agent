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

export function LoginPage() {
  const navigate = useNavigate();
  const { status, error, user } = useAuthStore();
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<LoginValues>();

  useEffect(() => {
    if (status === 'authenticated') {
      navigate(user?.is_admin ? '/dashboard' : '/shop', { replace: true });
    }
  }, [navigate, status, user]);

  async function handleSubmit(values: LoginValues) {
    setSubmitting(true);
    try {
      const authenticatedUser = await login(values);
      navigate(authenticatedUser.is_admin ? '/dashboard' : '/shop', { replace: true });
    } catch {
      // The auth store exposes the normalized error above the form.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <Typography.Title level={3}>登录运营后台</Typography.Title>
      <Typography.Paragraph type="secondary">
        使用员工账号登录，管理商品、库存、订单与售后。
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
        演示双端：普通窗口登录管理员，无痕窗口登录普通用户。
      </Typography.Paragraph>
    </AuthLayout>
  );
}
