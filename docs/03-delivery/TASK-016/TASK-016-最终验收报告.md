# TASK-016 最终验收报告

> 日期：2026-11-17  
> 分支：`feature/task-004-order`  
> 状态：本地生产化实施完成，存在明确未验证项  
> 真实支付宝沙箱：不在本任务验证范围，仍为 `SKIPPED_CREDENTIALS`

## 1. 结论

TASK-016 已完成本地生产级 Docker Compose 部署：

- 生产 Compose 独立于开发 Compose；
- 前端由 Nginx 提供静态资源并反向代理 `/api/`；
- Backend 与 Agent 仍是一个 FastAPI 服务；
- MySQL、Redis、Qdrant 使用独立生产卷；
- 上传文件和 BGE-M3 缓存使用持久化卷；
- Alembic 由独立一次性 `migrate` 服务执行；
- Nginx 是唯一宿主机入口 `127.0.0.1:8080`；
- MySQL、Redis、Qdrant 无宿主机端口；
- Backend 以 `appuser` 非 root 运行；
- 生产 E2E、业务联调、缓存复用和持久化验证通过；
- 开发 Compose 和 TASK-014/015 测试流程保留。

## 2. 新增和修改文件

### 新增

```text
docker-compose.prod.yml
frontend/Dockerfile
deploy/nginx/default.conf
deploy/docker/README.md
.env.production.example
docs/03-delivery/TASK-016/TASK-016-最终验收报告.md
```

### 修改

```text
backend/Dockerfile
.dockerignore
.gitignore
frontend/e2e/knowledge.spec.ts
README.md
docs/README.md
docs/PROJECT-STATUS.md
```

### 本地生成、未提交

```text
.env.production
```

`.env.production` 已被 Git 忽略；`.env.production.example` 已放行并提交占位符。

## 3. 生产服务和网络

```text
nginx   127.0.0.1:8080 -> 80
app     内部 8000
migrate 一次性任务
mysql   内部 3306
redis   内部 6379
qdrant  内部 6333
```

网络：

```text
edge: nginx, app
data: app, mysql, redis, qdrant
data.internal=true
```

`app` 同时加入 edge 和 data，保留访问 DeepSeek HTTPS 的能力。

验证结果：

```text
MySQL/Redis/Qdrant 无宿主机端口
只有 nginx 暴露 127.0.0.1:8080
```

## 4. Volume 持久化映射

| Volume | 容器路径 | 内容 |
|---|---|---|
| `mysql_data_prod` | `/var/lib/mysql` | MySQL |
| `redis_data_prod` | `/data` | Redis AOF |
| `qdrant_data_prod` | `/qdrant/storage` | Qdrant |
| `uploads_data_prod` | `/app/data/uploads` | RAG 上传文件 |
| `model_cache_prod` | `/app/.cache/huggingface` | BGE-M3 缓存 |

`model_cache_prod` 是 external volume，需先创建/初始化；Compose 不会自动删除它。

## 5. MySQL 用户和权限

生产数据库：

```text
ecommerce_agent
```

应用用户：

```text
ecommerce_app
```

验证到的授权：

```text
GRANT USAGE ON *.* TO `ecommerce_app`@`%`
GRANT ALL PRIVILEGES ON `ecommerce_agent`.* TO `ecommerce_app`@`%`
```

说明：

- root 只用于 MySQL 容器初始化和 DBA 操作；
- app 和 migrate 使用 `ecommerce_app`；
- app 容器的 `MYSQL_ROOT_PASSWORD` 已被空白覆盖，运行时没有 root 凭据；
- migration 使用同一个专用用户，具备该数据库迁移所需权限。

## 6. Alembic 迁移

新增独立 `migrate` 服务：

```text
python -m alembic -c backend/alembic.ini upgrade head
```

启动顺序：

```text
mysql healthy
  -> migrate 完成
  -> app 启动
  -> nginx 启动
```

迁移结果：

```text
7bf01171c77c
08b7848e6368
c851e383d3fe
22a36fc5af9c
5f14d68fcbd1
b96d3aae8b3d
```

验证：

```text
alembic current: b96d3aae8b3d (head)
alembic check: No new upgrade operations detected.
```

app 启动命令仍然只有 uvicorn，没有自动 migration；未新增 migration 文件。

## 7. BGE-M3 缓存迁移和复用

源缓存：

```text
D:/github_repository/E-ecommerce-agent/.cache/huggingface
文件数：64
表观总大小：约 18.2GB
```

目标：

```text
ecommerce-agent-prod_model_cache_prod
文件数：64
磁盘占用：8.6GB（硬链接去重后）
incomplete 文件：0
```

关键文件校验：

