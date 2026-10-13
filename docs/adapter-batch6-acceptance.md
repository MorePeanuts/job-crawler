# 五十家有实际岗位企业交付验收（2026-10-13）

对应 SPEC-042～046。所有采集、字段处理及 Excel 导出均由项目代码完成；未手工补岗位，未注册、登录、投递或绕过验证码。

## 交付口径

本日原 24 个完整来源中只有 19 家有有效岗位（6,645 条）；5 家零岗位不计入交付家数。本轮继续修复原 26 家中的 4 家，并从同一名录补充 27 家，共新增 31 家有有效岗位企业、4,531 条岗位。最终合并 **50 家企业、11,176 条有效校招岗位**。

原始采集 12,420 条，排除过期、关闭、实习/社招及不属于目标主体的记录后保留 11,176 条。50 个来源的声明范围均 coverage=complete，且各有有效岗位；不将“采集覆盖完成”混同“所有字段满足后台导入约束”。

- 主表：`outputs/batch6-20261013-final/岗位信息汇总.xlsx`，岗位信息 11,176 行、13 列；企业采集情况 50 行。
- 严格导入表：同目录 `jobs.xlsx`，2,160 条；其余 9,016 条在 `review.json`。主要问题是尚未配置后台地点映射（9,003 条涉及，原因可重叠），另有源站缺学历等情况。不会以猜填地址或学历凑导入行数。
- 截止时间非空 2,301 条，发布时间非空 7,672 条；两列均为 YYYY-MM-DD，未知留空。
- 输入清单：`outputs/batch6-fifty-inputs.json`；来源审计：`outputs/batch6-fifty-source-audit.json`；结果 `manifest.json.origins` 保留各站当日真实采集时刻。汇总时间不充当采集时间。
- 本轮汇总使用 deepseek-flash，缓存命中 13,349 次，新增模型调用 37 次（分类/复核/必要学历处理），复用已有正文与分类，无需再次全网采集。

## 新增或修复来源

