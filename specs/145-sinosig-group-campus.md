# SPEC-145 阳光保险集团北森校招目录

## 目标

接入名录 COM0209 阳光保险集团股份有限公司的公开集团校招门户 `https://sinosigcampus.zhiye.com/campus/jobs`。2026-10-15 的无筛选 Category=2 目录 243 条，包括集团、寿险、数科等 2027 届岗位；列表含职责、资格和发布时间。完整遍历并导出仍展示且未截止的正式校招岗位。

## 非目标

不采社招、实习岗位，不使用同租户但当前显示 0 条的 `sunzhaopin.sinosig.com` 入口，不将岗位标题中的部门简称推定为法律主体。

## 输入、输出与失败行为

输入为公开 `GetJobAdPageList` Category=2 无关键词、地点、分类筛选目录。按 PageIndex 完成全部岗位枚举；核对稳定总数、唯一 ID、完整正文、CategoryId、岗位性质和末页。输出快照、信息表、严格导入表、待补全与证据。日期哨兵和未知单位保留空值；单条内容异常隔离，目录契约变化时报覆盖问题，不能作为完整验收。

## 可验证验收

1. 离线回放租户绑定、Category=2、岗位性质与正文，并复用北森公共分页测试。
2. 实站 `expected=listed=unique=details`、末页闭合、`coverage=complete`，正式岗位大于零。
3. Ruff、ty、pytest 通过，记录岗位数量和导入字段限制。

对应测试：`tests/test_zhiye.py` 阳光保险租户测试。
