import {
  FileTextOutlined,
  MessageOutlined,
  ShoppingCartOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Col, Row, Space, Statistic, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listProducts } from '../../api/products';
import { listOrders } from '../../api/orders';
import { listDocuments } from '../../api/knowledge';
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
    queryFn: () => listOrders({ page: 1, page_size: 1 }),
  });
  const knowledge = useQuery({
    queryKey: ['dashboard', 'knowledge'],
    queryFn: () => listDocuments({ page: 1, page_size: 1 }),
  });
  const errors = [products.error, orders.error, knowledge.error].filter(Boolean);

  return (
    <div className="page-stack">
      <div className="hero-panel">
        <div>
          <Typography.Text className="eyebrow">E-COMMERCE AGENT CONSOLE</Typography.Text>
          <Typography.Title level={2}>你好，{user?.email ?? '管理员'}</Typography.Title>
          <Typography.Paragraph type="secondary">
            在一个工作台里管理真实业务数据、知识库与 AI Agent 的受控执行流程。
          </Typography.Paragraph>
          <Space wrap>
            <Link to="/agent">
              <Button type="primary" icon={<MessageOutlined />}>
                打开 AI Agent
              </Button>
            </Link>
            <Link to="/products">
              <Button>管理商品</Button>
            </Link>
          </Space>
        </div>
        <div className="hero-orbit">
          <span>LangGraph</span>
          <span>RAG</span>
          <span>Service</span>
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
              title="订单总数"
              value={orders.data?.total ?? 0}
              prefix={<ShoppingCartOutlined />}
            />
            <Link to="/orders">进入订单管理</Link>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card">
            <Statistic
              title="知识库文档"
              value={knowledge.data?.total ?? 0}
              prefix={<FileTextOutlined />}
            />
            <Link to="/knowledge">进入知识库</Link>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card">
            <Statistic
              title="Agent 能力"
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
            <Typography.Title level={5}>可信知识</Typography.Title>
            <Typography.Paragraph type="secondary">
              RAG 文档在后台入库；Agent 回答的来源由后端检索结果生成。
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
