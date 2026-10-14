# SPEC-062 华友钴业 Hotjob 校园目录

状态：已实现并真实验收。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

接入 COM0230 浙江华友钴业股份有限公司的公开校招。官方 `https://campus.huayou.com` 实测跳转至 `wecruit.hotjob.cn` 租户 `SU6465f3d9bef57c0907f3bb58`；其 `/pb/school.html` 提供校园招聘岗位。读取不带局部筛选的 `recruitType=1` 全目录，保留项目和实际招聘单位，只纳入仍展示且未截止的正式应届生与大专生岗位。

不把“实习生招聘”和“校园大使招聘”算成正式岗位，不因某个地区或项目筛选只剩少量结果就称完整。无明确截止或发布日期不推断，已截止的岗位按公共规则排除。

## 输入输出与失败行为

页面实际向 `/wecruit/positionInfo/listPosition/<suite>` 提交表单 `isFrompb=true&recruitType=1&pageSize=12&currentPage=1`。响应 `pageForm.dataCount`、`totalPage`、`currentPage` 和 `pageData[].postId`；探测时为 197 条、17 页。每页按 `postId` 去重，严格核对总数/页号/末页，详情从同租户 `/positionInfo/listPositionDetail/` 读取并核对 `postId` 与 `recruitType=1`。地点树来自同站 `/positionInfo/listSearchTerm/`，不能凭城市名猜省份。

列表的 `publishFirstDate` 是首次发布时间，`publishDate` 为更新日；优先使用首次发布日。输出标题、项目、单位、地点、学历、职责、要求、日期和证据，经公共流程分类、筛选并导出两份十三列表。登录只用于投递时可继续读取公开岗位。

请求失败、总数变化、重复 ID、详情身份或招聘类型不符、源字段缺失、访问受限时保留成功记录及错误，coverage 非 complete；明确零岗位且穷尽目录也不计入 50 家有岗位企业。

## 可验证验收条件

1. 离线回放验证租户请求、首/末页、详情 ID、项目中的实习和校园大使排除、日期与局部详情失败；Hotjob 既有测试回归。
2. 实采证明页数和总数一致、详情读完或有明确跳过理由、`coverage=complete`、有效正式校招大于零，确认各单位属于华友集团招聘范围。
3. 验收后才写来源和正式绑定；汇总及归档遵循 SPEC-050。
