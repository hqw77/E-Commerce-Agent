# TASK-014 测试数据与清理方案

> 本文件是 TASK-014 的测试数据基线。  
> 不包含真实密钥、默认管理员密码或生产数据。

## 1. 原则

- 使用独立测试账号，不使用现有用户数据。
- 所有测试数据使用可识别前缀 `TASK014-`。
- 测试账号使用运行时随机邮箱和随机密码。
- 管理员账号不写入代码或固定默认值，由测试运行环境注入。
- 清理只按本次创建的资源 ID/编号删除，禁止 `TRUNCATE`、整表清空或删除用户原有数据。
- 不调用真实支付、真实退款或支付宝沙箱；支付状态仅使用 MOCK 支付。
- 不新增数据库 migration。
- 测试完成后清理数据库记录、Redis 会话/确认凭证和临时文件。

## 2. 测试账号

| 账号 | 用途 | 创建方式 |
|---|---|---|
| 管理员 | 分类、商品、库存、知识库、管理端页面 | 测试启动时由 `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` 注入；仅允许测试环境 |
| 用户 A | 普通用户订单、Agent、售后 | 通过 `/auth/register` 随机创建 |
| 用户 B | 用户隔离、越权测试 | 通过 `/auth/register` 随机创建 |

约束：

- `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` 必须有值，不能有默认值。
- 管理员 `is_admin=true` 只通过测试初始化步骤设置；不得新增默认管理员生产代码。
- 测试脚本不得打印密码或 Token。
- 凭据只保存在被 Git 忽略的临时文件或进程环境中。

## 3. 测试数据矩阵

| 资源 | 标识示例 | 用途 | 清理方式 |
|---|---|---|---|
| 用户 A | `TASK014-a-<random>@example.test` | 普通流程 | 按用户 ID 删除 |
| 用户 B | `TASK014-b-<random>@example.test` | 用户隔离 | 按用户 ID 删除 |
| 分类 | `TASK014-CAT-<random>` | 商品分类 | 按 category ID 删除 |
| 商品 | `TASK014-P-<random>` | 商品/SKU/订单 | 按 product ID 删除 |
| SKU | `TASK014-SKU-<random>` | 库存/订单 | 按 SKU ID 删除 |
| 库存 | 对应 SKU | 入库、调整、流水 | 随 SKU 清理 |
| 订单 | `ORD...` | 订单、支付状态、Agent Tool | 按 order ID/order_no 清理 |
| 售后 | `AS...` | 售后列表、详情 | 按 after-sales ID 清理 |
| 知识文档 | `TASK014-KB-<random>` | 上传/索引/发布/检索 | 按 document ID 删除 |
| 知识版本 | 文档版本 ID | 发布/重试 | 随文档清理 |
| Redis 会话 | `agent:*:<user_id>:*` | Agent 多轮 | 按测试用户 ID 清理 |
| Redis 确认 | `agent:action:confirmation:*` | Confirm | 按本次确认 ID 清理 |

## 4. 测试数据初始化顺序

```text
1. 创建随机管理员（由测试环境注入并设置 is_admin）
2. 注册用户 A、用户 B
3. 管理员创建分类
4. 创建商品和 SKU
5. SKU 初始化/入库
6. 用户 A 创建订单
7. 可选：用户 A 创建售后
8. 管理员上传知识文档
9. 等待处理并发布
10. 执行浏览器/API 测试
```

## 5. 清理顺序

```text
1. 清理本次 Agent Redis 会话和确认凭证
2. 删除本次售后
3. 删除本次订单明细、支付、订单
4. 删除本次库存流水、库存、SKU
5. 删除本次商品、分类
6. 删除本次知识文档（软删除由后端处理）
7. 删除本次刷新会话
8. 删除本次用户
9. 删除本次上传的临时文档文件
```

清理只使用本次测试生成的 ID 集合。不得按前缀批量删除用户已有数据，除非该前缀已确认只属于本次运行。

## 6. 知识库测试文件

测试文件放在：

```text
docs/04-testing/TASK-014/fixtures/task014-refund-policy.md
```

内容只用于 RAG 测试，不包含真实密钥、用户隐私或生产数据。

上传要求：

- 通过真实 `/api/v1/knowledge/documents` multipart 接口；
- 管理员权限；
- 状态从 `UPLOADED/PROCESSING` 到 `INDEXED`；
- 发布后状态为 `PUBLISHED`；
- 使用真实 `/api/v1/knowledge/retrieve` 验证来源和片段；
- 检查 `PUBLIC` 和 `ADMIN_ONLY` 的访问边界。

## 7. 支付数据

TASK-014 只验证：

- 订单响应中的 `payment_status`；
- 独立 Payment API 的列表/详情；
- MOCK 支付状态变化。

不验证：

- 支付宝真实沙箱；
- 支付回调签名；
- 退款真实链路。

这些属于 TASK-015。

## 8. 浏览器 E2E 数据注入

Playwright 使用：

```text
E2E_BASE_URL=http://127.0.0.1:5173
E2E_API_BASE_URL=http://127.0.0.1:8000/api/v1
E2E_ADMIN_EMAIL=<runtime>
E2E_ADMIN_PASSWORD=<runtime>
E2E_USER_EMAIL=<runtime>
E2E_USER_PASSWORD=<runtime>
```

这些值只从进程环境或本地未跟踪文件读取。测试报告只记录账号前缀或资源编号，不记录密码和 Token。

## 9. 数据库和迁移

预计不新增 migration。

如果现有表结构无法支持 TASK-014，必须先提交：

```text
问题
影响的 API
最小表结构变更
迁移方案
回滚方案
```

经确认后才允许新增迁移。

## 10. 清理失败处理

如果清理失败：

- 记录残留资源 ID；
- 不执行整库清理；
- 不删除无法确认归属的数据；
- 在下一次测试运行前使用明确 ID 重试清理；
- 在 TASK-014 报告中记录残留项。
