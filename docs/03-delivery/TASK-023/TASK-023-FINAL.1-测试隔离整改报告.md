# TASK-023-FINAL.1 测试隔离整改报告

> 日期: 2026-11-25  
> 范围: 测试数据隔离、危险 fixture 整改、隔离验证  
> 本轮未恢复/覆盖开发库, 未删除开发数据, 未操作 Docker Volume, 未 commit/push。

## 1. 事故现场保护

三份备份均存在并通过 SHA256 校验:

```text
D:\Backups\E-Commerce-Agent\TASK-023.0_20261124_195424
D:\Backups\E-Commerce-Agent\TASK-023-FINAL_pre_20261124_203252
D:\Backups\E-Commerce-Agent\TASK-023-FINAL_incident_20261124_203638
```

校验结果:

```text
TASK-023.0           sha_bad=0
TASK-023-FINAL_pre   sha_bad=0
TASK-023-FINAL_incident sha_bad=0
```

Git 基线:

```text
branch: main
HEAD:   c732cc1
```

开发库 3307 在最终测试前后保持:

```text
users=55
orders=29
after_sales=6
knowledge_documents=1
knowledge_chunks=2
```

这些数字包含事故遗留数据, **不是原始状态**。

## 2. 测试资源架构

| 资源 | 开发 | 测试 |
|---|---|---|
| MySQL | `ecommerce_agent` @3307 | `ecommerce_agent_test` @3307 |
| MySQL 账号 | 开发账号 | `ecommerce_agent_test` 专用账号 |
| Redis | DB 0 | DB 15 |
| Qdrant | `knowledge_chunks_bge_m3_v1` | `knowledge_chunks_test_v1` |
| 文件 | `storage/knowledge` | `storage/test_knowledge` |

测试账号只拥有:

```text
GRANT USAGE ON *.*
GRANT ALL PRIVILEGES ON `ecommerce_agent_test`.*
```

已实际验证:

```text
测试库连接: 成功
访问 ecommerce_agent.users: DENIED (OperationalError)
```

## 3. 数据库隔离实现

- 新建 `ecommerce_agent_test`。
- 新建专用账号 `ecommerce_agent_test`。
- 测试库通过 Alembic migration 初始化, 当前 head `b96d3aae8b3d`。
- 没有对 `ecommerce_agent` 执行 migration。
- 根级 `conftest.py` 在导入阶段加载 `.env.test`, 并强制覆盖测试资源。
- `pytest_sessionstart` 连接真实测试库, 校验:
  - `SELECT DATABASE()` 必须是 `ecommerce_agent_test`;
  - `SHOW GRANTS` 不能包含开发库授权;
  - Redis 使用 DB 15;
  - Qdrant 使用测试 Collection;
  - 文件目录必须是 `storage/test_knowledge`。
- 任一检查失败, pytest 直接退出。

## 4. Redis/Qdrant/文件隔离

Redis:

- 测试使用 DB 15;
- 没有使用 `FLUSHDB`/`FLUSHALL`;
- 开发 Redis DB 0 未被测试操作。

Qdrant:

- 测试配置指向 `knowledge_chunks_test_v1`;
- 测试未删除开发 Collection;
- 当前 Qdrant 只有开发 Collection `knowledge_chunks_bge_m3_v1`, 2 points。

文件:

- 测试配置指向 `storage/test_knowledge`;
- 没有清理 `storage/knowledge`;
- 开发上传文件仍为 7 个。

## 5. 危险 fixture 整改

### 整改前

`backend/tests/integration/test_order_flow.py` teardown:

```text
delete(Refund)
delete(AfterSale)
...
delete(User)
```

这是对共享数据库的全表删除。

### 整改后

只删除 fixture 创建的用户/订单/SKU 及其依赖:

```text
删除条件:
- Refund/AfterSale: 本 fixture 用户或订单
- OrderItem/Payment: 本 fixture 订单
- Order: 本 fixture 用户
- Inventory/Sku/Product/Category: 本 fixture 的精确 ID
- User: 本 fixture 的 user/admin ID
```

Agent 测试中的全局 `assert after_sales count == 0` 已改为只统计当前测试订单。

## 6. 安全保护测试

新增:

```text
conftest.py
backend/tests/guard.py
backend/tests/test_environment_guard.py
```

覆盖:

- 错误数据库名拒绝;
- 错误账号拒绝;
- Redis DB 0 拒绝;
- 开发 Qdrant Collection 拒绝;
- 开发文件目录拒绝;
- 开发库授权拒绝。

结果:

```text
9 passed
```

## 7. 自动化测试结果

### Backend/Agent pytest

```text
380 passed
```

执行在 `ecommerce_agent_test` / Redis DB15; 开发库前后快照一致。

### Frontend

```text
typecheck passed
lint passed
Vitest 6 passed
Vite build passed
```

### Playwright

```text
10 passed
```

覆盖:

- 登录/刷新/退出;
- 普通用户权限;
- 分类/商品/库存/订单/售后;
- 知识库发布和检索;
- Agent 普通对话;
- Agent Query/Prepare/Confirm;
- Agent RAG Source;
- Agent READ Tool。

### RAG 离线评测

```text
dataset: task0212-rag-v1
documents: 6
questions: 43
answerable: 31
no_answer: 12
ACL: 1
```

用户范围:

```text
no-answer rejection: 12/12 = 1.0
answerable acceptance: 30/30 = 1.0
false rejection: 0
ACL: 1/1 filtered
```

管理员范围:

```text
no-answer rejection: 12/12 = 1.0
answerable acceptance: 30/30 = 1.0
ACL: admin in scope
```

该结果是离线小样本候选, 不是生产认证。

## 8. 开发库对比

```text
测试前: users=55 orders=29 after_sales=6 docs=1 chunks=2
测试后: users=55 orders=29 after_sales=6 docs=1 chunks=2
```

结论: 本轮隔离测试没有再改变开发库。

## 9. 修改文件

```text
conftest.py
backend/tests/guard.py
backend/tests/test_environment_guard.py
backend/tests/test_config.py
backend/tests/integration/test_order_flow.py
agent/tests/test_agent_tools.py
.gitignore
```

前端本轮收尾修改见最终交付报告。

## 10. 尚未解决

1. 3307 开发库仍是事故后 55/29/6, 未恢复;
2. 测试库仍有失败 seed 的部分数据, 属测试资源;
3. Redis DB15 有测试 key 残留;
4. 测试库 Qdrant Collection 未实际创建; 测试使用 fake/离线路径;
5. 人工视觉验收未由真实负责人执行。

## 11. 结论

```text
测试隔离: 已建立并验证
危险 teardown: 已整改
开发库再次被测试改写: 否
完整 pytest: 380 passed
完整 E2E: 10 passed
是否可以安全继续 FINAL: 是, 但开发库恢复仍需负责人批准
```
