# 12 订单库存代码阅读路线

> 目标：40 分钟内读懂“创建订单 → 预占库存 → 取消释放 → 发货扣减”这条主链路，并能用它回答面试追问。
>
> 阅读原则：不要从文件第一行读到最后一行，而是顺着一次请求的调用链读。

---

## 1. 一句话总结

```text
下单：创建订单 + 创建订单项 + 预占库存，三件事在同一个事务里。
取消：释放预占。
发货：把预占转成实际扣减。
```

库存字段：

```text
total_quantity     总库存
reserved_quantity  已预占
available          可用库存 = total - reserved
```

---

## 2. 调用链总图

```text
POST /api/v1/orders
  -> api/v1/orders.py::create_order
  -> OrderService.create_order
     -> 幂等检查
     -> 校验 SKU/商品/库存
     -> transaction_context
        -> 创建 Order
        -> 创建 OrderItem
        -> InventoryService.reserve
           -> 锁库存行
           -> InventoryRepository.reserve
              -> UPDATE inventory
           -> 写库存流水
  -> 返回订单详情
```

取消：

```text
POST /orders/{order_no}/cancel
  -> OrderService.cancel_order
     -> 锁订单 + 校验归属
     -> 校验状态
     -> InventoryService.release
     -> Order.status = CANCELLED
```

发货：

```text
POST /admin/orders/{order_no}/ship
  -> OrderService.ship
     -> 锁订单
     -> 校验状态
     -> InventoryService.deduct_reserved
     -> fulfillment_status = SHIPPED
```

---

## 3. 四个文件的职责

| 文件 | 职责 | 阅读重点 |
|---|---|---|
| `backend/app/api/v1/orders.py` | HTTP 入口 | 收参数、取当前用户、调用 Service |
| `backend/app/services/order.py` | 订单业务和事务 | 幂等、创建订单、取消、发货 |
| `backend/app/services/inventory.py` | 库存业务 | reserve / release / deduct_reserved |
| `backend/app/repositories/inventory.py` | 库存 SQL | 原子 UPDATE、WHERE 条件 |

先记住一句话：

```text
API 不写业务，Service 管流程和事务，Repository 管 SQL。
```

---

## 4. 第一遍：只看主流程

### 第 1 步：API 入口（5 分钟）

打开：

