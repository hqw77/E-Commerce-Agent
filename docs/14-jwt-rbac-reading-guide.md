# 14 JWT 与 RBAC 完整教程

这篇文档把 JWT、RBAC、项目代码、阅读方法和面试回答放在一起。

读完应该能做到：

1. 知道 JWT 和 RBAC 分别解决什么问题。
2. 能顺着一次登录和一次请求读完认证代码。
3. 能用自己的话讲清项目里的认证和权限。
4. 能回答初级全栈常见的 JWT/RBAC 面试题。

当前项目已经简化成：

只签发 Access Token。

没有 Refresh Token。

Token 默认有效期 24 小时。

过期后重新登录。

---

# 第一部分：先把概念讲明白

## 1. JWT 是什么

JWT 是服务端签发的一张身份凭证。

它长这样：

header.payload.signature

三部分用点分隔。

第一部分是头，说明签名算法。

第二部分是内容，主要放用户 ID、签发时间、过期时间、Token 类型。

第三部分是签名，服务端用来判断内容有没有被改过。

重点：

JWT 的内容可以被看见，但不是加密的。

客户端改了内容，签名就会对不上，服务端会拒绝。

所以 JWT 不是“秘密信息”，而是“带签名的身份凭证”。

## 2. JWT 解决什么问题

HTTP 请求本身不记得上一次请求是谁。

用户登录成功后，后面每个请求都要证明“我还是刚才那个人”。

JWT 就是每次请求随身带的身份凭证。

请求头：

Authorization: Bearer 你的token

后端看到 Bearer Token，就知道去解析 JWT。

## 3. 认证和授权

认证 Authentication：

你是谁。

授权 Authorization：

你能做什么。

JWT 主要解决“你是谁”。

RBAC 主要解决“你能做什么”。

这两件事必须分开。

JWT 有效，只代表身份可信。

不代表这个用户有管理员权限。

## 4. RBAC 是什么

RBAC 是基于角色的权限控制。

不是给每个用户单独写权限，而是先分角色，再看角色能做什么。

这个项目没有复杂的角色表，只用了三个字段：

is_active：账号是否可用。

is_admin：是否管理员。

is_debugger：是否调试人员。

角色和权限：

普通用户：商城、下单、订单、售后、AI 客服。

管理员：运营后台、商品、库存、订单、售后、知识库、Agent 审批。

调试人员：Agent Trace、调试对话，不能审批业务。

管理员也可以访问调试入口。

## 5. 为什么这个项目没有 Refresh Token

早期版本有 Refresh Token、轮换、重放检测和 family 撤销。

后来为了简化面试项目，改成了只保留 Access Token。

现在的设计：

登录发一个 Access Token。

有效期 24 小时。

过期后前端清除 Token，重新登录。

退出就是前端删除 Token。

好处：

代码少。

登录鉴权链路一眼能讲清。

不用解释 Refresh Token 轮换和重放检测。

代价：

Token 过期前，服务端不能主动撤销。

Token 被偷后，在有效期内仍然能用。

生产环境可以再加黑名单、短期 Token 或 Refresh Token。

面试时要主动说这是简化设计，不要说成生产级方案。

---

# 第二部分：项目里怎么写的

## 1. 相关文件

后端：

backend/app/api/v1/auth.py

登录、注册、当前用户、退出接口。

backend/app/services/auth.py

校验邮箱密码，签发 Access Token。

backend/app/core/token.py

JWT 的签发和校验。

backend/app/api/dependencies.py

从请求头拿 Token，解析用户，检查角色。

backend/app/core/security.py

密码哈希和校验。

backend/app/models/user.py

用户表，包含 is_active、is_admin、is_debugger。

backend/app/schemas/auth.py

登录请求、Token 响应、用户响应。

前端：

frontend/src/utils/token.ts

保存、读取、清除 Access Token。

frontend/src/api/auth.ts

调用登录、注册、当前用户接口。

