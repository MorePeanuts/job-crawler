# SPEC-020 智联招聘校招活动页

状态：代码与真实全量覆盖已验收。2026-10-12；导出见 `docs/adapter-batch3-acceptance.md`。

## 目标与非目标

接入本轮已观察到 `fe.zhaopin.com/grace/api/dsc/search-job-list` 的公开校招活动页。首批租户为中国联通 COM0069、上港集团 COM0373、重庆银行 COM0420、龙佰集团 COM0491。适配器只采 `jobSource=2` 的校招岗位；不采社招、不访问投递接口、不把接口 `modifiedTime` 当作发布时间。

## 输入输出与范围

从用户名录的原域名、已观察的业务接口和原始 JSON 请求构建同 `orgNumbers` 的无部门/地区/标签筛选请求。首批租户的无筛选目录分别返回 2818、43、46、23 条，均有 `pageInfo.totalNum/totalPage`、岗位 `jobNumber`、标题、正文、学历、地点和投递链接。以 `jobNumber` 为唯一键，按页读取全部列表；该接口的列表已含完整 `job.detail`，无须二次访问投递页面。输出 `Job` 与证据，由公共交付流程生成十三列 Excel、待补全报告与快照。

## 失败行为

接口未观察到、来源域名不符、`jobSource` 改变、`orgNumbers` 与租户不符、存在未清除筛选、分页总数或页码变化、重复 ID、正文缺失、跨租户公司归属不符时保持 partial/blocked，保留已获得记录和证据。不能把初始首页的单位筛选数当作整站总数。无明确发布时间时字段留空，日窗口按公共 SPEC-009 规则处理。

## 可验证验收

1. 回放覆盖首页带部门筛选、清空筛选后的首/次/末页、完整正文、重复页、源计数变化和零目录；各租户必须通过入口域名与 `orgNumbers` 核验。
2. 四站真实 Crawl4AI 全量运行的 `expected=listed=unique=details`、`terminal=true` 且 `coverage=complete`，岗位归属抽查与源总数一致。
3. 快照离线汇总成十三列 Excel，严格导入与待补全分别报告；README/验收记录陈述可导入限制与无发布日期。
