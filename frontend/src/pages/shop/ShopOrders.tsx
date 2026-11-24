import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Select, Space, Table, Typography } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listMyOrders } from '../../api/customerOrders';
import { StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { Order } from '../../types/order';

export function ShopOrdersPage() {
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['my-orders', status, page],
    queryFn: () => listMyOrders({ status, page, page_size: 10 }),
  });

  return (
    <div className="shop-page">
      <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          我的订单
        </Typography.Title>
        <Link to="/shop">
          <Button>继续购物</Button>
        </Link>
      </Space>
      <Card className="shop-detail-card">
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="订单状态"
            style={{ width: 180 }}
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={['CREATED', 'CANCELLED', 'COMPLETED'].map((value) => ({
              value,
              label: value,
            }))}
          />
        </Space>
        {query.error ? <Alert type="error" showIcon message={errorMessage(query.error)} /> : null}
        <Table<Order>
          rowKey="order_no"
          loading={query.isLoading}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: 10,
            total: query.data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            {
              title: '订单编号',
              dataIndex: 'order_no',
              render: (value: string) => <Link to={`/shop/orders/${value}`}>{value}</Link>,
            },
            {
              title: '商品',
              render: (_: unknown, order: Order) =>
                order.items.map((item) => item.product_name).join('、'),
            },
            {
              title: '金额',
              dataIndex: 'total_amount',
              render: (value: string) => formatMoney(value),
            },
            {
              title: '订单状态',
              dataIndex: 'status',
              render: (value: string) => <StatusTag status={value} />,
            },
            {
              title: '履约状态',
              dataIndex: 'fulfillment_status',
              render: (value: string) => <StatusTag status={value} />,
            },
            {
              title: '下单时间',
              dataIndex: 'created_at',
              render: formatDate,
            },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, order: Order) => (
                <Link to={`/shop/orders/${order.order_no}`}>查看详情</Link>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
