import { LockOutlined, MailOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../../layouts/AuthLayout';
import { useAuthStore, login } from '../../stores/authStore';

interface LoginValues {
  email: string;
  password: string;
}

export function LoginPage() {
  const navigate = useNavigate();
  const { status, error } = useAuthStore();
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<LoginValues>();

  useEffect(() => {
    if (status === 'authenticated') navigate('/dashboard', { replace: true });
  }, [navigate, status]);

  async function handleSubmit(values: LoginValues) {
    setSubmitting(true);
    try {
      await login(values);
      navigate('/dashboard', { replace: true });
    } catch {
      // The auth store exposes the normalized error above the form.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <Typography.Title level={3}>登录管理后台</Typography.Title>
      <Typography.Paragraph type="secondary">
        使用后端账号登录，身份与权限由 FastAPI 最终校验。
      </Typography.Paragraph>
      {error ? <Alert type="error" showIcon message={error} className="form-alert" /> : null}
      <Form form={form} layout="vertical" onFinish={handleSubmit} requiredMark={false}>
        <Form.Item
          name="email"
          label="邮箱"
          rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}
        >
          <Input prefix={<MailOutlined />} autoComplete="email" placeholder="admin@example.com" />
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
        还没有账号？<Link to="/register">注册</Link>
      </Typography.Paragraph>
    </AuthLayout>
  );
}