| 来源 | 名录企业 | 适配器 | 采集记录 | 有效校招 | 原始运行目录 |
| --- | --- | --- | ---: | ---: | --- |
| COM0032 | 厦门建发集团有限公司 | `cnd-campus@1` | 7 | 7 | `outputs/batch6-inline-fixed/COM0032` |
| COM0037 | 中国医药集团有限公司 | `sinopharm-campus@1` | 628 | 619 | `outputs/batch6-finish-live/COM0037` |
| COM0041 | 物产中大集团股份有限公司 | `moka-wzgroup@1` | 108 | 107 | `outputs/batch6-platform-live/COM0041` |
| COM0057 | 美的集团股份有限公司 | `midea-campus@1` | 216 | 216 | `outputs/batch6-inline-live/COM0057` |
| COM0078 | 紫金矿业集团股份有限公司 | `moka-zijin@1` | 25 | 25 | `outputs/batch6-platform2-fixed/COM0078` |
| COM0086 | 海尔智家股份有限公司 | `haier-campus@1` | 167 | 84 | `outputs/batch6-final-verified/COM0086` |
| COM0097 | 北京汽车集团有限公司 | `zhiye-baic@1` | 426 | 426 | `outputs/batch6-recheck-live/COM0097` |
| COM0098 | 新华人寿保险股份有限公司 | `nci-campus-html@1` | 218 | 218 | `outputs/batch6-custom-live/COM0098` |
| COM0135 | 洛阳栾川钼业集团股份有限公司 | `hotjob-cmoc@1` | 25 | 22 | `outputs/batch6-recheck-live/COM0135` |
| COM0167 | 碧桂园控股有限公司 | `hotjob-countrygarden@1` | 8 | 8 | `outputs/batch6-first-live/COM0167` |
| COM0174 | 快手科技 | `kuaishou-campus@1` | 279 | 279 | `outputs/batch6-inline-fixed/COM0174` |
| COM0179 | 中兴通讯股份有限公司 | `moka-zte@1` | 101 | 57 | `outputs/batch6-platform2-fixed/COM0179` |
| COM0187 | 浙商银行股份有限公司 | `czbank-campus@1` | 90 | 90 | `outputs/batch6-final-verified/COM0187` |
| COM0196 | 唯品会控股有限公司 | `moka-vipshop@1` | 38 | 35 | `outputs/batch6-platform-live/COM0196` |
| COM0203 | 中国铁塔股份有限公司 | `chinatower-campus@1` | 199 | 199 | `outputs/batch6-tower-fixed/COM0203` |
| COM0269 | 金发科技股份有限公司 | `kingfa-campus@1` | 113 | 113 | `outputs/batch6-recheck-live/COM0269` |
| COM0274 | 欣旺达电子股份有限公司 | `sunwoda-campus@1` | 484 | 484 | `outputs/batch6-custom-live/COM0274` |
| COM0279 | 宁波均胜电子股份有限公司 | `moka-joyson@1` | 129 | 50 | `outputs/batch6-first-live/COM0279` |
| COM0294 | 天能动力国际有限公司 | `tianneng-campus@1` | 37 | 37 | `outputs/batch6-finish-live/COM0294` |
| COM0302 | 农夫山泉股份有限公司 | `moka-nongfu@1` | 36 | 26 | `outputs/batch6-finish-live/COM0302` |
| COM0331 | 安徽江淮汽车集团股份有限公司 | `jac-campus@1` | 544 | 544 | `outputs/batch6-last-live/COM0331` |
| COM0336 | 哈尔滨电气股份有限公司 | `zhaopin-hadian@1` | 125 | 125 | `outputs/batch6-finish-live/COM0336` |
| COM0351 | 浙江正凯集团有限公司 | `zhink-campus@1` | 21 | 21 | `outputs/batch6-extra-live/COM0351` |
| COM0366 | 云南白药集团股份有限公司 | `hotjob-baiyao@1` | 80 | 77 | `outputs/batch6-platform2-fixed/COM0366` |
| COM0367 | 中国国际金融股份有限公司 | `zhiye-cicc@1` | 104 | 104 | `outputs/batch6-recheck-live/COM0367` |
| COM0375 | 北方华创科技集团股份有限公司 | `zhiye-naura@1` | 40 | 36 | `outputs/batch6-recheck-live/COM0375` |
| COM0385 | 中国银河证券股份有限公司 | `zhiye-chinastock@1` | 72 | 72 | `outputs/batch6-first-live/COM0385` |
| COM0424 | 哈尔滨银行股份有限公司 | `hrbb-campus@1` | 58 | 58 | `outputs/batch6-finish-live/COM0424` |
| COM0428 | 浙江大华技术股份有限公司 | `zhiye-dahua@1` | 143 | 142 | `outputs/batch6-platform2-fixed/COM0428` |
| COM0445 | 安克创新科技股份有限公司 | `anker-campus@1` | 496 | 243 | `outputs/batch6-cross-live/COM0445` |
| COM0464 | 广东生益科技股份有限公司 | `syst-campus@1` | 7 | 7 | `outputs/batch6-banks-fixed/COM0464` |

原 26 家修复成功：COM0203 中国铁塔、COM0274 欣旺达、COM0367 中金、COM0385 银河。其余新增来源为补充企业，没有将同一集团的子公司拆成多个企业凑数。

## 范围与字段限制

