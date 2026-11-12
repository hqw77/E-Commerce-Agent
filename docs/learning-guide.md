# 项目代码学习启动报告

> 本文档记录 E-Commerce Agent 项目当前真实状态、TASK-001/002/003 的文件结构、TASK-001 学习顺序以及第一个推荐学习文件。
>
> 后续代码讲解将以本文档为索引，并严格以当前仓库真实代码为依据。
>
> 学习进度与问题记录见：`docs/learning-log.md`。

---

## 1. 报告生成时的 Git 状态

> 说明：本文档自身提交后，`HEAD` 会继续前进一个文档提交；以下记录的是报告生成时的代码基线。

```text
当前分支: feature/product-inventory
HEAD:     b87424f
远程:     origin/feature/product-inventory（已同步）
工作区:   clean
```

分支关系：

```text
main / feature/user-login     3292b85   TASK-002 收尾 + TASK-003.1 设计
feature/product-inventory     b87424f   TASK-003.2 ~ TASK-003.5
```

注意：TASK-003.2 ~ TASK-003.5 目前在功能分支，尚未合并到 `main`。

最近提交：

```text
b87424f feat(inventory): implement inventory operations and ledger
c296327 feat(product): implement product and SKU management APIs
e099e34 feat(category): implement category management APIs
847d03b feat(product): add product and inventory data models and migration
3292b85 docs(product): add TASK-003.1 product and inventory design baseline
3ff0640 feat(auth): complete authentication and refresh session flow
```

---

## 2. 当前真实目录树

```text
app/
  main.py
  api/
    dependencies.py
    router.py
    v1/
      auth.py
      health.py
      admin/
        categories.py
        products.py
        skus.py
        inventory.py
        validation.py
  core/
    config.py
    exceptions.py
    exception_handlers.py
    logging.py
    security.py
    token.py
  db/
    base.py
    session.py
    redis.py
  middleware/          # 只有空 __init__.py
  models/
    user.py
    refresh_session.py
    category.py
    product.py
    sku.py
    inventory.py
    inventory_transaction.py
  repositories/
    user.py
    refresh_session.py
    category.py
    product.py
    sku.py
    inventory.py
    inventory_transaction.py
  schemas/
    auth.py
    category.py
    product.py
    sku.py
    inventory.py
  services/
    auth.py
    user.py
    category.py
    product.py
    sku.py
    inventory.py
    transaction.py
  utils/               # 只有空 __init__.py

alembic/
  env.py
  versions/
    7bf01171c77c_create_users_table.py
    08b7848e6368_create_refresh_sessions_table.py
    c851e383d3fe_create_product_and_inventory_tables.py

tests/
  test_config.py
  test_database.py
  test_exceptions.py
  test_exception_handlers.py
  test_health.py
  test_logging.py
  test_main.py
  test_migrations.py
  test_product_models.py
  test_redis.py
  api/
    test_auth.py
    test_admin_dependency.py
  core/
    test_security.py
    test_token.py
  models/test_user.py
  repositories/test_user.py
  schemas/test_auth.py
  services/
    test_auth.py
    test_user.py
  integration/
    test_user_registration.py
    test_auth_flow.py
    test_auth_transactions.py
    test_category_api.py
    test_product_api.py
    test_product_schema.py
    test_inventory_api.py

docs/
  product-design.md   约 81 KB
  architecture.md     0 字节
  database.md         0 字节
  development.md      0 字节

根目录关键文件：
  Dockerfile
  docker-compose.yml
  alembic.ini
  pytest.ini
  requirements*.in / requirements*.txt
  .env.example
  README.md           0 字节
```

---

## 3. TASK-001/002/003 实际文件结构核对

### TASK-001 基础设施

实际对应：

- `app/main.py`：应用入口、lifespan、异常处理器注册、路由挂载。
- `app/core/config.py`：Pydantic Settings 配置。
- `app/core/logging.py`：structlog + 标准 logging。
- `app/core/exceptions.py`：统一异常基类。
- `app/core/exception_handlers.py`：FastAPI 全局异常处理。
- `app/db/base.py`：SQLAlchemy `Base`。
- `app/db/session.py`：异步引擎、Session 工厂、`get_db`。
- `app/db/redis.py`：Redis 连接池与客户端。
- `app/api/router.py`：聚合路由。
- `app/api/v1/health.py`：存活/就绪探针。
- `alembic/env.py`、`alembic.ini`、`versions/7bf...`：迁移基础设施。
- `Dockerfile`、`docker-compose.yml`。
- `pytest.ini` 与根目录测试文件。

**实际没有自定义中间件**：`app/middleware/` 只有空 `__init__.py`。学习计划中的“中间件”在当前代码中暂无内容，后续可以单独学习 FastAPI/Starlette 中间件机制，或等真正需要时再添加。

### TASK-002 用户认证

- `app/models/user.py`
- `app/models/refresh_session.py`
- `app/core/security.py`
- `app/core/token.py`
- `app/services/auth.py`、`app/services/user.py`
- `app/api/v1/auth.py`、`app/api/dependencies.py`
- `app/schemas/auth.py`
- `alembic/versions/08b...`
- `tests/api/test_auth.py`、`tests/core/test_token.py`、`tests/services/test_auth.py`、`tests/integration/test_auth_flow.py` 等

### TASK-003 商品与库存

