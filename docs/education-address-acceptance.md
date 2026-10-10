# 学历与详细地址验收

日期：2026-10-10。需求见 [SPEC-007](../specs/007-education-address.md)。分支 `fix/education-address-extraction`。

## 输入、结果及边界

从 `outputs/initial20-deadline-date-20261010` 离线重导出到 `outputs/initial20-fields-20261010`，沿用输入 manifest 的 `as_of`，未访问网站、未调用模型。所有原始岗位、分类、截止日期和原始采集时间保留。程序生成 `岗位信息汇总.xlsx`，继续包含 20 个来源的覆盖信息和 4,611 条岗位；建行 3,784 条过期记录仍被排除，保留在原始 JSON 中。

| 核验项 | 结果 |
| --- | --- |
| 原始非空学历 | 2,452 |
| 从正文新增学历 | 1,735 |
| 原有学历同义词或多值规范化 | 1,421 |
| 最终合法学历 | 4,187 |
| 仍为空的学历 | 424：保存的正文未包含学历 375、提及但未明确解析 26、条件或冲突 23 |
| 明确的岗位详细地址 | 0 |
| 证据匹配 | 4,611 条均匹配到同一岗位 ID 的原始对象 |
| 严格导入表 | 30 条；另 4,581 条因地点格式、缺少学历或分类等仍待补全 |

用户确认将并列的可报名学历取最低档。正文“硕士及以上，本科为某专业”仍为硕士；“本科年龄限制”“博士优先”不据此填学历；放宽条件和冲突要求保留核验状态。“研究生学历”在最低档规则下为硕士。中文与英文明确学历要求都有规则，未覆盖的语句保留原文，不通过填值掩盖缺口。

详细地址审计区分了岗位与企业对象：16 家智联招聘平台详情接口共 1,744 条的 `DetailAddress` 均为空；平安 1,208 条、阿里 469 条的已保存列表对象没有地址键，中石油 1,190 条岗位对象提供地区信息，未提供岗位详细地址。中石油单位介绍里的 `unitAddress` 是单位地址，不能证明是该岗位工作地址，因此未抄入。正文中亦未发现可明确提取的岗位详细地址。**本轮未抓取平安和阿里独立详情页，不能据列表响应断言源网站没有详细地址。**

## 可复现核验

使用 `job_crawler.bundle.bundle` SDK，传入原目录、空输出目录、`load_settings(Path("config.toml"))`，并显式传入 `as_of=datetime.fromisoformat(原manifest["as_of"])`。保持 `settings.llm.enabled=False`。SDK 原始记录和证据不改写。

```sh
uv run python scripts/audit_saved_fields.py outputs/initial20-fields-20261010
uv run python scripts/verify_fields.py \
  outputs/initial20-deadline-date-20261010 outputs/initial20-fields-20261010
```

`field-audit.json` 给出逐条原值、结果、原因及原文；`saved-evidence-field-audit.json` 保留同 ID 原始对象中的学历/地点/地址字段；`field-verification.json` 记录对比结果。

逐单元格比较确认只改变学历列 3,156 格，以及企业覆盖表中 7 个来源的待补全数量。正文按 Excel 字符转义语义比较；源文件的 x14 扩展分类验证与新文件的标准数据验证等价，四组下拉范围/枚举保持不变。8,395 条原始 JSON 记录完全一致；3,156 个修改均有原文引证。截止列、分类列与其他岗位列未改变。

## 需求到测试

| 行为 | 验证 |
| --- | --- |
| 单值/多值/最低档/优先项/条件/背景/英文学历 | `tests/test_field_extraction.py` |
| 城市、总部、联系地址不误当岗位地址 | `tests/test_field_extraction.py` |
| 规范化不修改原始记录，输出字段审计 | `tests/test_runner.py` |
| 证据按岗位 ID 关联、漏匹配明确报告 | `tests/test_evidence_audit.py` |
| LLM 提示遵循学历策略 | `tests/test_llm.py` |
| 模板导出、日期与历史数据回归 | `tests/test_exporter.py` 及上述两条验收脚本 |

本轮真实证据回放不代表重新确认网站仍在线或岗位当前可申请。运行产物不入 Git。

质量门禁：`uv sync --locked`、`ruff format --check .`、`ruff check .`、`ty check` 全部通过；`pytest` 为 **185 passed**。新表学历/详细地址区域已渲染检查，表头、列宽、学历值及空地址显示正常。
