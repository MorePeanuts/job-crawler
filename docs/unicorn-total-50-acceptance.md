# SPEC-277 2026-10-22 累计 50 家最终验收

## 交付结果

用户将当日目标调整为累计新增并验收 50 家有正式校招岗位的不同企业，且允许从其他待接入企业补足。最终 **50/50 家**均有独立的 2026-10-22 真实采集快照、`coverage=complete`、终止的源目录和至少 1 条有效岗位；没有用昨日快照或零岗位来源补数。

50 份快照汇总共收集 **1,784** 条源记录，筛选出 **1,721 条有效岗位**，全部进入[今日岗位信息表](../outputs/2026-10-22/今日累计50家-20261022-岗位信息汇总.xlsx)。其中 **414 条**满足导入约束，进入[严格导入表](../outputs/2026-10-22/今日累计50家-20261022-严格导入.xlsx)；**1,307 条**在 `review.json` 待补全。其余 63 条未通过正式校招、在招状态等范围筛选。岗位属于 `all` 窗口的当日在招存量，不能称为全部当日新发布；源未给发布日期的岗位维持空值。

逐源实采时间（上海）：`2026-10-22T10:22:20.986561+08:00` 至 `2026-10-22T13:53:46.937381+08:00`；最终离线汇总时间：`2026-10-22T13:56:31.086951+08:00`。

只读审计 `.runtime/batches/unicorn50-20261022/delivery-audit-final.json` 返回 `ok=true`，50 个不同企业 ID、50 个来源，信息表 1,721 行、严格导入表 414 行与快照报告一致。最终归档为 `.runtime/runs/unicorn50-20261022-delivery50`，由 `.runtime/archive-index.json` 定位压缩文件。批次基线、逐站输入和审计分别保存在 `.runtime/batches/unicorn50-20261022/baseline.json`、`inputs-50.json`、`delivery-audit-final.json`。

## 逐源岗位统计

以下计数来自各独立运行报告。每站 `coverage=complete`，所有 scope 都 `terminal=true`；导入待补全属于字段质量问题，未将目录残缺视为成功。入口链接以当前正式来源文件为准。

