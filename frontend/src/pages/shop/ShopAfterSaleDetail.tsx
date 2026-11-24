import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Space,
  Typography,
} from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getMyAfterSale,
  submitAfterSaleReturn,
} from '../../api/customerAfterSales';
import { getMyOrder } from '../../api/customerOrders';
import { StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';

interface ReturnFormValues {
  return_carrier: string;
  return_tracking_no: string;
}

export function ShopAfterSaleDetailPage() {
  const { afterSalesNo } = useParams<{ afterSalesNo: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [returnForm] = Form.useForm<ReturnFormValues>();
  const query = useQuery({
    queryKey: ['my-after-sale', afterSalesNo],
    queryFn: () => getMyAfterSale(afterSalesNo!),
    enabled: Boolean(afterSalesNo),
  });
  const orderQuery = useQuery({
    queryKey: ['my-after-sale-order', query.data?.order_no],
    queryFn: () => getMyOrder(query.data!.order_no),
    enabled: Boolean(query.data?.order_no),
  });
  const returnMutation = useMutation({
    mutationFn: (values: ReturnFormValues) => submitAfterSaleReturn(afterSalesNo!, values),
    onSuccess: async () => {
      message.success('退货物流已提交');
      await query.refetch();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  if (!afterSalesNo) return <Alert type="error" showIcon message="无效的售后编号" />;
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;

  const afterSale = query.data;
  const canSubmitReturn = afterSale.status === 'WAITING_RETURN';

  return (
    <div className="shop-page">
      <Space wrap>
        <Button onClick={() => navigate('/shop/after-sales')}>返回我的售后</Button>
        <Button onClick={() => navigate(`/shop/orders/${afterSale.order_no}`)}>查看订单</Button>
      </Space>

      <Card className="shop-detail-card" title={`售后 ${afterSale.after_sales_no}`}>
        <Descriptions column={2} size="middle">
          <Descriptions.Item label="售后状态"><StatusTag status={afterSale.status} /></Descriptions.Item>
          <Descriptions.Item label="类型">{afterSale.type}</Descriptions.Item>
          <Descriptions.Item label="订单编号">{afterSale.order_no}</Descriptions.Item>
          <Descriptions.Item label="SKU">{afterSale.sku_code}</Descriptions.Item>
          <Descriptions.Item label="数量">{afterSale.quantity}</Descriptions.Item>
          <Descriptions.Item label="申请金额">{formatMoney(afterSale.requested_amount)}</Descriptions.Item>
          <Descriptions.Item label="申请原因">{afterSale.reason}</Descriptions.Item>
          <Descriptions.Item label="申请时间">{formatDate(afterSale.created_at)}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{afterSale.description ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="审核意见" span={2}>{afterSale.review_note ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="退货承运商">{afterSale.return_carrier ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="退货单号">{afterSale.return_tracking_no ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="换货承运商">{afterSale.replacement_carrier ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="换货单号">{afterSale.replacement_tracking_no ?? '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {orderQuery.data ? (
        <Card className="shop-detail-card" title="关联订单">
          <Typography.Text>
            {orderQuery.data.order_no} · {orderQuery.data.receiver_name} ·{' '}
            {formatMoney(orderQuery.data.total_amount)}
          </Typography.Text>
        </Card>
      ) : null}

      {canSubmitReturn ? (
        <Card className="shop-detail-card" title="填写退货物流">
          <Form form={returnForm} layout="vertical" onFinish={(values) => returnMutation.mutate(values)}>
            <Form.Item
              name="return_carrier"
              label="退货承运商"
              rules={[{ required: true, message: '请输入承运商' }]}
            >
              <Input placeholder="例如 顺丰速运" />
            </Form.Item>
            <Form.Item
              name="return_tracking_no"
              label="退货单号"
              rules={[{ required: true, message: '请输入退货单号' }]}
            >
              <Input />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={returnMutation.isPending}>
              提交退货物流
            </Button>
          </Form>
        </Card>
      ) : null}
    </div>
  );
}
