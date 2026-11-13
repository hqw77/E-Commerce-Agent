# TASK-004 支付宝沙箱真实联调准备

> 状态记录
> TASK-004：代码与自动化验收通过，支付宝沙箱真实 E2E 待完成。
> 当前阶段只做沙箱联调准备，不扩展订单、库存、MOCK 支付和售后主流程。

## 1. 当前基线

- 设计冻结：`f268e76`
- 代码分支：`feature/task-004-order`
- 当前自动化验收：259 个测试通过
- 当前支付实现：
  - MOCK 支付：已通过自动化测试
  - 支付宝：RSA2 参数生成、验签、查询、关闭适配器已实现
  - 支付宝真实异步通知、沙箱页支付、真实退款：尚未做 E2E

当前项目**没有安装官方支付宝 Python SDK**。支付宝部分使用内部 `AlipayClient`：

- Python 3.12.10；
- `cryptography==50.0.2`；
- `httpx==0.28.1`；
- RSA2 签名/验签与单元测试已通过。

因此：

```text
当前内部适配器在 Python 3.12 下已验证
官方 alipay-sdk-python 在 Python 3.12 下的兼容性尚未验证
```

PyPI 上 `alipay-sdk-python` 的元数据没有声明 `Requires-Python`，分类器仍停留在较早的 Python 版本。若必须使用官方 SDK，需要单独做兼容性验证和依赖固定，不能直接声称 3.12 已兼容。

---

## 2. 用户需要准备的沙箱信息

在开始真实 E2E 前，请准备以下内容。**不要把任何密钥发到聊天、Issue、提交记录或截图中。**

### 2.1 支付宝开放平台沙箱应用

- 沙箱 APPID；
- 沙箱卖家 ID（seller_id / PID，建议提供）；
- 应用私钥（RSA2 private key）；
- 支付宝公钥（Alipay public key）；
- 沙箱买家账号；
- 沙箱登录密码或可用的沙箱买家登录方式。

### 2.2 公网回调地址

支付宝异步通知必须能从公网访问，不能使用：

```text
http://127.0.0.1:8000
http://localhost:8000
```

需要准备以下之一：

1. 一台有公网 HTTPS 域名的服务器；
2. Cloudflare Tunnel、ngrok、localtunnel 等临时 HTTPS 隧道；
3. 公司/学校提供的公网反向代理。

最终需要两个 HTTPS 地址：

```text
https://<public-host>/api/v1/payments/alipay/notify
https://<public-host>/api/v1/payments/alipay/return
```

可选前端回跳地址：

```text
https://<frontend-host>/payment/result
```

### 2.3 环境确认

- 本机或服务器可以运行 FastAPI；
- MySQL 8 和 Redis 7 可连接；
- Alembic 已升级到 head；
- 端口 8000 可被隧道或反向代理访问；
- 防火墙允许隧道出站。

---

## 3. 配置项

在本地 `.env` 或部署环境变量中配置，**不要提交 `.env`**。

```env
APP_ENV=development

ALIPAY_APP_ID=<sandbox-app-id>
ALIPAY_SELLER_ID=<sandbox-seller-id>
ALIPAY_PRIVATE_KEY=<application-private-key-pem>
ALIPAY_PUBLIC_KEY=<alipay-public-key-pem>

ALIPAY_GATEWAY=https://openapi.alipaydev.com/gateway.do

ALIPAY_NOTIFY_URL=https://<public-host>/api/v1/payments/alipay/notify
ALIPAY_RETURN_URL=https://<public-host>/api/v1/payments/alipay/return
ALIPAY_FRONTEND_RETURN_URL=https://<frontend-host>/payment/result
```

说明：

- `ALIPAY_PRIVATE_KEY` 是应用私钥，不是支付宝公钥；
- `ALIPAY_PUBLIC_KEY` 是支付宝公钥，不是应用公钥；
- 仅支持公钥模式，当前未实现公钥证书模式；
- `ALIPAY_SELLER_ID` 建议配置，代码会校验通知中的 seller_id；
- `ALIPAY_FRONTEND_RETURN_URL` 可为空；
- 私钥和公钥使用 PEM 格式；
- 环境变量中的多行 PEM 必须确保实际换行符正确，不能把字面量 `\n` 直接交给加密库。

`.env` 已被 `.gitignore` 忽略：

```text
.gitignore: .env
.gitignore: .env.*
.gitignore: !.env.example
```

`.env.example` 只保留空占位，不包含真实密钥。

---

## 4. 启动与公网检查

### 4.1 启动服务

```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health/live
```

### 4.2 启动隧道示例

Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

或 ngrok：

```bash
ngrok http 8000
```

把隧道分配的 HTTPS 域名填入：

```text
ALIPAY_NOTIFY_URL=https://<tunnel-host>/api/v1/payments/alipay/notify
ALIPAY_RETURN_URL=https://<tunnel-host>/api/v1/payments/alipay/return
```

### 4.3 公网回调预检

必须确认：

```bash
curl -i https://<public-host>/api/v1/health/live
```

返回 200，并且支付宝服务器能够访问该域名。

注意：

- 支付宝通知是 `POST` 表单请求；
- 通知路由不能要求 Bearer Token；
- 不要在反向代理层启用会拦截 POST 表单的 WAF 规则；
- 不要把 `return_url` 当作支付成功依据。

---

## 5. 沙箱 E2E 验收流程

### 5.1 准备商品和库存

1. 创建分类；
2. 创建 ACTIVE 商品；
3. 创建 ACTIVE SKU；
4. 初始化库存；
5. 确认商品和 SKU 可购买。

建议使用最小金额：

```text
0.01 或 1.00 CNY
```

