# 北森租户批量接入验收

2026-10-12 13:48–13:52（Asia/Shanghai），按 [SPEC-018](../specs/018-zhiye-batch-expansion.md) 对名录中尚未绑定的北森租户探测，再以 Crawl4AI 逐家采集公开校园招聘 Category=2 全目录和详情。只有目录 `expected = listed = unique = details` 且分页终止的来源绑定为 ready。本次新增八家、787 条；下列计数是当次采集快照，不保证以后仍在线。

| 来源 | 企业 | 目录/详情 | 覆盖 |
| --- | --- | ---: | --- |
| COM0226 | 中国蒙牛乳业有限公司 | 91/91 | complete |
| COM0247 | 金风科技股份有限公司 | 72/72 | complete |
| COM0272 | 浙江零跑科技股份有限公司 | 305/305 | complete |
| COM0388 | 明阳智慧能源集团股份公司 | 132/132 | complete |
| COM0393 | 泡泡玛特国际集团有限公司 | 24/24 | complete |
| COM0452 | 深圳市燃气集团股份有限公司 | 50/50 | complete |
| COM0461 | 豪威集成电路(集团)股份有限公司 | 82/82 | complete |
| COM0484 | 浙江巨化股份有限公司 | 31/31 | complete |

逐家 `manifest.json`、`report.json`、`collections/`、`evidence/` 和 Excel 保存在 `outputs/zhiye-bulk-validation-20261012/COMxxxx/`。采集使用 `scripts/collect_batch.py` 与临时验收配置，LLM 关闭；`--config` 参数让批量工具沿用正式项目配置并单独调整验收运行时间。蒙牛浏览器页面出现一次空壳提示，同轮业务接口成功返回有效 JSON，恢复证据保存在其采集报告；最终目录及详情均为 91，无缺口。

程序用 `job-crawler bundle` 从八份采集快照导出 `outputs/zhiye-bulk-combined-20261012/岗位信息汇总.xlsx`，共 787 行、13 列。此表包含待补全行，不是可直接导入的严格表；各源采集时间见汇总目录 `manifest.json`。随后用默认 `deepseek-flash` 从快照离线分类，结果在 `outputs/zhiye-bulk-classified-20261012/result/`：787 条中 776 条完成分类、11 条待判，模型调用 106 次；严格 `jobs.xlsx` 有 3 条，`review.json` 有 784 条。待补全中 784 条缺少已核验的后台地点映射，216 条学历值无效或不确定，11 条分类未能确定。原始采集与分类结果均保留，可完善映射后从快照重新导出，无需重复访问网站。

另两家完成了技术层面的全目录探测，但**不绑定**：COM0468 招商局能源运输的链接实际是招商局集团统一门户，303 条中含招商局检测车辆研究院、港口等其他法人岗位；COM0471 申能股份链接是申能集团统一门户，149 条中既有发电也有燃气、贸易等单位岗位。当前适配器无法可靠将全集团岗位只归入名录法人。原始探测快照分别保存在同一验收目录的 COM0468、COM0471 子目录，待确认法人映射与过滤边界后才能作为适配器接入。其他已探测但只有零目录、404、维护页、旧协议或无接口证据的北森来源也继续 pending，不将空结果视为完整覆盖。

复现命令：

```sh
uv run python scripts/collect_batch.py COM0226 COM0247 COM0272 COM0388 COM0393 COM0452 COM0461 COM0484 --output outputs/zhiye-bulk-validation-YYYYMMDD --config config.toml
uv run job-crawler bundle outputs/zhiye-bulk-validation-YYYYMMDD/COM0226 outputs/zhiye-bulk-validation-YYYYMMDD/COM0247 outputs/zhiye-bulk-validation-YYYYMMDD/COM0272 outputs/zhiye-bulk-validation-YYYYMMDD/COM0388 outputs/zhiye-bulk-validation-YYYYMMDD/COM0393 outputs/zhiye-bulk-validation-YYYYMMDD/COM0452 outputs/zhiye-bulk-validation-YYYYMMDD/COM0461 outputs/zhiye-bulk-validation-YYYYMMDD/COM0484 --output outputs/zhiye-bulk-combined-YYYYMMDD
uv run job-crawler classify outputs/zhiye-bulk-combined-YYYYMMDD --output outputs/zhiye-bulk-classified-YYYYMMDD
```

质量门禁：`uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run ty check` 均通过；`uv run pytest -q` 为 301 passed。程序复核确认来源清单有 228 条链接，其中 53 条 ready、175 条 pending；本批检查表有 787 条数据行、13 列，严格导入表有 3 条数据行、13 列。
