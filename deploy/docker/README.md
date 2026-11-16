# TASK-016 本地生产化 Docker Compose

## 1. 前置条件

- Docker Compose v2+
- 本地 `.env.production`，不要提交 Git
- 已初始化 `ecommerce-agent-prod_model_cache_prod` 模型缓存卷

## 2. 创建环境文件

```powershell
Copy-Item .env.production.example .env.production
# 编辑 .env.production，填入强密码、JWT Secret 和本地 DeepSeek Key
```

`.env.production` 已被 `.gitignore` 忽略，不能提交。

## 3. 初始化 BGE-M3 模型缓存

生产卷是 external volume，Compose 不会自动创建或删除它。

```powershell
docker volume create ecommerce-agent-prod_model_cache_prod

docker run --rm `
  -v "D:/path/to/.cache/huggingface:/source:ro" `
  -v "ecommerce-agent-prod_model_cache_prod:/target" `
  alpine sh -c "cp -a /source/. /target/"
```

该命令只复制缓存，不删除或覆盖原始缓存。

## 4. 启动

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

唯一宿主机入口：

```text
http://127.0.0.1:8080
```

## 5. 迁移

`migrate` 是独立一次性服务，应用启动前必须完成。

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production logs migrate
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate `
  python -m alembic -c backend/alembic.ini current
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate `
  python -m alembic -c backend/alembic.ini check
```

不要在 app 启动命令中自动执行 Alembic。

## 6. 查看日志

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f app
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f nginx
```

## 7. 停止

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production down
```

禁止使用：

```text
docker compose down -v
```

该命令会删除 MySQL、Redis、Qdrant、上传文件和模型缓存卷。

## 8. 当前端口和网络

```text
nginx: 127.0.0.1:8080 -> 80
app:   内部 8000，无宿主机端口
mysql/redis/qdrant: 无宿主机端口
```

网络：

```text
edge: nginx + app
data: app + mysql + redis + qdrant，internal=true
```

## 9. 备份和恢复

TASK-016 只验证本地持久化，不包含正式备份恢复演练；完整备份恢复属于 TASK-018。
