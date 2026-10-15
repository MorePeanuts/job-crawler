# 企业招聘信息采集

当前版本：`v0.0.1-alpha.3`（Python 包版本 `0.0.1a3`）。默认自动完成补全交付流程；变更与限制见 [发布记录](CHANGELOG.md)。

维护企业招聘来源，使用 Crawl4AI 与平台适配器采集校招岗位，筛选仍展示且未截止的岗位，由程序导出符合用户模板的 Excel。支持全部存量、最近一天、最近一周、最近一个月，默认自动进行缓存优先的 LLM 分类及必要学历补全，完成校验后直接输出最终表格。

已导入 **500 家企业、290 个招聘链接**，目前已接入并真实验收 **226 家企业**；其余 **65 个有链接来源**待适配，空链接待补充。平台逻辑共享，企业入口和覆盖逐家核验。2026-10-15 在国机集团漏采修复之外新增 50 家的任务仍在进行：国机集团已从错误的 8 条总部岗位修正为完整集团目录中 1,004 条正式校招；另外 **47/50 家**名录企业真实覆盖验收通过，共 15,328 条有效岗位，详见[本轮进度与快照](docs/adapter-20261015-progress.md)。先前发布的[8 条阶段表](outputs/2026-10-15/新增1家-阶段汇总-岗位信息汇总.xlsx)仅保留历史证据，已被国机全目录复采取代，不用于本轮最终汇总。2026-10-14 新批次 **50 家有实际岗位的企业、6,287 条有效岗位**已交付，见[前批验收](docs/adapter-batch7-acceptance.md)；历史批次见 [前一批 50 家交付](docs/adapter-batch6-acceptance.md)、[首轮验收](docs/acceptance.md)、[第三批](docs/adapter-batch3-acceptance.md)、[第四批](docs/adapter-batch4-acceptance.md) 和 [42 家复查](docs/adapter-batch5-triage.md)。

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
uv run job-crawler run

# 选择单个/多个来源
uv run job-crawler run --source COM0012 --window day
uv run job-crawler run --source COM0002 --source COM0008 --window week
uv run job-crawler run --window month

# 显式纳入全部名录：未接入/没有链接的来源逐一报告为阻塞
uv run job-crawler run --all-sources
```

省略 `--output` 会在 `.runtime/runs/` 创建独立工作目录，导出后压缩归档，并将最终表格发布到 `outputs/YYYY-MM-DD/`。文件名区分 all/day/week/month 和运行编号，同日不同窗口或多轮运行不覆盖、不混淆。显式 `--output` 保留开发模式（完整未压缩目录），程序仍拒绝覆盖非空目录。初始来源 ID：中石油 `COM0002`、建行 `COM0008`、平安 `COM0012`、阿里 `COM0015`。

| 模式 | 规则 |
| --- | --- |
| `all`（默认） | 当前目录仍展示、未明确关闭、截止日期尚未过去；没有截止日期时保留 |
| `day` | 同上，且源站发布时间在最近 24 小时内；默认也纳入建立基线后最近 24 小时首次发现的无日期岗位，依据单独标记 |
| `week` | 同上，且源站发布时间在最近 7 天内 |
| `month` | 同上，且源站发布时间在最近一个日历月内，月底按上月最后一天截断 |

默认以 Asia/Shanghai 当前时间为基准。发布时间只有日期时，按当天时间区间与窗口相交判断；截止日期有效至当天结束。week/month 缺少发布时间进入待核验；day 的无日期发现规则见下文，不会把首次发现时间写入发布日期。非空但无法解析的日期仍进入待核验。

可用 `--as-of '2026-10-10T12:00:00+08:00'` 固定筛选基准。它只筛选当前可访问目录，不还原历史网页。建行列表已经证明过期的岗位不再读取详情，计入 `skipped_expired` 并保留列表证据。

## 结果目录与自动清理

日常只需运行 `uv run job-crawler run` 或 `uv run job-crawler run --window day`。在 `outputs/2026-10-14/` 这样的日期目录中查看 `all-运行编号-岗位信息汇总.xlsx` 和 `all-运行编号-严格导入.xlsx`；前者包含待补全信息，后者只包含通过导入校验的岗位。日期取本轮 manifest 中的 `as_of`（上海时区）；指定历史 `--as-of` 不等于历史网页回溯。来源状态及原始快照保存在后台，不额外加入模板列。

不同筛选时刻的 day 不能直接混合，因此同一天多次运行保留独立表格。若分批采集后需要一份汇总，仍使用 `bundle` 明确选择来源快照；同一来源只选一轮、窗口及 day 筛选时刻必须一致。

后台 `.runtime/archives/` 保存经 SHA-256 逐文件校验的压缩包，`.runtime/archive-index.json` 记录原目录、日期发布文件、哈希及状态库路径。旧证据引用通过索引读取压缩内容，单纯归档不会迫使每日重读详情。代码升级仍遵循原有“代码身份变化则重建基线”的规则，本次没有绕过身份校验或把旧代码历史强制迁移成新代码基线。不要手动删除索引、状态库或仍受引用保护的归档。LLM 分类/学历缓存继续共用，不因按日期输出而重置。

```sh
# 显式输出适合开发；完成后按历史日期发布并压缩
uv run job-crawler archive outputs/my-run --publish
# 重要交付可加 --pin，长期保留其后台快照

