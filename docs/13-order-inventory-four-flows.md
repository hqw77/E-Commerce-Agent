# 13 订单库存四条主链路面试总结

这篇文档只讲四件事：

1. 创建订单与库存预占
2. 取消订单与库存释放
3. 发货与库存扣减
4. 事务、锁与并发专项

阅读顺序建议：先看每节的“一句话”，再看调用链，最后看面试问答。

---

## 0. 先记住总图

创建订单：

POST /orders
→ create_order
→ OrderService.create_order
→ 幂等检查
→ 校验 SKU、商品、库存
→ 事务
→ 创建 Order
→ 创建 OrderItem
→ InventoryService.reserve
→ 锁库存行
→ InventoryRepository.reserve 原子 UPDATE
→ 写库存流水

取消订单：

POST /orders/{order_no}/cancel
→ OrderService.cancel_order
→ 锁订单并校验归属
→ 校验订单状态
→ InventoryService.release
→ Order.status = CANCELLED

发货：

POST /admin/orders/{order_no}/ship
→ OrderService.ship
→ 锁订单
→ 校验订单和履约状态
→ InventoryService.deduct_reserved
→ fulfillment_status = SHIPPED

库存字段：

total_quantity：总库存

reserved_quantity：已预占

available：可用库存，等于 total_quantity 减 reserved_quantity

---

# 一、创建订单与库存预占

## 1. 一句话

下单时，订单、订单项和库存预占在同一个事务里完成；预占失败会整体回滚，库存预占用行锁加带条件的原子 UPDATE 防止并发超卖。

## 2. 调用链

API 入口：backend/app/api/v1/orders.py 的 create_order

Service 入口：backend/app/services/order.py 的 OrderService.create_order

库存入口：backend/app/services/inventory.py 的 InventoryService.reserve

SQL 入口：backend/app/repositories/inventory.py 的 InventoryRepository.reserve

## 3. 分步解释

### 第一步：幂等检查

create_order 先计算请求指纹，再按 user_id 和 idempotency_key 查询旧订单。

同一个幂等键且参数一致，直接返回旧订单。

同一个幂等键但参数不同，返回 409。

这一步在事务之前完成，主要处理正常重试。

### 第二步：校验商品和库存

_load_purchase_lines 做预检查：

SKU 存在且状态为 ACTIVE

商品存在且状态为 ACTIVE

库存可用量足够

计算订单项金额

注意：这里只是预检查，真正的并发安全在库存 Repository 的原子 UPDATE。

### 第三步：开启事务

create_order 使用 transaction_context 包住核心写操作。

transaction_context 的行为：

如果当前 session 已经在事务中，复用它，结束时 commit，异常时 rollback。

如果当前没有事务，就新开一个事务。

订单、订单项和库存预占都在这个事务里。

### 第四步：创建订单和订单项

先创建 Order，初始状态：

status = CREATED

fulfillment_status = UNSHIPPED

订单不再写 payment_status、paid_amount、refunded_amount、paid_at 等支付遗留字段。

当前项目没有支付流程，订单创建只关注业务状态、履约状态、金额和收货信息。

然后逐行创建 OrderItem，保存商品和 SKU 快照：

product_no

product_name

sku_code

sku_attributes

unit_price

quantity

line_amount

订单项保存快照，商品之后改名或改价，不影响历史订单。

### 第五步：逐行预占库存

订单项创建完成后，按 sku_id 排序，逐行调用 InventoryService.reserve。

排序的目的是让同一批商品按稳定顺序加锁，降低死锁概率。

每个订单项使用独立的幂等键：

order:{order_id}:line:{item_id}:reserve

这样库存流水可以定位到具体订单项。

### 第六步：库存预占的实现

InventoryService.reserve 做三件事：

先通过 _locked_inventory 锁住库存行。

再调用 InventoryRepository.reserve 执行原子 UPDATE。

最后调用 _ledger 写库存流水。

Repository 的 SQL 逻辑：

UPDATE inventory

SET reserved_quantity = reserved_quantity + quantity

