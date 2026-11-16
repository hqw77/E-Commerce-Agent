import { PlusOutlined } from '@ant-design/icons';
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
  Table,
  Tag,
} from 'antd';
import { useState } from 'react';
import {
  createCategory,
  listCategories,
  updateCategory,
} from '../../api/products';
import { PageHeader } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import type { Category, CategoryCreateRequest, CategoryUpdateRequest } from '../../types/product';

interface CreateValues {
  name: string;
  parent_id?: number;
  sort_order: number;
}

interface EditValues {
  name: string;
  sort_order: number;
  status: 'ENABLED' | 'DISABLED';
}

export function CategoryListPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);
  const [createForm] = Form.useForm<CreateValues>();
  const [editForm] = Form.useForm<EditValues>();

  const query = useQuery({
    queryKey: ['categories'],
    queryFn: listCategories,
  });
  const create = useMutation({
    mutationFn: (values: CreateValues) => {
      const payload: CategoryCreateRequest = {
        name: values.name,
        parent_id: values.parent_id ?? null,
        sort_order: values.sort_order,
      };
      return createCategory(payload);
    },
    onSuccess: async () => {
      message.success('分类已创建');
      setCreateOpen(false);
      createForm.resetFields();
      await queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const update = useMutation({
    mutationFn: (values: EditValues) => {
      const payload: CategoryUpdateRequest = {
        name: values.name,
        sort_order: values.sort_order,
        status: values.status,
      };
      return updateCategory(editing!.id, payload);
    },
    onSuccess: async () => {
      message.success('分类已更新');
      setEditing(null);
      await queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  const nameById = new Map((query.data ?? []).map((item) => [item.id, item.name]));

  return (
    <div className="page-stack">
      <PageHeader
        title="分类管理"
        subtitle="分类创建、编辑和启停使用现有 Backend Categories API"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新增分类
          </Button>
        }
      />
      {query.error ? <Alert type="error" showIcon message={errorMessage(query.error)} /> : null}
      <Card className="soft-card">
        <Table<Category>
          rowKey="id"
          loading={query.isLoading}
          dataSource={query.data ?? []}
          pagination={false}
          columns={[
            { title: 'ID', dataIndex: 'id' },
            { title: '分类名称', dataIndex: 'name' },
            {
              title: '父分类',
              dataIndex: 'parent_id',
              render: (value: number | null) =>
                value === null ? '根分类' : nameById.get(value) ?? value,
            },
            { title: '排序', dataIndex: 'sort_order' },
            {
              title: '状态',
              dataIndex: 'status',
              render: (value: string) => (
                <Tag color={value === 'ENABLED' ? 'green' : 'default'}>{value}</Tag>
              ),
            },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, record) => (
                <Button
                  size="small"
                  onClick={() => {
                    setEditing(record);
                    editForm.setFieldsValue({
                      name: record.name,
                      sort_order: record.sort_order,
                      status: record.status,
                    });
                  }}
                >
                  编辑
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新增分类"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={create.isPending}
        destroyOnHidden
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{ sort_order: 0 }}
          onFinish={(values) => create.mutate(values)}
        >
          <Form.Item name="name" label="分类名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="parent_id" label="父分类">
            <Select
              allowClear
              placeholder="不选择则为根分类"
              options={(query.data ?? []).map((category) => ({
                value: category.id,
                label: category.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑分类 ${editing?.name ?? ''}`}
        open={Boolean(editing)}
        onCancel={() => setEditing(null)}
        onOk={() => editForm.submit()}
        confirmLoading={update.isPending}
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical" onFinish={(values) => update.mutate(values)}>
          <Form.Item name="name" label="分类名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'ENABLED', label: 'ENABLED' },
                { value: 'DISABLED', label: 'DISABLED' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
