# 企业招聘信息采集

维护企业招聘来源，使用 Crawl4AI 与平台适配器采集校招岗位，筛选仍展示且未截止的岗位，由程序导出符合用户模板的 Excel。支持全部存量、最近一天、最近一周、最近一个月，以及可选的 LLM 字段辅助。

已导入 **500 家企业、228 个招聘链接**，初版已接入并真实验收 **20 家企业**：原四站加 16 家北森平台企业。平台逻辑共享，企业入口和覆盖逐家核验；其他链接待适配，空链接待补充。名单与结果见 [20 家企业验收](docs/initial20-acceptance.md)，历史四站记录见 [首轮验收](docs/acceptance.md)。

**已配置用户提供的真实分类树：20 个一级分类、113 条二级路径。** 分类来源是 `job-position.js`，第三级岗位名称用于模型理解，Excel 仍保留原来的一级、二级两列。缺少合法分类、学历或地点格式的记录保留在 `review.json`，不进入严格导入表。可以对已保存岗位进行批量分类和重新导出，无须重复爬取。

## 安装

要求 Python 3.12+、uv 和可用的浏览器。在项目根目录运行：

```sh
uv sync --locked
uv run job-crawler check
```

默认使用本机 Google Chrome。没有 Chrome 时运行 `uv run playwright install chromium`，再将 `config.toml` 的 `crawl.chrome_channel` 改为 `"chromium"`。Linux 可能还需要 Playwright 浏览器系统依赖。未启用 LLM 时无需模型密钥。

## 维护来源

```sh
uv run job-crawler sources list --status supported
uv run job-crawler sources list --status pending
uv run job-crawler sources list --status missing

# 导入其他名录；默认拒绝覆盖，确认替换时显式添加 --replace
uv run job-crawler sources import /path/企业名录.csv --file sites/new-sources.csv

# 同一企业多个入口使用不同来源 ID，企业 ID 可以相同
uv run job-crawler sources add --id COM0002-campus-new \
  --company-id COM0002 --company '中国石油天然气集团有限公司' \
  --url 'https://example.com/campus'
```

也可以直接编辑 `sites/sources.csv`，列为 `来源ID,企业ID,主体名称,招聘官网,备注`。主体名称用于导出的“公司”列，应与后台名称完全一致；可在 `sites/bindings.toml` 的对应来源下设置 `company_name` 覆盖导出名。

`supported` 表示已绑定启用的适配器，`pending` 为待适配，`missing` 为缺少入口，`disabled` 为禁用。新增链接不会自动生成适配器，后续将 URL 和 [适配器开发规范](docs/adapter-development.md) 交给 Codex 按契约扩展。

## 采集

```sh
# 默认运行全部已启用适配器，采集当前未截止的校招岗位
uv run job-crawler run --output outputs/current

# 选择单个/多个来源
uv run job-crawler run --source COM0012 --window day --output outputs/pingan-day
uv run job-crawler run --source COM0002 --source COM0008 --window week
uv run job-crawler run --window month

# 显式纳入全部名录：未接入/没有链接的来源逐一报告为阻塞
uv run job-crawler run --all-sources
```

省略 `--output` 会在 `outputs/` 创建带时间戳的目录，程序拒绝覆盖非空目录。初始来源 ID：中石油 `COM0002`、建行 `COM0008`、平安 `COM0012`、阿里 `COM0015`。

| 模式 | 规则 |
| --- | --- |
| `all`（默认） | 当前目录仍展示、未明确关闭、截止日期尚未过去；没有截止日期时保留 |
| `day` | 同上，且源站发布时间在最近 1 天内 |
| `week` | 同上，且源站发布时间在最近 7 天内 |
| `month` | 同上，且源站发布时间在最近一个日历月内，月底按上月最后一天截断 |

默认以 Asia/Shanghai 当前时间为基准。发布时间只有日期时，按当天时间区间与窗口相交判断；截止日期有效至当天结束。窗口模式缺少发布时间时进入待核验，不用更新时间或首次发现时间代替。非空但无法解析的日期也进入待核验。

可用 `--as-of '2026-10-10T12:00:00+08:00'` 固定筛选基准。它只筛选当前可访问目录，不还原历史网页。建行列表已经证明过期的岗位不再读取详情，计入 `skipped_expired` 并保留列表证据。

## 输出与退出码

