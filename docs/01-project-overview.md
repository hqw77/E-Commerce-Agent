# 01 项目总览

## 1. 项目定位

清风数码是一个双端电商智能体项目：

```text
消费者商城
+
AI 导购 / 客服
+
运营管理后台
```

它的目标不是做一个大而全的电商平台，而是回答一个工程问题：

> 大模型如何在真实商品、库存、订单、售后和权限边界内安全工作？

项目用真实业务表、真实库存扣减、订单状态机、Prepare/Confirm 和 RAG 来验证这个问题。

## 2. 双端结构

### 消费者端

```text
/shop                      商城首页
/shop/products/:productNo  商品详情
/shop/assistant            AI 导购
/shop/orders               我的订单
/shop/orders/:orderNo      订单详情
/shop/after-sales          我的售后
/shop/after-sales/:no      售后详情
```

### 运营端

```text
/dashboard       工作台
/products        商品管理
/inventory       库存管理
/orders          订单管理
/after-sales     售后管理
/knowledge       知识库
/agent           AI 助手
/agent/approvals Agent 审批中心
```

### Agent 调试端

```text
/agent/debug      Agent Trace
/agent/debug/chat 调试对话
/agent/debug/rag  RAG 检索诊断
```

## 3. 角色

```text
游客      浏览商城、查看商品
普通用户  商城、立即购买、我的订单、我的售后、AI 导购
管理员    运营后台，也可以进入商城
调试人员  Agent Trace、调试对话、RAG 检索诊断
```

登录只有一个页面，由后端 `is_admin` / `is_debugger` 决定跳转：

```text
普通用户 → /shop
管理员   → /dashboard
调试人员 → /agent/debug
```

普通用户访问运营后台会被重定向回商城。

## 4. 已完成功能

### 商品与库存

- 商品、分类、SKU；
- 本地商品图片；
- 商品编号 P001–P010；
- 库存初始化、入库、调整、流水；
- 订单创建预占、取消释放、发货扣减。

### 订单

- 消费者立即购买；
- 消费者查看自己的订单；
- 取消未发货订单；
- 管理员发货、标记送达、完成；
- 订单状态为 `CREATED`、`CANCELLED`、`COMPLETED`，履约状态独立。

### 售后

- 当前仅支持 `EXCHANGE`；
- 用户申请换货；
- 管理员审核通过/拒绝；
- 用户填写退货物流；
- 管理员确认收货；
- 管理员完成换货补发。

### AI Agent

- LangGraph 状态图；
- 商品、SKU、库存、订单、售后工具；
- READ / PREPARE 分离；
- Redis Prepare / 独立 Confirm；
- 管理员库存调整 HITL 审批；
- RAG 知识问答；
- Safety、Trace、Debug Console。

## 5. 明确不做

```text
购物车
支付
资金退款
优惠券
会员体系
多商家
生产级图片上传
云部署
```

这些是当前版本的边界，不应在面试中说成“已经完成”。

## 6. 技术栈

```text
后端       Python 3.12, FastAPI, Pydantic v2, 异步 SQLAlchemy
数据       MySQL 8, Redis 7, Qdrant
Agent      LangGraph, LangChain Core, langchain-openai, DeepSeek
RAG        BAAI/bge-m3, sentence-transformers, Qdrant
前端       React 18, TypeScript, Vite, Ant Design, TanStack Query
测试       Pytest, Vitest, Playwright
工程       Alembic, Ruff, Mypy, Docker Compose
```

## 7. 当前数据

```text
商品：10
SKU：10
分类：4
订单：12
售后：4
知识文档：7
```

其中包含管理员演示订单、普通用户实际下单和普通用户换货售后；知识库包含 6 篇政策/说明文档和 1 篇历史测试文档。

## 8. 面试时最值得讲的点

1. 双端角色分流；
2. 订单与库存一致性；
3. Agent 工具边界和 Prepare/Confirm；
4. RAG 的 ACL、MySQL 权威回查和无答案策略；
5. 前后端完整售后闭环；
6. 测试隔离和真实业务数据保护。
