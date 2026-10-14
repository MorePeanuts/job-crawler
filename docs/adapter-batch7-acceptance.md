# 2026-10-14 新增 50 家批次阶段验收

对应 SPEC-050～059。本文件是阶段记录；SPEC-050 要求的 50 家汇总尚未形成，不能将本表十家称为最终交付。

## 批次起点与当前通过来源

开始时正式绑定 128 个企业 ID，名录中另有 100 家填有招聘 URL 未接入。本轮选择范围为这些未接入企业，昨天 50 家交付中的既有企业不计入今天新增数。

| 来源 | 名录主体 | 适配器 | 实采时间（上海） | 目录/唯一/完整正文 | 有效校招 | 信息表 | 严格导入 | 待补全 | 快照 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| COM0065 | 拼多多控股公司 | `pdd-campus@1` | 11:03–11:04 | 34/34/34 | 34 | 34 | 0 | 34 | `outputs/dev-20261014-COM0065` |
| COM0425 | 深圳迈瑞生物医疗电子股份有限公司 | `zhiye-mindray@1` | 11:09–11:09 | 64/64/64 | 64 | 64 | 0 | 64 | `outputs/dev-20261014-COM0425` |
| COM0440 | 申洲国际集团控股有限公司 | `zhiye-shenzhou@1` | 11:10–11:10 | 40/40/40 | 40 | 40 | 0 | 40 | `outputs/dev-20261014-COM0440` |
| COM0497 | 泸州老窖股份有限公司 | `zhiye-luzhou-laojiao@1` | 11:12–11:13 | 12/12/12 | 12 | 12 | 1 | 11 | `outputs/dev-20261014-COM0497` |
| COM0421 | 浙江英特集团股份有限公司 | `yingte-campus@1` | 11:36–11:37 | 4/4/4 | 4 | 4 | 0 | 4 | `outputs/dev-20261014-COM0421` |
| COM0191 | 理想汽车 | `li-auto-campus@1` | 11:39–11:45 | 633/633/633 | 630 | 630 | 0 | 630 | `outputs/dev-20261014-COM0191-v3` |
| COM0058 | 小米集团 | `feishu-xiaomi@1` | 11:41–11:47 | 779/779/779 | 779 | 779 | 0 | 779 | `outputs/dev-20261014-COM0058` |
| COM0433 | 瑞声科技控股有限公司 | `feishu-aac@1` | 11:43–11:44 | 70/70/70 | 70 | 70 | 0 | 70 | `outputs/dev-20261014-COM0433` |
| COM0386 | 中际旭创股份有限公司 | `feishu-innolight@1` | 11:44–11:45 | 75/75/75 | 75 | 75 | 0 | 75 | `outputs/dev-20261014-COM0386` |
| COM0045 | 江西铜业集团有限公司 | `jxcc-campus@1` | 11:55–11:56 | 50/50/50 | 50 | 50 | 0 | 50 | `outputs/dev-20261014-COM0045` |

当前共 10 个新企业 ID、1,758 条有效且可核对来源的正式校招岗位。十个来源的 `coverage=complete`、`expected=listed=unique=details`，无源详情或分页问题。理想汽车 633 条正式筛选结果中 3 条详情项目标为实习，已由公共筛选排除，故有效岗位 630 条。总体严格导入 1 条、待补全 1,757 条；主要障碍是后台地点路径没有核定映射，缺学历的行由公共流程保留待补全。各岗位已按源发布日期和截止时间筛选，未把采集时刻当发布时间。原始 `jobs.json`、证据、`report.json` 和两份阶段工作簿位于上述忽略 Git 的运行目录。

拼多多源页明确区分“应届生招聘”与“实习生招聘”，从无筛选 POST 目录读到 34 条，逐条详情 ID 与列表吻合；34 条均为 2027 届。迈瑞与申洲公开 `Category=2` 列表直接包含职责及要求，翻页至稳定源总数，没有请求不必要的详情。泸州老窖的 12 条列表 `Org` 均为“泸州老窖股份有限公司”；适配器对今后跨法人记录会标记不完整，不默默归入该公司。

英特源站是浙江省国际贸易集团共享门户：校园渠道共 78 条，组织树证明其中 4 条属于英特集团下属单位，另 74 条不归入本企业。理想汽车共 633 条详情，核对 2026/2027 校园项目与 2027“理想+”专项；3 条虽列表标“正式”、详情却标“实习生招聘”，明确排除。小米 779、瑞声 70、中际旭创 75 条均通过站点实际签名分页、源 ID 去重和末页核对。小米旧官网公开链接指向新飞书校招门户，后两家由各自官网导航进入飞书目录；名录已换成直接目录 URL。实采时刻见各 `report.json.as_of`。

江西铜业集团官网校园菜单 `M000510` 五页共 50 条，单位字段涉及集团本部、技术研究院、德兴铜矿等，职位正文和截止日期均在官方 CMS 响应中；全部逐页去重并按源单位留存。

## 已探测但未计入的候选

本轮 Crawl4AI 探测快照保存在 `.runtime/batches/2026-10-14-*-probes*/`；旧日探测仅用于选候选，不充当今天验收。以下障碍代表本次观察，不表示永久无法接入。

