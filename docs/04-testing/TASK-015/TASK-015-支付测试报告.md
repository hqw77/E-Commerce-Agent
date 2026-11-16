# TASK-015 支付测试报告

> 结论：Mock、本地 RSA、Fake HTTP 通过；真实支付宝沙箱 SKIPPED_CREDENTIALS。

## 1. 当前配置

```text
ALIPAY_APP_ID         <missing>
ALIPAY_PRIVATE_KEY    <missing>
ALIPAY_PUBLIC_KEY     <missing>
ALIPAY_NOTIFY_URL     <missing>
```

没有真实沙箱凭证和 HTTPS 公网回调，因此不能执行真实沙箱支付、通知、退款、退款查询。

## 2. 已执行

### Mock

现有 `backend/tests/integration/test_order_flow.py` 覆盖：

- MOCK 支付成功；
- 订单支付状态；
- 库存扣减/释放；
- 迟到支付；
- 退款；
- 重复退款幂等。

### 本地 RSA / Fake HTTP

```text
backend/tests/services/test_alipay.py
backend/tests/security/test_task015_payment_security.py
```

覆盖：

- Page Pay URL 和签名；
- 正确/错误通知签名；
- 金额篡改；
- app_id/seller_id 不匹配；
- 稳定退款 `out_request_no`；
- 未配置时明确失败。

现有 Fake HTTP 退款测试覆盖：

- 退款成功；
- 退款失败；
- 退款超时后查询；
- 重复退款幂等；
- 未知响应。

## 3. 结果

```text
MOCK_VERIFIED
LOCAL_SIGN_VERIFIED
FAKE_HTTP_VERIFIED
REAL_SANDBOX: SKIPPED_CREDENTIALS
```

## 4. 未验证

- 真实沙箱创建支付；
- 真实异步通知；
- 真实退款；
- 真实退款查询；
- 公网 HTTPS notify 回调可达性。

这些项目不得写成“真实沙箱通过”。后续提供凭证和回调地址后，再单独执行。
