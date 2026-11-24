import { PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  changeProductStatus,
  createSku,
  getProduct,
  listCategories,
  updateProduct,
  updateSku,
} from '../../api/products';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate, formatMoney } from '../../utils/format';
import type { SkuDetail } from '../../types/product';

interface SkuFormValues {
  sku_code: string;
  price: number;
  attributes: Array<{ key: string; value: string }>;
}

const PRODUCT_PLACEHOLDER = '/products/placeholder.svg';

export function ProductDetailPage() {
  const { message } = App.useApp();
  const { productId } = useParams();
  const navigate = useNavigate();
  const id = Number(productId);
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editingSku, setEditingSku] = useState<SkuDetail | null>(null);
  const [productEditOpen, setProductEditOpen] = useState(false);
  const [productForm] = Form.useForm<{
    name: string;
    description?: string;
    category_id: number;
    image_url?: string;
  }>();
  const categories = useQuery({ queryKey: ['categories'], queryFn: listCategories });
  const [skuForm] = Form.useForm<SkuFormValues>();
  const [editForm] = Form.useForm<{ price: number; status: 'ACTIVE' | 'INACTIVE' }>();

  const query = useQuery({
    queryKey: ['product', id],
    queryFn: () => getProduct(id),
    enabled: Number.isInteger(id) && id > 0,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['product', id] });
  const statusMutation = useMutation({
    mutationFn: (action: 'activate' | 'deactivate' | 'archive') =>
      changeProductStatus(id, action),
    onSuccess: async () => {
      message.success('商品状态已更新');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const createSkuMutation = useMutation({
    mutationFn: (values: SkuFormValues) =>
      createSku(id, {
        sku_code: values.sku_code,
        price: values.price,
        attributes: Object.fromEntries(values.attributes.map((item) => [item.key, item.value])),
      }),
    onSuccess: async () => {
      message.success('SKU 已创建，库存初始为 0');
      setCreateOpen(false);
      skuForm.resetFields();
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const updateProductMutation = useMutation({
    mutationFn: (values: {
      name: string;
      description?: string;
      category_id: number;
      image_url?: string;
    }) => updateProduct(id, values),
    onSuccess: async () => {
      message.success('商品资料已更新');
      setProductEditOpen(false);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const editSkuMutation = useMutation({
    mutationFn: (values: { price: number; status: 'ACTIVE' | 'INACTIVE' }) =>
      updateSku(editingSku!.id, values),
    onSuccess: async () => {
      message.success('SKU 已更新');
      setEditingSku(null);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  if (!Number.isInteger(id) || id <= 0) {
    return <Alert type="error" showIcon message="无效的商品编号" />;
  }
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;
  const product = query.data;

  return (
    <div className="page-stack">
      <PageHeader
        title={product.name}
        subtitle={`商品编号 ${product.product_no}`}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/products')}>返回列表</Button>
            {product.status !== 'ACTIVE' ? (
              <Popconfirm
                title="确认上架该商品？"
                onConfirm={() => statusMutation.mutate('activate')}
              >
                <Button type="primary">上架</Button>
              </Popconfirm>
            ) : (
              <Popconfirm
                title="确认下架该商品？"
                onConfirm={() => statusMutation.mutate('deactivate')}
              >
                <Button>下架</Button>
              </Popconfirm>
            )}
            {product.status !== 'ARCHIVED' ? (
              <Popconfirm
                title="归档后不可修改，确认继续？"
                onConfirm={() => statusMutation.mutate('archive')}
              >
                <Button danger>归档</Button>
              </Popconfirm>
            ) : null}
          </Space>
        }
      />
      <Card className="soft-card" title="商品信息">
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', marginBottom: 16 }}>
          <Image
            src={product.image_url || PRODUCT_PLACEHOLDER}
            fallback={PRODUCT_PLACEHOLDER}
            alt={product.name}
            width={240}
            height={240}
            style={{ objectFit: 'cover', borderRadius: 12, flex: '0 0 auto' }}
          />
          <Descriptions column={1} bordered size="middle" style={{ flex: 1 }}>
            <Descriptions.Item label="商品编号">{product.product_no}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <StatusTag status={product.status} />
            </Descriptions.Item>
            <Descriptions.Item label="名称">{product.name}</Descriptions.Item>
            <Descriptions.Item label="分类 ID">{product.category_id}</Descriptions.Item>
            <Descriptions.Item label="描述">
              {product.description || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDate(product.created_at)}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{formatDate(product.updated_at)}</Descriptions.Item>
          </Descriptions>
        </div>
        <div className="inline-actions">
          <Button
            onClick={() => {
              productForm.setFieldsValue({
                name: product.name,
                description: product.description ?? undefined,
                category_id: product.category_id,
                image_url: product.image_url ?? undefined,
              });
              setProductEditOpen(true);
            }}
          >
            编辑商品资料
          </Button>
          <Typography.Text type="secondary">
            商品资料通过后端 PATCH 接口更新；SKU 价格和状态也由 Service 校验。
          </Typography.Text>
        </div>
      </Card>

      <Card
        className="soft-card"
        title="SKU 与库存"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新增 SKU
          </Button>
        }
      >
        <Table
          rowKey="id"
          dataSource={product.skus}
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
              title: '状态',
              dataIndex: 'status',
              render: (value: string) => <StatusTag status={value} />,
            },
            {
              title: '可用库存',
              dataIndex: 'inventory',
              render: (value: SkuDetail['inventory']) => value?.available_quantity ?? 0,
            },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, record: SkuDetail) => (
                <Space>
                  <Button
                    size="small"
                    onClick={() => {
                      setEditingSku(record);
                      editForm.setFieldsValue({
                        price: Number(record.price),
                        status: record.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE',
                      });
                    }}
                  >
                    编辑
                  </Button>
                  <Link to={`/inventory/transactions?skuId=${record.id}`}>流水</Link>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新增 SKU"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => skuForm.submit()}
        confirmLoading={createSkuMutation.isPending}
        destroyOnHidden
      >
        <Form
          form={skuForm}
          layout="vertical"
          initialValues={{ attributes: [{ key: '', value: '' }] }}
          onFinish={(values) => createSkuMutation.mutate(values)}
        >
          <Form.Item name="sku_code" label="SKU 编号" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="price" label="价格" rules={[{ required: true }]}>
            <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.List name="attributes">
            {(fields, { add, remove }) => (
              <Space direction="vertical" style={{ width: '100%' }}>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline">
                    <Form.Item
                      name={[field.name, 'key']}
                      rules={[{ required: true, message: '属性名' }]}
                    >
                      <Input placeholder="属性名，例如 color" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'value']}
                      rules={[{ required: true, message: '属性值' }]}
                    >
                      <Input placeholder="属性值" />
                    </Form.Item>
                    <Button type="link" danger onClick={() => remove(field.name)}>
                      删除
                    </Button>
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ key: '', value: '' })}>
                  添加属性
                </Button>
              </Space>
            )}
          </Form.List>
        </Form>
      </Modal>

      <Modal
        title={`编辑 SKU ${editingSku?.sku_code ?? ''}`}
        open={Boolean(editingSku)}
        onCancel={() => setEditingSku(null)}
        onOk={() => editForm.submit()}
        confirmLoading={editSkuMutation.isPending}
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical" onFinish={(values) => editSkuMutation.mutate(values)}>
          <Form.Item name="price" label="价格" rules={[{ required: true }]}>
            <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'ACTIVE', label: 'ACTIVE' },
                { value: 'INACTIVE', label: 'INACTIVE' },
              ]}
            />
          </Form.Item>
        </Form>
        <Typography.Text type="secondary">
          库存数量不能在此直接修改；请使用库存管理页的入库或调整接口。
        </Typography.Text>
      </Modal>

      <Modal
        title="编辑商品资料"
        open={productEditOpen}
        onCancel={() => setProductEditOpen(false)}
        onOk={() => productForm.submit()}
        confirmLoading={updateProductMutation.isPending}
        destroyOnHidden
      >
        <Form
          form={productForm}
          layout="vertical"
          onFinish={(values) => updateProductMutation.mutate(values)}
        >
          <Form.Item name="name" label="商品名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="category_id" label="分类" rules={[{ required: true }]}>
            <Select
              loading={categories.isLoading}
              options={(categories.data ?? []).map((category) => ({
                value: category.id,
                label: category.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="image_url" label="商品图片路径">
            <Input placeholder="例如 /products/05-smartphone.jpg" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

