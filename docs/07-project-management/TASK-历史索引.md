# TASK 历史索引

> 只建立索引, 不复制敏感数据。原始报告保留在原位置, `09-archive` 提供归档入口。

| TASK | 名称 | 状态 | 原始资料 | 源码/测试 | 验收证据 | 遗留 |
|---|---|---|---|---|---|---|
| 001 | 基础设施 | 代码完成, 独立报告缺失 | `docs/03-delivery/TASK-001/.gitkeep` | `backend/app/core`, `db` | README/历史状态 | 缺独立报告 |
| 002 | 用户认证 | 代码完成, 独立报告缺失 | `TASK-002/.gitkeep` | auth/security | backend tests | 缺独立报告 |
| 003 | 商品与库存 | 代码完成, 独立报告缺失 | `TASK-003/.gitkeep` | product/sku/inventory | product/inventory tests | 缺独立报告 |
| 004 | 订单/支付/售后 | 代码完成, 沙箱延期 | `TASK-004/TASK-004-final-delivery.md` | order/payment/refund/after_sale | 最终交付记录 | 真实沙箱未联调 |
| 005 | RAG 知识库 | 完成 | `TASK-005/TASK-005-final-delivery.md` | `services/rag` | 交付记录 | no-answer 历史问题 |
| 006 | LangGraph Agent | 代码完成, 独立交付缺失 | `02-design/TASK-006...` | `agent/` | 设计+测试 | 缺独立交付 |
| 007 | Agent 业务工具 | 代码完成, 独立交付缺失 | `02-design/TASK-007...` | `agent/tools` | 设计+测试 | 缺独立交付 |
| 008-013 | React 前端 | 完成 | `TASK-008-013/前端阶段交付报告.md` | `frontend/src` | 交付报告 | 无逐任务报告 |
| 014 | 前后端联调 | 完成 | `TASK-014/最终验收报告.md` | frontend/backend | 验收/E2E | 无 |
| 015 | E2E/安全/评估 | 完成, 外部验证缺口 | `TASK-015/最终验收报告.md` + `04-testing` | full stack | 测试/评估 | 真实支付, AI 评估 |
| 016 | 本地生产 Docker | 完成 | `TASK-016/最终验收报告.md` | deploy/compose | 验收 | HTTPS/生产未验证 |
| 017 | 云部署 | 暂缓 | 无 | 无 | 无 | 用户暂缓 |
| 018 | 部署验证/交付 | 暂缓 | 无 | 无 | 无 | 用户暂缓 |
| 019 | Agent 架构审查 | 完成 | `TASK-019/架构审查报告.md` | `agent/` | 审查报告 | HITL 等未做 |
| 020 | Agent 重构 | 完成 | `TASK-020/最终验收报告.md` | `agent/`, API | 报告/测试 | Debug UI/HITL |
| 020.A | E2E | 完成 | TASK-020 报告第 15 节 | `frontend/e2e` | 10 E2E | 无独立文件 |
| 021.0 | 阶段检查 | 完成 | `TASK-021.0...md` | all | 报告 | 无 |
| 021.1 | RAG 诊断 | 完成 | `TASK-021.1...md` | RAG | 离线实验 | 小样本 |
| 021.2 | RAG 无答案 | 代码/自动化完成, 待人工 | `TASK-021.2...md` | `agent/rag_evidence.py` | 372 tests | 生产阈值/HITL |
| 021.3 | 未定义 | 未开始 | 无 | 无 | 无 | 无资料 |
| 022 | 未定义 | 未开始 | 无 | 无 | 无 | 无资料 |
| 023.0 | 保护/盘点 | 完成 | `TASK-023.0-*.md` | all | 备份/报告 | 见风险文档 |
| 023-FINAL | 本地收尾 | 工程完成, 开发库恢复待批准 | TASK-023-FINAL 报告 | all | 357 pytest + 10 E2E | 3307 事故数据 |
| 023-FINAL.1 | 测试隔离整改 | 完成 | `TASK-023-FINAL.1-测试隔离整改报告.md` | tests | 380 pytest | 开发库未恢复 |
| 023-FINAL.2 | 支付下线/业务收敛 | 完成, 未 commit | `TASK-023-FINAL.2-支付业务下线与核心业务收敛报告.md` | backend/frontend/agent | 357 pytest + 10 E2E | 历史支付表保留 |

## 备注

- TASK-020 按负责人此前确认视为已验收; 报告文本仍保留“等待人工验收”的历史表述。
- TASK-021.2 不改为完全验收。
- TASK-021.3、TASK-022 没有任何资料, 不补造。
