import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Space, Table, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { listMyAfterSales } from '../../api/customerAfterSales';
import { StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { AfterSale } from '../../types/afterSales';

export function ShopAfterSalesPage() {
  const query = useQuery({
    queryKey: ['my-after-sales'],
    queryFn: () => listMyAfterSales({ page: 1, page_size: 50 }),
  });

  return (
    <div className="shop-page">
      <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          我的售后
        </Typography.Title>
        <Link to="/shop/orders">
          <Button>我的订单</Button>
        </Link>
      </Space>
      <Card className="shop-detail-card">
        {query.error ? <Alert type="error" showIcon message={errorMessage(query.error)} /> : null}
        <Table<AfterSale>
          rowKey="after_sales_no"
          loading={query.isLoading}
          dataSource={query.data?.items ?? []}
          locale={{ emptyText: '暂无售后记录，订单送达后可在「我的订单」申请换货' }}
          pagination={false}
          columns={[
            {
              title: '售后编号',
              dataIndex: 'after_sales_no',
              render: (value: string) => (
                <Link to={`/shop/after-sales/${value}`}>{value}</Link>
              ),
            },
            { title: '订单编号', dataIndex: 'order_no' },
            { title: '商品 SKU', dataIndex: 'sku_code' },
            { title: '类型', dataIndex: 'type' },
            {
              title: '状态',
              dataIndex: 'status',
              render: (value: string) => <StatusTag status={value} />,
            },
            {
              title: '申请金额',
              dataIndex: 'requested_amount',
              render: (value: string) => formatMoney(value),
            },
            { title: '申请时间', dataIndex: 'created_at', render: formatDate },
          ]}
        />
      </Card>
    </div>
  );
}
