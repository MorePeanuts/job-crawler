# SPEC-025 前程无忧 COAPI 校招站点

状态：代码与真实全量覆盖已验收。2026-10-12；导出见 `docs/adapter-batch3-acceptance.md`。

接入宁波华翔 COM0489 与中粮集团 COM0043 两个公开活动页。前者页面通过 `coapi.getJobList` 一次取得 31 条目录、`resultbody.totalnum` 与 31 张卡片核对；后者通过 `be.51job.com/zhongliang/index.php/index/position_list` 的空筛选表单分页，首轮总数 590。两站点击岗位时均调用公开 `coapi.getJobDetail(jobid)`，返回独立职责、要求、学历、地点、发布时间等字段。以 `jobid` 为唯一键，并核对详情 ID、租户 `ctmid`、页面目录与源计数。

浏览器中的 COAPI 使用脚本回调，不属于当前传输层记录的 XHR/fetch。适配器必须显式计入每次回调请求预算，把当轮返回 JSON 写入忽略目录作为岗位证据，不复用历史登录态，不访问投递入口。中粮列表自带 `issueDate`、`validDate`，用于源发布时间与截止日；宁波华翔使用公开详情的 `issuedate`。已截止岗位可按列表日期跳过详情并保留简略记录。

若源目录总数变化、重复 ID、未知租户、详情身份不符、职责缺失、JSONP 回调超时或列表尚有分页，保存已获记录并标记 partial，不将空或部分结果当作 ready。回放覆盖分页、详情、身份和日期边界；两个真实全量运行均须 `coverage=complete` 后启用绑定，程序导出十三列岗位表与待补全报告。
