# 14 JWT 与 RBAC 代码阅读与面试总结

这篇文档只讲认证和权限这一条线：

1. 注册、登录、签发 Token
2. Access Token 和 Refresh Token
3. CurrentUser / CurrentAdmin / CurrentDebugger
4. 前端 Token、401 刷新和路由守卫
5. 面试问答与易错点

阅读原则：不要从第一行读到尾，按“登录请求 → Token → 请求鉴权 → 角色校验”的顺序读。

---

## 0. 一句话总结

登录负责证明“你是谁”，JWT 负责在后续请求中携带身份，RBAC 负责判断“你能不能做这件事”。

本项目的分工：

登录和 Token 签发在 AuthService。

JWT 编解码在 TokenService。

请求鉴权在 FastAPI dependencies。

角色判断在 CurrentAdmin 和 CurrentDebugger。

前端只负责携带 Token、刷新 Token 和改善页面体验，真正的权限边界在后端。

---

## 1. 整体调用链

登录：

POST /api/v1/auth/login
→ api/v1/auth.py 的 login
→ AuthService.login
→ 查用户
→ Argon2id 校验密码
→ 创建 Refresh Session
→ TokenService.create_access_token
→ 返回 access_token 和 refresh_token

请求鉴权：

请求头 Authorization: Bearer access_token
→ get_current_user
→ TokenService.decode_access_token
→ 查数据库确认用户仍然存在且 is_active
→ CurrentUser

管理员接口：

CurrentUser
→ get_current_admin
→ 检查 is_admin
→ CurrentAdmin

调试接口：

CurrentUser
→ get_current_debugger
→ 检查 is_admin 或 is_debugger
→ CurrentDebugger

刷新 Token：

POST /api/v1/auth/refresh
→ AuthService.refresh
→ 按 token 哈希行锁查 Refresh Session
→ 轮换 Refresh Token
→ 返回新的 access_token 和 refresh_token

---

## 2. 角色模型

用户表里只有三个权限标记：

is_active：账号是否可用

is_admin：是否管理员

is_debugger：是否调试人员

对应三个依赖：

CurrentUser：只要登录且账号可用

CurrentAdmin：必须 is_admin

CurrentDebugger：必须 is_admin 或 is_debugger

权限矩阵：

消费者：商城、下单、订单、售后、AI 客服

管理员：运营后台、商品、库存、订单、售后、知识库、Agent 审批

调试人员：Agent Trace、调试对话；不能审批业务

管理员同时也可以访问调试入口。

---

## 3. 阅读顺序

### 第 1 步：认证 API（10 分钟）

打开 backend/app/api/v1/auth.py。

只看四个接口：

register_user：调用 UserService.register_user

login：调用 AuthService.login

refresh_tokens：调用 AuthService.refresh

get_me：直接返回 CurrentUser

logout：调用 AuthService.logout

重点：

API 层只做 HTTP 协议、依赖注入和响应头。

登录和刷新响应加了：

Cache-Control: no-store

Pragma: no-cache

原因是响应里包含 Token，不能被浏览器或代理缓存。

API 层不写密码校验、Token 编解码和 Refresh 轮换逻辑。

---

### 第 2 步：AuthService.login（15 分钟）

打开 backend/app/services/auth.py。

只看 login 方法。

第一步：归一化邮箱并查用户。

normalize_email 会去空白并转小写，避免 Foo@example.com 和 foo@example.com 注册成两个账号。

第二步：用户不存在时也要做一次 dummy 密码校验。

目的不是验证，而是消耗与真实校验接近的 Argon2id 时间，降低通过响应时间枚举邮箱的风险。

第三步：真实用户密码校验放到 asyncio.to_thread。

Argon2id 是 CPU 密集型操作，不能阻塞 FastAPI 事件循环。

第四步：密码错误或 is_active 为 False，都返回统一的登录失败。

不要告诉客户端“邮箱不存在”或“密码错误”，避免账号枚举。

第五步：创建 Refresh Session。

Refresh Token 是 secrets.token_urlsafe(48) 生成的不透明随机串。

数据库只保存它的 SHA-256 哈希，不保存明文。

每次登录创建一个新的 family_id。

第六步：签发 Access Token，组装 TokenResponse。

TokenResponse 包含：

access_token

refresh_token

token_type，值为 bearer

expires_in，单位是秒

---

### 第 3 步：TokenService 签发 Access Token（10 分钟）

打开 backend/app/core/token.py。

