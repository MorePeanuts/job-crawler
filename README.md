# 企业招聘信息采集

当前版本：`v0.0.1-alpha.3`（Python 包版本 `0.0.1a3`）。默认自动完成补全交付流程；变更与限制见 [发布记录](CHANGELOG.md)。

维护企业招聘来源，使用 Crawl4AI 与平台适配器采集校招岗位，筛选仍展示且未截止的岗位，由程序导出符合用户模板的 Excel。支持全部存量、最近一天、最近一周、最近一个月，默认自动进行缓存优先的 LLM 分类及必要学历补全，完成校验后直接输出最终表格。

已导入 **500 家企业、228 个招聘链接**，目前已接入并真实验收 **42 家企业**：原四站、16 家北森平台企业、6 家 Hotjob 平台企业、13 家 Moka 平台企业和 3 家前程无忧定制活动页企业。平台逻辑共享，企业入口和覆盖逐家核验；其余 **186 个有链接来源**待适配，空链接待补充。名单与结果见 [20 家企业验收](docs/initial20-acceptance.md)、[Hotjob 验收](docs/hotjob-acceptance.md)、[Moka 验收](docs/moka-acceptance.md)、[静态活动页验收](docs/static-campaign-acceptance.md) 和 [首轮验收](docs/acceptance.md)。

**已配置用户提供的真实分类树：20 个一级分类、113 条二级路径。** 分类来源是 `job-position.js`，第三级岗位名称用于模型理解，Excel 仍保留原来的一级、二级两列。缺少合法分类、学历或地点格式的记录保留在 `review.json`，不进入严格导入表。可以对已保存岗位进行批量分类和重新导出，无须重复爬取。

## 安装

要求 Python 3.12+、uv 和可用的浏览器。在项目根目录运行：

```sh
uv sync --locked
uv run job-crawler check
```

默认使用本机 Google Chrome。没有 Chrome 时运行 `uv run playwright install chromium`，再将 `config.toml` 的 `crawl.chrome_channel` 改为 `"chromium"`。Linux 可能还需要 Playwright 浏览器系统依赖。默认 LLM 已启用，请在启动环境中配置 `DEEPSEEK_API_KEY`；已有有效缓存或规则已满足字段要求时无需请求模型。显式关闭 LLM 时不需要模型密钥。

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
| `day` | 同上，且源站发布时间在最近 24 小时内；默认也纳入建立基线后最近 24 小时首次发现的无日期岗位，依据单独标记 |
| `week` | 同上，且源站发布时间在最近 7 天内 |
| `month` | 同上，且源站发布时间在最近一个日历月内，月底按上月最后一天截断 |

默认以 Asia/Shanghai 当前时间为基准。发布时间只有日期时，按当天时间区间与窗口相交判断；截止日期有效至当天结束。week/month 缺少发布时间进入待核验；day 的无日期发现规则见下文，不会把首次发现时间写入发布日期。非空但无法解析的日期仍进入待核验。

可用 `--as-of '2026-10-10T12:00:00+08:00'` 固定筛选基准。它只筛选当前可访问目录，不还原历史网页。建行列表已经证明过期的岗位不再读取详情，计入 `skipped_expired` 并保留列表证据。

## 每日减少详情请求

建议升级 alpha.2 后先执行一次全量建立基线，之后每天运行 day，每 15 天再次运行 all。输出目录每轮必须不同；**所有轮次共用同一 `--state` 和保留下来的证据文件**。默认状态库是 `.runtime/state.sqlite`，不应按天删除或换路径。

```sh
# 首次基线，以及之后每 15 天的全量刷新；每次使用新的输出目录
uv run job-crawler run --window all --output outputs/baseline-alpha2

# 每日：更换日期/目录；省略 --output 则自动使用时间戳目录
uv run job-crawler run --window day --output outputs/daily-20261011

# 无需另跑 classify；最终表格直接位于 outputs/daily-20261011/
# 如模型失败或缺 key，修复配置后只重试补全/导出，不重新访问招聘网站
uv run job-crawler export outputs/daily-20261011 --output outputs/daily-20261011-retried
```

上面是手动命令，本版本不自动安排定时。一次 run 已包含分类与必要学历辅助；退出码 2 表示采集不完整或字段仍待补全，先检查 report.json/review.json，修复后可用 export 重试，不代表没有输出产物。

