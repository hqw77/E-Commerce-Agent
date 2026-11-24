# 06 测试与验收

## 测试层次

| 层 | 工具 | 范围 |
|---|---|---|
| 单元 | Pytest | 安全、Schema、纯函数、Agent policy |
| 集成 | Pytest + MySQL/Redis | Auth、商品、库存、订单、售后、知识库、Agent API |
| 前端 | Vitest | token/format/component |
| E2E | Playwright | 登录、业务页面、知识库、Agent、Confirm |
| 静态 | Ruff/Mypy | 后端和 Agent |
| 迁移 | Alembic check | 无新 migration |
| 前端 | TypeScript/ESLint/Vite | 类型、Lint、构建 |
| RAG | 离线脚本 | 检索、阈值、ACL、无答案 |

## 推荐执行顺序

```text
1. Ruff
2. Mypy
3. Alembic check
4. Backend pytest
5. Frontend typecheck
6. Frontend lint
7. Vitest
8. Frontend build
9. Playwright E2E
10. RAG 离线评测
```

## 数据安全

- Backend pytest 可能创建/清理测试数据, 执行前确认测试 DB 目标;
- 当前开发演示数据在 MySQL 3307;
- 不要用 3306 空库覆盖 3307;
- 不删除共享测试数据;
- 测试失败必须分类为环境/数据/历史缺陷/本轮缺陷。

## 手工验收

必须覆盖:

- 登录/Refresh/退出;
- 商品/SKU/库存;
- 订单 CREATED 创建/取消/发货/送达/完成;
- 简化售后 EXCHANGE;
- 知识库上传/发布/检索;
- Agent GENERAL/RAG/TOOL/WORKFLOW;
- Prepare/Confirm;
- Trace Debug 权限;
- RAG 无答案。

真实支付宝沙箱已从当前项目范围移除, 不再作为验收项。

## 已知限制

- HITL 未实现;
- Debug Console 已实现;
- Trace 只在进程内;
- RAG 评测样本小;
- 当前知识库规模小;
- Qdrant `indexed_vectors_count=0` 是点数低于阈值;
- 支付/退款已下线, 历史表保留。
