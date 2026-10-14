# 适配器开发规范

将新增招聘链接交给 Codex 时使用本规范，确保新站复用现有采集、筛选、验证和模板导出流程。

执行入口为项目 skill [add-recruitment-adapters](../.agents/skills/add-recruitment-adapters/SKILL.md)，包含批次计数、临时绑定实采、只读交付核验和快照归档命令。本文件维护底层适配器契约。

## 可直接使用的任务说明

> 阅读 AGENTS.md、specs/001-production.md、specs/011-publication-and-adapter-rollout.md 和 docs/adapter-development.md，为以下来源接入适配器：企业 ID、主体名称、招聘 URL（填入）。先编写该站 spec，确认平台、校招范围、目录/单位树/分页/详情与终止依据。探测和采集全部由程序执行，不手工补录岗位。优先复用现有适配器；新增逻辑须有回放测试和真实验收。使用 uv、Ruff、ty，走功能分支与分阶段提交。按当前十三列模板导出，不改变字段。遇到登录、验证码、403、附件或分类障碍如实报告。更新来源绑定、支持范围和验收记录。

仅有企业名称与 URL 也可开始调查。不要将链接加入清单就称为已完成接入。

## 接入步骤

1. 创建 `feat/adapter-<平台>` 分支，为入口增加稳定来源 ID，同企业可共享企业 ID。
2. 新建 `specs/<编号>-<平台>.md`：入口、纳入/排除范围、唯一键、目录树、接口、日期、附件、认证、分页末端和源计数语义。
3. 编写探测程序，以 Crawl4AI 页面/网络证据确认接口；优先公开 JSON，其次 DOM。不猜测接口，不手填岗位。
4. 检查是否可以复用平台。相同域名或第三方平台不保证版本相同；租户参数与平台流程分开。
5. 实现、注册适配器，增加首/次/末页、空目录、其他分支、详情关联和失败回放。
6. 真实试运行，核对源计数、唯一键、目录覆盖、过期筛选、必填字段和输出。单个分公司成功不等于整站完成。
7. 更新绑定版本、README 和验收记录，通过质量门禁后提交；按 AGENTS.md 的本地分支流程合回本地 main，不要求每次创建 PR，推送远端按用户要求执行。

## 代码契约

继承 `job_crawler.adapters.base.Adapter`，在 `adapters/__init__.py` 的 `REGISTRY` 显式注册。当前基类面向单个已知域名，多租户平台需要新增经验证的配置模型，不能删除入口检查来接受任意 URL。

```python
class NewPlatform(Adapter):
    name = "new-platform"
    version = "1"
    host = "jobs.example.com"
    path = "/campus"
    scope_description = "明确说明所有纳入目录、批次和类型"

    async def harvest(self) -> None:
        # observed() 读取已观察请求；request() 复用 Crawl4AI 会话。
        # 每个目录创建 Scope；add_page() 核对唯一键和重复页。
        # jobs.append(self.job(...)) 逐条保存，不在末尾一次性返回。
        # 有源总数或明确末页依据后，才能设置 terminal。
        ...
```

`Session` 为可替换协议：测试注入回放，正式使用 `BrowserSession`。JSON 边界允许 `dict[str, Any]`，随后必须校验；跨模块使用 `Job`、`Scope`、`Collection`。不得为每个适配器另建独立 Cookie 的 HTTP 客户端。

如果页面导航状态不能代表业务页是否就绪，可声明 `ready_endpoints`，或调用 `session.open(url, ready_endpoints=(... ,))`。每项必须是已观察到的同源完整路径前缀（如 `/web/recruitInfo/listN?`），跨源接口必须填写完整 HTTPS URL。参考 SPEC-003：恢复只适用于入口 412 或导航超时，要求本轮目标页面和全部声明接口的成功 JSON；后续仍须验证业务结构与覆盖。不能使用任意 XHR、历史响应或标题作为依据。恢复警告进入报告，不等同于覆盖成功。

可恢复详情失败调用 `self.error(exc, key)` 并继续其他详情。认证拒绝、重复页、预算耗尽停止受影响范围。`collect()` 保存异常和已获得岗位，不得清空已有结果或吞掉问题后返回成功。

## 覆盖规则

- 每个批次/单位独立 Scope，嵌套目录还需父目录计数；一个子单位完成不能代表全部完成。
- `expected`、`listed`、`unique` 口径一致。公告数量与展开岗位数分开核对。
- `details + reused_details + skipped_window + skipped_expired + skipped_closed == unique` 才通过任务核对。过期/窗口跳过必须有可靠列表日期；`skipped_closed` 只能用于详情明确回报“已下架”的目录行。都要保留简略记录和证据；缺少日期时首次读取详情，之后可按 SPEC-009 的可靠历史复用，不把未知日期当成旧日期。
- `terminal` 依据源总数、明确末页或穷尽游标。重复页、数量变化、目录未知均保持 partial。
- `source_key` 包含岗位 ID 及必要的单位/批次；禁止按标题去重。详情参数来自对应列表行，并核验身份，不能沿用样本的单位 ID。
- 没有抓到元素不等于零岗位；源站明确显示零且目录核对完成才是 complete。

