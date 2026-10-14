# SPEC-090 万华化学 2027 校招

状态：已实现并真实验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0139 万华化学集团股份有限公司 2027 校招公开 Hotjob 租户 `https://wecruit.hotjob.cn/SU6a7ad69c43154813049755d7/pb/school.html`。高校发布的[万华化学 2027 招聘简章](https://career.nankai.edu.cn/recruitment/content/type/2/id/6046.html)明确对应此届次及万华化学主体；岗位逐条须由源列表 `company`、`orgCode` 和详情 `orgName` 验证。只收本公司正式校招；独立子公司、实习、社招和身份不明岗位不归本来源。不进入投递流程。

## 输入、输出和失败行为

使用 Hotjob 已验证的 `recruitType=1` 无筛选目录、`listSearchTerm` 地点树及 `listPositionDetail` 公开详情。按返回 `dataCount`、`totalPage` 和每页唯一 `postId` 遍历；条目需 `company=orgName=万华化学集团股份有限公司`、`orgCode=0`、`projectName=本硕博招聘`、`projectId=100001`。源 `publishFirstDate` 为首次发布时间，`publishDate` 仅更新时间；截止日来自 `endDate`。岗位数量不展开为职位记录。其他城市的岗位只要源详情明确同一主体也纳入，但记录实际地点；任一身份冲突须报告并保留已成功岗位，不能把部分目录标为完整。正文无独立任职要求时保留空值，地点未能映射详细地址时进入待补全。

## 可验证验收条件

1. 离线回放验证源项目、法人身份、详情 ID、跨主体失败和既有 Hotjob 分页契约。
2. 当日独立状态库 `--window all` 全目录实采，所有页面、唯一 ID、详情数及源总数闭合，`coverage=complete` 且有效本公司岗位大于零。
3. 验收后才启用来源绑定，纳入新增企业审计和阶段总表，归档发布并通过 Ruff、ty、pytest。

## 验收记录

2026-10-14 17:22（上海）独立状态库、`--window all` 实采无筛选校招目录 93 条、7 页。93 个唯一职位 ID 的列表和详情均核对本级法人、机构编码和项目，`coverage=complete`、有效岗位 93 条、严格导入 52 条、待补全 41 条；未将人数展开为记录。离线分页及法人与项目回放见 `tests/test_hotjob.py`，阶段审计 `.runtime/batches/2026-10-14-stage41-audit.json` 通过，证据按 SPEC-047 归档。