frontend/src/api/client.ts

Axios 自动加 Token，401 时清 Token 跳登录页。

frontend/src/stores/authStore.ts

维护登录状态和当前用户。

frontend/src/router/ProtectedRoute.tsx

AdminRoute.tsx

DebugRoute.tsx

页面级路由守卫。

## 2. 数据库

用户表主要字段：

id

email

password_hash

is_active

is_admin

is_debugger

数据库不保存 Access Token。

也不再有 refresh_sessions 表。

服务端不维护登录会话。

## 3. 登录返回什么

登录成功只返回：

access_token

token_type

expires_in

没有 refresh_token。

前端把 access_token 存到 sessionStorage。

---

# 第三部分：完整代码链

先记住两条链：

登录链。

请求鉴权链。

## 1. 登录链

前端：

登录页面

-> frontend/src/stores/authStore.ts 的 login

-> frontend/src/api/auth.ts 的 login

-> POST /api/v1/auth/login

后端：

backend/app/api/v1/auth.py 的 login

-> AuthService.login

-> UserRepository.get_by_email

-> 校验密码

-> 检查 is_active

-> TokenService.create_access_token

-> 返回 TokenResponse

前端拿到响应：

-> saveAccessToken

-> GET /auth/me

-> 得到当前用户

-> 根据角色跳转

## 2. 请求鉴权链

页面或组件

-> frontend/src/api/client.ts 请求拦截器

-> 自动加 Authorization: Bearer access_token

-> 后端 get_current_user

-> TokenService.decode_access_token

-> UserRepository.get_by_id

-> 检查 is_active

-> CurrentUser

-> 业务接口

## 3. 管理员链

业务接口声明 CurrentAdmin

-> get_current_user

-> get_current_admin

-> 检查 is_admin

-> 返回 CurrentAdmin

不是管理员，返回 403。

## 4. 调试链

业务接口声明 CurrentDebugger

-> get_current_user

-> get_current_debugger

-> 检查 is_admin 或 is_debugger

-> 返回 CurrentDebugger

两个都不是，返回 403。

## 5. 401 链

请求没带 Token

或 Token 无效

或 Token 过期

-> 后端返回 401

-> 前端 Axios 拦截器

-> 清除 Token

-> 跳登录页

## 6. 403 链

用户已登录

但角色不够

-> 后端返回 403

-> 前端提示无权限

-> 不跳登录页

---

# 第四部分：按顺序读代码

不要从第一行读到尾。

按下面的顺序读。

## 第 1 步：API 入口

打开 backend/app/api/v1/auth.py。

只看四个接口：

login

get_me

logout

register_user

重点：

API 不写密码校验和 JWT 逻辑。

它只调用 Service。

登录响应加了 no-store，避免缓存 Token。

## 第 2 步：登录业务

打开 backend/app/services/auth.py。

只看 login。

它在做什么：

邮箱归一化。

按邮箱查用户。

用户不存在时做一次假密码校验。

用户存在时校验真实密码。

检查 is_active。

签发 Access Token。

你要能回答：

为什么用户不存在也要校验一次？

为什么要检查 is_active？

Token 在哪里签发？

## 第 3 步：JWT 签发与校验

打开 backend/app/core/token.py。

只看两个方法：

create_access_token

decode_access_token

签发时写入：

用户 ID

签发时间

过期时间

Token 类型

签名

校验时检查：

签名

过期时间

签发者

受众

必需字段

Token 类型

你不需要背签名算法。

只要知道：

JWT 被改过，验签会失败。

其他类型 Token 不能当 Access Token 用。

## 第 4 步：请求鉴权

打开 backend/app/api/dependencies.py。

只看三个函数：

get_current_user

get_current_admin

get_current_debugger

get_current_user 做四件事：

从 Authorization 取 Bearer Token。

解析 JWT。

按 user_id 查库。

确认用户存在且 is_active。

