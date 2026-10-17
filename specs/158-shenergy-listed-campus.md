# SPEC-158 申能股份校园招聘单位树

状态：已实现并通过实时覆盖验收，详见 docs/remaining-271-acceptance.md；SPEC-156 A 组 COM0471。

## 目标与非目标

从申能集团共享官方招聘门户采集“申能股份有限公司”及门户明确归属该节点的下属单位校招。不得将上海燃气、保险等其他集团板块归入名录上市主体。

## 输入输出与已观察契约

入口 `https://shenergy.zhiye.com/custom/campus` 无筛选全目录 Category=2，本轮列表总数 149，PageIndex 从 0 起，初始 PageSize=10。复用 Zhiye 分页并逐条检查单位归属。

页面“申能股份有限公司”链接参数为 ClassificationTwo=6、unit_val=6；API `/api/OpenCustomization/GetJobAdCustomTypeList` 的 TypeCode=1 返回招聘单位树，在 Value=6、Text=申能股份有限公司节点下列出所属电力企业。不能将 URL 参数名推定为列表字段语义：岗位 ClassificationOne 是单位名称，ClassificationTwo 是岗位类别。

运行时从实际观察的端点重新请求 TypeCode=1 并验证名称/值/层级；树中所有单位名称必须唯一。纳入目标节点及所有后代；其他已知节点岗位计入 skipped_out_of_scope；树外单位或岗位 Org/ClassificationOne 不一致时报错，不静默排除。

列表 Data 包含 Duty、Require、Degree、PostDate、EndTime、DetailAddress、CategoryId 和 GUID，直接使用全文，无重复详情请求。岗位源链接为 `/custom/campusxq?jobAdId=<GUID>`。发布时间只取 PostDate，单位类别从 ClassificationTwo，日期哨兵按共享契约留空。公共 delivery 完成分类与导出。

## 失败与验收

缺树、重名、目标节点不唯一/值改变、范围无法关联、重复页、总数变化或缺正文均不得完成；保留已得岗位。回放覆盖递归下属单位、其他板块排除、树外单位、身份不一致和多页目录。真实临时绑定验证完整 149 全集团目录的处理守恒及申能股份子集，成功后才能正式启用。真实计数以报告为准。质量门禁遵循 AGENTS.md。
