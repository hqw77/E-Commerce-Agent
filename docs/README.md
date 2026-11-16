# E-Commerce Agent 学习资料库

> 本目录是项目学习资料的统一入口。
>
> 当前状态：已建立五大分类目录骨架；现有文档暂时保留在 `docs/` 根目录，尚未移动。
>
> 目标：把教程、设计、交付记录、技术知识和面试资料分开维护，避免重复和冲突。

---

## 1. 目录结构

```text
docs/
├── README.md                     # 本索引
├── learning-guide.md             # 学习路线与资料索引
├── learning-log.md               # 实际学习进度
├── 01-learning/                  # 技术学习教程
│   ├── TASK-001-基础设施/
│   ├── TASK-002-用户认证/
│   ├── TASK-003-商品与库存/
│   ├── TASK-004-订单/
│   └── AI应用/
├── 02-design/                    # 设计与架构
│   ├── product-design.md
│   ├── architecture.md
│   └── 技术决策记录.md
├── 03-delivery/                  # 任务交付记录
│   ├── TASK-001/
│   ├── TASK-002/
│   ├── TASK-003/
│   └── TASK-004/
├── 04-knowledge/                 # 技术知识积累
│   ├── 学习问题与解答.md
│   ├── 核心调用链.md
│   ├── database.md
│   └── development.md
└── 05-interview/                 # 面试准备
    ├── Python面试题.md
    ├── FastAPI面试题.md
    ├── 数据库与并发面试题.md
    ├── AI应用开发面试题.md
    └── 项目综合面试题.md
```

> 说明：Git 不跟踪空目录，因此当前空分类目录放置了 `.gitkeep`。后续放入实际文档后，可按需删除对应 `.gitkeep`。

---

## 2. 五类资料职责

### 01-learning：技术学习教程

- 解释技术原理；
- 结合真实源码讲实现；
- 说明设计原因和调用过程；
- 包含常见问题与面试表达。

### 02-design：设计与架构

- 设计基线；
- 系统架构；
- 技术决策记录。

### 03-delivery：任务交付记录

- 任务目标；
- 实际修改；
- 数据库迁移；
- 真实测试结果；
- Git 提交与遗留问题。

### 04-knowledge：技术知识积累

- 学习问题与解答；
- 核心调用链；
- 数据库参考；
- 开发/运行/测试参考资料。

### 05-interview：面试准备

- 从真实项目实现提炼面试题；
- 标准回答；
- 可能的追问。

---

## 3. 现有文档的当前位置与最终归属

