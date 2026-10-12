# SPEC-022 联想校招目录

状态：代码与真实全量覆盖已验收。2026-10-12；导出见 `docs/adapter-batch3-acceptance.md`。

目标是接入 COM0040 `talent.lenovo.com.cn/position` 的公开岗位目录，并只交付其中 `projectType=1` 的应届生招聘。Crawl4AI 已观察到无筛选 `gateway/jobBase/list?pageNum=1`，首轮总数 86、每页 10 条；翻页时确认目录还混有实习及人才项目，因此必须完整读取 86 条，再按源项目类型由公共筛选排除非校招。列表含 `jobDuties` 和 `jobRequirement` 全文及唯一 `id`；详情页可用 `id` 关联。`gateway/sysDict/all` 明确给出 `city_portal` 和 `education` 枚举，用于把岗位的数字代码映射成原站名称，不猜测。

输出为完整 `Job` 快照、范围计数及公共十三列表格。页面无岗位发布时间和截止日，均留空。分页总数变化、重复 ID、未知项目类型或字典代码、正文缺失、详情 URL 无法构成时为 partial，已获得记录与证据仍保存。验收要求首/次/末页和失败回放、真实全量 `expected=listed=unique=details` 且终止、导出字段检查；不访问投递接口。
