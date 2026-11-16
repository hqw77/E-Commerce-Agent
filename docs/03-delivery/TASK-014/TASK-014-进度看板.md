# TASK-014 进度看板

> 更新时间：2026-11-17  
> 状态：完成，待人工验收  
> 说明：这是实时进度记录，最终结论以 `TASK-014-最终验收报告.md` 为准。

## 总体状态

```text
TASK-014.1  API 契约矩阵与测试数据方案   完成
TASK-014.2  认证与权限联调               完成
TASK-014.3  核心业务联调                 完成
TASK-014.4  RAG 联调                     完成
TASK-014.5  Agent 联调                   完成
TASK-014.6  整体回归与报告               完成
```

## 已完成证据

### Phase 014.1

- [TASK-014 API 契约矩阵](TASK-014-API契约矩阵.md)
- [TASK-014 测试数据与清理方案](TASK-014-测试数据方案.md)

### Phase 014.2

Playwright：

```text
3 passed
- 未登录路由保护
- 管理员登录、Refresh、登出
- 普通用户访问管理员页面显示权限不足
```

### Phase 014.3

- 分类管理页面：列表、创建、编辑；
- 商品/库存/订单/售后页面真实数据；
- Playwright core：

```text
2 passed
```

### Phase 014.5

- Agent 普通对话；
- 查询订单 Tool；
- 取消订单 Prepare；
- Confirm；
- 订单最终状态 CANCELLED；
- Playwright：

```text
1 passed
```

### RAG

- BGE-M3 使用主机已有缓存，不再重新下载；
- 测试文档真实上传；
- 版本处理状态达到 `INDEXED`；
- 发布/非空检索 E2E 待最后一次重跑确认。

## 最终验收

- Playwright：7 passed
- Backend：331 passed
- Ruff / Mypy / Alembic：通过
- 测试数据已清理
- 最终报告：[TASK-014-最终验收报告.md](TASK-014-最终验收报告.md)

## 已完成清单

- [x] 重置测试数据并重跑完整 Playwright 套件；
- [x] 知识库发布和非空检索 E2E 最终确认；
- [x] 干净环境下重跑 331 个后端测试；
- [x] Ruff/Mypy 最终确认；
- [x] 前端 typecheck/lint/Vitest/build 最终确认；
- [x] 清理本次测试数据；
- [x] 写最终验收报告。

## 已知环境风险

- BGE-M3 模型体积大，首次加载慢；当前已复制缓存到容器；
- Docker 容器重建会丢失容器内模型缓存，TASK-016 需要持久化卷；
- 上一轮后端 331 测试是在模型下载/缓存复制期间运行的，结果不作为最终回归；
- 测试数据只按本次生成的 ID 清理，不执行整库清空。
