# 第三批二十站适配器验收（2026-10-12）

本批从最新版 `origin/main` 创建 `feat/adapter-batch-3`，先恢复先前未进入 main 的八家北森租户，再从仍未绑定的来源中接入下列 **20 家新增企业**。这 20 家都以 Crawl4AI 浏览器会话真实访问公开招聘页，`coverage=complete`；每个来源的原始快照、接口/页面证据、`report.json` 均保存在 `outputs/` 下对应目录，不纳入 Git。没有用人工手填岗位。

| 来源 | 企业 | 适配器 | 目录采集 | 当前入选 | 结果目录（`outputs/` 下） |
| --- | --- | --- | ---: | ---: | --- |
| COM0009 | 京东集团 | jd-campus | 124 | 124 | batch3-jd-validation/COM0009 |
| COM0027 | 腾讯控股 | tencent-campus | 403 | 387 | batch3-tencent-validation-v2/COM0027 |
| COM0040 | 联想集团 | lenovo-campus | 86 | 83 | batch3-lenovo-validation-v2/COM0040 |
| COM0043 | 中粮集团 | coapi-cofco | 590 | 590 | batch3-coapi-validation-v2/COM0043 |
| COM0048 | 交通银行 | bankcomm-campus | 536 | 536 | batch3-bankcomm-validation/COM0048 |
| COM0069 | 中国联通 | zhaopin-unicom | 2,818 | 2,818 | batch3-zhaopin-validation/COM0069 |
| COM0073 | 广汽集团 | gac-2027-static | 143 | 143 | batch3-gac-validation/COM0073 |
| COM0076 | 美团 | meituan-campus | 196 | 196 | batch3-meituan-validation-v2/COM0076 |
| COM0084 | 顺丰控股 | sf-campus | 149 | 149 | batch3-sf-validation/COM0084 |
| COM0136 | 上海建工 | coapi-scg | 3 | 3 | batch3-scg-validation/COM0136 |
| COM0172 | 牧原食品 | moka-muyuan | 473 | 451 | batch3-moka-more-validation/COM0172 |
| COM0198 | 温氏食品 | moka-wens | 90 | 90 | batch3-moka-more-validation/COM0198 |
| COM0202 | 徐工机械 | moka-xcmg | 585 | 569 | batch3-moka-more-validation/COM0202 |
| COM0284 | 正泰电器 | moka-chint | 203 | 177 | batch3-moka-validation/COM0284 |
| COM0373 | 上港集团 | zhaopin-sipg | 43 | 43 | batch3-zhaopin-validation/COM0373 |
| COM0420 | 重庆银行 | zhaopin-cqbank | 46 | 46 | batch3-zhaopin-validation/COM0420 |
| COM0429 | 德赛西威 | feishu-desaysv | 109 | 108 | batch3-feishu-validation/COM0429 |
| COM0446 | 哔哩哔哩 | bilibili-campus | 90 | 90 | batch3-bilibili-validation-v3/COM0446 |
| COM0489 | 宁波华翔 | coapi-nbhx | 31 | 31 | batch3-coapi-validation-v2/COM0489 |
| COM0491 | 龙佰集团 | zhaopin-lbjt | 23 | 23 | batch3-zhaopin-validation/COM0491 |
| **合计** | **20 家** | | **6,741** | **6,657** | |

“目录采集”是逐站已核对的岗位行，包含明确已下架或非校招的行；“当前入选”经过公开状态和校招类型筛选。腾讯有一条目录行在详情接口明确返回“岗位已下架”，另有其他不可投岗位，共排除 16 条；联想、牧原、正泰、德赛西威排除非校招类型。`coverage=complete` 只表示声明的公开目录已完整核对，**不代表全部 6,657 行满足导入模板约束**。缺少后台省市映射、学历、分类或其他必填字段的行会进入待补全报告。

本批的关键范围与终止依据在 SPEC-020 至 SPEC-032 中。四家智联租户均核对 `jobSource=2`、租户、公开列表总数；Moka 租户均核对 `orgId/siteId`、加密响应与逐条详情；中粮、宁波华翔、上海建工分别核对 51job COAPI 的 `ctmid`、单页上限和页面可见规则。腾讯以招聘项目树限定应届/青云应届，美团用已验证的 200 条单页避免动态排序跨页重复，哔哩哔哩通过官网控件翻页，顺丰和交通银行以公开 API 遍历详情。没有把更新时间写作发布时间；原站没有发布日期的岗位该列为空。

`outputs/batch3-20-inputs.json` 是本工作区保存的 20 份独立快照路径清单。以下命令**离线**重新合并，不再访问招聘站点，但默认会调用配置的 DeepSeek 进行分类与必要学历补全：

```sh
uv run job-crawler bundle --inputs-file outputs/batch3-20-inputs.json \
  --output outputs/batch3-20-delivered-full-llm-20261012 --config config.toml
```

产物目录的 `岗位信息汇总.xlsx` 是 13 列采集信息检查表，含“企业采集情况”页；`jobs.xlsx` 是满足严格约束的导入表；`review.json`、`field-audit.json`、`enrichment-report.json` 说明未能导入的行和模型使用。要重新访问 20 站并建立新快照，可对 `job-crawler run --window all` 重复传入上述来源 ID 的 `--source` 参数，写入新的 `--output` 目录。

本轮最终离线合并结果：汇总表 6,657 行，严格导入表 410 行，待补全 6,247 行。默认 1,000 次调用上限的初次尝试在学历补全阶段耗尽；调高本项目配置至 2,000 后，复用已验证的分类/学历缓存重新合并，第二轮仅新增 191 次调用、命中缓存 5,603 次，模型预算不再耗尽。严格导入数量仍受到大量缺失或未核验的后台省市映射等源字段约束；报告为 `partial`，不能将汇总表当作可整体导入表。两个工作簿都已检查为 13 列，截止/发布日期中的非空值均为 `YYYY-MM-DD`。

吉利 COM0039 公开目录曾报告 2,283 条，但完整采集期间目录总数变化；两次运行分别因时间预算与总数变化保持 partial，所以本批**未绑定**。小米接口的签名在修改偏移后失效、部分老活动页空目录或维护、第三方门户跨法人范围不清，均未算入本批 20 家。后续逐站处理前先确认实时范围与可复核终止条件。

代码质量门禁：`uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run ty check` 与 `uv run pytest -q` 均通过；314 个离线测试通过。真实站点验收与离线测试分开记录，以上 20 个 `report.json` 均为 complete。