[orders.py:31](backend/app/api/v1/orders.py#L31)

核心只有三行：

```python
service = OrderService(session)
order = await service.create_order(user_id=user.id, request=request)
return order_response(order)
```

确认：

```text
用户身份来自 CurrentUser
API 不直接操作数据库
业务逻辑在 OrderService
```

然后看取消入口：

[orders.py:87](backend/app/api/v1/orders.py#L87)

同样只是调用 Service。

---

### 第 2 步：OrderService.create_order（15 分钟）

打开：

[order.py:142](backend/app/services/order.py#L142)

把函数拆成 5 块，不要一次读完。

#### ① 幂等检查（160～168 行）

```python
fingerprint = self._fingerprint(request)
existing = await self._existing_or_conflict(
    user_id=user_id,
    idempotency_key=request.idempotency_key,
    fingerprint=fingerprint,
)
if existing is not None:
    return existing
```

含义：

```text
同一个幂等键 + 相同参数 -> 返回旧订单
同一个幂等键 + 不同参数 -> 409
```

相关唯一约束：

```text
orders(user_id, idempotency_key) 唯一
```

#### ② 校验商品和库存（170～172 行）

```python
lines = await self._load_purchase_lines(request)
total_amount = money(sum(...))
```

它做的是预检查：

```text
SKU 存在且 ACTIVE
商品存在且 ACTIVE
库存可用量足够
计算订单项金额
```

注意：

```text
这里只是预检查，真正的并发安全在 InventoryRepository.reserve。
```

#### ③ 核心事务（174～226 行）

```python
async with transaction_context(self.session):
    order = Order(...)
    await self.orders.create(order)

    for ...:
        await self.items.create(...)

    for item in ...:
        await self.inventory.reserve(...)
```

同一个事务里做三件事：

```text
1. 创建订单
2. 创建订单项
3. 预占库存
```

任何一步失败，整体回滚。

订单创建时：

```text
status = CREATED
fulfillment_status = UNSHIPPED
```

注意：

```text
订单不再写 payment_status、paid_amount、refunded_amount、paid_at 等支付遗留字段。
当前项目没有支付流程，订单创建只关注业务状态、履约状态、金额和收货信息。
```

#### ④ 并发兜底（227～243 行）

```python
except IntegrityError as exc:
    await self.session.rollback()
    ...
    existing = await self.orders.get_by_user_and_key(...)
```

两个请求同时提交时：

```text
唯一约束报错
-> 回滚
-> 按幂等键重新读取旧订单
```

#### ⑤ 返回详情（245 行）

```python
return await self._detail(order.order_no)
```

---

### 第 3 步：库存预占（10 分钟）

打开：

[inventory.py:458](backend/app/services/inventory.py#L458)

只看 `reserve`：

```python
await self._locked_inventory(sku_id)
rowcount = await self.repository.reserve(sku_id, quantity)
if rowcount != 1:
    raise ConflictException(...)
```

含义：

```text
先锁库存行
再执行原子 UPDATE
受影响行数不是 1，说明库存不足
```

打开：

[inventory.py:102](backend/app/repositories/inventory.py#L102)

核心 SQL：

```python
update(Inventory)
.where(
    Inventory.sku_id == sku_id,
    Inventory.total_quantity - Inventory.reserved_quantity >= quantity,
)
.values(reserved_quantity=Inventory.reserved_quantity + quantity)
```

**防超卖的核心在这里。**

不是：

```text
先 SELECT 查库存
再在 Python 里判断
再 UPDATE
```

而是：

```text
一条 UPDATE 同时判断可用库存并增加预占量
```

---

### 第 4 步：取消和发货（10 分钟）

取消：

[cancel_order:310](backend/app/services/order.py#L310)

```text
锁订单 + 校验归属
校验状态
逐行 release
订单改为 CANCELLED
```

发货：

[ship:354](backend/app/services/order.py#L354)

```text
锁订单
校验状态
逐行 deduct_reserved
履约状态改为 SHIPPED
```

对应 Repository：

[release:115](backend/app/repositories/inventory.py#L115)

```python
reserved_quantity = reserved_quantity - quantity
```

[deduct_reserved:128](backend/app/repositories/inventory.py#L128)

```python
total_quantity = total_quantity - quantity
reserved_quantity = reserved_quantity - quantity
```

一句话记忆：

```text
预占：reserved +
取消：reserved -
发货：total -，reserved -
```

---

## 5. 库存变化表

| 操作 | total_quantity | reserved_quantity | 可用库存 |
|---|---:|---:|---:|
| 创建订单并预占 | 不变 | +qty | -qty |
| 取消订单并释放 | 不变 | -qty | +qty |
| 发货并扣减 | -qty | -qty | 不变 |

例子：

```text
初始：total=10, reserved=0, available=10
下单 2：total=10, reserved=2, available=8
取消：  total=10, reserved=0, available=10
再次下单 2 并发货：
        total=8, reserved=0, available=8
```

---

## 6. 第二遍：看失败路径

第一遍只看成功路径，第二遍看异常：

```text
SKU 不存在 / 商品下架
库存不足
幂等键参数冲突
订单状态不允许取消
订单状态不允许发货
释放时 reserved 不足
扣减时 total/reserved 不足
```

重点看每个 `raise ConflictException` 前的条件。

面试时能说出：

```text
不是所有失败都返回 500。
业务冲突返回 409，资源不存在返回 404，参数问题返回 422。
```

---

## 7. 第三遍：看并发和幂等

只问三个问题：

### 问题 1：两个请求同时用同一个幂等键下单

```text
唯一约束只允许一个成功
另一个触发 IntegrityError
回滚后按幂等键读取旧订单
```

### 问题 2：两个请求同时买最后一件库存

```text
UPDATE 的 WHERE 条件保证只有一个 rowcount=1
另一个 rowcount=0，返回库存不足
```

### 问题 3：下单后取消，再发货

```text
取消要求状态是 CREATED/PENDING_PAYMENT
取消后状态是 CANCELLED
发货要求 CREATED/PAID 且 UNSHIPPED
所以已取消订单不能发货
```

---

## 8. 读完后要能回答的 10 个问题

```text
1. 下单请求从哪个函数进入？
2. 哪三样东西在同一个事务里？
3. 幂等检查在事务前还是事务内？
4. 库存预占发生在订单创建前还是后？
5. 并发重复下单怎么兜底？
6. 防超卖的核心 SQL 在哪？
7. 取消订单对库存做了什么？
8. 发货对库存做了什么？
9. 为什么订单状态和履约状态要分开？
10. 为什么 Repository 不 commit？
```

参考回答：

```text
1. api/v1/orders.py 的 create_order。
2. Order、OrderItem、库存预占。
3. 事务前先查幂等键；并发冲突在事务异常里兜底。
4. 先创建 Order 和 OrderItem，再逐行 reserve。
5. 唯一约束 + IntegrityError + 回滚后按 key 回读。
6. InventoryRepository.reserve 的原子 UPDATE。
7. 逐行 release，reserved 减少。
8. CREATED 订单逐行 deduct_reserved，total 和 reserved 同时减少。
9. 主状态表达业务生命周期，履约状态表达物流进度。
10. 事务边界由 Service 控制，Repository 只 flush。
```

---

## 9. 不要第一遍读的东西

```text
_fingerprint 内部实现
_existing_or_conflict 内部实现
_load_purchase_lines 每一行
_ledger 内部
_same_fingerprint
日志和异常栈
```

这些第二遍再看。

第一遍只跟主流程，否则很容易陷进细节。

---

## 10. 验证自己是否读懂

合上文档，画出：

```text
POST /orders
  -> create_order
  -> OrderService.create_order
     -> 幂等
     -> 校验
     -> 事务
        -> Order
        -> OrderItem
        -> reserve
           -> 锁行
           -> UPDATE
           -> 流水
```

如果画不出来，回到第 4 节重读一遍。

---

## 11. 一句话面试总结

> 下单时，订单、订单项和库存预占在同一个事务里完成；取消释放预占，发货把预占转成实际扣减。幂等键和唯一约束防止重复下单，行锁和带条件的原子 UPDATE 防止超卖。
