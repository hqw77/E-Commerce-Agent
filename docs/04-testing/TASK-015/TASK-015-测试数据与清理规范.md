# TASK-015 测试数据与清理规范

> 数据集/运行版本：`TASK015-v1`  
> 目标：独立账号、可识别资源、按 ID 清理、不覆盖用户数据。

## 1. 账号

| 账号 | 用途 | 标识/凭据 |
|---|---|---|
| 管理员 | 管理端、RAG 上传、支付管理 | 运行时随机生成，`TASK015-admin-*` |
| 用户 A | 正常订单/售后/Agent | 运行时随机生成，`TASK015-user-a-*` |
| 用户 B | 跨用户隔离 | 运行时随机生成，`TASK015-user-b-*` |

- 不写入默认管理员账号；
- 不写入固定密码；
- 测试凭据只保存在本地被 Git 忽略的临时文件；
- 报告只记录账号前缀或资源编号，不记录密码和 Token；
- DeepSeek Key 只从本地环境变量读取，不进入测试数据或报告。

## 2. 业务数据

| 数据 | 前缀 | 用途 | 清理 |
|---|---|---|---|
| 分类 | `TASK015-CAT-` | 商品 | 按 category ID |
| 商品 | `TASK015-P-` | SKU/订单 | 按 product ID |
| SKU | `TASK015-SKU-` | 库存/订单 | 按 SKU ID |
| 库存 | 关联 SKU | 入库/释放 | 按 SKU ID |
| 订单 | `ORD...` | 订单/支付 | 按 order ID/no |
| 支付 | `PAY...` | Mock/状态 | 按 payment ID/no |
| 售后 | `AS...` | 售后状态 | 按 after-sales ID |
| 知识文档 | `TASK015-KB-` | RAG 评估 | 按 document ID |
| 知识版本 | 版本 ID | 发布/检索 | 随 document |

不执行 `TRUNCATE`、整库清空或按宽泛前缀删除用户已有数据。

## 3. 订单状态数据

TASK-015 需要至少覆盖：

```text
PENDING_PAYMENT  待支付订单，用于取消/Confirm/库存释放
PAID             MOCK 支付成功订单，用于支付状态/售后
CANCELLED        已取消订单，用于幂等/重复操作
COMPLETED        完成订单，用于售后边界（如适用）
```

所有状态必须由现有业务 API 或 Service 产生，不直接 SQL 伪造成功状态。

## 4. 支付测试数据

### Mock

- `MOCK` 支付单；
- `mock-success`；
- `mock-fail`；
- 重复成功/失败；
- 订单状态、支付状态和库存一致。

### 本地 RSA / Fake HTTP

- 运行时生成 RSA 测试密钥，不写入业务配置；
- 只用于验证签名和请求协议；
- 不能标记为真实支付宝沙箱通过。

### 真实沙箱

当前缺少：

```text
ALIPAY_APP_ID
ALIPAY_PRIVATE_KEY
ALIPAY_PUBLIC_KEY
ALIPAY_NOTIFY_URL
```

真实沙箱测试项全部标记 `SKIPPED_CREDENTIALS`，不得伪造成功。

## 5. RAG 数据

### 文档集

- 现有 TASK-005 评估文档保留；
- TASK-015 新增独立文档集；
- 包含：
  - 直接答案；
  - 同义表达；
  - 相似但无直接答案；
  - 完全无答案；
  - `ADMIN_ONLY` 权限文档；
  - 恶意指令注入文档（仅安全测试）。

### 问题集

TASK-015 数据集独立版本，建议：

```text
原有可回答问题 25 条
无答案/相似无答案 8～10 条
权限受限 3～5 条
```

每条包含：

```json
{
  "id": "T15-RAG-...",
  "question": "...",
  "expected_document": "..." | null,
  "expected_chunk_ids": [],
  "answerable": true,
  "visibility": "PUBLIC",
  "category": "refund|shipping|product|policy"
}
```

## 6. Agent 评估数据

- 30～35 条用例；
- Fake LLM 全量执行；
- 真实 DeepSeek 选取 10～15 条代表性用例；
- 报告分开统计；
- 每条记录 intent/tool/args/expected/allowed_tool/security_expectation；
- 不逐字匹配自然语言。

## 7. 清理顺序

```text
1. Redis Agent 会话/确认/限流 key（本次 user_id）
2. 售后记录
3. 退款记录
4. 支付记录
5. 订单明细、订单
6. 库存流水、库存、SKU
7. 商品、分类
8. 知识版本、Chunk、文档
9. 刷新会话
10. 测试用户
11. 测试上传文件
12. 临时凭据/结果文件
```

清理脚本只接受本次运行 ID 集合。

## 8. 清理失败处理

- 记录资源 ID 和失败原因；
- 不扩大删除范围；
- 不删除无法确认归属的数据；
- 下一次运行前按明确 ID 重试；
- 在最终报告中列出残留项。

## 9. 当前数据状态

TASK-015.1 基线：

```text
users=0
products=0
orders=0
knowledge_documents=0
```

测试数据将在 015.2 开始创建，完成后清理。