只看 create_access_token 和 decode_access_token。

Access Token 是 JWT，payload 包含：

iss：签发者

aud：受众

sub：用户 ID 字符串

iat：签发时间

exp：过期时间

jti：每次签发的唯一标识

token_type：access

iss 和 aud 用来限制 Token 只能被本服务接受。

jti 为后续审计或黑名单预留唯一标识。

user_id 必须是正整数，布尔值也会被拒绝。

decode_access_token 会校验：

签名

过期时间

issuer

audience

所有必需的 claims

strict_aud

token_type 必须是 access

_validate_application_claims 还会额外校验：

sub 必须是规范的十进制字符串，拒绝 01、1.0、负数和布尔值

iat 和 exp 必须是整数，且 exp 大于 iat

jti 必须是非空字符串

这样即使攻击者拿到一个 Refresh Token，也不能把它当作 Access Token 使用。

---

### 第 4 步：Refresh Token 轮换（15 分钟，进阶）

打开 backend/app/services/auth.py 的 refresh。

流程：

按 Refresh Token 的哈希查记录

用 for_update 锁住这一行

如果记录不存在，返回无效 Token

如果 revoked_at 不为空，说明旧 Token 被重复使用

重复使用时撤销整个 family

如果已过期，撤销当前记录

如果用户不存在或禁用，撤销整个 family

正常情况：生成新 Refresh Token，创建新记录，旧记录标记 replaced_by

返回新的 Access Token 和 Refresh Token

注意一个细节：

重放检测的异常是在事务提交之后才抛出的。

原因是撤销 family 必须持久化，不能因为抛异常而回滚。

这部分面试不要求背每个分支，但要知道：

Refresh Token 会轮换，旧 Token 不能再次使用，重复使用会撤销整个会话家族。

---

### 第 5 步：请求鉴权（15 分钟）

打开 backend/app/api/dependencies.py。

get_current_user 做四件事：

从 Authorization 头取 Bearer Token

TokenService.decode_access_token

按 claims.user_id 查数据库

确认用户存在且 is_active

为什么 Token 还有效还要查数据库？

因为用户可能已经被禁用或删除。JWT 本身不知道账号最新状态，所以每次请求回查。

用户身份只来自服务端解析后的 claims。

请求体或 Header 里的 user_id 一律不能作为身份依据。

CurrentUser 是一个 Annotated 类型别名，业务路由直接声明它即可。

get_current_admin 在 CurrentUser 之上检查 is_admin。

不满足时抛 PermissionDeniedException，也就是 403。

get_current_debugger 允许 is_admin 或 is_debugger。

普通用户不能访问调试接口。

---

### 第 6 步：密码哈希（10 分钟）

打开 backend/app/core/security.py。

hash_password 使用 Argon2id，每次自动生成随机盐。

verify_password 校验失败或哈希格式损坏时都返回 False，不泄露数据库内部格式。

verify_dummy_password 对固定 dummy hash 做一次真实校验，用来拉平登录耗时。

needs_rehash 用于 Argon2 参数升级后，在用户下次登录时透明重算哈希。

面试只需要说清楚：

不存明文，使用 Argon2id，随机盐，CPU 密集操作放线程池。

---

### 第 7 步：前端 Token 和路由守卫（10 分钟）

打开 frontend/src/utils/token.ts。

Access Token 和 Refresh Token 存在 sessionStorage。

sessionStorage 是每个浏览器标签页独立的。

所以同一个浏览器可以开三个标签页，分别登录普通用户、管理员和调试人员。

这是演示项目的取舍，不是生产环境的唯一方案。

打开 frontend/src/api/client.ts。

请求拦截器自动加：

Authorization: Bearer access_token

响应拦截器遇到 401：

如果请求不是 login 或 refresh

且当前请求没有重试过

就调用 refresh 接口

用 refreshPromise 做单飞，避免多个 401 同时刷新

刷新成功后重放原请求

刷新失败则清 Token、触发 auth:expired、跳登录页

打开 frontend/src/router 下的三个守卫。

ProtectedRoute：未登录跳登录页

AdminRoute：不是管理员跳商城

DebugRoute：不是管理员也不是调试人员跳商城

注意：

前端守卫只改善体验，不是安全边界。

真正的权限校验在后端依赖里，前端跳转不能代替后端 403。

---

## 4. 关键设计问答

### 1. 为什么 Access Token 用 JWT，Refresh Token 不用 JWT？

Access Token 需要无状态校验，每次请求都能快速验证，所以用 JWT。