每日始终遍历完整列表，不假设按时间倒序。北森和建行的可靠列表日期早于窗口时跳过详情；列表没有日期时，已见岗位可复用最近成功的详情。中石油按公告 ID 缓存整篇展开岗位；平安/阿里列表已包含正文，仍需完整读取列表，主要获得首次发现追踪而非请求减少。

默认配置：

```toml
[incremental]
enabled = true              # day 的列表预筛选与跨轮详情复用
refresh_days = 15            # 距实际详情读取达到此天数后重新读取
include_undated_new = true   # day 包含基线建立后新发现的无发布日期岗位
```

列表任意字段变化、岗位从上一完整目录消失后重新出现、详情达到刷新期限、证据丢失或缓存损坏时重读；可靠旧日期仍可直接排除。`all` 绕过跨轮详情缓存，`week/month` 保持原抓取方式。`enabled=false` 可关闭每日请求优化，但首次发现追踪仍保留。严格要求源站发布日期时将 `include_undated_new=false`，无日期岗位进入待核验。

无历史的第一次采集只建立基线，既有无日期岗位不会全部算作“今天新发布”；原始详情仍保存在 JSON。完整且成功核对的来源才推进历史；失败源不推进。旧版数据库没有列表指纹，不自动作为 alpha.2 的可信详情缓存；入口/来源或代码身份变化后也会重新建立基线。

`report.json` 的每个 scope 将 `details`（本轮读取）、`reused_details`、`skipped_window`、`skipped_expired` 分开统计，公告 scope 按公告数计。`jobs.json` 标记 `detail_mode`（fresh/cached/listing_only），缓存详情保留旧的 `collected_at` 并附本轮列表证据。来源 `selection_basis` 和 `field-audit.json` 区分发布时间筛选与 `first_discovered_without_publication`，不冒充源站发布日期。

列表未变但详情被改动时，可能等到刷新期限/全量任务才发现；公告内新增岗位而公告列表不变也有此限制。day 是滚动 24 小时，失败后自动补采、跨轮交付去重尚未实现。各平台实际节省比例取决于列表日期及新增量；[验收记录](docs/daily-incremental-acceptance.md)中的请求数量来自离线回放。

## 输出与退出码

每轮生成一份 `jobs.xlsx`，保留模板的 `岗位导入`、`枚举值`、`填写说明` 工作表，删除示例行。导出共 13 列：公司、岗位名称、工作类型、一级分类、二级分类、学历、地点、详细地址、岗位职责、任职要求、申请链接、**截止时间、发布时间**。两列日期均为 `YYYY-MM-DD` 文本，例如 `1970-01-01`；精确时间按北京时间取日期，源站未提供时留空。无法解析的日期也留空，原文与核验原因保存在 JSON。底层精确时间保留，仍用于过期及时间窗口筛选。仅导出通过约束的记录，不猜测分类/日期/行政区，不静默截断超长文本。

| 文件 | 内容 |
| --- | --- |
| `report.json` | 每个来源的覆盖状态、目录与详情数量、过滤原因、待补全数量、障碍和导航恢复警告 |
| `jobs.json` | 本轮获取的所有岗位及原始字段、来源和证据引用，包括被筛选排除的记录 |
| `岗位信息汇总.xlsx` | 本次窗口内的岗位及待补全记录；保持十三列，不保证可直接导入 |
| `delivered.json` | 本次入表及待补全岗位的规范化结果，含分类/学历补全及引证；原始 collections/jobs.json 保持源值 |
| `enrichment-report.json` | 分类、复核、学历辅助的调用量、缓存命中与错误；同时写入 report.json 的 enrichment 字段 |
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

**最新十三列格式**：`outputs/initial20-publication-20261012/岗位信息汇总.xlsx`。从已保存的 20 家快照离线重导出，共 4,611 条岗位，其中 3,986 条有发布时间；末两列为“截止时间”“发布时间”，均按 `YYYY-MM-DD` 输出。离线导出会按当前配置重新处理分类等字段，因此不是旧表仅追加一列的逐单元格副本；源站没有重新采集。模板与导出验收见 [发布时间记录](docs/publication-acceptance.md)。

