import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Select, Space, Table, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { listTransactions } from '../../api/inventory';
import { getProduct, listProducts } from '../../api/products';
import { PageHeader } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';
import type { InventoryTransaction } from '../../types/inventory';

export function InventoryTransactionsPage() {
  const [searchParams] = useSearchParams();
  const initialSku = Number(searchParams.get('skuId'));
  const [productId, setProductId] = useState<number | undefined>();
  const [skuId, setSkuId] = useState<number | undefined>(
    Number.isInteger(initialSku) && initialSku > 0 ? initialSku : undefined,
  );
  const [page, setPage] = useState(1);

  const products = useQuery({
    queryKey: ['inventory-products'],
    queryFn: () => listProducts({ page: 1, page_size: 100 }),
  });
  useEffect(() => {
    if (!productId && products.data?.items.length) {
      setProductId(products.data.items[0].id);
    }
  }, [productId, products.data]);
  const detail = useQuery({
    queryKey: ['inventory-product', productId],
    queryFn: () => getProduct(productId!),
    enabled: Boolean(productId),
  });
  useEffect(() => {
    if (!skuId && detail.data?.skus.length) {
      setSkuId(detail.data.skus[0].id);
    }
  }, [detail.data, skuId]);
  const transactions = useQuery({
    queryKey: ['inventory-transactions', skuId, page],
    queryFn: () => listTransactions(skuId!, { page, page_size: 20 }),
    enabled: Boolean(skuId),
  });

  return (
    <div className="page-stack">
      <PageHeader title="库存流水" subtitle="展示后端记录的库存变更，不在前端推算" />
      {products.error ? <Alert type="error" showIcon message={errorMessage(products.error)} /> : null}
      <Card className="soft-card">
        <Space wrap className="filter-row">
          <Select
            style={{ minWidth: 320 }}
            placeholder="选择商品"
            loading={products.isLoading}
            value={productId}
            onChange={(value) => {
              setProductId(value);
              setSkuId(undefined);
              setPage(1);
            }}
            options={(products.data?.items ?? []).map((product) => ({
              value: product.id,
              label: `${product.product_no} · ${product.name}`,
            }))}
          />
          <Select
            style={{ minWidth: 240 }}
            placeholder="选择 SKU"
            loading={detail.isLoading}
            value={skuId}
            onChange={(value) => {
              setSkuId(value);
              setPage(1);
            }}
            options={(detail.data?.skus ?? []).map((sku) => ({
              value: sku.id,
              label: sku.sku_code,
            }))}
          />
        </Space>
        {transactions.error ? (
          <Alert type="error" showIcon message={errorMessage(transactions.error)} />
        ) : null}
        <Table<InventoryTransaction>
          rowKey="id"
          loading={transactions.isLoading}
          dataSource={transactions.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: 20,
            total: transactions.data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            { title: '类型', dataIndex: 'transaction_type' },
            { title: '总库存变化', dataIndex: 'total_delta' },
            { title: '预留变化', dataIndex: 'reserved_delta' },
            { title: '变更后总库存', dataIndex: 'total_after' },
            { title: '变更后预留', dataIndex: 'reserved_after' },
            { title: '业务类型', dataIndex: 'business_type' },
            {
              title: '业务编号',
              dataIndex: 'business_id',
              render: (value: number | null) => value ?? '-',
            },
            { title: '备注', dataIndex: 'remark', render: (value: string | null) => value ?? '-' },
            { title: '时间', dataIndex: 'created_at', render: formatDate },
          ]}
        />
        <Typography.Text type="secondary">
          流水来自 GET /admin/inventory/{"{sku_id}"}/transactions，需要管理员权限。
        </Typography.Text>
      </Card>
    </div>
  );
}
