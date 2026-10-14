# 快照复用、批次验收与日期交付

以下是从仓库根目录执行的流程模板。日期、来源 ID、标签和文件名换成本批真实值；`batch` 使用一个唯一名称，不重复使用已归档路径。

## 开发阶段：分别保存采集结果与状态

为待验收站点写临时 bindings 文件（格式与 sites/bindings.toml 相同）。源码已注册适配器后，可显式选一个来源运行，不必提前启用正式绑定：

```sh
uv run job-crawler check --source COM0501 --bindings .runtime/batches/batch-bindings.toml
uv run job-crawler run --source COM0501 \
  --bindings .runtime/batches/batch-bindings.toml --window all \
  --output outputs/dev-batch-COM0501 \
  --state .runtime/development-state/batch-COM0501.sqlite
```

显式 `outputs/dev-...` 保留原始目录，适合调试及汇总。SDK 的 `run` 同样可以使用独立输出与状态路径。不要把状态库放在待归档目录内：当前 maintenance 会核对已注册数据库，目录内 SQLite 被打包后会被判为缺失。

`scripts/collect_batch.py` 是历史开发脚本，平台候选列表不是全部 REGISTRY，并将 state.sqlite 放在输出目录内；不要原样套用到新批次的归档工作流。优先使用上面的 CLI/SDK 调用；如需扩展批处理脚本，先按项目规范开发验证。

状态独立不等于跨状态库自动共享增量基线。正式日常任务使用默认 `.runtime/state.sqlite`，首次完整采集建立它自己的基线。模型缓存默认共享 `.runtime/classification` 与 `.runtime/education`；不要给每家新建模型缓存。

命令退出 2 仍可能生成有效表格：读取 `report.json` 的逐来源 coverage、selected、exported、review，以及 `review.json`。目录覆盖失败与字段待补全分开处理。

## 汇总：每来源选择一轮真实快照

保存本批候选、已通过、零岗位、阻塞和替代情况到 `.runtime/batches/`，文档只提交脱敏统计与验收结论。对“新增 N 家”，先与开始时的已接入 `company_id` 集合比对，排除旧企业；同企业多个来源要完整核对范围，但只算一家。

输入 JSON 是路径字符串数组，可以是完整运行目录，也可以是 `collections/<文件>.json`：

```json
[
  "outputs/dev-batch-COM0501",
  "outputs/dev-batch-COM0502"
]
```

混合成功/失败的运行中，只选择已经验证且范围完整的来源 collections 文件；不能借此掩盖同一家企业遗漏的其他来源或单位。每个 source_id 只选一轮；同公司跨入口不自动跨源去重，需证明范围不重叠或在适配器明确处理重叠。

若输入已归档，先 `restore 原运行路径 --output outputs/restored-batch-COM0501`。若只需顶层归档中的一个嵌套结果，恢复顶层后再选择其子目录。恢复不会访问站点或调用模型，不代表历史岗位重新确认在线。

```sh
uv run job-crawler bundle \
  --inputs-file .runtime/batches/batch-inputs.json \
  --output .runtime/runs/batch-final
```

`bundle` 不访问招聘网站，但会按配置调用必要的模型补全并优先命中缓存。完整快照可直接复用，不重采来凑一份总表。不能混合 all/day/week/month；非 all 的筛选时刻也必须一致。all 在汇总时按当前时刻再次筛选，已截止岗位可能减少，因此汇总后再核对最终家数。

## 验收并发布

```sh
uv run python .agents/skills/add-recruitment-adapters/scripts/audit_delivery.py \
  .runtime/runs/batch-final --expected-companies 50 \
  --output .runtime/batches/batch-delivery-audit.json
```

脚本只读快照、报告和两份工作簿；核对来源集合、覆盖、源计数、企业 ID 去重、信息/严格表行数及 13 列日期格式。它不能证明端点选择正确、名录范围全部遍历、跨源岗位没有业务重复，也不能证明输入企业是本批新增；这些依赖本站 spec、原始证据及批次开始时的名录对照。

脚本失败先查原因，不删除失败行来让数字通过。用户要求有岗位企业数量时，零岗位与 coverage 非 complete 都不能凑数。信息表可能同时包含日期待核验行，因此明确区分有效 selected、信息表行数、严格 exported 与 review；总 report.status 为 partial 不代表源 coverage 一定不完整。

通过后发布，普通批次不使用 --pin：

```sh
uv run job-crawler archive .runtime/runs/batch-final --publish --label 新增50家-批次名
uv run job-crawler archive outputs/dev-batch-COM0501
uv run job-crawler archive outputs/dev-batch-COM0502
uv run job-crawler maintenance
```

逐个归档的前提是目录已停止写入、没有需要继续 resume 的任务，且状态库在目录外；只发布最终汇总，调试目录不要 --publish。恢复后的临时目录也可单独归档。不要直接 rm outputs、.runtime 或索引引用的证据。maintenance 默认为预览，确认目标属于本次授权整理范围后按需 --apply；默认 run 会自动维护。

结果位于 `outputs/日期/新增50家-批次名-岗位信息汇总.xlsx` 和 `新增50家-批次名-严格导入.xlsx`。日期来自最终 manifest.as_of（上海时区），各来源真实采集时刻保留在 origins 和汇总来源页；不能用日期文件夹掩盖旧日输入。同日第二批用新标签，不覆盖原表。

快照、报告、待补全、超长原文与证据在 `.runtime/archives/`，原路径映射在 `.runtime/archive-index.json`；需要重新补全时 restore 后 export，再发布。最终表格永久保存；后台保留策略以 SPEC-047/config.toml 为准，--pin 只用于用户需要长期保留的原始快照。

## 验证与交付给用户

按照 AGENTS.md 执行 uv sync --locked、Ruff format/check、ty、pytest；离线测试与真实站点验收分别记录。提交新 spec、适配器/绑定、必要回放与验收说明；运行产物不入 Git。按当前本地 Git 流程合并，无须默认创建 PR。

交付时提供最终两个表格链接及：目标家数、成功有岗位企业数、有效/信息/严格导入/待补全行数、使用的采集日期、剩余受阻或零岗位企业和原因。若只完成适配器未完成真实采集，应直说，不宣称已交付岗位。
