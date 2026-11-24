# 06 测试与质量

## 1. 测试分层

```text
单元测试      Schema、工具函数、状态判断
集成测试      API + Service + MySQL
Agent 测试    图、路由、工具、Prepare/Confirm、Trace
前端测试      TypeScript、ESLint、Vitest
E2E            Playwright
迁移测试      Alembic upgrade/downgrade/check
```

## 2. 当前基线

```text
Backend/Agent pytest：361 passed
Frontend typecheck：通过
Frontend lint：通过
Frontend production build：通过
Vitest：6 passed
```

此前已实际执行并通过：

```text
商城浏览
商品详情
普通用户登录分流
我的订单
我的售后
管理员登录
```

## 3. 测试隔离

测试使用独立环境：

```text
MySQL：ecommerce_agent_test
Redis：DB 15
Qdrant：knowledge_chunks_test_v1
Storage：storage/test_knowledge
```

根 `conftest.py` 会校验实际数据库和账号，拒绝在开发库上运行破坏性测试。

关键目的：

- 不污染 3307 开发库；
- 不覆盖开发 Redis；
- 不覆盖开发 Qdrant；
- 不删除开发知识文件。

## 4. 覆盖重点

### 认证

- 注册、登录、Refresh；
- 过期/无效 Token；
- 普通用户访问管理员接口 403；
- `is_admin` 返回。

### 商品

- 创建、查询、详情、更新；
- 图片 URL 空/非空；
- 商品编号唯一；
- 商品编号格式；
- 分类/状态约束。

### 库存

- 初始化；
- 入库、调整；
- 预占、释放、扣减；
- 幂等流水；
- 库存不为负。

### 订单

- 创建订单；
- 取消未发货；
- 发货、送达、完成；
- 非法状态冲突；
- 幂等键。

### 售后

- 仅 EXCHANGE；
- 订单必须已送达；
- 审核、拒绝、收货、完成换货；
- 用户数据隔离。

### Agent

- 路由；
- READ Tool；
- PREPARE / Confirm；
- nonce / 用户 / 会话 / 参数 hash；
- 输出校验；
- Trace。

## 5. 前端检查

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

E2E：

```powershell
npm run e2e
```

部分 E2E 依赖：

```text
frontend/.tmp/task014-e2e.json
```

没有 fixture 时会跳过依赖 fixture 的测试。

## 6. 已知测试限制

- 没有完整生产级 E2E 套件；
- 管理员订单/售后按钮的最终 E2E 受环境限制，未在所有会话中重跑；
- RAG 评测是小样本；
- Trace 是进程内，不适合生产审计；
- 没有性能测试；
- 没有安全渗透测试；
- 没有前端视觉回归测试。

## 7. 提交前检查

```text
[ ] README 与实际功能一致
[ ] .env 未提交
[ ] 无临时账号密码
[ ] 无测试缓存/截图
[ ] 迁移 head 唯一
[ ] pytest 通过
[ ] 前端 typecheck/lint/build 通过
[ ] 普通用户不能访问管理后台
[ ] 订单/售后状态机未被绕过
```

## 8. 质量判断

当前可以称为：

```text
可运行、可演示、可回归的 MVP
```

还不能称为：

```text
生产级系统
```

生产化还需要：

```text
CI/CD
HTTPS
域名拆分
监控/告警
备份恢复
限流/审计
依赖漏洞扫描
容量和性能测试
```
