# SPEC-301 2027 届飞书校招租户

状态：3 个飞书租户已逐站真实采集验收，详见 `docs/adapter-batch-20261023-acceptance.md`。

## 目标与非目标

复用飞书公开校园门户已验收的 UI 签名分页契约，接入普源精电 `rigolportal`、沐瞳科技 `moonton`、面壁智能 `modelbest` 的独立校园站点。保留公开岗位正文、要求、地点、职位 ID 和源发布时间。只读取岗位，不登录、投递或绕过验证码；已绑定企业的其他门户不计入本批新增数。

## 输入输出、范围与分页

- 入口分别为 `https://rigolportal.jobs.feishu.cn/campus/position/list`、`https://moonton.jobs.feishu.cn/campus/position/list`、`https://modelbest.jobs.feishu.cn/campus/position/list`。2026-10-23 渲染页分别显示 21、92、64 个无筛选校园职位，首请求为同源 `/api/v1/search/job/posts`，`portal_type=6`、`limit=10`、`offset=0` 且含本轮签名。按 UI 下一页操作捕获新签名请求，核对总数、重复 ID 和末页。
- 实习按 `recruit_type`、项目或标题标记排除；面壁同时展示 2026 校招与 Top Talent 项目，只纳入明确 2027 校园项目的正式岗位。未有具体发布时间或分类时保留空值进入待补全，不使用采集时间作发布时间。
- 输出与 SPEC-299 相同：独立快照、Scope 计数、岗位信息、严格导入和待补全；只有 `coverage=complete`、`terminal=true`、有效岗位大于零才计入。

## 失败行为与验收

签名缺失、页面目录仍有筛选、总数变化、翻页缺页、同 ID 不同正文、公开正文缺失或登录限制时保留 partial/blocked，正式绑定不启用。离线测试检查过滤后的范围计数、飞书分页和源身份；真实站点证据核对最后页、项目类型、岗位数量和可复现入口。
