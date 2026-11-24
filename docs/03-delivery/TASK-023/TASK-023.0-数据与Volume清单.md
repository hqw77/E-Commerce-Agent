# TASK-023.0 数据与 Volume 清单

> 日期：2026-11-24  
> 本轮只盘点，不删除、不重建、不执行 migration。

## 1. Docker Compose

### 开发环境

`docker-compose.yml`：

| 服务 | 端口 | Volume |
|---|---|---|
| MySQL 8.0 | 3307 -> 3306 | `mysql_data` |
| Redis 7 | 6380 -> 6379 | `redis_data` |
| Qdrant v1.20.1 | 6333, 6334 | `qdrant_data` |
| app | 8000 | 无业务数据卷 |

### 生产环境

`docker-compose.prod.yml`：

| 服务 | 端口 | Volume |
|---|---|---|
| MySQL | 内部 3306 | `mysql_data_prod` |
| Redis | 内部 6379 | `redis_data_prod` |
| Qdrant | 内部 6333 | `qdrant_data_prod` |
| migrate | 无 | 无 |
| app | 内部 8000 | `uploads_data_prod`, `model_cache_prod` |
| nginx | 8080 -> 80 | 无 |

生产 Compose 当前未启动，本轮未启动生产栈。

## 2. Docker Volume

```text
e-ecommerce-agent_mysql_data
e-ecommerce-agent_redis_data
e-ecommerce-agent_qdrant_data

ecommerce-agent-prod_mysql_data_prod
ecommerce-agent-prod_redis_data_prod
ecommerce-agent-prod_qdrant_data_prod
ecommerce-agent-prod_uploads_data_prod
ecommerce-agent-prod_model_cache_prod
```

生产模型缓存此前盘点约 8.5GB、64 个文件；本轮没有重新计算。

## 3. MySQL 实例

### 3306 宿主机 MySQL

```text
status: running
database: ecommerce_agent
alembic: no new upgrade operations
```

当前行数：

```text
users: 0
categories: 0
products: 0
skus: 0
inventory: 0
inventory_transactions: 0
orders: 0
after_sales: 0
payments: 0
refunds: 0
knowledge_documents: 0
knowledge_document_versions: 0
knowledge_chunks: 0
```

判断：3306 是空业务库，不能用于当前演示；不能把“空”直接解释为数据被删除。

### 3307 Docker MySQL

```text
container: e-ecommerce-agent-mysql-1
status: running
port: 127.0.0.1:3307
```

当前行数：

```text
users: 3
categories: 2
products: 1
skus: 1
inventory: 1
inventory_transactions: 5
orders: 2
order_items: 2
payments: 0
refunds: 0
after_sales: 0
knowledge_documents: 1
knowledge_document_versions: 2
knowledge_chunks: 2
```

这是当前可恢复的 TASK-015/020.A 测试数据来源。

已生成逻辑备份：

```text
D:\Backups\E-Commerce-Agent\TASK-023.0_20261124_195424\data\mysql-3307.sql
```

## 4. Redis

```text
container: e-ecommerce-agent-redis-1
status: running
port: 127.0.0.1:6380
volume: e-ecommerce-agent_redis_data
```

Redis 数据是短期状态，包括限流、会话锁、会话历史和 Confirm pending，不是业务事实的最终来源。

## 5. Qdrant

```text
container: e-ecommerce-agent-qdrant-1
status: running
port: 127.0.0.1:6333
collection: knowledge_chunks_bge_m3_v1
status: green
points_count: 2
indexed_vectors_count: 0
segments_count: 8
hnsw_config.indexing_threshold: 10000
```

点数量低于 HNSW 索引阈值，不等于 Collection 损坏。当前不重建、不删除 Point。

## 6. 上传文件

宿主机：

```text
storage/knowledge/
文件数: 7
总大小: 约 5.5KB
```

已复制到：

```text
D:\Backups\E-Commerce-Agent\TASK-023.0_20261124_195424\data\uploads\
```

## 7. 环境变量文件

存在：

```text
.env               1035 bytes
.env.production    1017 bytes
.env.example       2895 bytes
.env.production.example 1761 bytes
```

本轮没有读取或输出其中的值，没有将 `.env` 或 `.env.production` 放入备份。

## 8. 数据恢复优先级

```text
第一优先: 保留现有 3307 Volume
第二优先: 使用 data/mysql-3307.sql 逻辑备份
第三优先: 在明确批准后使用 seed 创建新测试数据
禁止: 用 3306 空库覆盖 3307，或重建 Volume
```

Qdrant 和上传文件应继续使用现有 Volume/宿主目录，不单独重建。

## 9. 结论

```text
可恢复测试数据: 3307 中存在
3306: 空业务库
Redis: 运行中
Qdrant: 运行中, 2 points, indexed=0
上传文件: 7 个, 已备份
生产 Volume: 保留, 未启动
删除/重建: 无
```
