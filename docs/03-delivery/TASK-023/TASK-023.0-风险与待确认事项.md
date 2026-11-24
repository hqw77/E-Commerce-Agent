# TASK-023.0 风险与待确认事项

> 日期：2026-11-24  
> 本轮未删除数据、未清理 Volume、未执行 migration、未 commit/push。

## 1. 高风险

### 1.1 83 个工作区变更未提交

```text
staged: 0
unstaged: 66
untracked: 29
```

包括 TASK-019/020/021 代码、测试、报告、评测数据和注释修改。

风险：

- 工作区误操作会丢失；
- 当前备份是本机目录，不是异地备份；
- 还没有 Code Review 和 Git 提交。

建议：

- 保留 `D:\Backups\E-Commerce-Agent\TASK-023.0_20261124_195424`；
- 在恢复验证完成后做一次正式 Code Review；
- 再决定 commit，不在本轮执行。

### 1.2 3306 与 3307 数据分叉

```text
3306: 空业务库
3307: 有 TASK015/020.A 测试数据
```

风险：

- Backend 若使用 3306 会看起来“所有数据都没了”，但事实不是；
- 误把 3306 空库当成 3307 数据丢失；
- 错误地重建 3307 可能真正覆盖可恢复数据。

建议：

- 明确所有启动命令使用 3307；
- 不修改 3306，除非负责人确认；
- 不把 3306 数据迁移到 3307，除非另行审批。

### 1.3 Docker Volume 未做原始备份

以下 Volume 只有清单，没有块级备份：

```text
e-ecommerce-agent_mysql_data
e-ecommerce-agent_redis_data
e-ecommerce-agent_qdrant_data
ecommerce-agent-prod_*
```

MySQL 3307 有逻辑 dump，Qdrant 只有现有 Volume 和 2 个 Point。

风险：

- Volume 损坏时 Qdrant 向量可能需要重新生成；
- 生产 Volume 未验证内容；
- Redis 是短期状态，但仍可能有未过期 pending。

### 1.4 环境变量文件

存在：

```text
.env
.env.production
```

本轮没有读取或输出值，也没有放入备份。

风险：

- 文件包含本地/生产敏感配置；
- 不能提交到 Git；
- 不能复制到可公开分享的目录。

## 2. 中风险

### 2.1 当前 Backend/Frontend 未运行

```text
8000: 未监听
5173: 未监听
```

因此本轮无法确认：

- 前后端联调；
- 健康检查；
- E2E；
- 人工验收。

### 2.2 后端测试未实际执行

本轮只执行了：

```text
pytest --collect-only: 372 tests collected
```

没有执行完整 pytest，原因是避免测试写开发数据库和当前环境不完整。

### 2.3 前端 build 未执行

已执行：

```text
typecheck: passed
lint: passed
Vitest: 6 passed
```

未执行 `npm run build`，因为 build 会写 dist，不符合本轮只读保护原则。

### 2.4 Qdrant indexed_vectors_count=0

当前：

```text
points_count: 2
indexed_vectors_count: 0
indexing_threshold: 10000
```

判断是点数低于 HNSW 索引阈值，不是 Collection 损坏；但没有做重建或强制优化。

### 2.5 SQL dump 敏感

`data/mysql-3307.sql` 含测试数据，可能包含测试账号、订单和知识库内容；需要限制访问，不能外发。

## 3. 待确认事项

1. 是否允许在恢复后执行完整 Backend pytest？
2. 是否允许执行 Playwright E2E？
3. 是否允许使用 3307 现有测试数据，不清理？
4. 是否允许恢复 `mysql-3307.sql`，以及恢复目标是什么？
5. 是否需要在本轮修复前端 Debug Console/Trace 展示？
6. HITL 是否属于当前本地最终开发范围？
7. 是否要求真实支付宝沙箱联调后才能验收？
8. 是否需要对 Qdrant Volume 做额外备份？
9. 是否需要对生产 Volume 做快照？
10. 是否允许后续执行 Git commit？

## 4. 当前未做事项

```text
未删除数据
未清理 Volume
未重建数据库
未执行 migration
未 commit/push
未启动生产 Compose
未修改源码
```

## 5. 结论

```text
代码保护: 完成
Git diff/untracked 清单: 完成
上传文件备份: 完成
3307 逻辑备份: 完成
3306 schema 备份: 完成
环境恢复方案: 完成
完整运行验证: 待负责人确认
```