# 预览；加 --apply 才删除到期数据。默认 run 成功导出后会自动应用
uv run job-crawler maintenance
uv run job-crawler maintenance --apply

# 从索引中的原运行路径恢复到不存在的新目录，不访问网站
uv run job-crawler restore outputs/my-run --output .runtime/restored/my-run
# 重新补全并导出（按默认模型配置可能调用 LLM）
uv run job-crawler export .runtime/restored/my-run --output .runtime/runs/remapped
uv run job-crawler archive .runtime/runs/remapped --publish
```

默认非固定归档至少保留 30 天，从归档时刻开始计时；每个来源/窗口的最新快照及仍被增量状态引用的归档额外保留，最终 Excel 永不自动删除。LLM 缓存保留 90 天，合计上限 2 GiB，超限淘汰最旧文件；淘汰后该内容再次出现可能需要模型调用。可在 `config.toml` 的 `[retention]` 修改 `archive_days`、`cache_days`、`cache_mb`。这些是清理阈值，并非对受保护数据的硬容量上限。

`archive` 仅用于已停止写入的目录，默认只压缩；`--publish` 要求存在 manifest 和两份最终表格。归档失败保留原数据；采集中断时，CLI 显示的 `.runtime/runs/<运行编号>` 仍保留，可用 `--output 该目录 --resume` 恢复。已完成并归档的快照用 `restore/export`，不作为过期断点继续采集。历史文档中的旧 `outputs/...` 路径可作为 `restore` 的输入；如果是某个归档目录下的子目录，先恢复其顶层目录。

本地历史整理记录见 [目录清理验收](docs/output-retention-acceptance.md)。10 月 10 日的 20 家、12 日新增 53 家、13 日新增 50 家分别保留最终表格，属于当时离线汇总结果，不代表重新确认了今天的在招状态。

## 项目内适配器接入 Skill

新增链接或批量接入时可以直接告诉 Codex：

> 使用 $add-recruitment-adapters，从名录中新增 50 家企业的招聘适配器，复用调试阶段采集结果，完成验收后汇总并按日期归档。受阻企业按本次允许的范围处理，明确报告缺口。

也可以指定企业和 URL 列表。skill 位于 [.agents/skills/add-recruitment-adapters/SKILL.md](.agents/skills/add-recruitment-adapters/SKILL.md)，随仓库保存；AGENTS.md 提供发现入口。若当前客户端未列出该 skill，或使用 Claude Code 等其他代理，可直接要求读取该文件并执行，不依赖全局安装或专属工具。

skill 包含实现定位、分页/详情/增量契约、真实验收标准、批次企业去重计数、快照复用、两份表格核对与归档步骤，并提供只读交付核验脚本。零岗位、部分覆盖和同公司多个入口不能凑足目标家数；不会仅因创建适配器文件就报告交付完成。日常运行已有站点的 day/all 命令无需调用此 skill。

## 项目内公司信息整理 Skill

已有岗位表需要整理公司资料时，可以告诉 Codex：

> 使用 $enrich-company-profiles，根据我指定的岗位信息汇总.xlsx 搜集这批企业的公司信息，只交付本批公司；Logo 尽量使用适合圆形头像的透明 PNG，最后一列填写总部详细地址。

需要合并时明确给出旧表：

> 使用 $enrich-company-profiles，把指定新岗位表中的企业资料与我提供的历史公司表合并，按公司主体去重，保留来源并核对重叠公司的岗位计数。

入口为 [.agents/skills/enrich-company-profiles/SKILL.md](.agents/skills/enrich-company-profiles/SKILL.md)，包含企业范围、公开资料查证、字段枚举、总部地址、PNG 头像、合并计数和导出验收规则。[公司导入模板](.agents/skills/enrich-company-profiles/assets/公司导入模板.xlsx) 随仓库保存，原始 13 列和示例保持不变；执行时删除示例并追加第 14 列 `详细地址`。不要与岗位导入模板混用。

客户端未列出 skill 时，直接要求读取上述 SKILL.md 执行即可，无需全局安装。该 skill 是研究与交付指南，不是新增自动爬取 CLI，也不重新采集岗位。结果保存在 `outputs/YYYY-MM-DD/`（公司 XLSX 与 PNG ZIP），过程与逐字段依据保存在 `.runtime/company-enrichment/`；未查证资料明确标记，不承诺未知字段可以直接通过系统导入。设计与离线验收见 [SPEC-049](specs/049-company-profile-skill.md)。

## 每天新增一批适配器后的交付

2026-10-14 本批实际交付文件：[50 家岗位信息汇总](outputs/2026-10-14/新增50家-批次汇总-岗位信息汇总.xlsx)、[50 家严格导入](outputs/2026-10-14/新增50家-批次汇总-严格导入.xlsx)。信息表 6,287 行，严格导入 459 行，其余 5,828 行保留待补全；汇总审计及每家实采限制见[本批验收](docs/adapter-batch7-acceptance.md)。

同一批公司的公开资料已另存为[50 家公司导入表](outputs/2026-10-14/公司导入-新增50家.xlsx)、[50 张透明 PNG Logo](outputs/2026-10-14/公司Logo-新增50家-PNG头像.zip)及[待补全清单](outputs/2026-10-14/公司资料-新增50家-待补全清单.md)。公司表按上面的岗位信息表统计 50 家、6,287 条校招记录；模板必填的类型缺 37 家、行业缺 1 家、规模缺 43 家，尚不符合系统整表导入约束。逐字段来源和 Logo 原始链接保存在 `.runtime/company-enrichment/20261014-batch50/research.json`，重复核验时使用该文件与随附模板重新导出，范围、字段规则和验收见 [SPEC-100](specs/100-batch50-company-profiles.md)。

开发时显式指定独立工作目录，保留调试时已采到的每家公司快照。确认这批 50 家均有有效岗位、覆盖范围明确后，选择每家最新通过验收的快照路径（同来源不能重复），写入 JSON 数组，例如 `.runtime/batches/2026-10-14-inputs.json`。已压缩的输入先 restore，再选择恢复后的目录或 collections 文件。

```sh
uv run job-crawler bundle --inputs-file .runtime/batches/2026-10-14-inputs.json \
  --output .runtime/runs/new50-20261014