每轮生成一份 `jobs.xlsx`，保留模板的 `岗位导入`、`枚举值`、`填写说明` 工作表，删除示例行。导出共 12 列：公司、岗位名称、工作类型、一级分类、二级分类、学历、地点、详细地址、岗位职责、任职要求、申请链接、**截止时间**。最后一列为 `YYYY-MM-DD` 格式文本，例如 `1970-01-01`；精确时间按北京时间取日期，无截止时间时留空。无法解析的日期也留空，原文与核验原因保存在 JSON。底层精确时间保留，仍用于过期筛选。仅导出通过约束的记录，不猜测分类/日期/行政区，不静默截断超长文本。

| 文件 | 内容 |
| --- | --- |
| `report.json` | 每个来源的覆盖状态、目录与详情数量、过滤原因、待补全数量、障碍和导航恢复警告 |
| `jobs.json` | 本轮获取的所有岗位及原始字段、来源和证据引用，包括被筛选排除的记录 |
| `review.json` | 日期不确定、分类/学历/地点不合格、LLM 失败等记录及原因 |
| `field-audit.json` | 入表/待补全岗位的学历、详细地址原值、规范值、处理状态和原文引证 |
| `manifest.json` | 运行 ID、代码指纹、配置、来源和筛选时刻 |
| `collections/` | 各来源独立结果，用于重新导出 |
| `evidence/` | 页面、接口与错误证据；异常站点可能仅有错误证据 |
| `llm/` | 模型决策、引证和用量，不保存密钥 |

覆盖状态 `complete` 表示声明的目录已核对，不代表所有行均可导入。任务状态还考虑待补全记录：有数据但未全部解决为 `partial`，没有数据且受阻为 `blocked`。已验证的零岗位目录可以为 `complete`。

退出码：`0` 全部完成；`2` 部分结果或阻塞；`1` 输入/配置错误；`130` 用户中断。调用方应同时查看报告，不能只按 Excel 行数判断成功。运行产物和 SQLite 不提交 Git。

## 合并开发期间已经采集的结果

不必为了得到一份总表再次采集。`bundle` 接受一个或多个采集目录，也接受目录内单独的 `collections/*.json` 文件，用于从多来源任务中只选择已完成的企业：

```sh
uv run job-crawler bundle outputs/company-a outputs/company-b --output outputs/combined

# 路径多时，使用 JSON 字符串数组。相对路径以当前工作目录为准。
uv run job-crawler bundle --inputs-file outputs/initial20-inputs.json \
  --output outputs/initial20-reexport
```

这次交付已保存在 `outputs/initial20-20261010-final/岗位信息汇总.xlsx`，共 **4,611 条岗位**。“企业采集情况”页列出 20 家企业的原始采集时刻、覆盖情况和排除数量。建行 3,784 条均已截止，所以当前岗位表有 19 家企业的实际岗位，企业覆盖报告仍为 20 家。其余 16 家新增企业的独立原始结果保存在 `outputs/twenty-company-validation/<来源ID>/`。

**分类更新版**：`outputs/initial20-taxonomy-20261010/result/岗位信息汇总.xlsx`。原 4,611 条记录中，4,599 条已补充合法分类；其余 12 条涉及未能确定主职能的混合岗位、宽泛职位或校招行程公告，保留为空并列于 `outputs/initial20-taxonomy-20261010/classification-unresolved.json`。原始表保留不覆盖，分类验收与分企业统计见 [分类验收](docs/taxonomy-acceptance.md)。

**最新统一日期版**：`outputs/initial20-deadline-date-20261010/岗位信息汇总.xlsx`。保持上述 4,611 条记录和前十一列不变，最后一列“截止时间”统一为 `YYYY-MM-DD`：1,220 条有值，3,391 条留空。项目模板 `src/job_crawler/assets/job-template.xlsx` 同步更新说明；后续采集、分类与汇总自动使用这一格式。本次离线重导出保留原筛选时刻与企业采集时间，没有重爬或调用模型。

汇总不会重新访问招聘网站；按汇总时刻再次筛除已截止记录，保留原始采集时间，不宣称重新验证在线状态。同一来源若指定两轮结果会拒绝合并，需自行选择其中一轮。启用 LLM 时仍可能为缺失字段调用模型；默认关闭。

`岗位信息汇总.xlsx` 包含待补全记录，使用更新模板的十二字段，缺失值留空，正文不截断。`jobs.xlsx` 则始终是严格校验的导入表。分类补全后，学历或地点不合要求的记录仍进入 `review.json`，不能把分类成功等同于全部可直接导入。JSON 同时保留全部原始岗位（包括已排除的岗位）及证据。

