# TASK-004 最终交付记录

> 状态：业务代码开发与自动化验收完成，支付宝沙箱真实 E2E 延期
> 更新日期：2026-11-14
> 代码分支：`feature/task-004-order`
> 设计冻结：`f268e76`

## 1. 最终结论

```text
TASK-004：业务代码开发与自动化验收完成，支付宝沙箱真实 E2E 延期。
```

TASK-004 允许进入下一阶段；支付宝沙箱 E2E 不再作为 TASK-005 的阻塞条件。

未执行的沙箱测试不得描述为通过。

---

## 2. 已完成能力

### 订单

- 创建、查询、取消；
- 商品、SKU、价格和收货信息快照；
- 服务端金额计算；
- 订单创建幂等和请求指纹；
- 库存预占与释放；
- 支付超时关闭；
- 管理员发货、送达、完成。

### 支付

- 一单一支付；
- MOCK 支付成功/失败；
- 支付单渠道、状态和过期校验；
- 支付成功扣减预占库存；
- 重复回调幂等；
- 晚到支付处理；
- 支付宝 RSA2 适配器；
- 支付宝页支付参数、查询、关闭。

### 退款

- 全额退款；
- 退款额度占用；
- 稳定 `out_request_no`；
- `alipay.trade.refund` 网络调用；
- `alipay.trade.fastpay.refund.query` 查询；
- `fund_change`、金额、订单号、请求号校验；
- 网络超时/未知结果保留 `PROCESSING`；
- 管理端 sync 查询；
- 防重复退款；
- 退款成功后更新 payment、order、after_sales、refunds；
- MOCK 退款保留。

### 售后

- `REFUND_ONLY`；
- `RETURN_REFUND`；
- `EXCHANGE`；
- 审核、拒绝、取消；
- 退货物流、收货；
- 退货入库；
- 换货补发；
- 售后期限、整行金额、活跃售后和状态校验；
- 售后与退款联动。

### 管理端

- 订单查询与履约；
- 支付查询与同步；
- 退款创建、查询、重试、同步；
- 售后查询、审核、收货、换货完成。

---

## 3. 自动化验收

最近一次实际执行：

```text
pytest: 267 passed
Ruff check: passed
Mypy: passed
 83 source files
Alembic check: passed
  No new upgrade operations detected.
```

数据库迁移链：

```text
c851e383d3fe
  → 22a36fc5af9c  create order payment after-sales tables
  → 5f14d68fcbd1  widen inventory transaction type
```

已执行升级、降级、再次升级验证。

---

## 4. 交付提交

```text
cec38bd  feat(order): add order payment after-sales models and migration
6ff265e  feat(task-004): implement orders payments refunds and after-sales
e69a75d  test(task-004): cover payment timeout race and finalize formatting
e7eea62  docs(task-004): prepare Alipay sandbox E2E checklist
de3e9ad  feat(refund): add Alipay full refund flow
```

说明：

- `cec38bd`：TASK-004.2 模型与迁移；
- `6ff265e`：TASK-004.3～004.8 主体；
- `e69a75d`：并发测试和格式收口；
- `e7eea62`：沙箱 E2E 准备清单；
- `de3e9ad`：支付宝真实全额退款能力。

---

## 5. 尚未验证的沙箱 E2E

以下事项延期，不纳入当前 TASK-004 自动化通过范围：

1. 支付宝沙箱真实支付 E2E；
2. 支付宝沙箱真实退款 E2E；
3. 支付宝异步通知真实联调；
4. 支付宝退款查询真实全链路验证。

延期原因：

- 当前缺少沙箱应用信息、密钥或可公网访问的异步通知地址；
- 未进行真实沙箱支付/退款；
- 未使用真实资金。

统一计划执行阶段：

```text
TASK-015：E2E 测试与最终评测
```

检查清单保留在：

- [alipay-sandbox-e2e.md](alipay-sandbox-e2e.md)

---

## 6. TASK-015 验收预留

TASK-015 必须纳入：

- 支付宝沙箱页支付；
- 异步通知验签和金额/订单号校验；
- 重复通知幂等；
- 支付查询；
- 支付关闭；
- 晚到支付；
- 全额退款；
- 退款查询；
- 网络超时/未知结果；
- 退款幂等和重复请求；
- 回调 URL 公网可达性；
- 密钥不进入 Git；
- 只使用沙箱，不使用真实资金。

测试要求：

- 使用确定性断言；
- 不得用 MOCK 代替真实沙箱；
- 不得用静态检查代替真实联调；
- 未执行项必须明确标记为未验证。

本次不创建完整 TASK-015 设计文档。

---

## 7. TASK-017 生产部署前检查

TASK-017 正式生产部署前必须重新检查：

- 支付渠道真实联调状态；
- 支付宝生产应用配置；
- 生产密钥管理；
- 公网 HTTPS 回调；
- 支付/退款查询和关闭；
- 沙箱与生产差异；
- 生产禁用 MOCK；
- 支付/退款异常人工处理流程。

TASK-004 的沙箱延期不取消 TASK-017 的检查责任。

---

## 8. 下一任务

```text
TASK-005：RAG 知识库
状态：允许正式启动，尚未开始
```

本次只同步文档和状态，不开始 TASK-005。

---

## 9. 文档边界

本次更新：

- 项目总进度；
- TASK-004 最终交付记录；
- 支付宝沙箱 E2E 清单状态；
- 学习进度表中的任务状态。

不修改：

- 业务代码；
- 数据库模型/迁移；
- 测试；
- 依赖；
- 已冻结的 TASK-004 业务规则。
