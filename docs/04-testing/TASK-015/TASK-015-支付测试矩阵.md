# TASK-015 支付测试矩阵

> 当前真实支付宝配置：未提供。  
> 本文件区分 Mock、本地签名/Fake HTTP 和真实沙箱，禁止把前者写成后者。

## 1. 当前实现能力

```text
backend/app/services/alipay.py
backend/app/services/payment.py
backend/app/services/refund.py
backend/app/api/v1/payments.py
backend/tests/services/test_alipay.py
backend/tests/integration/test_order_flow.py
```

已实现：

- Page Pay URL；
- RSA2 签名；
- 通知验签；
- app_id、seller_id、金额、商户订单号校验；
- 支付成功幂等；
- 支付查询；
- 退款请求；
- 退款查询；
- 稳定 `out_request_no`；
- 退款状态和金额校验。

## 2. 执行分类

### A. MOCK_VERIFIED

| ID | 场景 | 预期 |
|---|---|---|
| T15-PAY-MOCK-01 | 创建 MOCK 支付 | PENDING |
| T15-PAY-MOCK-02 | mock-success | 支付/订单状态更新，库存扣减一次 |
| T15-PAY-MOCK-03 | 重复 mock-success | 无重复扣减/副作用 |
| T15-PAY-MOCK-04 | mock-fail | FAILED，不支付成功 |
| T15-PAY-MOCK-05 | 支付超时/关闭 | CLOSED，库存按规则释放 |
| T15-PAY-MOCK-06 | 取消订单后支付 | 不产生成功副作用 |

### B. LOCAL_SIGN_VERIFIED

| ID | 场景 | 预期 |
|---|---|---|
| T15-PAY-SIGN-01 | 生成 Page Pay URL | app_id/method/sign/biz_content 正确 |
| T15-PAY-SIGN-02 | 正确 RSA2 通知 | verify=True |
| T15-PAY-SIGN-03 | 篡改金额 | verify=False |
| T15-PAY-SIGN-04 | 错误签名 | verify=False |
| T15-PAY-SIGN-05 | app_id/seller_id 不匹配 | identity=False |
| T15-PAY-SIGN-06 | 未配置密钥 | 明确配置错误，不伪造成功 |

### C. FAKE_HTTP_VERIFIED

| ID | 场景 | 预期 |
|---|---|---|
| T15-PAY-FAKE-01 | 支付查询成功 | 只按可信结果更新 |
| T15-PAY-FAKE-02 | 支付查询失败/超时 | 保持原状态，不伪造成功 |
| T15-PAY-FAKE-03 | 退款请求稳定 out_request_no | 不生成新退款单 |
| T15-PAY-FAKE-04 | 退款响应金额不一致 | 失败/不结算 |
| T15-PAY-FAKE-05 | 退款未知结果 | PROCESSING，查询确认 |
| T15-PAY-FAKE-06 | 退款查询成功 | 只结算一次 |
| T15-PAY-FAKE-07 | 重复通知/退款重试 | 幂等，无重复副作用 |

### D. REAL_SANDBOX

| ID | 场景 | 当前状态 |
|---|---|---|
| T15-PAY-SANDBOX-01 | 真实沙箱创建支付 | `SKIPPED_CREDENTIALS` |
| T15-PAY-SANDBOX-02 | 真实沙箱支付回调 | `SKIPPED_CREDENTIALS` |
| T15-PAY-SANDBOX-03 | 重复真实通知 | `SKIPPED_CREDENTIALS` |
| T15-PAY-SANDBOX-04 | 真实退款 | `SKIPPED_CREDENTIALS` |
| T15-PAY-SANDBOX-05 | 真实退款查询 | `SKIPPED_CREDENTIALS` |

缺少条件：

```text
ALIPAY_APP_ID
ALIPAY_PRIVATE_KEY
ALIPAY_PUBLIC_KEY
ALIPAY_NOTIFY_URL（HTTPS 公网可达）
```

## 3. 回调场景

必须验证：

- 无签名；
- 错误签名；
- 金额不一致；
- 商户订单号不匹配；
- 未知支付单；
- 已关闭支付单收到迟到通知；
- 重复 TRADE_SUCCESS / TRADE_FINISHED；
- 通知处理异常重试；
- 主动查询结果。

真实回调不能在没有 HTTPS notify URL 的情况下宣称通过。

## 4. 报告规则

```text
Mock 通过       -> MOCK_VERIFIED
本地签名通过    -> LOCAL_SIGN_VERIFIED
Fake HTTP 通过  -> FAKE_HTTP_VERIFIED
真实沙箱未执行  -> SKIPPED_CREDENTIALS
```

不得使用 `REAL_SANDBOX_PASSED`，除非真实沙箱请求、回调、查询或退款均有证据。

## 5. 不修改范围

- 不修改支付/退款业务规则；
- 不修改 PaymentResponse；
- 不新增订单-支付关联字段；
- 不新增 migration；
- 不为通过测试而放宽签名、金额或订单校验。