## 分类与字段映射

默认 `config.toml` 已包含实际父子路径；完整三级参考保存在 `src/job_crawler/assets/job-taxonomy.json`，记录源文件 SHA256。收到新版脚本时运行下面的安全导入程序（只解析数据，不执行 JS），同步资源与配置并校验模板枚举：

```sh
uv run python scripts/import_taxonomy.py /path/job-position.js
```

批量分类已保存的完整或汇总快照：

```sh
uv run job-crawler classify outputs/initial20-20261010-final \
  --output outputs/initial20-classified \
  --max-calls 700 --concurrency 8 --batch-size 10 --refine
```

此命令明确启用模型分类，不要求设置 `llm.enabled=true`；使用 `[llm]` 中的模型、端点和密钥环境变量配置，默认 `deepseek-flash` / `DEEPSEEK_API_KEY`。`--max-calls` 是本次调用硬上限（含重试），独立于采集时的 `llm.max_calls`；默认每批 10 条、并发 5、最多 1000 次，单批最多重试 2 次。只发送公司名、岗位名称、来源类别、职责和要求；不访问招聘站点，也不改动学历、地点等其他字段。

结果位于输出目录：

- `result/岗位信息汇总.xlsx`：补充分类的完整信息表；`result/jobs.xlsx`：通过全部导入约束的子集。
- `classification-report.json`：已分类/未分类统计、每条模型判断、原文引证、失败原因与缓存标识。
- `classification-unresolved.json`：仅列出仍无法判断的岗位、来源链接和原因，方便业务复核。
- `classification-audit/`：本轮模型响应和用量。
- `classified-snapshot/` 与 `result/collections/`：持久化分类后的来源快照，可直接用于后续 `bundle` / `export`。

分类沿用输入快照的筛选时刻，只处理未排除记录，并保留每个企业原始采集时间。当前支持 `window=all` 快照。成功项立即写入 `.runtime/classification/`（可用 `--cache` 修改）；中断后换一个空的输出目录并复用 cache 即可继续。内容、模型配置、分类树或提示版本变化会使缓存失效。`--max-calls 0` 可验证缓存并完全离线导出；缺少缓存的记录明确报告，不自动发起请求。语义分类属于模型推断，结构和原文校验不代替业务复核；无法确定主职能的岗位留空并说明原因。

`--refine` 在同一调用总预算内，使用紧凑的完整父子路径复核未分类项及与精确三级名称不一致的项，降低模型漏读长分类树的影响。复核有独立缓存与 `classification-refinement/` 审计；不会强制把混合岗位放进兜底类别。

例如后续不调用模型重新汇总已经分类的快照：

```sh
# 默认 config.toml 的 llm.enabled=false
uv run job-crawler bundle outputs/initial20-classified/result \
  --output outputs/initial20-classified-reexport
```

其他字段映射仍在 `config.toml` 中维护。以下仅展示语法；不要用这个示例覆盖已有完整分类树，源站类别映射只填写已经确认的精确对应关系：

```toml
[mapping.category_paths]
"互联网/AI" = ["软件研发", "前端开发"]

[mapping.categories]
"源站研发类别" = ["互联网/AI", "软件研发"]

[mapping.education]
"本科及以上" = "本科"

[mapping.locations]
"深圳" = "广东省/深圳市"
```

分类名称必须来自模板枚举，父子关系由后台配置确认。学历默认按用户确认的**最低可报名学历**填写，例如明确接受本科/硕士/博士时填本科，“硕士研究生”规范为硕士。该规则在采集、重导出、汇总中统一生效，不需要调用模型。`[mapping]` 下的 `education_policy = "minimum_eligible"` 可改为 `"explicit_only"`，恢复不缩减并列学历的保守模式；`[mapping.education]` 中的显式映射优先。

空学历会从任职要求中的明确要求补全，保留原文；仅有优先项、放宽条件、年龄说明或冲突要求时留空并报告。详细地址仅从岗位自身明确的工作/办公地址提取，不拿企业联系地址或总部地址代替；只有城市的地点不会自动补成详细地址。原始 `jobs.json` 不改写，处理结果见表格、`review.json` 与 `field-audit.json`。

地点可为省/市/区、省/市或直辖市/区，多城市不自动缩减，不能补造未知行政区。申请链接缺失时默认使用岗位详情页作为入口，可用 `use_source_url_as_apply_url = false` 关闭。

修改映射后，从历史结果重新导出：

