# E-Commerce Agent Frontend

TASK-008～013 的 React 管理后台，直接连接现有 FastAPI 后端。

## 启动

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

默认地址：`http://127.0.0.1:5173`。

## 环境变量

```env
VITE_API_BASE_URL=/api/v1
```

只允许公开配置。不要把 DeepSeek Key、MySQL/Redis 密码、JWT Secret 或支付私钥写入前端环境变量。

默认使用相对路径 `/api/v1`，由 Vite 代理到 `http://127.0.0.1:8000`。当前 FastAPI 未配置 CORS 中间件，因此开发环境不要改成绝对跨域 URL；生产环境应由 Nginx 同源反向代理 `/api`。

## 质量检查

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

Windows 环境如遇到 esbuild 临时目录权限错误，可将 `TEMP`/`TMP` 指向项目内可写目录后再构建。

## 认证和 Token

后端返回 JSON Access/Refresh Token，前端存储在 `localStorage`：

- `ecommerce_agent_access_token`
- `ecommerce_agent_refresh_token`

401 时使用共享 Refresh Promise 协调并发刷新，避免多个请求同时消费 Refresh Token Rotation。Refresh 失败会清除 Token 并回到登录页。

`localStorage` 方案意味着 XSS 可读取 Token；本项目依赖 React 默认转义、无 `dangerouslySetInnerHTML` 和受限 Markdown 展示降低风险，生产环境建议评估 HttpOnly Cookie + CSRF 防护。

## 页面

- `/login`、`/register`
- `/dashboard`
- `/products`、`/products/:productId`
- `/inventory`、`/inventory/transactions`
- `/orders`、`/orders/:orderNo`
- `/after-sales`、`/after-sales/:afterSalesNo`
- `/knowledge`、`/knowledge/:documentId`
- `/agent`

管理员页面依赖后端 `CurrentAdmin`。`GET /auth/me` 当前不返回 `is_admin`，因此前端不伪造角色；非管理员访问会看到后端 403 提示。

Agent 页面不实现 SSE/WebSocket，Confirm 严格提交：

```json
{
  "conversation_id": "uuid",
  "nonce": "opaque-nonce"
}
```

不提交订单号、SKU、金额或售后类型，这些参数已绑定在 Redis confirmation 中。