Refresh Token 需要撤销、轮换和重放检测，所以用数据库中的不透明随机串，只保存哈希。

### 2. 为什么 Access Token 要短，Refresh Token 要长？

Access Token 泄露后的风险窗口要小，所以有效期短。

Refresh Token 用来换取新的 Access Token，有效期长，但可以撤销和轮换。

### 3. 为什么每次请求都回查数据库？

JWT 只能证明签发时的身份，不能证明账号现在仍然可用。

用户可能被禁用或删除，所以每次请求都要确认 is_active。

### 4. 401 和 403 的区别？

401：没有登录、Token 缺失、Token 无效或过期。

403：已经登录，但当前角色没有权限。

### 5. 为什么前端路由守卫不能替代后端权限？

前端代码可以被修改，接口也可以被直接调用。

前端守卫只负责页面跳转，后端依赖才是最终权限边界。

### 6. 为什么登录失败不区分邮箱不存在和密码错误？

避免账号枚举。

用户不存在时也执行一次 dummy 密码校验，拉平响应时间。

### 7. 为什么密码哈希要放线程池？

Argon2id 是 CPU 密集型操作，直接放在 async 函数里会阻塞事件循环。

### 8. Refresh Token 重复使用会怎样？

旧 Token 已经被撤销后再次使用，会撤销整个 family，防止 Token 被窃取后继续轮换。

### 9. JWT 里为什么要 issuer 和 audience？

限制 Token 只能由本服务签发，并且只能被本服务接受，降低 Token 混用风险。

### 10. 为什么 Token 存在 sessionStorage？

当前项目需要在同一浏览器开多个标签页，分别登录消费者、管理员和调试人员。

sessionStorage 按标签页隔离，正好支持这个演示场景。

生产环境要结合 XSS 风险、HttpOnly Cookie 和 CSRF 防护重新评估。

---

## 5. 面试口述版

认证这块分成登录、Token 和鉴权三部分。

登录时，AuthService 先归一化邮箱并查用户，然后用 Argon2id 校验密码。用户不存在时也会做一次 dummy 校验，拉平响应时间。校验通过后创建 Refresh Session，数据库只保存 Refresh Token 的哈希，同时签发 Access Token。

Access Token 是 JWT，包含 iss、aud、sub、iat、exp、jti 和 token_type；解码时会校验签名、过期时间、issuer、audience、必需 claims 和 token_type。Refresh Token 是不透明随机串，支持轮换和重放检测，旧 Token 重复使用会撤销整个 family。

请求进来后，get_current_user 从 Bearer Token 解析用户 ID，再回查数据库确认账号仍然可用。CurrentAdmin 在 CurrentUser 之上检查 is_admin，CurrentDebugger 允许管理员或调试人员。401 是身份没确认，403 是身份确认了但没权限。

前端用 sessionStorage 存 Token，Axios 自动加 Authorization，遇到 401 会单飞刷新并重放一次请求。路由守卫只改善体验，真正权限仍然后端校验。

---

## 6. 最容易答错的点

错误一：说“请求体可以传 user_id”。

正确：身份只来自服务端解析后的 Token claims。

错误二：说“前端路由守卫就是权限控制”。

正确：前端守卫只是体验，后端依赖才是安全边界。

错误三：说“JWT 有效就代表用户一定可用”。

正确：还要回查数据库确认 is_active。

错误四：说“Refresh Token 也存 JWT 明文”。

正确：数据库只存 Refresh Token 的哈希，而且它会轮换。

错误五：说“权限不足返回 401”。

正确：未认证是 401，已认证但无权限是 403。

---

## 7. 五分钟自检

合上文档，回答：

1. 登录成功后返回哪两个 Token？
2. Access Token 里有哪些 claims？
3. 为什么每次请求还要查数据库？
4. CurrentUser、CurrentAdmin、CurrentDebugger 的区别？
5. 401 和 403 的区别？
6. Refresh Token 为什么不用 JWT？
7. Refresh Token 重复使用会怎样？
8. 前端 401 拦截器做了什么？
9. 前端路由守卫能替代后端权限吗？
10. 密码为什么要用 Argon2id？

---

## 8. 最后背这一句

登录证明身份，JWT 携带身份，CurrentUser 回查账号，CurrentAdmin 和 CurrentDebugger 做角色校验；Access Token 无状态，Refresh Token 可撤销可轮换；前端只负责携带和刷新，真正的权限边界在后端。
