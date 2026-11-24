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
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { applyOrderAfterSale, listOrderAfterSales } from '../../api/customerAfterSales';
import { cancelMyOrder, getMyOrder } from '../../api/customerOrders';
import { StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { AfterSale } from '../../types/afterSales';
import type { OrderItem } from '../../types/order';

interface ApplyFormValues {
  sku_code: string;
  reason: string;
  description?: string;
}

export function ShopOrderDetailPage() {
  const { orderNo } = useParams<{ orderNo: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [applyOpen, setApplyOpen] = useState(false);
  const [applyForm] = Form.useForm<ApplyFormValues>();

  const orderQuery = useQuery({
    queryKey: ['my-order', orderNo],
    queryFn: () => getMyOrder(orderNo!),
    enabled: Boolean(orderNo),
  });
  const afterSalesQuery = useQuery({
    queryKey: ['my-order-after-sales', orderNo],
    queryFn: () => listOrderAfterSales(orderNo!),
    enabled: Boolean(orderNo),
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelMyOrder(orderNo!, '用户取消未发货订单'),
    onSuccess: async () => {
      message.success('订单已取消');
      await queryClient.invalidateQueries({ queryKey: ['my-order', orderNo] });
      await queryClient.invalidateQueries({ queryKey: ['my-orders'] });
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const applyMutation = useMutation({
    mutationFn: (values: ApplyFormValues) =>
      applyOrderAfterSale(orderNo!, {
        sku_code: values.sku_code,
        type: 'EXCHANGE',
        reason: values.reason,
        description: values.description,
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: (afterSale) => {
      message.success('换货申请已提交');
      setApplyOpen(false);
      applyForm.resetFields();
      navigate(`/shop/after-sales/${afterSale.after_sales_no}`);
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  if (!orderNo) return <Alert type="error" showIcon message="无效的订单编号" />;
  if (orderQuery.error) return <Alert type="error" showIcon message={errorMessage(orderQuery.error)} />;
  if (!orderQuery.data) return <Card loading />;

  const order = orderQuery.data;
  const canCancel = order.status === 'CREATED' && order.fulfillment_status === 'UNSHIPPED';
  const canApply =
    order.fulfillment_status === 'DELIVERED' || order.fulfillment_status === 'COMPLETED';

  return (
    <div className="shop-page">
      <Space wrap>
        <Button onClick={() => navigate('/shop/orders')}>返回我的订单</Button>
        {canCancel ? (
          <Popconfirm
            title="确认取消这个未发货订单？"
            onConfirm={() => cancelMutation.mutate()}
          >
            <Button danger loading={cancelMutation.isPending}>
              取消订单
            </Button>
          </Popconfirm>
        ) : null}
        {canApply ? (
          <Button type="primary" onClick={() => setApplyOpen(true)}>
            申请换货
          </Button>
        ) : (
          <>
            <Button disabled>申请换货</Button>
            <Typography.Text type="secondary">
              {order.status === 'CANCELLED'
                ? '订单已取消，无法申请换货'
                : '订单送达后可申请换货，请等待管理员发货并确认送达'}
            </Typography.Text>
          </>
        )}
      </Space>

      <Card className="shop-detail-card" title={`订单 ${order.order_no}`}>
        <Descriptions column={2} size="middle">
          <Descriptions.Item label="订单状态"><StatusTag status={order.status} /></Descriptions.Item>
          <Descriptions.Item label="履约状态"><StatusTag status={order.fulfillment_status} /></Descriptions.Item>
          <Descriptions.Item label="订单金额">{formatMoney(order.total_amount)}</Descriptions.Item>
          <Descriptions.Item label="下单时间">{formatDate(order.created_at)}</Descriptions.Item>
          <Descriptions.Item label="收货人">{order.receiver_name}</Descriptions.Item>
          <Descriptions.Item label="联系电话">{order.receiver_phone}</Descriptions.Item>
          <Descriptions.Item label="收货地址" span={2}>{order.receiver_address}</Descriptions.Item>
          <Descriptions.Item label="承运商">{order.shipping_carrier ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="运单号">{order.tracking_no ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="发货时间">{formatDate(order.shipped_at)}</Descriptions.Item>
          <Descriptions.Item label="送达时间">{formatDate(order.delivered_at)}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="shop-detail-card" title="商品明细">
        <Table<OrderItem>
          rowKey={(item) => `${item.sku_code}-${item.unit_price}`}
          dataSource={order.items}
          pagination={false}
          columns={[
            { title: '商品', dataIndex: 'product_name' },
            { title: 'SKU', dataIndex: 'sku_code' },
            {
              title: '规格',
              dataIndex: 'sku_attributes',
              render: (value: Record<string, string>) =>
                Object.entries(value).map(([key, item]) => `${key}: ${item}`).join(' / '),
            },
            { title: '单价', dataIndex: 'unit_price', render: (value: string) => formatMoney(value) },
            { title: '数量', dataIndex: 'quantity' },
            { title: '小计', dataIndex: 'line_amount', render: (value: string) => formatMoney(value) },
          ]}
        />
      </Card>

      <Card className="shop-detail-card" title="售后记录">
        {afterSalesQuery.error ? (
          <Alert type="warning" showIcon message={errorMessage(afterSalesQuery.error)} />
        ) : (
          <Table<AfterSale>
            rowKey="after_sales_no"
            loading={afterSalesQuery.isLoading}
            dataSource={afterSalesQuery.data?.items ?? []}
            locale={{ emptyText: '暂无售后记录，订单送达后可申请换货' }}
            pagination={false}
            columns={[
              {
                title: '售后编号',
                dataIndex: 'after_sales_no',
                render: (value: string) => (
                  <Link to={`/shop/after-sales/${value}`}>{value}</Link>
                ),
              },
              { title: '类型', dataIndex: 'type' },
              { title: '状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> },
              { title: '原因', dataIndex: 'reason' },
              { title: '申请时间', dataIndex: 'created_at', render: formatDate },
            ]}
          />
        )}
      </Card>

      <Modal
        title="申请换货"
        open={applyOpen}
        onCancel={() => setApplyOpen(false)}
        onOk={() => applyForm.submit()}
        confirmLoading={applyMutation.isPending}
        okText="提交申请"
        destroyOnHidden
      >
        <Form form={applyForm} layout="vertical" onFinish={(values) => applyMutation.mutate(values)}>
          <Form.Item
            name="sku_code"
            label="商品"
            rules={[{ required: true, message: '请选择商品' }]}
          >
            <Select
              options={order.items.map((item) => ({
                value: item.sku_code,
                label: `${item.product_name} / ${item.sku_code}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="reason" label="换货原因" rules={[{ required: true, message: '请输入原因' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="补充说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
        <Typography.Text type="secondary">
          当前售后仅支持换货；提交后等待运营人员审核。
        </Typography.Text>
      </Modal>
    </div>
  );
}
