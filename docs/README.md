# 清风数码 E-Commerce Agent 面试文档

> 一套面向面试讲解的当前项目文档。
> 只记录已经实现的能力，不把设计稿、历史计划当功能。

## 推荐阅读顺序

```text
01 项目总览
02 整体架构
03 核心业务流程
04 Agent 与 RAG
05 数据模型与 API
06 测试与质量
07 面试问答
08 现场演示脚本
09 面试学习规划
10 Agent 架构升级分析（阶段 0 快照）
11 初级全栈面试速成执行手册
12 订单库存代码阅读路线
13 订单库存四条主链路面试总结
14 JWT 与 RBAC 代码阅读与面试总结
15 Agent 工具与审批完整教程
16 RAG 完整教程与效果评估
```

## 文档索引

- [01 项目总览](01-project-overview.md)
- [02 整体架构](02-architecture.md)
- [03 核心业务流程](03-business-flows.md)
- [04 Agent 与 RAG](04-agent-and-rag.md)
- [05 数据模型与 API](05-data-and-api.md)
- [06 测试与质量](06-testing-and-quality.md)
- [07 面试问答](07-interview-qa.md)
- [08 现场演示脚本](08-demo-script.md)
- [09 面试学习规划](09-study-plan.md)
- [10 Agent 架构升级分析](10-agent-upgrade-analysis.md)
- [11 初级全栈面试速成执行手册](11-interview-crash-plan.md)
- [12 订单库存代码阅读路线](12-order-inventory-reading-guide.md)
- [13 订单库存四条主链路面试总结](13-order-inventory-four-flows.md)
- [14 JWT 与 RBAC 代码阅读与面试总结](14-jwt-rbac-reading-guide.md)
- [15 Agent 工具与审批完整教程](15-agent-tool-approval-guide.md)
- [16 RAG 完整教程与效果评估](16-rag-complete-guide.md)

## 项目一句话

一个本地可运行的双端电商智能体 MVP：

```text
消费者商城 + AI 导购/客服 + 运营后台
```

## 当前基线

```text
商品：10 个（P001–P010）
SKU：10 个
分类：4 个
订单：12 个
售后：4 个
知识文档：7 篇
```

## 相关入口

- [项目 README](../README.md)
- [后端 API 文档](http://127.0.0.1:8000/docs)
- [商城](http://127.0.0.1:5173/shop)
- [运营后台](http://127.0.0.1:5173/dashboard)

## 边界

```text
未实现购物车
未实现支付
未实现普通用户地址簿
未做生产部署、HTTPS 和正式运维
```

阅读时请以源码和实际测试结果为准。