```text
config.json SHA256             source == target
pytorch_model.bin SHA256       source == target
```

哈希值：

```text
config.json: 26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa
pytorch_model.bin: b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38
```

原始缓存未删除、未移动、未覆盖。

应用验证：

- 生产知识库上传/索引成功；
- app 强制重建后缓存仍为 64 文件、8.6GB；
- 未出现完整模型重新下载日志；
- 发布后 `/knowledge/retrieve` 返回实际 chunk。

## 8. 上传文件持久化

验证时上传文件数：

```text
/app/data/uploads: 5 个文件
```

执行：

```text
docker compose ... up -d --force-recreate app
```

之后：

```text
/app/data/uploads: 5 个文件
/app/.cache/huggingface: 8.6GB / 64 文件
```

说明容器重建后上传文件和模型缓存均保留。

测试数据清理后：

```text
/app/data/uploads: 0 个文件
```

## 9. MySQL/Redis/Qdrant 持久化

重启 MySQL、Redis、Qdrant 后：

```text
users=2
products=1
orders=2
knowledge_documents=1
```

重启后 app 恢复 healthy，Nginx 和 API 正常。

之后清理了 TASK-016 测试数据：

```text
users=0
products=0
orders=0
knowledge_documents=0
```

没有删除 Volume。

## 10. 健康检查

```text
mysql    healthy
redis    healthy
qdrant   healthy
app      healthy
nginx    healthy
```

```text
http://127.0.0.1:8080/healthz                 200
http://127.0.0.1:8080/                          200
http://127.0.0.1:8080/api/v1/health/live       200
http://127.0.0.1:8080/api/v1/health/ready      200
```

## 11. 生产业务验收

Playwright 直接访问生产 Nginx：

```text
E2E_BASE_URL=http://127.0.0.1:8080
7 passed
```

覆盖：

- 认证和路由保护；
- 管理员登录、Token Refresh、登出；
- 普通用户管理员 API 403；
- 分类、商品、库存、订单、售后；
- Agent 查询、Prepare、Confirm；
- 知识库上传新版本、发布、非空检索。

生产 API 同时验证：

- 登录；
- 分类/商品/SKU/库存；
- 订单创建和取消；
- 知识库上传/发布/检索；
- Agent Tool/Prepare/Confirm。

## 12. 开发环境兼容性

开发 Compose 未修改，仍运行：

```text
app     0.0.0.0:8000
mysql   127.0.0.1:3307
redis   127.0.0.1:6380
qdrant  127.0.0.1:6333/6334
```

开发环境健康：

```text
/api/v1/health/live   200
/api/v1/health/ready  200
```

全量测试：

```text
pytest:     336 passed
Ruff:       passed
Mypy:       128 source files passed
Vitest:     6 passed
typecheck:  passed
lint:       passed
build:      passed
Alembic:    no new operations
```

## 13. 镜像检查

Backend：

```text
user: appuser (uid 100)
/app/.env: 不存在
/app/backend/tests: 不存在
/app/agent/tests: 不存在
```

Frontend：

```text
nginx:1.27-alpine
静态文件存在
npm ci + typecheck + lint + test + build 构建阶段通过
```

Nginx 镜像使用官方镜像，master 进程为 root；Backend 已满足非 root 要求。

## 14. 未完成、失败、跳过

1. 真实支付宝沙箱支付/通知/退款/退款查询：TASK-015 仍未验证，无凭证。
2. RAG No-answer Accuracy 仍为 0，属于 TASK-015 未通过项，TASK-016 未修改检索策略。
3. Agent 真实模型仍为 10/30 抽样，未在 TASK-016 重跑全量评估。
4. 正式 HTTPS、域名、云服务器：不属于 TASK-016，属于 TASK-017。
5. 备份恢复演练：属于 TASK-018。
6. Nginx master root：官方镜像默认行为；Backend 非 root。
7. `model_cache_prod` 是 external volume，新环境必须先创建并初始化，否则 Compose 启动会失败。
8. 生产数据已清理，当前生产库为空，仅保留 schema 和 Volume。

## 15. Git

```text
branch: feature/task-004-order
HEAD:   7d3b836
staged: 0
commit/push/reset/clean: 未执行
```

未输出真实 DeepSeek Key、JWT Secret、MySQL 密码或支付宝私钥。

## 16. 验收判定

```text
TASK-016 本地生产化部署：通过
镜像构建：通过
Nginx/静态资源/API 代理：通过
迁移服务：通过
网络隔离和端口：通过
非 root Backend：通过
数据持久化：通过
BGE-M3 缓存迁移和复用：通过
开发环境兼容：通过
真实支付沙箱：未验证（不属于本任务）
HTTPS 和公网部署：未开始（TASK-017）
```