只使用沙箱买家账号，不进行真实资金交易。

### 5.2 创建订单和支付宝支付单

1. 登录普通用户；
2. 调用创建订单；
3. 调用创建支付宝支付单；
4. 获取 `pay_url`；
5. 在沙箱买家环境打开 `pay_url`；
6. 使用沙箱买家完成支付。

### 5.3 异步通知验收

检查服务端日志和数据库：

- 收到 `POST /api/v1/payments/alipay/notify`；
- 签名验证通过；
- `app_id` 匹配；
- `seller_id` 匹配；
- `out_trade_no` 匹配支付单；
- `total_amount` 与支付金额一致；
- `trade_status` 为 `TRADE_SUCCESS` 或 `TRADE_FINISHED`；
- 支付单变为 `SUCCESS`；
- 订单变为 `PAID`；
- 预占库存转换为 `RESERVED_OUTBOUND`；
- 返回纯文本 `success`。

### 5.4 重复通知幂等

对同一支付单重复发送相同通知：

- 返回 `success`；
- 不重复扣库存；
- 不重复改变订单状态；
- 不产生第二条支付成功流水。

### 5.5 金额和签名失败

构造以下失败场景：

- 篡改 `total_amount`；
- 篡改 `out_trade_no`；
- 使用错误签名；
- 使用错误 `app_id`；
- 使用错误 `seller_id`。

预期：

- 返回 `failure` 或 400；
- 支付单不变；
- 订单不变；
- 不扣库存；
- 记录告警日志。

### 5.6 支付查询

管理员调用：

```text
POST /api/v1/admin/payments/{payment_no}/sync
```

预期：

- 调用 `alipay.trade.query`；
- 只有可信 `TRADE_SUCCESS` / `TRADE_FINISHED` 才更新支付状态；
- 查询结果和本地状态最终一致。

### 5.7 支付关闭

取消一个未支付订单：

- 本地订单变为 `CANCELLED`；
- 库存预占释放；
- 本地支付单变为 `CLOSED`；
- 尽力调用 `alipay.trade.close`；
- 支付宝侧交易关闭；
- 关闭失败只记录日志，不回滚本地取消。

### 5.8 晚到支付

在订单取消/关闭后，用沙箱完成支付：

- 支付单记录 `SUCCESS`；
- `exception_reason=LATE_PAYMENT`；
- 订单业务状态保持 `CANCELLED`/`CLOSED`；
- 订单 `payment_status=PAID`；
- 不恢复订单、不重新预占、不扣库存；
- 管理员手动退款；
- 退款成功不回补库存。

### 5.9 return_url

访问同步跳回地址：

```text
GET /api/v1/payments/alipay/return
```

预期：

- 只做页面跳转；
- 不改变订单或支付状态；
- 不把 GET 参数当作支付成功依据。

### 5.10 全额退款

第一版设计要求支付宝沙箱验证全额退款。

当前代码状态：

```text
支付宝退款记录可以创建为 PENDING/PROCESSING
尚未在 RefundService 中接入真实 alipay.trade.refund 网络调用
```

因此真实沙箱全额退款 E2E **目前不能直接通过**。在开始此步骤前，需要：

1. 实现 `alipay.trade.refund` 调用；
2. 使用稳定 `out_request_no`；
3. 校验 `fund_change=Y`，不能只看 `code=10000`；
4. 结果未知时先查询，不创建新退款单；
5. 退款成功后更新支付/订单/售后状态；
6. 保持 MOCK 退款作为自动化测试路径。

在上述实现完成前，不得宣称支付宝全额退款 E2E 通过。

---

## 6. 当前实现与联调风险

### 已实现

- `alipay.trade.page.pay` 参数与 URL；
- RSA2 签名；
- 异步通知验签；
- app_id / seller_id 校验；
- 金额和支付单号校验；
- `alipay.trade.query`；
- `alipay.trade.close`；
- `return_url` 页面；
- MOCK 支付自动化测试。

### 尚未完成

- 真实沙箱页支付；
- 真实异步通知；
- 真实查询/关闭 E2E；
- 官方 SDK 在 Python 3.12 下的兼容性验证；
- `alipay.trade.refund` 调用和真实全额退款 E2E；
- 公网 HTTPS 回调地址。

### 风险

- 内部 RSA2 适配器与官方 SDK 的编码/签名细节可能存在差异；
- 沙箱异步通知要求公网可达；
- 私钥/公钥格式错误会导致签名失败；
- 若使用反代，必须保留原始 POST 表单；
- 退款未知状态只能人工核查，不能自动新建退款单。

---

## 7. 开始联调前需要用户确认

请提供或确认：

1. 沙箱 APPID；
2. 沙箱 seller_id；
3. 应用私钥是否已生成并妥善保管；
4. 支付宝公钥是否已获取；
5. 沙箱买家账号是否可用；
6. 公网 HTTPS 地址或隧道方案；
7. `ALIPAY_NOTIFY_URL`；
8. `ALIPAY_RETURN_URL`；
9. 是否接受当前内部 RSA2 适配器，还是必须改用官方 SDK；
10. 是否同意先补 `alipay.trade.refund`，再进行全额退款 E2E。

在以上信息确认前，不进行真实沙箱调用，不伪造通过结果。

---

## 8. 安全边界

- 只使用支付宝沙箱，不连接生产网关；
- 不使用真实资金；
- 不提交 `.env`、私钥、公钥证书、沙箱账号密码；
- 不在日志中打印完整私钥、签名原文或买家凭证；
- 不把沙箱密钥写入代码、测试快照或 Git 历史；
- 如密钥已泄露，先在开放平台重置，再继续联调。
