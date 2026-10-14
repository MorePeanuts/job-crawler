# SPEC-045 替代企业公开目录

状态：已实现并验收。

## 目标与已观察协议

- COM0269 金发科技：校园页实际加载 `/portal/list/getjobuslist.html`，表单 `category_id=459/jobad_category=2/list_tpl=list_job/page_size=20/page_num`。`job_list` 含完整正文；HTML `data` 的申请链接同时含岗位 JobId 和广告 Id，须逐条关联。按 `more_data=0` 终止，没有总数时不得自行捏造总数；重复页停止。只读公开列表，不调用申请操作。
- COM0351 正凯：官网校招页面 GET `listPosition?tenantId=1&type=1`，空岗位名/地点/公司筛选；result.records/total/current/size/pages 核对。保留子单位名，isShow=Y、delFlag=0；createTime/updateTime 是后台时间，未证明首次发布语义，发布日期留空。
- COM0445 安克：官方“查看所有岗位”页面请求公开 `open.anker-in.com/service/lark/openapi/getJobPosts/6962795203808217351`，按 page/size 分页，总数 total。列表不含完整任职要求，必须从对应公开岗位详情读取，验证 jobId/websiteId；排除实习招聘，modifyTime 不作发布日期。详情接口及字段以同一页面观察证据补充。

## 输出、非目标与失败

输入为名录企业和已验证的公开入口，输出标准 Job/Scope、原始证据和十三列表格。字段缺失保留待补全；不从后台操作人、HR 联系人等无关字段提取岗位值。不能以页内一类岗位或一个子单位代表目录，不能以空白页作为零岗位。

目录标识/类型变化、重复页、缺少明确末页、详情身份错配、总数变化均保持 partial/blocked。全部读取通过统一 Crawl4AI 浏览器会话和请求预算。

## 验收

测试分页终止、正文关联、实习排除、错租户/类别和局部失败；分别真实全量采集后才绑定，Ruff、ty、pytest 通过；来源有效岗位数大于零才计入五十家交付。

## 验收记录

2026-10-13 真实范围与数量见 [50家交付验收](../docs/adapter-batch6-acceptance.md)。相关离线合同见 `tests/test_batch6_contracts.py`，原平台测试保留；完整门禁365项通过。正文、截图或空壳探测不算实采验收，绑定仅包含完成的来源。
