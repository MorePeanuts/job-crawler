# SPEC-207 盛虹控股集团北森校园全目录

状态：计划实现；SPEC-156固定A组COM0044，尚未真实验收。

## 目标与非目标

接入盛虹控股集团有限公司北森门户https://shenghonggroup.zhiye.com/campus/jobs，覆盖Category=2所有板块、地区和年份的公开校园目录。新集团官网www.shenghongholding.com仍将校园招聘链接到2024年51job已结束页面，不能把该旧页面当集团当前零招聘。北森门户品牌及页脚主体为盛虹控股集团；2027石化虹途岗位与高校企业招聘简章五类岗位相符。保留新旧入口差异及公开身份依据。

校园首页展示盛虹控股0、盛虹印染2、化纤5、石化5，合计12。石化卡片链接带ClassificationTwo=6筛选，仅有5条；必须使用去除板块、地点、关键词、时间筛选的全目录12条，不能只采石化。非目标为社会招聘、实习、登录、投递、收藏或验证码操作；不宣称未在该集团统一门户发布的独立子公司渠道已覆盖。

## 真实契约与输入输出

/campus/jobs直接加载POST /api/Jobad/GetJobAdPageList，已观察PageIndex=0、PageSize=20、Category=["2"]、KeyWords=""、SpecialType=0、PortalId=""，DisplayFields为页面公开请求的Category/Kind/LocId/PostDate/WorkWeChatQrCode。首页概览另有PortalId及PageSize=1，不能替代完整列表。复用已观察请求，不增加未展示字段。Code=200、Count=12、Data当前12条且页面“没有更多了”；未来按页码推进，核对稳定总数、唯一ID、末页，重复/提前空失败。

详情路径/campus/detail?jobAdId=Id正常打开后观察GET /api/JobAd/GetJobAdInfo，原样保留category=2及页面displayFields，只改变当前岗位ID。详情Code=200、Data.Id对应目录、CategoryId=2，Duty/Require为完整职责和任职要求。正文中的硕士要求交给公共学历处理，结构化Degree为空则不猜填。Org、DetailAddress本次样本均空，不用集团注册地址补地址，不从匿名OrgId推定法人。LocNames保持全部省市区，多个城市不随意缩为一个。

PostDate是页面明确“发布”时间；EndTime为0001哨兵时留空，不能用ChangeDate、采集日期或毕业年份代替。当前5条2027虹途发布于2026-09-15，其余7条印染/化纤发布于2024-08；较早发布不等于已截止，应读取完整详情保留原日期，由公共筛选处理明确截止与实习。不把高校简章更新时间覆盖门户职位发布日期。

使用Zhiye公共契约，regular_only=True；列表需确认CategoryId=2及Kind为全职/实习，未知类别失败。源ID唯一，不按标题或板块合并。详情前before_detail、成功后remember，逐岗保留列表/详情证据；未知日期首次读取，部分失败保留成功岗位、coverage不完整，不以空或异常启用。

## 验收条件

回放覆盖真实租户字段、无筛选全目录、多页/末页、板块筛选拒绝、详情ID/类别、缺失学历地址及0001日期、实习和旧发布时间。复用已有北森分页、局部失败及增量回归，新增本站有效字段样本。全量UV/Ruff/ty/pytest通过后临时绑定实采，12目录/12唯一/12详情核对，记录有效/信息/严格/待补全与具体限制；审计通过才正式绑定、更新A组输入并离线汇总发布。计划和探测不算正式验收。