| 来源 | 本轮结论 |
| --- | --- |
| COM0412 软通动力 | `/campus/all` 共 9 条，完整读取两页后 `hiretype_name` 全部为“实习”；没有符合默认正式校招范围的岗位。 |
| COM0468 招商局能源运输、COM0471 申能股份 | 仍为集团共享门户，历史验收已证明混合其他法人；不能把全目录归给名录中的上市主体。 |
| COM0465 世茂 | Moka 原入口显示“页面不存在”。 |
| COM0500 东方证券 | 当前门户为日常实习、社会招聘，缺正式校招。 |
| COM0435 恒瑞医药、COM0208 歌尔 | 所给旧页面分别受页面保护、返回 404，缺完整目录。 |
| COM0437 闻泰科技 | 所给校园入口当前页面所有岗位类别显示 0；不能把零条计作有岗位企业。 |
| COM0423 蜜雪冰城 | 公开校招目录 26 条，但页面以“蜜雪集团”招聘，API 未给出逐岗位法人 `Org`；名录主体是蜜雪冰城股份有限公司，跨法人边界待核实。 |
| COM0278 亿纬锂能 | 官网页面只有若干职位类别与总需求人数，缺逐岗位身份与正文。 |
| COM0324 粤海控股 | 所给旧详情可读，但通用 `/campus/jobs` 未呈现完整岗位目录；暂不绑定。 |

其它旧活动、只有公告、无职位响应或混合集团入口继续 pending；仅探测首页或职位标题不算完成适配。

## 复现

```sh
# 以下每个来源独立使用临时绑定、开发运行目录及状态库；正式绑定在实采后写入
uv run job-crawler run --source COM0065 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0065 --state .runtime/development-state/20261014-COM0065.sqlite
uv run job-crawler run --source COM0425 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0425 --state .runtime/development-state/20261014-COM0425.sqlite
uv run job-crawler run --source COM0440 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0440 --state .runtime/development-state/20261014-COM0440.sqlite
uv run job-crawler run --source COM0497 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0497 --state .runtime/development-state/20261014-COM0497.sqlite
uv run job-crawler run --source COM0421 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0421 --state .runtime/development-state/20261014-COM0421.sqlite
uv run job-crawler run --source COM0191 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0191-v3 --state .runtime/development-state/20261014-COM0191-v3.sqlite
uv run job-crawler run --source COM0058 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0058 --state .runtime/development-state/20261014-COM0058.sqlite
uv run job-crawler run --source COM0433 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0433 --state .runtime/development-state/20261014-COM0433.sqlite
uv run job-crawler run --source COM0386 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0386 --state .runtime/development-state/20261014-COM0386.sqlite
uv run job-crawler run --source COM0045 --bindings .runtime/batches/2026-10-14-bindings.toml --window all --output outputs/dev-20261014-COM0045 --state .runtime/development-state/20261014-COM0045.sqlite
```

单站运行退出码 2 是导入字段待补全，源覆盖按 `report.sources[].coverage` 单独核对。离线测试包括 `tests/test_pdd.py`、`tests/test_zhiye.py`、`tests/test_lixiang.py`、`tests/test_yingte.py`、`tests/test_jxcc.py` 和 `tests/test_feishu_campus.py`。本批最终质量门禁与阶段 bundle 结果在下节记录。最终 50 家 bundle 尚待 SPEC-050 完成。

## 九家阶段汇总与审计

九个完整来源快照列在 `.runtime/batches/2026-10-14-stage9-inputs.json`，用 `job-crawler bundle` 离线汇总到 `.runtime/runs/20261014-stage9`，避免再次抓取已验收站点。`audit_delivery.py --expected-companies 9` 审计通过，记录在 `.runtime/batches/2026-10-14-stage9-audit.json`：9 家有岗位企业、源采 1,711 条（其中理想汽车 3 条实习）、有效 1,708 条、信息表 1,708 行、严格导入 1 行、待补全 1,707 行。汇总 as_of 为 2026-10-14 11:48:41（上海）。已发布到 `outputs/2026-10-14/新增9家-阶段汇总-岗位信息汇总.xlsx` 与 `新增9家-阶段汇总-严格导入.xlsx`；这是九家阶段结果，不是用户要求的 50 家最终交付。

## 十家阶段汇总与审计

新增 COM0045 后，从已归档九家阶段快照恢复并连同本次江铜全量快照离线汇总，输入记录 `.runtime/batches/2026-10-14-stage10-inputs.json`。`audit_delivery.py --expected-companies 10` 在 `.runtime/batches/2026-10-14-stage10-audit.json` 通过：10 家有岗位企业、源采 1,761 条（含理想汽车 3 条实习）、有效 1,758 条、信息表 1,758 行、严格导入 1 行、待补全 1,757 行。汇总 as_of 为 2026-10-14 11:57:22（上海）。已发布 `outputs/2026-10-14/新增10家-阶段汇总-岗位信息汇总.xlsx` 和 `新增10家-阶段汇总-严格导入.xlsx`，并按项目规则压缩归档后台快照。这是当前最新阶段表格，离 50 家目标仍差 40 家。
