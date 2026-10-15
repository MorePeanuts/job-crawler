# SPEC-128 超聚变公开校园招聘

状态：已实现并通过 2026-10-15 真实全量目录验收；归属 SPEC-101。

## 目标与输入输出

从名录 COM0285（超聚变数字技术股份有限公司）的官方 `career.xfusion.com/OfficialPortal/#/campusList` 采集当前公开校园招聘的全部正式岗位，按目录分页、主岗位方向、逐岗位详情生成程序化岗位快照与标准导出。沿用公共筛选、增量、字段校验和留证流程。

## 非目标

不采集社会招聘、实习生招聘、不投递或注册；不凭主岗位卡片代替方向岗位，不从更新日期推断发布日期，不给未公开的截止时间补值。

## 已观察契约

- 页面校园入口发出跨域 `POST /api/xJob/xjobpostdeliver/osPostpagelist?pageSize=10&curPage=1&X-HW-ID=...`，请求体 `pubChannel="2"`，其它岗位类别、部门、地点及关键字筛选为空。公开请求头 `lang=zh_CN`、`datasource=6`、`X-HW-ID` 与 URL 参数同值，均由本轮页面请求观察，不硬编码。翻页须验证 `pageVO.totalRows/curPage/pageSize/totalPages` 一致，逐页身份 `mainPostId`（主岗位）或 `postIdKey`（独立岗位）唯一，到源总数才闭合。
- `postCnt>0` 的卡片以 `mainPostDeliverDetail?mainPostId=...&pubChannel=2` 展开 `postList`；长度须等于 `postCnt`。`postCnt=0` 的卡片以其 `postIdKey` 直接进入详情。所有叶子岗位通过 `postDeliverDetail?postId=...&pubChannel=2` 获取身份、发布状态、职责、要求、首次发布时间、地点与实际部门。主岗位和独立岗位的叶子 ID 不可重复。
- 2026-10-15 探测目录 92 项，其中 18 项为主岗位；展开后 198 个不重复叶子 ID。该数仅为探测基线，真实采集必须重新读取和核对，不写死为预期产量。
- 仅保留公开校园频道 `postPubChannList[].pubChannel=2` 且 `jobType=1/全职`、在目录中仍公开的岗位。`firstPubTime` 才作为发布时间；`updateTime` 不替代。源站没有截止时间则为空。可能出现已关闭或实习的叶子岗位时保留列表证据并明确过滤。

## 失败行为与验收

目录响应失败、筛选结构变化、页码或总数不一致、主岗位方向数量不符、重复叶子 ID、详情身份错配或局部分支失败均保持 `coverage=partial`，保留已成功岗位与证据。仅当 92 项目录在本轮完整翻完、每项的方向/详情均核对、计数平衡且有效正式岗位大于零，COM0285 才可计入本批 50 家；实际总数以实采为准。回放测试覆盖分页末端、主岗位展开、重复身份、详情错配与局部失败；另记录真实站点目录数、叶子数、选中数和导入待补全数。

## 实际验收

`outputs/dev-20261015-COM0285` 于 12:12 上海时间运行，92 项卡片全量分页，18 个主岗位展开，198 个唯一叶子岗位逐岗详情核对；`expected=listed=unique=details=92`、`coverage=complete`、正式校招选中与信息表 198 条。目录本身按主岗位计数，叶子岗位数为 198；不得将 92 误报为岗位数。严格导入 0，分类/地点等字段仍待公共交付补全。`tests/test_xfusion.py` 覆盖分页、方向展开和局部失败。真实快照与状态库分离保存。
