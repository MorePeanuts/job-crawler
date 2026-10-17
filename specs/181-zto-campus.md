# SPEC-181 中通快递公开校园项目

状态：开发中；SPEC-156 B组 COM0318。

## 目标与非目标

覆盖hr.zto.com校园入口school_project公开字典中的全部当届项目。本轮2027总部ZTO STAR（17）6条、省区青鸟（18）16条，schoolObject=[1]为应届、postType=2为校园。不纳入实习、社会或其他生态业务门户，不登录、不收藏、不申请。

## 输入输出与契约

首页公开getRecruitmentNews包含2027届校招公告144，正文明确毕业范围和报名截止2026年10月31日；项目年份需与公告一致，截止从明确的“简历投递的起止时间”章节解析。不得把岗位gmtModified当发布日期。

按公开页面路由/campus-position?object=1&projectId=项目ID进入目录，观察getPostInfoPageList的实际参数：postType=2、schoolObject=["1"]、项目ID，其他关键词、地区及类型筛选为空，pageNum从1、pageSize20。核对total/pages/pageNum/hasNextPage和每页行数，全部项目逐一闭合。

列表qualification为空不能代表缺失；必须按ID调用公开getPostInfoDetail，核对ID/标题/单位/地点/学历/状态并读取完整职责和任职资格。保留educationName、workPlaceNameStr、workPlaceDetail及controlCenterName。中通快递-管理培训生等页面展示前缀不作为多个岗位拆分。同标题不同城市按源ID保留。发布日期未知留空，校招公告截止可关联至当前年度项目。

## 失败行为与验收

项目或岗位重复、年度不一致、目录筛选残留、分页总数变化、提前空页、未知状态、详情错配或任职资格缺失均失败，保留成功记录。首页单位范围与实际详情必须核验；不因按钮文案而执行申请，适配器仅调用公开目录及详情查询。

回放覆盖多项目多页、详情要求完整、公告截止解析、未知状态/身份及计数错误；真实22条全目录、公共分类补全、只读审计通过后启用。更新日期不冒充发布时间。
