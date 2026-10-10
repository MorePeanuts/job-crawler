# SPEC-002 首轮四站适配器

状态：版本 1 已实现；网络验收结果单独记录。依据此前 `validation/crawl4ai-campus` 验证的接口与本轮程序观察迁移。

## 范围和接口

| 适配器/来源 | 范围与入口 | 列表/详情 | 唯一键与覆盖单位 |
| --- | --- | --- | --- |
| pingan / COM0012 | `/freshGraduates` 的 `positionType=1` 应届生，排除实习 | 观察 `queryPositionPage` 的 POST，保留实际负载，遍历 PageNum；列表包含职责/要求 | idPosition；岗位总数 totalCount 与 unique，逐页检查 totalPage |
| ccb / COM0008 | `plan_index.html?planType=XY` 全校招目录 | 观察 NHR104，PAGE_JUMP/REC_IN_PAGE 分页；NHR107 详情关联 orgId 使用当前行 secondOrgId 或 orgId | planId:planPost:orgId:secondOrgId；岗位×分支，总数 TOTAL_REC |
| cnpc / COM0002 | `/web/recruitInfolist.html`，type=1 高校毕业生 | listN 的 offset/max；showN 的 recruitId；每篇 post 数组展开 | announcementId:postId；源总数为启事，不是岗位 |
| alibaba / COM0015 | `/campus/position` 全 graduate 批次，排除实习；检查 AliStar | listBatch 的 graduate 目录；position/search 的 batchId/pageIndex；AliStar 入口配置和子集核对 | batchId:positionId；先核批次，再核岗位，阿里星是额外覆盖检查 |

绑定采用确定的已知域名；用户来源入口保留在名录。当前适配器不覆盖同企业其他招聘域名、社会招聘、实习或登录后独有岗位。不能把一个 URL 的成功推断成集团互联网所有岗位。

## 日期与字段

| 平台 | 发布时间 | 截止时间 | 主要字段 |
| --- | --- | --- | --- |
| 平安 | publishDate | 可选 endDate；当前样本未提供 | duty / qualification / education / workCity / positionCategoryName |
| 建行 | 详情 postDate，过期预筛选保留列表 postDate | 列表 endDate、详情 endTime | postDesc / PostRequest / cityName；样本缺少结构化学历 |
| 中石油 | showN.time1，公告级并保留来源 | showN.time2 | 岗位 remark/remark2/foreignRequire/professionDescribe，加公告 qualificationDemand/recruitStandard；educationRequiredName |
| 阿里 | publishTime，可为空，不能替换成 modifyTime | 可选 endTime；样本未提供 | description / requirement / degree / workLocations / categoryName |

未提供的学历或类别留待映射/模型处理。上述可选日期字段若不存在即为空，不从毕业日期等其他字段补造。没有截止日期且仍显示的岗位按 SPEC-001 保留。

## 失败与验收

列表业务失败、数量改变、ID 缺失/重复、详情关联错误、子目录遗漏或阿里星出现未覆盖 ID 均不能 complete。已抓取记录保留。0 条目录只有源计数和终止条件明确才能通过。

测试分两层：`test_adapters.py` 用合成响应验证分页、错误、复合键和公告展开；`test_observed_replay.py` 用最小真实响应字段验证结构。后者不是当前站点完整性验收。

真实运行使用 `uv run job-crawler run`，记录在 `docs/acceptance.md`。如果遇到 HTTP 412/403、脚本加载中断或导航超时，保存障碍，不伪造岗位或使用历史数据代替本轮数据。
