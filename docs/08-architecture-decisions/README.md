# 08 架构决策

## ADR-001: Agent 不直接访问数据库

- 状态: 已采纳
- 原因: 防止 LLM 绕过权限、状态机和事务。
- 实现: Agent → Tool/Prepare → Backend Service → Repository → DB。
- 取舍: 多一层调用, 但安全边界清晰。

## ADR-002: Prepare/Confirm 独立于 LangGraph

- 状态: 已采纳
- 原因: LLM 只能准备, 不能确认自己的动作。
- 实现: Redis PREPARED + nonce + params_hash + TTL; 独立 Confirm API; Lua 原子消费。
- 取舍: 用户多一步确认, 但避免模型直接写业务。

## ADR-003: MySQL 是 RAG 权威, Qdrant 只是索引

- 状态: 已采纳
- 原因: 需要 ACL、版本、Source 和 stale point 校验。
- 实现: MySQL 发布版本/Chunk + Qdrant 向量 + MySQL 回查。
- 取舍: 多一次 DB 校验, 换取一致性和权限安全。

## ADR-004: RAG 无答案策略放在 Agent 边界

- 状态: 已采纳
- 原因: `/knowledge/retrieve` 仍需要保留原始 Top-K 供调试。
- 实现: `agent/rag_evidence.py`; 低分和低证据不生成。
- 限制: 阈值是离线候选, 不是生产认证。

## ADR-005: Trace 采用日志 + 进程内 Buffer

- 状态: 已采纳, 有明确限制
- 原因: 本地项目不引入新存储基础设施。
- 实现: structlog + `TraceBuffer` + Debug API。
- 限制: 重启丢失, 多 Worker 不共享, 不是审计系统。

## ADR-006: 暂不实现 HITL

- 状态: 暂缓
- 原因: 需要独立审批表、任务分配、审计和权限模型。
- 影响: 当前只有用户 Confirm, 没有人工审批流。

## ADR-007: 支付业务从当前范围移除

- 状态: 已采纳
- 原因: 支付/支付宝/退款带来外部依赖、测试和数据库收尾复杂度, 不符合当前求职作品定位。
- 决策: 删除支付/退款运行时 API、Service、Tool 和前端入口。
- 兼容: payments/refunds 表和支付字段保留, 历史数据可读。
- 售后: 只保留 EXCHANGE, 不再执行任何资金退款。

## ADR-008: 3306/3307 数据分叉

- 状态: 待确认
- 事实: 3306 为空, 3307 有 TASK-015/020.A 测试数据。
- 默认: 本地演示使用 3307; 3306 保留, 不覆盖 3307。

## ADR-009: 订单以 CREATED 为起点

- 状态: 已采纳
- 原因: 去掉支付后, 订单不能以 PENDING_PAYMENT/PAID 作为新数据起点。
- 实现: 创建即 CREATED; 取消释放预占; 发货扣减; 送达/完成。
- 兼容: 旧 PAID 订单可读取并允许兼容发货。