WHERE sku_id = 当前 SKU

AND total_quantity - reserved_quantity >= quantity

返回值是 rowcount。

rowcount 等于 1，预占成功。

rowcount 不等于 1，说明库存不足或库存行不存在，抛库存不足冲突。

关键点：不是先 SELECT 再在 Python 里判断，而是一条 UPDATE 同时判断可用库存并增加预占量。

### 第七步：失败回滚

如果库存预占失败，InventoryService 抛 ConflictException。

异常穿出 transaction_context，事务回滚。

订单和订单项不会留下半成品。

### 第八步：并发重复下单

两个请求同时使用同一个幂等键时，数据库唯一约束只允许一个成功。

另一个请求触发 IntegrityError。

create_order 捕获后先 rollback，再按幂等键读取旧订单。

如果旧订单的请求指纹和本次一致，返回旧订单。

如果指纹不一致，返回 409。

## 4. 库存变化

操作：创建订单并预占

total_quantity：不变

reserved_quantity：加 qty

available：减 qty

## 5. 失败场景

SKU 不存在或下架：抛业务冲突。

商品不存在或下架：抛业务冲突。

可用库存不足：库存预占 rowcount 为 0，抛库存不足。

幂等键复用但参数变化：返回 409。

并发重复下单：唯一约束兜底，回滚后回读旧订单。

## 6. 面试问答

问：为什么下单只预占，不直接扣库存？

答：订单还没发货，库存只是被锁定。取消可以释放，发货才真正出库。预占和扣减分开，才能支持取消。

问：为什么订单和库存要在同一个事务？

答：订单创建成功但库存预占失败，会留下无法履约的订单。放在同一事务里，任何一步失败都整体回滚。

问：库存预占发生在订单创建前还是后？

答：先创建订单和订单项，再逐行预占库存。因为库存流水需要订单和订单项的 ID 作为业务标识。

问：怎么防止重复下单？

答：幂等键加数据库唯一约束。正常重试直接返回旧订单，并发冲突靠唯一约束兜底。

问：怎么防止超卖？

答：库存 Repository 使用带条件的原子 UPDATE，只有可用库存足够时才增加 reserved_quantity，rowcount 为 0 就失败。

## 7. 一句话收尾

下单链路的核心是：订单、订单项和库存预占同事务；幂等键防重复；行锁加原子 UPDATE 防超卖。

---

# 二、取消订单与库存释放

## 1. 一句话

取消订单先锁订单并校验归属和状态，再逐行释放预占，最后把订单改成 CANCELLED；任何一步失败整体回滚。

## 2. 调用链

API 入口：backend/app/api/v1/orders.py 的 cancel_order

Service 入口：backend/app/services/order.py 的 OrderService.cancel_order

库存入口：backend/app/services/inventory.py 的 InventoryService.release

SQL 入口：backend/app/repositories/inventory.py 的 InventoryRepository.release

## 3. 分步解释

### 第一步：锁订单并校验归属

_lock_order_for_user 使用 for_update 锁住订单行。

如果订单不存在，或者订单不属于当前用户，统一按订单不存在处理，返回 404。

这里先锁订单，是为了让取消和发货这类状态变更串行，避免并发状态冲突。

### 第二步：校验订单状态

取消只允许：

CREATED

PENDING_PAYMENT

PENDING_PAYMENT 是历史兼容状态，新订单从 CREATED 开始。

其他状态返回 409，例如已发货、已完成、已取消。

这一步保证重复取消不会再次释放库存。

### 第三步：逐行释放预占

取出订单项，按 sku_id 排序。

每个订单项调用 InventoryService.release。

每个订单项使用独立幂等键：

order:{order_id}:line:{item_id}:release

### 第四步：释放库存的 SQL

Repository 的逻辑：

UPDATE inventory

SET reserved_quantity = reserved_quantity - quantity

WHERE sku_id = 当前 SKU

AND reserved_quantity >= quantity

rowcount 等于 1 才是成功。

