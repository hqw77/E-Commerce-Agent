import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Space,
  Table,
  Typography,
} from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { getOrder } from '../../api/orders';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { OrderItem } from '../../types/order';

export function OrderDetailPage() {
  const { orderNo } = useParams();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['order', orderNo],
    queryFn: () => getOrder(orderNo!),
    enabled: Boolean(orderNo),
  });

  if (!orderNo) return <Alert type="error" showIcon message="无效的订单编号" />;
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;
  const order = query.data;

  return (
    <div className="page-stack">
      <PageHeader
        title={`订单 ${order.order_no}`}
        subtitle="订单金额、支付状态与履约状态均来自后端"
        extra={<Button onClick={() => navigate('/orders')}>返回列表</Button>}
      />
      <Card className="soft-card" title="订单信息">
        <Descriptions column={2} bordered size="middle">
          <Descriptions.Item label="订单状态"><StatusTag status={order.status} /></Descriptions.Item>
          <Descriptions.Item label="履约状态"><StatusTag status={order.fulfillment_status} /></Descriptions.Item>
          <Descriptions.Item label="金额">{formatMoney(order.total_amount)}</Descriptions.Item>
          <Descriptions.Item label="币种">{order.currency}</Descriptions.Item>
          <Descriptions.Item label="收货人">{order.receiver_name}</Descriptions.Item>
          <Descriptions.Item label="联系电话">{order.receiver_phone}</Descriptions.Item>
          <Descriptions.Item label="收货地址" span={2}>{order.receiver_address}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(order.created_at)}</Descriptions.Item>
          <Descriptions.Item label="发货时间">{formatDate(order.shipped_at)}</Descriptions.Item>
          <Descriptions.Item label="送达时间">{formatDate(order.delivered_at)}</Descriptions.Item>
          <Descriptions.Item label="完成时间">{formatDate(order.completed_at)}</Descriptions.Item>
          <Descriptions.Item label="取消时间">{formatDate(order.cancelled_at)}</Descriptions.Item>
          <Descriptions.Item label="承运商">{order.shipping_carrier ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="运单号">{order.tracking_no ?? '-'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card className="soft-card" title="订单明细">
        <Table<OrderItem>
          rowKey={(record) => `${record.sku_code}-${record.unit_price}`}
          dataSource={order.items}
          pagination={false}
          columns={[
            { title: '商品', dataIndex: 'product_name' },
            { title: '商品编号', dataIndex: 'product_no' },
            { title: 'SKU', dataIndex: 'sku_code' },
            { title: '规格', dataIndex: 'sku_attributes', render: (value: Record<string, string>) => Object.entries(value).map(([key, item]) => `${key}: ${item}`).join(' / ') },
            { title: '单价', dataIndex: 'unit_price', render: (value: string) => formatMoney(value) },
            { title: '数量', dataIndex: 'quantity' },
            { title: '行金额', dataIndex: 'line_amount', render: (value: string) => formatMoney(value) },
          ]}
        />
      </Card>
      <Card className="soft-card" title="履约与售后">
        <Space direction="vertical">
          <Typography.Text>
            本版本已移除支付和资金退款能力。订单创建后为 CREATED，可取消、发货、送达和完成。
          </Typography.Text>
          <Typography.Text type="secondary">
            售后仅支持换货；售后申请和审核由后端管理端流程完成。
          </Typography.Text>
        </Space>
      </Card>
    </div>
  );
}
