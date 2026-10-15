# SPEC-118 中国电信 2027 校园招聘

状态：已实现并通过真实覆盖验收。日期：2026-10-15。归属 SPEC-101。

## 目标与非目标

接入名录 COM0038 中国电信集团有限公司官方招聘站 `https://job.chinatelecom.com.cn/wt/TELE/web/index?brandCode=1` 的公开校园招聘。遍历集团页面列出的所有招聘单位和下辖岗位，保留逐岗实际招聘单位；排除社招、实习及已截止岗位。不注册、登录或投递，不把公告当逐岗记录。

## 输入、输出与平台契约

2026-10-15 首页 `getShowRecruitOrg?corpCode=TELE&recruitType=1` 返回 49 个不同 `uniqueKey` 的公开招聘根单位，页面同步显示“招聘单位(49)”。点击中国电信北京公司时，页面以 `mode400/position/list` 表单 `rowSize=50&rowIndex=1&recruitType=1&org=581617` 获取 `rowCount=23` 及岗位行，再以 `mode400/position/detail` 表单 `postId=140002&recruitType=1` 获取正文。详细岗位显示 `SecondOrgName=中国电信北京公司`、`orgCode` 含根单位 ID、`name` 与列表标题相符；职责为 `workConcet`，要求为 `serviceCondition`。`ReleaseTime` 是源发布时间，未见截止日期时保留空白。

适配器逐个遍历实时单位树，每单位按 `rowCount` 和明确末页核对列表数，使用 `PostId` 唯一键并核对招聘类别 `RecruitType=1`。详情逐条以列表 `PostId` 请求，核对标题、根单位归属及招聘项目，保留单位、地点、学历、专业、职责、要求和发布日期。根单位失败只影响该范围，保留其他已成功数据；同一岗位跨单位重复须报告覆盖问题。输出公共 Collection、13 列信息表与严格导入表。

## 失败行为

根单位数量或身份重复、分页/总数变化、详情和列表标题或单位不匹配、正文缺失、网络/访问错误及预算耗尽时保留证据和已采记录，受影响范围为 partial 或 blocked。不能用一省岗位代表集团，也不能把 49 家招聘单位当作 49 家名录企业。

## 可验证验收条件

1. 回放覆盖多个根单位、两页以上、详情关联、重复岗位及局部失败。
2. 真实采集全部 49 个当前单位，逐范围 `expected=listed=unique`、任务闭合且 `terminal=true`，集团 coverage=complete 且有效正式校招大于零。
3. 通过后才启用正式来源/绑定并计入本批 1 家。

## 真实验收

2026-10-15 11:16（上海时间）以 `--window all` 和禁用模型的覆盖验证配置重跑，快照 `outputs/dev-20261015-COM0038-v2`。首页 49 个根单位逐一遍历，范围汇总 `expected=listed=unique=details=2850`，49 个均 `terminal=true`，`coverage=complete`；正式校招选中、信息表及待补全均为 2850 条，严格导入 0 条。首轮 996 条因部分 2027 校招详情未返回 `quickRecruitType` 而截断；修复为该字段存在时校验 21，缺失时要求源项目明确写有“校园招聘”，再全量复采。回放见 `tests/test_chinatelecom.py`。
