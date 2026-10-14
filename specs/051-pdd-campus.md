# SPEC-051 拼多多应届生公开岗位目录

状态：已实现并真实验收。日期：2026-10-14。归属 SPEC-050。

## 目标与范围

接入名录 COM0065 拼多多控股公司的官方拼多多集团 PDD 校园招聘入口 `https://careers.pddglobalhr.com/campus/`，采集“应届生招聘”公开目录 `https://careers.pddglobalhr.com/campus/grad` 中所有正式校招岗位。该目录页面明确与独立的“实习生招聘”分离。页面显示 2027 届招聘项目，当前首轮观察为 34 条。

不采集实习目录、校招公告、社招或申请动作；不把首页卡片、第一页或仅有目录标题当完整岗位交付。名录主体名称保留原值，实际岗位未给法人公司字段时，不推断子公司。

## 已观察平台契约

目录页面 POST `/api/careers/api/recruit/position/list`，初始 JSON 为 `{"page":1,"pageSize":10,"t":null}`，响应 `success=true`、`result.total` 和 `result.list`。每条有唯一 `id`、`name`、`workLocationName`、`jobName`、`releaseTime`（毫秒 Unix 时间戳）、`jobDuty`、`graduationYear`。适配器保留源端第一页无其他筛选，逐页请求至唯一 ID 数等于稳定的 `total`；重复、空页提前出现、计数变化都报告不完整。

岗位页面 `/campus/grad/detail?positionId=<id>` POST `/api/careers/api/recruit/position/detail`，请求为 `{"id":"<id>","t":null}`。详情 `result.id` 必须与对应列表记录匹配，正文 `jobDuty` 和资格 `serveRequirement` 分开保存；`releaseTime` 只作为发布时间，未观察到截止日期和详细地址时留空。`normal` 源字段目前为真，但其完整业务语义未知，不用它推造截止日期；若详情声明不可用或响应异常则保留局部失败，不把该条记为成功。投递页面和二维码不调用。

## 输入、输出和失败行为

输入为 COM0065 官方 URL 和受控 Crawl4AI 会话；输出 `Job`、逐页 `Scope`、证据引用、报告、程序生成的十三列表格。岗位键使用详情 ID，工作类型为校招；学历若源站只有正文要求则交给公共补全层，不自行猜填。每条详情在增量模式下走公共复用钩子，`all` 实采仍须重新核对。

列表或详情业务错误、ID 不匹配、缺少正文结构、重复页、总数漂移或访问预算触顶时，保留成功岗位和问题，并使 coverage 为 partial/blocked。空目录必须同时有 `total=0` 和空列表才可称完整零岗位；零岗位不计入 SPEC-050 的 50 家。

## 可验证验收

1. 回放首/末页、重复页、总数漂移、详情 ID 错配和局部详情失败，成功范围满足 `expected=listed=unique=details+reused_details`。
2. 实采应届生目录至公开总数终点，逐条比对详情 ID、职责、要求与发布时间，不混入实习；记录真实采集时刻和有效岗位数。
3. 按 SPEC-050 质量门禁通过后才写入正式绑定，并在本批汇总中仅按一个公司 ID 计数。

2026-10-14 11:03–11:04（上海）实采 34/34 条，coverage=complete，正式校招 selected=34，严格导入 0，待补全 34；逐项证据与命令见 `docs/adapter-batch7-acceptance.md`。
