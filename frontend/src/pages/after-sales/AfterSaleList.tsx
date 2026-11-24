import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Input, Select, Space, Table, Typography } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listAfterSales } from '../../api/afterSales';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';
import type { AfterSale } from '../../types/afterSales';

export function AfterSaleListPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string | undefined>();
  const [keyword, setKeyword] = useState('');
  const query = useQuery({
    queryKey: ['after-sales', page, status],
    queryFn: () => listAfterSales({ page, page_size: 10, status }),
  });

  return (
    <div className="page-stack">
      <PageHeader
        title="售后管理"
        subtitle="售后状态由 AfterSaleService 管理，当前仅支持换货"
      />
      {query.error ? <Alert type="error" showIcon message={errorMessage(query.error)} /> : null}
      <Card className="soft-card">
        <Space wrap className="filter-row">
          <Input.Search
            allowClear
            placeholder="售后编号 / 订单编号（当前页）"
            style={{ width: 280 }}
            onSearch={setKeyword}
          />
          <Select
            allowClear
            placeholder="售后状态"
            style={{ width: 200 }}
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              'PENDING_REVIEW', 'REJECTED', 'CANCELLED', 'WAITING_RETURN',
              'RETURN_SHIPPED', 'RECEIVED', 'COMPLETED',
            ].map((value) => ({ value, label: value }))}
          />
        </Space>
        <Table<AfterSale>
          rowKey="after_sales_no"
          loading={query.isLoading}
          dataSource={(query.data?.items ?? []).filter(
            (item) =>
              !keyword ||
              item.after_sales_no.toLowerCase().includes(keyword.toLowerCase()) ||
              item.order_no.toLowerCase().includes(keyword.toLowerCase()),
          )}
          pagination={{
            current: page,
            pageSize: 10,
            total: query.data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            {
              title: '售后编号',
              dataIndex: 'after_sales_no',
              render: (value: string) => <Link to={`/after-sales/${value}`}>{value}</Link>,
            },
            { title: '订单编号', dataIndex: 'order_no' },
            { title: 'SKU', dataIndex: 'sku_code' },
            { title: '类型', dataIndex: 'type' },
            { title: '状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> },
            { title: '原因', dataIndex: 'reason' },
            { title: '申请时间', dataIndex: 'created_at', render: formatDate },
          ]}
        />
        <Typography.Text type="secondary">
          售后审核、收货和换货补发由管理员后端接口执行；本页面不提供前端自行批准。
        </Typography.Text>
      </Card>
    </div>
  );
}
