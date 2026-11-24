# 09 历史归档

> 本目录不复制数据库 SQL、密钥或敏感数据。原始 TASK 报告保留在原位置, 此目录提供归档索引和后续迁移目标。

## 归档原则

1. 原始 TASK 报告不删除、不改写。
2. 历史设计即使描述旧实现, 也属于历史证据。
3. 当前有效结论提炼到专题文档时, 必须记录来源。
4. 迁移只复制, 不覆盖原文件。
5. 任何删除/合并需负责人确认。

## 归档来源

```text
docs/02-design/              历史总体设计、TASK-004.1/005/006/007/008-013/014/015/016
docs/03-delivery/            TASK-001～023.0 交付/验收
docs/04-testing/             TASK-014/015 测试与评估
docs/architecture.md         V1.2 安全基线
docs/learning-guide.md       旧学习入口
docs/learning-log.md         旧学习日志
docs/product-design.md       TASK-003.1 商品设计
docs/database.md             空文件
docs/development.md          空文件
```

## 归档目标

```text
docs/09-archive/original/02-design/
docs/09-archive/original/03-delivery/
docs/09-archive/original/04-testing/
docs/09-archive/original/root/
docs/09-archive/original/frontend/
docs/09-archive/original/deploy/
```

本轮不执行复制, 等负责人确认目录映射后再迁移。

## 不可归档内容

- `.env` / `.env.production` 值;
- MySQL dump;
- 上传文件;
- 任何 Token/密码/密钥;
- 未经审核的测试数据。