rowcount 不等于 1，说明预占量不足，抛业务冲突。

### 第五步：修改订单状态

释放全部订单项后：

status = CANCELLED

cancelled_at = 当前时间

cancel_reason = 取消原因

然后保存订单。

### 第六步：失败回滚

如果任意一行释放失败，异常穿出 transaction_context，事务回滚。

订单仍然保持取消前的状态，不会出现“订单已取消但库存没释放”的半成品。

## 4. 库存变化

操作：取消订单并释放

total_quantity：不变

reserved_quantity：减 qty

available：加 qty

## 5. 失败场景

订单不存在或不属于当前用户：404。

订单已发货、已完成或已取消：409。

预占量不足：释放 rowcount 为 0，抛业务冲突。

重复取消：状态校验拦截，不会重复释放。

## 6. 面试问答

问：为什么取消要锁订单？

答：取消和发货都会改变订单状态，先锁订单可以让状态变更串行，避免并发下重复释放或状态覆盖。

问：为什么取消不直接删订单？

答：订单是业务记录，取消是状态变化，不是删除。订单项、库存流水和售后都可能还要引用它。

问：取消后库存怎么恢复？

答：释放 reserved_quantity，total_quantity 不变，可用库存增加。

问：重复取消会怎样？

答：第二次取消时订单状态已经是 CANCELLED，状态校验返回 409，不会再次释放库存。

问：如果释放到一半失败？

答：整个取消事务回滚，订单状态和库存预占都回到取消前。

## 7. 一句话收尾

取消链路的核心是：锁订单、校验状态、逐行 release、订单改为 CANCELLED，失败整体回滚。

---

# 三、发货与库存扣减

## 1. 一句话

发货时锁订单，校验状态后把预占转成实际扣减；新订单扣减 total 和 reserved，历史 PAID 订单不重复扣库存。

## 2. 调用链

API 入口：backend/app/api/v1/admin/orders.py 的 ship_order

Service 入口：backend/app/services/order.py 的 OrderService.ship

库存入口：backend/app/services/inventory.py 的 InventoryService.deduct_reserved

SQL 入口：backend/app/repositories/inventory.py 的 InventoryRepository.deduct_reserved

## 3. 分步解释

### 第一步：锁订单

ship 使用 for_update 锁住订单行。

订单不存在返回 404。

### 第二步：校验订单和履约状态

可发货状态：

CREATED

PAID

PAID 是历史兼容状态，新订单不会进入 PAID。

履约状态必须是 UNSHIPPED。

如果订单已取消、已完成或已经发货，返回 409。

### 第三步：读取订单项

按订单 ID 读取订单项，按 sku_id 排序，保持稳定加锁顺序。

### 第四步：扣减库存

只有订单主状态是 CREATED 时才执行扣减。

调用 InventoryService.deduct_reserved。

Repository 的逻辑：

UPDATE inventory

SET total_quantity = total_quantity - quantity,

    reserved_quantity = reserved_quantity - quantity

WHERE sku_id = 当前 SKU

AND reserved_quantity >= quantity

AND total_quantity >= quantity

rowcount 不等于 1，说明库存数据不一致，抛业务冲突。

历史 PAID 订单已经走过旧的支付扣减流程，所以不再重复扣库存。

### 第五步：修改履约信息

扣减成功后：

fulfillment_status = SHIPPED

shipping_carrier = 承运商

tracking_no = 运单号

shipped_at = 发货时间

订单主状态仍然保持 CREATED。

这是订单状态和履约状态分离的体现。

### 第六步：失败回滚

如果任意一行扣减失败，异常穿出事务，订单履约状态和库存扣减都回滚。

不会出现“订单已发货但库存没扣”的半成品。

## 4. 库存变化

操作：发货扣减

total_quantity：减 qty

reserved_quantity：减 qty

available：不变

## 5. 订单状态和履约状态

订单主状态表达业务生命周期：

CREATED

CANCELLED

COMPLETED

履约状态表达物流进度：

UNSHIPPED

SHIPPED