- 模型：`category.py`、`product.py`、`sku.py`、`inventory.py`、`inventory_transaction.py`
- Repository：分类、商品、SKU、库存、流水
- Service：分类、商品、SKU、库存、事务上下文
- API：`admin/categories.py`、`admin/products.py`、`admin/skus.py`、`admin/inventory.py`
- 迁移：`c851e383d3fe`
- 测试：分类 14 个、商品/SKU 36 个、库存 15 个，以及模型/迁移测试

### TASK-004

当前仓库中**没有订单模块代码**，只有设计文档中的订单/快照/预留设计。

---

## 4. TASK-001 核心文件

| 文件 | 作用 |
|---|---|
| `app/main.py` | 创建 FastAPI app、注册 lifespan、异常处理器、路由 |
| `app/core/config.py` | 环境变量/.env/默认值配置，`settings` 单例 |
| `app/db/base.py` | 所有 ORM 模型的 Declarative Base |
| `app/db/session.py` | 异步 MySQL 引擎、Session 工厂、`get_db` |
| `app/db/redis.py` | Redis 连接池、客户端、关闭逻辑 |
| `app/core/logging.py` | structlog 初始化、日志格式 |
| `app/core/exceptions.py` | `AppException` 及业务异常体系 |
| `app/core/exception_handlers.py` | 统一 JSON 错误响应 |
| `app/api/router.py` | 汇总 health/auth/admin 路由 |
| `app/api/v1/health.py` | `/health/live`、`/health/ready` |
| `alembic/env.py` | Alembic 异步迁移环境 |
| `alembic.ini` | Alembic 配置入口 |
| `Dockerfile` | 生产镜像构建 |
| `docker-compose.yml` | MySQL/Redis/app 本地编排 |
| `pytest.ini` | pytest 路径与 asyncio 模式 |

---

## 5. 建议的 TASK-001 学习顺序

按真实依赖关系，建议：

1. **`app/main.py`** —— 先看应用如何启动。
2. **`app/core/config.py`** —— 理解配置从哪里来。
3. **`app/db/base.py`** —— 理解 ORM 基类。
4. **`app/db/session.py`** —— 理解异步引擎、Session、依赖注入。
5. **`app/db/redis.py`** —— 理解 Redis 连接池与生命周期。
6. **`app/core/logging.py`** —— 理解日志初始化。
7. **`app/core/exceptions.py` → `app/core/exception_handlers.py`** —— 理解统一异常体系。
8. **`app/api/router.py` → `app/api/v1/health.py`** —— 理解路由聚合和健康检查。
9. **`alembic.ini` / `alembic/env.py` / 第一个迁移** —— 理解迁移如何连接模型和数据库。
10. **`Dockerfile` / `docker-compose.yml`** —— 理解部署与本地依赖。
11. **`pytest.ini` + TASK-001 测试** —— 理解测试如何启动应用、连接真实 DB/Redis。

---

## 6. 第一个最适合开始学习的文件

### 推荐：`app/main.py`

原因：

1. 只有 39 行，是当前项目最短、最完整的“总入口”。
2. 它一次性暴露了应用生命周期的关键节点：
   - `setup_logging()`；
   - `lifespan` 启动时检查 Redis，关闭时释放连接；
   - 创建 `FastAPI`；
   - 注册全局异常处理器；
   - 挂载 `/api/v1` 路由。
3. 它天然连接后续所有基础设施文件：`config`、`logging`、`exception_handlers`、`redis`、`router`。
4. 从 `main.py` 开始，学习路径是“顺着真实调用关系走”，不是按目录死记。
5. 它还能说明一个真实运行行为：应用启动依赖 Redis，Redis 不可用时 lifespan 会失败。这是理解真实项目与测试差异的好切入点。

学习完 `main.py` 后，下一步建议进入 `app/core/config.py`，因为其他所有模块都依赖 `settings`。

---

## 7. 需要提前说明的实际情况

1. **文档不完整**：`README.md`、`docs/architecture.md`、`docs/database.md`、`docs/development.md` 当前都是 **0 字节**。目前唯一完整文档是 `docs/product-design.md`。因此后续讲解会以真实代码为主，不假设这些空白文档存在内容。
2. **没有自定义中间件**：`app/middleware/` 只有空包。学习计划里的“中间件”暂时没有对应代码。
3. **部分旧文件中文注释乱码**：例如 `alembic/env.py`、`tests/test_database.py` 中部分中文注释显示为乱码。代码逻辑不受影响；当前阶段不修改，避免学习期间引入无关变更。
4. **应用启动依赖 Redis**：`app/main.py` 的 lifespan 会执行 `redis_client.ping()`；使用 `TestClient(app)` 且不绕过 lifespan 时，Redis 必须可用。
5. **TASK-003.2~003.5 只在功能分支**：`main` 还停在设计基线；学习时请确认在 `feature/product-inventory` 分支。

---

## 8. 后续讲解约定

- 每次只讲一个文件或一个小功能。
- 先读取真实代码，再讲解。
- 讲解结构：
  1. 文件作用；
  2. 代码逐段讲解；
  3. 技术原理；
  4. 调用关系；
  5. 设计原因；
  6. 实际运行过程；
  7. 常见问题；
  8. 面试表达；
  9. 理解检查。
- 先讲解，再提问；不直接替学习者回答理解检查题。
- 不修改代码，不重构，不提前开始 TASK-004。