## 字段规则

- `company` 为名录企业，`unit` 保存实际招聘子单位；后台公司名可在绑定配置中覆盖。
- `published`、`deadline` 保留源值与字段路径。不得用更新时间、毕业时间或采集时间代替发布日期。缺失为空，“招满即止”等非空未知值保留原文并待核验。
- 职责与要求分开，公告通用要求追加时标明来源。附件未解析属于未完成任务，不能丢弃附件岗位后称完整。
- `category_raw` 保存原类别；模板分类由明确配置或有引证的模型输出产生，不能为整家公司固定某类别。
- 不将“不限”填为本科，不随意缩减多城市；多学历按 SPEC-007 的最低可报名策略与配置处理。
- 没有投递链接时可保留详情入口；不得调用投递、注册、收藏等修改用户数据的接口。

## 证据、会话和模型

Job 附带 `evidence` 与关键字段 `field_sources`。仅提交最小脱敏回放样本，不提交 Cookie、token、会话、完整日志或大批量结果。

适配器提供原始岗位和字段证据，默认 run 通过公共 delivery 流程自动执行分类、规则无法确定的学历辅助与最终导出。LLM 统一使用 `Classifier`/`Enricher`/`LLMConfig`，默认启用 `deepseek-flash`，key 来自环境。不得在适配器中重复补全或绕过共用预算、缓存、枚举和引证校验。模型不决定采集覆盖，不在运行过程中改写适配器；具体契约见 SPEC-010。

目前已验收企业的接入范围均为公开目录，尚未实现授权登录会话导入。新站确需登录时先补充会话生命周期 spec；没有会话就报告 blocked。仅投递需要登录时继续采集公开岗位。

每日优化使用公共 `IncrementalSource`，由 runner 注入。详情请求前调用 `before_detail`，返回 None 才需要读详情；成功核对后 `remember` 保存列表指纹与完整岗位，公告允许一对多。详情入口页面应延迟到确实需要请求时打开；并发时保存本页列表证据，不能把其他岗位详情当成列表依据。只有确认源字段是发布时间才传入预筛选记录。列表直接包含全文的适配器不需要额外读详情，由 runner 记录首次发现。失败不推进历史、身份隔离和全量强制刷新均须回放测试，不能只测缓存命中。

北森新版可复用 `adapters/zhiye.py`，但必须逐租户确认 Category=2、无局部筛选的入口、GetJobAdInfo 详情与 GUID 关联。只有真实全量验收后才启用绑定；不能把该平台的旧版站点或仅有静态首页的入口直接登记为已支持。`scripts/probe_sites.py` 用于有限探测，`scripts/collect_batch.py` 是历史开发脚本，其内置平台候选和输出目录内状态库设计不宜直接套用到新批次归档；优先使用 skill 中将输出与状态库分开的 CLI/SDK 调用。使用 `job-crawler bundle` 合并已保存结果，不要为了输出一份总表重复采集。

Hotjob `pb/school.html` 租户可参考 `adapters/hotjob.py`。新租户仍须先观察 `listPosition` 的原始表单，确认 `recruitType=1`、第一页无局部筛选、`dataCount` 与末页，再核对 `listPositionDetail` 的 `postId`。表单请求走同一 Crawl4AI 浏览器会话，不能把 JSON POST 直接套用。`publishFirstDate` 是首次发布时间；页面的“更新日期”对应 `publishDate`，不能拿来做每日新发布筛选。部分租户将职责和资格放在同一正文，只有明确小标题时拆分；源站未给资格则留空并报告。`mc/position/campus` 移动入口不能未经验证复用 `pb` 的路径和表单。

Moka `campus-recruitment` 与 `campus_apply` 的已验收单站点租户可参考 `adapters/moka.py` 和 SPEC-013。该平台公开页面在 `window.TurboApply.data.aesIv` 给出本页响应 IV，接口通过响应中的 `necromancer` 解码；不要复用另一轮保存的 IV、密钥或已解码目录。先直接访问该租户的 `#/jobs`，确认 `website/jobs/v2` 是同组织/同 siteId 的无筛选目录，`jobStats.total` 与每页岗位数一致，再核对 `website/job` 详情 ID。观察接口时按完整 URL 路径精确匹配；`/website/jobs/v2/filterFieldsAggregations` 不是职位列表。`publishedAt` 是发布时间，`updatedAt` 只是更新；移动链接仅在核对公开跳转后的同租户目录时复用，跨多个 siteId 的首页门户必须另做范围设计。即使租户同属 Moka，也不能只因域名相同就启用绑定。

