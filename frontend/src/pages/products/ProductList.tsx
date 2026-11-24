import { PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Image,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { createProduct, listCategories, listProducts } from '../../api/products';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';
import type { Product } from '../../types/product';

interface ProductFormValues {
  product_no: string;
  category_id: number;
  name: string;
  description?: string;
  image_url?: string;
}

const PRODUCT_PLACEHOLDER = '/products/placeholder.svg';

export function ProductListPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<ProductFormValues>();

  const query = useQuery({
    queryKey: ['products', page, keyword, status, categoryId],
    queryFn: () =>
      listProducts({
        page,
        page_size: 10,
        keyword: keyword || undefined,
        status,
        category_id: categoryId,
      }),
  });
  const categories = useQuery({
    queryKey: ['categories'],
    queryFn: listCategories,
  });
  const create = useMutation({
    mutationFn: createProduct,
    onSuccess: async () => {
      message.success('商品已创建');
      setCreateOpen(false);
      form.resetFields();
      await queryClient.invalidateQueries({ queryKey: ['products'] });
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const columns: ColumnsType<Product> = [
    {
      title: '图片',
      dataIndex: 'image_url',
      width: 84,
      render: (value: string | null, record) => (
        <Link to={`/products/${record.id}`}>
          <Image
            src={value || PRODUCT_PLACEHOLDER}
            fallback={PRODUCT_PLACEHOLDER}
            alt={record.name}
            width={56}
            height={56}
            preview={false}
            style={{ objectFit: 'cover', borderRadius: 8 }}
          />
        </Link>
      ),
    },
    {
      title: '商品编号',
      dataIndex: 'product_no',
      render: (value: string, record) => <Link to={`/products/${record.id}`}>{value}</Link>,
    },
    { title: '商品名称', dataIndex: 'name' },
    {
      title: '分类',
      dataIndex: 'category_id',
      render: (value: number) =>
        categories.data?.find((category) => category.id === value)?.name ?? value,
    },
    { title: '状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> },
    { title: '创建时间', dataIndex: 'created_at', render: formatDate },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => <Link to={`/products/${record.id}`}>查看 / 编辑</Link>,
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        title="商品管理"
        subtitle="商品主数据与 SKU 由后端 Service 管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新增商品
          </Button>
        }
      />
      {query.error ? <Alert type="error" showIcon message={errorMessage(query.error)} /> : null}
      <Card className="soft-card">
        <Space wrap className="filter-row">
          <Input.Search
            allowClear
            placeholder="按名称搜索"
            onSearch={(value) => {
              setKeyword(value);
              setPage(1);
            }}
            style={{ width: 260 }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED'].map((value) => ({
              value,
              label: value,
            }))}
          />
          <Select
            allowClear
            placeholder="分类"
            style={{ width: 180 }}
            value={categoryId}
            onChange={(value) => {
              setCategoryId(value);
              setPage(1);
            }}
            options={(categories.data ?? []).map((category) => ({
              value: category.id,
              label: category.name,
            }))}
          />
        </Space>
        <Table
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: 10,
            total: query.data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
        />
      </Card>

      <Modal
        title="新增商品"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText="创建"
        confirmLoading={create.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => create.mutate(values)}>
          <Form.Item
            name="product_no"
            label="商品编号"
            rules={[{ required: true, message: '请输入商品编号' }]}
          >
            <Input placeholder="例如 PROD-001" />
          </Form.Item>
          <Form.Item
            name="category_id"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select
              loading={categories.isLoading}
              options={(categories.data ?? []).map((category) => ({
                value: category.id,
                label: category.name,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label="商品名称"
            rules={[{ required: true, message: '请输入商品名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="image_url" label="商品图片路径">
            <Input placeholder="例如 /products/05-smartphone.jpg" />
          </Form.Item>
          <Typography.Text type="secondary">
            创建后可在详情页补充 SKU；分类与商品规则由后端校验。
          </Typography.Text>
        </Form>
      </Modal>
    </div>
  );
}
