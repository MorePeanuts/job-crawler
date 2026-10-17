# SPEC-163 鸿海 / 富士康官方校园目录

状态：已实现并通过完整实采和只读审计；SPEC-156 A 组 COM0005。

## 目标与范围

名录鸿海精密工业股份有限公司的富士康官方校园门户 foxconn.hotjob.cn，全部机构、城市和职位类别。沿用来源主体名，实际事业群保留 orgName；不把一个“通用岗位”拆成正文提及的近百个职位，不采社招或实习，不凭旧页头 2026 标签排除正文明确为 2027 的当前岗位。

## 契约与输出

入口 `/wt/Foxconn/web/index/CompFoxconnPagerecruit_School` 跳转经典 Hotjob 目录。观察 GET `/wt/Foxconn/web/json/position/list`，recruitType=1、brandCode=1、page=1，positionType/comPart/sicCorpCode/releaseTime/projectId/workPlace/keyWord 为空，site 亦为空。响应 req_state=9200、pageCount/page/rowCount/rowSize/postList，初始唯一一条，rowSize=10 与请求 rowSize=50 不同，按返回分页元数据核对。

稳定 postId=245937，postName=Rayprus-通用岗位，实际机构 Rayprus。列表包含完整 workContent/serviceCondition，与已点击详情页面一致。详情路由 `/wt/Foxconn/web/templet1000/index/positionInfoFoxconn!getOnePosition?brandCode=1&lanType=1&showComp=true&postId=<id>&recruitType=1`。publishDate=2026-10-13，endDate=2026-10-18；按源日期语义，截止当天包含在内。学历 education、地点 workPlace、类别 postType，缺失地址留空。

## 实现、失败和验收

提取伊利已验证经典 Hotjob GET 分页为公共基类，伊利继续保留总部/部门/2027 届限制，不扩大其范围。富士康保留全部机构，明确校招类型和全职/实习标记；分页总数变化、重复页、末页不闭合、筛选残留、未知类型、正文缺字段均失败并保留已采记录。

回放覆盖分页、重复身份、混入招聘类型、正文缺失、截止当天有效及通用岗位保持一条。复跑伊利边界测试，临时绑定实采核对一条真实目录、分类及两份表格；通过只读审计和质量门禁后启用。零岗位或通用职责无法分类时透明记录，不强行凑数。
