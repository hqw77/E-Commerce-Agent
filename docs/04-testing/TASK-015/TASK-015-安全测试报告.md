# TASK-015 安全测试报告

> 执行时间：2026-11-17  
> 结论：新增安全测试通过；部分 Agent 安全项只能做确定性/Fake 或真实回答抽样，不能宣称覆盖所有模型行为。

## 1. 新增测试

```text
agent/tests/security/test_task015_security.py        3 passed
backend/tests/security/test_task015_payment_security.py  2 passed
```

覆盖：

- Prompt Injection 常见模式识别；
- System Prompt/API Key 形式内容被输出校验拒绝；
- 伪造 RAG Source 被拒绝；
- 支付通知签名篡改；
- 支付金额篡改导致验签失败；
- app_id 与 seller_id 身份不匹配；
- 未配置支付宝时明确失败，不伪造支付 URL。

## 2. 复用已有安全测试

TASK-014/之前已有测试已经覆盖，未重复实现：

- 无 Token/错误密码/过期 Token → 401；
- Refresh Token Rotation、重放撤销、并发刷新；
- 普通用户访问管理端 → 403；
- 订单跨用户隔离；
- Agent 会话跨用户隔离；
- Agent Tool Registry 未注册 Tool；
- Tool Schema 禁止额外字段和 `user_id`；
- Prepare/Confirm 跨用户、错误 nonce、过期、重复、并发；
- 知识库 ADMIN_ONLY ACL。

关联文件：

```text
backend/tests/api/test_admin_dependency.py
backend/tests/api/test_auth.py
backend/tests/integration/test_order_flow.py
agent/tests/test_agent_tools.py
agent/tests/test_tools.py
```

## 3. Prompt Injection 与越权检查

已执行：

- 恶意指令不进入 Tool 执行路径的确定性测试；
- System Prompt/Key 形式输出拒绝；
- 真实 DeepSeek 抽样中包含 Prompt Injection 和“伪造管理员/指定其他用户”用例；
- 真实 Agent 抽样中：
  - 无未授权 Prepare；
  - 无其他用户订单返回；
  - 无 Secret 泄漏；
  - 无数据库写副作用。

限制：

- Chat API 不返回完整 Tool Call 轨迹，无法对真实模型每次调用做逐 Tool 审计；
- 真实模型的自然语言拒绝不能替代后端权限；
- 权限最终由 Backend `CurrentUser`、Tool Registry、Confirm 校验保证。

## 4. Prepare/Confirm

现有测试覆盖：

- 跨用户确认；
- nonce 篡改；
- 凭证过期；
- 重复确认；
- 并发确认；
- 参数篡改；
- 订单、库存、AfterSale 等最终状态检查。

TASK-015 没有修改这些规则。

## 5. 结论

```text
新增安全测试：5 passed
Backend/Agent 全量：336 passed
真实沙箱支付安全：SKIPPED_CREDENTIALS
```

未验证：

- 真实支付宝异步通知攻击面；
- 真实模型完整 Tool Call 审计；
- 浏览器 localStorage/XSS 的运行时安全扫描（仅设计/代码审查）。
