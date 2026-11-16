# TASK-015 环境基线

> 采集时间：2026-11-17  
> 用途：TASK-015.1 测试环境快照，不代表 TASK-015 测试结果。

## 1. 工程基线

```text
Branch: feature/task-004-order
HEAD:   7d3b836 feat(rag): complete knowledge base and retrieval system
```

TASK-014 最新状态：

```text
backend pytest: 331 passed
Ruff: passed
Mypy: 128 source files passed
Frontend typecheck: passed
Frontend lint: passed
Frontend Vitest: 6 passed
Frontend build: passed
Playwright: 7 passed（TASK-014 验收记录）
Alembic current: b96d3aae8b3d
Alembic check: No new upgrade operations detected
```

说明：本轮 TASK-015.1 没有重新创建 E2E 数据，因此 Playwright 7 passed 引用 TASK-014 最终验收记录；015.2 将重新 seed 并执行扩展 E2E。

## 2. Docker 基线

```text
app       Up       http://127.0.0.1:8000
mysql     Up healthy
redis     Up healthy
qdrant    Up
```

健康检查：

```text
/api/v1/health/live  200
/api/v1/health/ready 200
```

开发数据库当前测试数据：

```text
users=0
products=0
orders=0
knowledge_documents=0
```

## 3. 外部依赖

| 依赖 | 状态 | 说明 |
|---|---|---|
| DeepSeek Key | 已配置（仅本地） | 真实模型抽样使用 |
| Alipay app_id/private/public/notify | 未配置 | 真实沙箱 SKIPPED |
| BGE-M3 模型缓存 | 已存在（约 13G） | 位于 Docker 容器层，非持久化 |
| Qdrant | 运行中 | RAG 评估可用 |
| MySQL/Redis | 运行中 | 业务/安全测试可用 |
| Playwright Chrome | 可用 | 使用 channel=chrome |

## 4. 当前测试资产

```text
backend/tests/                 331 tests
agent/tests/                   Agent tests
frontend/e2e/                  7 tests (TASK-014)
backend/scripts/task014_e2e_seed.py
backend/scripts/evaluate_rag.py
backend/tests/evaluation/rag_eval_dataset.json
```

## 5. 已知环境风险

1. 容器内 BGE-M3 缓存未挂载独立 Volume；容器重建会丢失。
2. 无真实支付宝凭证和 HTTPS notify URL。
3. DeepSeek 真实输出具有非确定性。
4. 测试数据清理必须按本次 ID，不做整库清理。
5. TASK-015 E2E 需要重新 seed，不能直接复用 TASK-014 已清理的账号。