- 欣旺达同时完成本硕和博士两目录；唯品会同时检查两校园门户并按源 ID 去重，排除实习。美的枚举正式应届项目；快手为官网应届入口当前指向的 2027 项目。
- 农夫山泉的列表只有内部 deptId，详情才返回可核对的法人 department；仅详情 department.id=1867931 且名称匹配才纳入，其余养生堂主体排除。
- 海尔名录主体为海尔智家：遍历集团全部 5 个应届项目后，根据详情当前招聘产业的明确主体介绍排除其他法人，最终 84 条；未把集团目录 167 条全归到海尔智家。
- 建发是名录校园入口公开的建发股份目录；天能是所给官网的校园目录，表中公司名称沿用名录。哈电是官方当前 2027 智联活动全目录。每个适配器 scope_description 记录入口边界，不宣称穷尽互联网上所有子公司网站。
- 哈尔滨银行为当前主校园门户 58 条；官方公告另提及哈银消费金融独立域名，但此次独立入口未能取得可验证岗位列表，不纳入这 58 条，不声称覆盖该独立门户。
- 生益官网岗位卡只有专业/学历/地点，没有职责正文；天能部分岗位卡正文为空且外部投递系统本次未返回可用页面。信息表保留已知字段并进入待补全，不虚构职责。
- 江汽 status=招聘中用于判断岗位状态；is_open 的源语义是“是否公开”，不能误判下架。江汽自动下线时间不当报名截止；铁塔同字段的页面标签明确是“职位申请结束时间”，可作为截止。
- 国药项目夹杂少量社招，按每条实际招聘类型排除；安克正式招聘和实习按源字段区分，create_time/modify_time 不作为发布时间。
- 浙商银行共 9 页、90 条，动态页学历没有第一页的CSS类；详情声明 GBK，必须按 gb18030 解码，不能将乱码误判为缺失信息。

## 原 26 家剩余情况

以下 22 家仍未绑定，不进入今日 50 家交付。它们有的是暂时无在招数据，有的是旧入口失效或目录尚不可验证；不能据此认定永久无法爬取。探索证据在 `outputs/batch6-initial-probes/`、`batch6-follow-probes/`、`batch6-extra-probes/` 等对应来源目录，结果不是历史岗位回填。

| 来源 | 本次障碍 |
| --- | --- |
| COM0004 中国建筑集团有限公司 | 公开 HCM 门户可以打开，但所观察目录返回 0，尚未验证有效校招组织范围。 |
| COM0005 鸿海精密工业股份有限公司 | 旧 Hotjob 校园活动本次明确无数据，无法据此还原新的在招批次。 |
| COM0011 中国银行股份有限公司 | 官方招聘公告指向的 Chinahr 目录仍空白/重定向，缺可用职位响应。 |
| COM0025 山东能源集团有限公司 | 原 51job 活动跳转通用站点，当前校招全目录入口未验证。 |
| COM0034 中国邮政集团有限公司 | 智联活动页访问受限/空白，未绕过限制。 |
| COM0183 广东海大集团股份有限公司 | 名录旧 51job 活动跳转通用页面，未取得当前校园全目录。 |
| COM0192 中天科技集团有限公司 | 旧移动活动受访问限制，岗位列表与详情未通过验证。 |
| COM0220 越秀地产股份有限公司 | 智联入口 HTTP 403。 |
| COM0234 康师傅控股有限公司 | 所给 2026 活动目录为 0；没有用搜索索引旧岗位补表。 |
| COM0308 广东领益智造股份有限公司 | 原招聘官网明确已关闭。 |
| COM0313 中原银行股份有限公司 | 北森入口错误页面/404，缺当前公开目录。 |
| COM0337 无锡药明康德新药开发股份有限公司 | 入口明确显示企业已暂停招聘。 |
| COM0360 上海龙旗科技股份有限公司 | 静态活动只有招聘大类和统一申请入口，未取得逐岗位完整目录。 |
| COM0362 宇通客车股份有限公司 | MC 校园目录为 0；博士导航尚未形成可验收的完整范围，保留待核验。 |
| COM0379 鹏鼎控股(深圳)股份有限公司 | 旧北森首页和校招导航可见，但校园列表未提供可验证数据。 |
| COM0402 成都农村商业银行股份有限公司 | 智联入口空白/受限，缺完整列表证据。 |
| COM0448 北京首都开发股份有限公司 | 旧 2026 活动访问受限，当前校招范围未验证。 |
| COM0453 李宁有限公司 | 旧 2026 活动只有导航/页脚，缺职位正文。 |
| COM0454 宁波拓普集团股份有限公司 | 所给活动校招列表为 0，未证明涵盖当前新批次。 |
| COM0482 青岛银行股份有限公司 | 旧 2026 活动显示暂无数据，未取得新批次全目录。 |
| COM0485 贵阳银行股份有限公司 | 旧活动仅页脚，缺校园目录。 |
| COM0500 东方证券股份有限公司 | 当前公开 Moka 门户展示日常实习/社招，不能替代正式校招。 |

