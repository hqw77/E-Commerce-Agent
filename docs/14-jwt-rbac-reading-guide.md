# 14 JWT 与 RBAC 代码阅读与面试总结

这篇文档只回答两个问题：

这个人是谁？

他能做什么？

当前项目使用简化版认证：只签发 Access Token，不再使用 Refresh Token。

---

## 1. 用生活例子理解

登录：去前台办一张门禁卡。

Access Token：这张门禁卡，进楼时给保安看。

RBAC：不同卡片能进不同区域。

普通用户只能进商城。

管理员能进运营后台。

调试人员能进调试区。

保安只认卡，不认你口头说“我是管理员”。

Token 过期后，需要重新登录换一张新卡。

---

## 2. 这个项目里谁管什么

认证只有四个核心文件：

backend/app/api/v1/auth.py

负责注册、登录、获取当前用户、退出接口。

backend/app/services/auth.py

负责校验邮箱密码，并签发 Access Token。

backend/app/core/token.py

负责 JWT 的签发和校验。

backend/app/api/dependencies.py

负责从请求头拿 Token、解析用户、检查管理员或调试权限。

前端对应：

frontend/src/utils/token.ts

保存和清除 Access Token。

frontend/src/api/client.ts

请求自动带 Token，遇到 401 清除 Token 并跳登录页。

frontend/src/router 下的 ProtectedRoute、AdminRoute、DebugRoute

负责页面跳转，不是最终权限边界。

---

## 3. 登录时发生了什么

入口：

POST /api/v1/auth/login

进入 AuthService.login。

第一步：查用户

邮箱去空格、转小写，然后按邮箱查用户。

第二步：校验密码

用 Argon2id 校验密码。

密码哈希是 CPU 密集型操作，所以放到线程池。

用户不存在时也执行一次假的密码校验，让响应时间和真实用户接近，防止别人通过响应快慢猜邮箱是否存在。

第三步：签发 Access Token

Access Token 是 JWT。

JWT 里主要放：

用户 ID

签发时间

过期时间

Token 类型

JWT 由服务端签名，客户端不能修改。

第四步：返回 Token

登录只返回：

access_token

token_type

expires_in

默认有效期是 24 小时。

---

## 4. 后续请求怎么认人

请求头带：

Authorization: Bearer access_token

后端进入 get_current_user。

第一步：取 Token

没有 Token，返回 401。

第二步：解析 JWT

校验签名、过期时间、签发者和受众。

解析出 user_id。

第三步：回查数据库

按 user_id 查用户。

确认用户存在，并且 is_active 为 True。

为什么 JWT 有效还要查库？

因为用户可能已经被禁用或删除。

JWT 只证明“签发时你是谁”，不证明“现在你还能不能用”。

第四步：得到 CurrentUser

后面的业务接口直接声明 CurrentUser，就能拿到当前用户。

请求体里传 user_id 不算数。

身份只来自服务端解析后的 Token。

---

## 5. 三个角色

用户表里只有三个开关：

is_active：账号能不能用。

is_admin：是不是管理员。

is_debugger：是不是调试人员。

对应三个依赖：

CurrentUser：登录且账号可用。

CurrentAdmin：必须是管理员。

CurrentDebugger：管理员或调试人员。

权限大概是这样：

普通用户：商城、下单、订单、售后、AI 客服。

管理员：运营后台、商品、库存、订单、售后、知识库、Agent 审批。

调试人员：Agent Trace、调试对话，不能审批业务。

管理员也可以访问调试入口。

---

## 6. 401 和 403

401：没登录，或者 Token 无效、过期。

403：登录了，但权限不够。

例子：

不带 Token 访问订单接口：401。

普通用户访问管理员接口：403。

这两个不要答反。

---

## 7. Token 过期和退出

Token 过期：

前端请求会收到 401。

Axios 清除本地 Token，跳登录页。

用户重新登录。

退出：

前端直接删除 sessionStorage 里的 Token。

后端 /auth/logout 返回 204，不保存服务端会话。

这是一种简化设计，适合面试 Demo。

代价是：

Token 过期前无法在服务端主动撤销。

Token 被偷后，在过期前仍然有效。

生产环境可以再引入 Refresh Token、黑名单或更短的 Token。

---

## 8. 前端怎么配合

