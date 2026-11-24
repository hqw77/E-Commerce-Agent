import { LockOutlined, MailOutlined } from '@ant-design/icons';
import { Alert, App, Button, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../../layouts/AuthLayout';
import { login, register } from '../../stores/authStore';

interface RegisterValues {
  email: string;
  password: string;
  confirmPassword: string;
}

export function RegisterPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(values: RegisterValues) {
    setSubmitting(true);
    setError(null);
    try {
      await register({ email: values.email, password: values.password });
      const user = await login({ email: values.email, password: values.password });
      message.success('注册成功');
      navigate(user.is_admin ? '/dashboard' : '/shop', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <Typography.Title level={3}>创建账号</Typography.Title>
      <Typography.Paragraph type="secondary">
        注册接口返回用户信息；注册成功后自动登录。
      </Typography.Paragraph>
      {error ? <Alert type="error" showIcon message={error} className="form-alert" /> : null}
      <Form layout="vertical" onFinish={handleSubmit} requiredMark={false}>
        <Form.Item
          name="email"
          label="邮箱"
          rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}
        >
          <Input prefix={<MailOutlined />} autoComplete="email" />
        </Form.Item>
        <Form.Item
          name="password"
          label="密码"
          rules={[{ required: true, min: 8, message: '密码至少 8 位' }]}
        >
          <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirmPassword"
          label="确认密码"
          dependencies={['password']}
          rules={[
            { required: true, message: '请再次输入密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                return !value || getFieldValue('password') === value
                  ? Promise.resolve()
                  : Promise.reject(new Error('两次输入的密码不一致'));
              },
            }),
          ]}
        >
          <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={submitting}>
          注册
        </Button>
      </Form>
      <Typography.Paragraph className="auth-switch">
        已有账号？<Link to="/login">登录</Link>
      </Typography.Paragraph>
    </AuthLayout>
  );
}
