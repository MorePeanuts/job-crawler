# 2026-10-23 新增 50 家招聘适配器验收

对应 [SPEC-299](../specs/299-unicorn-priority-20261023.md)、[SPEC-300](../specs/300-2027-moka-zhiye-candidates.md)、[SPEC-301](../specs/301-feishu-2027-tenants.md)。

## 交付结论

- 本批从开始时 414 家已绑定企业之外，新接入 **50 个不同企业 ID**。50 家均于 2026-10-23 实时采集，窗口 `all`，逐站 `coverage=complete`、`terminal=true`、有效正式校招岗位 `selected>0`，无目录覆盖问题。
- 50 个来源合计发现 **2,526 条**目录记录；源范围和日期筛选后 **2,318 条**有效岗位，岗位信息表 2,318 行；严格导入表 **1,405 行**，待补全 **913 行**。待补全常见原因是源站未给可直接映射的地点、学历或完整字段；信息表仍保留这些岗位，未虚填。
- 最终汇总时刻为 `2026-10-23T12:04:21.070769+08:00`。各来源实采时刻和原始快照 ID 保存在已归档最终 `report.json` 的 `origins` 字段。`all` 表示当时仍展示的存量，不表示这些岗位都在今日发布。
- 发布文件：[岗位信息汇总](../outputs/2026-10-23/新增50家-20261023-岗位信息汇总.xlsx)、[严格导入](../outputs/2026-10-23/新增50家-20261023-严格导入.xlsx)。只读审计：`.runtime/batches/unicorn50-20261023/delivery-audit.json`，`ok=true`、50 家、50 来源、两表行数一致。

## 逐来源实采