DELIVERED

COMPLETED

发货只改履约状态，不改订单主状态。

所以发货后订单主状态仍然是 CREATED，但 fulfillment_status 是 SHIPPED。

## 6. 失败场景

订单不存在：404。

订单已取消或已完成：409。

订单已经发货：409。

预占量或总量不足：扣减 rowcount 为 0，抛业务冲突。

重复发货：履约状态已经不是 UNSHIPPED，返回 409。

## 7. 面试问答

问：发货为什么不直接改订单状态为 SHIPPED？

答：订单主状态和履约状态分开建模。主状态表达业务生命周期，履约状态表达物流进度，发货只推进履约状态。

问：为什么新订单要扣 reserved，历史 PAID 不扣？

答：新订单下单时只是预占，发货才真正出库；历史 PAID 订单在旧支付流程里已经扣过库存，不能重复扣。

问：发货时库存不足怎么办？

答：deduct_reserved 的 rowcount 不为 1，抛业务冲突，整个发货事务回滚。

问：重复发货怎么防？

答：锁订单后检查 fulfillment_status，必须是 UNSHIPPED；第二次发货会返回 409。

问：发货和取消能同时发生吗？

答：两者都会锁订单行，只有一个能先拿到锁；后一个会根据最新状态校验并失败。

## 8. 一句话收尾

发货链路的核心是：锁订单、校验 UNSHIPPED、CREATED 订单扣减 total 和 reserved、履约状态改为 SHIPPED。

---

# 四、事务、锁与并发专项

## 1. 一句话

事务边界在 Service；Repository 只执行 SQL 和 flush；并发安全靠行锁、带条件的原子 UPDATE、唯一约束和幂等键共同保证。

## 2. 事务边界

transaction_context 的逻辑：

当前 session 已有事务时，复用它，正常结束 commit，异常 rollback。

当前没有事务时，新开事务，退出时提交或回滚。

Service 负责开启事务。

Repository 不主动 commit。

这样做的原因：

一个业务操作可能涉及多个 Repository。

如果每个 Repository 自己 commit，订单创建成功但库存预占失败时，就无法整体回滚。

## 3. 三层幂等

### 第一层：订单幂等键

orders 表有 user_id 加 idempotency_key 唯一约束。

同一个用户、同一个幂等键只能有一张订单。

### 第二层：库存流水幂等键

inventory_transactions 表有 idempotency_key 唯一约束。

同一个业务动作重复执行时，可以复用已有流水。

### 第三层：状态机校验

取消要求订单处于 CREATED 或 PENDING_PAYMENT。

发货要求订单可发货且履约状态为 UNSHIPPED。

已经处理过的订单不会再次执行库存操作。

## 4. 行锁解决什么

InventoryService 在修改库存前调用 _locked_inventory。

_locked_inventory 使用 SELECT ... FOR UPDATE 锁住库存行。

作用：

同一 SKU 的库存操作串行化。

保护库存值和库存流水的一致性。

让后续的状态校验和更新在同一个锁保护下完成。

## 5. 原子 UPDATE 解决什么

只加行锁还不够表达业务条件，所以 Repository 使用带条件的 UPDATE。

以预占为例：

WHERE total_quantity - reserved_quantity >= quantity

SET reserved_quantity = reserved_quantity + quantity

这条 SQL 同时完成“判断可用量”和“增加预占量”。

不会出现两个请求都查到库存足够、然后都扣减的情况。

rowcount 是最终判断：

1 表示成功。

0 表示条件不满足或库存行不存在。

## 6. 为什么行锁和原子 UPDATE 都要

行锁负责串行化和保护流水一致性。

原子 UPDATE 的 WHERE 条件是最终防超卖判断。

两者配合，既保证并发安全，也让库存流水的写入有稳定的事务边界。

## 7. 死锁怎么降低

同一批订单项按 sku_id 排序后再操作。

创建订单、取消订单、发货都使用稳定顺序。

这样多个事务以相同顺序获取库存行锁，降低交叉等待造成的死锁概率。

