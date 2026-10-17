# SPEC-170 华为应届生岗位与意向展开

状态：开发中；SPEC-156 A 组 COM0021。

## 目标与非目标

完整接入华为官方校园“应届生职位”入口，不含实习、社会招聘、博士后和独立挑战课题。覆盖根目录全部地区、岗位类别和部门，不上传简历、不登录申请。

## 输入输出与观察契约

页面 `/cn/campus-recruitment-job-list?recruitmentType=FRESH_GRADUATE` 观察公开网关 recruitmentPosition/pub/getJobPage，JSON {curPage:1,pageSize:10,jobType:"CR",recruitmentType:["FRESH_GRADUATE"]}，status=SUCCESS。公开应用标识 X-HW-ID 必须从观察请求的查询参数与 public_headers 双重核对，并作为请求头传递；还需观察到的公开 X-Jalor-Tenantalias=hcm 请求头；缺失租户别名会返回 missing tenant code。同时保持观察到的 X-Language=zh_CN、X-Referer=https://career.huawei.com/cn、X-ALB-Gray=prod 公开页面上下文。传输层仅追加这些非凭据头到白名单，不采集或重放 CSRF/登录凭据。data.pageVO 包含 totalRows/totalPages/curPage/pageSize，data.result 当前 71 条父岗位、8 页。

根目录 advertisementId/jobId/advertisementsIntegrationId 必须区分。公开详情页面 `/cn/job-details?advertisementId=<advertisementId>` 加载 getRecruitmentPositionDetail（advertisementId）与 getPositionIntentionList（jobId）。详情身份、recruitType=CR/scenarioName=应届生核对，岗位方向数组逐条核对 jobId，positionIntentionId 在父岗位内唯一。

父岗位职责若为“请您详见岗位意向”不能当作完整正文。每个实际意向生成一行，稳定键为 advertisementId:positionIntentionId，标题“父岗位 - 方向名称”，职责 jobResponsibilities、要求 jobDemand、地点 jobPlaceName、部门 deptName，公开类别沿父岗位 categoryName。部门地点关联不再次拆行。无方向时仅在详情有真实完整正文时输出父岗位；占位或空正文则报告覆盖缺口。

列表/详情 lastUpdateDate 是“更新于”，不写发布日期；releaseDate 缺失则空，截止缺失则空。学历交公共补全，不能将整个校园项目的毕业学历套给每个岗位。根目录与各方向数组均保留可核对 scope，详情/方向及父列表证据关联，沿用 before_detail/remember。

## 失败行为与验收

未知筛选、业务失败、分页变动/重复、详情身份错配、实习混入、重复意向或无真实正文均显式报告并保留其他成功记录。公开请求 URL 从实际网络观察取得，不猜测接口或伪造会话。

回放验证多页父目录、方向展开去重、父/子身份、更新日期不冒充发布日期及局部失败。实时核对 71 父目录与全部意向，公共分类后审计通过才启用；实际展开数量由程序记录，不预设或凑数。
