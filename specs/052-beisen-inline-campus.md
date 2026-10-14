# SPEC-052 北森列表完整正文的校园租户

状态：已实现并真实验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0425 深圳迈瑞生物医疗电子股份有限公司的 `https://career.mindray.com/campus/jobs` 与 COM0440 申洲国际集团控股有限公司的 `https://career.shenzhouintl.com/campus/jobs`，只采集各自公开 Category=2 的正式校园岗位。两站列表均展示实际岗位，且已观察的 `GetJobAdPageList` 记录直接包含 `Duty` 和 `Require` 全文；申洲点击列表卡进入 `/campus/detail?jobAdId=<列表 Id>`，页面正文与列表同源。迈瑞公开目录另含博士校招，不因学历层次高而排除。

不采社招/实习，不把 Group 门户其他法人岗位自动归给这两个主体；若列表单位字段出现跨法人且无法确定归属，本站保持待核验。列表当前未出现发布时间或学历源字段时留空，不用更新时间、岗位名或正文描述虚构日期及最低学历。

## 已观察输入与输出契约

两站从各自 `/campus/jobs` 发起 POST `/api/Jobad/GetJobAdPageList`，第一页 `PageIndex=0`、`PageSize=20`、`Category=["2"]`，其他筛选项为空。迈瑞当前目录 64 条，申洲当前目录 40 条；这些是探测时计数，验收以实际运行时稳定源总数为准。每页以 `Id` 去重，逐页遍历至 `Count`，核对列表 `CategoryId=2`、非空标题、`Duty` 与 `Require` 字段。列表直接提供完整正文时不再强制加载 `GetJobAdInfo`；来源岗位链接仍使用本站实际卡片对应的 `/campus/detail?jobAdId=<Id>`。

每个 `Job` 保留源 ID、标题、单位、地点、学历、分类原值、职责、要求、已提供的发布日期及截止时间，以及列表响应证据。空目录仅在 `Count=0`、`Data=[]` 且目录来源已确认时为完整零岗位。重复 ID、总数变化、非校招类别、缺正文、未知筛选、预算或请求失败必须保留成功记录并使 coverage 为 partial/blocked。

## 验收

1. 回放验证两租户的第一页请求、跨页总数与去重、列表全文、不读无必要详情、类别或正文异常和局部失败。
2. 两家分别实采至 `Count=listed=unique=details`，核对主体归属和有效岗位，来源覆盖为 complete 后才加入正式绑定。
3. 运行 SPEC-050 门禁，保留完整快照与十三列表格；严格导入缺值进入待补全。

2026-10-14 11:09–11:10（上海）实采迈瑞 64/64、申洲 40/40，两个来源 coverage 均为 complete；逐项证据与命令见 `docs/adapter-batch7-acceptance.md`。