## 8. 并发场景

场景一：两个请求同时用同一个幂等键下单

结果：唯一约束只允许一个成功，另一个回滚后读取旧订单。

场景二：两个请求同时买最后一件库存

结果：原子 UPDATE 只有一个 rowcount 等于 1，另一个库存不足。

场景三：取消和发货同时发生

结果：两个操作都锁订单行，只有一个先执行；后执行的操作根据最新状态失败。

场景四：重复发货

结果：第二次发货时 fulfillment_status 已经不是 UNSHIPPED，返回 409。

场景五：重复取消

结果：第二次取消时订单状态已经是 CANCELLED，返回 409。

## 9. 事务隔离和锁的关系

项目依赖 MySQL 的事务和行锁来保证并发写安全。

业务层不依赖“先查再改”的乐观判断，而是把关键条件放进 UPDATE 的 WHERE 子句。

这样即使两个事务同时执行，数据库也会根据行锁和条件判断决定谁成功。

## 10. 面试问答

问：为什么 Repository 不 commit？

答：Repository 只负责 SQL。事务边界由 Service 控制，才能保证多个写操作原子提交或整体回滚。

问：为什么不用先 SELECT 再 UPDATE？

答：先查再改在并发下会出现丢失更新。带条件的原子 UPDATE 把判断和修改放在同一条 SQL 里。

问：rowcount 为 0 代表什么？

答：条件不满足或目标行不存在。库存场景通常表示库存不足或预占量不足。

问：幂等键和唯一约束有什么区别？

答：幂等键是业务层的请求标识，唯一约束是数据库层的最终兜底。两者一起用，正常重试返回旧结果，并发冲突由数据库拦住。

问：如果库存流水写入失败怎么办？

答：整个事务回滚，库存更新和流水写入一起失败，不会只改库存不写流水。

## 11. 一句话收尾

事务边界在 Service；Repository 不 commit；并发安全靠行锁、条件 UPDATE、唯一约束和稳定加锁顺序。

---

# 五、面试时的完整口述版

这个项目的订单库存链路围绕“预占、释放、扣减”三个动作展开。

创建订单时，先在事务前做幂等检查；然后在同一事务里创建订单和订单项，再逐行预占库存。库存预占用行锁加带条件的原子 UPDATE，只有可用库存足够时才增加 reserved_quantity，rowcount 不是 1 就失败。订单、订单项和库存预占任何一步失败都会整体回滚。

取消订单时，先锁订单并校验归属和状态，只允许未发货订单取消；然后逐行 release，把 reserved_quantity 减回去，最后把订单改成 CANCELLED。重复取消会被状态校验拦住。

发货时，先锁订单，校验履约状态是 UNSHIPPED；对 CREATED 订单逐行 deduct_reserved，total_quantity 和 reserved_quantity 同时减少；最后把 fulfillment_status 改成 SHIPPED。订单主状态仍然是 CREATED，因为订单状态和履约状态是分开的。

并发控制主要靠四层：Service 控制事务，Repository 不 commit；订单和库存流水都有幂等键和唯一约束；库存修改使用行锁；最终防超卖靠带条件的原子 UPDATE。同一批订单项按 sku_id 排序，降低死锁概率。

---

# 六、最容易答错的点

错误一：说“先查库存再扣减”。

正确：用带条件的原子 UPDATE，不是先查再改。

错误二：说“下单直接扣库存”。

正确：下单预占，取消释放，发货扣减。

错误三：说“事务在 Repository 里”。

正确：事务在 Service，Repository 只执行 SQL 和 flush。

错误四：说“发货后订单状态变成 SHIPPED”。

正确：发货改的是 fulfillment_status，订单主状态仍是 CREATED。

错误五：说“取消是删除订单”。

正确：取消是状态变化，订单记录保留。

---

# 七、最后背这一句

下单预占、取消释放、发货扣减；订单和库存同事务；幂等键防重复；行锁加条件 UPDATE 防超卖；Repository 不 commit，事务边界在 Service。
