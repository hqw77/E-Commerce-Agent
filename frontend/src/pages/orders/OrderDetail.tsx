import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  completeOrder,
  deliverOrder,
  getOrder,
  shipOrder,
} from '../../api/orders';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { OrderItem } from '../../types/order';

interface ShipFormValues {
  shipping_carrier: string;
  tracking_no: string;
}

export function OrderDetailPage() {
  const { orderNo } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [shipOpen, setShipOpen] = useState(false);
  const [shipForm] = Form.useForm<ShipFormValues>();
  const query = useQuery({
    queryKey: ['order', orderNo],
    queryFn: () => getOrder(orderNo!),
    enabled: Boolean(orderNo),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['order', orderNo] });
    await queryClient.invalidateQueries({ queryKey: ['orders'] });
  };
  const shipMutation = useMutation({
    mutationFn: (values: ShipFormValues) => shipOrder(orderNo!, values),
    onSuccess: async () => {
      message.success('订单已发货');
      setShipOpen(false);
      shipForm.resetFields();
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const deliverMutation = useMutation({
    mutationFn: () => deliverOrder(orderNo!),
    onSuccess: async () => {
      message.success('订单已标记送达');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const completeMutation = useMutation({
    mutationFn: () => completeOrder(orderNo!),
    onSuccess: async () => {
      message.success('订单已完成');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  if (!orderNo) return <Alert type="error" showIcon message="无效的订单编号" />;
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;
  const order = query.data;
  const canShip =
    (order.status === 'CREATED' || order.status === 'PAID') &&
    order.fulfillment_status === 'UNSHIPPED';
  const canDeliver = order.fulfillment_status === 'SHIPPED';
  const canComplete =
    order.fulfillment_status === 'DELIVERED' && order.status !== 'CANCELLED';

  return (
    <div className="page-stack">
      <PageHeader
        title={`订单 ${order.order_no}`}
        subtitle="订单金额与履约状态均来自后端"
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/orders')}>返回列表</Button>
            {canShip ? (
              <Button type="primary" onClick={() => setShipOpen(true)}>
                发货
              </Button>
            ) : null}
            {canDeliver ? (
              <Popconfirm
                title="确认该订单已送达？"
                onConfirm={() => deliverMutation.mutate()}
              >
                <Button type="primary" loading={deliverMutation.isPending}>
                  标记送达
                </Button>
              </Popconfirm>
            ) : null}
            {canComplete ? (
              <Popconfirm
                title="确认完成该订单？"
                onConfirm={() => completeMutation.mutate()}
              >
                <Button loading={completeMutation.isPending}>完成订单</Button>
              </Popconfirm>
            ) : null}
          </Space>
        }
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
            本版本不接支付。订单创建后为 CREATED，可取消、发货、送达和完成。
          </Typography.Text>
          <Typography.Text type="secondary">
            售后仅支持换货；订单送达后，普通用户可在商城订单详情申请换货。
          </Typography.Text>
        </Space>
      </Card>

      <Modal
        title="订单发货"
        open={shipOpen}
        onCancel={() => setShipOpen(false)}
        onOk={() => shipForm.submit()}
        confirmLoading={shipMutation.isPending}
        okText="确认发货"
        destroyOnHidden
      >
        <Form
          form={shipForm}
          layout="vertical"
          initialValues={{ shipping_carrier: '顺丰速运' }}
          onFinish={(values) => shipMutation.mutate(values)}
        >
          <Form.Item
            name="shipping_carrier"
            label="承运商"
            rules={[{ required: true, message: '请输入承运商' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="tracking_no"
            label="运单号"
            rules={[{ required: true, message: '请输入运单号' }]}
          >
            <Input placeholder={`SF${order.order_no.slice(-3)}`} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