前程无忧 `campus.51job.com` 的活动页通常按企业定制。参考 `adapters/wtmec.py`、`adapters/hzsteel.py` 和 `adapters/ansteel.py` 处理三类已验收页面；新活动页必须重新检查实际导航、招聘企业选项、岗位卡片与占位元素、分页或弹窗、申请 ID 以及公开日期，不套用同域名的选择器。鞍钢默认只显示一个招聘企业，必须逐选项点击并保存各选项证据才能报告整个集团的覆盖。若页面没有发布/截止日期或某项岗位字段，保留空值和字段来源说明。公开申请链接进入登录页不阻止采集公开岗位正文，也不能据此推断投递状态。

第二批前程无忧活动页见 `adapters/campaign51.py` 与 SPEC-017：蓝思把全量岗位放在页面 `obj`，首屏只渲染一个地区，其中「智能机器人公司」是单位而非地名；中国燃气在 `jobListData` 提供全目录，但脚本变量不一定是 `window` 属性，必须核对数组与页面卡片及申请 ID；天津银行城市切换时申请 ID 不同，必须同时遍历热招和专项两个分支。页面脚本或静态卡片的完整正文可以直接采集，不必向投递入口发送申请请求。活动页年份或可打开状态不足以证明逐岗位仍可投递。

第三批扩展见 SPEC-019 至 SPEC-032 和 `docs/adapter-batch3-acceptance.md`。51job COAPI 活动页必须按企业验证 `ctmid`、无筛选页上限、页面实际显示规则与详情关联。美团小页动态排序会重复岗位，本次以站点接受的 200 条单页读取；未来总数超出上限时仍要检测重复和遗漏。哔哩哔哩站点翻页要求页面自带会话头，适配器点击官方分页控件并记录响应，不复制或硬编码会话令牌。腾讯目录可能含已下架详情，只有明确的 404“岗位已下架”才计入 `skipped_closed`。

## 测试与交付

| 范围 | 要求 |
| --- | --- |
| 列表 | 首/次/末页、零结果、重复页、源总数变化 |
| 层级 | 多批次/单位；其他分支失败不被成功分支掩盖 |
| 详情 | 参数关联、部分失败、公告展开、复合 ID |
| 日期 | 日粒度、未知发布、当天截止、精确时刻、未来/无效日期 |
| 导出 | 13 列、分类路径、未知枚举、待补全、超长文本、公式安全、保持日/周/月窗口 |
| 执行 | 有限重试、预算、恢复失配、错误退出码 |
| 真实验收 | 命令、时刻、范围、数量、证据和障碍；历史样本不能冒充实时结果 |

执行 `uv run ruff format --check .`、`uv run ruff check .`、`uv run ty check`、`uv run pytest`。若需要改变公共契约，先更新 spec、版本与受影响回放。

交付包含平台 spec、代码/版本、来源绑定、回放/测试、验收记录、程序生成的结果路径与尚未解决障碍。访问受限或业务配置缺失时明确标记，不能宣称整站完整交付。

## 本批新增协议参考（SPEC-042～046）

完整实例见 [50 家交付验收](adapter-batch6-acceptance.md) 与 `tests/test_batch6_contracts.py`。不能仅按域名后缀批量绑定：同一个 HCM 的字段标签可以不同，Moka 列表 deptId 不一定等于公开法人 department.id，校招项目也可能夹杂社招或实习。

- `inline_catalogs.py` / `sinopharm.py`：先验证项目集合、无局部筛选、招聘类型和明确分页终态；列表已有完整正文就不另请求详情。
- `chinatower.py`：公开虚拟表格需读取整页模型，并等待模型页码、分页控件、记录数同步；只保留公开岗位字段。字段元数据决定日期和学历语义。
- `nci.py` / `static_campus.py` / `bank_catalogs.py`：DOM内嵌正文、动态滚动分页、旧GBK网页；不能把CSS省略标题、不可见“没有更多”文本或乱码当完整结果。
- `anker.py` / `haier.py`：列表身份关联公开详情，调用公共增量钩子；多法人门户按明确的源主体字段过滤。
- `BrowserSession.request(..., credentials="omit")` 只用于已观察的公开无登录跨域API；默认仍为include。`request_html(..., encoding="gb18030")` 仅用于源页面明确声明GBK的站点。请求模式和编码参与缓存键，不能跨模式复用证据。跨域ready_endpoints必须为完整HTTPS URL。

采集验收为complete且有效岗位大于零，才能计入“有岗位企业”交付数量。无日期、无职责或地点未映射的岗位可保留信息表，但必须同时保留待补全原因和严格导入表，不为达成数量填造字段。
