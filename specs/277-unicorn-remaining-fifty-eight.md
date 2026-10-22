# SPEC-277 独角兽来源第二批 50 家接入与当日岗位汇总

状态：2026-10-22 最终验收 50/50 家；累计 1,721 条有效岗位、414 条严格导入。用户将当日目标从 58 家调整为累计 50 家，并允许从其他待接入企业补足；前一轮 17 家验收见 `docs/unicorn-remaining-58-acceptance.md`，本轮累计验收见 `docs/unicorn-total-50-acceptance.md`。

## 目标与非目标

在 2026-10-22 累计新增并真实验收 50 家不同企业，将本批实采的仍展示、未截止正式校招岗位汇总为当日信息表和严格导入表。原始独角兽调查表的 108 个入口仅有 30 个包含在 SPEC-276 已验收的 50 家中，最初候选为其余 78 家；用户先将目标从 58 家调整为累计 50 家，随后明确允许从其他待接入企业补足。因此优先尝试原始候选，缺额可从批次开始尚未绑定的 `sites/sources.csv` 企业选取，仍须按同一验收条件逐家验证。

不将 SPEC-276 的旧企业、同一企业的别名或不同入口、只在平台挂名未完成实采、零岗位、仅实习或社会招聘的来源计入 50 家。不以昨日快照冒充当日采集，不自动注册、投递或破解验证码。

## 输入与输出

- 输入：`sites/sources.csv`、`sites/bindings.toml` 的批次开始状态、`docs/unicorn-2026-recruitment-research.md` 的原始入口，以及其他待接入企业逐站可核验的公开页面和接口证据。
- 纳入范围：各来源明确标注的正式校园招聘目录，逐站验证主体、招聘类型、批次、分页与详情身份。来源的公布日期、截止日期和状态按源语义保存；缺失字段不推断。
- 输出：更新的站点契约与适配器、版本化正式绑定、回放测试、逐站实采验收台账、由程序生成并发布在 `outputs/2026-10-22/` 的本批岗位信息表及严格导入表，运行报告与证据归档在 `.runtime/`。

## 失败行为

访问失败、登录或反爬、范围不明、分页/详情缺失、源计数不一致、只有社招/实习、或者当日公开目录零岗位时，保留证据与原因，不启用绑定，不计入 50 家。局部采集保留已成功记录但 coverage 为 partial/blocked。学历、地点、详细地址、分类、发布日期无法确定时留空并进入待补全，不为满足模板虚构。

## 可验证验收条件

1. 保存批次开始的已绑定企业集合、原始 78 个待接入入口及新增候选清单，确认最终计数是新增的不同 `company_id`，每家有本批 `coverage=complete` 且有效岗位大于零。
2. 每个接入来源有可复核的官方入口、主体与校招范围；列表源总数、首/次/末页、唯一身份、详情关联、日期语义和结束依据得到真实站点验证。同平台不同租户单独核对。
3. 新协议的离线测试覆盖本站真实风险，如分页末端、重复页、混合招聘类型、详情错配、局部失败或日期边界；对已有平台的必要修改运行受影响回归。
4. 只用本批通过验收的完整快照执行 `bundle`，`audit_delivery.py --expected-companies` 使用实际验收家数核对不同企业数、来源计数、两份工作簿及日期列，随后 `archive --publish`。实际家数不足 50 时保留缺口并明确报告，不将审计通过解释为数量目标达成。报告分别记录有效、信息表、严格导入、待补全数量和每来源实采时刻。
5. `uv sync --locked`、Ruff format/check、ty、pytest 通过；spec、实现与验收记录提交到功能分支，并按本地 Git 工作流合并。

## 需求到验证对应

| 需求 | 验证依据 |
| --- | --- |
| 只计本批新增不同企业 | 批次开始基线、逐站验收台账、`audit_delivery.py` 企业 ID 校验 |
| 完整校招目录和可靠字段 | 站点证据、Scope 计数、平台回放、真实全范围快照 |
| 当日汇总与导入约束 | `bundle` manifest、信息与严格表、待补全报告、只读审计 |
| 可重跑交付与归档 | 正式绑定、README 步骤、归档索引与发布路径 |

## 首批已观察站点契约（2026-10-22）