为什么 JWT 有效还要查库？

因为用户可能被禁用或删除。

JWT 只证明签发时是谁，不证明现在还能不能用。

用户身份只来自服务端解析后的 Token。

请求体里传 user_id 不算数。

## 第 5 步：密码哈希

打开 backend/app/core/security.py。

只看：

hash_password

verify_password

verify_dummy_password

要能说出：

密码不存明文。

使用 Argon2id。

每次哈希带随机盐。

密码校验是 CPU 密集型操作，所以放线程池。

用户不存在时也做一次假校验，拉平响应时间。

## 第 6 步：前端 Token

打开 frontend/src/utils/token.ts。

只看：

saveAccessToken

getAccessToken

clearTokens

Token 存在 sessionStorage。

sessionStorage 按标签页隔离。

所以可以同时开三个标签页，分别登录三个角色。

## 第 7 步：Axios

打开 frontend/src/api/client.ts。

看两个拦截器：

请求拦截器：

自动加 Authorization。

响应拦截器：

遇到 401，清 Token，跳登录页。

当前没有自动刷新。

## 第 8 步：路由守卫

打开 frontend/src/router 下的：

ProtectedRoute.tsx

AdminRoute.tsx

DebugRoute.tsx

它们只负责页面跳转：

没登录，跳登录页。

不是管理员，跳商城。

不是管理员也不是调试人员，不能进调试页。

记住：

前端守卫只改善体验，不是安全边界。

真正权限在后端。

---

# 第五部分：代码怎么读才不容易忘

## 方法一：三遍法

第一遍只看成功路径。

登录成功。

请求带 Token 成功。

管理员访问管理接口成功。

第二遍只看失败路径。

邮箱不存在。

密码错误。

账号禁用。

Token 缺失。

Token 过期。

Token 无效。

普通用户访问管理员接口。

第三遍看测试。

backend/tests/core/test_token.py

backend/tests/services/test_auth.py

backend/tests/api/test_auth.py

测试会告诉你每个函数的输入、输出和边界。

## 方法二：打断点跟一次请求

在 AuthService.login 打断点，看：

user

password_valid

access_token

在 get_current_user 打断点，看：

credentials

claims

user

## 方法三：改一行看什么坏了

例如临时去掉 is_active 判断。

跑测试。

看哪些用例失败。

再改回来。

这比只看代码更容易理解每个判断的作用。

## 方法四：合上代码自己画图

画两条线：

登录线。

请求鉴权线。

画不出来，就回到对应函数重读。

---

# 第六部分：面试怎么讲

## 30 秒版

这个项目用的是简化版 JWT 认证，只签发 Access Token，没有 Refresh Token。

登录时校验邮箱和密码，成功后签发 JWT。请求进来后，后端解析 JWT、回查用户，再通过 is_admin 和 is_debugger 做 RBAC。

401 是没认证，403 是没权限。前端只负责带 Token 和跳转，真正的权限在后端。

## 1 分钟版

登录时，AuthService 先归一化邮箱并查用户，用 Argon2id 校验密码。用户不存在时也做一次假校验，拉平响应时间。校验通过后签发 Access Token，JWT 里带用户 ID 和过期时间。

请求进来后，get_current_user 从 Bearer Token 解析用户 ID，再回查数据库确认账号仍然可用。CurrentAdmin 在 CurrentUser 之上检查 is_admin，CurrentDebugger 允许管理员或调试人员。

401 是身份没确认，403 是身份确认了但权限不够。前端用 sessionStorage 存 Token，Axios 自动加 Authorization，遇到 401 清除 Token 并跳登录页。前端路由守卫只负责页面跳转，真正权限在后端。

当前没有 Refresh Token，Token 默认 24 小时，过期后重新登录。这是简化设计，生产环境可以再加黑名单、短期 Token 或 Refresh Token。

---

# 第七部分：高频面试题

## 1. JWT 是什么

