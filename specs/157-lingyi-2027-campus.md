# SPEC-157 领益智造 2027 Moka 校招

状态：待实现与真实验收。属于 SPEC-156 A 组 COM0308。

## 目标、范围与依据

旧 Hotjob `SU600e1e985d83dc11e4a3e07f` 本轮显示系统维护。中南大学发布的企业招聘公告 `https://career.csu.edu.cn/campus/view/id/589751` 指向 `https://app.mokahr.com/campus-recruitment/lingyiitech`，实际跳转站点 182049，页脚为广东领益智造股份有限公司，且链接回公司官网。

纳入官方 2027 届本硕博校园站完整目录；首页六类数量 3+5+3+3+6+15=35，与无筛选职位列表 35 一致。不扩展社会招聘、实习或其他组织站点。

## 输入输出和契约

输入 COM0308，入口 `https://app.mokahr.com/campus-recruitment/lingyiitech/182049#/jobs`，复用 Moka。
本轮页面观察到 `/api/outer/ats-apply/website/jobs/v2` POST：orgId=lingyiitech，siteId=182049，site=campus，limit=30，offset=0，needStat=true，空 jobIdTopList/customFields，无地区或职能筛选。
按 offset 遍历，以 jobStats.total 和唯一 ID 核对终态；详情从页面观察到的 website/job 读取并关联 ID，额外核对标题。首页 module 不是采集入口，不将其首屏当全量。
每页响应使用本轮页面公开 IV 解码，不保存凭据到源码。发布时间取 publishedAt，截止时间取源字段；地点保留全部城市，不填造详细地址。输出公共十三列岗位表和证据快照，分类与学历由公共 delivery 完成。

## 失败行为

组织/站点/招聘类型不匹配、重复页、总数变化、详情错配或无完整正文均保留问题。异常不视为零岗位；只有真实覆盖完整才启用绑定。

## 验收

- tests/test_moka.py 扩展真实平台契约回放：分页、详情、实习原类型、标题错配拒绝；复用重复页、缺正文及增量测试。
- 临时来源/绑定实采，核对 35 目录与详情身份、全部页末端、selected/exported/review；记录实际结果，不预设成功。
- 完整质量门禁通过后启用正式绑定、更新来源入口与本批验收台账。