- COM0519 大疆：官网校园页明确链接 `apply.careers.dji.com/campus-recruitment/dji/143359`。该白标 Moka 校园门户的 `/api/outer/ats-apply/website/jobs/v2` 无筛选首屏请求为 `orgId=dji,siteId=143359,site=campus,offset=0,limit=30`，UI 显示 142 条结果。需按当前页面公开 IV 解码逐页核对总数、ID 与详情，按源性质排除实习，并保留栏目中跨项目条目的原文。
- COM0525 货拉拉：官网“校园招聘”链接 `app.mokahr.com/campus-recruitment/huolalahr/98660`。同类接口无筛选首屏请求为 `orgId=huolalahr,siteId=98660,site=campus,offset=0,limit=30`，UI 显示 57 条，性质筛选含全职、兼职、实习、其他；全量遍历后只纳入有效正式校招。不能因同集团其他北森门户存在就混合岗位。
- COM0580 平凯星辰：官网指向 `campus.pingcap.com/campus_apply/pingcap/39951`；当前校园职位页只显示 1 条“商务运营实习生”，不计有岗位企业，后续若新增正式岗位再复核。
- COM0505 微众银行：公开校园 Moka 门户仍显示“岗位更新中”；COM0625 千寻位置校园页目前为 2025 校招旧职位。两者均不据当前页面计数。
- COM0571 莉莉丝：官网链接 `lilithgames.jobs.feishu.cn/campus`，其无筛选公开飞书接口 `/api/v1/search/job/posts` 使用 `portal_type=6,offset=0,limit=10`，首屏总数 19；源招聘类型为正式、标题标 2027 秋招。须按站点签名翻至末页、核对 19 个 ID 与项目/性质。
- COM0574 蓝箭航天：官网链接 `uq1h428xyc.jobs.feishu.cn/522146/position/list`，同类接口无筛选首屏总数 74，含“可实习”标题，项目显示 2027 届校园招聘。须核对全部页与源类型，标题含实习者排除正式校招。
- COM0659 沃飞长空：官网招聘页明确链接 `app.mokahr.com/campus-recruitment/geely/94419`。虽然 Moka `orgId=geely`，该独立站点表面为沃飞长空招聘，职位所属部门和航空器岗位与官网一致；无筛选 `site=campus,offset=0,limit=30` 首屏显示 32 条。须以站点 94419 为边界逐页核对，不能抓取吉利其他站点并归入沃飞长空。
- COM0612 中关村科金：官网“校园招聘”直达飞书 `weikezhijia.jobs.feishu.cn/952383/position/list`，公开无筛选 `portal_type=6,offset=0,limit=10` 首屏返回 26 条；多条标题为“27届校招/应届生”，源招聘类型、项目字段为空。须以官网专属校园入口和所有 26 个 ID 佐证范围，不凭空补写缺失的源类型。
- COM0617 高仙机器人：官网链接 Hotjob 租户 `SU6629d2ce1eb8053acd8065ac`，`/pb/school.html` 的无筛选 `recruitType=1,pageSize=12,currentPage=1` 返回 42 条、4 页，列表公司为“上海高仙自动化科技发展股份有限公司”。`publishFirstDate` 为首次发布时间，`publishDate` 为更新日，`endDate=3000-01-01` 为无截止占位值；须逐页、逐详情核对同一 `postId`、主体和岗位性质。
- COM0729 此芯科技：官网校园链接 `cixin.zhiye.com/campus/jobs`，公开北森 `Category=["2"]` 无筛选首屏返回 21 条；列表包含稳定 `Id`、完整 `Duty/Require`、源发布日期与性质。须核对全 21 条与末页，排除实习性质或标题。
- COM0694 联影智能：其官网校园链接进入 `united-imaging.zhiye.com` 集团站，当前 Category=2 目录 139 条却没有逐岗法人名称。不能把集团全部岗位直接归给联影智能；需找到可证实的单位筛选或独立子公司站点再接入。
- COM0506 小红书：官方校园页 `job.xiaohongshu.com/campus/position` 的 2027 校招目录无关键词筛选，`/websiterecruit/position/pageQueryPosition` 请求指定 `recruitType=campus,jobProjects=[campus_autumn_27],pageNum=1,pageSize=10`；首屏返回 166 条、17 页。列表带稳定 `positionId`、公开状态、完整职责/资格、发布日期，详情链接为 `/campus/position/{positionId}`。需检查每页总数、页码、去重、招聘项目、公开状态和正文完整性；源日期只用 `publishTime`，实习栏目不得混入。
- COM0508 荣耀：官网“应届生”链接 `career.honor.com/SU60eea919bef57c1023f6fe78/pb/school.html`，Hotjob 无筛选 `recruitType=1,pageSize=15,currentPage=1` 首屏返回 101 条、7 页；列表项目为“2027届应届本硕”，源 `publishFirstDate` 为首次发布日期、`publishDate` 为更新日。需核对全页项目和稳定 `postId`，逐岗详情身份及工作地点、截止日；不依据投递需登录时的 `canDelivery` 假值误判为岗位已关闭。
- COM0608 依图科技：官网“校园招聘”指向 `/cn/career?mode=campus`，页面显示 4 条，公开 `api.mokahr.com/v1/jobs/yitu-inc?mode=campus&limit=1000&offset=0` 返回 `total=5`，其中两条为实习；正式 2027 校招 3 条。接口含完整 HTML 正文、稳定 ID、`publishedAt`、状态、性质和工作地点；须按总数遍历并按标题与性质排除实习，不以更新日替代发布时间。页面显示与接口总数差异需在验收记录中注明。
- COM0509 米哈游：官网校招入口跳转 `jobs.mihoyo.com/#/campus/position`；无项目筛选时公开 `ats.openout.mihoyo.com/ats-portal/v1/job/list` 返回 271 条，其中项目 `13=2027届秋招` 的筛选请求 `jobName="",projectIds=["13"],channelDetailIds=[1],hireType=1,pageNo=1,pageSize=10` 返回 129 条。逐岗公开路由 `#/campus/position/{id}` 展示职位标题、职责、任职要求和面向对象；接口列表无源发布日期，须留空，不用观察时间代替。需核对项目计数、13 页完整分页、每岗详情 URL 与标题/面向对象一致；详情失效则 coverage 部分完成，不计有岗位企业。
- COM0594 辰瑞光学：官网人才招募页 `aacoptics.com/?page_id=1517` 的 WordPress 招聘插件当前完整渲染 12 个 `.aol-ad-inner-wrapper` 职位卡，无分页控件；其中两个卡片在 `panel-footer` 明确标为“招聘渠道: 校园招聘”，其余为社招或未标性质。各卡片有稳定 `aol_ad_{id}`、职位详情链接、职责与资格全文；须对 12 卡逐条计数，只纳入明确校园招聘的两条，发布日期留空，分页控件或卡片结构变化则不标完整。
- COM0535 万得：官网“校招入口”链接 `www.wind.com.cn/mobile/JoinUS/RecruitDetail/zh.html?entry=school`，服务端页面 `__NEXT_DATA__.props.pageProps.locale.channelPositions` 当前含 111 条公开岗位，其中 `Projects[].Name=2027年校园招聘` 的 16 条为项目候选，另有实习与社招。逐条校验 `ChannelPositionID`、`PositionTypeText=校招`、`InUse=true`、`ExpireFlag=false`、完整职责/要求、源 `PublishDate`、地点与项目；发布日期可早于 2027 项目，必须按源原值保存，不按批次改写。SSR 目录无分页；若 `channelPositions` 消失或结构改变，保留失败而不宣称空目录成功。
- COM0507 OPPO：官网校园页的独立职位列表 `careers.oppo.com/university/oppo/campus/post` 当前显示 243 个在招岗位。公开 `/openapi/position/project/list` 给出 2027 寻梦实习 `29`、2027 应届校招 `30`、2027 博士生招聘 `31`；无筛选 `/openapi/position/pageNew` 请求 `pageNum=1,pageSize=10,positionName="",projectList=[],positionTypeList=[],workCityCodeList=[],shareId=""` 返回 243 条、25 页。列表有稳定 `idRecruitPosition`、项目 ID/性质、公开状态、职责、资格与 `releaseTime`；详情路由为 `/university/oppo/campus/post/{id}?recruitType=Graduate`。须逐页核对总数与项目、排除项目 29 实习，按项目 30/31 保留正式校招，正文缺字段如实报告。
- COM0666 开沃汽车：官网“校园招聘”进入 `www.skywellcorp.com/website/skywellcorp/recruitment?tab=2`，公开 `/api/recruit/list` 无部门、城市、关键词筛选，`type="2",langType=1,pageNo=1,pageSize=10` 返回 44 条、5 页，逐岗含稳定 `id`、类型、状态、职责、要求、学历及地点。UI 显示的 `updateTime` 是更新日期，`createTime` 是后台创建时间，均不等同源发布日期；岗位 `published` 留空，不能把 2025 年更新日当发布日。须核对 44 条 ID、完整分页、类型=2、公开状态=1；如站点只有旧岗位，也如实标注更新时间，不伪称新发。
- COM0558 多益网络：官网“招聘职位”进入 `sz.duoyi.com/v40/#/positions?recruit=10`，无职位类别筛选的公开 `/v40/api/index/positions/jds/page?pageIndex=1&pageSize=15&recruit=10` 首屏返回 34 条。列表含稳定 `id`、`category=SCHOOL`、`outerNature` 正式/实习、完整 `jobResponsibility`/`jobRequirements`、`publishDate` 和地点。须以无 `outerTypeId` 的 34 条目录遍历末页，只纳入 `outerNature=[正式]`，排除实习；`canDelivery=false` 在未登录时不直接解释为已关闭。
- COM0511 Vivo：官网“校园招聘”明确链接 `hr-campus.vivo.com/campus/jobs`。该独立北森租户公开 `/api/Jobad/GetJobAdPageList` 首屏请求为 `PageIndex=0,PageSize=20,Category=["2"],KeyWords="",SpecialType=0,PortalId=""`，返回 `Count=36`，职位名称标有“27届秋招/蓝极星”，`CategoryId=2`，列表包含稳定 `Id`、职责、任职要求和地点。`PostDate=0001-01-01`、`EndTime=0001-01-01` 为源占位，应留空。需核对完整分页、逐条 2027 届和正式岗位性质；如目录混入其他届、实习或主体，不能直接全收。
- COM0784 微店：官网招聘门户的独立 `hr.weidian.com/campus/jobs` 页面明示“2027届校园招聘”。公开北森 `Category=["2"],PageIndex=0,PageSize=20` 无关键词及地点筛选目录返回 `Count=9`，其中 6 条 `Kind=全职`、3 条 `Kind=实习`；列表带完整职责/要求、稳定 `Id`、发布日期与地点。需验证 9 条源计数及末端，仅纳入 2027 正式全职，源无截止日期留空。
- COM0530 正泰安能：公司官网招聘入口指向正泰集团独立 Moka 校园站 `campus.chint.com/campus-recruitment/chint/40745/`。官网“按公司投递”展示“正泰安能数字能源（浙江）股份有限公司”独立节点 `departmentId=725411`、46 条；点击后路由 `#/jobs?department%5B0%5D=725411`，公开 `website/jobs/v2` 请求含 `site=campus,orgId=chint,siteId=40745,departmentIds=["725411"],offset=0,limit=30`。需以该节点为限定、核对两页 46 个 ID、逐岗所属部门/主体及详情一致性；不得收取正泰集团其他法人岗位。
- COM0376 中国旭阳集团：名录校园入口 `risun.zhiye.com/campus/jobs` 的北森公开目录首屏显示 65 条，但列表 `Org` 为空且集团包含不同主体；其中大量为 2023–2024 年旧岗位。已有 `docs/remaining-271-acceptance.md` 指出主体混同风险。本批不把这 65 条整体归给名录主体，须有逐岗法人依据后才能启用。
- COM0319 苏宁易购：官网 `careers.suning.cn/graduates/` 的一条“租赁经理”详情所属苏宁置业，不能归入上市主体。官网“校园招聘”实际跳转 `campus.suning.cn/rps-campus/`，其“1200招聘”无地点筛选页 `/rps-campus/ftl/campus/managePlan.htm?type=manage` 当前按类别展示 11 个 `post-link`，每条携带唯一 `poId`，详情 `/managePositionDetail.htm?poId=...` 明列全职、职责、任职要求、学历与地点。需验证全部 11 个 ID 与详情标题一致、页面无未处理分页或筛选、岗位均属于苏宁易购校园项目；没有源发布日期时留空。
- COM0575 KK集团：官网 `/zh-CN/join` 的“校园招聘”按钮直接打开 `kkguan.zhiye.com/campus/jobs`，独立北森 `Category=["2"]` 无关键词/地点筛选目录 9 条，全部标题明确“27...管培生”，列表带稳定 ID、职责/要求、源发布日期及地点。`Kind`、`Org` 为空，租户和官网指向提供集团身份，单位可用“KK集团”回退；须核对全部 9 条的项目标题、Category、正文和唯一 ID，源 `EndTime=0001` 留空。
