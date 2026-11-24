# TASK-023.0 本地环境恢复方案

> 日期：2026-11-24  
> 本方案只做恢复准备，不执行迁移、不重建数据、不清理 Volume。

## 1. 当前环境结论

```text
Docker Desktop: 可启动, 当前已启动
MySQL 3307: 运行中
Redis 6380: 运行中
Qdrant 6333: 运行中
MySQL 3306: 宿主机服务运行中, 但业务库为空
Backend 8000: 未运行
Frontend 5173: 未运行
```

## 2. 推荐使用的数据库

优先使用：

```text
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
```

原因：

- 3307 有可恢复的 TASK-015/020.A 测试数据；
- 3306 当前业务表为 0 行；
- 不能用空库覆盖 3307；
- 不要为了恢复演示而删除 3307 Volume。

## 3. 启动顺序

### 第 1 步: Docker Desktop

确认 Docker daemon 可用：

```powershell
docker info
```

### 第 2 步: 开发依赖容器

只启动开发 MySQL、Redis、Qdrant：

```powershell
docker start e-ecommerce-agent-mysql-1 e-ecommerce-agent-redis-1 e-ecommerce-agent-qdrant-1
```

不要启动生产 Compose，不要执行 `down -v`。

验证：

```text
MySQL 127.0.0.1:3307
Redis 127.0.0.1:6380
Qdrant 127.0.0.1:6333
```

### 第 3 步: Backend

使用 3307/6380/6333：

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3307"
$env:REDIS_HOST="127.0.0.1"
$env:REDIS_PORT="6380"
$env:RAG_QDRANT_URL="http://127.0.0.1:6333"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

本轮不执行 Alembic migration。若 schema 已存在，直接启动；若 schema 不存在，先停下来确认恢复方案。

### 第 4 步: Frontend

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

验证：

```text
http://127.0.0.1:8000/api/v1/health/live
http://127.0.0.1:8000/api/v1/health/ready
http://127.0.0.1:5173/
```

## 4. 端口与冲突

| 端口 | 当前用途 | 冲突判断 |
|---:|---|---|
| 3306 | 宿主机 MySQL | 与 Docker 3307 不冲突, 但数据为空 |
| 3307 | 开发 Docker MySQL | 推荐 |
| 6379 | 历史 Redis | 当前未监听 |
| 6380 | 开发 Docker Redis | 推荐 |
| 6333 | Qdrant HTTP | 推荐 |
| 6334 | Qdrant gRPC | 推荐 |
| 8000 | Backend | 当前未监听 |
| 5173 | Vite | 当前未监听 |
| 8080 | 生产 Nginx | 本轮不启动 |

不要同时把 Backend 指向 3306 和 3307；先确认目标数据库。

## 5. 测试数据恢复方案

### 首选

使用现有 3307 Volume：

```text
TASK015/020.A 测试用户、商品、SKU、订单、知识文档
```

### 次选

仅在明确批准后恢复逻辑 dump：

```text
D:\Backups\E-Commerce-Agent\TASK-023.0_20261124_195424\data\mysql-3307.sql
```

恢复前必须先确认目标数据库为空或已备份，不允许直接覆盖现有 3307 数据。

### 新测试数据

如果只是做新的演示，不要清理旧数据，使用独立前缀：

```text
TASK023-...
```

并通过现有 seed 脚本生成新数据。先确认脚本目标 DB，不要执行 `--cleanup`。

## 6. Qdrant 和上传文件

Qdrant：

```text
collection: knowledge_chunks_bge_m3_v1
points_count: 2
indexed_vectors_count: 0
```

当前不重建 Collection，不删除 Point。

上传文件：

```text
storage/knowledge: 7 files
backup/data/uploads: 7 files
```

恢复时优先保留现有宿主机目录，不要清空。

## 7. 恢复后的验证顺序

```text
1. /health/live
2. /health/ready
3. 登录
4. 查询商品/订单
5. 知识库列表
6. Agent 普通对话
7. Agent RAG
8. Agent READ Tool
9. Agent Prepare
10. Confirm
```

如果 health 失败，先检查 MySQL/Redis 端口和数据库选择，不要直接修改代码。

## 8. 禁止操作

```text
docker compose down -v
docker volume rm
docker system prune
删除数据库
重建数据库
Alembic migration
删除 uploads
覆盖 3307
清空 Redis/Qdrant
```
