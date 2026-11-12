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
| `docs/product-design.md` | 保留不动 | `docs/02-design/product-design.md` |
| `docs/architecture.md` | 空文件，保留不动 | `docs/02-design/architecture.md` |
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
7. TASK-004、RAG、Agent 当前只预留目录，不提前编写虚构教程。
8. 现有文件暂不移动；待 TASK-001/002/003 教程放入后，再检查归档和引用关系。

---

## 6. 当前状态

```text
已完成：五大分类目录骨架、索引文件
未完成：现有文档迁移、教程归档、问答/决策/面试/交付内容
当前重点：等待 TASK-001/002/003 学习教程放入 01-learning 对应目录
```

当前不移动、不删除、不覆盖任何现有文档；不修改业务代码；不开始 TASK-004 或前端开发。