| 来源 ID | 企业 | 招聘入口 | 有效岗位 | 严格导入 | 待补全 | 实采时间（上海） |
| --- | --- | --- | ---: | ---: | ---: | --- |
| COM0519 | 大疆 | [apply.careers.dji.com](https://apply.careers.dji.com/campus-recruitment/dji/143359?locale=zh-CN#/jobs) | 142 | 141 | 1 | 10:22:20 |
| COM0525 | 货拉拉 | [app.mokahr.com](https://app.mokahr.com/campus-recruitment/huolalahr/98660#/jobs) | 41 | 23 | 18 | 10:22:20 |
| COM0571 | 莉莉丝 | [lilithgames.jobs.feishu.cn](https://lilithgames.jobs.feishu.cn/campus) | 19 | 0 | 19 | 10:25:06 |
| COM0574 | 蓝箭航天 | [uq1h428xyc.jobs.feishu.cn](https://uq1h428xyc.jobs.feishu.cn/522146/position/list) | 71 | 0 | 71 | 10:25:06 |
| COM0659 | 沃飞长空 | [app.mokahr.com](https://app.mokahr.com/campus-recruitment/geely/94419#/jobs) | 32 | 32 | 0 | 10:27:24 |
| COM0612 | 中关村科金 | [weikezhijia.jobs.feishu.cn](https://weikezhijia.jobs.feishu.cn/952383/position/list) | 25 | 0 | 25 | 10:31:27 |
| COM0617 | 高仙机器人 | [wecruit.hotjob.cn](https://wecruit.hotjob.cn/SU6629d2ce1eb8053acd8065ac/pb/school.html) | 31 | 31 | 0 | 10:31:27 |
| COM0729 | 此芯科技 | [cixin.zhiye.com](https://cixin.zhiye.com/campus/jobs) | 21 | 5 | 16 | 10:31:27 |
| COM0506 | 小红书 | [job.xiaohongshu.com](https://job.xiaohongshu.com/campus/position) | 166 | 0 | 166 | 10:37:44 |
| COM0508 | 荣耀 | [career.honor.com](https://career.honor.com/SU60eea919bef57c1023f6fe78/pb/school.html) | 101 | 0 | 101 | 10:40:49 |
| COM0608 | 依图科技 | [www.yitutech.com](https://www.yitutech.com/cn/career?mode=campus) | 3 | 0 | 3 | 10:44:37 |
| COM0594 | 辰瑞光学 | [www.aacoptics.com](https://www.aacoptics.com/?page_id=1517) | 2 | 0 | 2 | 10:52:20 |
| COM0535 | 万得 | [www.wind.com.cn](https://www.wind.com.cn/mobile/JoinUS/RecruitDetail/zh.html?entry=school) | 16 | 0 | 16 | 10:55:14 |
| COM0507 | Oppo | [careers.oppo.com](https://careers.oppo.com/university/oppo/campus/post) | 146 | 0 | 146 | 10:59:01 |
| COM0509 | 米哈游 | [jobs.mihoyo.com](https://jobs.mihoyo.com/#/campus/position?jobName=&projectIds%5B0%5D=13) | 129 | 0 | 129 | 10:50:17 |
| COM0666 | 开沃汽车 | [www.skywellcorp.com](https://www.skywellcorp.com/website/skywellcorp/recruitment?tab=2) | 44 | 0 | 44 | 11:03:26 |
| COM0558 | 多益网络 | [sz.duoyi.com](https://sz.duoyi.com/v40/#/positions?recruit=10) | 33 | 0 | 33 | 11:06:04 |
| COM0511 | Vivo | [hr-campus.vivo.com](https://hr-campus.vivo.com/campus/jobs) | 36 | 8 | 28 | 11:16:57 |
| COM0784 | 微店 | [hr.weidian.com](https://hr.weidian.com/campus/jobs) | 6 | 0 | 6 | 11:19:48 |
| COM0530 | 正泰安能 | [campus.chint.com](https://campus.chint.com/campus-recruitment/chint/40745/#/jobs?department%5B0%5D=725411) | 45 | 41 | 4 | 11:31:03 |
| COM0575 | KK集团 | [kkguan.zhiye.com](https://kkguan.zhiye.com/campus/jobs) | 9 | 1 | 8 | 11:48:34 |
| COM0319 | 苏宁易购集团股份有限公司 | [campus.suning.cn](https://campus.suning.cn/rps-campus/ftl/campus/managePlan.htm?type=manage) | 11 | 0 | 11 | 11:49:05 |
| COM0630 | 芯驰科技 | [app.mokahr.com](https://app.mokahr.com/campus_apply/semidrive/42941#/) | 7 | 1 | 6 | 12:11:08 |
| COM0622 | 波克 | [boke.jobs.feishu.cn](https://boke.jobs.feishu.cn/581609/position/list) | 100 | 0 | 100 | 12:10:53 |
| COM0585 | 转转 | [zhuanzhuan.zhiye.com](https://zhuanzhuan.zhiye.com/campus/jobs) | 11 | 1 | 10 | 12:14:41 |
| COM0598 | 燧原科技 | [app.mokahr.com](https://app.mokahr.com/campus-recruitment/enflame/168420#/jobs/) | 48 | 26 | 22 | 12:13:48 |
| COM0682 | 认养一头牛 | [ryytn.zhiye.com](https://ryytn.zhiye.com/campus/jobs) | 15 | 0 | 15 | 12:17:09 |
| COM0603 | 星星充电 | [talent.wbstar.com](https://talent.wbstar.com/campus/jobs) | 22 | 0 | 22 | 12:19:43 |
| COM0679 | 镁伽 | [megarobo.zhiye.com](https://megarobo.zhiye.com/campus/jobs) | 20 | 11 | 9 | 12:28:44 |
| COM0748 | e签宝 | [esign.zhiye.com](https://esign.zhiye.com/campus/jobs) | 7 | 0 | 7 | 12:33:12 |
| COM0756 | 飞骧科技 | [www.lansus.com](https://www.lansus.com/about/careers/campus-jobs) | 15 | 0 | 15 | 12:37:49 |
| COM0538 | 智己汽车 | [saic-recruit.saicmotor.com](https://saic-recruit.saicmotor.com/recruit/pc/#/collegeRecruit) | 2 | 2 | 0 | 12:48:53 |
| COM0785 | 享道出行 | [saic-recruit.saicmotor.com](https://saic-recruit.saicmotor.com/recruit/pc/#/collegeRecruit) | 8 | 4 | 4 | 12:49:12 |
| COM0726 | 傅利叶 | [app.mokahr.com](https://app.mokahr.com/campus-recruitment/fftai/147078#/jobs/) | 15 | 15 | 0 | 12:51:27 |
| COM0750 | XTransfer | [xtransfer.zhiye.com](https://xtransfer.zhiye.com/campus/jobs) | 5 | 1 | 4 | 12:55:26 |
| COM0602 | 兆芯集成 | [campus.51job.com](https://campus.51job.com/zhaoxin2027/job.html) | 24 | 0 | 24 | 12:59:18 |
| COM0721 | 思朗科技 | [smartlogictech.jobs.feishu.cn](https://smartlogictech.jobs.feishu.cn/xiaozhao/position/list) | 44 | 0 | 44 | 13:01:30 |
| COM0700 | 加特兰 | [app.mokahr.com](https://app.mokahr.com/campus_apply/calterah/1109#/) | 26 | 17 | 9 | 13:09:54 |
| COM0685 | 芯粤能 | [app.mokahr.com](https://app.mokahr.com/campus-recruitment/ascenpower/166280#/) | 10 | 9 | 1 | 13:10:10 |
| COM0680 | 镁信健康 | [meditrusthealth.m.zhiye.com](https://meditrusthealth.m.zhiye.com/yjlist.html) | 8 | 0 | 8 | 13:12:04 |
| COM0582 | 芯迈 | [campus.51job.com](https://campus.51job.com/SiliconMagic2026/job.html) | 26 | 0 | 26 | 13:16:24 |
| COM0707 | 数坤 | [shukun.zhiye.com](https://shukun.zhiye.com/campus/detail?jobAdId=24544e10-8954-4ff6-ad43-ae646a4c5c04) | 13 | 0 | 13 | 13:19:24 |
| COM0611 | 粤芯半导体 | [cansemitech.zhiye.com](https://cansemitech.zhiye.com/campus/jobs) | 20 | 0 | 20 | 13:22:07 |
| COM0505 | 微众银行 | [app-tc.mokahr.com](https://app-tc.mokahr.com/campus-recruitment/webankhr/20060?locale=zh-CN#/jobs) | 9 | 9 | 0 | 13:25:10 |
| COM0540 | 宇树科技 | [unitree.zhiye.com](https://unitree.zhiye.com/campus/jobs) | 35 | 0 | 35 | 13:26:39 |
| COM0321 | 碧桂园服务控股有限公司 | [app.mokahr.com](https://app.mokahr.com/campus-recruitment/bgyfw/47073/#/jobs) | 16 | 0 | 16 | 13:28:44 |
| COM0692 | 智平方 | [ai2robotics.jobs.feishu.cn](https://ai2robotics.jobs.feishu.cn/094992/position/list) | 18 | 0 | 18 | 13:49:19 |
| COM0675 | 联合飞机 | [www.uatair.com](https://www.uatair.com/about/school.html) | 39 | 15 | 24 | 13:50:18 |
| COM0620 | 蕉内 | [bananain.zhiye.com](https://bananain.zhiye.com/campus/jobs) | 23 | 18 | 5 | 13:51:49 |
| COM0529 | 嘉立创 | [jlcehr.zhiye.com](https://jlcehr.zhiye.com/campus/jobs) | 6 | 3 | 3 | 13:53:46 |

## 目录边界与限制

- 最后接入的 10 家为芯迈、数坤、粤芯、微众银行、宇树科技、碧桂园服务、智平方、联合飞机、蕉内、嘉立创。各站源计数、筛选与岗位字段契约分别见 SPEC-289 至 SPEC-298；其中 COM0529 嘉立创北森独立品牌租户的租户标题、隐私政策和岗位正文可识别企业与 2027 届，但企业官网没有直接指向该租户的链接，证据边界已在 SPEC-298 记录。
- 原始独角兽剩余入口中仍有空目录、仅实习、集团法人范围不清及访问阻断来源；未计数也未启用这些候选。具体已尝试入口和障碍见[原始候选验收记录](unicorn-remaining-58-acceptance.md)及 [SPEC-277](../specs/277-unicorn-remaining-fifty-eight.md)。先前阶段记录中的“当前不足 50”是当时状态，以本最终审计为准。
- 1,307 条待补全记录保存在最终归档 `review.json`。缺失地点、分类、学历或发布日期等源字段没有编造；后续获得可靠数据可从归档恢复后重新导出。

## 复核与质量门禁

```sh
uv run job-crawler restore .runtime/runs/unicorn50-20261022-delivery50 \
  --output .runtime/runs/unicorn50-20261022-verify
uv run python .agents/skills/add-recruitment-adapters/scripts/audit_delivery.py \
  .runtime/runs/unicorn50-20261022-verify --expected-companies 50
```

上述复核复用本日快照，不会重新访问招聘站点。若要重新汇总，按归档索引恢复 `inputs-50.json` 中已归档的输入路径，再执行 `bundle`。新采集应重新访问网站确认届时在招状态。

完整质量门禁：`uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run ty check`、`uv run pytest`。
