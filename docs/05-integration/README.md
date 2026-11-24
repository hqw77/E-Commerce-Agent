# 05 前后端集成

## 契约

前端通过 `frontend/src/api/client.ts` 统一请求后端 `/api/v1`。认证 Token 注入和 401 刷新在 client/authStore 中处理。

## 主要接口

| 功能 | 方法/路径 |
|---|---|
| 注册 | `POST /auth/register` |
| 登录 | `POST /auth/login` |
| 刷新 | `POST /auth/refresh` |
| 当前用户 | `GET /auth/me` |
| 退出 | `POST /auth/logout` |
| 商品 | `/admin/products` |
| 分类 | `/admin/categories` |
| SKU | `/admin/skus` |
| 库存 | `/admin/inventory` |
| 订单 | `/orders`, `/admin/orders` |
| 售后 | `/after-sales` |
| 知识库 | `/knowledge` |
| Agent | `/agent/chat` |
| Confirm | `/agent/actions/{id}/confirm` |
| Trace | `/agent/runs/{trace_id}` |

支付和退款接口已从当前 API 中移除。

## Agent 契约

`POST /agent/chat`:

```json
{
  "message": "查询我的订单",
  "conversation_id": null
}
```

响应:

```json
{
  "conversation_id": "...",
  "message_id": "...",
  "answer": "...",
  "sources": [],
  "pending_action": null,
  "created_at": "...",
  "trace_id": "..."
}
```

PendingAction 必须通过独立 Confirm API 执行:

```text
POST /agent/actions/{confirmation_id}/confirm
{ conversation_id, nonce }
```

## 错误约定

后端统一返回:

```json
{
  "success": false,
  "code": "ERROR_CODE",
  "message": "...",
  "details": null
}
```

前端不根据文本判断业务成功, 只看 HTTP 状态和稳定 code。

## 集成边界

- 前端不判断支付成功; 当前已无支付入口;
- 前端不判断售后审核结果;- 前端不自行取消订单, 只调用 Confirm API;
- Source 由后端构造;
- 所有用户身份由后端 CurrentUser 提供。
