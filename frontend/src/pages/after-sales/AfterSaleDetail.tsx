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
  Typography,
} from 'antd';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  approveAfterSale,
  completeExchange,
  getAfterSale,
  receiveAfterSale,
  rejectAfterSale,
} from '../../api/afterSales';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';

export function AfterSaleDetailPage() {
  const { afterSalesNo } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [approveForm] = Form.useForm<{ review_note?: string }>();
  const [rejectForm] = Form.useForm<{ review_note: string }>();
  const [completeForm] = Form.useForm<{
    replacement_carrier: string;
    replacement_tracking_no: string;
  }>();
  const query = useQuery({
    queryKey: ['after-sale', afterSalesNo],
    queryFn: () => getAfterSale(afterSalesNo!),
    enabled: Boolean(afterSalesNo),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['after-sale', afterSalesNo] });
    await queryClient.invalidateQueries({ queryKey: ['after-sales'] });
  };
  const approveMutation = useMutation({
    mutationFn: (values: { review_note?: string }) =>
      approveAfterSale(afterSalesNo!, values.review_note),
    onSuccess: async () => {
      message.success('售后已审核通过');
      setApproveOpen(false);
      approveForm.resetFields();
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const rejectMutation = useMutation({
    mutationFn: (values: { review_note: string }) =>
      rejectAfterSale(afterSalesNo!, values.review_note),
    onSuccess: async () => {
      message.success('售后已拒绝');
      setRejectOpen(false);
      rejectForm.resetFields();
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const receiveMutation = useMutation({
    mutationFn: () => receiveAfterSale(afterSalesNo!),
    onSuccess: async () => {
      message.success('已确认收到退货');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const completeMutation = useMutation({
    mutationFn: (values: {
      replacement_carrier: string;
      replacement_tracking_no: string;
    }) => completeExchange(afterSalesNo!, values),
    onSuccess: async () => {
      message.success('换货已完成');
      setCompleteOpen(false);
      completeForm.resetFields();
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  if (!afterSalesNo) return <Alert type="error" showIcon message="无效的售后编号" />;
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;
  const item = query.data;
  const canReview = item.status === 'PENDING_REVIEW';
  const canReceive = item.status === 'RETURN_SHIPPED';
  const canComplete = item.status === 'RECEIVED';

  return (
    <div className="page-stack">
      <PageHeader
        title={`售后 ${item.after_sales_no}`}
        subtitle="售后申请与审核是不同阶段；当前仅支持换货"
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/after-sales')}>返回列表</Button>
            {canReview ? (
              <>
                <Button type="primary" onClick={() => setApproveOpen(true)}>
                  审核通过
                </Button>
                <Button danger onClick={() => setRejectOpen(true)}>
                  拒绝
                </Button>
              </>
            ) : null}
            {canReceive ? (
              <Popconfirm
                title="确认已收到用户退回商品？"
                onConfirm={() => receiveMutation.mutate()}
              >
                <Button type="primary" loading={receiveMutation.isPending}>
                  确认收货
                </Button>
              </Popconfirm>
            ) : null}
            {canComplete ? (
              <Button type="primary" onClick={() => setCompleteOpen(true)}>
                完成换货
              </Button>
            ) : null}
          </Space>
        }
      />
      <Card className="soft-card" title="售后信息">
        <Descriptions column={2} bordered size="middle">
          <Descriptions.Item label="售后状态"><StatusTag status={item.status} /></Descriptions.Item>
          <Descriptions.Item label="类型">{item.type}</Descriptions.Item>
          <Descriptions.Item label="关联订单">{item.order_no}</Descriptions.Item>
          <Descriptions.Item label="SKU">{item.sku_code}</Descriptions.Item>
          <Descriptions.Item label="数量">{item.quantity}</Descriptions.Item>
          <Descriptions.Item label="申请原因">{item.reason}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{item.description ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="证据" span={2}>
            {item.evidence_urls?.length ? item.evidence_urls.join(', ') : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="审核意见" span={2}>{item.review_note ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="申请时间">{formatDate(item.created_at)}</Descriptions.Item>
          <Descriptions.Item label="审核时间">{formatDate(item.reviewed_at)}</Descriptions.Item>
          <Descriptions.Item label="退货承运商">{item.return_carrier ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="退货单号">{item.return_tracking_no ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="换货承运商">{item.replacement_carrier ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="换货单号">{item.replacement_tracking_no ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="完成时间">{formatDate(item.completed_at)}</Descriptions.Item>
        </Descriptions>
      </Card>
      {item.status === 'PENDING_REVIEW' ? (
        <Alert
          type="info"
          showIcon
          message="申请已提交，等待审核"
          description="审核通过后用户可填写退货物流。"
        />
      ) : null}
      {item.status === 'WAITING_RETURN' ? (
        <Alert
          type="info"
          showIcon
          message="等待用户寄回商品"
          description="用户填写退货物流后，管理员可确认收货。"
        />
      ) : null}
      <Card className="soft-card" title="流程说明">
        <Space direction="vertical">
          <Typography.Text>售后审核、收货和换货补发由当前页面完成。</Typography.Text>
          <Typography.Text type="secondary">
            当前版本仅支持换货，不接支付和资金退款。
          </Typography.Text>
        </Space>
      </Card>

      <Modal
        title="审核通过"
        open={approveOpen}
        onCancel={() => setApproveOpen(false)}
        onOk={() => approveForm.submit()}
        confirmLoading={approveMutation.isPending}
        okText="通过"
        destroyOnHidden
      >
        <Form form={approveForm} layout="vertical" onFinish={(values) => approveMutation.mutate(values)}>
          <Form.Item name="review_note" label="审核备注">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="拒绝售后"
        open={rejectOpen}
        onCancel={() => setRejectOpen(false)}
        onOk={() => rejectForm.submit()}
        confirmLoading={rejectMutation.isPending}
        okText="确认拒绝"
        okButtonProps={{ danger: true }}
        destroyOnHidden
      >
        <Form form={rejectForm} layout="vertical" onFinish={(values) => rejectMutation.mutate(values)}>
          <Form.Item
            name="review_note"
            label="拒绝原因"
            rules={[{ required: true, message: '请输入拒绝原因' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="完成换货补发"
        open={completeOpen}
        onCancel={() => setCompleteOpen(false)}
        onOk={() => completeForm.submit()}
        confirmLoading={completeMutation.isPending}
        okText="完成换货"
        destroyOnHidden
      >
        <Form
          form={completeForm}
          layout="vertical"
          onFinish={(values) => completeMutation.mutate(values)}
        >
          <Form.Item
            name="replacement_carrier"
            label="补发承运商"
            rules={[{ required: true, message: '请输入承运商' }]}
          >
            <Input placeholder="例如 顺丰速运" />
          </Form.Item>
          <Form.Item
            name="replacement_tracking_no"
            label="补发运单号"
            rules={[{ required: true, message: '请输入运单号' }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
