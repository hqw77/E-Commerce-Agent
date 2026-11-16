import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Space, Typography } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { getAfterSale } from '../../api/afterSales';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';

export function AfterSaleDetailPage() {
  const { afterSalesNo } = useParams();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['after-sale', afterSalesNo],
    queryFn: () => getAfterSale(afterSalesNo!),
    enabled: Boolean(afterSalesNo),
  });

  if (!afterSalesNo) return <Alert type="error" showIcon message="无效的售后编号" />;
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;
  const item = query.data;

  return (
    <div className="page-stack">
      <PageHeader
        title={`售后 ${item.after_sales_no}`}
        subtitle="售后申请与审核、退款是不同阶段"
        extra={<Button onClick={() => navigate('/after-sales')}>返回列表</Button>}
      />
      <Card className="soft-card" title="售后信息">
        <Descriptions column={2} bordered size="middle">
          <Descriptions.Item label="售后状态"><StatusTag status={item.status} /></Descriptions.Item>
          <Descriptions.Item label="类型">{item.type}</Descriptions.Item>
          <Descriptions.Item label="关联订单">{item.order_no}</Descriptions.Item>
          <Descriptions.Item label="SKU">{item.sku_code}</Descriptions.Item>
          <Descriptions.Item label="数量">{item.quantity}</Descriptions.Item>
          <Descriptions.Item label="申请金额">{formatMoney(item.requested_amount)}</Descriptions.Item>
          <Descriptions.Item label="审核金额">
            {item.approved_amount ? formatMoney(item.approved_amount) : '-'}
          </Descriptions.Item>
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
          <Descriptions.Item label="完成时间">{formatDate(item.completed_at)}</Descriptions.Item>
        </Descriptions>
      </Card>
      {item.status === 'PENDING_REVIEW' ? (
        <Alert
          type="info"
          showIcon
          message="申请已提交，等待审核"
          description="当前状态不代表审核通过，也不代表已退款。"
        />
      ) : null}
      <Card className="soft-card" title="流程说明">
        <Space direction="vertical">
          <Typography.Text>售后审核、收货、退款和换货补发由后端管理端流程完成。</Typography.Text>
          <Typography.Text type="secondary">
            本页面只读展示；前端不提供越权的审核或退款按钮。
          </Typography.Text>
        </Space>
      </Card>
    </div>
  );
}
