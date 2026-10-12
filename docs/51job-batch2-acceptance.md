# 第二批前程无忧定制活动页验收

2026-10-12 13:21–13:22（Asia/Shanghai）按 [SPEC-017](../specs/017-51job-campaign-batch-2.md) 实际运行 Crawl4AI 全量采集。三来源均通过目录、申请 ID、岗位正文和终止核对；数据是当次公开页面快照，不代表今后页面保持不变。

| 来源 | 范围与终止依据 | 当前目录 | 获得岗位 | 覆盖 |
| --- | --- | ---: | ---: | --- |
| COM0245 蓝思科技 | `window.obj` 全数组；四个地区选项与数组地区一致，首屏卡片 ID 在数组中 | 26 | 26 | complete |
| COM0259 中国燃气 | 唯一「校园招聘」链接后的 `jobListData` 全数组与 308 个 DOM 卡片、申请 ID 逐项一致 | 308 | 308 | complete |
| COM0406 天津银行 | 热招 21 个申请 ID（两个直接岗位、一个 19 城市岗位），专项招聘 7 个城市 ID；两个分支分别验收 | 28 | 28 | complete |

运行命令对应 `uv run job-crawler run --source COM0245 --source COM0259 --source COM0406 --bindings /tmp/job-crawler-batch2-bindings.toml --config /tmp/job-crawler-long-wait.toml --output outputs/batch2-validated-20261012 --state outputs/batch2-validated-20261012/state.sqlite`。临时绑定与配置仅用于接入验收，其中 LLM 关闭；正式绑定已进入 `sites/bindings.toml`，默认 `config.toml` 仍启用 `deepseek-flash`。原始岗位、逐来源集合、报告、网页证据和十三列检查表保存在上述输出目录。

该检查表 `岗位信息汇总.xlsx` 有 362 行，三个来源各自的覆盖状态均为 complete。复核发现蓝思第四个「智能机器人公司」选项是单位而非地点，其八条岗位正文均明确写有长沙浏阳园区；修正后另行运行 `outputs/batch2-lens-recheck-20261012/`，26 条覆盖仍完整。程序使用 `job-crawler bundle` 将修正后的蓝思快照和已验收的另两站快照离线合并，最终检查表在 `outputs/batch2-final-20261012/岗位信息汇总.xlsx`，362 行。原始校验阶段关闭 LLM；其后用默认 `deepseek-flash` 离线补全，再次合并时命中已有缓存，零新增模型调用。

最终严格 `jobs.xlsx` 仍为 0 行。`review.json` 保留 362 行，其中全部缺少已核验的后台省/市地点映射，另 32 行缺少确定学历；分类已完成且无模型错误。目录覆盖与可导入性分开报告，不以字段待补全否定已完成的岗位遍历，也不把检查表称为可直接导入。地点映射须按实际后台路径配置后从快照重新导出，无须重复采集。

蓝思页面公开完整职责、要求及部分详细地址；中国燃气的页面脚本含完整岗位正文；天津银行所有城市选项有不同申请 ID。三站没有可核实的岗位发布日期或截止日，均留空。中国燃气名录入口备注为 2025 届历史专题；当前页面仍公开展示这些岗位，但站点未提供逐岗位在招/关闭状态或截止时间，不能由页面仍可打开推定仍可投递。投递入口可能要求登录，适配器只保存链接，不发起申请。

本次还探测了李宁 COM0453（25 个标题和申请链接，但页面无岗位职责/要求）、万向 COM0133（当前只有空壳）、海大 COM0183（页面不存在）、首开 COM0448（空壳/反爬阻断）、圆通 COM0240（岗位页只有活动导航）。这些来源继续 pending，不因有链接或标题就标记 ready。

质量门禁：`uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run ty check`、`uv run pytest -q` 均通过（291 个测试）。最终检查表经程序复核为十三列、362 条岗位，企业计数分别为 26、308、28。
