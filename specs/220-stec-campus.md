# SPEC-220 隧道股份公开单位校园招聘

状态：已实现并真实验收；SPEC-156固定B组COM0287。

## 目标、输入与非目标

输入上海隧道工程股份有限公司官方zhaopin.stec.net。按校园招聘公开八类、全部二级单位读取Job/Scope、原始证据与岗位导出；本轮18单位，含集团总部及区域总部。输出公司名使用名录，单位保留ClassificationTwo。只读取公开招聘，不操作投递、注册、收藏，不访问旧脚本注释里的内网地址，不使用脚本error回调静态2023示例。

## 真实页面契约

根页POST /api/OpenCustomization/GetJobAdCustomTypeList?portalId=33063664-e982-4f2f-8621-63ad81a31700，TypeCode2；Code200、Data.Type.TypeCode2、Items为八类。Count0不是岗位数。页面handleRecruitMenu/handleRecruitMenuItem及zhaoPin_getCompanyCategory展示二级单位，并隐藏三级内招专用条目。只遍历全部二级单位，三级若出现非明确内招分支则失败待核对，不能随意遗漏新增公开范围。单位值唯一，空树/空分类不算零。

正常点击校园招聘→上海隧道工程有限公司，实际POST /api/JobAd/GetJobAdPageList?portalId=同上，PageIndex0、PageSize1000、Category["2"]、ClassificationTwo[单位Value]、ClassificationOne/LocId空、KeyWords空、SpecialType0、PortalId空；DisplayFields按页面实际配置。列表直接包含Duty/Require全文，页面展开只是显示内联内容。按单位一次请求，Code200、Count必须等于完整数组长度且不超过1000；未来超过上限明确失败，不声称已实现超1000分页。本轮18单位总103条、103唯一Id，最大41，6单位明确Count0/[]。Total始终0，不能当总数。单位失败隔离，其他已成功范围保留。

每条Id/JobAdId唯一、CategoryId2、Status1、ClassificationTwo与请求单位相同，标题/职责/要求完整。正文图片、附件或链接变化须重新适配，不以去标签丢失内容。单位间重复ID失败。招聘性质Kind全职/实习必须已知。source_url保留实际公开校园根页，不能编造详情链接。

## 岗位范围与日期

Category2存在污染：4条实习；标题仅标社招且无校招/应届者不纳入；资格明确要求多年工作/专业实践经验且无应届可报或优先限定者亦不纳入。校招+社招、应届社招均可及经验优先保留；博士后正文明确应届博士可申请，保留一条公告岗位，不按五科研方向虚拆。全量103条保留原始字段与work_type以共同过滤记录排除，不删除证据。

职责Duty、要求Require、学历Degree、地点LocNames、详细地址DetailAddress；缺失不猜。PostDate是发布时间，核对PostDateInt中国时区同一时刻；EndTime0001-01-01与EndTimeInt0代表未知，保留空，不用发现时间/ChangeDate替代。明确业务截止按日期过滤。每次读取内联完整正文，无独立详情缓存需要。

## 验收与失败行为

回放覆盖18单位、103唯一岗位、6零目录、单位/类别/身份/日期错误、丢行/重复/超过1000、空树、遗漏新增公开分支、局部失败及实习/社招/多年经验/优先经验边界。完整uv sync、Ruff、ty、pytest通过后临时绑定真实全采；以实时总量核验守恒与范围筛选，单源审计通过才正式启用并加入B组。身份、正文、结构、业务或预算失败保留partial/blocked；不以fixtures或初始空白算实际完成。

## 验收记录

2026-10-18 12:38:43–12:39:32独立实采18单位、103唯一完整正文，6明确零单位；4实习与10明确社招过滤，89有效/89信息/1严格/88待补全。coverage complete，零采集问题；2条科创管理多方向岗位分类未决，原文保留、不猜分类。25项新测试及全量1248项、UVsync/Ruff/ty通过；单源与B41汇总审计通过，发布和归档字节一致。
