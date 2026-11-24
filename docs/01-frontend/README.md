# 01 前端

## 职责

React 管理后台和 Agent 聊天界面。前端只负责展示和调用 API, 不自行判断支付成功、库存权限或售后审核结果。

## 目录

```text
frontend/src/
├─ api/          后端请求
├─ components/   通用组件
├─ hooks/        React hooks
├─ layouts/      AdminLayout/AuthLayout
├─ pages/        页面
├─ router/       ProtectedRoute
├─ stores/       authStore
├─ types/        API 类型
└─ utils/        token/format/error
```

## 路由

```text
/login
/register
/dashboard
/products
/products/:productId
/categories
/inventory
/inventory/transactions
/orders
/orders/:orderNo
/after-sales
/after-sales/:afterSalesNo
/knowledge
/knowledge/:documentId
/agent
```

路由定义在 `frontend/src/App.tsx`。

## 页面职责

| 页面 | 路径 | 说明 |
|---|---|---|
| 登录/注册 | `pages/auth/` | 认证表单 |
| Dashboard | `pages/dashboard/` | 总览 |
| 商品 | `pages/products/` | 商品和 SKU |
| 分类 | `pages/categories/` | 分类树 |
| 库存 | `pages/inventory/` | 库存、入库、调整、流水 |
| 订单 | `pages/orders/` | 订单列表和详情 |
| 售后 | `pages/after-sales/` | 售后列表和只读详情 |
| 知识库 | `pages/knowledge/` | 上传、发布、检索 |
| Agent | `pages/agent/` | 聊天、Source、PendingAction、Confirm |

## Agent 前端

```text
AgentChat.tsx       消息列表、输入、Source、PendingAction、Confirm
PendingActionCard.tsx 展示待确认动作
SourceList.tsx      展示 RAG Source
api/agent.ts        chat/confirmAction
types/agent.ts      ChatResponse/Source/PendingAction
```

当前已有:

- Chat 请求;
- Source 展示;
- PendingAction 展示;
- Confirm 调用;
- 确认结果展示。

当前缺少:

- 售后审核/换货管理 UI（当前只读；支付/退款 UI 已随支付下线移除）。

已补齐:

- `trace_id` 类型和展示;
- Trace Console (`/agent/debug`);
- 订单 CREATED/履约状态展示。

## 认证

`stores/authStore.ts`, `utils/token.ts`, `api/client.ts` 负责:

- Access Token 注入;
- Refresh Token 轮换;
- 401 后刷新;
- 退出登录;
- 受保护路由。

## 测试

```text
Vitest: src/components/Common.test.tsx, src/utils/*.test.ts
Playwright: frontend/e2e/*.spec.ts
```
