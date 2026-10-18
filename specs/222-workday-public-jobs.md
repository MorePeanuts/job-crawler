# SPEC-222 Workday 公开职位目录：新濠

状态：实现前规范；仅核实公开协议，尚未完成真实适配验收。SPEC-156 固定 B 组 COM0396。

## 目标、非目标与输入输出

输入新濠国际发展有限公司的公开招聘目录 https://melcoresorts.wd3.myworkdayjobs.com/en-US/career；母公司官网明确旗下新濠博亚娱乐，租户 About Us 与该主体相符。遍历整个租户全部国家/地区，输出 Job/Scope、身份与正文证据，完成后才加入 B 组汇总。不限于澳门首屏。不得登录、投递或调用用户资料接口；不假定其他 Workday 租户同样支持，不把全部酒店社会招聘当校招。

## 已观察协议和分页终态

普通页面加载约 15–20 秒后显示完整目录；初始 minimal_text/script_heavy_shell 属导航结构启发式，不是验证码。使用已验证的同源 ready_endpoints `/wday/cxs/melcoresorts/career/jobs` 等待实际业务 JSON，不改变身份、不绕过挑战。

页面实际 POST jobs，JSON 为 appliedFacets={}、limit=20、offset=0、searchText=""。首响应 total=166，jobPostings=20；后续 offset 20…140 各20条、160为6条，后续 total=0 是实证协议，不代表空目录。真实 UI 末页标明 161–166 of 166。越界 offset180 会重置返回首页20条和 total166，故按首个可靠 total 与期望每页长度闭合，不把空页当终止。首次 total 必须正整数且在预算内；尚未实证零目录形态时 total0 失败，不默认为零。每页总数只能等于首总数或后页0，路径身份全程唯一；短页、重复、总数变化均 partial。结束重读首页确认总数和首屏身份一致，防止遍历中变化。

列表 externalPath 形如 /job/地点/标题_REQ，详情实际 GET `/wday/cxs/melcoresorts/career/job/最后路径段`。核对 jobPostingId、jobReqId 与 bulletFields、jobPostingSiteId、标题、externalUrl 与列表路径，使用 posting slug 作源键而非标题或可能重复的 reqId。日期来自详情 startDate/endDate，不把 postedOn 相对时间当发布日期。country、location、additionalLocations 保留来源信息，未提供具体街道不推断。canApply 与 posted 必须明确布尔值；未开放记录保留并排除，不能把请求失败当下架。

## 正文、范围与失败

逐详情完整读取 jobDescription；正文按明确 QUALIFICATIONS/Requirements 等标题拆分，无法可靠分节时保留原文并注明；不凭标题虚构职责。正文图片、附件及未验证外链必须报障碍。仅学历 graduate、零经验、trainee 不能自动判为校招；仅明确 fresh/recent/new graduates 或明确 graduate programme 纳入，实习和兼职单独排除。

166 详情初查有10条只有岗位标题、无职责资格，不能依据这种空白断言非校招，必须保留缺口，不启用正式绑定。Supervisor, Public Areas 明确 Fresh graduate is welcomed，但同段另列2年经验；如纳入候选，保留两句完整原文和冲突说明，不声称无经验要求。未知日期或字段不得填造。接口/身份/预算错误保留已成功岗位；单条失败继续其他详情，认证或预算耗尽停止。

列表没有可靠绝对发布日期，详情请求前使用公共增量钩子与完整列表指纹，未知日期首次必须读详情；不以相对日期预筛选。详情失败不 remember，全量 all 强制刷新由公共增量配置控制。

## 可验证验收条件

回放覆盖首/次/末页、后页 total0、越界重置不请求、首总数0失败、页短/重页/变总数、首屏复核、标题/ID/租户/路径错配、日期非法、附件、空正文、局部失败保留、增量列表证据与复用。UVsync/Ruff/ty/pytest 全部通过后临时绑定实采；完整 coverage 与源总数一致并审计通过才正式启用。当前空正文缺口仍存在时记录 partial，不能计入已完成数或汇总交付数。