前端把 Access Token 存在 sessionStorage。

sessionStorage 是每个浏览器标签页独立的。

所以同一个浏览器可以开三个标签页，分别登录消费者、管理员和调试人员。

请求时 Axios 自动加 Authorization。

如果接口返回 401：

清除 Token。

触发 auth:expired 事件。

跳登录页。

前端不再自动刷新 Token。

路由守卫：

没登录，跳登录页。

不是管理员，跳商城。

不是管理员也不是调试人员，不能进调试页。

但前端守卫只改善体验。

真正的权限在后端。

前端代码可以改，接口也可以直接调，所以后端必须再校验。

---

## 9. 面试时怎么讲

可以按这段说：

这个项目用的是简化版 JWT 认证，只签发 Access Token，没有 Refresh Token。

登录时，AuthService 先查用户并用 Argon2id 校验密码，然后签发 JWT。JWT 里带用户 ID 和过期时间，默认有效期 24 小时。

请求进来后，get_current_user 从 Bearer Token 解析用户 ID，再回查数据库确认账号仍然可用。CurrentAdmin 在 CurrentUser 之上检查 is_admin，CurrentDebugger 允许管理员或调试人员。

401 是身份没确认，403 是身份确认了但权限不够。前端用 sessionStorage 存 Token，Axios 自动加 Authorization，遇到 401 就清除 Token 并跳登录页。前端路由守卫只负责页面跳转，真正权限在后端。

---

## 10. 高频问题

问：JWT 是什么？

答：服务端签发的身份凭证，里面带用户 ID 和过期时间，客户端不能篡改。

问：为什么用 JWT？

答：Access Token 校验不依赖服务端 Session，适合前后端分离。

问：为什么本项目不需要 Refresh Token？

答：这是简化版面试项目，Token 有效期 24 小时，过期后重新登录，代码和讲解都更简单。

问：为什么每次请求还要查数据库？

答：用户可能被禁用或删除，JWT 不知道最新状态。

问：401 和 403 区别？

答：401 是没认证，403 是认证了但没权限。

问：RBAC 是什么？

答：基于角色的权限控制。这个项目用 is_admin 和 is_debugger 区分角色。

问：前端路由守卫能代替后端权限吗？

答：不能。前端只管页面跳转，后端才是安全边界。

问：密码为什么用 Argon2id？

答：抗暴力破解，带随机盐，不保存明文。

问：退出登录怎么实现？

答：前端删除 Token；服务端没有会话需要撤销。

问：这个方案有什么缺点？

答：Token 过期前无法主动撤销，生产环境需要更完整的会话撤销机制。

---

## 11. 最容易答错的点

错误一：说请求体可以传 user_id。

正确：身份只来自 Token。

错误二：说前端路由守卫就是权限控制。

正确：前端只是体验，后端才是权限。

错误三：说 JWT 有效用户就一定可用。

正确：还要回查数据库看 is_active。

错误四：说权限不足返回 401。

正确：未认证 401，已认证没权限 403。

错误五：说这个项目有 Refresh Token。

正确：当前已经改成只使用 Access Token。

---

## 12. 先读哪些代码

按这个顺序看：

backend/app/api/v1/auth.py

只看 login、me、logout 三个接口。

backend/app/services/auth.py

只看 login，知道密码校验和签发 Access Token。

backend/app/core/token.py

只看 create_access_token 和 decode_access_token。

backend/app/api/dependencies.py

只看 get_current_user、get_current_admin、get_current_debugger。

前端最后看：

frontend/src/utils/token.ts

frontend/src/api/client.ts

frontend/src/router 下的三个守卫。

---

## 13. 五分钟自检

1. 登录返回哪个 Token？
2. Access Token 里主要有什么？
3. 为什么每次请求还要查数据库？
4. CurrentUser、CurrentAdmin、CurrentDebugger 的区别？
5. 401 和 403 的区别？
6. 前端 401 后做了什么？
7. 前端路由守卫能代替后端权限吗？
8. 退出登录怎么实现？

---

## 14. 最后背这一句

登录签发 Access Token，JWT 携带身份，CurrentUser 回查账号，CurrentAdmin 和 CurrentDebugger 做角色校验；Token 过期后前端清除并重新登录，前端只负责携带 Token，真正的权限边界在后端。
