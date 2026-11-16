import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adjustInventory, stockIn } from '../../api/inventory';
import { getProduct, listProducts } from '../../api/products';
import { PageHeader } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatMoney } from '../../utils/format';
import type { SkuDetail } from '../../types/product';

interface OperationValues {
  quantity?: number;
  quantity_delta?: number;
  remark?: string;
}

export function InventoryListPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [productId, setProductId] = useState<number | undefined>();
  const [operation, setOperation] = useState<'stock-in' | 'adjust' | null>(null);
  const [selectedSku, setSelectedSku] = useState<SkuDetail | null>(null);
  const [form] = Form.useForm<OperationValues>();

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
  const operationMutation = useMutation({
    mutationFn: async (values: OperationValues) => {
      if (!selectedSku || !operation) return;
      const idempotency_key = crypto.randomUUID();
      if (operation === 'stock-in') {
        return stockIn(selectedSku.id, {
          quantity: values.quantity ?? 0,
          remark: values.remark,
          idempotency_key,
        });
      }
      return adjustInventory(selectedSku.id, {
        quantity_delta: values.quantity_delta ?? 0,
        remark: values.remark,
        idempotency_key,
      });
    },
    onSuccess: async () => {
      message.success('库存操作已完成，后端流水已记录');
      setOperation(null);
      form.resetFields();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['inventory-product', productId] }),
        queryClient.invalidateQueries({ queryKey: ['inventory-products'] }),
      ]);
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  return (
    <div className="page-stack">
      <PageHeader
        title="库存管理"
        subtitle="库存数量由后端 InventoryService 计算，前端只提交真实操作请求"
      />
      {products.error ? <Alert type="error" showIcon message={errorMessage(products.error)} /> : null}
      <Card className="soft-card">
        <Space wrap className="filter-row">
          <Typography.Text strong>选择商品</Typography.Text>
          <Select
            style={{ minWidth: 320 }}
            loading={products.isLoading}
            value={productId}
            onChange={setProductId}
            options={(products.data?.items ?? []).map((product) => ({
              value: product.id,
              label: `${product.product_no} · ${product.name}`,
            }))}
          />
        </Space>
        {detail.error ? <Alert type="error" showIcon message={errorMessage(detail.error)} /> : null}
        <Table<SkuDetail>
          rowKey="id"
          loading={detail.isLoading}
          dataSource={detail.data?.skus ?? []}
          pagination={false}
          columns={[
            { title: 'SKU 编号', dataIndex: 'sku_code' },
            {
              title: '属性',
              dataIndex: 'attributes',
              render: (value: Record<string, string>) =>
                Object.entries(value)
                  .map(([key, item]) => `${key}: ${item}`)
                  .join(' / '),
            },
            {
              title: '价格',
              dataIndex: 'price',
              render: (value: string) => formatMoney(value),
            },
            {
              title: '总库存',
              dataIndex: 'inventory',
              render: (value: SkuDetail['inventory']) => value?.total_quantity ?? 0,
            },
            {
              title: '预留库存',
              dataIndex: 'inventory',
              render: (value: SkuDetail['inventory']) => value?.reserved_quantity ?? 0,
            },
            {
              title: '可用库存',
              dataIndex: 'inventory',
              render: (value: SkuDetail['inventory']) => value?.available_quantity ?? 0,
            },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, record) => (
                <Space>
                  <Button
                    size="small"
                    onClick={() => {
                      setSelectedSku(record);
                      setOperation('stock-in');
                    }}
                  >
                    入库
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setSelectedSku(record);
                      setOperation('adjust');
                    }}
                  >
                    调整
                  </Button>
                  <Link to={`/inventory/transactions?skuId=${record.id}`}>流水</Link>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={operation === 'stock-in' ? '库存入库' : '库存调整'}
        open={Boolean(operation)}
        onCancel={() => setOperation(null)}
        onOk={() => form.submit()}
        confirmLoading={operationMutation.isPending}
        destroyOnHidden
      >
        <Typography.Paragraph>
          SKU：{selectedSku?.sku_code} · 当前可用库存：
          {selectedSku?.inventory?.available_quantity ?? 0}
        </Typography.Paragraph>
        <Form form={form} layout="vertical" onFinish={(values) => operationMutation.mutate(values)}>
          {operation === 'stock-in' ? (
            <Form.Item name="quantity" label="入库数量" rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          ) : (
            <Form.Item name="quantity_delta" label="调整数量（可为负数）" rules={[{ required: true }]}>
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          )}
          <Form.Item name="remark" label="备注">
            <Input placeholder="例如：后台手工入库" />
          </Form.Item>
          <Typography.Text type="secondary">
            后端会校验库存约束并记录 inventory_transactions。
          </Typography.Text>
        </Form>
      </Modal>
    </div>
  );
}
