# E-Commerce Agent 项目文档中心

> 项目定位: 本地完成度较高的全栈电商 AI Agent 工程实践项目。  
> 当前基线: `main` / `c732cc1`。  
> 当前阶段: TASK-023-FINAL 本地收尾。

## 快速入口

- [项目总览](00-project-overview/README.md)
- [前端架构](01-frontend/README.md)
- [后端架构](02-backend/README.md)
- [Agent 架构](03-agent/README.md)
- [公共环境](04-common/README.md)
- [前后端集成](05-integration/README.md)
- [测试与验收](06-testing/README.md)
- [项目管理](07-project-management/README.md)
- [架构决策](08-architecture-decisions/README.md)
- [历史归档](09-archive/README.md)
- [学习资料](10-learning/README.md)

## 项目能力

- 本地电商业务: 认证、商品、SKU、库存、订单、MOCK 支付、退款、售后、知识库。
- Agent: GENERAL、RAG、TOOL、WORKFLOW、UNSUPPORTED 五路路由。
- 安全: READ Tool 与 PREPARE Tool 分离, 独立 Confirm API, ACL, Source 服务端构造, Prompt Injection signal, Trace 脱敏。
- RAG: BGE-M3、Qdrant、MySQL 权威 Chunk、PUBLIC/ADMIN_ONLY、无答案策略。
- 前端: React 管理后台和 Agent 聊天。

## 当前状态边界

```text
已完成: TASK-001～016 本地业务与基础部署资料
已完成: TASK-019/020/020.A Agent 架构与 E2E
已完成: TASK-021.0/021.1
待人工验收: TASK-021.2
暂缓: TASK-017/018
未开始/范围待定义: TASK-021.3、TASK-022
```

## 文档原则

1. 当前说明以源码和本轮测试为准。
2. 历史 TASK 报告不删除、不改写, 由 [历史归档](09-archive/README.md) 建立来源索引。
3. 未验证的测试和环境状态必须明确标注。
4. 不把本地 MOCK 支付描述为真实支付宝联调。
5. 不把 TASK-021.2 的离线小样本指标描述为生产认证。
