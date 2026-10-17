# SPEC-164 联发科技大陆校园门户

状态：已实现并通过完整实采和只读审计；SPEC-156 B 组 COM0176。

## 目标与非目标

完整遍历 mediatek.zhiye.com 官方大陆校园门户所有地区与职位类别。首页北京/上海/深圳/成都/合肥/武汉数量合计 19，与无筛选目录一致；不使用任何单城市链接代替全量。不纳入社招、实习，不声称覆盖其他地区独立招聘系统。

## 输入输出与契约

`/campus/jobs` 观察 `/api/Jobad/GetJobAdPageList`，PageIndex=0、PageSize=20、Category=["2"]、KeyWords=""、SpecialType=0、PortalId=""，无地区/类型筛选。Count=19，列表完整包含 Duty/Require。点击多媒体算法工程师进入 `/campus/detail?jobAdId=<Id>`，页面正文与列表相同。复用 Zhiye listing_complete + regular_only 契约，按稳定总数、唯一 Id 和末页核对全量。

保留 JobAdName、LocNames、PostDate、EndTime、Degree、ClassificationOne 和原始正文；Org 未公开保持空，学历通过公共流程从要求辅助提取，0001 截止哨兵为空。无省市层级映射的地点保留原文，不臆造。

## 失败与验收

目录过滤残留、非校园 CategoryId、正文缺字段、重复页/提前终止及总数变化均不算完整。共享回放覆盖两页、无重复详情请求、未知单位留空和实习标记。临时绑定实采需确认唯一岗位数 19 与首页各城市计数闭合、公共分类导出完成、只读审计通过，再启用正式绑定。实时数量变化以新一轮稳定目录为准。