**42 家扩展采集检查表**：`outputs/initial42-publication-20261012/岗位信息汇总.xlsx`，由各站点在不同时间保存的快照离线汇总，含 7,032 条待补全岗位信息，6,124 条有发布时间，来源页列明 42 家的采集时刻。本次扩展验证关闭了 LLM，严格导入页为 0 行；该表用于核对采集结果，若需可导入表，请按默认配置重新运行，或对保存快照执行 `classify` 并检查待补全报告。详见 [Moka 验收](docs/moka-acceptance.md)与[静态活动页验收](docs/static-campaign-acceptance.md)。

汇总不会重新访问招聘网站；all 快照按汇总时刻再次筛除已截止记录，day/week/month 保留原窗口和筛选时刻。不同窗口或不同窗口基准时刻的快照拒绝混合，不会把每日预筛选的简略行重新当成全量岗位。保留原始采集时间，不宣称重新验证在线状态。同一来源若指定两轮结果会拒绝合并，需自行选择其中一轮。默认与 run 一样为未满足约束的字段进行缓存优先的模型补全；可能访问模型服务，但不访问招聘网站。设 llm.enabled=false 可关闭。

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

分类沿用输入快照的筛选时刻，只处理未排除记录，并保留每个企业原始采集时间。支持 all/day/week/month 快照并保留原窗口。成功项立即写入 `.runtime/classification/`（可用 `--cache` 修改）；中断后换一个空的输出目录并复用 cache 即可继续。内容、模型配置、分类树或提示版本变化会使缓存失效。`--max-calls 0` 可验证缓存并完全离线导出；缺少缓存的记录明确报告，不自动发起请求。语义分类属于模型推断，结构和原文校验不代替业务复核；无法确定主职能的岗位留空并说明原因。

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

默认启用。`run` 自动执行“采集 → 时间筛选 → 规则规范化 → 批量分类/复核 → 必要学历辅助 → 校验导出”，无需第二条 classify 命令。`export` / `bundle` 从保存的快照执行同样的补全流程，可在采集完成后独立重试。

最终文件在指定输出目录根部：`jobs.xlsx` 是满足全部导入约束的严格表；`岗位信息汇总.xlsx` 包含窗口内岗位及待核验记录，字段可能仍有缺失。即使模型返回成功，也不强行补造源站缺失的地址、日期、地点等字段。

默认配置：

```toml
[llm]
enabled = true
model = "deepseek-flash"
base_url = "https://api.deepseek.com"
api_key_env = "DEEPSEEK_API_KEY"
max_calls = 1000            # 分类、复核、学历及重试共用总上限
batch_size = 10            # 分类批次
concurrency = 5            # 分类并发
refine = true
cache_dir = ".runtime/classification"
education_cache_dir = ".runtime/education"
timeout = 60
max_tokens = 1500
```

在启动程序的环境中设置 `DEEPSEEK_API_KEY`。可替换 OpenAI 兼容端点、模型及环境变量名。程序不自动读取 `.env`，密钥不能写入配置或 Git。

`deepseek-flash` 默认关闭思考模式，避免字段抽取的输出预算被思考过程占用；其他模型不附加这一参数。需要供应商扩展参数时，可在 `[llm.extra_body]` 中显式配置并覆盖默认行为。

分类复用已有 `.runtime/classification/` 缓存，成功复核结果优先使用；学历辅助使用独立缓存，规则能确定学历时不调用模型。未变化且已成功处理的文本可以零模型请求重新交付。缓存绑定文本、模型/端点、提示及相关配置；命中仍校验路径和引证。保留这些目录即可跨轮复用，密钥不写入缓存。

缺 key、模型失败或预算不足时仍保存采集快照并导出部分结果，返回退出码 2，原因在 `review.json` 和 `enrichment-report.json`。修复后使用 `export` 和新的输出目录补齐，不必重爬。需要明确禁止模型时设置 `enabled=false`；此时缺分类/学历的记录进入待补全，不能把“输出了 Excel”当成“全部岗位可导入”。`max_calls=0` 则允许读取已验证缓存，但禁止新模型请求。

独立 `classify` 保留为手动重新分类工具；它显式调用分类，不受 enabled 开关控制，其 CLI 预算独立，也不会补学历。日常默认 run 无需使用它。

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