uv run job-crawler archive .runtime/runs/new50-20261014 \
  --publish --label 新增50家
```

得到 `outputs/2026-10-14/新增50家-岗位信息汇总.xlsx` 和 `新增50家-严格导入.xlsx`。bundle 不重新请求招聘网站，会复用模型缓存并在必要时调用模型补全；保留每家真实采集时刻。这里的“新增50家”是当天新接入的公司，其表中可包含仍在展示的存量岗位，与 day 的最近一天新增岗位不同。

调试目录不会因执行 bundle 自动消失。完成交付后，开发代理对已停止写入的调试目录逐一执行 `job-crawler archive 目录`（不加 --publish），只发布最终汇总；快照进入同一保留策略。一天多批用不同 label，例如 `新增50家-第二批`，已有同名交付不会被覆盖。

## 每日减少详情请求

建议升级 alpha.2 后先执行一次全量建立基线，之后每天运行 day，每 15 天再次运行 all。输出目录每轮必须不同；**所有轮次共用同一 `--state`，保留证据文件或完整的归档及索引**。默认状态库是 `.runtime/state.sqlite`，不应按天删除或换路径。

```sh
# 首次基线，以及之后每 15 天的全量刷新；每次使用新的输出目录
uv run job-crawler run --window all

# 每日：默认自动按日期发布并归档，无需手工指定输出目录
uv run job-crawler run --window day

