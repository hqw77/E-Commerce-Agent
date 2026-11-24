import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Input, Select, Space, Table, Typography } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listOrders } from '../../api/orders';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { Order } from '../../types/order';

export function OrderListPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | undefined>();
  const [keyword, setKeyword] = useState('');
  const query = useQuery({
    queryKey: ['orders', page, status],
    queryFn: () => listOrders({ page, page_size: 10, status }),
  });
  const rows = (query.data?.items ?? []).filter(
    (order) => !keyword || order.order_no.toLowerCase().includes(keyword.toLowerCase()),
  );

  return (
    <div className="page-stack">
      <PageHeader title="订单管理" subtitle="订单状态、金额与履约状态均以后端返回为准" />
      {query.error ? <Alert type="error" showIcon message={errorMessage(query.error)} /> : null}
      <Card className="soft-card">
        <Space wrap className="filter-row">
          <Input.Search
            allowClear
            placeholder="订单编号"
            style={{ width: 240 }}
            onSearch={setKeyword}
          />
          <Select
            allowClear
            placeholder="订单状态"
            style={{ width: 180 }}
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={['CREATED', 'CANCELLED', 'CLOSED', 'COMPLETED'].map(
              (value) => ({ value, label: value }),
            )}
          />
        </Space>
        <Table<Order>
          rowKey="order_no"
          loading={query.isLoading}
          dataSource={rows}
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
              render: (value: string) => <Link to={`/orders/${value}`}>{value}</Link>,
            },
            { title: '订单状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> },
            { title: '履约状态', dataIndex: 'fulfillment_status', render: (value: string) => <StatusTag status={value} /> },
            { title: '金额', dataIndex: 'total_amount', render: (value: string) => formatMoney(value) },
            { title: '收货人', dataIndex: 'receiver_name' },
            { title: '创建时间', dataIndex: 'created_at', render: formatDate },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, record) => <Link to={`/orders/${record.order_no}`}>查看详情</Link>,
            },
          ]}
        />
        <Typography.Text type="secondary">
          管理端订单列表需要管理员权限；当前用户不能在前端绕过 Service 修改订单状态。
        </Typography.Text>
      </Card>
    </div>
  );
}
