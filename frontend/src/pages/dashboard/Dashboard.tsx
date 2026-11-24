import {
  MessageOutlined,
  ProfileOutlined,
  ShoppingCartOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Col, Row, Space, Statistic, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listProducts } from '../../api/products';
import { listOrders } from '../../api/orders';
import { listAfterSales } from '../../api/afterSales';
import { errorMessage } from '../../utils/error';
import { useAuthStore } from '../../stores/authStore';

export function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const products = useQuery({
    queryKey: ['dashboard', 'products'],
    queryFn: () => listProducts({ page: 1, page_size: 1 }),
  });
  const orders = useQuery({
    queryKey: ['dashboard', 'orders'],
    queryFn: () => listOrders({ status: 'CREATED', page: 1, page_size: 1 }),
  });
  const afterSales = useQuery({
    queryKey: ['dashboard', 'after-sales'],
    queryFn: () => listAfterSales({ status: 'PENDING_REVIEW', page: 1, page_size: 1 }),
  });
  const errors = [products.error, orders.error, afterSales.error].filter(Boolean);

  return (
    <div className="page-stack">
      <div className="hero-panel">
        <div>
          <Typography.Text className="eyebrow">清风数码 · 运营后台</Typography.Text>
          <Typography.Title level={2}>你好，{user?.email ?? '管理员'}</Typography.Title>
          <Typography.Paragraph type="secondary">
            在一个工作台里管理商品、库存、订单、售后与受控 AI Agent。
          </Typography.Paragraph>
          <Space wrap>
            <Link to="/agent">
              <Button type="primary" icon={<MessageOutlined />}>
                打开 AI 助手
              </Button>
            </Link>
            <Link to="/products">
              <Button>管理商品</Button>
            </Link>
          </Space>
        </div>
        <div className="hero-orbit">
          <span>Commerce</span>
          <span>Service</span>
          <span>Agent</span>
        </div>
      </div>

      {errors.length ? (
        <Alert
          type="warning"
          showIcon
          message={errorMessage(errors[0])}
          description="概览依赖管理员接口；如果当前账号不是管理员，请使用管理员账号登录。"
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card">
            <Statistic
              title="商品总数"
              value={products.data?.total ?? 0}
              prefix={<TagsOutlined />}
            />
            <Link to="/products">进入商品管理</Link>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card">
            <Statistic
              title="待发货订单"
              value={orders.data?.total ?? 0}
              prefix={<ShoppingCartOutlined />}
            />
            <Link to="/orders">进入订单管理</Link>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card">
            <Statistic
              title="待审核售后"
              value={afterSales.data?.total ?? 0}
              prefix={<ProfileOutlined />}
            />
            <Link to="/after-sales">进入售后管理</Link>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card">
            <Statistic
              title="AI 助手"
              value="受控执行"
              prefix={<MessageOutlined />}
            />
            <Link to="/agent">开始对话</Link>
          </Card>
        </Col>
      </Row>

      <Card title="业务闭环" className="soft-card">
        <Row gutter={[24, 16]}>
          <Col xs={24} md={8}>
            <Typography.Title level={5}>真实数据</Typography.Title>
            <Typography.Paragraph type="secondary">
              商品、SKU、库存、订单与售后来自 FastAPI Service 和 MySQL，不在前端重算业务规则。
            </Typography.Paragraph>
          </Col>
          <Col xs={24} md={8}>
            <Typography.Title level={5}>状态机</Typography.Title>
            <Typography.Paragraph type="secondary">
              订单履约与 EXCHANGE 售后由后端状态机推进，前端只展示真实状态。
            </Typography.Paragraph>
          </Col>
          <Col xs={24} md={8}>
            <Typography.Title level={5}>受控操作</Typography.Title>
            <Typography.Paragraph type="secondary">
              取消订单和售后申请必须经过 Prepare / Confirm，Confirm 由后端一次性消费。
            </Typography.Paragraph>
          </Col>
        </Row>
      </Card>
    </div>
  );
}