| 来源 | 企业/招聘品牌 | 无筛选目录 | 有效岗位 | 严格导入 | 待补全 | 实采时间（上海） |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| [COM0808](https://app.mokahr.com/campus-recruitment/voyah/146293#/jobs) | 岚图汽车 | 67 | 33 | 30 | 3 | 11:26 |
| [COM0810](https://app.mokahr.com/campus-recruitment/huahong/70000#/jobs) | 上海华力 | 72 | 60 | 60 | 0 | 11:26 |
| [COM0812](https://app.mokahr.com/campus-recruitment/nbdeli/70019#/jobs) | 得力集团有限公司 | 38 | 38 | 23 | 15 | 11:21 |
| [COM0813](https://app.mokahr.com/campus-recruitment/ruijie/136206#/jobs) | 锐捷网络股份有限公司 | 75 | 75 | 53 | 22 | 11:21 |
| [COM0823](https://sanan-e.zhiye.com/campus/jobs) | 三安光电股份有限公司 | 42 | 17 | 0 | 17 | 11:21 |
| [COM0827](https://genvict1.zhiye.com/campus/jobs) | 金溢科技 | 4 | 3 | 0 | 3 | 11:28 |
| [COM0828](https://bomc.zhiye.com/campus/jobs) | 中山大洋电机股份有限公司 | 9 | 8 | 0 | 8 | 11:28 |
| [COM0829](https://aimer.zhiye.com/campus/jobs) | 爱慕集团 | 17 | 13 | 0 | 13 | 11:28 |
| [COM0830](https://leadchina.zhiye.com/campus/jobs) | 无锡先导智能装备股份有限公司 | 78 | 72 | 0 | 72 | 11:28 |
| [COM0831](https://lanxincn.zhiye.com/campus/jobs) | 蓝芯机器人 | 16 | 16 | 0 | 16 | 11:28 |
| [COM0832](https://dobot.zhiye.com/campus/jobs) | 越疆机器人 | 38 | 37 | 27 | 10 | 11:28 |
| [COM0833](https://ti5robot1.zhiye.com/campus/jobs) | 钛虎机器人科技（上海）有限公司 | 32 | 32 | 0 | 32 | 11:28 |
| [COM0834](https://nexchip.zhiye.com/campus/jobs) | 合肥晶合集成电路股份有限公司 | 27 | 27 | 27 | 0 | 11:28 |
| [COM0835](https://luxpowertek.zhiye.com/campus/jobs) | 鹏城新能 | 7 | 7 | 6 | 1 | 11:28 |
| [COM0836](https://app.mokahr.com/campus-recruitment/sina/43536#/jobs) | 新浪与微博 | 16 | 16 | 15 | 1 | 11:31 |
| [COM0837](https://app.mokahr.com/campus-recruitment/kfconcept/144795#/jobs) | 深圳市卓尔摄影器材有限公司 | 20 | 20 | 20 | 0 | 11:31 |
| [COM0838](https://app.mokahr.com/campus-recruitment/zhihu/68321#/jobs) | 知乎 | 55 | 12 | 7 | 5 | 11:31 |
| [COM0839](https://app.mokahr.com/campus-recruitment/vertiv/118713#/jobs) | 维谛技术有限公司 | 37 | 37 | 34 | 3 | 11:31 |
| [COM0840](https://app.mokahr.com/campus_apply/newvisionox/24735/#/jobs) | 维信诺 | 49 | 44 | 43 | 1 | 11:31 |
| [COM0841](https://qxkj1.zhiye.com/campus/jobs) | 南京全信传输科技股份有限公司 | 13 | 13 | 0 | 13 | 11:32 |
| [COM0842](https://njcttq.zhiye.com/campus/jobs) | 南京正大天晴制药有限公司 | 43 | 33 | 0 | 33 | 11:32 |
| [COM0843](https://iwhalecloud1.zhiye.com/campus/jobs) | 浩鲸科技 | 50 | 45 | 0 | 45 | 11:32 |
| [COM0844](https://spacestar.zhiye.com/campus/jobs) | 航天恒星 | 27 | 26 | 1 | 25 | 11:32 |
| [COM0845](https://warrant.zhiye.com/campus/jobs) | 华纳大药厂 | 14 | 13 | 0 | 13 | 11:32 |
| [COM0846](https://cetctj.zhiye.com/campus/jobs) | 中电太极集团 | 15 | 13 | 0 | 13 | 11:32 |
| [COM0847](https://dzwy.zhiye.com/campus/jobs) | 新大正物业集团 | 22 | 22 | 1 | 21 | 11:32 |
| [COM0858](https://awinic.zhiye.com/campus/jobs) | 艾为电子 | 47 | 46 | 0 | 46 | 11:35 |
| [COM0864](https://dynanonic.zhiye.com/campus/jobs) | 德方纳米 | 7 | 6 | 0 | 6 | 11:38 |
| [COM0870](https://app.mokahr.com/campus-recruitment/bjhl/102145#/jobs) | 高途 | 229 | 115 | 84 | 31 | 11:42 |
| [COM0871](https://rigolportal.jobs.feishu.cn/campus/position/list) | 普源精电科技股份有限公司 | 21 | 20 | 0 | 20 | 11:42 |
| [COM0872](https://moonton.jobs.feishu.cn/campus/position/list) | 沐瞳科技 | 92 | 90 | 0 | 90 | 11:42 |
| [COM0873](https://modelbest.jobs.feishu.cn/campus/position/list) | 面壁智能 | 64 | 1 | 0 | 1 | 11:42 |
| [COM0876](https://app.mokahr.com/campus-recruitment/gufen/143531#/jobs) | 东风汽车股份有限公司 | 16 | 15 | 1 | 14 | 11:50 |
| [COM0877](https://app.mokahr.com/campus-recruitment/supcon/172631#/jobs) | 中控技术 | 76 | 73 | 42 | 31 | 11:50 |
| [COM0878](https://app.mokahr.com/campus-recruitment/threatbook/39679#/jobs) | 微步在线 | 56 | 42 | 21 | 21 | 11:50 |
| [COM0879](https://app.mokahr.com/campus_apply/manbang/94191#/jobs) | 满帮集团 | 14 | 4 | 0 | 4 | 11:50 |
| [COM0880](https://app.mokahr.com/campus_apply/tuyoogame/146219#/jobs) | 途游游戏 | 75 | 72 | 57 | 15 | 11:50 |
| [COM0881](https://app.mokahr.com/campus_apply/didiglobal/96064#/jobs) | 滴滴出行 | 100 | 99 | 72 | 27 | 11:51 |
| [COM0882](https://app.mokahr.com/campus-recruitment/qianli1/147197#/jobs) | 千里智驾 | 164 | 118 | 79 | 39 | 11:51 |
| [COM0883](https://app.mokahr.com/campus-recruitment/gtx/102188#/jobs) | 上海光通信有限公司 | 46 | 46 | 45 | 1 | 11:51 |
| [COM0885](https://app.mokahr.com/campus-recruitment/wison/115998#/jobs) | 惠生工程 | 36 | 35 | 1 | 34 | 11:51 |
| [COM0886](https://app.mokahr.com/campus-recruitment/kingdeehr/166565#/jobs) | 金蝶 | 217 | 212 | 210 | 2 | 11:51 |
| [COM0888](https://app.mokahr.com/campus-recruitment/pwrd/172467#/jobs) | 完美世界 | 32 | 32 | 23 | 9 | 11:51 |
| [COM0889](https://app.mokahr.com/campus_apply/hypergryph/26326#/jobs) | 鹰角网络 | 101 | 57 | 7 | 50 | 11:51 |
| [COM0890](https://app.mokahr.com/campus_apply/amec/4362#/jobs) | 中微公司 | 170 | 160 | 135 | 25 | 11:51 |
| [COM0891](https://app.mokahr.com/campus-recruitment/tsinghuaic/39656#/jobs) | 紫光同芯微电子有限公司 | 28 | 28 | 19 | 9 | 11:51 |
| [COM0892](https://app.mokahr.com/campus_apply/pharmaron/45318#/jobs) | 康龙化成 | 213 | 140 | 120 | 20 | 11:51 |
| [COM0893](https://app.mokahr.com/campus-recruitment/dhrobotics/168695#/jobs) | 深圳市大寰机器人科技有限公司 | 29 | 29 | 26 | 3 | 11:51 |
| [COM0894](https://app.mokahr.com/campus-recruitment/sineng/172108#/jobs) | 上能电气股份有限公司 | 124 | 124 | 105 | 19 | 11:53 |
| [COM0895](https://app.mokahr.com/campus-recruitment/37/58016#/jobs) | 三七互娱 | 22 | 22 | 11 | 11 | 11:53 |

目录总数包括被排除的实习、旧批次、截止或已关闭岗位。表内“有效岗位”按当前时间筛选，不把 `review` 当作失败覆盖，也不将其混入严格导入。每站的 `scope_description`、分页首末证据、排除数量和单位字段保存在已归档 `report.json` 与原始快照。

## 独角兽优先核查与未启用入口

- 批次开始时独角兽名单尚有 **49 家有招聘链接但未绑定**。本批先对其中 48 家进行独立页面/业务请求探测；`COM0514` 京东科技只关联京东集团共享门户，不能从该入口可靠分离京东科技岗位，保留待接入。这 49 家本轮均未达到独立主体与当前正式校招完整目录的共同验收条件，因此最终 50 家由用户已允许的其他待接入及新查证企业补足。探测证据位于 `.runtime/batches/unicorn50-20261023/probe-*`。
- 另有华润置地 `COM0875`、当升科技 `COM0884` 当天完成平台目录遍历，但两个入口均覆盖多个业务主体/子公司，未纳入本批正式绑定或汇总；其网站链接保留在待接入名录。星环信息科技候选 `COM0887` 的首屏未取得可核实完整目录，未启用。
- 本批结束后名录共 859 家、615 个非空招聘入口，正式绑定 464 家，仍有 **151 家带链接待接入**（其中上述 49 家来自原独角兽名单）；另 244 家暂无链接。这是来源状态统计，不代表 151 家都有可接入的在招正式校招岗位。

## 验证与复现

- `uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run ty check` 全部通过；`uv run pytest`：**1,769 passed**。平台回放检查北森范围、Moka 分页/详情及 27 届过滤、飞书项目过滤；真实站点覆盖由上表与归档证据验证。
- 最终汇总使用 `.runtime/batches/unicorn50-20261023/inputs.json` 指定的 50 份当日单源快照执行 `bundle`；`audit_delivery.py --expected-companies 50` 通过后以 `archive --publish --label 新增50家-20261023` 发布。原始目录及最终汇总已压缩归档，路径映射保存在 `.runtime/archive-index.json`；若重建，先 `restore` 所需原目录。
- 可离线复核最终快照：`uv run job-crawler restore .runtime/runs/unicorn50-20261023-final --output .runtime/runs/unicorn50-20261023-review`，再运行 `uv run python .agents/skills/add-recruitment-adapters/scripts/audit_delivery.py .runtime/runs/unicorn50-20261023-review --expected-companies 50`。这只重读 2026-10-23 快照，不重新确认当前岗位状态。
