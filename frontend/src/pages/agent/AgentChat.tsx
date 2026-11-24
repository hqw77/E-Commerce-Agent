import { RobotOutlined, SendOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, App, Avatar, Button, Input, Spin, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { chat, confirmAction } from '../../api/agent';
import type { ChatResponse, PendingAction, Source } from '../../types/agent';
import { errorMessage } from '../../utils/error';
import { formatDate } from '../../utils/format';
import { PendingActionCard } from './PendingActionCard';
import { SourceList } from './SourceList';

interface ChatItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string;
  sources?: Source[];
  pendingAction?: PendingAction | null;
  confirmationResult?: string;
  traceId?: string | null;
}

const quickPrompts = [
  '查询最近的订单',
  '换货需要满足什么条件？',
  '帮我取消未发货订单',
  '查询我的售后记录',
];

export function AgentChatPage() {
  const { message, modal } = App.useApp();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const conversationRef = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items]);

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    const userItem: ChatItem = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    };
    setItems((current) => [...current, userItem]);
    setInput('');
    setSending(true);
    try {
      const response: ChatResponse = await chat({
        message: content,
        conversation_id: conversationRef.current,
      });
      conversationRef.current = response.conversation_id;
      setItems((current) => [
        ...current,
        {
          id: response.message_id,
          role: 'assistant',
          content: response.answer,
          createdAt: response.created_at,
          sources: response.sources,
          pendingAction: response.pending_action,
          traceId: response.trace_id,
        },
      ]);
    } catch (error) {
      message.error(errorMessage(error));
      setItems((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: errorMessage(error),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  function askConfirm(item: ChatItem) {
    const pending = item.pendingAction;
    if (!pending) return;
    modal.confirm({
      title: pending.title,
      content: (
        <div>
          <p>{pending.summary}</p>
          <p>业务编号：{pending.resource_no}</p>
          <p>影响：{pending.effect}</p>
          <p>有效期至：{formatDate(pending.expires_at)}</p>
          <Typography.Text type="secondary">
            确认后由后端一次性消费凭证并重新执行业务校验。
          </Typography.Text>
        </div>
      ),
      okText: '确认执行',
      cancelText: '暂不操作',
      onOk: async () => {
        setConfirming(item.id);
        try {
          const result = await confirmAction(pending.confirmation_id, {
            conversation_id: pending.conversation_id,
            nonce: pending.nonce,
          });
          setItems((current) =>
            current.map((entry) =>
              entry.id === item.id
                ? {
                    ...entry,
                    pendingAction: null,
                    confirmationResult: `${result.message}（${result.status}）`,
                  }
                : entry,
            ),
          );
          message.success(result.message);
        } catch (error) {
          message.error(errorMessage(error));
        } finally {
          setConfirming(null);
        }
      },
    });
  }

  return (
    <div className="agent-shell">
      <aside className="agent-sidebar">
        <div>
          <Typography.Text className="eyebrow">LANGGRAPH AGENT</Typography.Text>
          <Typography.Title level={3}>业务对话</Typography.Title>
          <Typography.Paragraph type="secondary">
            普通对话、RAG 知识、业务查询和受控写操作。
          </Typography.Paragraph>
        </div>
        <Button
          block
          onClick={() => {
            conversationRef.current = null;
            setItems([]);
            setInput('');
          }}
        >
          新建会话
        </Button>
        <div className="quick-prompts">
          <Typography.Text type="secondary">快捷提问</Typography.Text>
          {quickPrompts.map((prompt) => (
            <Button key={prompt} type="text" onClick={() => void send(prompt)} disabled={sending}>
              {prompt}
            </Button>
          ))}
        </div>
        <Typography.Text type="secondary" className="agent-note">
          Agent 不直接访问数据库；订单取消与售后申请必须经过独立确认接口。
        </Typography.Text>
      </aside>

      <section className="agent-main">
        <div className="chat-scroll">
          {!items.length ? (
            <div className="agent-empty">
              <RobotOutlined />
              <Typography.Title level={4}>从一个真实业务问题开始</Typography.Title>
              <Typography.Paragraph type="secondary">
                例如：查询我的订单、退款条件是什么，或准备取消一个待支付订单。
              </Typography.Paragraph>
            </div>
          ) : (
            items.map((item) => (
              <div key={item.id} className={`chat-row ${item.role}`}>
                <Avatar
                  icon={item.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  className="chat-avatar"
                />
                <div className="chat-bubble">
                  <div className="chat-meta">
                    <Typography.Text strong>{item.role === 'user' ? '你' : 'E-Commerce Agent'}</Typography.Text>
                    {item.createdAt ? (
                      <Typography.Text type="secondary">{formatDate(item.createdAt)}</Typography.Text>
                    ) : null}
                  </div>
                  <Typography.Paragraph className="chat-answer">{item.content}</Typography.Paragraph>
                  {item.traceId ? (
                    <Typography.Text type="secondary" className="agent-trace-link">
                      trace: <Link to={`/agent/debug?trace_id=${item.traceId}`}>{item.traceId}</Link>
                    </Typography.Text>
                  ) : null}
                  {item.sources?.length ? <SourceList sources={item.sources} /> : null}
                  {item.pendingAction ? (
                    <PendingActionCard
                      action={item.pendingAction}
                      confirming={confirming === item.id}
                      onConfirm={() => askConfirm(item)}
                      onDismiss={() =>
                        setItems((current) =>
                          current.map((entry) =>
                            entry.id === item.id
                              ? { ...entry, pendingAction: null }
                              : entry,
                          ),
                        )
                      }
                    />
                  ) : null}
                  {item.confirmationResult ? (
                    <Alert
                      type="success"
                      showIcon
                      message={item.confirmationResult}
                      description="结果来自后端 Confirm API；前端未自行修改业务状态。"
                    />
                  ) : null}
                </div>
              </div>
            ))
          )}
          {sending ? (
            <div className="chat-row assistant">
              <Avatar icon={<RobotOutlined />} className="chat-avatar" />
              <div className="chat-bubble">
                <Spin size="small" /> <Typography.Text type="secondary">Agent 正在执行…</Typography.Text>
              </div>
            </div>
          ) : null}
          <div ref={endRef} />
        </div>

        <div className="chat-composer">
          <Input.TextArea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入问题，Enter 发送，Shift + Enter 换行"
            autoSize={{ minRows: 2, maxRows: 6 }}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            disabled={sending}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={sending}
            onClick={() => void send()}
            disabled={!input.trim()}
          >
            发送
          </Button>
        </div>
      </section>
    </div>
  );
}