服务端签发的身份凭证。

里面带用户 ID、过期时间等信息。

客户端不能修改，因为改了签名会失效。

## 2. JWT 和 Session 的区别

JWT 无状态，服务端不用为每个用户保存 Session。

Session 服务端存储，撤销更方便。

这个项目用 JWT，适合前后端分离。

## 3. JWT 的三段是什么

header、payload、signature。

payload 里放用户 ID、签发时间、过期时间、Token 类型。

signature 用来防篡改。

## 4. 为什么每次请求还要查数据库

JWT 只证明签发时的身份。

用户可能被禁用或删除。

所以每次请求都要确认 is_active。

## 5. 401 和 403 的区别

401：没登录，或者 Token 缺失、无效、过期。

403：登录了，但角色权限不够。

## 6. RBAC 是什么

基于角色的权限控制。

这个项目用 is_admin 和 is_debugger 两个角色标记。

普通用户、管理员、调试人员能访问的接口不同。

## 7. CurrentUser、CurrentAdmin、CurrentDebugger 的区别

CurrentUser：登录且账号可用。

CurrentAdmin：必须是管理员。

CurrentDebugger：管理员或调试人员。

## 8. 为什么前端路由守卫不能代替后端权限

前端代码可以被修改。

接口也可以被直接调用。

前端守卫只是页面跳转。

后端依赖才是最终权限边界。

## 9. 密码为什么要用 Argon2id

抗暴力破解。

带随机盐。

不保存明文。

密码校验放线程池，避免阻塞事件循环。

## 10. 为什么用户不存在也要做假校验

防止别人通过响应时间判断邮箱是否存在。

真实用户和不存在用户的耗时尽量接近。

## 11. 退出登录怎么实现

前端删除 sessionStorage 里的 Token。

后端 /auth/logout 返回 204。

当前没有服务端会话需要撤销。

## 12. 这个方案有什么缺点

Token 过期前无法在服务端主动撤销。

Token 被偷后，在有效期内仍然有效。

生产环境需要更完整的会话撤销方案。

## 13. 为什么没有 Refresh Token

这是简化版面试项目。

Token 有效期 24 小时。

过期后重新登录。

代码和讲解都更简单。

## 14. JWT 过期了怎么办

前端收到 401。

清除 Token。

跳登录页。

用户重新登录，拿新 Token。

## 15. 如果面试官问 Token 被偷了怎么办

当前简化版只能在过期后失效。

生产环境可以加黑名单、短期 Access Token、Refresh Token 轮换、设备绑定等措施。

---

# 第八部分：最容易答错的点

错误一：说请求体可以传 user_id。

正确：身份只来自服务端解析后的 Token。

错误二：说前端路由守卫就是权限控制。

正确：前端只是体验，后端才是权限。

错误三：说 JWT 有效用户就一定可用。

正确：还要回查数据库看 is_active。

错误四：说权限不足返回 401。

正确：未认证 401，已认证没权限 403。

错误五：说这个项目有 Refresh Token。

正确：当前已经改成只使用 Access Token。

错误六：说 JWT 是加密的。

正确：JWT 内容是可见的，签名只负责防篡改。

---

# 第九部分：五分钟自检

1. 登录返回哪个 Token？

2. JWT 里主要有什么？

3. 请求怎么带 Token？

4. 后端怎么从 Token 得到 CurrentUser？

5. 为什么还要查数据库？

6. CurrentAdmin 和 CurrentDebugger 怎么判断？

7. 401 和 403 区别？

8. 前端 401 后做什么？

9. 退出登录怎么实现？

10. 前端守卫为什么不能代替后端？

---

# 第十部分：最后背这一句

登录签发 Access Token，JWT 携带身份，CurrentUser 回查账号，CurrentAdmin 和 CurrentDebugger 做角色校验；Token 过期后前端清除并重新登录，前端只负责携带 Token，真正的权限边界在后端。