```sh
uv run job-crawler export outputs/current --output outputs/current-remapped
```

重新导出保留原采集范围、原筛选时刻和覆盖状态，报告标记来源运行；不代表重新确认岗位仍在招聘。

对本地留存证据进一步核对岗位 ID 及学历/地址字段（无网络请求），可运行：

```sh
uv run python scripts/audit_saved_fields.py outputs/current-remapped
```

输出 `saved-evidence-field-audit.json`，未匹配或缺失证据会明确报告。此检查只覆盖已经抓取的字段，不能证明未访问的详情页没有地址。20 家历史快照的本轮学历/地址核验结果见 [字段验收记录](docs/education-address-acceptance.md)。

## LLM

默认关闭，纯规则采集不需要密钥。需要学历/分类辅助时修改配置：

```toml
[llm]
enabled = true
model = "deepseek-flash"
base_url = "https://api.deepseek.com"
api_key_env = "DEEPSEEK_API_KEY"
max_calls = 20
timeout = 60
max_tokens = 1500
```

在启动程序的环境中设置 `DEEPSEEK_API_KEY`。可替换 OpenAI 兼容端点、模型及环境变量名。程序不自动读取 `.env`，密钥不能写入配置或 Git。

`deepseek-flash` 默认关闭思考模式，避免字段抽取的输出预算被思考过程占用；其他模型不附加这一参数。需要供应商扩展参数时，可在 `[llm.extra_body]` 中显式配置并覆盖默认行为。

模型只对已采集字段提供有原文引证的学历/分类建议，不决定导航、分页或完成状态。没有分类树时不会让模型自行建立业务分类。预算耗尽、失败、截断或没有引证时进入待补全；结构验证通过也不等于语义分类一定正确，需根据业务样本评估。

## 恢复与预算

```sh
# 来源、窗口、配置、代码和输出目录与原任务一致
uv run job-crawler run --source COM0012 --window day \
  --output outputs/pingan-day --resume
```

SQLite 默认在 `.runtime/state.sqlite`，可用 `--state` 指定。恢复始终重新读取列表，只复用同一运行、同参数的成功详情；当前列表不再引用的旧详情不会参与结果。代码、配置或参数变化，或检查点超过 `crawl.resume_hours`（默认 6 小时）时拒绝恢复，应新建运行。

`crawl` 配置支持页面导航超时 `navigation_timeout`（默认 180 秒）、接口/页面脚本超时 `timeout`（默认 60 秒）、单来源时长 `max_seconds`、显式请求预算 `max_requests`、请求间隔 `delay`、重试数 `retries`。例如页面主脚本下载缓慢时可调大 `[crawl]` 中的 `navigation_timeout`，不必放宽接口超时。静态资源请求不计入显式请求预算。各来源顺序执行，错误彼此隔离；认证/403 停止受影响范围。已完成来源单独落盘，请求有检查点。中断可恢复，不会将未完成来源当作最终成功。

中石油入口可能返回 HTTP 412，但浏览器随后正常加载业务页。只有同轮已观察到适配器声明的成功 JSON 接口，程序才继续采集并将依据写入 `*-recovered.json` 和报告的 `warnings`；无业务数据的 412、真正的 403 仍失败。导航恢复不代替分页、详情和计数核验。

## Python SDK

```python
import asyncio
from pathlib import Path
from job_crawler.config import load_bindings, load_settings
from job_crawler.runner import run
from job_crawler.sources import read_sources

sources, _ = read_sources(Path("sites/sources.csv"))
report = asyncio.run(
    run(
        [s for s in sources if s.source_id == "COM0012"],
        load_bindings(Path("sites/bindings.toml")),
        load_settings(Path("config.toml")),
        output=Path("outputs/sdk-run"),
        window="week",
    )
)
print(report["status"], report["exported"])
```

## 开发

先读 [AGENTS.md](AGENTS.md) 和 [正式版 spec](specs/001-production.md)。从 main 创建功能分支，先写 spec，再实现、测试、更新验收记录，按阶段提交。有远程时通过 PR 评审，没有远程时保留本地分支，不直接合并未验证变更。

```sh
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build
```

默认测试使用合成及脱敏回放数据，不访问真实站点或真实模型。真实验收用 `job-crawler run` 单独执行。历史实验保留在 `validation/crawl4ai-campus`，不参与正式运行。[历史架构决策](docs/recruitment-crawler-plan.md) 与本轮需求冲突时以 spec 为准。