| 当前文件 | 当前状态 | 最终归属 |
|---|---|---|
| `docs/product-design.md` | TASK-003.1 设计，定稿待复核 | `docs/02-design/product-design.md` |
| `docs/02-design/V1.2-项目总体规划.md` | V1.2 总体设计，待 Review | 保留在 `docs/02-design/` |
| `docs/02-design/系统总体架构.md` | 系统总体架构，待 Review | 保留在 `docs/02-design/` |
| `docs/02-design/AI-Agent-总体设计.md` | AI Agent 总体设计，待 Review | 保留在 `docs/02-design/` |
| `docs/02-design/TASK-004.1-订单支付售后设计.md` | 设计冻结（第一版） | 保留在 `docs/02-design/` |
| `docs/02-design/TASK-005-RAG-详细设计.md` | TASK-005 详细设计，已实现 | 保留在 `docs/02-design/` |
| `docs/02-design/TASK-006-LangGraph-Agent-核心设计.md` | TASK-006 详细设计，已实现（待人工验收） | 保留在 `docs/02-design/` |
| `docs/02-design/TASK-007-Agent-业务工具集成设计.md` | TASK-007 详细设计，已实现（待人工验收） | 保留在 `docs/02-design/` |
| `docs/02-design/TASK-008-013-前端整体设计.md.md` | TASK-008～013 前端整体设计，已实现（待人工验收） | 保留在 `docs/02-design/` |
| `docs/02-design/TASK-014-前后端联调设计.md` | TASK-014 前后端联调设计，已实现（待人工验收） | 保留在 `docs/02-design/` |
| `docs/architecture.md` | AI Agent 安全设计基线（待 Review） | `docs/02-design/architecture.md` |
| `docs/PROJECT-STATUS.md` | 项目总进度与下一任务记录 | 保留在根目录 |
| `docs/03-delivery/TASK-004/` | TASK-004 交付和沙箱 E2E 清单 | 保留在 `docs/03-delivery/TASK-004/` |
| `docs/03-delivery/TASK-005/` | TASK-005 RAG 交付记录 | 保留在 `docs/03-delivery/TASK-005/` |
| `docs/03-delivery/TASK-008-013/` | TASK-008～013 前端交付报告 | 保留在 `docs/03-delivery/TASK-008-013/` |
| `docs/03-delivery/TASK-014/` | TASK-014 联调验收报告和测试证据 | 保留在 `docs/03-delivery/TASK-014/` |
| `docs/04-testing/TASK-015/` | TASK-015 测试计划、方案和评估结果 | 保留在 `docs/04-testing/TASK-015/` |
| `docs/03-delivery/TASK-016/` | TASK-016 本地生产化验收报告 | 保留在 `docs/03-delivery/TASK-016/` |
| `docs/database.md` | 空文件，保留不动 | `docs/04-knowledge/database.md` |
| `docs/development.md` | 空文件，保留不动 | `docs/04-knowledge/development.md` |
| `docs/learning-guide.md` | 保留在根目录 | `docs/learning-guide.md` |
| `docs/learning-log.md` | 保留在根目录 | `docs/learning-log.md` |

> `product-design.md` 是 TASK-003 设计基线，不是学习教程。
>
> 根目录 `README.md` 与 `docs/README.md` 是两个不同文件，前者用于项目总览，后者用于学习资料库索引。

---

## 4. 推荐阅读顺序

1. `docs/learning-guide.md`：了解学习路线和源码索引；
2. `docs/learning-log.md`：查看当前进度和未解决问题；
3. `docs/01-learning/TASK-001-基础设施/`：从基础设施开始；
4. `docs/01-learning/TASK-002-用户认证/`；
5. `docs/01-learning/TASK-003-商品与库存/`；
6. `docs/02-design/`、`docs/04-knowledge/`：按需查阅；
7. `docs/05-interview/`：复习与面试准备。

---

## 5. 整理原则

1. 教程必须结合真实仓库源码，不能只写通用技术知识。
2. 技术原理、项目设计、真实实现分开表述。
3. 不复制重复内容，优先交叉引用。
4. 不编造测试结果、Git 提交、代码位置和实际实现。
5. 学习问答只收录真实提出的问题。
6. 面试题从真实项目实现中提炼。
7. TASK-004 已完成业务代码与自动化验收；支付宝沙箱 E2E 延期至 TASK-015。
8. TASK-005 RAG、TASK-006 Agent 核心、TASK-007 业务工具集成、TASK-008～013 React 前端代码实现与自动化验收完成，待人工验收。
9. 现有文件暂不移动；待学习教程放入后，再检查归档和引用关系。

---

## 6. 当前状态

```text
已完成：五大分类目录骨架、索引文件
已完成：TASK-004 业务代码与自动化验收；支付宝沙箱 E2E 延期至 TASK-015
已完成：TASK-005 RAG 代码实现与自动化验收，待人工验收
已完成：TASK-006 LangGraph Agent 核心代码实现与自动化验收，待人工验收
已完成：TASK-007 Agent 业务工具集成代码实现与自动化验收，待人工验收
已完成：TASK-008～013 React 前端代码实现、构建与前端验收，待人工验收
已完成：TASK-016 本地生产化 Docker Compose（真实支付/HTTPS 未验证）
下一阶段：TASK-017 尚未开始
未完成：现有文档迁移、教程归档、问答/决策/面试/交付内容
```

当前不移动、不删除、不覆盖任何现有文档；不修改业务代码；不开始 TASK-005 编码。
