import { InboxOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { UploadFile } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteDocument, listDocuments, retrieve, uploadDocument } from '../../api/knowledge';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';
import type { KnowledgeDocument, RetrievalItem } from '../../types/knowledge';

const ACCEPT = '.pdf,.docx,.md,.txt,.html';
const MAX_SIZE = 20 * 1024 * 1024;

interface UploadValues {
  title: string;
  description?: string;
  visibility: 'PUBLIC' | 'ADMIN_ONLY';
}

export function KnowledgeListPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [visibility, setVisibility] = useState<string | undefined>();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploadForm] = Form.useForm<UploadValues>();
  const [retrievalOpen, setRetrievalOpen] = useState(false);
  const [queryText, setQueryText] = useState('');
  const [retrievalItems, setRetrievalItems] = useState<RetrievalItem[]>([]);

  const documents = useQuery({
    queryKey: ['knowledge', page, keyword, visibility],
    queryFn: () =>
      listDocuments({
        page,
        page_size: 10,
        keyword: keyword || undefined,
        visibility,
      }),
  });
  const upload = useMutation({
    mutationFn: (values: UploadValues) =>
      uploadDocument({
        file: fileList[0].originFileObj as File,
        title: values.title,
        description: values.description,
        visibility: values.visibility,
      }),
    onSuccess: async () => {
      message.success('文档已上传，后台正在处理；处理完成后才会发布');
      setUploadOpen(false);
      setFileList([]);
      uploadForm.resetFields();
      await queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      message.success('文档已删除');
      await queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const retrieval = useMutation({
    mutationFn: () => retrieve(queryText, 5),
    onSuccess: (data) => setRetrievalItems(data.items),
    onError: (error) => message.error(errorMessage(error)),
  });

  return (
    <div className="page-stack">
      <PageHeader
        title="RAG 知识库"
        subtitle="上传、处理、发布和检索都复用 TASK-005 后端能力"
        extra={
          <Space>
            <Button onClick={() => setRetrievalOpen(true)}>检索测试</Button>
            <Button type="primary" onClick={() => setUploadOpen(true)}>
              上传文档
            </Button>
          </Space>
        }
      />
      {documents.error ? <Alert type="error" showIcon message={errorMessage(documents.error)} /> : null}
      <Card className="soft-card">
        <Space wrap className="filter-row">
          <Input.Search
            allowClear
            placeholder="文档标题"
            style={{ width: 260 }}
            onSearch={(value) => {
              setKeyword(value);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="可见性"
            style={{ width: 160 }}
            value={visibility}
            onChange={(value) => {
              setVisibility(value);
              setPage(1);
            }}
            options={[
              { value: 'PUBLIC', label: 'PUBLIC' },
              { value: 'ADMIN_ONLY', label: 'ADMIN_ONLY' },
            ]}
          />
        </Space>
        <Table<KnowledgeDocument>
          rowKey="id"
          loading={documents.isLoading}
          dataSource={documents.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: 10,
            total: documents.data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            {
              title: '文档',
              dataIndex: 'title',
              render: (value: string, record) => <Link to={`/knowledge/${record.id}`}>{value}</Link>,
            },
            { title: '状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> },
            {
              title: '可见性',
              dataIndex: 'visibility',
              render: (value: string) => <Tag color={value === 'PUBLIC' ? 'blue' : 'purple'}>{value}</Tag>,
            },
            {
              title: '当前发布版本',
              dataIndex: 'current_published_version_id',
              render: (value: number | null) => value ?? '未发布',
            },
            { title: '创建时间', dataIndex: 'created_at', render: formatDate },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, record) => (
                <Space>
                  <Link to={`/knowledge/${record.id}`}>查看</Link>
                  <Popconfirm
                    title="删除文档及其版本？"
                    description="删除后检索将不再返回该文档。"
                    onConfirm={() => remove.mutate(record.id)}
                  >
                    <Button type="link" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="上传知识库文档"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={() => uploadForm.submit()}
        confirmLoading={upload.isPending}
        okButtonProps={{ disabled: !fileList.length }}
        destroyOnHidden
      >
        <Form form={uploadForm} layout="vertical" onFinish={(values) => upload.mutate(values)}>
          <Form.Item name="title" label="文档标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="visibility" label="可见性" initialValue="PUBLIC">
            <Select
              options={[
                { value: 'PUBLIC', label: 'PUBLIC · 登录用户可检索' },
                { value: 'ADMIN_ONLY', label: 'ADMIN_ONLY · 仅管理员' },
              ]}
            />
          </Form.Item>
          <Upload.Dragger
            accept={ACCEPT}
            maxCount={1}
            fileList={fileList}
            beforeUpload={(file) => {
              if (file.size > MAX_SIZE) {
                void message.error('文件不能超过 20MB');
                return Upload.LIST_IGNORE;
              }
              setFileList([file]);
              return false;
            }}
            onRemove={() => setFileList([])}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p>点击或拖拽文件到此处</p>
            <Typography.Text type="secondary">PDF / DOCX / Markdown / TXT / HTML，最大 20MB</Typography.Text>
          </Upload.Dragger>
          <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
            上传成功不等于索引完成；最终状态以版本列表为准。
          </Typography.Paragraph>
        </Form>
      </Modal>

      <Modal
        title="知识检索测试"
        open={retrievalOpen}
        onCancel={() => setRetrievalOpen(false)}
        footer={null}
        width={760}
        destroyOnHidden
      >
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={queryText}
            onChange={(event) => setQueryText(event.target.value)}
            placeholder="输入问题，调用真实 /knowledge/retrieve"
            onPressEnter={() => retrieval.mutate()}
          />
          <Button type="primary" loading={retrieval.isPending} onClick={() => retrieval.mutate()}>
            检索
          </Button>
        </Space.Compact>
        <div className="retrieval-list">
          {retrievalItems.map((item) => (
            <Card key={item.chunk_id} size="small" className="retrieval-card">
              <Space direction="vertical">
                <Space>
                  <Tag color="blue">{item.document_title}</Tag>
                  <Tag>score {item.score.toFixed(3)}</Tag>
                  {item.section_title ? <Tag>{item.section_title}</Tag> : null}
                </Space>
                <Typography.Paragraph ellipsis={{ rows: 4 }}>{item.content}</Typography.Paragraph>
              </Space>
            </Card>
          ))}
          {!retrievalItems.length && !retrieval.isPending ? (
            <Typography.Text type="secondary">输入问题后展示真实检索结果。</Typography.Text>
          ) : null}
        </div>
      </Modal>
    </div>
  );
}
