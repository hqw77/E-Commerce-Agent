import { InboxOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { UploadFile } from 'antd';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  deleteDocument,
  getDocument,
  publishVersion,
  retryVersion,
  uploadVersion,
} from '../../api/knowledge';
import { PageHeader, StatusTag } from '../../components/Common';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';
import type { KnowledgeVersion } from '../../types/knowledge';

export function KnowledgeDetailPage() {
  const { documentId } = useParams();
  const id = Number(documentId);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const query = useQuery({
    queryKey: ['knowledge-document', id],
    queryFn: () => getDocument(id),
    enabled: Number.isInteger(id) && id > 0,
  });

  async function refresh(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['knowledge-document', id] }),
      queryClient.invalidateQueries({ queryKey: ['knowledge'] }),
    ]);
  }

  const remove = useMutation({
    mutationFn: () => deleteDocument(id),
    onSuccess: async () => {
      message.success('文档已删除');
      await queryClient.invalidateQueries({ queryKey: ['knowledge'] });
      navigate('/knowledge');
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const publish = useMutation({
    mutationFn: (versionId: number) => publishVersion(id, versionId),
    onSuccess: async () => {
      message.success('版本已发布');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const retry = useMutation({
    mutationFn: (versionId: number) => retryVersion(id, versionId),
    onSuccess: async () => {
      message.success('版本已重新处理');
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });
  const upload = useMutation({
    mutationFn: () => {
      const file =
        fileList[0]?.originFileObj ??
        (fileList[0] as unknown as File | undefined);
      if (!file) throw new Error('请选择文件');
      return uploadVersion(id, file);
    },
    onSuccess: async () => {
      message.success('新版本已上传，处理完成后可发布');
      setUploadOpen(false);
      setFileList([]);
      await refresh();
    },
    onError: (error) => message.error(errorMessage(error)),
  });

  if (!Number.isInteger(id) || id <= 0) {
    return <Alert type="error" showIcon message="无效的文档编号" />;
  }
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;
  const document = query.data;

  return (
    <div className="page-stack">
      <PageHeader
        title={document.title}
        subtitle="文档状态、版本和索引处理结果"
        extra={
          <Space>
            <Button onClick={() => navigate('/knowledge')}>返回列表</Button>
            <Button onClick={() => setUploadOpen(true)}>上传新版本</Button>
            <Popconfirm
              title="删除文档及版本？"
              description="删除后检索不再返回该文档。"
              onConfirm={() => remove.mutate()}
            >
              <Button danger loading={remove.isPending}>删除</Button>
            </Popconfirm>
          </Space>
        }
      />
      <Card className="soft-card" title="文档信息">
        <Descriptions column={2} bordered size="middle">
          <Descriptions.Item label="文档状态"><StatusTag status={document.status} /></Descriptions.Item>
          <Descriptions.Item label="可见性">
            <Tag color={document.visibility === 'PUBLIC' ? 'blue' : 'purple'}>
              {document.visibility}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{document.description ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(document.created_at)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatDate(document.updated_at)}</Descriptions.Item>
          <Descriptions.Item label="当前发布版本" span={2}>
            {document.current_published_version_id ?? '未发布'}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card className="soft-card" title="版本与处理状态">
        <Table<KnowledgeVersion>
          rowKey="id"
          dataSource={document.versions}
          pagination={false}
          columns={[
            { title: '版本', dataIndex: 'version_no' },
            { title: '文件名', dataIndex: 'original_filename' },
            { title: '状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> },
            { title: 'Chunk 数', dataIndex: 'chunk_count' },
            {
              title: 'Embedding',
              dataIndex: 'embedding_model',
              render: (value: string | null, record) =>
                value ? `${value} / ${record.embedding_dimension ?? '-'}d` : '-',
            },
            {
              title: '错误',
              dataIndex: 'error_message',
              render: (value: string | null) => value ?? '-',
            },
            { title: '创建时间', dataIndex: 'created_at', render: formatDate },
            { title: '发布时间', dataIndex: 'published_at', render: formatDate },
            {
              title: '操作',
              key: 'actions',
              render: (_: unknown, record) => (
                <Space>
                  {record.status === 'INDEXED' ? (
                    <Button
                      type="primary"
                      size="small"
                      loading={publish.isPending}
                      onClick={() => publish.mutate(record.id)}
                    >
                      发布
                    </Button>
                  ) : null}
                  {record.status === 'FAILED' ? (
                    <Button
                      size="small"
                      loading={retry.isPending}
                      onClick={() => retry.mutate(record.id)}
                    >
                      重试
                    </Button>
                  ) : null}
                </Space>
              ),
            },
          ]}
        />
        <Typography.Text type="secondary">
          上传成功不代表索引完成；只有 PUBLISHED 版本会进入正常检索。
        </Typography.Text>
      </Card>

      <Modal
        title="上传新版本"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={() => upload.mutate()}
        confirmLoading={upload.isPending}
        okButtonProps={{ disabled: !fileList.length }}
        destroyOnHidden
      >
        <Upload.Dragger
          accept=".pdf,.docx,.md,.txt,.html"
          maxCount={1}
          fileList={fileList}
          beforeUpload={(file) => {
            if (file.size > 20 * 1024 * 1024) {
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
          <Typography.Text type="secondary">新版本会重新进入解析、切块和索引流程</Typography.Text>
        </Upload.Dragger>
      </Modal>
    </div>
  );
}