# 无需另跑 classify；最终表格位于 outputs/YYYY-MM-DD/
# 如模型失败或缺 key，修复配置后只重试补全/导出，不重新访问招聘网站
uv run job-crawler restore .runtime/runs/原运行编号 --output .runtime/restored/retry
uv run job-crawler export .runtime/restored/retry --output .runtime/runs/retried
uv run job-crawler archive .runtime/runs/retried --publish
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

**2026-10-13 最新交付**：`outputs/batch6-20261013-final/岗位信息汇总.xlsx` 含 **50 家企业、11,176 条岗位信息**，每家都实际有岗位。原 26 家继续修复 4 家，另补充 27 家，复用当天已完成的 19 家快照。严格导入表 `jobs.xlsx` 有 2,160 行，其余 9,016 行主要等待后台地点映射及缺失字段补全；主表不等同全部可直接导入。按 `outputs/batch6-fifty-inputs.json` 执行下述 `bundle` 命令可从快照重导出，无需重爬。范围、原始运行目录与仍受阻的 22 家见 [验收记录](docs/adapter-batch6-acceptance.md)。

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

**42 家分类后结果**：`outputs/initial42-classified-20261012/result/jobs.xlsx` 有 351 条通过严格校验、可直接导入的岗位；同目录 `岗位信息汇总.xlsx` 展示全部 7,032 条采集检查记录，未通过约束的 6,681 条见 `review.json`。当前主要障碍是地点缺少已核验的后台“省/市”映射，不会为了增加导入行数猜填城市。分类调用与缺失原因见 [42 家分类验收](docs/classification-42-acceptance.md)。

**第二批静态活动页**：蓝思 COM0245、中国燃气 COM0259、天津银行 COM0406 的 Crawl4AI 全量采集已通过覆盖核验，合计 362 条；最终十三列检查表在 `outputs/batch2-final-20261012/岗位信息汇总.xlsx`。蓝思智能机器人分支的地点经复核后使用重新采集的快照，和另两站结果由程序离线合并。分类已完成，严格导入表仍因缺少已核验的地点映射而没有合格行；具体数量与历史专题风险见 [第二批验收](docs/51job-batch2-acceptance.md)。

**北森批量接入**：本轮另有 8 家北森企业的公开校招目录与详情全量验收通过，共 787 条；由程序从八份快照离线合并的十三列检查表在 `outputs/zhiye-bulk-combined-20261012/岗位信息汇总.xlsx`。默认 `deepseek-flash` 离线分类后的结果在 `outputs/zhiye-bulk-classified-20261012/result/`，严格导入表有 3 行，其余 784 行主要等待地点映射。招商局能源运输和申能股份所给入口实际上是集团统一门户，存在跨法人岗位，尚未绑定；详见 [北森批量验收](docs/zhiye-batch-acceptance.md)。