## 入口变更追溯

这些是代码探测原入口跳转、页面校招导航或官网当期公告后确认的新入口。完整旧地址保留于 Git 历史；原始探测快照保留页面链接。

| 来源 | 原入口 | 已验证入口 |
| --- | --- | --- |
| COM0037 | `https://sinopharm2027.iguopin.com/notice` | `https://sinopharm2027.iguopin.com/job` |
| COM0078 | `https://www.zjky.cn/join/campus-recruitment.htm` | `https://join.zjky.cn/campus-recruitment/zijinmining/117957/#/jobs` |
| COM0086 | `https://maker.haier.net/client/campus/index` | `https://maker.haier.net/client/campus/activityindex.html` |
| COM0097 | `https://baicgroup.kongxuan.com/` | `https://baicgroup.zhiye.com/campus/jobs` |
| COM0098 | `https://nci.zhiye.com/sxszp?class=3` | `https://nci.zhiye.com/xyzp?class=2` |
| COM0135 | `https://www.cmoc.com/html/CareerDevelopment/CampusRecruitment/` | `https://wecruit.hotjob.cn/SU67e513c01c240e188726a2e9/pb/school.html` |
| COM0167 | `https://zhaopin.bgy.com.cn/campus` | `https://wecruit.hotjob.cn/SU5fe5ad319b0d78e6f422f6f8/pb/school.html` |
| COM0179 | `https://job.zte.com.cn/cn/campus-recruitment/School_Recruitment_Announcement/news/2023.html` | `https://app.mokahr.com/campus-recruitment/zte/46903#/jobs` |
| COM0196 | `https://campus.vip.com` | `https://app-tc.mokahr.com/campus-recruitment/vipshophr/10039#/jobs` |
| COM0203 | `https://www.china-tower.com/Index/show/catid/10/id/1897.html` | `https://zhaopin.chinatowercom.cn/recruit#/index` |
| COM0279 | `https://career.joyson.com/campus` | `https://app.mokahr.com/campus-recruitment/joyson/94311#/jobs` |
| COM0331 | `https://www.jac.com.cn/zhuantinews/20260911/10715.html` | `https://zp.jac.com.cn:8444/recruit#/portal_job_list?job_class=campus` |
| COM0336 | `https://www.harbin-electric.com/zxns/xyzp.htm` | `https://hadian.zhaopin.com/jobs/index.html` |
| COM0366 | `https://www.yunnanbaiyao.com.cn/view/ynbyPc/1/16/view/9087.html` | `https://wecruit.hotjob.cn/SU6136b970bef57c3b638162c4/pb/school.html` |
| COM0424 | `https://www.hrbb.com.cn/shoujizhan/jrhx27/hxzp69/1282787/index.html` | `https://wisehr.hrbb.com.cn/pages/jobs/index.html` |
| COM0428 | `https://www.dahuatech.com/about/campus.html` | `https://dahua.zhiye.com/campus/jobs` |

## 复现与质量门禁

```sh
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest

# 本机保存的50家快照重新汇总；输出目录必须为空
uv run job-crawler bundle --inputs-file outputs/batch6-fifty-inputs.json \
  --output outputs/fifty-reexport

# 使用已登记的新适配器实时重跑某一来源
uv run job-crawler run --source COM0203 --window all --output outputs/tower-next
```

Ruff、ty、365 项离线测试通过。新增 24 项合同测试覆盖虚拟页码同步、重复分页、错详情ID、两个应届目录、公开状态、跨法人排除、时间语义、GBK解码请求和不同凭据模式缓存隔离。网页真实运行与离线测试分开记录。工作簿核对 50 家、11,176 行、13 列、日期格式、严格表 2,160 行及无公式注入通过。

全部岗位由程序导出到 ignored 的 outputs 目录；不提交原始网页/接口、联系人字段、Cookie、凭证或批量运行产物。当前累计 128 个来源已绑定支持，仍有 100 个填写链接的来源待适配。
