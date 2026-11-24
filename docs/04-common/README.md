# 04 公共环境

> 开发数据库默认使用 **MySQL 3307**。3306 是宿主机空库, 保留但不要覆盖 3307。

## 服务与端口

| 服务 | 地址 |
|---|---|
| Backend | `http://127.0.0.1:8000` |
| Frontend | `http://127.0.0.1:5173` |
| MySQL Docker | `127.0.0.1:3307` |
| MySQL 宿主机 | `127.0.0.1:3306` |
| Redis Docker | `127.0.0.1:6380` |
| Qdrant | `http://127.0.0.1:6333` |
| Nginx 生产预留 | `127.0.0.1:8080` |

## 启动顺序

```text
1. Docker Desktop
2. e-ecommerce-agent-mysql-1
3. e-ecommerce-agent-redis-1
4. e-ecommerce-agent-qdrant-1
5. Backend 8000
6. Frontend 5173
```

## Backend 启动

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD"
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3307"
$env:REDIS_HOST="127.0.0.1"
$env:REDIS_PORT="6380"
$env:RAG_QDRANT_URL="http://127.0.0.1:6333"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

不要用 3306 替代 3307。启动前确认数据库的 Alembic 版本; 未确认不要执行 upgrade。

## Frontend 启动

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

## 健康检查

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

`ready` 检查 MySQL 和 Redis。

## 环境变量

模板:

```text
.env.example
.env.production.example
```

真实 `.env` 和 `.env.production` 不提交、不输出。`.gitignore` 已忽略 `.env` 和 `.env.*`, 但保留 example。

## Docker Compose

```text
docker-compose.yml       开发依赖和应用
docker-compose.prod.yml  本地生产化栈, 本轮不启动
deploy/nginx/default.conf
```

禁止:

```text
docker compose down -v
docker volume rm
docker system prune
```

## 数据

- 3307: TASK-015/020.A 测试数据;
- 3306: 空业务库;
- Redis: 限流、锁、会话、Confirm pending;
- Qdrant: `knowledge_chunks_bge_m3_v1`, 2 points;
- 上传: `storage/knowledge`, 7 files。
