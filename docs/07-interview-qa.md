# 07 面试问答

## 1. 30 秒介绍

这是一个双端电商智能体 MVP：消费者端可以浏览商品、立即购买、查看订单和申请换货；运营端负责商品、库存、订单和售后。认证使用 Access Token + RBAC，AI 导购通过 LangGraph 调用真实商品和订单工具，取消订单和换货必须经过 Prepare/Confirm，库存调整必须管理员审批。

## 2. 1 分钟介绍

项目后端是 FastAPI + 异步 SQLAlchemy，前端是 React + TypeScript。认证是简化版 Access Token，后端用 CurrentUser / CurrentAdmin / CurrentDebugger 做 RBAC。业务侧有商品、SKU、库存、订单和只支持换货的售后。订单创建会预占库存，取消释放，发货扣减。AI 侧用 LangGraph 做五类路由；工具有 READ 和 PREPARE 两种，用户 PREPARE 写 Redis pending，管理员库存调整写 MySQL 审批记录和 Redis pending；真正执行走 Confirm 或管理员审批，nonce 和参数 hash 由 Lua 原子消费。RAG 使用 BGE-M3 + Qdrant，但 MySQL 是 Chunk、版本和权限权威源。

## 3. 为什么做双端

只做运营后台无法体现 AI 导购价值；只做聊天机器人又没有真实业务闭环。双端可以形成“浏览商品→问 AI→下单→管理员履约→申请售后”的完整故事。

## 4. 为什么不用微服务

当前是本地面试项目，单体 FastAPI 足够，事务边界清晰。微服务会引入服务发现、分布式事务和部署复杂度，不符合当前目标。

## 5. 为什么用 FastAPI

- 类型友好；
- Pydantic 校验；
- 原生 OpenAPI/Swagger；
- 异步生态适合 SQLAlchemy/Redis/Qdrant；
- 依赖注入适合 CurrentUser/CurrentAdmin。

## 6. 为什么 Session/Context 分开

`AgentState` 要可序列化，不能放 `AsyncSession`、`User` 这类对象。`AgentRuntimeContext` 保存可信依赖，避免 State 被持久化或重放时携带数据库对象。

## 7. Agent 如何避免越权

- Tool Registry 白名单；
- Tool 调用 Service，不直接 SQL；
- 用户身份来自后端 CurrentUser；
- PREPARE 只生成 pending；
- Confirm 重新校验用户、会话、nonce、参数 hash；
- 管理端接口使用 CurrentAdmin。

## 8. 为什么 PREPARE 不直接执行

LLM 不应直接决定取消订单或创建售后。PREPARE 只记录意图，用户确认后再执行，避免模型误解、重放和越权。

## 9. Confirm 如何防止重复消费

Redis 中保存 pending，Lua 脚本一次性校验并删除记录。nonce、用户、会话、参数 hash、TTL 不匹配都会失败。

## 10. 订单和库存如何保持一致

创建订单在同一事务中预占库存；取消释放；发货把预占转为实际扣减。状态和库存都由 Service 推进，前端不能直接改。

## 11. 为什么订单状态和履约状态分开

订单主状态表达业务生命周期，履约状态表达物流进度。发货后订单可能仍是 `CREATED`，但履约状态为 `SHIPPED`。这样能支持取消、发货、送达、完成的独立规则。

## 12. 为什么新订单号格式不统一

历史演示订单使用 `ORD-2026-001`，新订单由 `OrderService` 生成时间戳+随机串。生产化应统一为可读序列或带业务前缀的编号，并处理并发。

## 13. 为什么售后只支持 EXCHANGE

支付和资金退款已下线；没有支付基础就不应该继续引入退款。换货仍然能形成完整售后闭环。

## 14. 为什么用户看不到申请换货

只有订单履约状态为 `DELIVERED` 或 `COMPLETED` 才允许申请。未发货时页面会显示禁用按钮和提示。

## 15. RAG 如何做权限

检索前先查 MySQL 中用户可见的已发布版本，再用 Qdrant 的 `version_id` 过滤。Qdrant 返回后还要回 MySQL 校验 Chunk，避免越权和 stale point。

## 16. 为什么 Qdrant 不是权威源

Qdrant 只负责向量召回。Chunk 正文、版本、ACL 和发布状态都在 MySQL。检索结果必须回查 MySQL。

## 17. 无答案策略怎么实现

`agent/rag_evidence.py` 根据 top score 和中文 bigram 证据覆盖判断：

```text
< 0.60 → LOW_SCORE
0.60–0.625 且 coverage < 0.50 → LOW_EVIDENCE
其他 → ACCEPTED
```

## 18. Trace 有什么价值

记录请求、路由、工具、RAG、输出校验和错误，并做脱敏。当前是进程内 TraceBuffer，重启丢失，不是审计存储；生产化应接入日志平台或独立存储。

## 19. 测试如何避免污染开发库

根 `conftest.py` 强制测试库 `ecommerce_agent_test`、Redis DB 15、独立 Qdrant Collection 和测试 storage，并校验实际数据库/Grants。

## 20. 当前最大的限制

```text
没有购物车和支付
没有生产部署
Trace 不持久化
RAG 评测样本小
同一个标签页只能保留一个登录身份，多标签页可以分别登录
```

面试时应主动说明边界，不把“未实现”讲成“已完成”。

## 21. 如果继续做，优先做什么

1. 固化演示数据和演示脚本；
2. 统一订单编号策略；
3. 补管理员操作 E2E；
4. 拆分 shop/admin 子域名；
5. 再做生产部署、监控和备份。