**第三批新增二十家**：京东、腾讯、联想、中粮、交通银行、中国联通、广汽、美团、顺丰、上海建工、牧原、温氏、徐工、正泰、上港、重庆银行、德赛西威、哔哩哔哩、宁波华翔、龙佰集团已完成公开目录全量验收；共采集 6,741 条目录行，按状态和校招范围入选 6,657 条。程序从各自快照生成的十三列检查表和严格导入表在 `outputs/batch3-20-delivered-full-llm-20261012/`：汇总表有 6,657 行，严格导入表有 410 行，其余 6,247 行待补全。缺失后台省市映射等字段的岗位继续列入 `review.json`，不人为填入导入表。逐站数量、范围、证据和复现步骤见 [第三批验收](docs/adapter-batch3-acceptance.md)。吉利仍因采集期间目录总数变化保持待验证，未绑定。

**第四批五十家扩展**：首次验收通过 8 家；对剩余 42 家复查后又修复并实采通过 16 家，累计 **24/50 家来源覆盖完整**。程序生成的 `outputs/batch5-20261013-final/岗位信息汇总.xlsx` 含 6,645 条有效岗位信息和 24 家来源的采集情况；其中 1,944 条满足严格导入格式，4,701 条在待补全报告中。其余 26 家仍未通过完整性验收，不进入汇总。逐站原因、证据与修复范围见 [剩余 42 家复查](docs/adapter-batch5-triage.md) 和 [SPEC-033](specs/033-fifty-source-expansion.md)。

汇总不会重新访问招聘网站；all 快照按汇总时刻再次筛除已截止记录，day/week/month 保留原窗口和筛选时刻。不同窗口或不同窗口基准时刻的快照拒绝混合，不会把每日预筛选的简略行重新当成全量岗位。保留原始采集时间，不宣称重新验证在线状态。同一来源若指定两轮结果会拒绝合并，需自行选择其中一轮。默认与 run 一样为未满足约束的字段进行缓存优先的模型补全；可能访问模型服务，但不访问招聘网站。设 llm.enabled=false 可关闭。

`岗位信息汇总.xlsx` 包含待补全记录，使用更新模板的十三字段，缺失值留空，正文不截断。`jobs.xlsx` 则始终是严格校验的导入表。分类补全后，学历或地点不合要求的记录仍进入 `review.json`，不能把分类成功等同于全部可直接导入。JSON 同时保留全部原始岗位（包括已排除的岗位）及证据。

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
max_calls = 2000            # 分类、复核、学历及重试共用总上限；20 站初次合并需更高预算
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

### 岗位正文章节与历史修复

[SPEC-034](specs/034-description-headings.md) 统一识别职责/要求章节，去掉 `【岗位职责】` 等冗余标题和因拆分产生的括号残留。支持标题同行、跨 HTML 段、编号与常见同义词；保留正文中的普通括号及词语。默认采集和导出均使用修复后的清理逻辑。

已被旧逻辑拆坏的快照不能靠普通 `export` 还原标题边界，应从原始证据重放。对 2026-10-12 汇总可运行以下离线工具（`MOKA_PUBLIC_IV` 是当时公开页面的 `TurboApply.data.aesIv` 参数，工具不联网获取，也不将其保存到报告）：

```sh
uv run python scripts/repair_description_snapshot.py \
  outputs/today-collected-20261012-combined outputs/description-repair-new \
  --moka-iv "$MOKA_PUBLIC_IV"
uv run python scripts/apply_description_workbook.py \
  outputs/today-collected-20261012-combined/岗位信息汇总.xlsx \
  outputs/description-repair-new/cell-patches.json \
  outputs/description-repair-new/岗位信息汇总-正文修复版.xlsx
```

工具核对岗位身份、旧解析结果与原单元格，只修改职责/要求，不重新分类、筛选或改写其他字段；输出必须为新目录/新文件，原件保留。修复计划、逐岗位依据、修复后的交付快照与工作簿核对结果分开保存。该工具按昨日已知适配器证据格式设计；缺失/冲突证据会报错，不适用于任意历史文件。此次统计和限制见 [验收记录](docs/description-headings-acceptance.md)。

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
